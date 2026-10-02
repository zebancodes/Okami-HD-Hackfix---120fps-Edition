group player
# wp51, wp55, wp5a, wp5e
lin 39E872 | wp51 (39E790): the caller passes a 4-degree steering limit to 39F770 every tick; the helper multiplies it by slow-motion dt, so pass s of the limit while leaving the helper stock for its one-shot caller
lin 39EE6F | wp51 (39EE30): the caller passes a 4-degree steering limit to 39F770 every tick; the helper multiplies it by slow-motion dt, so pass s of the limit while leaving the helper stock for its one-shot caller
dst 39EAFC ("slowmo",0x39EAE6) | wp51 (39EAC0): xmm6 = the slow-motion factor, the function's dt; its only live readers subtract dt from +10F0 in sub-states 3 and 1, after which xmm6 is overwritten
dst 39EE66 ("slowmo",0x39EE5C) | wp51 (39EE30): xmm6 = the slow-motion factor, the function's dt; every live reader is a per-tick step: +10F0 -= dt, +E18 -= 0.75 x dt, movement by +E10 x dt, +E28 -= dt, and the later +10F0 -= dt
lin 39F2F2 | wp51 (39F2B0): the +C0/+C4/+C8 vector grows by 0.05 a tick through cVec::operator+= before each component is clamped to 1.5: s of the step
dst 39F2E8 ("slowmo",0x39F2DE) | wp51 (39F2B0): xmm8 = the slow-motion factor, the function's dt; every live reader is a per-tick step: the two +10F0 countdowns, forward movement by 6 x dt, and +E18 += 0.3 x dt
pre 3A0352 | wp55 (3A0160, sub-state 1): position.x += the persistent launch velocity +E10 each tick: s of the move while the velocity keeps its stock value
pre 3A0373 | wp55 (3A0160, sub-state 1): position.y += the persistent launch velocity +E14 each tick: s of the move
pre 3A038C | wp55 (3A0160, sub-state 1): position.z += the persistent launch velocity +E18 each tick: s of the move
dst 3A100B ("slowmo",0x3A0FFF) | wp5a (3A0FE0): xmm6 = the slow-motion factor, the function's dt; its only live reader subtracts dt from the +10F0 sound countdown
lin 3A10D0 | wp5a (3A0FE0, sub-state 3): the hit radius +E18 grows by 3 a tick, from 3 to 53, before it is passed to 2DC7B0: s of the step
lin 3A1104 | wp5a (3A0FE0, sub-state 4): the hit radius +E18 shrinks by 6 a tick to 23 before it is passed to 2DC7B0: s of the step
callscale 3A123A (0x2DA410,"xmm1") | wp5a (3A0FE0, sub-state 1): forward by +E28 each tick: s of the per-tick step
dst 3A1A51 ("slowmo",0x3A1A45) | wp5e (3A1A30): xmm6 = the slow-motion factor, the function's dt; its only live reader subtracts 0.03 x dt from +D2C in sub-states 0 and 1
