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

### Cause analysis of dev runs 1-2 (from `measure --examples` on puzzle_solutions and quantQ)

- Refuted: every example was a spurious self-edge. A top-level definition `.ns.f:{...}` writes the global `.ns.f`; the
  wrapper-lambda free-name list reports that write and it was recorded as `f` writes `f`. q correctly lists no such
  reference, so each was marked refuted. Fixed: a definition's own assignment target is not a reference.
- Missed: names such as `ltrim`, `rtrim`, `.Q.v`, `.Q.pf` came from q's own keyword implementations (k lambdas such as
  `trim`) that appear as constants of user functions; the live side recursed into them. Fixed: only lambdas that are not
  `k)` lambdas are followed.
- Runs 1-2 numbers above are therefore partly measurement error and are superseded; run 3 is needed.

## Dev run 3 (out/dev3.jsonl, 116 dev repos, code at the commit "Fix spurious self-write edges...")

Reference-edge precision 0.9862 (agree 9709, refuted 136), recall 0.9993 (missed 7), per-repo precision median 1.0,
p10 0.917. 101 of 116 repos have zero refuted edges. Against the spec targets on dev: precision >= 98.5% met,
recall >= 96% met, median 100% met, p10 >= 95% NOT met (0.917). Largest remaining refuted: TorQ 38, pykx 31, ws.q 15.
Definitions: 10373 confirmed live, 196 refuted, 2291 defined at runtime that the static pass did not see (unexamined).
Coverage caveat: 948 files loaded, 1122 failed to load (not judged), 48 process failures; the numbers describe the
loadable subset. Test split not run. Indirect: 927 agree / 15 refuted. Namespace-context mismatches: 4.

### Cause analysis of dev run 3 (examples from TorQ, pykx, ws.q)

Five measurement/attribution bugs found, all in qlens, fixed in the commit after run 3:
1. Several definitions on one line (`del:{..};.z.pc:{..}`): every reference on the line was given to every function
   defined on it. Now each definition owns only the references in its own right-hand side; the rest belongs to the file.
2. Names defined only inside `$[c;..]`/`if[]`/`while[]`/`do[]` are marked conditional (tier S-indirect) and are not refuted
   when q never ran that branch.
3. `value` lists the definition namespace and a same-named variable (`cache` inside `.cache`) as one entry; that name is no
   longer judged either way.
4. A name defined more than once in a file: live q holds only the last, so its edges are not judged.
5. A namespace/dictionary that holds other defined names (`.pm.auth` holding `.pm.auth.ldap`) is no longer a "missed" definition.
Dev run 3 numbers (98.6% / 99.9% / median 1.0 / p10 0.917) therefore still include these artefacts; run 4 is needed.

## Dev run 4 (out/dev4.jsonl, 116 dev repos, code at the commit "Per-definition reference attribution...")

Reference edges: precision 0.9998 (agree 9672, refuted 2), recall 1.0 (missed 0), per-repo precision median 1.0, p10 1.0.
114 of 116 repos have zero refuted edges. All four dev targets from SPEC section 1 are met on the dev split.
Indirect edges: 952 agree / 1 refuted. Dangling (unresolved) references: 802. Namespace-context mismatches: 4.
Definitions: 10373 confirmed live, 169 refuted, 1924 defined at runtime but not seen statically
(puzzle_solutions 1024, quantQ 461, sphinxQ 107, kdbslack 75, btick 63; refuted: peachq 72, kdbx-modules 29, kdbslack 17,
TorQ 10, jupyterq 10). Definition recall about 84% (10373 / 12297), not yet analysed.

What the edge metric does and does not show: it compares static references with `value` of the live function, and both
come from q's compiler, so agreement on a function body is expected. It does not test that a name is bound to the right
definition when several exist. Coverage: 948 of 2070 files loaded; the other files are not judged.
The test split has not been run. Run 4 is the dev result to report; do not tune on the test split.

### Cause analysis of dev run 4 definition gaps (examples from puzzle_solutions, quantQ, peachq)

- peachq (72 refuted defs): `system "d .pkg";` with a trailing `;` did not match the namespace-switch detector, so
  functions were filed under the wrong name. Fixed.
- puzzle_solutions genarch (refuted `.genarch.state:(::)` etc.): q's `\v` omits variables whose value is `::`; the live
  listing now uses `key`. Fixed.
- quantQ tests / puzzle_solutions arch1 (missed defs): names defined in OTHER files that the target loads through a computed
  path (`system "l ",.qt.libDir,"/",x`). They are counted as `defs_elsewhere`, and the real dependency q revealed is added as a
  D2 `imports` edge. Names built at runtime with `(` sv fullNs,`addInput) set ...` that exist in no file remain genuinely
  invisible to a static pass and stay in `defs_missed`.

## Dev run 5 (out/dev5.jsonl, 116 dev repos, code at the commit "Namespace switch with trailing ;, live listing via key...")

