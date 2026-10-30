import pytest

from qlens import analyse
from qlens.sandbox import find_q

try:
    find_q()
    HAVE_Q = True
except Exception:
    HAVE_Q = False

pytestmark = pytest.mark.skipif(not HAVE_Q, reason="q not installed")


def _mk(tmp_path):
    for repo in ("repoA", "repoB"):
        (tmp_path / repo / ".git").mkdir(parents=True)
        (tmp_path / repo / "lib").mkdir()
        (tmp_path / repo / "lib" / "util.q").write_text(f"util:{{x+1}} / {repo}\n")
        # repo-root-relative load, same relative path in both repos
        (tmp_path / repo / "main.q").write_text("\\l lib/util.q\nrun:{util x}\n")
    return tmp_path


def test_repo_relative_loads_and_unique_ids(tmp_path):
    r = analyse(_mk(tmp_path))
    lab = {n["id"]: n for n in r["nodes"]}
    assert len(lab) == len(r["nodes"])  # ids unique across repos
    imports = [(lab[e["source"]]["label"], lab[e["target"]]["label"]) for e in r["edges"] if e["relation"] == "imports"]
    assert sorted(imports) == [("repoA/main.q", "repoA/lib/util.q"), ("repoB/main.q", "repoB/lib/util.q")]
    # each run() calls its own repo's util, not the other repo's
    calls = {(lab[e["source"]]["file"], lab[e["target"]]["file"]) for e in r["edges"] if e["relation"] == "calls"}
    assert calls == {("repoA/main.q", "repoA/lib/util.q"), ("repoB/main.q", "repoB/lib/util.q")}
    utils = [n for n in r["nodes"] if n["label"] == "util"]
    assert len(utils) == 2 and utils[0]["id"] != utils[1]["id"]


def test_workspace_dynamic_isolated_per_repo(tmp_path):
    r = analyse(_mk(tmp_path), execute=True)
    assert r["meta"]["dynamic"]["files_loaded"] == 4
    assert all(n["tier"] == "D2" for n in r["nodes"] if n["kind"] == "function")
