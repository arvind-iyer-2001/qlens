import os

import pytest

from qlens import analyse
from qlens.dynamic import dependency_order, run_file
from qlens.sandbox import find_q

try:
    find_q()
    HAVE_Q = True
except Exception:
    HAVE_Q = False

needs_q = pytest.mark.skipif(not HAVE_Q, reason="q not installed")


def test_dependency_order():
    imp = {"a": ["b", "c"], "b": ["d"], "c": ["d", "a"], "d": []}
    assert dependency_order("a", imp) == ["d", "b", "c"]


def _nodes(r):
    return {n["label"]: n for n in r["nodes"]}


@needs_q
def test_confirm_refute_and_edges(tmp_path):
    (tmp_path / "a.q").write_text("g:{x}\nf:{g x}\nif[0b; hidden:{x}]\nr:{undefinedfn x}\n")
    r = analyse(tmp_path, execute=True, timeout=30)
    n = _nodes(r)
    assert n["f"]["tier"] == "D2" and n["f"]["confidence_score"] == 0.97
    assert n["hidden"]["tier"] == "S-refuted" and n["hidden"]["confidence_score"] == 0.1
    lab = {x["id"]: x["label"] for x in r["nodes"]}
    e = {(lab[e["source"]], lab[e["target"]]): e for e in r["edges"] if e["relation"] == "calls"}
    assert e[("f", "g")]["tier"] == "D3"
    assert e[("r", "undefinedfn")]["tier"] == "S-unresolved"
    d = r["meta"]["dynamic"]
    assert d["files_loaded"] == 1 and d["agree"] >= 1 and d["refuted"] == 0 and d["dangling"] == 1


@needs_q
def test_exit_timeout_network_and_write_are_contained(tmp_path):
    (tmp_path / "ok.q").write_text("keep:{x}\n")
    (tmp_path / "exits.q").write_text("e1:{x}\nexit 3\ne2:{x}\n")
    (tmp_path / "hangs.q").write_text("h1:{x}\nwhile[1b;]\n")
    (tmp_path / "net.q").write_text("n1:{x}\nhopen `::5999\nn2:{x}\n")
    (tmp_path / "writes.q").write_text("w1:{x}\n`:/tmp/qlens_should_not_exist set 1\nw2:{x}\n")
    r = analyse(tmp_path, execute=True, timeout=6)
    res = {x["file"]: x for x in r["meta"]["dynamic"]["load_results"]}
    assert res["ok.q"]["loaded"]
    assert not res["net.q"]["loaded"] and "hop" in res["net.q"]["error"]
    assert not res["writes.q"]["loaded"]
    assert res["hangs.q"]["failure"] == "timeout"
    assert _nodes(r)["keep"]["tier"] == "D2"
    assert not os.path.exists("/tmp/qlens_should_not_exist")


@needs_q
def test_dependency_preload_and_only_target_diff(tmp_path):
    (tmp_path / "lib.q").write_text("libf:{x}\n")
    (tmp_path / "main.q").write_text("\\l lib.q\nusef:{libf x}\n")
    r = analyse(tmp_path, execute=True)
    n = _nodes(r)
    assert n["usef"]["tier"] == "D2" and n["libf"]["tier"] == "D2"
    assert r["meta"]["dynamic"]["defs_missed"] == 0  # lib's names are not attributed to main.q


@needs_q
def test_run_file_reports_namespace_context(tmp_path):
    (tmp_path / "x.q").write_text("\\d .ns\nf:{x}\n")
    d = run_file(tmp_path / "x.q", [], [".ns"], tmp_path, tmp_path)
    assert d.loaded and d.defs[".ns.f"]["ctx"] == "ns"


@needs_q
def test_nested_lambdas_are_not_refuted(tmp_path):
    (tmp_path / "a.q").write_text("g:{x+1}\nouter:{{g x} each y}\ndeep:{{{g x} each y} each z}\n")
    r = analyse(tmp_path, execute=True)
    d = r["meta"]["dynamic"]
    assert d["refuted"] == 0 and d["agree"] >= 2 and d["missed"] == 0
