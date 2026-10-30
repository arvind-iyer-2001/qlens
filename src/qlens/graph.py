"""Build the knowledge graph from split statements and q's static-pass results."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .classify import CALL, READ, USES, WRITE, all_free, classify, find_defs
from .discovery import discover
from .scoring import DEFAULT_SCORES, label
from .splitter import split_statements
from .static_pass import run_static

BUILTIN_PREFIXES = (".q.", ".Q.", ".j.", ".h.", ".z.", ".o.")
_SYSTEM = re.compile(r'^system\s*"((?:[^"\\]|\\.)*)"\s*;?\s*$', re.S)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.]+", "_", s).strip("_")[:40] or "x"


def make_id(file: str, qname: str) -> str:
    """Case-sensitive: the sha1 of the exact (file, name) keeps `l`/`L` and `.z.w`/`.z.W` apart."""
    h = hashlib.sha1(f"{file}\0{qname}".encode()).hexdigest()[:10]
    return f"{_slug(qname)}-{h}"


def qualify(name: str, ns: str) -> str:
    if name.startswith("."):
        return name
    return f"{ns}.{name}" if ns else name


def is_builtin(qname: str, builtins: set[str]) -> bool:
    return qname.startswith(BUILTIN_PREFIXES) or qname in builtins


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s)


@dataclass
class Graph:
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: dict[tuple, dict] = field(default_factory=dict)
    queue: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    cond: set = field(default_factory=set)  # node ids defined only inside a conditional
    redef: set = field(default_factory=set)  # node ids defined more than once in their file
    raw: dict[tuple, set] = field(default_factory=dict)  # edge key -> names as written in source
    fn: dict[str, dict] = field(default_factory=dict)  # function node id -> {free, ns, file}
    imports: dict[str, list[str]] = field(default_factory=dict)  # file rel -> imported file rels

    def node(self, id_, label_, kind, file, line, tier, evidence, score=None):
        if id_ in self.nodes:
            return self.nodes[id_]
        sc = DEFAULT_SCORES[tier] if score is None else score
        self.nodes[id_] = dict(
            id=id_, label=label_, kind=kind, file=file, line=line, tier=tier,
            confidence=label(sc), confidence_score=sc, evidence=evidence,
        )  # fmt: skip
        return self.nodes[id_]

    def edge(self, src, dst, rel, tier, evidence, file, line, score=None, raw=None):
        key = (src, dst, rel)
        if raw:
            self.raw.setdefault(key, set()).add(raw)
        if key in self.edges:
            return
        sc = DEFAULT_SCORES[tier] if score is None else score
        self.edges[key] = dict(
            source=src, target=dst, relation=rel, tier=tier, confidence=label(sc),
            confidence_score=sc, evidence=evidence, file=file, line=line,
        )  # fmt: skip


def _repo_root(path: Path, root: Path) -> Path:
    for p in [path.parent, *path.parent.parents]:
        if (p / ".git").exists():
            return p
        if p == root:
            break
    return root


def analyse(root: str | Path, execute: bool = False, out_dir: str | Path | None = None, backend: str | None = None, timeout: float = 60, log=None) -> dict:
    log = log or (lambda m: None)
    root = Path(root).resolve()
    base = root if root.is_dir() else root.parent
    log(f"looking for .q files under {root}")
    disc = discover(root, out_dir)
    log(f"found {len(disc.files)} q files ({len(disc.skipped)} skipped: too large, empty or not q)")
    g = Graph()

    # 1. split
    files: list[dict] = []
    foreign: dict[str, int] = {}
    texts: dict[int, str] = {}
    meta: dict[int, tuple[int, int]] = {}  # global stmt id -> (file idx, stmt idx)
    for fi, path in enumerate(disc.files):
        rel = path.relative_to(base).as_posix() if path != base else path.name
        stmts = split_statements(path.read_text(errors="replace"))
        files.append(dict(path=path, rel=rel, stmts=stmts, repo=_repo_root(path, base)))
        for si, s in enumerate(stmts):
            gid = len(texts)
            texts[gid], meta[gid] = (s.text if s.kind == "q" else ""), (fi, si)
            if s.kind != "q":
                foreign[s.kind] = foreign.get(s.kind, 0) + 1
    # 2. q parses everything (sandboxed)
    log(f"split into {len(texts)} statements; asking q to parse them in the sandbox")
    run = run_static({i: t for i, t in texts.items() if t}, base, timeout=timeout, backend=backend)

    log(f"q parsed {sum(1 for r in run.results.values() if r.ok)} statements, {sum(1 for r in run.results.values() if not r.ok)} failed to parse; building graph")
    # 3. definitions, imports, references (needs namespace tracking, per file in order)
    defs_index: dict[str, list[str]] = {}  # qname -> node ids
    pending_refs: list[dict] = []
    rel_to_file = {f["rel"]: f for f in files}
    for fi, f in enumerate(files):
        fid = make_id(f["rel"], "<file>")
        f["id"] = fid
        g.node(fid, f["rel"], "file", f["rel"], 1, "S", "discovered *.q file")
    gid = 0
    for fi, f in enumerate(files):
        ns = ""
        for si, s in enumerate(f["stmts"]):
            res = run.results.get(gid)
            gid += 1
            line = s.line
            if s.kind != "q":
                continue
            m = _SYSTEM.match(s.text)
            if m:
                cmd = _unescape(m.group(1)).strip()
                head, _, arg = cmd.partition(" ")
                arg = arg.strip()
                if head == "d":
                    ns = "" if arg in ("", ".") else (arg if arg.startswith(".") else "." + arg)
                elif head in ("l", "load") and arg:
                    _import(g, f, arg, line, files, base, rel_to_file)
                continue
            if res is None or not res.ok:
                g.diagnostics.append(dict(file=f["rel"], line=line, error=(res.err if res else "no result"), text=s.text[:120]))
                continue
            tree, free = res.tree, set(res.free or [])
            sdefs = find_defs(tree)
            def_nodes: list[tuple] = []
            for d in sdefs:
                q = qualify(d.name, ns)
                nid = make_id(f["rel"], q)
                if nid not in g.nodes:
                    tier = "S-indirect" if ((d.indirect and d.kind == "variable") or d.conditional) else "S"
                    ev = f"{d.name}: assigned at top level ({'lambda' if d.kind == 'function' else 'non-lambda'} rhs)"
                    if d.conditional:
                        ev += "; defined inside a conditional (may never execute)"
                        g.cond.add(nid)
                    elif tier == "S-indirect":
                        ev += "; rhs may evaluate to a function (indirect)"
                    g.node(nid, q, d.kind, f["rel"], line, tier, ev)
                    g.edge(f["id"], nid, "contains", "S", f"defined at {f['rel']}:{line}", f["rel"], line)
                    defs_index.setdefault(q, []).append(nid)
                    if d.kind == "function":
                        g.fn[nid] = dict(free=all_free(d.rhs), ns=ns, file=f["rel"], name=q)
                else:
                    g.redef.add(nid)  # defined again in the same file: live q holds only the last one
                def_nodes.append((d, nid))

            # each definition owns only the references inside its own right-hand side
            handled: set[int] = set()
            covered: set[tuple] = set()
            for d, nid in def_nodes:
                if d.kind == "function":
                    handled.add(id(d.rhs))
                    _lam(f, ns, [nid], d.rhs, line, pending_refs)
                else:
                    r2, n2 = classify(d.rhs, free)
                    covered |= {(k, role) for k, rs in r2.items() for role in rs}
                    handled |= {id(x) for x in n2}
                    _collect(f, ns, [nid], r2, line, pending_refs, "S")
                    for lam in n2:
                        _lam(f, ns, [nid], lam, line, pending_refs)
            # anything outside every definition belongs to the file
            roles, nested = classify(tree, free)
            own_names = {d.name for d, _ in def_nodes}
            rest = {}
            for k, rs in roles.items():
                keep = {role for role in rs if (k, role) not in covered and not (k in own_names and role == "writes")}
                if keep:
                    rest[k] = keep
            _collect(f, ns, [f["id"]], rest, line, pending_refs, "S")
            for lam in nested:
                if id(lam) not in handled:
                    _lam(f, ns, [f["id"]], lam, line, pending_refs)

    # 4. resolve references to nodes
    builtins = run.builtins
    for r in pending_refs:
        _resolve(g, r, defs_index, builtins, files)
    for c in run.crashes:
        g.diagnostics.append(dict(file=None, line=None, error=c, text=""))
    dyn_meta = None
    if execute:
        from .dynamic import run_all
        from .merge import merge

        nss = sorted({m.group(0) for q in defs_index if (m := re.match(r"^\.[^.]+(?:\.[^.]+)*(?=\.[^.]+$)", q))})
        log(f"loading {len(files)} files in q to confirm (one sandboxed process per file, timeout {timeout:.0f}s each)")
        dyn = run_all(files, g.imports, nss, base, timeout=timeout, backend=backend, log=log)
        dyn_meta = merge(g, files, dyn, defs_index)
    per_file: dict[str, list[int]] = {}
    for d in g.diagnostics:
        if d.get("file"):
            per_file.setdefault(d["file"], [0])[0] += 1
    suspect = [
        dict(file=f["rel"], failed=per_file[f["rel"]][0], statements=len(f["stmts"]))
        for f in files
        if f["rel"] in per_file and len(f["stmts"]) >= 5 and per_file[f["rel"]][0] / len(f["stmts"]) > 0.5
    ]  # most statements unparseable: probably k syntax or not q
    log(f"graph: {len(g.nodes)} nodes, {len(g.edges)} edges, {len(g.queue)} unresolved references queued")
    return dict(
        nodes=list(g.nodes.values()),
        edges=list(g.edges.values()),
        enrichment_queue=g.queue,
        meta=dict(root=str(base), files=len(files), skipped=[dict(file=str(p), reason=r) for p, r in disc.skipped],
                  diagnostics=g.diagnostics, qver=run.qver, tier="S+D" if execute else "S", statements=len(texts) - sum(foreign.values()), foreign_blocks=foreign, dynamic=dyn_meta, suspect_files=suspect),
    )  # fmt: skip


def _collect(f, ns, owner_ids, roles, line, out, tier):
    for name, rs in roles.items():
        for role in sorted(rs):
            for oid in owner_ids:
                out.append(dict(owner=oid, name=name, role=role, ns=ns, file=f["rel"], repo=f["repo"], line=line, tier=tier))


def _lam(f, ns, owner_ids, lam, line, out):
    roles, nested = classify(lam["body"], set(lam["free"]))
    _collect(f, ns, owner_ids, roles, line, out, "S")
    for n in nested:
        _lam(f, ns, owner_ids, n, line, out)


def _import(g, f, arg, line, files, base, rel_to_file):
    cands = []
    for b in (base, f["path"].parent, f["repo"]):
        p = (b / arg)
        cands += [p, p.with_suffix(".q") if p.suffix != ".q" else p]
    for c in cands:
        try:
            rel = c.resolve().relative_to(base).as_posix()
        except (ValueError, OSError):
            continue
        if rel in rel_to_file:
            g.edge(f["id"], rel_to_file[rel]["id"], "imports", "S", f"system \"l {arg}\" -> {rel}", f["rel"], line)
            g.imports.setdefault(f["rel"], []).append(rel)
            return
    g.queue.append(dict(**{"from": f["id"]}, name=arg, reason="unresolved import", file=f["rel"], line=line))


def _resolve(g: Graph, r: dict, defs_index, builtins, files):
    q = qualify(r["name"], r["ns"])
    if is_builtin(q, builtins) or (not r["name"].startswith(".") and r["name"] in builtins):
        return
    cands = defs_index.get(q, [])
    rel = {"calls": "calls", "reads": "reads", "writes": "writes", "uses": "uses"}[r["role"]]
    if not cands:
        if r["role"] == WRITE:  # assigning an undefined global creates it
            nid = make_id(r["file"], q)
            if nid not in g.nodes:
                g.node(nid, q, "variable", r["file"], r["line"], "S-indirect", "global assigned inside a function; no top-level definition")
                defs_index.setdefault(q, []).append(nid)
            g.edge(r["owner"], nid, rel, "S", f"{r['name']} assigned (global write)", r["file"], r["line"], raw=r["name"])
            return
        nid = make_id("<external>", q)
        g.node(nid, q, "external", None, None, "S-unresolved", "referenced but not defined in the analysed code")
        g.edge(r["owner"], nid, rel, "S-unresolved", f"{q} not defined anywhere", r["file"], r["line"], raw=r["name"])
        g.queue.append(dict(**{"from": r["owner"]}, name=q, reason="unresolved reference", file=r["file"], line=r["line"]))
        return
    chosen = _prefer(g, cands, r, files)
    if len(chosen) > 1:
        tier, ev = "S-indirect", f"{q} has {len(chosen)} definitions; edge to each"
    else:
        tier, ev = "S", f"{r['name']} resolves to {q}"
    for c in chosen:
        node = g.nodes[c]
        t = tier
        e = ev
        if node["tier"] == "S-indirect" and r["role"] == CALL and tier == "S":
            t, e = "S-indirect", e + "; target is a non-lambda definition (indirect)"
        if r["role"] == USES and node["kind"] == "variable":
            node["kind"] = "table"
        g.edge(r["owner"], c, rel, t, e, r["file"], r["line"], raw=r["name"])


def _closure(imports: dict[str, list[str]], rel: str) -> set[str]:
    seen, stack = set(), [rel]
    while stack:
        for d in imports.get(stack.pop(), []):
            if d not in seen:
                seen.add(d)
                stack.append(d)
    return seen


def _prefer(g: Graph, cands: list[str], r: dict, files: list[dict]) -> list[str]:
    """Pick which definitions a reference binds to: same file, then loaded files, then same repo, then all."""
    by_file = lambda ids, fs: [c for c in ids if g.nodes[c]["file"] in fs]  # noqa: E731
    same = by_file(cands, {r["file"]})
    if same:
        return same
    loaded = by_file(cands, _closure(g.imports, r["file"]))
    if loaded:
        return loaded
    repo_files = {f["rel"] for f in files if f["repo"] == r["repo"]}
    in_repo = by_file(cands, repo_files)
    return in_repo or cands


def write_outputs(result: dict, out: str | Path) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    from collections import Counter

    report = dict(
        counts=dict(
            nodes=len(result["nodes"]),
            edges=len(result["edges"]),
            enrichment=len(result["enrichment_queue"]),
            diagnostics=len(result["meta"]["diagnostics"]),
            edges_by_relation=dict(Counter(e["relation"] for e in result["edges"])),
            edges_by_tier=dict(Counter(e["tier"] for e in result["edges"])),
            edges_by_confidence=dict(Counter(e["confidence"] for e in result["edges"])),
            nodes_by_kind=dict(Counter(n["kind"] for n in result["nodes"])),
        ),
        meta=result["meta"],
        enrichment_queue=result["enrichment_queue"],
    )
    graph = {k: result[k] for k in ("nodes", "edges", "enrichment_queue")} | {"meta": {k: v for k, v in result["meta"].items() if k not in ("diagnostics",)}}
    (out / "graph.json").write_text(json.dumps(graph, indent=1))
    (out / "report.json").write_text(json.dumps(report, indent=1))
