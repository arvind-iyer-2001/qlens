# RESULTS

Only measured things are recorded here. No precision/recall figure exists yet: those need the live-load
comparison (`--execute`), which runs third-party code and is launched by Arvind.

## Trap corpus (hand-labelled, `corpus/traps/truth.json`)

Static pass, tier S: precision 1.0, recall 1.0 on the asserted edges (calls/reads/writes/uses/imports) and
nodes. With `--execute`: 27 definitions confirmed live, 14 reference edges confirmed, 0 refuted, 0 namespace
context mismatches. This corpus is small and written by us; it shows the traps are handled, not a general rate.

## Public corpus, static pass only (2026-10-30, code at the commit that added foreign-block handling)

135 repos fetched (`corpora/MANIFEST.json`; GitHub search returned fewer than the 250 aimed for), all
content-checked as q. Static build of all 135: 0 crashes, 2,439 files, 36,253 q statements, 78,080 edges.

- 541 statements (1.5%) did not parse in q. Causes seen in the diagnostics: data files named `.q`
  (Advent-of-Code inputs, circuit files), strings spanning lines, a multi-line function whose closing `}` is in
  column 0 (real q 5 also rejects it), q keywords used as names (`use`, `view`, `neg`), and k-syntax files
  (sambacha/q-evm `src/core.q`). 12 files have more than half their statements unparseable and are listed
  as `suspect_files` in each report.
- 302 `p)`/`d)`/`k)`/`q)` blocks (embedded Python, docs, k, REPL transcripts) are recognised as non-q and
  counted separately as `foreign_blocks`, not as failures.
- Edge tiers: 67k S, 6.5k S-indirect, 4.5k S-unresolved (these go to the enrichment queue).

Before foreign-block handling the statement failure rate was 2.2% (793 of 36,555).

## Not yet measured

- Precision/recall against live q on dev repos, per-repo distribution, held-out test number.
- Real run on the Linux/Docker server.

Commands for Arvind: `uv run qlens corpus corpora --split dev --jobs 4 --timeout 600 --out out/dev1.jsonl`,
then `uv run qlens summary out/dev1.jsonl`. Run the test split once at the end.
