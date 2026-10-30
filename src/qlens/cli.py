from __future__ import annotations

import argparse
import json
import sys

from .evaluate import evaluate
from .graph import analyse, write_outputs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qlens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build graph.json and report.json")
    b.add_argument("root")
    b.add_argument("--out", required=True)
    b.add_argument("--execute", action="store_true", help="dynamic pass (M4)")
    b.add_argument("--backend", choices=["docker", "sandbox-exec"])
    b.add_argument("--timeout", type=float, default=60)
    ms = sub.add_parser("measure", help="one JSON line of static-vs-dynamic agreement for a repo (runs q on its code, sandboxed)")
    ms.add_argument("root")
    ms.add_argument("--backend", choices=["docker", "sandbox-exec"])
    ms.add_argument("--timeout", type=float, default=30)
    e = sub.add_parser("eval", help="precision/recall against a truth file")
    e.add_argument("root")
    e.add_argument("truth")
    e.add_argument("--backend", choices=["docker", "sandbox-exec"])
    a = ap.parse_args(argv)
    if a.cmd == "build":
        res = analyse(a.root, execute=a.execute, out_dir=a.out, backend=a.backend, timeout=a.timeout)
        write_outputs(res, a.out)
        d = len(res["meta"]["diagnostics"])
        print(f"{len(res['nodes'])} nodes, {len(res['edges'])} edges, {len(res['enrichment_queue'])} queued, {d} diagnostics -> {a.out}")
        return 0
    if a.cmd == "measure":
        res = analyse(a.root, execute=True, backend=a.backend, timeout=a.timeout)
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
