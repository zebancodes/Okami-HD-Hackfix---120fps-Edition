# 2026-10-02: rows from reading the near sites.
group actor
# The animals' launch and knockback slides: each update adds the velocity
# +E10/+E18 (set once at the action's start: a direction x a speed) to the
# position every tick, then decays it by 0.97 or 0.95, which decay_factors.h
# roots. The adds were left at a stock tick's displacement, so at 120 a slide
# went about four times as far. As 205310's (a875edd1): the add scaled by s.
src 1D5937 | an00 1D57B0 launch slide: position.x += +E10 a tick (the velocity's decay is decay_factors.h's, 1D596C)
pre 1D5952 | an00 1D57B0 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1D5943)
pre 1D8C54 | an01 1D8B20 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at 1D8C4C)
src 1D8C68 | an01 1D8B20 launch slide: position.z += +E18 a tick
src 1DD1CE | an04 1DD060 slide (while +F48 <= 20): position.x += +E10 a tick
pre 1DD1E9 | an04 1DD060 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1DD1DA)
pre 1E0884 | an06/an08 1E0750 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at 1E087C)
src 1E0898 | an06/an08 1E0750 launch slide: position.z += +E18 a tick
src 1E36A5 | an07 1E3550 slide (while +F48 <= 20): position.x += +E10 a tick
pre 1E36C0 | an07 1E3550 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1E36B1)
pre 1E6E88 | an09 1E6D20 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at 1E6E79)
pre 1E6E9F | an09 1E6D20 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1E6E90)
src 1E9C87 | an0b 1E9B00 launch slide: position.x += +E10 a tick
pre 1E9CA2 | an0b 1E9B00 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1E9C93)
src 1ED0EE | an0c 1ECF50 launch slide: position.x += +E10 a tick
pre 1ED109 | an0c 1ECF50 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1ED0FA)
src 1EF942 | an0d/an0e 1EF700 launch slide: position.x += +E10 a tick
pre 1EF962 | an0d/an0e 1EF700 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1EF953)
src 1F09E7 | an05/an18 1F07A0 launch slide: position.x += +E10 a tick
pre 1F0A07 | an05/an18 1F07A0 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1F09F8)
pre 1F4770 | an19 1F4610 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at 1F4761)
pre 1F4787 | an19 1F4610 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1F4778)
src 1F73EA | an1a 1F7290 slide (while +F48 <= 20): position.x += +E10 a tick
src 1F7402 | an1a 1F7290 slide: position.z += +E18 a tick
src 1FA4A5 | an1b 1FA390 slide: position.x += +E10 a tick (its decay 0.95, decay_factors.h)
pre 1FA4C0 | an1b 1FA390 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1FA4B1)
src 1FDE05 | an1f 1FDCF0 slide: position.x += +E10 a tick (its decay 0.95, decay_factors.h)
pre 1FDE20 | an1f 1FDCF0 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1FDE11)
pre 1FE3F4 | an02/an20 1FE2C0 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at 1FE3EC)
src 1FE408 | an02/an20 1FE2C0 launch slide: position.z += +E18 a tick
# 202DC0 (the knockback 202C40 sets up, for an09, an19 and 1FAB80's): a
# forward step by the speed +E48 (decaying 0.97) and the slide +E10/+E18.
callscale 202DEB | knockback 202DC0: the forward step 2DA410 by the speed +E48 a tick (xmm1); +E48's 0.97 decay is decay_factors.h's (202DF8)
src 202E13 | knockback 202DC0: position.x += +E10 a tick
pre 202E2E | knockback 202DC0: position.z += +E18 a tick (xmm0 holds +E18, loaded at 202E1F)
# 206000 (cAnimal, 26 classes): as 205310's slide: on the ground (+D40 bit 3)
# v x 0.4 a tick, in the air v; the paths join at 2062AB with xmm0 = z's step.
lin 206279 | cAnimal 206000 slide on the ground: x += +E10 x 0.4 a tick
lin 206291 | cAnimal 206000 slide on the ground: z += +E18 x 0.4 a tick
pre 20629B | cAnimal 206000 slide in the air: x += +E10 a tick (xmm0 holds +E10, loaded at 20626F; entered only from 206277's je)
dst 2062A3 | cAnimal 206000 slide in the air: +E18, z's step, scaled right after its load; the ground path joins after it at 2062AB with its own 0.4 x s
src 48573D | cDogLikeHm 485390: position.x += +E10 a tick while it turns toward its point (the velocity's 0.97 decay is decay_factors.h's)
pre 485758 | cDogLikeHm 485390: position.z += +E18 a tick (xmm0 holds +E18, loaded at 485749)
# an01 1D9100 case 5: walking toward a point, +1170 counts down a random 0..31
# ticks; at 0 it reloads and +E3C (the reloads) steps, past 4 state 6.
count 1D932E | an01 1D9100 case 5: the countdown +1170 -= 1 a tick while far from its point: the store is skipped between stock ticks
notyet 1D9334 notyet:1D940E | an01 1D9100 case 5: `test ecx, ecx; jne` on the countdown's old value: between stock ticks it reads "not yet", so the reload and the +E3C step come on a stock tick
group objects
# cBallObj 33C290 state 2 (cBallObj, et9a, ut96: a ball rolled away): the
# position += +E20/+E28 a tick, which decays 0.985 (decay_factors.h), and the
# model turns by |v| x 2 pi / K a tick about the rolling axis.
pre 33C336 | cBallObj 33C290 roll: position.x += +E20 a tick (xmm0 holds +E20, loaded at 33C31D)
pre 33C34D | cBallObj 33C290 roll: position.z += +E28 a tick (xmm0 holds +E28, loaded at 33C33E)
lin 33C3B8 | cBallObj 33C290 roll: the model's turn this tick, |v| x 2 pi / K (4BD280's angle), multiplied into its matrix
# objScroll's falls (35C790, 35CC30, 35D0E0, from 35C490): y += vy a tick, then
# vy = (vy - 0.4) x 0.97 or 0.98: the gravity is phase_steps.h's, the drag
# decay_factors.h's, so vy stays in a stock tick's units and the add needs s.
pre 35C8CF | objScroll 35C790 fall: position.y += +E10 a tick (xmm0 holds +E10, loaded at 35C8C0)
src 35D001 | objScroll 35CC30 fall: position.y += +E24 a tick
src 35D21A | objScroll 35D0E0 fall: position.y += +E20 a tick
src 35D456 | objScroll 35D0E0 fall: position.y += +E24 a tick
# wp20 model 0x624 (393210, the reflector's second model) and utbd 22E430:
# two dangling parts on springs: spin -= joint x 0.05 (xmm8), joint += spin,
# spin x 0.9 (decay_factors.h). The pull changes the spin once a stock period
# (zfirst), the joint moves by s of it every tick.
zfirst 3934FC | wp20 0x624 part 1: the spring's pull on the spin +1C68, joint x 0.05: kept on the first tick of each stock period, 0 on the others
pre 39352F | wp20 0x624 part 1: joint += spin +1C68 a tick (xmm0 holds +1C68, loaded at 39351F)
zfirst 3935A8 | wp20 0x624 part 2: the pull on the spin +1C6C, as 3934FC
pre 3935D9 | wp20 0x624 part 2: joint += spin +1C6C a tick (xmm0 holds +1C6C, loaded at 3935CB)
zfirst 22E704 | utbd 22E430 part 1: the spring's pull on the spin +1104, joint x 0.05: kept on the first tick of each stock period
src 22E737 | utbd 22E430 part 1: joint += spin +1104 a tick
zfirst 22E7B0 | utbd 22E430 part 2: the pull on the spin +1108, as 22E704
src 22E7DE | utbd 22E430 part 2: joint += spin +1108 a tick
src 22E5B8 | utbd 22E430 state 3: the scale +C0 += 0.05 a tick up to 0.7
src 22E5BD | utbd 22E430 state 3: the scale +C8 += 0.05 a tick up to 0.7
count 22E60F | utbd 22E430 state 5: the countdown +E36 -= 1 a tick: the store is skipped between stock ticks
notyet 22E615 notyet:22E673 | utbd 22E430 state 5: `test cl, cl; jne` on the countdown's old value: between stock ticks "not yet", so state 6 starts on a stock tick
pre 38F741 | wp1c 38F400: position.x += +E20 a tick (xmm0 holds +E20, loaded at 38F734); +E20's acceleration is a world row (38F714) and its 0.94 decay decay_factors.h's
pre 38F75B | wp1c 38F400: position.z += +E28 a tick (xmm0 holds +E28, loaded at 38F74C)
group player
# pl00 states 0 and 1 (3B18D0, 3B2620): position += +10A0/+10A8 a tick, then
# x 0.98 (decay_factors.h): a push on Amaterasu that slides her.
pre 3B209E | pl00 state 0 3B18D0: position.x += +10A0 a tick (xmm0 holds +10A0, loaded at 3B2096); its 0.98 decay is decay_factors.h's
pre 3B20B5 | pl00 state 0 3B18D0: position.z += +10A8 a tick (xmm0 holds +10A8, loaded at 3B20A6)
pre 3B297F | pl00 state 1 3B2620: position.x += +10A0 a tick (xmm0 holds +10A0, loaded at 3B2977)
src 3B2993 | pl00 state 1 3B2620: position.z += +10A8 a tick
group actor
# an0b 1EC2C0: +1170 counts down a random 0..31 ticks; at 0 a new wander
# point +1160 (random within 220 of its anchor) and a reload.
count 1EC414 | an0b 1EC2C0: the wander countdown +1170 -= 1 a tick: the store is skipped between stock ticks
notyet 1EC41A notyet:1EC48D | an0b 1EC2C0: `test ecx, ecx; jne` on the countdown's old value: between stock ticks "not yet", so the new point is picked on a stock tick
group objects
pre 20981F | cKiType 2097C0 state 2 (a thrown or knocked object's fall): position.y += +E54 a tick (xmm0 holds +E54, just stored); its gravity 0.6 is phase_steps.h's (209808)
count 214059 (0x21402E,0x21405C,(0x21402E,0x214034,0x214036,0x214059),None) | ut04 213FB0 state 2: the countdown +111C -= 1 a tick (from 10): a skipped tick reads "not finished", as stock between its ticks
group actor
count 20C798 | slot 1 of 780 actor classes (20C620): the fade-in byte +D79 += 25 a tick up to 255: the store is skipped between stock ticks
group objects
# 21E850 / 21EBD0 / 21EF90 (five or six object classes): state 3's wait +13F0
# -= ecx, which is 1 there (`cmp ecx, 1; jne` before), and state 1's -= 1;
# jns: at -1 the state moves on. 21EDCC/21F18C pace the other waits.
count 21E98A down | 21E850 state 3: the wait +13F0 -= 1 a tick (ecx is 1: `cmp ecx, 1; jne` just before); a skipped tick reads "not finished" for the jns
count 21EA1E | 21E850 state 1: the wait +13F0 -= 1 a tick
count 21ED02 down | 21EBD0 state 3: the wait +13F0 -= 1 a tick (edx is 1: `cmp edx, 1; jne` just before)
count 21F0C2 down | 21EF90 state 3: the wait +13F0 -= 1 a tick (ecx is 1: `cmp ecx, 1; jne` just before)
src 22F83E | utcb 22F820: position.y += +1094 a tick, the speed growing by 0.5 a tick to 9.5 (phase_steps.h, 22F86A)
src 22F848 | utcb 22F820: position.y -= +1094 a tick (the other direction)
group actor
count 241296 | em00..em03 update (241180): the slot-8 effect spawner +1136 += 1 a tick, at 2 an effect and 0 (as em05's 25141C)
count 2412E8 | em00..em03 update (241180): +12B6 counts the ticks it spends more than 20 below its target's height
pre 256255 | 255ED0: position.z += +E18 a tick (xmm0 holds +E18, loaded at 256246); x approaches its point through the blend literal 256222
group objects
count 2313BE | utd7 231200: the cooldown +1630 -= 1 a tick while not 0 (at 0 the check 2DC7B0 runs and may reload it): the store is skipped between stock ticks
group actor
lin 25E535 | em12 25E4C0: the orbit radius +1384 += 2 a tick up to 150 + 22 x +1146
group actor
lin 272F5A | em27/em29 272EC0: the orbit radius +1414 -= 4 a tick down to 0 (its growth by 2 is the world literal 272F12)
count 27881C | em2b 278590: +E3E -= 1 a tick while above 0 (at 0 an effect and a reload to 1: one every other tick): the store is skipped between stock ticks
notyet 2787CB notyet:278811 | em2b 278590: `test ax, ax; jg` on +E3E: between stock ticks "above 0", so the effect and its reload come on stock ticks
pre 286B86 | em3d 2865B0: the clock +11C0 += speed (+1080) a tick (xmm0 holds the speed, copied at 286B83)
pre 286BB2 | em3d 2865B0: position.y += sin(+1258) x 0.7 x speed a tick (xmm0 holds that step); the phase +1258's step is the world step row 286BBC
lin 28D254 | em4d/em4e/em50 28D1A0: position.y += 2 a tick while below +E50 + 55 (the rise before its bob)
lin 28D72D | em4d/em4e 28D320: the same rise, y += 2 a tick
lin 2911FA | em50 290EC0: the same rise, y += 2 a tick
src 29D454 | em56 29D3B0: position.y -= 2 x speed (+1080) a tick while above its floor (xmm0 holds 2 x speed)
src 29D4C2 | em56 29D3B0: position.y += speed (+1080) a tick while below its ceiling
count 2A4E49 (0x2A4E2E,0x2A4E4C,(0x2A4E2E,0x2A4E35,0x2A4E38,0x2A4E49),None) | 29F770's state 2A4BA0: the wait +E3C -= 1 a tick while not 0 (at 0 the state ends): skipped between stock ticks
notyet 2A4E35 notyet:2A4E49 | 29F770's state 2A4BA0: `test ax, ax; jne` on +E3C: between stock ticks "not 0", so the state ends on a stock tick
pre 2D49A4 | em6a 2D48E0: the glow +11A4 += |sin(+11A0) x 8| a tick up to 255 (xmm2 holds that step)
# em8f's body (its parts were ffe6c5c8's): the death 2D90E0 (cases 1, 3), the
# hover 2D9460/2D9940 and the return 2D9C00.
scaledadd 2D9192 | em8f 2D90E0 case 3 (dying): position += the velocity +E10..+E18 a tick (cVec::operator+=)
scaledadd 2D92E2 | em8f 2D90E0 case 1: position += the velocity a tick
countlast 2D91B0 | em8f 2D90E0 case 3: the horizontal velocity +E10 x -0.4 a tick (a shake that dies out): on the last tick of each stock period only, so it flips once a stock tick
countlast 2D91C8 | em8f 2D90E0 case 3: +E18 x -0.4, as 2D91B0
countlast 2D9300 | em8f 2D90E0 case 1: +E10 x -0.4, as 2D91B0
countlast 2D9318 | em8f 2D90E0 case 1: +E18 x -0.4, as 2D91B0
lin 2D917B | em8f 2D90E0 case 3: the alpha +D2C -= 0.015 a tick until it is gone
srcblend 2D9666 | em8f 2D9460: y approaches its hover height (sin x 12 + floor + 30) by +1238 a tick, a factor that grows by 0.05 a tick (phase_steps.h)
blend 2D96FC | em8f 2D9460: y approaches sin x 6 + floor + 20 by 0.05 a tick
blend 2D9A6D | em8f 2D9940: y approaches sin x 3 + floor + 20 by 0.05 a tick
srcblend 2D9AC6 | em8f 2D9940: x approaches its target's x by +E20 a tick (+E20 grows by 0.02 a tick, phase_steps.h)
srcblend 2D9AEF | em8f 2D9940: y approaches its target's y + 28 by +E20 a tick
srcblend 2D9B19 | em8f 2D9940: z approaches its target's z by +E20 a tick
blend 2D9B73 | em8f 2D9940: the alpha +D2C approaches 0.3 by 0.2 a tick
blend 2D9B89 | em8f 2D9940: the alpha +D2C approaches 0.6 by 0.1 a tick
blend 2D9CBD | em8f 2D9C00 state 2: the alpha +D2C approaches 1 by 0.2 a tick
blend 2D9CDE | em8f 2D9C00 state 2: y approaches the floor +E50 by 0.1 a tick
group objects
lin 2E2703 | et07 2E25B0: material 1's U += -0.002583 a tick (a .data constant, 7A0060), wrapped into -1..1
count 2E2D60 | et07 2E2BE0 case 1: the fade-in count +E3C -= 1 a tick from 15 (alpha = (15 - it) / 15): the store is skipped between stock ticks
src 2E39FF | et08 2E36F0 case 4: submodel 1 sinks by the .data table's step a tick (7A0084 + 0x1C x +1C7) until it is at 0
count 2E555B | et0f 2E5330: +112C -= 1 a tick from 150 while it closes in; below 0 its speed rises to 9
count 2E6D13 | et12 2E6C80: the wait +1080 -= 1 a tick from 60
notyet 2E6D19 notyet:2E6D28 | et12 2E6C80: `cmp +1080, 0; jg`: between stock ticks "above 0", so the state's step comes on a stock tick
lin 2E84C2 | et24 2E83E0: the phase +1088 += 0.0005 a tick (a .data constant, 7A01C4), wrapped
lin 2EA9B1 | et2e 2EA790: position.y -= 0.5 a tick as it sinks
src 2F2E38 | et6b 2F2970 case 8: the alpha +D2C -= a double constant (6784D0) a tick down to 0 while +1080 counts 30
srcblend 307619 | 307110's 307340: x moves (target - x) / (+E3C + 1) a tick, +E3C paced by action_timers.h: the divisor's blend, so x passes stock's values at its stock ticks and lands when +E3C is 0
srcblend 307642 | 307110's 307340: z the same (xmm0 holds +E3C + 1)
group human
count 314DB2 | cHumanSpa/hm0a/hm0b/hm5d 314B60: the countdown +1328 -= 1 a tick while not 0: the store is skipped between stock ticks
count 314DC6 | 314B60: the countdown +1327 -= 1 a tick while not 0
count 314DD9 | 314B60: the countdown +132C -= 1 a tick while not 0
group objects
blend 31606F | 314B60's 315E60: x approaches its submodel's x by 0.1 a tick
src 3160C1 | 314B60's 315E60: y += +E14 a tick, a rise speed growing by 0.5 a tick to 1.5 (phase_steps.h, 316099)
group human
count 327724 | hm3c 327400: the material flipbook's tick +1450 += 1 a tick (frames at +1450 / 5 and / 3, mod 31)
group objects
pre 33ACCF | cBallObj 33ABC0: the vertical velocity +E54 += +112C a tick while 4643B0 holds (xmm0 holds +112C, loaded at 33ACC7); +E54 is in a stock tick's units (srcx 33B052 scales its add to y)
blend 3421C9 | cEnemyObj 341F10: material 4's colour (+50/+54/+58) approaches its target by 0.3 a tick (xmm4 is only that factor)
blend 342537 | cEnemyObj 3423D0: material 4's colour approaches its target by 0.3 a tick (xmm4 is only that factor)
pre 36884E | cKiType014/vt4a..4c 368790: position.y += +E54 a tick (xmm0 holds +E54, just stored); its gravity 0.6 is phase_steps.h's
pre 3690F6 | cKiType017 369090: position.y += +E54 a tick, as 36884E
pre 369AD6 | cKiType018/vt53 369A70: position.y += +E54 a tick, as 36884E
pre 36AACC | cKiType023/vt4f 36AA30: position.y += +E54 a tick (xmm1 holds +E54, just stored); its gravity 0.2 is phase_steps.h's
scaledadd 371F0E | vt29 371DE0: position += a turned (0, +E2C, K) a tick (cVec::operator+=)
lin 371F1C | vt29 371DE0: its roll +B8 -= 10 degrees a tick
group player
lin 38C2E2 | wp11 38C160 state 1: its spin +1078 += 20 degrees a tick
src 38DBBA | wp1a 38DB30: position.x += +E20 a tick (its 0.95 decay is decay_factors.h's, 38DBE7)
src 38DBD2 | wp1a 38DB30: position.z += +E28 a tick
pre 38DD7E | wp1a 38DCB0: position.x += +E20 a tick (xmm0 holds +E20, loaded at 38DD67)
pre 38DD95 | wp1a 38DCB0: position.z += +E28 a tick (xmm0 holds +E28, loaded at 38DD86)
lin 390309 | wp1d 390110: its spin +B0 += 30 degrees a tick
lin 392A55 | wp1e 392990: material 1's U += -0.002583 a tick (a .data constant, 7A7B9C), wrapped into -1..1
count 392E3F | wp1e 392D00 case 1: the fade-in count +E3C -= 1 a tick from 15: the store is skipped between stock ticks
group objects
count 3930CE | 392FE0 case 5 (a part's grow-in helper): its counter (param 4) -= 1 a tick from 5: the store is skipped between stock ticks
notyet 3930D0 notyet:39312D | 392FE0 case 5: `test cl, cl; jne` on the counter's old value: between stock ticks "not yet", so case 6 starts on a stock tick
count 396F8E | 396EA0 case 5 (the same helper's copy): the counter -= 1 a tick from 5
notyet 396F90 notyet:396FED | 396EA0 case 5: as 3930D0
group player
count 39B092 | wp47 39AEB0: the repeat timer +10F8 -= 1 a tick, reloaded when it goes below 0
count 39B2B0 | wp47 39B170: the repeat timer +10F8 -= 1 a tick, as 39B092
lin 39DE46 | wp4c 39DDB0 state 1: its spin +B0 += 30 degrees a tick (+ a random 0..20, 39DE4E)
lin 39DE4E | wp4c 39DDB0 state 1: the spin's random part, x 20 degrees a tick
callscale 39DE7A | wp4c 39DDB0 state 1: the forward step 2DA460 by 5 a tick (xmm1)
dst 3A0440 ("slowmo",0x3A0434) | wp55 3A0410: xmm6 keeps the slow-motion factor (23AD90) as its dt: its readers are the countdown +1108 -= dt (3A05F2) and the forward step dt x speed (3A062E, 2DA410), each a tick's step
group player
# pl00 integrates its vertical velocity +E54 as y += timeScale x +E54 (and
# gravity -= timeScale x 0.7), so +E54 is in a stock tick's units: what adds to
# it every tick, or moves y by itself, wants s.
pre 3A789A | pl00 3A75C0: +E54 += +10A4 a tick while +10A4 > 0, the push's vertical part (xmm0 holds +10A4, loaded at 3A788D)
pre 3A78B3 | pl00 3A75C0: y += +10A4 a tick while +10A4 <= 0 (xmm0 holds +10A4)
root 3AAEE9 | pl00 3A9630: xmm12 = 0.2, only the factor +E54 x 0.2 a tick while she rides something whose height changed (3AB70B)
pre 3B5648 | pl00 3B3FF0: position.x += the push +10A0 a tick (xmm0 holds +10A0, loaded at 3B5640); its 0.98 decay is decay_factors.h's
pre 3B565F | pl00 3B3FF0: position.z += +10A8 a tick (xmm0 holds +10A8, loaded at 3B5657)
lin 3BC9DB | pl00 3BC710 case 1: +E54 += 0.525 a tick
pre 3BB844 | pl00 3B9A70: the root motion's z step +EC8 += +E48 a tick, a forward drive decaying 0.9 (decay_factors.h); xmm0 holds +E48 (loaded at 3BB839)
pre 3C5DE3 | pl00 3C57A0: position.x += the push +10A0 a tick (xmm0 holds +10A0, loaded at 3C5DDB); its 0.98 decay is decay_factors.h's
src 3C5DF7 | pl00 3C57A0: position.z += the push +10A8 a tick
pre 3C6984 | pl00 3C68C0: y += +E54 = +E42 + 1 a tick (+E42 counts up on stock ticks, memory_timers.h); xmm0 holds that step
lin 3C9BB6 | pl00 3C9940: a submodel's y += sin(+E3C degrees) x 0.8 a tick (a bob)
count 3C9BC8 | pl00 3C9940: the bob's phase +E3C += 8 degrees a tick: skipped between stock ticks
callscale 3CA555 | pl00 3CA320 case 1: each tick she turns toward the lock-on target by at most 16 degrees (2DDF90's limit, xmm3)
callscale 3CA6F4 | pl00 3CA320 case 3: each tick she turns toward the target by at most 8 degrees
countlast 3CA75A | pl00 3CA320 case 3: +E48 x 0.6 a tick while +E58 bit 1 holds (after the mode-table pair): on the last tick of each stock period only
group menu
count 3FCF50 | cCockGameOver 3FCF50: the countdown +7C -= 1 a tick from 60; below 0 the screen's step +61 and a reload
group menu
count 45917F down | 459120 state 3 (a layout's wait): +68 -= 1 a tick (eax is 1: `cmp eax, 1; jne` just before); a skipped tick reads "not finished" for the jns
pre 4591C7 | 459120 state 1: a layout element's +2C += +48C a tick, a speed growing by 0.05 a tick (phase_steps.h); xmm0 holds +48C, just stored
group objects
srcblend 49948D | cItemObj 499410: x moves (target - x) / +E3C a tick, +E3C counted down by memory_timers.h: the divisor's blend
srcblend 4994B8 | cItemObj 499410: z the same
srcblend 499638 | cItemObj 4995A0: x moves (+E10 - x) / +E3C a tick, as 49948D
srcblend 499666 | cItemObj 4995A0: z the same
src 499878 | cItemObj 4997D0: y += +E54 (0.8, set just before) a tick
lin 4C20E7 | 4C1F50: +D2C += 0.05 a tick up to 1 (xmm6 is only that step)
group objects
src 4F0EA6 | ut23 4F0CD0: its spin +1164 -= 0.00058 a tick while its count is under 120, floored at 0.00058 (the floor compare keeps xmm0)
src 4F1081 | ut23 4F0CD0: the same in its other state
count 4F1A76 | ut25 4F1910: the wait +E42 -= 1 a tick while above its target and above 0: the store is skipped between stock ticks
src 509E02 | ut1b 509D10: position.y += +1098 a tick, its rise speed falling by 0.5 a tick (phase_steps.h, 509E17)
count 50E6FA | cDigObj 50E600: +1134 += 1 a tick up to 10 (then the fade by 0.06 a tick, phase_steps.h)
lin 515A55 | es13 515970: the phase +10E0 += 0.0005 a tick (a .data constant, 7B877C), wrapped
lin 5525F5 | ut47 5525B0: y -= sin(+1084) x 0.3 a tick (a bob; +1084's step is the world literal 55260E)
lin 5530CB | ut47 553000: the same bob, y -= sin(+1084) x 0.3 a tick
src 55D731 | uta2 55D630: position.y += +E54 a tick, its gravity 0.2 phase_steps.h's (55D746)
blend 560996 | uta4 5607A0: y approaches its hover height by 0.05 a tick
srcblend 560E5A | uta4 560BD0: x approaches its target by +E20 a tick (+E20 grows by 0.02 a tick, phase_steps.h)
srcblend 560E8A | uta4 560BD0: y approaches its target's y + 20 by +E20 a tick
srcblend 560EB4 | uta4 560BD0: z approaches its target's z by +E20 a tick
blend 560F0F | uta4 560BD0: the alpha +D2C approaches 0.6 by 0.2 a tick
blend 560F29 | uta4 560BD0: the alpha +D2C approaches its other target by 0.1 a tick
blend 5613E4 | uta4 561360 case 3: the alpha +D2C approaches its target by 0.1 a tick
scaledadd 5613F8 | uta4 561360 case 3: position += the velocity +E10..+E18 a tick (cVec::operator+=)
scaledadd 561629 | uta4 561360's other case: position += the velocity a tick
countlast 561416 | uta4 561360: the horizontal velocity +E10 x -0.6 a tick (a shake that dies out): on the last tick of each stock period only
countlast 56142E | uta4 561360: +E18 x -0.6, as 561416
countlast 561647 | uta4 561360's other case: +E10 x -0.6, as 561416
countlast 56165F | uta4 561360's other case: +E18 x -0.6, as 561416
srcblend 5618BE | uta4 5616C0: y approaches its hover height by +1118 a tick (a factor it grows)
blend 561CB0 | uta4 561A90: y approaches its hover height by 0.02 a tick
blend 561DFE | uta4 561A90: the same in its next case
blend 561F4C | uta4 561A90: the same in its third case
lin 5631A1 | uta6 562D30: its spin speed +E14 += 0.0052 a tick more while +10C0 has bit 0 or 14
lin 564322 | uta7 563EB0: its spin speed +E14 -= 0.0052 a tick while +10C0 has bit 0 or 14
callscale 564FFE | uta8 564E60: each tick it turns toward its point by at most n x 8 degrees (2DDF90's limit, xmm3)
count 5654DD | uta8 565410: +E3C += 1 a tick, its colour flashing on +E3C's parity: the store is skipped between stock ticks
src 56892C | utaa 568590: position.x -= +E10 a tick, a speed growing by 0.2 a tick (phase_steps.h)
src 56A9D9 | utab 56A640: position.x -= +E10 a tick, as 56892C
lin 56D485 | utb2 56D250 state 5: position.y -= 0.08 a tick while its wait +E3C runs (lea_timers.h)
lin 56D4D0 | utb2 56D250 state 7: position.y += 0.1 a tick while its wait runs
count 57040A | 570340 state 3: the wait +10DA -= 1 a tick from 90: the store is skipped between stock ticks
notyet 570411 notyet:5704AC | 570340 state 3: `test cx, cx; jne` on the wait's old value: between stock ticks "not yet", so state 4 starts on a stock tick
count 570499 | 570340 state 7: the wait +10DA -= 1 a tick from 90
notyet 5704A0 notyet:5704AC | 570340 state 7: as 570411, so state 1 starts on a stock tick
blend 57CBDA | ut2c 57CA00 case 6: material 0's +5C approaches 0.01 by 0.4 a tick
count 598C2C | 598B10 state 5 (a part's grow-in, as utbd's): the countdown +E36 -= 1 a tick: the store is skipped between stock ticks
notyet 598C32 notyet:598C9B | 598B10 state 5: `test cl, cl; jne` on the old value: between stock ticks "not yet", so state 6 starts on a stock tick
lin 5996C2 | et99 599590: material 1's +5C += 0.1 a tick (material 2's step is phase_steps.h's)
lin 5AB281 | utf9 5AB220 state 2: +10A8 += 2 a tick up to 2 (then state 0)
pre 5C6BF9 | em85 5C6450: its phase +3440 += speed x +343C a tick (xmm0 holds that step)
lin 5C6C97 | em85 5C6450: y += 0.4 a tick while it rises
lin 5C6CB9 | em85 5C6450: y += 2.4 a tick more while +D40 bit 3 is set
count 5C6DC0 | em85 5C6450: the countdown +348C -= 1 a tick while above 0
lin 5CBC60 | 5CBAD0 (em85's, 9 callers): +343C steps toward 3 x +3438 by 0.0065 a tick (one path)
lin 5CBD0D | 5CBAD0: the same by 0.0055 a tick (the other path)
blend 5D22A1 | em86 5D2050: y approaches its height by 0.2 a tick
lin 5D373F | em86 5D3600: +544C steps toward its target by 0.0065 a tick (one path)
lin 5D37EC | em86 5D3600: the same by 0.0025 a tick (the other path)
lin 5DAB40 | em87 5DA9A0: +535C steps toward its target by 0.0065 a tick
group actor
pre 5E06B8 | em88 5DF660: +390C += +3914 a tick up to +391C (xmm0 holds +3914, loaded at 5E06B0)
count 5EB465 | em89 5EB440: +50C0 += 1 a tick while 169EC0 answers 1
count 5EB477 (0x5EB46D,0x5EB479,(0x5EB46D,0x5EB473,0x5EB475,0x5EB477),None) | em89 5EB440: +50C0 -= 1 a tick otherwise, down to 0
count 5EC1C0 (0x5EC1B6,0x5EC1C2,(0x5EC1B6,0x5EC1BC,0x5EC1BE,0x5EC1C0),None) | em89 5EC0F0: the countdown +5080 -= 1 a tick while above 0
count 5EC209 | em89 5EC0F0: +5050 counts the ticks its target spends above 100
src 5EF876 | em89 5EF560: +5074 -= speed x 0.025 x xmm6 a tick (xmm1 holds that step; the speed's load is not a world row here)
pre 5EF890 | em89 5EF560: +5074 += speed x 0.025 x xmm6 a tick on the other path (xmm0 holds that step)
lin 5F2AAD | em89 5F2A60: +5060 steps toward its target by 0.0065 a tick (one of four paths)
lin 5F2AD1 | em89 5F2A60: the same, second path
lin 5F2AF5 | em89 5F2A60: the same, third path
lin 5F2B19 | em89 5F2A60: the same, fourth path
group objects
count 651F22 | ut35 651DC0: the countdown +11A9 -= 1 a tick (below 0 an effect and a reload): the store is skipped between stock ticks
notyet 651F28 notyet:651F58 | ut35 651DC0: `test cl, cl; jns` on the old value: between stock ticks "not yet", so the effect comes on a stock tick
group effect
lin 3633B0 | esfd 363210 case 3: +E54 += 0.5 a tick while +E3C is under its table's limit (then +E54 x 0.98, decay_factors.h; state 3 ends when +E54 < 0, 362D10)
count 3633B8 | esfd 363210 case 3: +E3C += 1 a tick up to the table's limit: the store is skipped between stock ticks
group player
group menu
count 407B92 | cCockTimer 407B00: the count-up timer +84 += 1 a tick up to 0x57E04: the store is skipped between stock ticks (the stock context's rate; its count-down twin 407BB2 is the mode group's)
group actor
# The slot-8 effect spawners (+1136: at 2 an effect and 0, else += 1) count
# their store on stock ticks; their `cmp al, 2; jb` read the held value on the
# ticks between and spawned on the first tick at 2: one every 2 stock ticks
# instead of 3. Between stock ticks the compare now reads "below" (notyetb).
notyetb 2513EA notyet:25141A | em05 family 2512E0: the spawner's `cmp al, 2; jb`: between stock ticks "below 2", so the effect comes on a stock tick, one every 3
notyetb 25B932 notyet:25B962 | em12 25B7A0: the spawner's test, as 2513EA
notyetb 25F423 notyet:25F462 | em13/em14 25F300: the spawner's test, as 2513EA
notyetb 26F0E9 notyet:26F119 | em27/em29 26F030: the spawner's test, as 2513EA
notyetb 274140 notyet:274170 | em2b 273FF0: the spawner's test, as 2513EA
notyetb 285947 notyet:285954 | em3d 285870: the spawner's test, as 2513EA
notyetb 288E7E notyet:288EB0 | em4d/em4e/em50 288D90: the spawner's test, as 2513EA
notyetb 291497 notyet:2914A4 | em51 2913B0: the spawner's test, as 2513EA
notyetb 29EF16 notyet:29EF48 | 29EF4A's spawner: its test, as 2513EA
notyetb 2CE934 notyet:2CE966 | 2CE968's spawner: its test, as 2513EA
notyetb 2D8C0D notyet:2D8C1A | em8f 2D8C1C's spawner: its test, as 2513EA
notyetb 241264 notyet:241294 | em00..em03 241180: the spawner's test, as 2513EA
