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

## Dev run 1 (out/dev1.jsonl, 116 dev repos, code at f7e6ba0) — superseded, do not mix with later runs

precision 0.7505 (agree 9194, refuted 3056), recall 0.9992 (missed 7), per-repo precision median 0.884,
p10 0.536. 948 files loaded, 1122 failed to load, 48 process failures. Far below the 98.5% target.
Cause found by analysis: the live comparison used the outer function's `value` free list, which omits names used
only inside nested lambdas, so edges from nested lambdas were marked refuted. This is a measurement bug, fixed
in the commit after f7e6ba0 (static and live sides both use outer + nested free names). Run 2 is needed to see
what remains. Other refuted sources are not yet known.

## Dev run 2 (out/dev2.jsonl, 116 dev repos, code at 60b663d)

precision 0.7949 (agree 9737, refuted 2513), recall 0.8896 (missed 1208), per-repo precision median 0.957, p10 0.595.
65 of 116 repos had zero refuted edges. 948 files loaded, 1122 failed, 48 process failures. Indirect edges: 927 agree,
15 refuted. Defs: 10373 confirmed live, 196 refuted, 2291 defined at runtime that static missed.
The nested-lambda fix helped (3056 -> 2513 refuted) but is not the main cause, and "missed" rose from 7 to 1208
because the live side now includes nested names. Still far below the 98.5% target; cause unknown until examples
are inspected (`qlens measure REPO --examples FILE`).
