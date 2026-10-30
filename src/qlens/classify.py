"""Turn q's tagged parse trees into definitions and name references with roles.

Scope facts (params, locals, free globals, qsql columns) come from q's `value` on lambdas (the `free`
field); this module only decides the ROLE of each free name from the tree: call, read, write or uses.
"""

from __future__ import annotations

from dataclasses import dataclass

ADVERBS = {"'", "/", "\\", "':", "/:", "\\:"}
CALL, READ, WRITE, USES = "calls", "reads", "writes", "uses"


@dataclass(frozen=True)
class Ref:
    name: str
    role: str
    via: str = "direct"  # direct | indirect


@dataclass(frozen=True)
class Def:
    name: str
    kind: str  # function | variable
    indirect: bool
    rhs: dict
    conditional: bool = False  # assigned inside $[c;..;..], if[], while[] or do[]: may never execute


def _kids(n: dict) -> list[dict]:
    return n["v"] if n["k"] == "app" else []


def _fn(n: dict) -> str | None:
    return n["v"] if n["k"] == "fn" else None


def _is_assign_head(n: dict) -> bool:
    return _fn(n) in (":", "::")


def _is_amend_head(n: dict) -> bool:
    f = _fn(n)
    return bool(f) and len(f) > 1 and f.endswith(":") and f != "::" and not f.endswith("::")


def _is_kfn(n: dict) -> bool:
    f = _fn(n)
    return bool(f) and (f.startswith("k)") or f.startswith("(k)"))


def _add(out: dict[str, set[str]], name: str, role: str, free: set[str]) -> None:
    if name in free:
        out.setdefault(name, set()).add(role)


def classify(tree: dict, free: set[str], out: dict[str, set[str]] | None = None, nested: list | None = None):
    """Walk a tree (statement or lambda body). Returns name -> {roles}; nested lambda nodes are
    appended to `nested` (they have their own free lists)."""
    out = {} if out is None else out
    nested = [] if nested is None else nested
    _walk(tree, free, out, nested, head=False)
    return out, nested


def _walk(n: dict, free: set[str], out, nested, head: bool) -> None:
    k = n["k"]
    if k == "lam":
        nested.append(n)
        return
    if k == "sym":
        _add(out, n["v"], CALL if head else READ, free)
        return
    if k != "app":
        return
    ch = n["v"]
    if not ch:
        return
    h, args = ch[0], ch[1:]
    if _is_assign_head(h) and len(args) == 2:
        tgt, rhs = args
        if tgt["k"] == "sym":
            _add(out, tgt["v"], WRITE, free)
        elif tgt["k"] == "app" and tgt["v"] and tgt["v"][0]["k"] == "sym":  # indexed amend e[i]:v
            _add(out, tgt["v"][0]["v"], WRITE, free)
            for a in tgt["v"][1:]:
                _walk(a, free, out, nested, False)
        _walk(rhs, free, out, nested, False)
        return
    if _is_amend_head(h) and len(args) == 2 and args[0]["k"] in ("sym", "app"):
        tgt, rhs = args
        if tgt["k"] == "sym":
            _add(out, tgt["v"], WRITE, free)
        elif tgt["v"] and tgt["v"][0]["k"] == "sym":
            _add(out, tgt["v"][0]["v"], WRITE, free)
        _walk(rhs, free, out, nested, False)
        return
    if _fn(h) in ("?", "!") and len(args) >= 4 and args[0]["k"] == "sym":
        _add(out, args[0]["v"], USES, free)  # qsql: first arg is the from-table
        for a in args[1:]:
            _walk(a, free, out, nested, False)
        return
    if h["k"] == "sym":
        _add(out, h["v"], CALL, free)
    elif h["k"] == "app" and h["v"] and _fn(h["v"][0]) in ADVERBS:  # derived verb f/ f' ...
        for x in h["v"][1:]:
            _walk(x, free, out, nested, head=True)
    elif _is_kfn(h) and args and args[0]["k"] == "sym":  # each/peach/... : first arg is applied
        _add(out, args[0]["v"], CALL, free)
        args = args[1:]
    elif h["k"] != "fn":
        _walk(h, free, out, nested, head=True)
    for a in args:
        _walk(a, free, out, nested, False)


def find_defs(tree: dict) -> list[Def]:
    """Global definitions made by a top-level statement (not entering lambdas)."""
    defs: list[Def] = []

    def go(n: dict, cond: bool = False) -> None:
        if n["k"] != "app" or not n["v"]:
            return
        h, args = n["v"][0], n["v"][1:]
        if (_fn(h) == "$" and len(args) >= 3) or (h["k"] == "sym" and h["v"] in ("if", "do", "while")):
            cond = True
        if _is_assign_head(h) and len(args) == 2 and args[0]["k"] == "sym":
            rhs = args[1]
            names = [args[0]["v"]]
            while rhs["k"] == "app" and rhs["v"] and _is_assign_head(rhs["v"][0]) and len(rhs["v"]) == 3 and rhs["v"][1]["k"] == "sym":
                names.append(rhs["v"][1]["v"])  # chained a:b:{...}
                rhs = rhs["v"][2]
            kind = "function" if rhs["k"] == "lam" else "variable"
            for nm in names:
                defs.append(Def(nm, kind, _indirect(rhs), rhs, cond))
            go(rhs, cond)
            return
        for a in n["v"]:
            go(a, cond)

    go(tree)
    return defs


def _indirect(rhs: dict) -> bool:
    """rhs that may evaluate to a function without being a lambda literal."""
    k = rhs["k"]
    if k == "sym":
        return True  # alias f:g
    if k != "app" or not rhs["v"]:
        return False
    h = rhs["v"][0]
    if _fn(h) == "$":
        return len(rhs["v"]) >= 4  # $[c;a;b] conditional; 3-element form is a cast
    if _fn(h) in ("?", "!", "+:", ",", "enlist", ":", "::"):
        return False
    return h["k"] in ("sym", "lam") or _is_kfn(h)


def all_free(lam: dict) -> set[str]:
    """Free names of a lambda plus those of every lambda nested inside it (q's `value` omits the inner ones)."""
    out = set(lam["free"])
    _, nested = classify(lam["body"], set(lam["free"]))
    for n in nested:
        out |= all_free(n)
    return out
