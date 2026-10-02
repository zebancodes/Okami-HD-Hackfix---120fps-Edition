# 2026-10-02: the near sites (a patch within 64 bytes, unproven), read by hand.
once | 189650: after its paced loop (wait 1897EB) ends, the entry's +4 word gains 1 and its state goes to 3, once | 18980F
follows | esp 18FBD0: the flipbook frame +26E advances when the countdown +26D (count row 18FBE0) runs out, and wraps | 18FC2F 18FC4E
follows | esp 190DA0: the phases +1A0 and +1A2 wrapped back into range after their paced adds (190EFC, 190FC1) | 190F28 190FED
follows | esp20 1A6C60: the material alpha +D2C is set from +1D0 each tick, then multiplied by the fade fraction (+276 - +277) / +276, whose window +277 is paced (19292C) | 1A6DA7
follows | esp20 1A6C60: the UV offsets +60/+64 wrapped by 2 after their scaled scrolls (rows at 1A6DBB, 1A6DD3, 1A6E01, 1A6E4C) | 1A6E91 1A6EAC 1A6ED2
stock | cMcLoad/cMcSave 1BE750: +D4 is the cursor's row, stepped on a navigation input (the menu repeat paces held directions) | 1BEA4D
fixed | memory-card save 1C0160 state 0x66: +284 counts down from +288 = 8 / mode, which imuln 1C0A74 makes N times that; the progress +C (to 30) steps once per reload | 1C0BC1 1C0BCA
follows | layout flipbook 1B2A50: the frame +87 steps (and ping-pongs) when the hold +86, paced by count2 1B2AC3, passes the sheet's delay | 1B2C03 1B2C1B
fixed | an00 1D57B0 / an01 1D8B20 launch slide: position += velocity a tick, now src/pre rows 1D5937, 1D5952, 1D8C54, 1D8C68 (the velocity's decay is decay_factors.h's) | 1D593F 1D5957 1D8C58 1D8C70
fixed | an01 1D9100 case 5: the countdown +1170 is count row 1D932E with notyet 1D9334 on its zero test | 1D932E
once | an00/an01/an03 state starters: the sub-state +E36/+E37 steps once after the motion starts and the timer +E3C is set, then the next sub-state counts the timer | 1D8516 1DC212 1DC500
once | an00 1D7020 / an01 1DA470 state starters: +E3C gains 60 or 45 once at the state's start when 169620 says so | 1D7178 1DA5D8
fixed | an00 1D72B0 / an01 1DA750: +B4 is 2DA510's blend toward +E14, whose factor FixTurnRate converts at 2DA510's entry for every caller | 1D778E 1DAC1B
once | an01 1DAEB0: +B4 = a parent's heading + its own (0 or kept), wrapped, once at the state's start (+E36 steps right after) | 1DAFCA
once | an04 1DD060 / an07 1E3550 / an1a 1F7290: the launch's start: +E10/+E18 = the normalized direction x 2 or x 1.5 and the sub-state +E36 steps, once | 1DD123 1DD132 1DD13A 1E3616 1E3625 1E362D 1F735A 1F7372
fixed | the animals' launch and knockback slides (an00..an20, cAnimal 202DC0/206000, cDogLikeHm 485390): position += velocity a tick, now src/pre/lin/dst rows (un_rows51) | 1DD1D6 1DD1EE 1E0888 1E08A0 1E36AD 1E36C5 1E6E8C 1E6EA4 1E9C8F 1E9CA7 1ED0F6 1ED10E 1EF94F 1EF967 1F09F4 1F0A0C 1F4774 1F478C 1F73F2 1F740A 1FA4AD 1FA4C5 1FDE0D 1FDE25 1FE3F8 1FE410 202E1B 202E33 206285 20629F 2062B7 485745 48575D
fixed | cBallObj 33C290 roll: position += +E20/+E28 a tick and the rolling turn, now pre 33C336/33C34D and lin 33C3B8 | 33C33A 33C352
fixed | objScroll falls: y += vy a tick, now rows 35C8CF, 35D001, 35D21A, 35D456 (gravity phase_steps.h, drag decay_factors.h) | 35C8D4 35D009 35D222 35D45E
follows | objScroll 35CC30/35D0E0: the colour's G and B lerp toward 1 by xmm2, the 0.05 its R lerp loads through a world blend literal (35CE40, 35D346) | 35CE6F 35CE8B 35D388 35D398
fixed | wp20 0x624 / utbd 22E430: the parts' springs, now zfirst on the pull and pre/src on the joint's move (near_rows01) | 39350F 393537 3935BB 3935E1 22E717 22E73F 22E7C3 22E7E6
follows | utbd 22E430 / wp20 0x624: the joint gives back 0.8 of the parent's turn since the last tick (+110C/+1C64 keep the last), whatever the rate | 22E793 39358B
fixed | utbd 22E430: the scale growth (src 22E5B8/22E5BD) and the state-5 countdown (count 22E60F, notyet 22E615) | 22E5C9 22E5D1 22E60F
fixed | wp1c 38F400: position += velocity a tick, now pre 38F741/38F75B | 38F748 38F760
follows | wp20 393210: materials 1 and 2's U scroll by xmm7, the 0.02 that lin 39325C loads for material 0, and their wraps | 393299 3932A4 3932C5 3932D0
follows | wp20 393210: the glow's B channel +58 steps by xmm2, the 0.1 that lin rows 3932F3/39333B load for +50/+54 | 39332B 39336F
fixed | pl00 states 0 and 1: position += the push +10A0/+10A8 a tick, now pre/src rows 3B209E, 3B20B5, 3B297F, 3B2993 | 3B20A2 3B20BA 3B2983 3B299B
stock | pl00 3B18D0: +B8 *= the port's mode-table pair at 7A8240, which mode_constants.h rewrites to k^timeScale | 3B216B
once | an00/an04/an06 state starters: the sub-state +E36/+E37 steps once after the motion starts and +E3C is set (the next sub-state counts +E3C) | 1DB759 1DF0C4
once | an04 1DE770: +E3C gains 45 once at the state's start | 1DE8D8
fixed | an04 1DE9F0 / an06 1E2040: +B4 is 2DA510's blend toward +E14, whose factor FixTurnRate converts at 2DA510's entry | 1DEE7D 1E2528
once | an04 1DD9A0 / an06 1E2790: +B4 = a parent's heading + its own (negated or zeroed at random), wrapped, once at the state's start (+E36 steps right after) | 1DDC57 1E294C
once | animal state starters (an06/an08, an09): the sub-state +E36/+E37 steps once after the motion starts, beside the timer +E3C's set | 1E2F91 1E8C63
once | animal state starters (an07, an09, an0b): +E3C gains 60 once at the state's start when 169620 says so | 1E4C01 1E83AE 1EB589
once | an09 1E77E0: +B4 = a parent's heading + its own (negated at random), wrapped, once at the state's start | 1E79CB
follows | an09 1E7AF0 / an0b 1EAC20: the colour's G channel +D24 steps by xmm1, the 0.03 that the world row on its load (1E7CD6, 1EAE28) scales for R | 1E7D08 1EAE5A
once | animal state starters (an0b, an0c, an16, an05/an18): the sub-state +E36/+E37 steps once at the state's start | 1EC3BA 1ED60F 1EFC64 1F3A5F
once | animal state starters (an0c, an05/an18): +E3C gains 60 once at the state's start when 169620 says so | 1EE487 1F1ED1
follows | an0c 1EDC50: the colour's G channel +D24 steps by xmm1, the 0.03 the world row 1EDFAA scales for R | 1EDFDC
fixed | an0b 1EC2C0: the wander countdown +1170 is count row 1EC414 with notyet 1EC41A | 1EC414
stock | an05/an18 1F0DB0 case 7: +1170 counts down and reloads itself with a random 0..31; nothing else reads it (the turn toward +1160 runs every tick either way) | 1F1028
once | animal state starters (an19, an1a): the sub-state +E36 steps once at the state's start, beside the motion's start and +E3C's set | 1F65F4 1F67CC 1F7AB2 1F7B94
once | an19 1F50E0 / 1F66C0: +B4 = a parent's heading + its own (negated or zeroed at random), wrapped, once at the state's start | 1F51CF 1F67B7
follows | an19 1F5420: the colour's G channel +D24 steps by xmm1, the 0.03 the world row 1F5628 scales for R | 1F565A
once | an19 1F5BE0: +E3C gains 60 once at the state's start when 169620 says so | 1F5D3F
fixed | +B4 is 2DA510's blend toward a target heading, whose factor FixTurnRate converts at 2DA510's entry for every caller (template turn_blend) | 1F89D3 1F8B7C 1FC554 1FFEED 2A5605 3C5C45 3CA44F
follows | the colour's G/B channel steps by xmm1, the constant the world row on its rip load scales for R (template colour_channel) | 1FB8B7
once | +E3C gains a constant once at the state's start when 169620 says so (template e3c_bonus) | 1FBF71 1FF968
once | a state's start: the sub-state +E36/+E37 steps once beside the motion's start, an effect or sound, or the timer +E3C's set (em7a 2D4BFE: once per animation end) (template substate_start) | 1FC936 1FCB46 200C14 255372 255DE6 25D44C 28C69D 28C959 28E778 2A2FCC 2A30FA 2A3483 2A3576 2A36AE 2B9A2A 2D4BFE 30D77D 32C212 37F1A2 38B594 39AE7C 3A03D2 3A0C1E 3A0CA2 4AB88C 4AB96C 4ABA4C 62F01D 631C6E
once | +B4 = a parent's heading + its own (negated or zeroed at random), wrapped, once at the state's start (template heading_start) | 1FCB31 1FEFB3
once | an1a 1F85B0: +E3C gains 60 once at the state's start when 169620 says so | 1F8726
follows | anc7 2017E0: +E36 steps when the alpha +D2C, stepped by phase_steps.h, passes 0.2 | 2018C9
fixed | 203FE0: position.x += dir.x x 0.9, the 0.9 a world literal (2040FE), as z's (204123) | 204119
once | cKiType reaction 206A10 (from 363F90, a hit): the sway's velocities +1128/+112C x -0.4 once per reaction | 206A58
follows | 209330: the colour's B channel +D28 steps by xmm2, the 0.2 world literal (209354) R and G use | 209397
fixed | cKiType 2097C0 state 2: the fall, now pre 20981F | 209824
fixed | actors' slot 1 (20C620): the fade-in byte +D79, now count 20C798 | 20C798
fixed | turn toward a point 20E210: the heading's step is clamped by the limit argscale 20E230 scales | 20E282
fixed | ut04 213FB0: the countdown +111C, now count 214059 | 21405C
fixed | 21E850/21EBD0/21EF90: the waits +13F0, now count rows 21E98A, 21EA1E, 21ED02, 21F0C2 | 21E98A 21EA1E 21ED02 21F0C2
follows | ut66 222B30: the colour's G/B lerp toward 1 by xmm2, the 0.1 world literal its R lerp loads (222B49) | 222B8B 222B9B
follows | ut92 228200/2284E0: +E36 steps when +E3C, paced by memory_timers.h, passes 60 | 228352 22865D
fixed | utcb 22F820: position.y +-= +1094 a tick, now src 22F83E/22F848 | 22F850
follows | utd7 2310C0: the colour's B channel +D28 steps by xmm2, the 0.05 world literal R and G use (231157) | 23119A
follows | utd9 231A80: the colour's G/B lerp toward 1 by xmm2, the 0.1 world literal its R lerp loads (231C73) | 231CB5 231CC5
once | utf6 236A50: a submodel's y gains xmm6 once when its countdown runs out (the state +E36 is set in the same branch) | 23731C
stock | 239AA0 (enemies' advance-and-test, 10 callers): +F54 = +F54 x speed only for the motion advance's call, and put back right after | 239ACE
fixed | em00..em03 241180: the effect spawner +1136 and the below-target count +12B6, now count rows 241296/2412E8 | 241296 2412E8
once | em02 24D9B0: +E37 (repeats left) steps once per wait +E3C's end, with the state +E36 = 3 | 24DCE1
once | 253D20: position.y += 20 once as it starts (an effect and +E36's step follow) | 253EEB
fixed | 255ED0: x approaches its point through the blend literal 256222; z += +E18 a tick, now pre 256255 | 256242 25625A
fixed | utd7 231200: the cooldown +1630, now count 2313BE | 2313BE
once | enemy states (2529B0's): +E37, the repeats left, steps once per animation end or clock expiry, with the state's next step | 256DD8 257697 258136 25852D
once | enemy state starters (2529B0's, em13/em14 25F960's): +E36 steps once at the state's start, beside an effect or a sound | 25832F 260283 26045D
fixed | em12 25E4C0: the orbit radius +1384, now lin 25E535 | 25E54B
fixed | em12 25E4C0: the orbit angle +1380 += speed x 0.0698 a tick, the speed's load a world step row (25E5AE) | 25E5DA
follows | em13/em14 261AC0: heading += +EF4, the root rotation the motion advance writes each tick | 261C7F
once | em13/em14 263400/263550, em27/em29 2723C0: a repeats-left count (+E37, +11B3) steps once per animation end | 2634F9 263A41 2724C5
once | em27/em29 state starters: +E36 steps once at the state's start (with +11B4 += 20, +13E8 = 90 + 30 x random) | 26FD5C 26FD62 270D66 2714D3 2714E1 27261D
fixed | em27/em29 272EC0: the orbit radius' shrink, now lin 272F5A; the angle +1410 += speed x 0.0698, the speed's load a world step row (272FB7) | 272F65 272FE3
once | em2b 275A80: the repeats-left +1398 steps once per animation end | 275C3D
once | em2b 2779A0 case 4: the leap's velocity +E10/+E18 = the direction x distance / 16, once at its start (its moves are world rows 277CF6/277D0D) | 277CA9 277CB1
fixed | em2b 278590: the effect pacer +E3E, now count 27881C with notyet 2787CB | 27881C
stock | em2d 27AD50 on map 0x304: +248C is halved while above 60 and then set to 40 if above 40, in the same pass, so it lands at 40 whatever the rate | 27B8AD
once | em2d 281AE0: a piece's bounce count steps once per bounce (its velocity x -0.95 there) | 2824A4
fixed | em3d 2865B0: +B0 is 2DA510's blend, whose factor FixTurnRate converts at 2DA510's entry | 28689E
fixed | em3d 2865B0: the clock +11C0 and the bob's y step, now pre 286B86/286BB2 | 286B8F
once | em4d 28AE50: +E36 steps once at the state's start | 28AFAA
once | em4d/em4e/em50 28B670: +E37 steps once per animation end | 28B88E
fixed | em4d/em4e/em50: the rise y += 2 a tick, now lin 28D254, 28D72D, 2911FA | 28D25C 28D735 291202
once | em4d/em4e/em50, em52: +E36, +E37 or the repeats-left +124A step once per animation end | 28D2CD 28D2D7 28D7DB 2912A8 297C46 298442
once | em51 291B80: a spawned child's y += 5 once at its spawn | 291C2E
follows | em52 2940C0: the phases +12B0/+12BC step by speed x the .data literals 79FD48/79FD58, which world rows scale | 294143 2942C0 294305
follows | em52 2990A0: +1278 -= xmm2, the 0.0025 world literal its other branch adds (2993BC) | 2993EE
follows | em52 2994C0: the phase +12B0 steps by speed x the .data literals 79FD60/79FD48 (world rows), and +1278 -= xmm3, the 0.003 world literal (299624) | 299511 299705 29965A
follows | em52 29A380: +1278 -= xmm2, the 0.0025 world literal (29A4B4) | 29A4E6
once | em52 29B300: a piece's bounce count steps once per bounce | 29B66C
fixed | em56 29D3B0: y moves by the speed a tick, now src 29D454/29D4C2 | 29D458 29D4CA
once | em56/em57/em59 2A1260: +E37 steps once per animation end | 2A1425
once | em56..em58 2A3AF0, 29F770's 2A4BA0/2A53F0: a clock (+1390, +1394) loses 450..900 once at the state's start, beside +E36's step | 2A3BD9 2A4DF6 2A5584
fixed | em56..em58 2A3AF0: z += 2 x +E18 a tick, +E18's load a world row (2A3F9B), as x's | 2A3FB3
fixed | 29F770's 2A4BA0: the wait +E3C, now count 2A4E49 with notyet 2A4E35 | 2A4E4C
once | 29F770's 2A5CA0, em59 2A7C00/2A8030: a clock +1394 loses 600..900 once at the state's start | 2A5D89 2A7CA1 2A8296
once | em59 2A8030, em60 2AF240, em61 2BAE40: +E37 steps once per animation end | 2A8144 2AF561 2BB0A1
once | em61 2BA4A0/2BB590 state starters: +1410 -= 1000, +144A and +E3E step once at the state's start | 2BA538 2BA54A 2BA613 2BB631 2BB641
stock | em65 2C40A0: y += +16F4 a tick, but +16F4 is 0 (2C427B zeroes it after the direction +16F0 is set); x and z are speed-scaled world rows | 2C42CC 2C43B5 2C44B0 2C45A6
stock | em65 2C48D0: y += +16F4 a tick, which 2C4A9E zeroes after the direction is set; x and z are world rows | 2C4AEF 2C4BCA 2C4DE2
fixed | em65 2C40A0: x += +16F0 x speed a tick, the speed's mulss a world row (2C4578) | 2C458E
fixed | em65 2C5770: y += speed x 0.76 a tick, the speed's load a world step row (2C5D0A) | 2C5D26
once | em68 2CA9C0: +124A steps down once per edge of the global flag B6B2C0 bit 11, which it then sets | 2CAA3C
once | em68 2CBF20, em69 2D0F90, em7c 2D4D40: +E36 steps once at the state's start | 2CBFCD 2D0FE1 2D4ECF
once | em69 2D2140, em83 2D7240: +E37 steps once per animation end | 2D2589 2D7463
fixed | em6a 2D48E0: the glow +11A4, now pre 2D49A4 | 2D49B3
follows | em8f 2D79F0 (ffe6c5c8's parts): +1448 and +1444 x xmm6, the damping ufirst rows load (2D7B61, 2D7E86, 2D831C); the part's lerps by xmm8 (blendr 2D7A70) and xmm2 (blend 2D8054) | 2D7C5C 2D7C8C 2D7CAC 2D7F88 2D8095 2D80B4 2D80D4 2D823A 2D8417
fixed | em8f's body: the death's moves and shake, the hover and return approaches, now rows 2D9192..2D9CDE (near_rows01) | 2D918A 2D91D8 2D9328 2D9673 2D9709 2D9A7A 2D9AD2 2D9AFC 2D9B26 2D9B95 2D9CC9 2D9CEB
fixed | et07: material 1's U scroll (lin 2E2703) and its wraps; the fade-in count (count 2E2D60) | 2E2723 2E272E 2E2D60
fixed | et08 2E36F0 case 4: the submodel's sink, now src 2E39FF | 2E3A0B
stock | et0f 2E4CA0: +B4 += the angle to the target clamped at 2 pi: a snap, the same at any rate | 2E4EA7
fixed | et0f 2E5330: the countdown +112C, now count 2E555B | 2E555B
once | et12 2E6C80: +E34 steps once at the state's start | 2E6CD7
fixed | et12 2E6C80: the wait +1080 (count 2E6D13, notyet 2E6D19) and the state's step after it | 2E6D13 2E6D22
fixed | et24 2E83E0: the phase +1088, now lin 2E84C2 | 2E84D7
follows | et2b 2E8FB0: material U wrapped by 1 after its phase_steps.h scroll (2E8FE6) | 2E9008
follows | et2d 2E93A0: +E34 steps when +E3C, paced by memory_timers.h, runs out | 2E9DA6
fixed | et2e 2EA790: the sink, now lin 2EA9B1 | 2EA9B9
fixed | et6b 2F2970 case 8: the alpha's fade, now src 2F2E38 | 2F2E4A
once | et6f 2F3210: three values lose 30 once each when the timer 1674C0 reports its end | 2F3292
once | the waypoint follower 3049D0: the waypoint index +1274 steps once per waypoint reached | 304A2D
fixed | 307340: x and z move by (target - x) / (+E3C + 1), now srcblend 307619/307642 | 307622 30764B
once | cHumanAngel 3105D0, hm08 31AAC0, hm0d 31CC60/31CDA0: +E36 steps once at the state's start | 310675 31AB85 31CCDA 31CE1A
fixed | 314B60: the countdowns +1328, +1327, +132C, now count rows | 314DB2 314DC6 314DD9
fixed | 315E60: x's approach (blend 31606F) and y's rise (src 3160C1) | 31607B 3160C9
once | 3206A0, hm1f 3208F0, hm22 3213A0, hm24 321870, hm8e 333960: +E36 steps once at the state's start | 3206F4 320944 321434 32191E 333A04
follows | hm27 323240 / hmbd 335530: y and z lerp by xmm6, the factor whose divss world row (323380, 3356AF) converts x's | 3233B1 3233D1 3356DA
fixed | hm3c 327400: the flipbook tick +1450, now count 327724 | 327724
fixed | cBallObj 33ABC0: +E54 += +112C, now pre 33ACCF | 33ACD7
fixed | cEnemyObj 341F10: the colour approach's factor, now blend 3421C9 | 342235 34223A
fixed | cEnemyObj 3423D0: the colour approach's factor, now blend 342537 | 342571 3425A1
follows | esfd 362F50/363790: +E36 steps when +14F0, stepped by phase_steps.h, reaches 0 | 3631E0 3638B7
fixed | cKiType014/017/018/023: the falls y += +E54, now pre 36884E, 3690F6, 369AD6, 36AACC | 368853 3690FB 369ADB 36AAD1
fixed | vt29 371DE0: its move and roll, now scaledadd 371F0E and lin 371F1C | 371F3A
once | wp04 384930/384A80: +E36 steps once at the state's start | 384A3C 384B7A
once | wp04 384E30, wp07 386580/386620, wp0e 389A30: +E36 steps (and +B0 gains a random turn) once at the state's start | 384EB2 3865E9 386689 389AC0
fixed | wp11 38C160: the spin +1078, now lin 38C2E2 | 38C308
once | wp11 38C160: +E24 and +E28 x 0.95 once per bounce off the floor | 38C387 38C3A6
fixed | wp1a 38DB30/38DCB0: the slides, now src/pre rows 38DBBA, 38DBD2, 38DD7E, 38DD95 | 38DBC2 38DBDA 38DD82 38DD9A
fixed | wp1d 390110: the spin +B0, now lin 390309 | 39031D
fixed | wp1e: material 1's U scroll (lin 392A55) and its wraps; the fade-in count (count 392E3F) | 392A75 392A80 392A93 392E3F
fixed | 392FE0/396EA0 case 5: the counter, now count 3930CE/396F8E with notyet 3930D0/396F90 | 3930CE 396F8E
fixed | wp47 39AEB0/39B170: the repeat timer +10F8, now count rows 39B092/39B2B0 | 39B092 39B2B0
follows | wp47 39B950: +10EC -= xmm6, the slow-motion dt the world row on 39B98A scales | 39BABB
once | wp47 39BB10: +E54 loses a random 0..3 once as the state starts | 39BD00
fixed | wp4c 39DDB0: the spin and forward step, now lin 39DE46/39DE4E and callscale 39DE7A | 39DE72
fixed | wp55 3A0410: its dt, now dst slowmo 3A0440 | 3A05F9
fixed | pl00 3A75C0: the push's vertical part into +E54 or y, now pre 3A789A/3A78B3 | 3A78A2 3A78B8
fixed | pl00 3A9630: +E54 x 0.2 while riding, now root 3AAEE9 | 3AB710
stock | pl00: +B8 x the port's mode-table pairs (7A81E8, 7A8240), which mode_constants.h rewrites to k^timeScale | 3B17A9 3B4079
once | pl00 3B3FF0: +1145 steps once per combo step (a state change in the same branch) | 3B4B0E
fixed | pl00 3B3FF0: position += the push +10A0/+10A8, now pre 3B5648/3B565F | 3B564C 3B5664
once | pl00 3B7320/3B9A70: a turn toward the lock-on target within 32..60 degrees, once at each attack step's start (with its motion and sounds) | 3B78D7 3B7BA4 3BA00F 3BA32E 3BA661 3BA949 3BAC24 3BAF04 3BB17F 3BB441
fixed | pl00 3BC710 case 1: +E54 += 0.525 a tick, now lin 3BC9DB | 3BC9E3
fixed | pl00 3B9A70: the forward drive into the root motion step, now pre 3BB844 | 3BB84C
stock | pl00: +B8 and +E48 x the port's mode-table pairs (7A8160, 7A8170, 7A81E8, 7A8240), which mode_constants.h rewrites to k^timeScale | 3BE9DF 3C3763 3C481A 3C4844 3C4869
once | pl00 3C18B0: the motion factor +F54 gains 0.5 once per press of the button | 3C19D4
once | pl00 3C2430: +1145 steps once per combo step or once +E3E passes 300 (a state change in the same branch) | 3C2841 3C2865
fixed | pl00 3C43C0/3C4D90/3C9940/3C5350: +E48 x 0.6 (or 0.5) a tick while a flag holds, now find_decay_factors.HAND (decay_factors.h) | 3C48EF 3C50CD 3C9D27 3C545C
stock | pl00: +B8 and +E48 x the port's mode-table pairs (7A8158, 7A8160, 7A8170, 7A81E8, 7A8240), which mode_constants.h rewrites to k^timeScale | 3C5023 3C5AED 3C9C1C 3C9C46 3C9C6B
stock | pl00 3C70C0: +10E8 x the engine's own mode table at 7A81B8 (0.86 / 0.9274), which mode_constants.h rewrites | 3C7221
fixed | pl00 3C57A0: +B4 is 2DA510's blend (FixTurnRate) | 3C5C45
fixed | pl00 3C57A0: position += the push, now pre 3C5DE3 / src 3C5DF7 | 3C5DE7 3C5DFF
fixed | pl00 3C68C0: the rise y += +E42 + 1, now pre 3C6984 | 3C6989
fixed | pl00 3C9940: the bob, now lin 3C9BB6 and count 3C9BC8 | 3C9BC3 3C9BC8
fixed | pl00 3CA320 cases 1 and 3: the homing turns, now callscale 3CA555/3CA6F4 | 3CA567 3CA706
stock | pl00 3CA320: +E48 x the mode-table pair at 7A8158 (mode_constants.h) | 3CA750
fixed | pl00 3CA320 case 3: +E48 x 0.6 a tick while +E58 bit 1 holds, now countlast 3CA75A | 3CA762
once | pl00 3D08E0: +E3C = 120 less the word B6B13C, once as the state starts | 3D0A2F
follows | the player's weapon 3D1CB0: +D2C x the fade byte +1070 / 255, +1070 a count row (3D1D49) | 3D1D76
follows | cCockCombo 3FAB00: +71 and +78 change once each time the phase +74, stepped by phase_steps.h, passes pi | 3FAB2D 3FAB45
fixed | cCockGameOver 3FCF50: the countdown +7C, now count 3FCF50, and the step after it | 3FCF50 3FCF57
follows | cCockGameOver 3FCFC0: +61 steps when +78, stepped by phase_steps.h, passes 1 | 3FCFDB
once | 415B30: a bounce: +90 x -0.43 and +99's step once per bounce | 415BE7 415C3A
follows | 4397B0: +29 steps when the count +20 (menu_transitions.h) passes 27 | 43986E
follows | 439AD0: +29 steps when +C or +10, stepped by phase_steps.h, pass their bounds | 439B2D 439B5A
fixed | 459120: the wait +68 (count 45917F) and the element's move (pre 4591C7) | 45917F 4591CF
stock | camera 468420: +3B4 x the mode-table pair at 7A8178 (mode_constants.h) | 46847C
follows | camera 468FF0: +25C x xmm4, the 0.96 a world row on its load converts (469007) | 4690BB
fixed | camera 46E890: +244 x 0.8 a tick beside +240's, now find_decay_factors.HAND | 46EE6B
follows | camera 477820: +190 lerps by xmm2, the factor blendr 477CE9 converts | 477D20
fixed | cItemObj 499410/4995A0: x and z move by (target - x) / +E3C, now srcblend rows | 499495 499640
fixed | cItemObj 4997D0: y += 0.8 a tick, now src 499878 | 499880
follows | 4BBE10: the flicker table is walked once a pass of the task loop whose wait(1) at 4BBEB0 task_waits.h makes a stock tick's (the walk is an inner loop over the table) | 4BBED9 4BBF01
fixed | 4C1F50: +D2C's step, now lin 4C20E7 | 4C2106
once | scripted tasks (4C31C0, 4C7D80, 4CBB70, 4D4B60, 4E1BA0, 4EF210, 504930): a fade's first step before its loop, whose wait(1) task_waits.h makes a stock tick's (the loop repeats the step once a pass) | 4C34B3 4C84B4 4CBBE1 4D514C 4D5154 4D515C 4E2261 4E2269 4E2271 4EF891 4EF899 4EF8A1 504FD2
fixed | ut23 4F0CD0: the spin's slowdown, now src 4F0EA6/4F1081 | 4F0EAD 4F1088
fixed | ut25 4F1910: the wait +E42, now count 4F1A76 | 4F1A76
once | ut17 4FF080 / cBamboo 4FFB00: on a hit, +E36 steps back and the hit count +10DA/+10DB steps (at 90 it breaks) | 4FF21D 4FF23C 4FFC76 4FFC95
fixed | ut1b 509D10: the rise y += +1098, now src 509E02 | 509E0A
fixed | cDigObj 50E600: the count +1134, now count 50E6FA | 50E6FA
fixed | es13 515970: the phase +10E0, now lin 515A55 | 515A6A
once | scripted tasks (51FE30, 520F90, 52FE00, 530860): a fade's or a counter's first pass before its loop, whose wait(1) task_waits.h makes a stock tick's (as 521105, 5309EB) | 520289 520291 520299 5210EA 521120 521229 5300F2 5300FA 530102 530A02 530A11 530B26 530B3D
follows | ut5e 524790: material 1's U wrapped by 1 after its scroll row | 52493F
fixed | cutscene task 54EDC0: in the walk loops task_waits.h runs once a stock tick (waits 54F698, 54FA0A), each pass doubles a walker's step +EC8 (this tick's: the motion advance rewrites it every tick, 363A20) and applies it once more through cMatrix::Apply (2DA3D0); dstn rows 54F665, 54F9D7 make the doubling x 2N, a stock tick's push a pass | 54F669 54F9DB
fixed | ut47 5525B0/553000: the bob, now lin 5525F5/5530CB | 552601 5530D7
fixed | uta2 55D630: the fall, now src 55D731 | 55D739
fixed | uta4 5607A0: the hover approach, now blend 560996 | 5609A3
fixed | uta4 560BD0..561A90: its approaches (srcblend, blend), moves (scaledadd) and shake (countlast), now rows 560E5A..561F4C (near_rows01) | 560E66 560E97 560EC1 560F1B 560F35 5613F0 56143E 56166F 5618CB 561CBD 561E0B 561F59
fixed | uta6 562D30 / uta7 563EB0: the extra spin step, now lin 5631A1/564322 | 5631B1 564331
fixed | uta8 564E60: the turn, now callscale 564FFE | 565013
fixed | uta8 565410: the flash count +E3C, now count 5654DD | 5654DD
fixed | utaa 568590 / utab 56A640: the slide, now src 56892C/56A9D9 | 568934 56A9E1
fixed | utb2 56D250: the sink and the rise, now lin 56D485/56D4D0 | 56D48D 56D4D8
fixed | 570340: the waits +10DA, now count 57040A/570499 with notyet 570411/5704A0 | 57040A 570499
follows | scripted tasks (576E30, 577490, 585AE0, 5884F0, 5887E0, 58C7E0, 58CD50): a fade's first pass before its loop, whose wait(1) task_waits.h makes a stock tick's (as 588655, 588F91) | 57709C 5770A4 5770AC 5775BA 586197 588625 58863D 5886AB 588F53 588F72 58C9BF 58C9C7 58C9CF 58CE6A
stock | ut2b 57AC60: +B4 += the angle to its point clamped at pi: a snap | 57B11C
fixed | ut2c 57CA00 case 6: material 0's approach, now blend 57CBDA | 57CBE7
follows | 598B10 state 3: the scales +C0/+C8 step by xmm7, the 0.05 world literal (598B56) | 598BE3 598BEB
fixed | 598B10 state 5: the countdown +E36, now count 598C2C with notyet 598C32 | 598C2C
fixed | et99 599590: material 1's step, now lin 5996C2 | 5996CA
follows | the scripted task 59D230: a fade's first pass before its loop, whose wait(1) task_waits.h makes a stock tick's | 59D652 59D656 59D65E
follows | utbf 5A2E20: material 1's U wrapped by 1 after its scroll row | 5A2E9A
fixed | utf9 5AB220: the ramp +10A8, now lin 5AB281 | 5AB290
follows | 5B5BF0: the flicker table is walked once a pass of the task loop whose wait(1) at 5B5CA0 task_waits.h makes a stock tick's (an inner loop over the table) | 5B5CC8 5B5CF5
follows | 5C4B00: y sinks by xmm6 or xmm7 a tick, constants world lin rows load (5C4B2D, 5C4BC7, 5C4D26, 5C4D9A, 5C4E19) | 5C4C06 5C4C50 5C4D11 5C4D4E 5C4E48
once | em85 5C5DD0: +3450 steps once as its state changes (+E34 = 0x102 in the same branch) | 5C62B5
fixed | em85 5C6450: the phase, the rise and the countdown +348C, now rows 5C6BF9, 5C6C97, 5C6CB9, 5C6DC0 | 5C6C06 5C6C9F 5C6CC1 5C6DC0
fixed | 5CBAD0, em86 5D3600, em87 5DA9A0: the steps toward a target, now lin rows on their step loads | 5CBD4F 5D382E 5DAB72
fixed | em86 5D2050: the height approach, now blend 5D22A1 | 5D22AE
once | em87 5DBA90: a piece's bounce count steps once per bounce | 5DC9FF
fixed | em88 5DF660: the ramp +390C, now pre 5E06B8 | 5E06C0
fixed | em89 5EB440: the count +50C0 up and down, now count 5EB465/5EB477 | 5EB465 5EB479
fixed | em89 5EC0F0: the countdown +5080 and the count +5050, now count 5EC1C0/5EC209 | 5EC1C2 5EC209
fixed | em89 5EF560: +5074's steps by the speed, now src 5EF876 / pre 5EF890 | 5EF89C
fixed | em89 5F2A60: the step toward a target, now lin rows on its four loads | 5F2C71
once | 60C0E0: a spawned object's y += 16 once | 60C66F
follows | scripted tasks (618A00, 61C2E0, 627C20, 627F70, 64E450): a fade's first pass before its loop, whose wait(1) task_waits.h makes a stock tick's | 618A77 61C3E3 61C3F0 61C3FE 627D78 627D93 627E10 6285A6 6285C8 64E653
once | scripted tasks 618C70 / 650720: a flag byte steps once per step of the script | 618CA9 65083B
stock | ut35 6518E0: +E48 and +B8 x the mode-table pairs at 7A8160/7A81E8 (mode_constants.h) | 651A00 651A25
stock | ut35 651B40/651DC0: +E48 and +B8 x the mode-table pairs at 7A8160/7A8240 (mode_constants.h) | 651C60 651EAB
fixed | ut35 651DC0: the countdown +11A9, now count 651F22 with notyet 651F28 | 651F22
fixed | esfd 363210 case 3: +E54's rise (lin 3633B0) and the count +E3C (count 3633B8) | 3633B8 3633C0
fixed | pl00 3B2CF0, her ground movement: the run fix's jog parameters (kJogParams in dinput8_proxy.cpp, written to .data) carry the acceleration 7A8148 (ts^2), the charge threshold 7A8350 and divisor 7A8360 (ts) and the charge frames 7A8354 (/ts), so the speed and the charge +1174 are already in real time; rows here doubled them (removed 10-02) | 3B2FCC 3B31C4 3B31E5 3B358B
follows | pl00 3B2CF0: +E48 x xmm7, the 0.94 whose load hoisted_decay.h converts (3B2FF7) | 3B3139
fixed | cCockTimer 407B00: the count-up timer +84, now count 407B92 | 407B92
