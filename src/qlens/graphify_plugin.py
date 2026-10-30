"""graphify extractor plugin for q files. Does not import graphify: graphify reads the plain dict below.

graphify finds it through the entry-point group `graphify.extractors` (see pyproject.toml); installing qlens is
all it takes. qlens resolves names across files, so graphify hands over every `.q` file at once (`extract_batch`).

Environment: QLENS_GRAPHIFY_EXECUTE=1 adds the dynamic pass (runs the q code in the sandbox; off by default).
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .export import to_graphify
from .graph import analyse
from .sandbox import find_q

try:
    _VERSION = version("qlens")
except PackageNotFoundError:  # running from a source tree
    _VERSION = "dev"


def _available() -> str | None:
    try:
        find_q()
    except Exception as exc:
        return f"q is needed to parse q files and was not found ({exc})"
    return None


def _split(export: dict, root: Path, wanted: set[str]) -> dict[str, dict]:
    """Group the export by file. A file gets the nodes it defines and the edges that start at one of them;
    a node defined outside the batch (or nowhere) is attached to the first file that references it."""
    by_id = {n["id"]: n for n in export["nodes"]}
    out: dict[str, dict] = {}
    placed: set[str] = set()

    def slot(rel: str) -> dict | None:
        key = str((root / rel).resolve())
        return out.setdefault(key, {"nodes": [], "edges": []}) if key in wanted else None

    def absolute(n: dict, rel: str) -> dict:
        return {**n, "source_file": str((root / rel).resolve())}

    for n in export["nodes"]:
        rel = n.get("source_file")
        s = slot(rel) if rel else None
        if s is not None:
            s["nodes"].append(absolute(n, rel))
            placed.add(n["id"])
    for e in export["edges"]:
        owner = by_id.get(e["source"], {}).get("source_file") or e.get("source_file")
        s = slot(owner) if owner else None
        if s is None:
            continue
        tgt = by_id.get(e["target"])
        if tgt is not None and e["target"] not in placed:
            s["nodes"].append(absolute(tgt, tgt.get("source_file") or owner))
            placed.add(e["target"])
        s["edges"].append({**e, "source_file": str((root / owner).resolve())})
    return out


def extract_batch(paths: list[Path], ctx) -> dict[Path, dict]:
    files = [Path(p).resolve() for p in paths]
    root = Path(os.path.commonpath([str(p.parent) for p in files]))
    execute = os.environ.get("QLENS_GRAPHIFY_EXECUTE") == "1"
    ctx.log(f"  qlens: analysing {len(files)} q files under {root}" + (" (with the dynamic pass)" if execute else ""))
    graph = analyse(root, execute=execute)
    by_file = _split(to_graphify(graph), root, {str(p) for p in files})
    ctx.log(f"  qlens: {sum(len(v['nodes']) for v in by_file.values())} nodes, {sum(len(v['edges']) for v in by_file.values())} edges")
    return {p: by_file[str(p)] for p in files if str(p) in by_file}


PLUGIN = {
    "name": "qlens",
    "suffixes": [".q"],
    "extract_batch": extract_batch,
    "available": _available,
    "cache_key": _VERSION,
    "api": 1,
}
