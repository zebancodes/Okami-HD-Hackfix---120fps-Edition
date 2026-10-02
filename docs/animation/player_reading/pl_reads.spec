# pl00's update (3A9630)
fixed | pl00 update: the slide-off push, on stock ticks by notyet at 3A9E07 (its velocity changes once a stock tick) | 3A9E9B 3A9EA3 3A9EBA 3A9EC2
fixed | pl00 update: the slide's move, s of the velocity a tick (srcx 3A9ED5, pre 3A9F09) | 3A9EDD 3A9F0E
stock | pl00 update: the slide's y component +10C4 is never written (0): pos.y += 0 | 3A9EF5
fixed | pl00 update: the slide's damping on the last tick of each stock period (countlast 3A9F37..3A9F5A) | 3A9F3F 3A9F47 3A9F5F 3A9F67
follows | pl00 update: B4DFBA's zero test, a timer the count row at 3AA0D1 paces | 3AA1B5
left | pl00 update: +1140 is set to 1 on a lock-on change and x 0.97 a tick, but nothing reads pl00's +1140 (its only other uses are other classes' fields) | 3AAE43
stock | pl00 update: y - 450 (950) for the ground query 45FC40, undone right after | 3AB468 3AB486 3AB4C0 3AB4DE
stock | pl00 update: +FF8 is the ground query's height (45FC40 writes it, 46063C) plus 0.5 each tick, an offset after a fresh copy | 3AB582
follows | pl00 update: on a moving platform, her local offset +FD0/+FD8 gains this tick's own move (already scaled) in the platform's frame | 3AB89C 3AB8A4
follows | pl00 update: on a moving platform, heading += the platform's turn since last tick (+1028): follows the platform | 3AB903
# wp02's beads (382340)
stock | wp02 beads: +1110 counts the beads in state 1 this tick (3822D0 zeroes it every tick) | 3825BF
fixed | wp02 bead: its rate +1938 += 0.8 (lin 3827F7) | 382806
stock | wp02 bead, homing again (state 10): the rate +1938 is set to 8 as the state starts (382F75) and += 0.8 is capped at 8: always 8 | 382FAF 382FBD
fixed | wp02 bead: the position's stores after the scaled step (pre rows) | 3828D5 3828EB 3828F5 382B7A 382B93 382BB0 382CF5 382D0B 382D15 383059 38306F 383079 383319 383332 38334F
once | wp02 bead, hit (state 4): the bounce v.x, v.z x -0.8 and v.y = 6, once as the state starts (then state 5) | 382ABA 382AE1
fixed | wp02 bead: the dampings on the last tick of each stock period (countlast rows) | 382BD8 382BEE 382BF7 38336F 383385 38338A
# wp3a's beads (397C70)
stock | wp3a beads: +1110 counts the beads in state 1 this tick (397B70 zeroes it every tick) | 397EDE
stock | wp3a bead, homing (state 3): the rate +1938 is set to 18 as the state starts (398116) and += 0.8 is capped at 18: always 18 | 398141
fixed | wp3a bead: the position's stores after the scaled step (pre/srcx rows) | 3981CE 3981D7 3981EA 39843A 398450 39846B 3986B3 3986C9 3986E4
once | wp3a bead, hit (state 4): the bounce v.x, v.z x -0.8 and v.y = 6, once as the state starts | 398366 39838D
fixed | wp3a bead: the dampings on the last tick of each stock period (countlast rows) | 398493 3984AA 3984B3
# wp3a's bead kinds 2 and 3 (398920, 399590)
stock | wp3a beads: +1110 counts the beads in state 1 this tick (397B70 zeroes it every tick) | 398BBD 39982D
fixed | wp3a bead kinds 2, 3: the speed +1938 += 20 (lin 398D3D, 3999AD) | 398D4C 3999BC
fixed | wp3a bead kinds 2, 3: the position's stores after the scaled step (pre/srcx rows) | 398DE1 398DEA 398DFF 39909E 3990B4 3990CF 3992DD 3992F5 399310 399A51 399A5A 399A6F 399CD7 399CED 399D08 399F16 399F2E 399F49
once | wp3a bead kinds 2, 3, hit (state 4): the bounce v.x, v.z x -0.1 and v.y = 6, once as the state starts | 398FCD 398FF4 399C06 399C2D
fixed | wp3a bead kinds 2, 3: the dampings on the last tick of each stock period (countlast rows) | 3990F7 39910E 399117 399D30 399D47 399D50
# pl00's attack lunge (3B8540)
stock | pl00 lunge (3B8540): +B8 x the port's mode table 7A8240 (0.6 at 30), which mode_constants.h sets for the rate | 3B85BB
once | pl00 lunge (3B8540): a turn toward the locked-on target by at most 60 degrees (2DDF90) as an attack starts | 3B86A5 3B8B2C 3B9074 3B9258 3B9552 3B9709
once | pl00 lunge (3B8540): +E10 x 0.5 on the tick an attack connects (3A9390) | 3B8F47
fixed | pl00 lunge (3B8540): +E48 x 0.75 on the last tick of each stock period (countlast 3B8FA3) | 3B8FB3
stock | pl00 lunge (3B8540): the root-motion step +EC0..+EC8, which the motion advance rewrites every tick at this rate, zeroed (+F90 bit 7) or halved on a moving platform before 2DA3D0 applies it; +EC8 += +E48, a per-tick-at-this-rate speed | 3B988A 3B989F 3B98A7 3B98F2 3B9906 3B990E
# the 3AEE80 twins of 3AFA90's sites (two decompile heads for one state)
fixed | the same instruction is 3AFA90's too (the decompile gives it two heads), where lea_timers/memory_timers/action_timers/phase_steps cover it | 3AFDA2 3AFEDF 3B0082 3B008C 3B012D 3B01E8 3B02AF 3B02EE 3B036A 3B04B7 3B04C1
once | pl00 state 3AFA90, sub-state 0: a counter in B205C8 (+0x40) bumped once as the state starts | 3AFD95
fixed | pl00 state 3AFA90, sub-state 2: +E3E's count on stock ticks (count 3AFEAD, notyet on its two sound ticks) | 3AFEAD
# wp1c (38F400)
once | wp1c (38F400), sub-state 0: the throw (direction x the owner's speed, the slope push, 0.2 of the last move, the rise), once, then sub-state 1 | 38F5EA 38F5F2 38F5FA 38F602 38F630 38F638 38F674 38F6AE 38F6C0 38F6D0
fixed | wp1c rolling: the slope push s^2 (lin 38F438, pre 38F714/38F71C) | 38F724 38F72C
# wp1d (391D60)
fixed | wp1d (391D60): its steps by the slow-motion factor xmm7, scaled at the copy (dst 391DD3) | 391FE4 392041 392067 392084 3920A2 3920F3 392157 3921CF 3921E4 39225D 3922CB
stock | wp1d (391D60): 2DA510 (FixTurnRate converts k at its entry for every caller) | 3923F3
