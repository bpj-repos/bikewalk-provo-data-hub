"""Verify a reviewed GitHub Actions candidate and publish the approved Data Hub package."""

import argparse
import fcntl
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from scripts.build_catalog import checked_package, build
from scripts.safe_routes import DATASET

ROOT = Path(__file__).resolve().parents[1]
REPO = "bpj-repos/bikewalk-provo-data-hub"
SCOPE = "--scope=brycepjs-projects"
GEO = [
    "safe-school-routes",
    "safe-route-plan-features",
    "safe-routes-schools",
    "safe-route-stress-segments",
    "safe-route-stress-crossings",
]


def cmd(args, cwd=ROOT, env=None, output=False):
    p = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        check=True,
        env=env,
        stdout=subprocess.PIPE if output else None,
    )
    return p.stdout if output else None


def git(repo, *args):
    return cmd(["git", *args], repo, output=True).decode().strip()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(p):
    return json.loads(p.read_bytes())


def verify_candidate(folder, pin):
    report = load(folder / "review.json")
    if not re.fullmatch(r"\d+\.\d+\.\d+", report["version"]) or report["sha256"] != pin:
        raise ValueError("Run and approved SHA do not match")
    entry = dict(dataset=DATASET, version=report["version"], sha256=pin)
    package = folder / "package"
    files = checked_package(package, entry)
    if set(p.name for p in package.iterdir()) != set(files):
        raise ValueError("Unexpected unmanifested candidate file")
    sources = json.loads(files["sources.json"])
    receipt = load(folder / "receipt/receipt.json")
    if sources["receipts"] != receipt or report["sources"] != sources["bicycleStress"]:
        raise ValueError("Candidate provenance mismatch")
    for name, value in receipt.items():
        if (
            Path(name).name != name
            or sha((folder / "receipt" / name).read_bytes()) != value["sha256"]
        ):
            raise ValueError("Source receipt mismatch")
    s = sources["bicycleStress"]
    pins = {
        **s["pinnedResources"],
        **{k: v["sha256"] for k, v in s["modelInputs"].items()},
        "published-ways.geojson": s["comparisonSha256"],
    }
    for name, digest in pins.items():
        if (
            Path(name).name != name
            or sha((folder / "inputs" / name).read_bytes()) != digest
        ):
            raise ValueError("Upstream digest mismatch: " + name)
    if report["coverage"] != json.loads(files["stress-coverage.json"]):
        raise ValueError("Coverage mismatch")
    return entry, report


def download(runid, work):
    folder = work / "candidate"
    if folder.exists():
        return folder
    details = json.loads(
        cmd(
            [
                "gh",
                "run",
                "view",
                runid,
                "-R",
                REPO,
                "--json",
                "conclusion,headBranch,workflowName,headSha",
            ],
            output=True,
        )
    )
    if (details["headBranch"], details["workflowName"], details["conclusion"]) != (
        "main",
        "Monthly Safe Routes source review",
        "success",
    ):
        raise ValueError("Use a successful main-branch Safe Routes run")
    with tempfile.TemporaryDirectory(dir=work) as t:
        cmd(
            [
                "gh",
                "run",
                "download",
                runid,
                "-R",
                REPO,
                "-n",
                "safe-routes-review-" + runid,
                "-D",
                t,
            ]
        )
        Path(t).rename(folder)
    return folder


def ledger_check(entry, report):
    ledger = load(ROOT / "releases/release-ledger.json")
    withdrawn = {(w["dataset"], w["version"]) for w in ledger["withdrawn"]}
    if (DATASET, entry["version"]) in withdrawn:
        raise ValueError("Withdrawn version")
    latest = next(
        e
        for e in reversed(ledger["approved"])
        if e["dataset"] == DATASET and (DATASET, e["version"]) not in withdrawn
    )
    if latest not in (entry, report["previous"]):
        raise ValueError("Release superseded; refresh against the current pin")
    if any(
        e["dataset"] == DATASET and e["version"] == entry["version"] and e != entry
        for e in ledger["approved"]
    ):
        raise ValueError("Version already has different bytes")
    return ledger


