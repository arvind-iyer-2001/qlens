"""Dynamic pass (tier D, opt-in --execute): load each file in an isolated sandboxed q process."""

from __future__ import annotations

import json
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


def run_file(
    target: Path,
    deps: list[Path],
    namespaces: list[str],
    base: Path,
    cwd: Path,
    timeout: float = 30,
    backend: str | None = None,
) -> DynFile:
    script = _script()
    with tempfile.TemporaryDirectory(prefix="qlens-dyn-") as td:
        tmp = Path(td).resolve()
        out = tmp / "result.json"
        args = [str(script), "-target", str(target), "-deps", ",".join(map(str, deps)), "-ns", ",".join(namespaces), "-out", str(out), "-q"]
        res = run_q(args, read_paths=[base, script.parent], write_dir=tmp, timeout=timeout, backend=backend, cwd=cwd)
        if not out.exists():
            why = "timeout" if res.timed_out else f"no result (rc={res.returncode}): {(res.stderr or res.stdout).strip()[:200]}"
            return DynFile(failure=why)
        try:
            d = json.loads(out.read_text())
        except json.JSONDecodeError as e:
            return DynFile(failure=f"unreadable result: {e}")
    return DynFile(
        loaded=bool(d.get("loaded")),
        error=d.get("error") or "",
        dep_errors=d.get("dep_errors") or [],
        defs={x["name"]: x for x in d.get("defs", [])},
    )


def run_all(
    files: list[dict], imports: dict[str, list[str]], namespaces: list[str], base: Path, timeout: float = 30, backend: str | None = None, jobs: int = 4
) -> dict[str, DynFile]:
    by_rel = {f["rel"]: f for f in files}

    def one(f: dict) -> tuple[str, DynFile]:
        deps = [by_rel[d]["path"] for d in dependency_order(f["rel"], imports) if d in by_rel]
        return f["rel"], run_file(f["path"], deps, namespaces, base, f["repo"], timeout, backend)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return dict(ex.map(one, files))
