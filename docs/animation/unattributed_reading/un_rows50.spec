# 2026-10-02: the four functions whose gate went on 10-01 and cDogLikeHm's
# gate, each now paced by rows on its own fields.
group menu
# 1C8D80 (the HUD's number slide): the +48 step 0..10 shares its store 1C8DC5
# between the inc (state 1, reaching it by a jmp) and the dec (state 0); the
# register-counter proof now takes a jmp to the store and the sibling row's entry.
count 1C8DA6 (0x1C8D9E,0x1C8DC5,(0x1C8D9E,0x1C8DA1,0x1C8DA4,0x1C8DA6),None) | HUD number slide 1C8D80, state 1 (sliding out): +48 += 1 a tick up to 10; the layout's position is (+3C, +38) blended by (+48 / 10)^k each tick, and the layout update 1B54E0 it calls still runs every tick
count 1C8DC3 (0x1C8DBC,0x1C8DC5,(0x1C8DBC,0x1C8DBF,0x1C8DC1,0x1C8DC3),None) | HUD number slide 1C8D80, state 0 (sliding in): +48 -= 1 a tick down to 0
notyetneg 1C8DA1 notyet:1C8DA6 | HUD number slide 1C8D80, state 1: `cmp +48, 10; jge` hides the number on the tick after +48 reaches 10; between stock ticks it reads "below 10" (jge falls through to the skipped inc), so the last position shows a whole stock tick as in stock
group objects
# 4763F0 (a camera mode's update): 4A0900's call of it comes right after
# 481A10 set the transition length +290 = +292 = r13d, which is 0 from 4A0942
# on, so that pass never reaches the count; the count runs from the per-tick
# camera update (4BA500 -> 475C70 -> 4763F0 or 46D5A0's three helpers).
count 476805 (0x4767E9,0x476808,(0x4767E9,0x4767F0,0x4767F3,0x4767F9,0x476800,0x476803,0x476805),None) | Camera 4763F0: the mode transition's count +290 -= 1 a tick from +292 to 0
blendr 47683D | Camera 4763F0: the transition's factor k = min(1, 0.04 + 0.96 (len - count) / len) blends the stored view (+1A0, +190, +1D0 field of view, +380) toward this tick's computed one, x = (1 - k) x + k target, every tick: with the count paced, k is 1 - (1 - k)^(1/N) between stock ticks; xmm7 = 1.0 (476607, callee-saved), so 1 - k follows at 476841
# 33DE40 (cCarryObj, et99: a carried object floating on water): v(+E54) +=
# +-0.03 toward the rest height, x 0.8 past +-0.4, height (+A8)->y += v.
zfirst 33DEF4 | cCarryObj 33DE40 float bob: the velocity's change -0.03 (above the rest height) is this tick's change to +E54: kept on the first tick of each stock period, 0 on the others
zfirst 33DEFE | cCarryObj 33DE40 float bob: the change +0.03 (below the rest height), as 33DEF4
count 33DF2C factor | cCarryObj 33DE40 float bob: the velocity's damping x 0.8 past +-0.4 runs before the move: kept on the first tick of each stock period, skipped on the others (the velocity is unchanged there, so the bound test repeats it otherwise)
src 33DF41 | cCarryObj 33DE40 float bob: height += v a tick; v changes once a stock period, so the height passes through stock's values at every stock tick
# 375FF0 (vtca state 1): +E36 counts down the state, +1070 counts up and
# plays a sound at some of its values; at +E36 = 0 the next pass restarts
# the motion and goes to state 0. The caller 375AA0 discards rax.
notyet 375FFA notyet:3760BA | vtca 375FF0: `cmp +E36, 0; jne`: between stock ticks the state's end (motion restart, state 0) waits, so it comes on a stock tick as in stock
callgate 376136 (0x44E470,"void") | vtca 375FF0: the sound 44E470 at the +1070 values it plays on: with +1070 held between stock ticks, the call runs on stock ticks only, once per value
count 37613B | vtca 375FF0: the state's countdown +E36 -= 1 a tick
count 376141 | vtca 375FF0: the phase +1070 += 1 a tick (its sounds at fixed values)
group actor
# 4873A0 (cDogLikeHm): its gatefn also ran the root motion (2DA3D0 applies the
# motion advance's +EC0, already a tick's share) and, in sub-states 0..3,
# 4B9B70's motion advance once a stock tick (4x slow); its quantities instead:
pre 4875AB | cDogLikeHm 4873A0, +1230 = 0: heading +B4 += the spin +1204 a tick (xmm0 holds the spin, copied at 4875A8)
countlast 4875B8 | cDogLikeHm 4873A0: the spin +1204 /= 1.5 a tick after it turns the heading: on the last tick of each stock period only, so the heading gains the stock spin over each period
lin 4874B6 | cDogLikeHm 4873A0, +1230 = 1: heading +B4 steps 0.1 a tick toward +1234 (wrapped) and snaps to it within 0.1; xmm6 is both the step and the snap's bound
count 4875FB | cDogLikeHm 4873A0: +E36 += 1 a tick, two sounds at 18 and 36, back to 0 at 37: the store is skipped between stock ticks (the wrap test reads the stored byte)
callgate 48762A (0x44E3C0,"void") | cDogLikeHm 4873A0: the sound at +E36 = 18 or 36: al holds the unstored count between stock ticks, so the call runs on stock ticks only
