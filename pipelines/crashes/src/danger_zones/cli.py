"""Installed routine command delegates to the maintained Hub checkout."""
from pathlib import Path
import os
import subprocess
import sys


def main():
    root = next((p for p in (Path.cwd(), *Path.cwd().parents)
                 if (p / "scripts/update_crashes.py").is_file()
                 and (p / "pipelines/crashes/src/danger_zones/config.py").is_file()), None)
    if root is None:
        print("Run bwp-update-crashes from the maintained Data Hub checkout.", file=sys.stderr)
        return 1
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(root), str(root / "pipelines/crashes/src")]))
    return subprocess.run([sys.executable, "-m", "scripts.update_crashes", *sys.argv[1:]], cwd=root, env=env).returncode
