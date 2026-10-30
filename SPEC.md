# qlens: SPEC (greenfield)

Status: spec only. No implementation exists yet. Anyone (or any session) must be able to build the
project from this file alone.

## 0. Ground rules (non-negotiable)

1. FULLY GREENFIELD. New repo at `/Users/arvindiyer/qlens`. Do not use, import, vendor, copy code from,
   or depend on any earlier project: not `q-tree-sitter`, not `tree-sitter-q`, not `better-q-graphify`/`qverify`,
   not `graphify` as a dependency. Do not read those repos for implementation. (This spec records the lessons
   learned; that is all you need.)
2. No tree-sitter and no hand-written q grammar. The parser is **q itself** (see section 3).
3. Python tooling: `uv` only. Never pip, `python -m venv`, or poetry.
4. Git: never add commit trailers or signatures (no `Co-Authored-By`, no "Generated with ...").
   Commit message = subject + optional body. Do not create a GitHub remote or push until the owner says so.
5. Third-party q code is untrusted data. Anything that executes q code runs in a sandbox (section 6) and is
   opt-in (`--execute`). Never run downloaded repos outside the sandbox.
6. Be honest in reporting: quote errors verbatim, state what is unverified, never claim a metric you did not
   measure. Held-out data is used once for the final number and never tuned on.
7. Owner: Arvind. Address as "Arvind". Terse communication preferred.

## 1. Goal

Given a directory (a single repo or a multi-repo workspace) of q/kdb+ source, produce a knowledge graph of
nodes (files, functions, variables, tables) and edges (contains, calls, reads, writes, uses, imports)
where **every node and edge carries a confidence score, a tier (how it was established) and an evidence string**.
The scores must be trustworthy: when the tool says EXTRACTED, it is right ~99% of the time.

Target quality (numbers an earlier prototype reached on public GitHub q repos, measured against q's own
resolution of loaded code; match or beat them):
- precision of reference edges >= 98.5%, recall >= 96% on development repos
- precision >= 99% on a held-out set; report recall honestly, including outlier repos
- per-repo precision: median 100%, p10 >= 95%

Confidence labels (fixed, keep identical semantics): score >= 0.9 -> `EXTRACTED`; >= 0.5 -> `INFERRED`;
otherwise `AMBIGUOUS`. Output is a plain JSON graph (section 7), consumable by graphify-style tools
but with no dependency on any.

## 2. Why this is hard (what the earlier prototype learned)

q is unusual:
- Functions are assignments of lambdas: `f:{x+g y}`; there is no `def`.
- Namespaces: `\d .gw` or `system"d .gw"` switches the current namespace; unqualified names in later
  definitions live in it (`f` -> `.gw.f`). Names starting with `.` are absolute.
- No imports: `\l file.q` / `system"l file.q"` executes a file; load order matters.
- Loading a file EXECUTES its top-level statements (hopen, writes, `system`, timers).
- Lambdas are not closures: a nested lambda cannot see its parent's locals.
- Locals are any `name:value` inside a lambda; params are `[a;b]` or implicit `x y z`.
- qsql (`select a,b from t where c>d`) uses bare column names that are NOT globals.
- Lambda parameter/local names shadow globals; many stray "references" are just locals or columns.
- Chained assignment `a:b:{...}` defines both names.
- `::` inside a lambda assigns a global (`svc::1`); `.ns.x:v` too; `x,:v`, `x[i]:v` amend a global.
- Definitions whose right-hand side is not a lambda literal (`f:$[c;g;h]`) are real but cannot be
  checked statically; label such edges differently (`indirect`), do not count them as misses.
- Typed-null/inf literals (`0nf`, `0wu`, `0Nj`) look like identifiers to naive scanners.
- `.z.s` is "the running lambda"; `.z.m`/`.z.M` are per-module namespaces, unresolvable statically.
- ID collisions: lowercasing ids merged `l` and `L`, `.z.w` and `.z.W`. Node ids must be case-sensitive.
- Stray text can break any grammar-based parser (one odd literal made an ERROR swallow 400 lines);
  statements must be parsed independently so one bad statement loses only itself.
