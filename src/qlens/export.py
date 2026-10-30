"""Export a qlens graph in the shape graphify's AST step produces ({nodes, edges}), no graphify import.

Node ids follow graphify's rule `{parent_dir}_{file_stem}_{entity}`, lowercase, `[a-z0-9_]` only, so ids
line up with what graphify's own extractors and its semantic pass generate. Lowercasing can merge q names
that differ only by case (`l` and `L`); the later one gets a short stable hash suffix so ids stay unique.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

RELATION_MAP = {
    "contains": "contains",
    "calls": "calls",
    "reads": "references",
    "uses": "references",
    "writes": "writes",
    "imports": "imports",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _stem(path: str | None) -> str:
    if not path:
        return "external"
    p = PurePosixPath(path)
    parent = p.parent.name
    stem = _norm(p.stem)
    return f"{_norm(parent)}_{stem}" if parent else stem


def to_graphify(graph: dict) -> dict:
    nodes_in = sorted(graph["nodes"], key=lambda n: (n["file"] or "", n["label"], n["id"]))
    ids: dict[str, str] = {}  # qlens id -> graphify id
    taken: dict[str, str] = {}  # graphify id -> qlens id
    for n in nodes_in:
        if n["kind"] == "file":
            base = _stem(n["file"])
        else:
            base = f"{_stem(n['file'])}_{_norm(n['label']) or 'x'}"
        gid = base
        if gid in taken and taken[gid] != n["id"]:
            gid = f"{base}_{hashlib.sha1(n['id'].encode()).hexdigest()[:6]}"
        taken[gid] = n["id"]
        ids[n["id"]] = gid

    out_nodes = []
    for n in nodes_in:
        out_nodes.append(
            {
                "id": ids[n["id"]],
                "label": n["label"],
                "file_type": "code",
                "source_file": n["file"],
                "source_location": f"L{n['line']}" if n.get("line") else None,
                "source_url": None,
                "captured_at": None,
                "author": None,
                "contributor": None,
                "qlens_kind": n["kind"],
                "qlens_tier": n["tier"],
                "qlens_evidence": n["evidence"],
                "confidence": n["confidence"],
                "confidence_score": n["confidence_score"],
            }
        )
    out_edges = []
    for e in graph["edges"]:
        if e["source"] not in ids or e["target"] not in ids:
            continue
        out_edges.append(
            {
                "source": ids[e["source"]],
                "target": ids[e["target"]],
                "relation": RELATION_MAP.get(e["relation"], e["relation"]),
                "confidence": e["confidence"],
                "confidence_score": e["confidence_score"],
                "source_file": e["file"],
                "source_location": f"L{e['line']}" if e.get("line") else None,
                "weight": 1.0,
                "qlens_relation": e["relation"],
                "qlens_tier": e["tier"],
                "qlens_evidence": e["evidence"],
            }
        )
    return {"nodes": out_nodes, "edges": out_edges, "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
