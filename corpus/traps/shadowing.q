/ locals and params shadow globals
g:{x*2}
h:{x+1}
shadow:{[g] g+1}
local:{h:3; h*2}
real:{g x}
