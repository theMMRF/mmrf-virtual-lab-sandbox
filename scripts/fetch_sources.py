"""Fetch only pinned public repositories into ignored, disposable build contexts."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
for name, source in json.loads((root / "sources.json").read_text()).items():
    dest = root / ".sources" / name
    if dest.exists():
        actual = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(dest), "status", "--porcelain"], text=True)
        if actual != source["commit"] or dirty:
            raise SystemExit(f"Refusing to overwrite modified source context: {dest}")
        continue
    subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none", source["url"], str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "--detach", source["commit"]], check=True)
