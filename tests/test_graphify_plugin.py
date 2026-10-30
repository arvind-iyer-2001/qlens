import subprocess
import sys
from pathlib import Path

import pytest

from qlens import graphify_plugin as gp
from qlens.sandbox import find_q

try:
    find_q()
    HAVE_Q = True
except Exception:
    HAVE_Q = False

needs_q = pytest.mark.skipif(not HAVE_Q, reason="q not installed")


class Ctx:
    def __init__(self):
        self.lines = []

    def log(self, msg):
        self.lines.append(msg)


def test_plugin_declaration_is_a_plain_dict_for_graphify():
    p = gp.PLUGIN
    assert p["name"] == "qlens" and p["suffixes"] == [".q"] and callable(p["extract_batch"]) and p["api"] == 1


def test_importing_the_plugin_does_not_import_graphify():
    code = "import sys, qlens.graphify_plugin; sys.exit('graphify' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_split_groups_by_file_and_attaches_outside_nodes(tmp_path):
    export = {
        "nodes": [
            {"id": "a_q", "label": "a.q", "source_file": "a.q"},
            {"id": "a_f", "label": "f", "source_file": "a.q"},
            {"id": "b_g", "label": "g", "source_file": "b.q"},  # defined in a file outside the batch
            {"id": "ext", "label": "x", "source_file": None},
        ],
        "edges": [
            {"source": "a_f", "target": "b_g", "relation": "calls", "source_file": "a.q"},
            {"source": "a_f", "target": "ext", "relation": "calls", "source_file": "a.q"},
        ],
    }
    out = gp._split(export, tmp_path, {str((tmp_path / "a.q").resolve())})
    [(path, got)] = out.items()
    assert path == str((tmp_path / "a.q").resolve())
    assert {n["id"] for n in got["nodes"]} == {"a_q", "a_f", "b_g", "ext"}
    assert all(Path(n["source_file"]).is_absolute() for n in got["nodes"])
    assert len(got["edges"]) == 2


@needs_q
def test_extract_batch_resolves_across_files(tmp_path):
    (tmp_path / "a.q").write_text("g:{x+1}\n")
    (tmp_path / "b.q").write_text("\\l a.q\nf:{g x}\n")
    ctx = Ctx()
    res = gp.extract_batch([tmp_path / "a.q", tmp_path / "b.q"], ctx)
    assert set(res) == {(tmp_path / "a.q").resolve(), (tmp_path / "b.q").resolve()}
    b = res[(tmp_path / "b.q").resolve()]
    assert {n["label"] for n in b["nodes"]} >= {"b.q", "f"}
    calls = [e for e in b["edges"] if e["relation"] == "calls"]
    assert calls and calls[0]["confidence_score"] >= 0.9
