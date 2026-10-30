# Q_FACTS (M0 spike)

Measured against `~/.kx/bin/q`, `.z.K`=`5f`, `.z.k`=`2026.05.01`, macOS arm64. NOTE: SPEC says "q 4.x"; this
binary reports version 5. Facts below are for this binary only. All inputs were my own strings (no third-party code).
Method: scripts in the session scratchpad, run as `q file.q -q </dev/null` (never interactive stdin: it hangs).

## Verified: `parse` is inert and covers the "NOT yet verified" list

| Input | `parse` result |
|---|---|
| `\d .ns` | `(.,["\\"];"d .ns")` |
| `\l foo.q` | `(.,["\\"];"l foo.q")` |
| `system"l foo.q"` | identical to `\l foo.q` (cannot tell the two apart; equivalent) |
| `system"d .gw"` | identical to `\d .gw` |
| `\t`, `\ls`, `\cd`, `\\` | same shape: `(.,["\\"];"<rest>")`; `\\` is inert (does not exit) |
| `.ns.x:5` | `(:;`.ns.x;5)` (dotted name is one symbol) |
| `a.b.c:1` | `(:;`a.b.c;1)` |
| `a:b:{x}` | `(:;`a;(:;`b;{x}))` |
| `c::2`, `d,:3` | `(::;`c;2)`, `(,:;`d;3)` |
| `e[1]:4`, `f[x]:{y}` | `(:;(`e;1);4)` (lhs is an application) |
| `f:$[c;g;h]` | `(:;`f;($;`c;`g;`h))` (non-lambda rhs: `$` head) |
| `f:{x}[1]` | `(:;`f;({x};1))` |
| `f:.ns.g` | `(:;`f;`.ns.g)` (alias, rhs is a bare symbol) |
| `g each x` | `((k){x'y};`g;`x)` (each is a k lambda constant, not a symbol head) |
| `f'[a;b]`, `f/[0;x]`, `x f/ y` | `((';`f);`a;`b)`, `((/;`f);0;`x)`, `((/;`f);`x;`y)` |
| `` `a set 1`` | k-lambda constant applied to `` ,`a`` and `1` (name is a 1-elem sym list) |
| `if[1;a:2]` | `(`if;1;(:;`a;2))` (`if`/`do`/`while` appear as symbol heads: not calls) |
| `a:1;b:2` | `(";";(:;`a;1);(:;`b;2))` |
| `select a from t where b>c` | `(?;`t;,,(>;`b;`c);0b;(,`a)!,`a)`: columns are symbols, table is arg 1 |
| `update`/`delete`/`exec` | `!` / `!` / `?` heads, table symbol is arg 1 |
| `select from .ns.t` | `(?;`.ns.t;();0b;())` |
| `0nf+1`, `x:0wu`, `a:0Nj` | typed nulls/infs are literals (`0n`, `0Wu`, `0N`), not symbols |
| `x:neg y` | `(:;`x;(-:;`y))` |
| `/ comment`, empty string | `::` |
| `a:1 / c` | trailing comment stripped by q: `(:;`a;1)` |

Multi-line statements parse when given with embedded newlines (indent continuation), e.g. `"f:{\n c:1;\n c+g x\n }"`.
Lambda constants keep their original source text (including newlines) as a char list.

## Verified: `value` on lambdas

`value lam` -> `(bytecode; params; locals; free-names; constants...; source)`. Index 1 params, 2 locals, 3 free names
(leading empty symbol, then names). Observed details:

- Free names list global reads, calls AND writes (`.a.b:1`, `c::2`, `d,:3`, `e[1]:4`, `t[`a]:1` all list the target).
  Read vs call vs write must come from the body tree. A name read and written (`{f x; f::1}`) appears ONCE.
- Free-name ORDER is not source order (`{g'[a;b]}` -> `` `b`a`g``). Treat as a set.
- qsql: columns are NOT free; only the table and non-column names appear. `{select a,b from t where c>d,e=x}` -> free `t`
  only (`x` is the implicit param). Functional form `?[t;enlist(>;`c;d);...]` -> free `d`,`t` (`c` is a symbol constant).
- Implicit params: lambda with no `[..]` gets `x`, plus `y`/`z` if used. `{y:1;x+y}` -> params `x y`, locals empty
  (assigning to `y` assigns the param, not a local). `{[x] x+y}` -> `y` is a free global.
- Nested lambda: outer `value` omits inner free names entirely; inner is a constant needing its own `value`.
  Inner `{a+z}` -> params `x y z`, free `a` (parent `a` NOT visible: non-closure confirmed).
- `.z.s` is NOT listed in free names; `.z.w` IS listed.
- Dynamic forms are invisible to `value`: `{value "g 1"}`, `{system"l foo.q"}`, `` {`a set 1} `` list no free names.
- Max 8 explicit params: 9 params raises `'params`.

## FINDING (affects design): unary minus on a name is a PARSE ERROR in this build

`parse "-x"`, `"a:-x"`, `"x:-y"`, `"(-abc)"`, `"f:{-x}"` all raise `'-`; `parse "- x"` raises `' `. Even
`value "-abc"` (abc defined) raises `'-`. `neg x` works; `-1`, `a:-1+x`, `1-abc`, `b-c`, `a b -c` (dyadic) work.
Real q code uses `-x` a lot, so a whole statement containing it would be lost, and a lambda containing it is
unparseable. Unverified: whether this is specific to this q 5 build (SPEC assumed 4.x) or a licence/mode artefact.
Open question for Arvind: is a q 4.x binary available? Mitigation option: per-statement fallback rewriting `-name`
-> `neg name` outside strings (risky; only with a lower-confidence tier).

## Crash/robustness probes (own strings only, each in its own process)

No process crash or hang observed for: 5000-deep parens (raises `'(`), 20 MB string literal, 100k-statement lambda
body, 200k `;`-joined statements (0.1 s), nul byte / invalid UTF-8 (raise `'type`, protected), 2000-nested braces.
Two probes were broken by my own test code (a `-3#` on a non-list), so 100k-deep parens and 2000-nested braces are
UNMEASURED. Still treat q as crashable: one process per chunk, timeout, re-run remaining chunks after a crash.
Errors from `parse` are catchable with `@[parse;s;handler]`; the message is only the error symbol text (`'-`, `'type`).
Observed: `'{` for `a:{`, `'(` for `((`, `'type` for a whitespace-only string
(whitespace-only must be skipped by the splitter).

## Static-pass wire format decision

`.j.j` directly is lossy: symbols and strings both become JSON strings and a lambda becomes only its source text, so
`value`-derived facts would be lost. Spike of a tagged walker in q (`k`=`app|sym|syms|str|lam|fn|lit`, lambda node carries
`src`, `params`, `locals`, `free`) emitted valid JSON for `f:{[a;b] c:a+g b; select x from t where y>a}`:
`{"k":"lam","src":"...","params":["a","b"],"locals":["c"],"free":["","g","t",""]}`. Decision: use this tagged tree
(q emits JSON via `.j.j` of its own tagged structure). Gaps to fix in M2: the `:`/`;` heads show up as `lit` (type 102h is
below the 104h check; need a proper "primitive" tag), single-element `` ,`a`` vs atom `` `a`` must stay distinct
(`syms` vs `sym`), and nested lambdas inside the tree need their own `value` (the walker already recurses).