def archive(folder, work, tag):
    asset = work / "source-receipts.tar.gz"
    if not asset.exists():
        temp = asset.with_suffix(".partial")

        def stable(info):
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if info.isdir() else 0o644
            return info

        with (
            temp.open("wb") as raw,
            gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream,
            tarfile.open(fileobj=stream, mode="w") as archive,
        ):
            for name in (
                "inputs",
                "receipt",
                "review.json",
                "changes.json",
                "campus.json",
                "school-coverage-review.txt",
                "unrated-review.json",
                "published-comparison.json",
            ):
                if (folder / name).is_file() or (folder / name).is_dir():
                    archive.add(folder / name, arcname=name, filter=stable)
        temp.rename(asset)
    # Use GitHub's stored asset digest; retries never overwrite a release or asset.
    existing = subprocess.run(
        ["gh", "release", "view", tag, "-R", REPO, "--json", "assets"],
        capture_output=True,
    )
    if existing.returncode:
        cmd(
            [
                "gh",
                "release",
                "create",
                tag,
                str(asset),
                "-R",
                REPO,
                "--latest=false",
                "--target",
                git(ROOT, "rev-parse", "HEAD"),
                "--title",
                tag,
                "--notes",
                "Private source receipts for the reviewed Safe Routes release.",
            ]
        )
    assets = json.loads(
        cmd(["gh", "release", "view", tag, "-R", REPO, "--json", "assets"], output=True)
    )["assets"]
    expected = "sha256:" + sha(asset.read_bytes())
    if not any(a["name"] == asset.name and a["digest"] == expected for a in assets):
        raise ValueError("Durable source backup checksum mismatch")


def unchanged_head(repo):
    cmd(["git", "fetch", "origin", "main"], repo)
    if git(repo, "rev-parse", "HEAD") != git(repo, "rev-parse", "FETCH_HEAD"):
        raise ValueError(f"Refresh {repo} before promoting an older deployment")


def clean(repo, paths, owned=()):
    if git(repo, "branch", "--show-current") != "main":
        raise ValueError(f"Use main in {repo}")
    if set(git(repo, "diff", "--cached", "--name-only").splitlines()) - set(owned):
        raise ValueError(f"Existing staged changes in {repo}")
    dirty = cmd(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "-z",
            "--",
            *paths,
        ],
        repo,
        output=True,
    )
    names = {r[3:].decode() for r in dirty.split(b"\0") if r}
    if names - set(owned):
        raise ValueError(f"Local changes in the release paths in {repo}")
    cmd(["git", "fetch", "origin", "main"], repo)
    if git(repo, "rev-parse", "HEAD") != git(repo, "rev-parse", "FETCH_HEAD"):
        raise ValueError(f"Sync {repo} with origin/main before publication")


def verified_push(repo, paths, message):
    cmd(["git", "add", "--", *paths], repo)
    cmd(["git", "diff", "--cached", "--check"], repo)
    cmd(["git", "commit", "--only", "-m", message, "--", *paths], repo)
    cmd(["git", "push", "origin", "main"], repo)
    return git(repo, "rev-parse", "HEAD")


def stage_url(cwd, project, prebuilt=False):
    args = ["vercel", "deploy", "--prod", "--skip-domain", "--yes", SCOPE]
    if prebuilt:
        args += ["--prebuilt"]
    raw = cmd(args, cwd, output=True).decode()
    matches = re.findall(
        r"https://" + project + r"-[a-z0-9]+-brycepjs-projects\.vercel\.app", raw
    )
    if not matches:
        raise ValueError("Cannot identify staged deployment URL")
    return matches[-1]


