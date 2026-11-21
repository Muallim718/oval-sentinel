"""One command for focused tests, the official checker, and replay benchmarks.

Add --docker on a machine with Docker to build and check the actual sandbox.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(command, env=None):
    print("\n> " + " ".join(str(c) for c in command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", action="store_true")
    args = parser.parse_args()
    py = sys.executable
    run([py, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([py, "check/check.py", "--", py, "-u", "bot.py"])
    run([py, "tools/benchmark.py"])
    if args.docker:
        run(["docker", "build", "--platform", "linux/amd64", "-t", "oval-sentinel", "."])
        run([py, "check/check.py", "--map-dir", "/arena", "--", "docker", "run", "--rm", "-i",
             "--platform", "linux/amd64", "--network", "none", "--cpus", "1", "--memory", "512m",
             "--memory-swap", "512m", "--pids-limit", "128", "--cap-drop", "ALL", "--read-only",
             "--tmpfs", "/tmp:rw,size=64m", "--user", "65534:65534", "-v",
             f"{ROOT / 'arena'}:/arena:ro", "oval-sentinel"])
    else:
        print("\nLocal checks passed. Docker sandbox check was NOT run; use --docker or GitHub Actions.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
