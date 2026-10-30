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
    (tmp_path / "a.q").write_text("g:{x}\nf:{g x}\nif[0b; hidden:{x}]\ngone:{x}\ndelete gone from `.\nr:{undefinedfn x}\n")
    r = analyse(tmp_path, execute=True, timeout=30)
    n = _nodes(r)
    assert n["f"]["tier"] == "D2" and n["f"]["confidence_score"] == 0.97
    assert n["hidden"]["tier"] == "S-indirect"  # defined inside a conditional that did not run: not a mistake
    assert n["gone"]["tier"] == "S-refuted" and n["gone"]["confidence_score"] == 0.1
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


@needs_q
def test_dotted_definition_has_no_self_edge_and_q_keywords_are_not_missed(tmp_path):
    (tmp_path / "a.q").write_text(
        ".ns.helper:{x+1}\n.ns.run:{trim string .ns.helper x}\n.ns.cols2:{.Q.v x}\n"
    )
    r = analyse(tmp_path, execute=True)
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    selfs = [e for e in r["edges"] if e["source"] == e["target"]]
    assert selfs == []
    d = r["meta"]["dynamic"]
    assert d["refuted"] == 0 and d["missed"] == 0, d["examples"]


@needs_q
def test_two_definitions_on_one_line_get_their_own_references(tmp_path):
    (tmp_path / "u.q").write_text("\\d .u\nw:1\ndel:{w};add:{del x}\n")
    r = analyse(tmp_path, execute=True)
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(lab[e["source"]], lab[e["target"]]) for e in r["edges"] if e["relation"] in ("calls", "reads")}
    assert calls == {(".u.del", ".u.w"), (".u.add", ".u.del")}
    d = r["meta"]["dynamic"]
    assert d["refuted"] == 0 and d["missed"] == 0, d["examples"]


@needs_q
def test_namespace_same_name_variable_and_container_and_redefinition(tmp_path):
    (tmp_path / "c.q").write_text("\\d .cache\ncache:()\nadd:{cache,:x}\n\\d .\n.pm.auth.ldap:{x}\nre:{g x}\nre:{h x}\ng:{x}\nh:{x}\n")
    r = analyse(tmp_path, execute=True)
    d = r["meta"]["dynamic"]
    assert d["refuted"] == 0, d["examples"]
    assert d["defs_missed"] == 0, d["examples"]  # .pm.auth is a container for .pm.auth.ldap


@needs_q
def test_null_valued_variables_and_trailing_semicolon_and_runtime_load(tmp_path):
    (tmp_path / "g.q").write_text('system "d .pk";\nlg:{x}\nstate:(::)\nvals:5\n')
    (tmp_path / "lib.q").write_text("libfn:{x}\n")
    (tmp_path / "t.q").write_text('p:"lib.q";\nrun:{system "l ",p};\nrun[]\n')
    r = analyse(tmp_path, execute=True)
    n = {x["label"]: x for x in r["nodes"]}
    assert ".pk.lg" in n and ".pk.state" in n  # namespace switch with trailing ; applied
    d = r["meta"]["dynamic"]
    assert d["defs_refuted"] == 0, d["examples"]  # `state:(::)` exists although \v omits it
    assert d["defs_missed"] == 0 and d["defs_elsewhere"] >= 1, d["examples"]
    lab = {x["id"]: x["label"] for x in r["nodes"]}
    imps = {(lab[e["source"]], lab[e["target"]]) for e in r["edges"] if e["relation"] == "imports"}
    assert ("t.q", "lib.q") in imps  # the dependency q revealed
