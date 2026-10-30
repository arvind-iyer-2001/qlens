"""Dynamic pass (tier D, opt-in --execute): load each file in an isolated sandboxed q process."""

from __future__ import annotations

import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .sandbox import run_q


@dataclass
class DynFile:
    loaded: bool = False
    error: str = ""
    dep_errors: list[dict] = field(default_factory=list)
    defs: dict[str, dict] = field(default_factory=dict)  # qualified name -> info
    failure: str | None = None  # process-level problem (timeout, crash, no output)


def _script() -> Path:
    return Path(str(resources.files("qlens") / "q" / "dynamic.q"))


def dependency_order(rel: str, imports: dict[str, list[str]]) -> list[str]:
    """Transitive imports of `rel` in load order (deps first), cycles broken, excluding `rel`."""
    seen: set[str] = {rel}
    order: list[str] = []

    def go(x: str) -> None:
        for d in imports.get(x, []):
            if d not in seen:
                seen.add(d)
                go(d)
                order.append(d)

    go(rel)
    return order


_ERR_LINE = re.compile(r"^'(?:\d{4}\.\d\d\.\d\dT[\d:.]+ )?(.+)$", re.M)


def run_file(
    target: Path,
    deps: list[Path],
    namespaces: list[str],
    base: Path,
    cwd: Path,
    timeout: float = 30,
    backend: str | None = None,
) -> DynFile:
    """Load `target` as the main script of a sandboxed q, after its dependencies, and report what it defined.

    The target is the main script (not loaded by a harness) so `.z.f` and relative paths behave as they do when
    a user runs `q <target>` from the repo root. A harness preloaded through QINIT reports the result, and the
    error, if the file stopped on one, is read from q's own error line.
    """
    script = _script()
    with tempfile.TemporaryDirectory(prefix="qlens-dyn-") as td:
        tmp = Path(td).resolve()
        out = tmp / "result.json"
        try:
            main = str(Path(target).resolve().relative_to(Path(cwd).resolve()))
        except ValueError:
            main = str(target)
        env = {"QINIT": str(script), "QLENS_OUT": str(out), "QLENS_DEPS": ",".join(map(str, deps)), "QLENS_NS": ",".join(namespaces)}
        res = run_q([main, "-q"], read_paths=[base, script.parent], write_dir=tmp, timeout=timeout, backend=backend, cwd=cwd, env=env, stdin_text=".dy.fin[]\n")
        if not out.exists():
            why = "timeout" if res.timed_out else f"no result (rc={res.returncode}): {(res.stderr or res.stdout).strip()[:200]}"
            return DynFile(failure=why)
        try:
            d = json.loads(out.read_text())
        except json.JSONDecodeError as e:
            return DynFile(failure=f"unreadable result: {e}")
    loaded, error = bool(d.get("loaded")), d.get("error") or ""
    m = _ERR_LINE.search(f"{res.stderr}\n{res.stdout}")
    if m:  # the main script stopped on an error: q prints it and goes on to read stdin
        loaded, error = False, m.group(1).strip()
    return DynFile(
        loaded=loaded,
        error=error,
        dep_errors=d.get("dep_errors") or [],
        defs={x["name"]: x for x in d.get("defs", [])},
    )


def run_all(
    files: list[dict], imports: dict[str, list[str]], namespaces: list[str], base: Path, timeout: float = 30, backend: str | None = None, jobs: int = 4, log=None
) -> dict[str, DynFile]:
    log = log or (lambda m: None)
    counter = {"n": 0}
    by_rel = {f["rel"]: f for f in files}

    def one(f: dict) -> tuple[str, DynFile]:
        deps = [by_rel[d]["path"] for d in dependency_order(f["rel"], imports) if d in by_rel]
        d = run_file(f["path"], deps, namespaces, base, f["repo"], timeout, backend)
        counter["n"] += 1
        what = "loaded ok" if d.loaded else (f"process problem: {d.failure}" if d.failure else f"load stopped: {d.error[:60]}")
        log(f"  [{counter['n']}/{len(files)}] {f['rel']}: {what}, {len(d.defs)} names defined")
        return f["rel"], d

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return dict(ex.map(one, files))
