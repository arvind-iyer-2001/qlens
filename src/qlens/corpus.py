"""Corpus runs: dev/test split by sha1 of the repo dir name, one subprocess per repo, resumable."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .scoring import TIERS


def split_of(name: str) -> str:
    """Stable: 20% of repos are `test`, the rest `dev`."""
    return "test" if int(hashlib.sha1(name.encode()).hexdigest()[:8], 16) % 5 == 0 else "dev"


def repo_dirs(corpora: Path, split: str) -> list[Path]:
    dirs = sorted(p for p in corpora.iterdir() if p.is_dir() and not p.name.startswith("."))
    return [p for p in dirs if split == "all" or split_of(p.name) == split]


def _done(out: Path) -> set[str]:
    if not out.exists():
        return set()
    done = set()
    for line in out.read_text().splitlines():
        try:
            done.add(json.loads(line)["repo"])
        except (json.JSONDecodeError, KeyError):
            pass
    return done


def run_corpus(corpora: Path, split: str, jobs: int, timeout: float, out: Path, backend: str | None = None) -> int:
    todo = [p for p in repo_dirs(corpora, split) if p.name not in _done(out)]
    lock = threading.Lock()
    out.parent.mkdir(parents=True, exist_ok=True)

    def one(p: Path) -> None:
        t = time.time()
        cmd = [sys.executable, "-m", "qlens.cli", "measure", str(p), "--timeout", str(min(timeout, 60))]
        if backend:
            cmd += ["--backend", backend]
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if cp.returncode == 0 and cp.stdout.strip():
                rec = json.loads(cp.stdout.strip().splitlines()[-1])
                rec.update(status="ok")
            else:
                rec = dict(status="error", error=(cp.stderr or cp.stdout).strip()[-300:])
        except subprocess.TimeoutExpired:
            rec = dict(status="timeout")
        except json.JSONDecodeError as e:
            rec = dict(status="error", error=f"bad measure output: {e}")
        rec.update(repo=p.name, split=split_of(p.name), seconds=round(time.time() - t, 1))
        with lock, out.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        list(ex.map(one, todo))
    return len(todo)


def summarise(results: Path, splits: tuple[str, ...] = ("dev",)) -> dict:
    """Pooled precision/recall plus per-repo precision distribution and the biggest contributors to misses."""
    recs = [json.loads(x) for x in results.read_text().splitlines() if x.strip()]
    recs = [r for r in recs if r.get("status") == "ok" and r["split"] in splits]
    agree = sum(r["agree"] for r in recs)
    refuted = sum(r["refuted"] for r in recs)
    missed = sum(r["missed"] for r in recs)
    per_repo = sorted(r["agree"] / (r["agree"] + r["refuted"]) for r in recs if r["agree"] + r["refuted"] > 0)
    pct = lambda q: per_repo[min(len(per_repo) - 1, int(q * len(per_repo)))] if per_repo else None  # noqa: E731
    return dict(
        repos=len(recs), agree=agree, refuted=refuted, missed=missed,
        precision=agree / (agree + refuted) if agree + refuted else None,
        recall=agree / (agree + missed) if agree + missed else None,
        per_repo_precision_median=pct(0.5), per_repo_precision_p10=pct(0.1),
        top_missed=sorted(((r["repo"], r["missed"]) for r in recs), key=lambda x: -x[1])[:5],
    )  # fmt: skip


def calibrate(results: Path, out: Path, allow_test: bool = False) -> dict:
    """Refit tier scores from DEV measurements only (the held-out split is never tuned on)."""
    if allow_test:
        raise SystemExit("refusing: the test split is never used for calibration")
    s = summarise(results, ("dev",))
    recs = [json.loads(x) for x in results.read_text().splitlines() if x.strip()]
    recs = [r for r in recs if r.get("status") == "ok" and r["split"] == "dev"]
    ia = sum(r.get("indirect_agree", 0) for r in recs)
    ir = sum(r.get("indirect_refuted", 0) for r in recs)
    from .scoring import load_scores

    scores = dict(load_scores())
    if s["precision"] is not None and s["agree"] + s["refuted"] >= 200:
        scores["S"] = round(min(0.99, max(0.5, s["precision"])), 3)
    if ia + ir >= 50:
        scores["S-indirect"] = round(min(0.89, max(0.5, ia / (ia + ir))), 3)
    doc = {t: scores[t] for t in TIERS} | {"_fit": dict(split="dev", repos=s["repos"], precision=s["precision"], indirect=[ia, ir])}
    out.write_text(json.dumps(doc, indent=2))
    return doc
