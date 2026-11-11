"""Prepare and independently rebuild a private monthly Safe Routes candidate."""
import argparse
import fcntl
import os
import sys
import plistlib
import shlex
from datetime import datetime
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.umask(0o077)
    runs = ROOT / "private/candidates"
    runs.mkdir(parents=True, exist_ok=True)
    with (runs / "monthly-route-review.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = runs / datetime.now().strftime("%Y-%m-%d-safe-routes-%H%M%S")
        run.mkdir()
        candidate = run / "candidate"
        with (run / "run.log").open("x") as log:
            for module, args in [
                ("scripts.refresh_route_sources", [candidate]),
                ("scripts.rebuild_route_candidate", [candidate, run / "rebuild"]),
            ]:
                subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT,
                               stdout=log, stderr=subprocess.STDOUT, check=True)
        from scripts.route_refresh_summary import summary
        (run / "review.md").write_text(summary(candidate, candidate.relative_to(ROOT)))
        print(run.relative_to(ROOT))


def install():
    """Install the reviewed schedule with an external checkout guard."""
    os.umask(0o077)
    logs = ROOT / "private/route-publication"
    logs.mkdir(parents=True, exist_ok=True)
    # The guard lives outside tracked source so a contributor branch cannot remove it.
    guard = f"""set -eu
cd {shlex.quote(str(ROOT))}
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
exec {shlex.quote(sys.executable)} -m scripts.monthly_route_review
"""
    destination = Path.home() / "Library/LaunchAgents/org.bikewalkprovo.safe-routes.plist"
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = dict(
        Label="org.bikewalkprovo.safe-routes",
        ProgramArguments=["/bin/sh", "-c", guard],
        StartCalendarInterval=dict(Day=1, Hour=7, Minute=41),
        EnvironmentVariables=dict(PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"),
        StandardOutPath=str(logs / "monthly.stdout.log"),
        StandardErrorPath=str(logs / "monthly.stderr.log"),
    )
    payload = plistlib.dumps(data)
    if destination.exists() and destination.read_bytes() != payload:
        raise ValueError("Existing LaunchAgent differs. Review it before replacing.")
    destination.write_bytes(payload)
    print(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-launchagent", action="store_true")
    args = parser.parse_args()
    install() if args.install_launchagent else main()
