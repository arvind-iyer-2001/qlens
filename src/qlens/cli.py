from __future__ import annotations

import argparse
import json
import sys

from .evaluate import evaluate
from .graph import analyse, write_outputs


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qlens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build graph.json and report.json")
    b.add_argument("root")
    b.add_argument("--out", required=True)
    b.add_argument("--execute", action="store_true", help="dynamic pass (M4)")
    b.add_argument("--backend", choices=["docker", "sandbox-exec"])
    b.add_argument("--timeout", type=float, default=60)
    x = sub.add_parser("export", help="write a graphify-shaped AST-style JSON (nodes/edges) for q files")
    x.add_argument("source", help="a q directory/file, or an existing graph.json")
    x.add_argument("--out", required=True, help="output .json path")
    x.add_argument("--format", choices=["graphify"], default="graphify")
    x.add_argument("--backend", choices=["docker", "sandbox-exec"])
    ms = sub.add_parser("measure", help="one JSON line of static-vs-dynamic agreement for a repo (runs q on its code, sandboxed)")
    ms.add_argument("root")
    ms.add_argument("--backend", choices=["docker", "sandbox-exec"])
    ms.add_argument("--timeout", type=float, default=30)
    c = sub.add_parser("corpus", help="resumable corpus run, one subprocess per repo")
    c.add_argument("corpora")
    c.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    c.add_argument("--jobs", type=int, default=2)
    c.add_argument("--timeout", type=float, default=600)
    c.add_argument("--out", required=True)
    c.add_argument("--backend", choices=["docker", "sandbox-exec"])
    cal = sub.add_parser("calibrate", help="refit calibration.json from DEV results")
    cal.add_argument("results")
    cal.add_argument("--out", default="src/qlens/calibration.json")
    sm = sub.add_parser("summary", help="precision/recall summary of a results file")
    sm.add_argument("results")
    sm.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    e = sub.add_parser("eval", help="precision/recall against a truth file")
    e.add_argument("root")
    e.add_argument("truth")
    e.add_argument("--backend", choices=["docker", "sandbox-exec"])
    a = ap.parse_args(argv)
    if a.cmd == "build":
        res = analyse(a.root, execute=a.execute, out_dir=a.out, backend=a.backend, timeout=a.timeout, log=_log)
        write_outputs(res, a.out)
        d = len(res["meta"]["diagnostics"])
        print(f"{len(res['nodes'])} nodes, {len(res['edges'])} edges, {len(res['enrichment_queue'])} queued, {d} diagnostics -> {a.out}")
        return 0
    if a.cmd == "corpus":
        from pathlib import Path

        from .corpus import run_corpus

        n = run_corpus(Path(a.corpora), a.split, a.jobs, a.timeout, Path(a.out), a.backend)
        print(f"ran {n} repos -> {a.out}")
        return 0
    if a.cmd == "calibrate":
        from pathlib import Path

        from .corpus import calibrate

        print(json.dumps(calibrate(Path(a.results), Path(a.out)), indent=2))
        return 0
    if a.cmd == "summary":
        from pathlib import Path

        from .corpus import summarise

        sp = ("dev", "test") if a.split == "all" else (a.split,)
        print(json.dumps(summarise(Path(a.results), sp), indent=2))
        return 0
    if a.cmd == "export":
        from pathlib import Path

        from .export import to_graphify

        src = Path(a.source)
        graph = json.loads(src.read_text()) if src.is_file() and src.suffix == ".json" else analyse(src, backend=a.backend)
        res = to_graphify(graph)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False))
        print(f"{len(res['nodes'])} nodes, {len(res['edges'])} edges -> {a.out}")
        return 0
    if a.cmd == "measure":
        res = analyse(a.root, execute=True, backend=a.backend, timeout=a.timeout, log=_log)
        dyn = {k: v for k, v in res["meta"]["dynamic"].items() if k != "load_results"}
        print(json.dumps(dict(root=a.root, **dyn)))
        return 0
    if a.cmd == "eval":
        res = analyse(a.root, backend=a.backend)
        truth = json.load(open(a.truth))
        print(json.dumps(evaluate(res, truth), indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
