"""Hub publication preserves the consumer checkout and can resume after a failed verification."""

import contextlib
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts import publish_route_update as p


def repo(root, name):
    bare = root / (name + ".git")
    working = root / name
    p.cmd(["git", "init", "-q", "--bare", "--initial-branch=main", bare])
    p.cmd(["git", "clone", "-q", bare, working])
    p.git(working, "config", "user.name", "Test")
    p.git(working, "config", "user.email", "test@example.invalid")
    return working


class RehearsePublication(unittest.TestCase):
    def test_retry_does_not_modify_or_deploy_the_map_consumer(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            hub = repo(d, "hub")
            projects = repo(d, "projects")
            path = "apps/maps/public/data/safe-routes"
            app = projects / "apps/maps"
            routes = projects / path
            package = d / "candidate/package"
            package.mkdir(parents=True)
            routes.mkdir(parents=True)
            old = {"dataset": p.DATASET, "version": "1.2.0", "sha256": "1" * 64}
            (hub / "releases/datasets" / p.DATASET).mkdir(parents=True)
            (hub / ".gitignore").write_text("/private/\n")
            (hub / "releases/release-ledger.json").write_text(
                json.dumps({"approved": [old], "withdrawn": []})
            )
            (routes / "datapackage.json").write_bytes(b"old")
            for r in [hub, projects]:
                p.git(r, "add", ".")
                p.git(r, "commit", "-qm", "Baseline")
                p.git(r, "push", "origin", "main")
            files = []
            for k in p.GEO:
                n = k + ".geojson"
                raw = b'{"type":"FeatureCollection","features":[]}'
                (package / n).write_bytes(raw)
                files.append(
                    {
                        "path": n,
                        "hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw),
                    }
                )
            manifest = json.dumps(
                {"version": "1.3.0", "name": p.DATASET, "resources": files}
            ).encode()
            (package / "datapackage.json").write_bytes(manifest)
            pin = hashlib.sha256(manifest).hexdigest()
            entry = dict(old, version="1.3.0", sha256=pin)
            report = dict(previous=old, changes={})
            publish = []
            tests = [False]
            original = p.cmd

            def command(args, cwd=None, **opts):
                command = list(map(str, args))
                if command[0] == "git":
                    return original(args, cwd or hub, **opts)
                if command[0] == "npm" or "scripts/hub-update.py" in command:
                    self.fail("Hub publication must not operate the map consumer")
                if "scripts/verify_public_catalog.py" in " ".join(command) and not tests[0]:
                    tests[0] = True
                    raise subprocess.CalledProcessError(1, command)
                if command[:2] == ["vercel", "promote"]:
                    publish.append(command[2])
                return b""

            with contextlib.ExitStack() as st:
                for k, v in dict(
                    ROOT=hub,
                    cmd=command,
                    download=lambda *_: package.parent,
                    verify_candidate=lambda *_: (entry, report),
                    archive=lambda *_: None,
                    build=lambda proj, dest: dest.mkdir(),
                    stage_url=lambda cwd, name, *args: name,
                ).items():
                    st.enter_context(patch.object(p, k, v))
                with self.assertRaises(subprocess.CalledProcessError):
                    p.publish("123", pin, projects, False)
                self.assertEqual(publish, [])
                p.publish("123", pin, projects, False)
                p.publish("123", pin, projects, False)
                self.assertEqual(
                    publish, ["bikewalk-provo-data"]
                )
                for repo_ in (hub, projects):
                    self.assertEqual(
                        p.git(repo_, "rev-parse", "HEAD"),
                        p.git(repo_, "rev-parse", "origin/main"),
                    )

                self.assertEqual((routes / "datapackage.json").read_bytes(), b"old")
                self.assertEqual(p.git(projects, "status", "--porcelain"), "")