- Many real files do not load in isolation (missing libraries, network, data); ~40% loaded on public code.
  Files that do not load must still produce static results, with lower confidence.
- Some `.q` files in the wild are not q at all (query logs, 12 MB fuzz data); content-check before parsing.

## 3. Core idea: q is the parser

The q interpreter ships `parse` and `value`. Both are **inert** for static analysis:
- `parse "<one statement>"` returns the parse tree and executes nothing.
- A lambda inside that tree is an unevaluated lambda object. `value lam` is also inert and returns, in
  order: bytecode, parameter symbols, local symbols, a symbol list of **free names the body references**
  (global reads/calls/writes, with a leading empty symbol), constants..., and the source string.

Verified on kdb+ (q 4.x) on macOS, input `f:{[a;b] c:a+g b; c*.ns.h x}`:
- `parse` -> `(:;`f;lambda)`; `value lambda` -> params ``a`b``, locals `` ,`c ``, free names ``` ``g`x`.ns.h` ```
  (note `x` is a free global because the explicit params are `a`b).
- `parse` of a lambda body (braces and `[params]` stripped) gives the application tree:
  `(*;`c;(`.ns.h;`x))`, i.e. a call is a list whose head is a symbol; `(:;`c;...)` is assignment.
- qsql: `value` of `{select a,b from t where c>d, e=x}` lists free names `` `t`` and `` `x`` only. Column
  names (`a b c d e`) are NOT free globals. This is exactly the column-vs-global distinction.
- Nested lambda: the outer `value` lists only the outer's own free names; the inner lambda is a constant
  and has its own `value` (no parent locals visible).
- `.a.b:1`, `c::2`, `d,:3`, `e[1]:4` inside a lambda all appear in the free-name list (they are global writes);
  the parse tree of the body tells read vs write vs call.
- `parse "a:1;b:2"` returns a `;`-headed list of statements.
- `parse` on a malformed statement raises; wrap in `@[parse;s;handler]` and record a diagnostic.

NOT yet verified (check first, in a short spike, before building on it): behaviour of `parse` on
`\d .ns`, `\l`, `system"..."` lines; dotted-name assignment trees; adverb forms (`g each x` appears as a
call of an adverb-derived verb); how `value` reports names inside qsql constants for nested/functional
forms; whether very large files or odd bytes can crash the q process (it must be treated as crashable).

Consequence: lambda-body scope analysis (params, locals, free globals, qsql columns) comes from q's compiler,
not from our code. Our code only: splits files into statements, tracks the namespace, builds nodes/edges,
resolves names to nodes, assigns confidence.

## 4. Pipeline

1. **Discover**: recurse the root, `*.q` (and `*.k` ignored), skip `.git`, `.venv`, `graphify-out`, output dir;
   skip files > 1 MB; `looks_like_q` content check (reject binary, logs, mostly non-q lines).
2. **Split** each file into top-level statements the way q's loader does: a line starting in column 0 begins a
   statement, indented lines continue it; a line `/` alone starts a block comment, a line `\` alone ends it
   (a lone `\` outside a block ends the script); `/ comment` lines and trailing ` /` comments are stripped;
   keep line numbers. Pure Python, no q needed.
3. **Static pass (tier S)**: one sandboxed q process per workspace chunk reads the statements, `parse`s each
   (protected), emits a JSON tree; per lambda also emits `value`-derived params/locals/free-names and a
   role (call/read/write) per free name taken from the body tree. Python then:
   - tracks the namespace (`\d`, `system"d ..."`) and qualifies definitions and references,
   - records definitions (symbol lhs of `:`/`::`, chained assignments, `.ns.x:` forms, lambda vs non-lambda rhs),
   - records imports (`\l`, `system"l"`), resolving paths against: workspace root, the file's directory,
     the enclosing repo root (nearest `.git`),
   - resolves each reference to a defined node (same namespace rules q uses: no fallback from `.ns` to root,
     builtins and `.q.*`/`.Q.*`/`.j.*`/`.h.*`/`.z.*` are builtin namespaces, not dangling),
   - emits dangling references into an `enrichment_queue` (never silently dropped).
4. **Dynamic pass (tier D, opt-in `--execute`)**: load files in dependency order inside the sandbox, in ONE
   isolated q process per file (transitive deps preloaded, only the target's diff attributed), with a
   timeout; record which names exist afterwards, their types, and `value` of live functions. Confirms
   definitions (tier D2) and reference edges (tier D3) and detects environmental load failures.
5. **Merge**: combine static and dynamic evidence into final tiers and scores (section 5).
6. **Emit** `graph.json` (+ `report.json` with counts, diagnostics, load results, enrichment queue).

## 5. Tiers and confidence scores

| Tier | Meaning | Default score |
|---|---|---|
| D3 | reference edge confirmed by live q (`value` of the loaded function) | 0.98 |
| D2 | definition confirmed to exist after loading | 0.97 |
| S  | established by q's `parse`/`value` statically, name resolved to a defined node | 0.92 |
| S-indirect | def whose rhs is not a lambda literal (`f:$[c;g;h]`) or reference through it | 0.80 |
| S-unresolved | name did not resolve to any defined node | 0.35 (AMBIGUOUS) + enrichment_queue |
| S-refuted | live q disagrees with the static claim | edge kept with score 0.1, evidence says why |

Scores are defaults; they live in `calibration.json` and are re-fit from measurement (section 8), never
hand-tuned on held-out data. Rules: a static edge from a file that failed to load is capped at INFERRED (<0.9)
only if the evidence for it relies on runtime state (non-literal rhs, dynamic `value`/`set`/`eval`); a plain
static edge between two statically defined names may be EXTRACTED because q's compiler produced it.
Every node/edge has `tier`, `confidence`, `confidence_score`, `evidence`.

Nodes: `file`, `function` (lambda defs), `variable` (non-lambda defs), `table` (symbol `uses`d via
`select/exec/update/delete ... from`), `external` (referenced but undefined). Edges: `contains` (file ->
def), `calls`, `reads`, `writes`, `uses` (qsql from-table), `imports`.
Node id = `sha1`-suffixed, case-sensitive slug of (file path, qualified name); never lowercase.

## 6. Sandbox (required for anything that executes q)

The static pass also runs inside the sandbox (a crashing or hostile `parse` input must not hurt the host).
- macOS: `sandbox-exec` profile: deny network, deny file writes except a temp dir, deny process exec except
  the q binary, deny reads under `$HOME` except the q install, the target root and `reflect/analyse` scripts.
- Linux: `docker run --rm --init --network none --read-only --cap-drop ALL --security-opt no-new-privileges
  --pids-limit 256 --memory 2g --cpus 1 --user <uid>:<gid> --tmpfs /tmp`, mounting the workspace, the q
  install and licence READ-ONLY at their host paths and one writable temp bind for the result file; named
  container, `docker rm -f` on timeout (killing the CLI does not stop the container). Image is configurable
  (`QV_IMAGE`-style env var), must be a glibc image already present.
- Backend: env var selects `sandbox-exec` | `docker`; default by platform.
- q binary from `$Q` or `~/.kx/bin/q`; licence via `$QHOME`/`$QLIC`. q on this Mac is 4.x at `~/.kx/bin/q`.
- Per-file timeout (default 30s); a hang, crash or `exit` in one file must not lose others.
- Residual risk to document: a native `.so` in the repo would run inside the sandbox; execution of third-party
  code stays opt-in.

## 7. Interfaces

CLI (`qlens`, Python >= 3.13, installed via uv):
- `qlens build <root> --out <dir> [--execute] [--backend docker|sandbox-exec]` -> `graph.json`, `report.json`
- `qlens eval <root> <truth.json>` -> precision/recall of the graph against a hand-made truth file
- `qlens measure <root>` -> one JSON line of static-vs-dynamic agreement counts for a repo (needs --execute)
- `qlens corpus <corpora_dir> --split dev|test|all --jobs N --timeout S --out results.jsonl` -> resumable,
  one subprocess per repo, results appended as each completes
- `qlens calibrate` -> refit `calibration.json` from measurement results

`graph.json`: `{"nodes":[{id,label,kind,file,line,tier,confidence,confidence_score,evidence}],
"edges":[{source,target,relation,tier,confidence,confidence_score,evidence,file,line}],
"enrichment_queue":[{from,name,reason,file,line}],"meta":{...}}`.

Also provide a Python API `qlens.analyse(root, execute=False) -> dict` (same shape).

## 8. Measurement and evidence (how we know it works)

1. **Trap corpus** (in repo, hand-written, ~6 files + `truth.json`): one file per q gotcha in section 2
   (shadowing, qsql columns, namespaces, chained assignment, `::` in lambda, typed nulls, non-literal rhs,
   a deliberately unparseable statement followed by good ones, case-only name differences). Truth is
   hand-labelled; all edges asserted.
2. **Public corpus**: ~250 public GitHub q repos fetched by a script into a gitignored `corpora/` with a
   committed `MANIFEST.json` (repo, commit, number of real q files). Split dev/test by sha1 of the repo dir name
   (stable). Content-check every file so non-q repos drop out. Third-party code is never executed outside
   the sandbox, and the owner launches the corpus runs.
3. **Truth for reference edges** = what live q reports for the loaded function; for definitions = the
   names that exist after load. Metrics: `agree` (static edge confirmed), `refuted` (static edge q denies),
   `missed` (q has it, static pass lacks it), `indirect`, `dangling`. Precision = agree/(agree+refuted),
   recall = agree/(agree+missed). Files that fail to load are not judged.
4. Workflow: error-analyse dev results by cause, fix generally, re-run dev into a NEW results file (never mix
   code versions), record each run in `docs/RESULTS.md`. Run `test` ONCE at the end. Report outliers
   (one repo can dominate recall: an Advent-of-Code repo held 77% of misses on the earlier test split).
5. Tests: pytest, a trap-corpus end-to-end test, unit tests for splitter, namespace tracking, resolver,
   sandbox command construction (flags asserted), scoring.

## 9. Milestones (build in this order, commit after each, tests green)

- M0 Spike: confirm the "NOT yet verified" list in section 3 against real q; write results into
  `docs/Q_FACTS.md`. Decide static-pass wire format.
- M1 Splitter + discovery + content check + tests.
- M2 Sandboxed q static pass (tree + lambda facts as JSON) + Python graph builder (defs, namespaces,
  refs, resolution, imports) + `graph.json` at tier S. Trap corpus passes at tier S.
- M3 Scoring/calibration file, labels, `enrichment_queue`, `report.json`.
- M4 Dynamic pass (isolation per file, dependency order, timeouts), merge, refuted/missed, `indirect`.
- M5 Docker + sandbox-exec backends; command-construction tests; a real run on the owner's Linux server.
- M6 Corpus fetcher, `corpus`/`measure`/`calibrate`, dev iterations, one test run, `docs/RESULTS.md`.
- M7 Multi-repo workspace behaviour verified (repo-root-relative `\l`, unique ids across repos).
- M8 (later) feed `enrichment_queue` to an LLM step as INFERRED edges below dynamic tiers; stub
  environmental load failures to raise the loaded rate; resolve `.z.m` module state.

## 10. Environment facts

- Dev machine: macOS arm64, zsh, uv available, q 4.x at `~/.kx/bin/q` with licence `~/.kx/kc.lic`.
- Target: an enterprise Linux server with Docker, a multi-repo q workspace. Run T0-style/static first, then
  `--execute` on one small repo, then the workspace. A second Claude session runs there; keep README
  instructions exact.
- Scratch/temp files: use the session scratchpad directory, not `/tmp`.

## 11. Open decisions (owner may answer; otherwise take the default)

- Package name `qlens` (default). Repo location `/Users/arvindiyer/qlens`; private GitHub remote created only on request.
- Static-pass wire format: q emits JSON via `.j.j` of a tagged tree (default) vs a custom text format.
- Whether to add an optional graphify-compatible export (default: yes, small adapter, no dependency).
