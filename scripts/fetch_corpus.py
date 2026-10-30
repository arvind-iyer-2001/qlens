"""Fetch public q repos into corpora/ (gitignored) and write corpora/MANIFEST.json (committed).

Data only: repos are cloned shallow with hooks disabled and are never executed here.
Usage: uv run python scripts/fetch_corpus.py --limit 250
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from qlens.discovery import discover

ROOT = Path(__file__).resolve().parent.parent
CORPORA = ROOT / "corpora"
QUERIES = [["--language=q"], ["--topic=kdb"], ["--topic=kdb-plus"], ["--topic=kdbq"], ["--topic=q-language"]]


def search(limit: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for q in QUERIES:
        cp = subprocess.run(
            ["gh", "search", "repos", *q, "--sort=stars", "--limit", "100", "--json", "fullName,size,stargazersCount"],
            capture_output=True, text=True,
        )  # fmt: skip
        if cp.returncode != 0:
            print(f"search {q} failed: {cp.stderr.strip()[:200]}", file=sys.stderr)
            continue
        for r in json.loads(cp.stdout):
            seen.setdefault(r["fullName"], r)
    return sorted(seen.values(), key=lambda r: (-r["stargazersCount"], r["fullName"]))[:limit]


def clone(full: str) -> Path | None:
    dest = CORPORA / full.replace("/", "__")
    if dest.exists():
        return dest
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}
    cp = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "clone", "--depth", "1", "--no-tags", "--quiet",
         f"https://github.com/{full}.git", str(dest)],
        capture_output=True, text=True, env=env, timeout=300,
    )  # fmt: skip
    if cp.returncode != 0:
        print(f"clone {full} failed: {cp.stderr.strip()[:200]}", file=sys.stderr)
        return None
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=250)
    ap.add_argument("--max-size-kb", type=int, default=200_000)
    a = ap.parse_args()
    CORPORA.mkdir(exist_ok=True)
    manifest_path = CORPORA / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for r in search(a.limit * 2):
        if len(manifest) >= a.limit:
            break
        full = r["fullName"]
        if full in manifest or r["size"] > a.max_size_kb:
            continue
        dest = clone(full)
        if not dest:
            continue
        files = discover(dest).files
        if not files:  # not q after the content check
            subprocess.run(["rm", "-rf", str(dest)])
            continue
        sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        manifest[full] = dict(dir=dest.name, commit=sha, q_files=len(files), stars=r["stargazersCount"])
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
        print(f"{full}: {len(files)} q files @ {sha[:8]}")
    print(f"{len(manifest)} repos in manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
