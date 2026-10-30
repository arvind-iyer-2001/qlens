/ qlens static pass: parse each statement with q itself (inert), emit a tagged tree as JSON lines.
/ usage: q static.q -in statements.json -out result.jsonl -q
/ input : JSON array of {"i":<int>,"t":"<statement text>"}
/ output: line 1 {"kind":"meta",...}; then one line per statement {"i","ok","tree","free"|"err"}

.ql.trunc:{[s] $[200<count s;200#s;s]}
.ql.s1:{.ql.trunc .Q.s1 x}

/ body of a lambda source "{[a;b] ...}" with braces and parameter list removed
.ql.body:{[s]
 b:trim 1_-1_s;
 if[(0<count b)&"["=first b; b:trim (1+b?"]")_b];
 b}

.ql.lam:{[t]
 s:string t;
 if[(s like "k)*")|s like "(k)*"; :`k`v!(`fn;s)];
 v:@[value;t;0b];
 if[not (0h=type v)&4<=count v; :`k`v!(`fn;s)];
 b:.ql.body s;
 bt:$[0=count b; `k`v!(`fn;"::"); .ql.enc parse b];
 `k`src`params`locals`free`body!(`lam;s;string each v 1;string each v 2;string each (v 3) except `;bt)}

.ql.enc:{[t]
 ty:type t;
 $[ty=100h; .ql.lam t;
   ty=0h; `k`v!(`app;.ql.enc each t);
   ty=-11h; `k`v!(`sym;string t);
   ty=11h; `k`v!(`syms;string each t);
   ty=10h; `k`v!(`str;t);
   ty=-10h; `k`v!(`chr;(),t);
   (ty>100h)&ty<=112h; `k`v!(`fn;.ql.s1 t);
   `k`v!(`lit;.ql.s1 t)]}

/ free global names of a statement, computed by wrapping it as a niladic lambda
.ql.topfree:{[txt] @[{string each ((value parse "{[]",x,"\n}") 3) except `};txt;{()}]}

.ql.one:{[r]
 i:"j"$r`i; t:(),r`t;
 res:@[{(0b;.ql.enc parse x;.ql.topfree x)};t;{(1b;x;())}];
 $[res 0; `i`ok`err!(i;0b;res 1); `i`ok`tree`free!(i;1b;res 1;res 2)]}

.ql.main:{
 a:.Q.opt .z.x;
 stm:.j.k raze read0 hsym `$first a`in;
 h:hopen hsym `$first a`out;
 h (.j.j `kind`qver`builtins!(`meta;.z.K;string key `.q)),"\n";
 {[h;r] h (.j.j .ql.one r),"\n"}[h] each stm;
 hclose h;}

.ql.main[];
exit 0
