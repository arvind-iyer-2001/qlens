from pathlib import Path

from qlens.classify import classify, find_defs
from qlens.graph import make_id, qualify
from qlens.sandbox import docker_command, sandbox_exec_profile


def sym(v):
    return {"k": "sym", "v": v}


def fn(v):
    return {"k": "fn", "v": v}


def app(*c):
    return {"k": "app", "v": list(c)}


def test_roles():
    body = app(fn(";") , app(fn("::"), sym("svc"), {"k": "lit", "v": "1"}), app(sym("g"), sym("x")), sym("v"))
    roles, _ = classify(body, {"svc", "g", "v"})
    assert roles == {"svc": {"writes"}, "g": {"calls"}, "v": {"reads"}}


def test_find_defs_chain_and_indirect():
    lam = {"k": "lam", "src": "{x}", "params": ["x"], "locals": [], "free": [], "body": sym("x")}
    ds = find_defs(app(fn(":"), sym("a"), app(fn(":"), sym("b"), lam)))
    assert [(d.name, d.kind, d.indirect) for d in ds] == [("a", "function", False), ("b", "function", False)]
    ds = find_defs(app(fn(":"), sym("f"), app(fn("$"), sym("c"), sym("g"), sym("h"))))
    assert ds[0].indirect and ds[0].kind == "variable"


def test_qualify_and_ids():
    assert qualify("f", ".gw") == ".gw.f" and qualify(".a.f", ".gw") == ".a.f" and qualify("f", "") == "f"
    assert make_id("a.q", "l") != make_id("a.q", "L")
    assert make_id("a.q", ".z.w") != make_id("a.q", ".z.W")


def test_sandbox_exec_profile():
    p = sandbox_exec_profile(Path("/opt/q/bin/q"), [Path("/work")], Path("/tmp/w"), home=Path("/Users/me"))
    assert "(deny network*)" in p and "(deny file-write*)" in p
    assert '(allow file-write* (subpath "/tmp/w")' in p
    assert '(deny file-read-data (subpath "/Users/me"))' in p
    assert '(allow process-exec (literal "/opt/q/bin/q"))' in p and "(deny process-exec*)" in p


def test_docker_flags():
    cmd = docker_command(Path("/opt/q/bin/q"), [Path("/work")], Path("/tmp/w"), ["s.q"], "n1", "img", uid=1000, gid=1000)
    j = " ".join(cmd)
    for flag in ("--rm", "--init", "--network none", "--read-only", "--cap-drop ALL",
                 "--security-opt no-new-privileges", "--pids-limit 256", "--memory 2g", "--cpus 1",
                 "--user 1000:1000", "--tmpfs /tmp", "--name n1", "-v /work:/work:ro", "-v /tmp/w:/tmp/w:rw"):  # fmt: skip
        assert flag in j, flag
    assert cmd[-3:] == ["img", "/opt/q/bin/q", "s.q"]
