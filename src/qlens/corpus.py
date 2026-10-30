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
    every = repo_dirs(corpora, split)
    todo = [p for p in every if p.name not in _done(out)]
    lock = threading.Lock()
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    state = dict(n=0, ok=0, bad=0, agree=0, refuted=0)

    def say(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    say(f"corpus: split={split}, {len(every)} repos, {len(every) - len(todo)} already done (resuming), {len(todo)} to run, jobs={jobs}")
    say(f"corpus: results append to {out}")

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
        with lock:
            with out.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            state["n"] += 1
            if rec["status"] == "ok":
                state["ok"] += 1
                state["agree"] += rec.get("agree", 0)
                state["refuted"] += rec.get("refuted", 0)
                detail = (
                    f"files loaded {rec.get('files_loaded', 0)}/{rec.get('files_loaded', 0) + rec.get('files_failed', 0)}, "
                    f"edges agree {rec.get('agree', 0)} refuted {rec.get('refuted', 0)} missed {rec.get('missed', 0)}"
                )
            else:
                state["bad"] += 1
                detail = rec.get("error", "")[:120].replace("\n", " ")
            done_n = state["n"]
            elapsed = time.time() - started
            eta = elapsed / done_n * (len(todo) - done_n)
            tot = state["agree"] + state["refuted"]
            prec = f"{100 * state['agree'] / tot:.1f}%" if tot else "n/a"
            say(
                f"[{done_n}/{len(todo)}] {rec['status']:<7} {p.name}  {rec['seconds']}s  {detail}\n"
                f"          running: ok {state['ok']} bad {state['bad']}, precision so far {prec}, "
                f"elapsed {elapsed / 60:.1f}m, about {eta / 60:.1f}m left"
            )

    running: dict[str, float] = {}
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(60):
            with lock:
                now = time.time()
                busy = ", ".join(f"{k} ({(now - v) / 60:.1f}m)" for k, v in running.items())
            if busy:
                say(f"  ... still running: {busy}")

    def start(p: Path) -> None:
        with lock:
            running[p.name] = time.time()
        say(f"  starting {p.name} ...")
        try:
            one(p)
        finally:
            with lock:
                running.pop(p.name, None)

    threading.Thread(target=heartbeat, daemon=True).start()
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        list(ex.map(start, todo))
    stop.set()
    say(f"corpus: done, {state['ok']} ok, {state['bad']} bad in {(time.time() - started) / 60:.1f}m")
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
