import json

import pytest

from qlens.corpus import calibrate, run_corpus, split_of, summarise
from qlens.sandbox import find_q

try:
    find_q()
    HAVE_Q = True
except Exception:
    HAVE_Q = False


def test_split_is_stable_and_roughly_80_20():
    names = [f"owner__repo{i}" for i in range(500)]
    assert [split_of(n) for n in names] == [split_of(n) for n in names]
    frac = sum(split_of(n) == "test" for n in names) / len(names)
    assert 0.1 < frac < 0.3


def _rec(repo, split, agree, refuted, missed, ia=0, ir=0):
    return dict(status="ok", repo=repo, split=split, agree=agree, refuted=refuted, missed=missed, indirect_agree=ia, indirect_refuted=ir)


def test_summary_and_calibrate_use_dev_only(tmp_path):
    res = tmp_path / "r.jsonl"
    rows = [_rec("a", "dev", 190, 10, 5), _rec("b", "dev", 100, 0, 50, 60, 10), _rec("c", "test", 1, 99, 0)]
    res.write_text("\n".join(json.dumps(r) for r in rows))
    s = summarise(res, ("dev",))
    assert s["repos"] == 2 and s["agree"] == 290 and s["refuted"] == 10
    assert abs(s["precision"] - 290 / 300) < 1e-9 and abs(s["recall"] - 290 / 345) < 1e-9
    out = tmp_path / "cal.json"
    doc = calibrate(res, out)
    assert doc["S"] == round(290 / 300, 3)  # test-split row (precision 1%) did not leak in
    assert doc["S-indirect"] == round(60 / 70, 3)
    assert doc["D3"] == 0.98 and doc["_fit"]["split"] == "dev"
    with pytest.raises(SystemExit):
        calibrate(res, out, allow_test=True)


@pytest.mark.skipif(not HAVE_Q, reason="q not installed")
def test_run_corpus_is_resumable(tmp_path):
    corp = tmp_path / "corpora"
    for name in ("o__one", "o__two"):
        (corp / name).mkdir(parents=True)
        (corp / name / "a.q").write_text("g:{x}\nf:{g x}\n")
    out = tmp_path / "res.jsonl"
    assert run_corpus(corp, "all", jobs=2, timeout=120, out=out) == 2
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert {r["repo"] for r in rows} == {"o__one", "o__two"} and all(r["status"] == "ok" for r in rows)
    assert all(r["agree"] >= 1 and r["refuted"] == 0 for r in rows)
    assert run_corpus(corp, "all", jobs=2, timeout=120, out=out) == 0  # nothing left to do


@pytest.mark.skipif(not HAVE_Q, reason="q not installed")
def test_measure_examples_cli(tmp_path):
    from qlens.cli import main

    (tmp_path / "a.q").write_text("g:{x}\nf:{g x}\n")
    ex = tmp_path / "ex.json"
    assert main(["measure", str(tmp_path), "--examples", str(ex)]) == 0
    assert json.loads(ex.read_text()) == []  # nothing disputed in clean code
