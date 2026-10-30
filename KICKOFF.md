You are starting a FULLY GREENFIELD project in /Users/arvindiyer/qlens (git repo already initialised, nothing pushed).

1. Read SPEC.md completely before doing anything. It is the single source of truth.
2. Do not use, read for implementation, or depend on any earlier project (q-tree-sitter, tree-sitter-q,
   better-q-graphify, qverify, graphify). No tree-sitter. q itself is the parser (SPEC section 3).
3. Rules: uv only; no commit trailers; no remote/push until Arvind says so; third-party q code only runs in
   the sandbox and only with --execute; quote errors verbatim; never claim unmeasured results.
4. Start with milestone M0 (the spike): verify the "NOT yet verified" list in SPEC section 3 against the real q
   at ~/.kx/bin/q, write findings to docs/Q_FACTS.md, commit. Then stop and report to Arvind before M1.
5. After each milestone: tests green, commit, short report (what was done, what is unverified).
