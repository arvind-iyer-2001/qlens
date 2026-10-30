/ qsql column names are not globals
trades:([] sym:`a`b; px:1 2)
px:99
colsel:{select sym,px from trades where px>5}
glob:{[lim] select from trades where px>lim}
fromfn:{select from lookup[]}
lookup:{trades}
