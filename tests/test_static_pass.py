import pytest

from qlens.sandbox import find_q
from qlens.static_pass import run_static

try:
    find_q()
    HAVE_Q = True
except Exception:
    HAVE_Q = False

pytestmark = pytest.mark.skipif(not HAVE_Q, reason="q not installed")


def test_static_pass_basic(tmp_path):
    run = run_static({0: "f:{[a;b] c:a+g b; c*.ns.h x}", 1: "a:1 +", 2: "t:select a from u where b>v"}, tmp_path)
    r0 = run.results[0]
    assert r0.ok
    lam = r0.tree["v"][2]
    assert lam["k"] == "lam" and lam["params"] == ["a", "b"] and lam["locals"] == ["c"]
    assert set(lam["free"]) == {"g", "x", ".ns.h"}
    assert run.results[2].free == ["u"]  # columns b, v are not globals
    assert "count" in run.builtins


def test_parse_error_isolated(tmp_path):
    run = run_static({0: "a:{", 1: "b:2"}, tmp_path)
    assert not run.results[0].ok and run.results[1].ok
