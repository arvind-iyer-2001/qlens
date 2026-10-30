# qlens

Knowledge graph of q/kdb+ source with a confidence score on every node and edge. q itself is the parser
(`parse` and `value` are inert), so there is no tree-sitter grammar and no LLM. See SPEC.md.

## Install and test (uv only)

```bash
uv sync
uv run pytest -q
```

Needs a q binary: `$Q`, else `~/.kx/bin/q`, plus a licence (`$QLIC`/`$QHOME` or `~/.kx/kc.lic`).

## Build a graph

```bash
uv run qlens build /path/to/q/workspace --out out/ws            # static pass only (safe)
uv run qlens build /path/to/q/workspace --out out/ws --execute  # also loads files in q to confirm (runs third-party code, sandboxed)
uv run qlens export /path/to/q/workspace --out out/ws.graphify.json   # graphify-shaped nodes/edges
```

Outputs `graph.json` and `report.json` (counts, diagnostics, enrichment queue, load results).
Every node/edge has `tier`, `confidence` (EXTRACTED >= 0.9, INFERRED >= 0.5, else AMBIGUOUS), `confidence_score`, `evidence`.

## Sandbox backends

The static pass also runs inside the sandbox. Pick with `--backend` or `QLENS_BACKEND`:

- macOS default `sandbox-exec`: no network, writes only to a temp dir, exec only q, no reads under `$HOME`
  except the q install, the target root and qlens's own scripts.
- Linux default `docker`: `--network none --read-only --cap-drop ALL --security-opt no-new-privileges
  --pids-limit 256 --memory 2g --cpus 1`, workspace + q install + licence mounted read-only at their host
  paths, one writable temp bind. The image must be a glibc image already present locally:

```bash
docker pull debian:stable-slim            # or any glibc image you already have
export QLENS_IMAGE=debian:stable-slim     # image used for the sandbox
export Q=/path/to/q                       # q binary (glibc build)
export QLIC=/path/to/kc.lic               # licence file or directory
uv run qlens build /path/to/workspace --out out/ws --backend docker
```

Recommended order on the Linux server: (1) static build of the workspace, (2) `--execute` on ONE small repo,
(3) `--execute` on the workspace. A hang, crash or `exit` in one file never loses the others (per-file timeout, `--timeout`).

Residual risk: a native `.so` shipped in a repo would run inside the sandbox. `--execute` stays opt-in.

## Commands

| command | what |
|---|---|
| `qlens build ROOT --out DIR [--execute] [--backend B] [--timeout S]` | graph.json + report.json |
| `qlens export SRC --out FILE` | graphify-shaped JSON (SRC = q dir or graph.json) |
| `qlens eval ROOT TRUTH.json` | precision/recall against a hand-made truth file |
| `qlens measure ROOT` | one JSON line of static-vs-live agreement (runs q on the code, sandboxed) |
| `qlens corpus DIR --split dev\|test\|all --jobs N --timeout S --out results.jsonl` | resumable corpus run |
| `qlens calibrate RESULTS.jsonl` | refit calibration.json from measurements |

q backslash commands are normalised to `system "..."` (`\l f.q` -> `system "l f.q"`).
Known limit on q 5 builds: unary minus on a name (`-x`) and assignment to q keywords fail in q's own parser;
those statements are reported as diagnostics, not guessed. See docs/Q_FACTS.md.
