import json
from pathlib import Path

import pytest

from qlens import analyse
from qlens.evaluate import evaluate
from qlens.sandbox import find_q

try:
    find_q()
    HAVE_Q = True
except Exception:
    HAVE_Q = False

pytestmark = pytest.mark.skipif(not HAVE_Q, reason="q not installed")
TRAPS = Path(__file__).parent.parent / "corpus" / "traps"


@pytest.fixture(scope="module")
def result():
    return analyse(TRAPS)


def test_trap_corpus_exact(result):
    ev = evaluate(result, json.loads((TRAPS / "truth.json").read_text()))
    assert ev["extra"] == [] and ev["missing"] == [] and ev["nodes_missing"] == []


def test_case_sensitive_ids(result):
    ids = {n["label"]: n["id"] for n in result["nodes"] if n["label"] in ("l", "L")}
    assert len(set(ids.values())) == 2


def test_bad_statement_loses_only_itself(result):
    diag = result["meta"]["diagnostics"]
    assert [d["line"] for d in diag if d["file"] == "indirect.q"] == [4]
    labels = {n["label"] for n in result["nodes"]}
    assert "after" in labels


def test_scores_and_labels(result):
    for e in result["edges"]:
        assert e["confidence"] in ("EXTRACTED", "INFERRED", "AMBIGUOUS")
        assert e["evidence"] and e["tier"]
    unresolved = [e for e in result["edges"] if e["tier"] == "S-unresolved"]
    assert unresolved and all(e["confidence"] == "AMBIGUOUS" for e in unresolved)
    assert result["enrichment_queue"]


def test_qsql_columns_not_references(result):
    lab = {n["id"]: n["label"] for n in result["nodes"]}
    tgt = {lab[e["target"]] for e in result["edges"] if lab[e["source"]] == "colsel"}
    assert tgt == {"trades"}  # px/sym are columns; global px is not referenced


def test_reserved_word_assignment_is_diagnostic(tmp_path):
    (tmp_path / "a.q").write_text("cols:{x}\nok:{x}\n")
    r = analyse(tmp_path)
    assert any(d["error"] == "assign" for d in r["meta"]["diagnostics"])
    assert "ok" in {n["label"] for n in r["nodes"]}
