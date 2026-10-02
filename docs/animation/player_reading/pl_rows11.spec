group player
# wp5e/wp5f follow-up
dst 3A1B8E ("slowmo",0x3A1B80) | wp5e (3A1B50): xmm6 = the slow-motion factor, the function's dt; its only live reader multiplies +E28 by dt for the per-tick forward move in sub-state 1
dst 3A1E16 ("slowmo",0x3A1E0A) | wp5e (3A1DF0): xmm7 = the slow-motion factor, the function's dt; its only live reader subtracts dt from the lifetime +1108 in sub-state 1
dst 3A1F11 ("slowmo",0x3A1F05) | wp5e (3A1EF0): xmm6 = the slow-motion factor, the function's dt; its only live reader subtracts 0.03 x dt from +D2C in sub-states 2 and 3
dst 3A2551 ("slowmo",0x3A2545) | wp5f (3A2530): xmm7 = the slow-motion factor, the function's dt; its only live readers subtract dt from +1108, once conditionally and once on every update
callscale 3A25BA (0x2DA410,"xmm1") | wp5f (3A2530): forward by +E48 each tick on the 23B750-true path: s of the per-tick move while +E48 keeps its stock value
callscale 3A25D1 (0x2DA410,"xmm1") | wp5f (3A2530): forward by +E48 each tick on the other path: s of the per-tick move while the already-covered +E48 acceleration stays stock-valued
