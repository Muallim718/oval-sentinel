"""Check project size and create a clean, deterministic ZIP beside this folder.

--check-commit checks Git's actual HEAD tree (the submitted commit) without zipping.
"""
import argparse
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 20_000_000
EXCLUDED = {".git", "__pycache__", ".venv", "test-results", ".pytest_cache"}


def files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not any(part in EXCLUDED for part in p.relative_to(ROOT).parts):
            if p.suffix not in {".pyc", ".pyo", ".zip"} and p.name != ".env":
                yield p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-commit", action="store_true")
    args = parser.parse_args()
    if args.check_commit:
        data = subprocess.check_output(["git", "ls-tree", "-r", "-l", "-z", "HEAD"], cwd=ROOT)
        sizes = [int(entry.split(b"\t",1)[0].split()[-1]) for entry in data.split(b"\0") if entry]
        total = sum(sizes)
        print(f"HEAD tree: {len(sizes)} files; {total:,} bytes / {LIMIT:,} bytes allowed")
    else:
        paths = list(files())
        total = sum(p.stat().st_size for p in paths)
        print(f"Project: {len(paths)} files; {total:,} bytes / {LIMIT:,} bytes allowed")
    if total > LIMIT:
        raise SystemExit("Project exceeds the 20 MB submission limit")
    if not args.check_commit:
        output = ROOT.parent/f"{ROOT.name}.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in paths:
                entry = zipfile.ZipInfo(f"{ROOT.name}/{p.relative_to(ROOT).as_posix()}", (2026,11,21,0,0,0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                z.writestr(entry, p.read_bytes())
        print(f"Created {output} ({output.stat().st_size:,} compressed bytes)")


if __name__ == "__main__":
    main()
