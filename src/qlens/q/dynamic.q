/ qlens dynamic pass: load deps then ONE target file in this isolated process, report what it defined.
/ usage: QINIT=dynamic.q QLENS_OUT=result.json QLENS_DEPS=/abs/a.q,/abs/b.q QLENS_NS=.gw,.a.b q <target> -q  (stdin: `.dy.fin[]`)
/ The target is the MAIN script, so .z.f and relative paths behave as when a user runs `q <target>` from the repo root.
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
 / a dictionary variable holds names too: `lin.send:{..}` at the root makes `lin` a dict, and `lin.send` resolves through its keys
 if[99h=ty; k:@[key;v;()]; if[11h=type k; d,:enlist[`keys]!enlist string each 500#k where not null k]];
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
 .dy.out::getenv`QLENS_OUT;
 ns:getenv`QLENS_NS;
 .dy.nss::.dy.allns .dy.nsfix each `$$[count ns;"," vs ns;()];
 d:getenv`QLENS_DEPS;
 deps:$[count d;"," vs d;()];
 / runs if the file calls exit before it finished loading
 .z.exit:{.dy.write[]};
 errs:{[p] e:@[{system "l ",x;""};p;{x}]; $[count e;enlist `file`error!(p;e);()]} each deps;
 .dy.before::.dy.snap[.dy.nss];
 .dy.res::`loaded`error`dep_errors!(0b;"exited before the file finished loading";raze errs)}

/ the driver feeds this line on stdin; q reads it once the target (the main script) has finished or stopped on an error
.dy.fin:{
 .dy.res[`loaded]:1b;
 .dy.res[`error]:"";
 .dy.write[];
 exit 0}

.dy.main[];