Reference edges: precision 0.9998 (agree 9765, refuted 2), recall 1.0 (missed 0), per-repo median 1.0, p10 1.0.
Definitions: 10449 confirmed live, 88 refuted (precision 0.9916), 79 missed (recall 0.9925), plus 1832 names defined in
a different file than the one being loaded (counted as dependencies, with D2 `imports` edges, not as confirmations or misses).
Indirect edges 955 agree / 1 refuted. Dangling references 804. Namespace-context mismatches 0.
Files: 947 loaded, 1122 failed to load (not judged), 49 process failures (timeouts/crashes; one more than run 4, so
file-level outcomes are not perfectly deterministic).
Remaining refuted definitions by repo: kdbx-modules 28, kdbslack 17, peachq 13, jupyterq 10, aoc 6 (not analysed).
Remaining missed: puzzle_solutions 31, qspec 13, dpy 8, kdbx-modules 7. This is the final dev result; the code is
frozen for the one test-split run. Nothing is tuned on the test split.

## TEST split, single run (out/test1.jsonl, 19 held-out repos, code at 982afc3, nothing tuned afterwards)

Reference edges: precision 1.0 (agree 1958, refuted 0), recall 1.0 (missed 0), per-repo precision median 1.0, p10 1.0.
Indirect edges 174 agree / 0 refuted. Dangling references 266. Namespace mismatches 0.
Definitions: 1679 confirmed live, 0 refuted (precision 1.0), 25 missed (recall 0.9853), 53 defined in another file.
Files: 171 loaded, 147 failed to load (not judged), 3 process failures.

Limits of this number, stated plainly:
- Small and concentrated: KxSystems/ml contributes 1104 of 1958 edges (56%). 5 of 19 repos had no judged edges (no file loaded),
  so the effective sample is 14 repos. Zero refuted of 1958 edges is consistent with a true error rate up to roughly 0.15%.
- About 46% of files load in q here (dev 947/2069, test 171/318); the metric is silent about the rest.
- The metric compares static references with `value` of the live function (both from q's compiler); it does not test that each
  name binds to the right definition when several exist.
- Outliers: no repo dominates misses (missed edges 0). Dev outliers for definitions are listed under dev run 5.
Spec targets on held-out data (precision >= 99%; recall reported): met. This is the one test run; it is not to be repeated
after further changes, and any later code change must be reported as made after seeing test data.

## After the held-out run: dynamic pass launches the target as the main script
Made AFTER the single test run (test split not re-run, nothing tuned on it). Dev run 6 added `load_causes` to the output:
of 1122 dev files that did not load, 596 stopped on "missing or unreadable file". Part of that was a qlens bug: `.z.f` pointed at
qlens's own harness, so files locating their folder from it looked inside qlens (e.g. kdbx-modules,
`.../qlens/src/qlens/q/dynamic.q/analytics.q: Not a directory`). Fixed by launching the target as the main script.
Other causes are environment limits, not bugs: puzzle input files absent from the repo (Advent-of-Code repos: 4 repos, ~364 files),
downloads and network (`.ut.download`, `hop`), framework bootstrap (`.proc.getconfigfile`), embedPy (`.p.import`).

Dev run 7 (after the fix; dev split only):
- Files loaded 947 -> 988 of 2069 (45.8% -> 47.1%), almost all in kdbx-modules (70 -> 111). Process failures 49 -> 19.
- Reference edges judged 9765 -> 9838; refuted 2 -> 2; missed 0 -> 0; precision 0.99980, recall 1.0 (unchanged).
- Definitions: refuted 88 -> 90 (+2, kdbx-modules), missed 79 -> 270. More code now runs, so more runtime-created names show up:
  `k)` definitions and state created inside functions (quantQ's test files create framework state; kdb-taq defines `o,F,S,dst,D` on a `k)` line).
  These are gaps in the static pass's view of definitions, not wrong edges. Files that call `exit` before finishing (43 in amber's bench)
  are reported as "exited before the file finished loading": names defined before the exit are confirmed, nothing after it is judged.
- q-evm 3 -> 2 loaded files: per-file results (`--load-results`) show 2 of 8 load; 3 stop on `'assign` (keyword assignment, the q 5 limit),
  `globals.q` on `hopen` of a unix socket, others on network or a missing path. Which file loaded before is not identified.
- Cause found for the refuted definitions (88 in run 6, 90 in run 7: kdbx-modules, kdbslack, peachq, jupyterq, ...): a name like `lin.sendevent:{..}`
  at the root makes `lin` a dictionary variable, and `lin.sendevent` resolves through its keys. The snapshot saw only `lin`, so correct
  definitions were marked S-refuted (confidence 0.10). Fixed in the merge: a static name that is a key of a live dictionary is confirmed
  (evidence says so); a name that is not a key is still refuted (tested both ways). Effect not yet measured (dev run 8 pending).
