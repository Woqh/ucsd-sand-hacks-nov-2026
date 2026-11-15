#!/usr/bin/env python3
"""Keep codemap.md honest. Fails (exit 1) if:
  * a project file (tracked, or untracked-but-not-ignored) isn't mentioned in codemap.md, or
  * a file listed in a codemap table row doesn't exist.
Empty files (package markers like __init__.py) are exempt. Standard library only.

  python scripts/check_codemap.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
text = (ROOT / "codemap.md").read_text(encoding="utf-8")

files = subprocess.run(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
    cwd=ROOT, capture_output=True, text=True, check=True,
).stdout.split()
# The teammate's model repo is vendored whole (data, weights, results): it has its own README and gets ONE row.
VENDORED = ("posture_pipeline-main/",)
files = [f for f in files if (ROOT / f).is_file() and (ROOT / f).stat().st_size > 0 and not f.startswith(VENDORED)]

missing = [f for f in files if f not in text]

# first column of table rows: | `path` (optional note) | ... (skip anything that isn't a path-looking token)
listed = re.findall(r"^\|\s*`([^`]+)`[^|]*\|", text, flags=re.M)
dangling = [p for p in listed if ("/" in p or "." in p) and not (ROOT / p).exists()]

if missing:
    print("Not in codemap.md (add a row):")
    print("\n".join(f"  {f}" for f in missing))
if dangling:
    print("Listed in codemap.md but missing on disk (fix or remove the row):")
    print("\n".join(f"  {p}" for p in dangling))
# Nudge: this run changed files but didn't touch the codemap. Row *content* can still be stale
# even when every file is listed, so this is a warning (exit 0), not a failure.
status = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all"],
    cwd=ROOT, capture_output=True, text=True, check=True,
).stdout.splitlines()
changed = [line[3:].strip().strip('"') for line in status]
if changed and "codemap.md" not in changed:
    shown = ", ".join(changed[:8]) + (f", … (+{len(changed) - 8} more)" if len(changed) > 8 else "")
    print(f"WARNING: {len(changed)} file(s) changed but codemap.md did not: {shown}")
    print("         Confirm no row, flow or invariant in codemap.md needs updating.")

if missing or dangling:
    sys.exit(1)
print(f"codemap.md OK: {len(files)} files covered, {len(listed)} rows resolve.")
