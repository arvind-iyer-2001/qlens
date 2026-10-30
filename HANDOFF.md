# Handoff — 2026-10-30

## State
qlens: greenfield q/kdb+ knowledge-graph tool; q itself is the parser (SPEC.md is source of truth). Only M0 (spike) is done: no code, no tests. Findings are in `docs/Q_FACTS.md`.

## Done this session
- M0 spike: verified parse/value behaviour for `\d`, `\l`, `system`, dotted assignment, adverbs, qsql, nested lambdas, crash probes (`43d8dca`, `4c792d8`).
- Chose tagged-tree JSON wire format (prototype only, in scratchpad).

## In progress
- Waiting on Arvind: go-ahead for M1 plus answers to the q-version and unary-minus questions below.

## Open tasks
| # | Task | Priority | Area |
|---|------|----------|------|
| 1 | Decide: q 4.x binary available? Or `-name` -> `neg name` fallback at lower confidence | High | M1/M2 |
| 2 | M1: splitter, discovery, content check, tests | High | M1 |
| 3 | M2: sandboxed static pass, graph builder, trap corpus | High | M2 |
| 4 | Re-run unmeasured probes: 100k-deep parens, 2000-nested braces | Low | M0 |
| 5 | M3-M8 per SPEC section 9 | Normal | later |

## Constraints & assumptions
- Fully greenfield: no earlier projects (q-tree-sitter, tree-sitter-q, better-q-graphify, qverify, graphify); no tree-sitter.
- uv only. No commit trailers. No remote or push until Arvind says so.
- Third-party q code runs only in the sandbox and only with `--execute`.
- Quote errors verbatim; never claim unmeasured results. Stop and report after each milestone.
- Normalize backslash commands to `system "..."` form (`\l f.q` -> `system "l f.q"`, `\w` -> `system "w"`, `\d` likewise). Lone `\` is not a command.
- MUST work with graphify: add an export adapter (graphify-compatible graph), no dependency on graphify. Confirm schema source with Arvind first.
- Scratch files go in the session scratchpad, not `/tmp`.

## Gotchas
- Never run q with interactive stdin (hangs); use `q file.q -q </dev/null`.
- This q is version 5 (`.z.K=5f`, `.z.k=2026.05.01`), not 4.x. `parse "-x"` raises `'-` here; `neg x` works.
- `.j.j` is lossy for symbols vs strings and for lambdas; use the tagged tree.
- Untracked `.serena/` is not ours; leave it.

## Commands
- run: `~/.kx/bin/q <file.q> -q </dev/null`  test: none yet
