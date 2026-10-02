group player
# --- wp00 weapon pieces (37F790..3803A0) ---
dst 37F7C2 ("slowmo",0x37F7AE) | wp00 (37F790): xmm7 = the slow-motion factor (23AD90), the function's dt; its only live readers multiply it by +E28 (= 10) and pass that result to 2DA410, the forward step each tick
dst 37F9EB ("slowmo",0x37F9E1) | wp00 (37F9C0): xmm7 = the slow-motion factor, the function's dt; its only live readers scale the +E10 direction vector before 2DA3F0 moves the piece and subtract dt from the lifetime +E28
dst 37FFF0 ("slowmo",0x37FFE4) | wp00 (37FFC0): xmm6 = the slow-motion factor, the function's dt; its only live reader is +10FC -= dt, the 20-unit sound countdown
lin 3800B1 | wp00 (37FFC0, sub-state 3): the hit radius +E18 grows by 3 a tick, from 3 to 53, before it is passed to 2DC7B0: s of the step
lin 3800E5 | wp00 (37FFC0, sub-state 4): the hit radius +E18 shrinks by 6 a tick to 23 before 2DC7B0: s of the step
callscale 38029C (0x2DA410,"xmm1") | wp00 (37FFC0, sub-state 1): forward by +E28 a tick (+E28 is signed +1101 x 5.5): s of it
dst 3803DF ("slowmo",0x3803CB) | wp00 (3803A0): xmm6 = the slow-motion factor, the function's dt; its only live reader is +10FC -= dt, the 20-unit sound countdown
scaledadd 380575 | wp00 (3803A0, sub-state 1): position += the normalized way to Amaterasu x +E28 each tick; +E28 falls from 8 to 3.5 at the already-scaled 0.35 step, so add s of the vector while its value stays stock
# --- wp06 (385C50) ---
dst 385C88 ("slowmo",0x385C7C) | wp06 (385C50): xmm6 = the slow-motion factor, the function's dt; its only live readers add sin(+10F8) x dt to y and advance/wrap +10F8 by 0.3 x dt
pre 385E23 | wp06 (385C50, sub-state 1): position.x += the persistent launch velocity +E10 a tick: s of it while the velocity keeps its stock value
pre 385E3A | wp06 (385C50, sub-state 1): position.y += the persistent launch velocity +E14 a tick: s of it
pre 385E53 | wp06 (385C50, sub-state 1): position.z += the persistent launch velocity +E18 a tick: s of it
callscale 385EF9 (0x2DA410,"xmm1") | wp06 (385C50, sub-state 1): forward by 4 a tick within 60 of Amaterasu, otherwise 6: s of the per-tick step