def publish(runid, pin, projects, verify_only):
    if not re.fullmatch(r"[1-9]\d*", runid) or not re.fullmatch(r"[a-f0-9]{64}", pin):
        raise ValueError("Expected numeric GitHub run and exact SHA-256")
    root = ROOT / "private/route-publication"
    root.mkdir(parents=True, exist_ok=True)
    with (root / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        work = root / runid
        work.mkdir(exist_ok=True)
        folder = download(runid, work)
        entry, report = verify_candidate(folder, pin)
        ledger = ledger_check(entry, report)
        version = entry["version"]
        # Rebuild from received bytes before recording or publishing the release.
        with tempfile.TemporaryDirectory(dir=work) as t:
            cmd([sys.executable, "-m", "scripts.rebuild_route_candidate", folder, t])
        if verify_only:
            print(
                json.dumps({"verified": entry, "changes": report["changes"]}, indent=2)
            )
            return
        projects = projects.resolve()
        release = ROOT / "releases/datasets" / DATASET / version
        statefile = work / "publication.json"
        state = load(statefile) if statefile.exists() else {}

        def save(k, v):
            state[k] = v
            tmp = statefile.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            tmp.replace(statefile)

        if state.get("pin", pin) != pin:
            raise ValueError("Publication state pin mismatch")
        save("pin", pin)
        hub_paths = ["releases/release-ledger.json", str(release.relative_to(ROOT))]
        # A retry may resume a locally committed but not yet pushed release.
        for repo, marker in (
            (ROOT, release / "datapackage.json"),
        ):
            ahead = git(repo, "rev-list", "--count", "origin/main..HEAD")
            if ahead == "1" and marker.exists() and sha(marker.read_bytes()) == pin:
                paths = git(
                    repo, "diff", "--name-only", "origin/main..HEAD"
                ).splitlines()
                allowed = hub_paths
                if all(
                    any(p == a or p.startswith(a + "/") for a in allowed) for p in paths
                ):
                    cmd(["git", "push", "origin", "main"], repo)
        # Resume only publication-owned bytes after a failed test, commit, or push.
        head_ledger = json.loads(git(ROOT, "show", "HEAD:releases/release-ledger.json"))
        expected_ledger = json.loads(json.dumps(head_ledger))
        if entry not in expected_ledger["approved"]:
            expected_ledger["approved"].append(entry)
        if ledger not in (head_ledger, expected_ledger):
            raise ValueError("Unexpected local release ledger edits")
        hub_owned = (
            {"releases/release-ledger.json"} if ledger == expected_ledger else set()
        )
        if release.exists():
            expected_files = checked_package(folder / "package", entry)
            if {f.name for f in release.iterdir()} != set(expected_files) or any(
                (release / n).read_bytes() != v for n, v in expected_files.items()
            ):
                raise ValueError("Existing release differs from approved candidate")
            hub_owned.update(
                str((release / n).relative_to(ROOT)) for n in expected_files
            )
        clean(ROOT, ["."], hub_owned)
        archive(folder, work, f"source-receipts-safe-routes-{version}-{pin[:12]}")
        if entry not in head_ledger["approved"]:
            if not release.exists():
                with tempfile.TemporaryDirectory(dir=work) as t:
                    ready = Path(t) / "package"
                    shutil.copytree(folder / "package", ready)
                    ready.rename(release)
            ledger = expected_ledger
            pending = work / "release-ledger.pending"
            pending.write_text(json.dumps(ledger, indent=2) + "\n")
            pending.replace(ROOT / "releases/release-ledger.json")
            cmd(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests/hub",
                    "-t",
                    ".",
                ],
                env={**os.environ, "BWP_SOURCE_REPO": str(projects)},
            )
            verified_push(ROOT, hub_paths, "Publish reviewed Safe Routes " + version)
        producer = git(
            ROOT, "log", "-1", "--format=%H", "--", str(release.relative_to(ROOT))
        )
        if not producer or sha((release / "datapackage.json").read_bytes()) != pin:
            raise ValueError("Published package mismatch")
        ledger_sha = sha((ROOT / "releases/release-ledger.json").read_bytes())
        stage = work / ("hub-stage-" + ledger_sha[:12])
        if state.get("hubLedger") != ledger_sha:
            state.pop("hubURL", None)
            state.pop("hubLive", None)
            save("hubLedger", ledger_sha)
        if not stage.exists():
            with tempfile.TemporaryDirectory(dir=work) as t:
                ready = Path(t) / "hub"
                build(projects, ready)
                ready.rename(stage)
        if "hubURL" not in state:
            cmd(
                [
                    "vercel",
                    "link",
                    "--yes",
                    "--project",
                    "bikewalk-provo-data-hub",
                    SCOPE,
                ],
                stage,
            )
            save("hubURL", stage_url(stage, "bikewalk-provo-data"))
        verify = [sys.executable, ROOT / "scripts/verify_public_catalog.py", "public"]
        if not state.get("hubLive"):
            cmd([*verify, "--stage", state["hubURL"]], stage)
            unchanged_head(ROOT)
            cmd(["vercel", "promote", state["hubURL"], "--yes", SCOPE], stage)
        cmd(verify, stage)
        save("hubLive", True)
        # Map adoption is reviewed and published independently by Streets Watch.
        save("verified", True)
        print(json.dumps(state, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run")
    p.add_argument("manifest_sha256")
    p.add_argument(
        "--projects",
        type=Path,
        default=Path.home() / "Documents/ChatGPT/bikewalk-provo",
    )
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args()
    publish(args.run, args.manifest_sha256, args.projects, args.verify_only)
