"""Verify a reviewed local candidate and publish the approved Data Hub package."""

import argparse
import fcntl
import hashlib
import gzip
import json
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
SCOPE = "--scope=brycepjs-projects"


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


def archive(folder, tag):
    destination = ROOT / "private/backups" / tag
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        temp = Path(tmp) / "source-receipts.tar.gz"

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

        def checksum(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

        digest = checksum(temp)
        receipt = "SHA256SUMS"
        line = f"{digest}  {temp.name}\n"
        if destination.exists():
            if (destination / receipt).read_text() != line or checksum(destination / temp.name) != digest:
                raise ValueError("Local source backup checksum mismatch")
        else:
            (Path(tmp) / receipt).write_text(line)
            Path(tmp).rename(destination)


def unchanged_head(repo):
    cmd(["git", "fetch", "origin", "main"], repo)
    if git(repo, "rev-parse", "HEAD") != git(repo, "rev-parse", "FETCH_HEAD"):
        raise ValueError(f"Refresh {repo} before promoting an older deployment")


def clean(repo, paths):
    if git(repo, "branch", "--show-current") != "main":
        raise ValueError(f"Use main in {repo}")
    if git(repo, "diff", "--cached", "--name-only"):
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
    if names:
        raise ValueError(f"Local changes in the release paths in {repo}")
    cmd(["git", "fetch", "origin", "main"], repo)
    if git(repo, "rev-parse", "HEAD") != git(repo, "rev-parse", "FETCH_HEAD"):
        raise ValueError(f"Sync {repo} with origin/main before publication")


def stage_url(cwd, project):
    args = ["vercel", "deploy", "--prod", "--skip-domain", "--yes", SCOPE]
    raw = cmd(args, cwd, output=True).decode()
    matches = re.findall(
        r"https://" + project + r"-[a-z0-9]+-brycepjs-projects\.vercel\.app", raw
    )
    if not matches:
        raise ValueError("Cannot identify staged deployment URL")
    return matches[-1]


def publish(runid, pin, projects, verify_only, prepare_pr=False):
    if not re.fullmatch(r"[a-f0-9]{64}", pin):
        raise ValueError("Expected exact manifest SHA-256")
    root = ROOT / "private/route-publication"
    root.mkdir(parents=True, exist_ok=True)
    legacy = re.fullmatch(r"[1-9]\d*", str(runid))
    folder = root / str(runid) / "candidate" if legacy else Path(runid).resolve()
    if not folder.resolve().is_relative_to((ROOT / "private").resolve()) or not folder.is_dir():
        raise ValueError("Use a retained candidate directory under private/")
    with (root / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        work = root / (str(runid) if legacy else pin)
        work.mkdir(exist_ok=True)
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
        if prepare_pr:
            if git(ROOT, "branch", "--show-current") in ("", "main"):
                raise ValueError("Prepare a release on a named PR branch")
            if release.exists() or entry in ledger["approved"]:
                raise ValueError("Release already present. Inspect the prepared branch.")
            if git(ROOT, "status", "--porcelain", "--", *hub_paths):
                raise ValueError("Release paths contain unpublished changes")
            archive(folder, f"source-receipts-safe-routes-{version}-{pin[:12]}")
            with tempfile.TemporaryDirectory(dir=work) as t:
                ready = Path(t) / "package"
                shutil.copytree(folder / "package", ready)
                ready.rename(release)
            ledger["approved"].append(entry)
            pending = work / "release-ledger.pending"
            pending.write_text(json.dumps(ledger, indent=2) + "\n")
            pending.replace(ROOT / hub_paths[0])
            print("Run the maintainer checks and submit the package and ledger for owner PR review.")
            return
        clean(ROOT, ["."])
        if entry not in ledger["approved"] or checked_package(release, entry) != checked_package(folder / "package", entry):
            raise ValueError("Record the reviewed package and ledger on main before promotion")
        archive(folder, f"source-receipts-safe-routes-{version}-{pin[:12]}")
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
    p.add_argument("run", help="Local candidate directory, or an already retained historical run ID")
    p.add_argument("manifest_sha256")
    p.add_argument(
        "--projects",
        type=Path,
        default=Path.home() / "Documents/ChatGPT/bikewalk-provo",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--prepare-pr", action="store_true")
    args = p.parse_args()
    publish(args.run, args.manifest_sha256, args.projects, args.verify_only, args.prepare_pr)
