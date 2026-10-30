"""Compare a built graph with a hand-labelled truth file (names, not ids)."""

from __future__ import annotations


def edge_keys(result: dict) -> set[tuple[str, str, str]]:
    lab = {n["id"]: n["label"] for n in result["nodes"]}
    return {(lab[e["source"]], lab[e["target"]], e["relation"]) for e in result["edges"]}


def evaluate(result: dict, truth: dict) -> dict:
    """truth: {"edges": [[src, dst, relation], ...], "nodes": [[label, kind], ...]}.
    Edges are scored over the relations the truth file mentions (so truth may ignore `contains`)."""
    want = {tuple(e) for e in truth["edges"]}
    rels = set(truth.get("relations") or {r for _, _, r in want})
    got = {k for k in edge_keys(result) if k[2] in rels}
    tp = want & got
    nodes_got = {(n["label"], n["kind"]) for n in result["nodes"]}
    nodes_want = {tuple(n) for n in truth.get("nodes", [])}
    return dict(
        precision=len(tp) / len(got) if got else 1.0,
        recall=len(tp) / len(want) if want else 1.0,
        extra=sorted(got - want),
        missing=sorted(want - got),
        nodes_missing=sorted(nodes_want - nodes_got),
    )
