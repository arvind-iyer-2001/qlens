"""Merge dynamic (live q) evidence into the static graph: tiers D2/D3, S-refuted, missed, indirect."""

from __future__ import annotations

from .classify import CALL  # noqa: F401  (relations are strings on edges)
from .scoring import DEFAULT_SCORES, label

REF_RELATIONS = ("calls", "reads", "writes", "uses")
IMPLICIT = "no top-level definition"


def _set(obj: dict, tier: str, extra: str) -> None:
    obj["tier"] = tier
    obj["confidence_score"] = DEFAULT_SCORES[tier]
    obj["confidence"] = label(obj["confidence_score"])
    obj["evidence"] = f"{obj['evidence']}; {extra}"


def merge(g, files: list[dict], dyn: dict, defs_index: dict) -> dict:
    m = dict(
        files_loaded=0, files_failed=0, files_process_failed=0,
        defs_agree=0, defs_refuted=0, defs_missed=0,
        agree=0, refuted=0, missed=0, indirect=0, indirect_agree=0, indirect_refuted=0, dangling=0, ns_mismatch=0,
    )  # fmt: skip
    load_results = []
    out_edges: dict[str, list[tuple]] = {}
    for k, e in g.edges.items():
        if e["relation"] in REF_RELATIONS:
            out_edges.setdefault(e["source"], []).append(k)
    by_file: dict[str, list[dict]] = {}
    for n in g.nodes.values():
        if n["kind"] in ("function", "variable", "table") and n["file"]:
            by_file.setdefault(n["file"], []).append(n)

    for f in files:
        rel, dr = f["rel"], dyn.get(f["rel"])
        if dr is None:
            continue
        load_results.append(dict(file=rel, loaded=dr.loaded, error=dr.error, dep_errors=dr.dep_errors, failure=dr.failure))
        if dr.failure:
            m["files_process_failed"] += 1
            continue
        m["files_loaded" if dr.loaded else "files_failed"] += 1
        static_q = set()
        for n in by_file.get(rel, []):
            q = n["label"]
            static_q.add(q)
            info = dr.defs.get(q)
            if info is not None:
                _set(n, "D2", f"confirmed after load (q type {info['type']})")
                if info["type"] == 100 and n["kind"] == "variable":
                    n["kind"] = "function"
                m["defs_agree"] += 1
            elif dr.loaded and IMPLICIT not in n["evidence"]:
                _set(n, "S-refuted", "file loaded in q but this name does not exist afterwards")
                m["defs_refuted"] += 1
        for q, info in dr.defs.items():
            if q not in static_q:
                m["defs_missed"] += 1
                from .graph import make_id

                nid = make_id(rel, q)
                if nid not in g.nodes:
                    kind = "function" if info["type"] == 100 else "variable"
                    g.node(nid, q, kind, rel, None, "D2", f"defined at runtime (q type {info['type']}); static pass did not see it")
                    g.edge(f["id"], nid, "contains", "D2", "defined at runtime", rel, None)
                    defs_index.setdefault(q, []).append(nid)
        # reference edges of live functions
        for nid, fi in g.fn.items():
            if fi["file"] != rel:
                continue
            info = dr.defs.get(fi["name"])
            if info is None or info["type"] != 100 or "free" not in info:
                continue
            ctx = ("." + info["ctx"]) if info.get("ctx") else ""
            if ctx != fi["ns"]:
                m["ns_mismatch"] += 1
                g.diagnostics.append(dict(file=rel, line=None, error=f"namespace context: static {fi['ns'] or '.'} vs live {ctx or '.'} for {fi['name']}", text=""))
            dfree = set(info.get("free_all") or info["free"])
            for key in out_edges.get(nid, []):
                e = g.edges[key]
                raws = g.raw.get(key, set())
                if e["tier"] == "S-unresolved":
                    m["dangling"] += 1
                    continue
                if raws & dfree:
                    if e["tier"] == "S-indirect":
                        m["indirect"] += 1
                        m["indirect_agree"] += 1
                    _set(e, "D3", "confirmed by value of the loaded function")
                    m["agree"] += 1
                elif raws:
                    if e["tier"] == "S-indirect":
                        m["indirect_refuted"] += 1
                    _set(e, "S-refuted", "name absent from the free names of the live function")
                    m["refuted"] += 1
            m["missed"] += len(dfree - fi["free"])
    m["load_results"] = load_results
    return m
