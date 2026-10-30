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


def _dict_key_of(q: str, defs: dict) -> str | None:
    """The live dictionary that `q` resolves through (`lin.send` is key `send` of the dict `lin`), else None."""
    head, dot, key = q.rpartition(".")
    info = defs.get(head) if dot and head else None
    if info is not None and info["type"] == 99 and key in info.get("keys", ()):
        return head
    return None


def merge(g, files: list[dict], dyn: dict, defs_index: dict) -> dict:
    m = dict(
        files_loaded=0, files_failed=0, files_process_failed=0,
        defs_agree=0, defs_refuted=0, defs_missed=0, defs_elsewhere=0,
        agree=0, refuted=0, missed=0, indirect=0, indirect_agree=0, indirect_refuted=0, dangling=0, ns_mismatch=0,
    )  # fmt: skip
    m["examples"] = []
    by_rel = {f["rel"]: f for f in files}
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
            via = _dict_key_of(q, dr.defs) if info is None else None
            if info is not None:
                _set(n, "D2", f"confirmed after load (q type {info['type']})")
                if info["type"] == 100 and n["kind"] == "variable":
                    n["kind"] = "function"
                m["defs_agree"] += 1
            elif via is not None:
                _set(n, "D2", f"confirmed after load (a key of the dictionary {via})")
                m["defs_agree"] += 1
            elif dr.loaded and IMPLICIT not in n["evidence"] and n["id"] not in g.cond:
                _set(n, "S-refuted", "file loaded in q but this name does not exist afterwards")
                m["defs_refuted"] += 1
                if len([x for x in m["examples"] if x["kind"] == "def_refuted"]) < 12:
                    m["examples"].append(dict(kind="def_refuted", file=rel, name=q, line=n["line"], static_kind=n["kind"], evidence=n["evidence"][:140],
                                              live_names_sample=sorted(dr.defs)[:15]))  # fmt: skip
        for q, info in dr.defs.items():
            elsewhere = sorted({g.nodes[c]["file"] for c in defs_index.get(q, []) if g.nodes[c]["file"] not in (rel, None)})
            if q not in static_q and elsewhere:
                # defined by a file this one loaded at runtime (computed `\l` path, `set` ...): a real dependency, not a miss
                m["defs_elsewhere"] += 1
                if len(elsewhere) == 1 and elsewhere[0] in by_rel:
                    other = by_rel[elsewhere[0]]
                    g.edge(f["id"], other["id"], "imports", "D2", f"{q} became defined while loading {rel}; defined in {elsewhere[0]} (runtime load)", rel, None)
                continue
            container = info["type"] == 99 and any(o.startswith(q + ".") for o in [*static_q, *dr.defs])
            if q not in static_q and not container:  # a namespace/dict holding other names is not a missed definition
                m["defs_missed"] += 1
                if len([x for x in m["examples"] if x["kind"] == "def_missed"]) < 12:
                    m["examples"].append(dict(kind="def_missed", file=rel, name=q, live_type=info["type"], static_names_sample=sorted(static_q)[:15]))
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
            if nid in g.redef:
                continue  # defined more than once in this file: live q holds only the last, cannot judge edges
            ctxname = info.get("ctx") or ""  # q lists the context namespace and a same-named variable as one entry
            dfree = set(info.get("free_all") or info["free"])
            for key in out_edges.get(nid, []):
                e = g.edges[key]
                raws = g.raw.get(key, set()) - {ctxname}
                if not raws:
                    continue
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
                    if len([x for x in m["examples"] if x["kind"] == "refuted"]) < 12:
                        m["examples"].append(dict(kind="refuted", file=rel, fn=fi["name"], names=sorted(raws), role=e["relation"], line=e["line"],
                                                  live_free=sorted(dfree)[:20], static_free=sorted(fi["free"])[:20], live_ctx=info.get("ctx"), static_ns=fi["ns"]))  # fmt: skip
                    if e["tier"] == "S-indirect":
                        m["indirect_refuted"] += 1
                    _set(e, "S-refuted", "name absent from the free names of the live function")
                    m["refuted"] += 1
            extra = dfree - fi["free"] - {ctxname}
            if extra and len([x for x in m["examples"] if x["kind"] == "missed"]) < 12:
                m["examples"].append(dict(kind="missed", file=rel, fn=fi["name"], names=sorted(extra)[:10], live_free=sorted(dfree)[:20],
                                          static_free=sorted(fi["free"])[:20], live_ctx=info.get("ctx"), static_ns=fi["ns"]))  # fmt: skip
            m["missed"] += len(extra)
    m["load_results"] = load_results
    return m
