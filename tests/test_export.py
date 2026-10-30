import re
from pathlib import Path

import pytest

from qlens import analyse
from qlens.export import to_graphify
from qlens.sandbox import find_q

try:
    find_q()
    HAVE_Q = True
except Exception:
    HAVE_Q = False

TRAPS = Path(__file__).parent.parent / "corpus" / "traps"


def _g(nodes, edges):
    return {"nodes": nodes, "edges": edges}


def _n(id_, label, file, kind="function", line=3):
    return dict(id=id_, label=label, kind=kind, file=file, line=line, tier="S", confidence="EXTRACTED", confidence_score=0.92, evidence="x")


def test_id_rule_and_case_collision():
    g = _g(
        [_n("a", "l", "lib/core.q"), _n("b", "L", "lib/core.q"), _n("c", ".gw.run", "svc/main.q"), _n("f", "lib/core.q", "lib/core.q", "file")],
        [dict(source="c", target="a", relation="calls", tier="S", confidence="EXTRACTED", confidence_score=0.92, evidence="e", file="svc/main.q", line=4),
         dict(source="c", target="b", relation="reads", tier="S", confidence="EXTRACTED", confidence_score=0.92, evidence="e", file="svc/main.q", line=4)],
    )  # fmt: skip
    out = to_graphify(g)
    ids = [n["id"] for n in out["nodes"]]
    assert len(set(ids)) == 4  # l / L did not merge
    assert all(re.fullmatch(r"[a-z0-9_]+", i) for i in ids)
    assert "svc_main_gw_run" in ids and "lib_core" in ids
    assert {e["relation"] for e in out["edges"]} == {"calls", "references"}
    assert all(n["file_type"] == "code" for n in out["nodes"])
    e = out["edges"][0]
    assert set(e) >= {"source", "target", "relation", "confidence", "confidence_score", "source_file", "source_location", "weight"}
    assert {x["id"] for x in out["nodes"]} >= {e["source"], e["target"]}


@pytest.mark.skipif(not HAVE_Q, reason="q not installed")
def test_trap_export_is_consistent():
    out = to_graphify(analyse(TRAPS))
    ids = {n["id"] for n in out["nodes"]}
    assert len(ids) == len(out["nodes"])
    assert all(e["source"] in ids and e["target"] in ids for e in out["edges"])
    assert all(e["confidence"] in ("EXTRACTED", "INFERRED", "AMBIGUOUS") for e in out["edges"])
