#!/usr/bin/env python3
"""Push the whole project to GitHub via the git data API.

The sandbox has no git credentials, so `git push` cannot work. This walks the
working tree, creates a blob per file, assembles a tree, commits it, and points
the branch at the commit. Text files go up as utf-8; binaries as base64.

Usage: python3 scripts/push_to_github.py <owner> <repo> <branch>
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories and files that must never be pushed.
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv", "node_modules"}
SKIP_SUFFIX = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".log"}
SKIP_NAMES = {".DS_Store", "proteoscope.db", "prod_check.db"}

BINARY_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".woff", ".woff2"}


def collect_files() -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_NAMES:
                continue
            p = Path(dirpath) / name
            if p.suffix in SKIP_SUFFIX:
                continue
            out.append(p)
    return sorted(out)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: push_to_github.py <owner> <repo> <branch>", file=sys.stderr)
        return 2
    owner, repo, branch = sys.argv[1], sys.argv[2], sys.argv[3]

    files = collect_files()
    print(f"{len(files)} files to push")

    # Emit a manifest the caller (the agent) turns into MCP calls. We do not
    # call the API from here — the MCP tool is the only authenticated path.
    manifest = []
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        raw = p.read_bytes()
        if p.suffix.lower() in BINARY_SUFFIX:
            manifest.append({"path": rel, "encoding": "base64", "content": base64.b64encode(raw).decode()})
        else:
            try:
                manifest.append({"path": rel, "encoding": "utf-8", "content": raw.decode("utf-8")})
            except UnicodeDecodeError:
                manifest.append(
                    {"path": rel, "encoding": "base64", "content": base64.b64encode(raw).decode()}
                )

    out = ROOT / ".push_manifest.json"
    out.write_text(json.dumps(manifest, indent=1))
    total = sum(len(m["content"]) for m in manifest)
    print(f"manifest written: {out} ({total} chars of payload)")
    for m in manifest:
        print(f"  {m['path']}  [{m['encoding']}] {len(m['content'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
