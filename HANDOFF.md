# Handoff — 2026-10-30 (updated after graphify plugin work)

## State
qlens extracts a q/kdb+ knowledge graph deterministically (no LLM, no tree-sitter): q's own `parse`/`value` is the parser, every node/edge has tier + confidence + evidence. Works: discovery, splitter, sandboxed static pass, graph builder, trap corpus (exact), dynamic `--execute` pass (D2/D3/refuted), graphify-shaped export, corpus tooling, 43 tests green. Purpose: graphify has no tree-sitter grammar for q, so qlens supplies the AST-step equivalent for `.q` files; graphify would call `qlens export` for q files and merge by node id.

## Done this session
- M0 spike (`docs/Q_FACTS.md`), M1 splitter/discovery, M2 static pass + graph + trap corpus, M3 calibration/report, M4 dynamic pass + tests, graphify export (`src/qlens/export.py`), multi-repo resolution fix (M7), README (M5 instructions), M6 tooling (`scripts/fetch_corpus.py`, `qlens corpus|summary|calibrate`).
- Real-repo trial (static only): KxSystems/kdb parses with 1 diagnostic; sambacha/q-evm has k-syntax files (honest diagnostics).

## Graphify (current)
- All old graphify installs removed from this machine (Arvind's request). Fresh clone of `Graphify-Labs/graphify` (default branch `v8`) at `~/development/graphify`; the earlier `safishamsi/graphify` clone with the q-support commits is gone.
- Branch `plugin-extractors` (1 commit, NOT pushed): `graphify/plugins.py` plugin system (entry-point group `graphify.extractors`, `GRAPHIFY_PLUGINS`, per-file or batch, validated output, no fallback), wired into detect/extract/cache salt/watch, `graphify plugins` command, `docs/PLUGINS.md`, 31 tests. Baseline note: 2 tests in `test_extractor_scan_root_context.py` fail on untouched v8 when run after other files (order-dependent, not ours).
- qlens side: `src/qlens/graphify_plugin.py` (plain dict, no graphify import) + entry point in `pyproject.toml`. Verified end to end: `uv pip install -e /Users/arvindiyer/qlens --python ~/development/graphify/.venv/bin/python`, then `graphify plugins`.

## Next for qlens (loaded rate)
- Only ~46% of files load in q, so the rest is never judged. `qlens measure` and `qlens summary` now record WHY files stop loading (`load_causes`: cause -> [files, sample error, sample file]). Next step needs Arvind: re-run the dev corpus (README command), then `qlens summary` and read `load_causes`; design stubs (hopen, missing files, env) from the top causes. The test split stays untouched; any change made after seeing test data must be reported as such.

## In progress
- Background fetch of up to 250 public q repos into `corpora/` (gitignored; `corpora/MANIFEST.json` lists them). Next: static-build all, error-analyse by cause, fix generally, record in `docs/RESULTS.md`.

## Open tasks
| # | Task | Priority | Area |
|---|------|----------|------|
| 1 | Arvind: decide on q 4.x binary vs `-x` limitation (q5 parser rejects `-name`, keyword assignment) | High | q version |
| 2 | Static-build full corpus; error-analyse; commit MANIFEST.json | High | M6 |
| 3 | Arvind launches `--execute` corpus runs: `qlens corpus corpora --split dev --jobs 4 --timeout 600 --out out/dev1.jsonl`; then `qlens summary`, `qlens calibrate`; test split ONCE at the end | High | M6 |
| 4 | Real run on the Linux server with docker (README steps) | High | M5 |
| 5 | Wire `qlens export` into graphify (graphify-side change, Arvind's repo) | Normal | integration |
| 6 | M8: LLM step for enrichment_queue as INFERRED edges, stub env failures, `.z.m` modules | Later | M8 |

## Constraints & assumptions
- Fully greenfield: no earlier projects (q-tree-sitter, tree-sitter-q, better-q-graphify, qverify); graphify only as output-format target, no dependency, no code read. No tree-sitter.
- uv only. No commit trailers. Remote: `origin` = github.com/arvind-iyer-2001/qlens (PRIVATE, published 2026-10-30 on Arvind's request); push only when asked.
- Third-party q code runs only in the sandbox and only with `--execute`; static pass is also sandboxed.
- Quote errors verbatim; never claim unmeasured results; held-out test split used once, never tuned on.
- Normalize backslash commands to `system "..."` form. Lone `\` is not a command.
- Must work with graphify (export adapter, graphify id rule `{parent}_{stem}_{entity}`, lowercase).
- Scratch files go in the session scratchpad, not `/tmp`. Updates to Arvind: plain language, what and why, concise.

## Gotchas
- Never run q with interactive stdin (hangs); `q script.q args -q </dev/null`; `-q` goes AFTER the script.
- q here is version 5 (`.z.K=5f`): `parse "-x"` raises `'-`; assigning to keywords (`cols:`, `use:`, `neg:`) raises `'assign`.
- Lambda `value` free list: first element is the definition namespace, last is empty; strip both.
- sandbox-exec: pair `deny file-read-data` with `allow file-read-data file-read-metadata`.
- Untracked `.serena/` is not ours.

## Commands
- test: `uv run pytest -q`   build: `uv run qlens build ROOT --out DIR [--execute]`   export: `uv run qlens export ROOT --out FILE`
