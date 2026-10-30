/ qlens dynamic pass: load deps then ONE target file in this isolated process, report what it defined.
/ usage: q dynamic.q -target /abs/f.q -deps /abs/a.q,/abs/b.q -ns .gw,.a.b -out result.json -q
/ Runs only inside the sandbox. Third-party code executes here.

.dy.skipns:`q`Q`h`j`o`z`s`m;
.dy.sig:{[v] $[100h=type v;string v;(string type v),"/",string count v]}
.dy.qn:{[ns;n] $[ns=`.;n;`$string[ns],".",string n]}
.dy.snap:{[nss]
 out:()!();
 {[nss;ns] 
  / key lists every name; `system "v"` omits variables whose value is :: (generic null)
  nm:distinct @[key;ns;()];
  nm:nm where not null nm;
  {[ns;n] q:.dy.qn[ns;n]; `.dy.cur set .dy.cur,enlist[q]!enlist .dy.sig @[get;q;()]}[ns] each nm
 }[nss] each nss;
 .dy.cur}
.dy.cur:()!();
.dy.allns:{[extra]
 vars:(@[system;"v .";()]),@[system;"f .";()];
 distinct `.,(extra,((key `) except .dy.skipns) except vars) except `}
.dy.nsfix:{[x] $[(first string x)="."; x; `$".",string x]}

/ free names of a lambda and of every lambda nested inside it (value of the outer omits the inner ones)
.dy.allfree:{[v]
 r:@[value;v;()];
 if[not (0h=type r)&4<=count r; :()];
 own:(1_r 3) except `;
 cs:4_ -1_ r;
 / only lambdas written in the user's code: q's own keywords (trim, xkey, ...) are k lambdas ("k){...}") with their own free names
 cs:cs where {$[100h=type x;not (string x) like "k)*";0b]} each cs;
 inner:raze .z.s each cs;
 distinct own,inner}

.dy.info:{[q]
 v:@[get;q;()];
 ty:type v;
 d:`name`type!(string q;ty);
 if[100h=ty;
  r:@[value;v;()];
  if[(0h=type r)&4<=count r; d,:`params`locals`free`ctx`free_all!(string each r 1;string each r 2;string each (1_r 3) except `;string first r 3;string each .dy.allfree v)]];
 d}

.dy.done:0b;
.dy.write:{
 if[.dy.done; :()];
 .dy.done::1b;
 a:.dy.res; 
 after:.dy.snap[.dy.nss];
 chg:where not (key after) in key .dy.before;
 chg:chg,where {[b;a;k] (k in key b)&not (b k)~a k}[.dy.before;after] each key after;
 chg:distinct chg; names:(key after) chg;
 a,:enlist[`defs]!enlist .dy.info each names;
 a,:enlist[`namespaces]!enlist string .dy.nss;
 (hsym `$.dy.out) 0: enlist .j.j a;}

.dy.main:{
 o:.Q.opt .z.x;
 .dy.out::first o`out;
 .dy.nss::.dy.allns .dy.nsfix each `$$[count first o`ns;"," vs first o`ns;()];
 deps:$[count first o`deps; "," vs first o`deps; ()];
 .z.exit:{.dy.write[]};
 errs:{[p] e:@[{system "l ",x;""};p;{x}]; $[count e;enlist `file`error!(p;e);()]} each deps;
 .dy.before::.dy.snap[.dy.nss];
 e:@[{system "l ",x;""};first o`target;{x}];
 .dy.res::`loaded`error`dep_errors!(0=count e;e;raze errs);
 .dy.write[];
 exit 0}

.dy.main[];
