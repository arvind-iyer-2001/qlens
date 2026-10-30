"""Find q source files under a root and reject things that are not q."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "graphify-out", "node_modules", "__pycache__"}
MAX_BYTES = 1_000_000
MAX_MEAN_LINE = 2_000

# a top-level line that plausibly is q: assignment, backslash command, bracket form, control form
_QISH = re.compile(
    r"^(?:\\|[A-Za-z_.][A-Za-z0-9_.]*(?:\[[^\]]*\])?\s*[:,]|\.?[A-Za-z_][\w.]*:|"
    r"(?:if|do|while)\[|\$\[|@\[|\.\[|\(|`|[A-Za-z_][\w.]*\s*\[|select\b|update\b|delete\b|exec\b|"
    r"system\b|show\b|-1\b)"
)


@dataclass
class Discovery:
    files: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)


def looks_like_q(data: bytes) -> tuple[bool, str]:
    """Content check. Returns (ok, reason)."""
    if not data.strip():
        return False, "empty"
    if b"\x00" in data[:8192]:
        return False, "binary (NUL byte)"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        bad = sum(1 for c in text[:8192] if ord(c) < 9 or 13 < ord(c) < 32)
        if bad > 8:
            return False, "binary (control bytes)"
    lines = text.splitlines()
    if sum(len(x) for x in lines) / max(len(lines), 1) > MAX_MEAN_LINE:
        return False, "mean line length too long (data file)"
    top = [
        x
        for x in lines
        if x and x[0] not in " \t/" and x.strip() not in ("\\", "/")
    ]
    if not top:
        return True, "comments only"
    if all(x.lstrip("-").replace(".", "").replace(",", "").isdigit() for x in top[:200]):
        return False, "numeric data"
    good = sum(1 for x in top if _QISH.match(x))
    if good / len(top) < 0.3:
        return False, f"only {good}/{len(top)} top-level lines look like q"
    return True, "ok"


def discover(root: str | Path, out_dir: str | Path | None = None) -> Discovery:
    root = Path(root).resolve()
    skip_out = Path(out_dir).resolve() if out_dir else None
    result = Discovery()
    if root.is_file():
        candidates = [root]
    else:
        candidates = []
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in SKIP_DIRS and not (skip_out and (here / d).resolve() == skip_out)
            )
            candidates.extend(here / f for f in sorted(filenames) if f.endswith(".q"))
    for p in candidates:
        try:
            if p.is_symlink() and not p.resolve().is_relative_to(root):
                result.skipped.append((p, "symlink outside root"))
                continue
            size = p.stat().st_size
            if size > MAX_BYTES:
                result.skipped.append((p, f"too large ({size} bytes)"))
                continue
            ok, why = looks_like_q(p.read_bytes())
        except OSError as e:
            result.skipped.append((p, f"unreadable: {e}"))
            continue
        (result.files.append(p) if ok else result.skipped.append((p, why)))
    return result
