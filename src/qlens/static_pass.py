"""Run the q static pass (src/qlens/q/static.q) over many statements, sandboxed and crash-tolerant."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .sandbox import run_q

CHUNK = 400


@dataclass
class StaticResult:
    ok: bool
    tree: dict | None = None
    free: list[str] | None = None
    err: str | None = None


@dataclass
class StaticRun:
    results: dict[int, StaticResult] = field(default_factory=dict)
    builtins: set[str] = field(default_factory=set)
    qver: float | None = None
    crashes: list[str] = field(default_factory=list)


def _script() -> Path:
    return Path(str(resources.files("qlens") / "q" / "static.q"))


def _read_out(path: Path, run: StaticRun) -> None:
    if not path.exists():
        return
    for line in path.read_text(errors="replace").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue  # torn last line after a crash
        if d.get("kind") == "meta":
            run.builtins |= {b for b in d.get("builtins", []) if b}
            run.qver = d.get("qver")
        elif "i" in d:
            run.results[int(d["i"])] = (
                StaticResult(True, d.get("tree"), d.get("free") or [])
                if d.get("ok")
                else StaticResult(False, err=str(d.get("err")))
            )


def run_static(
    texts: dict[int, str],
    root: Path,
    timeout: float = 60,
    backend: str | None = None,
    tmp_base: Path | None = None,
) -> StaticRun:
    """texts: global statement id -> text. A crash or timeout loses only the culprit statement."""
    run = StaticRun()
    pending = sorted(texts)
    script = _script()
    with tempfile.TemporaryDirectory(prefix="qlens-", dir=tmp_base) as td:
        tmp = Path(td).resolve()
        n = 0
        while pending:
            chunk, pending = pending[:CHUNK], pending[CHUNK:]
            n += 1
            inp, out = tmp / f"in{n}.json", tmp / f"out{n}.jsonl"
            inp.write_text(json.dumps([{"i": i, "t": texts[i]} for i in chunk]))
            out.unlink(missing_ok=True)
            res = run_q(
                [str(script), "-in", str(inp), "-out", str(out), "-q"],
                read_paths=[root, script.parent],
                write_dir=tmp,
                timeout=timeout,
                backend=backend,
            )
            before = set(run.results)
            _read_out(out, run)
            done = set(run.results) - before
            missing = [i for i in chunk if i not in done]
            if missing:
                bad = missing[0]
                why = "timeout" if res.timed_out else f"q exited rc={res.returncode}: {res.stderr.strip()[:200]}"
                run.results[bad] = StaticResult(False, err=f"static pass crashed: {why}")
                run.crashes.append(f"statement {bad}: {why}")
                pending = missing[1:] + pending
    return run
