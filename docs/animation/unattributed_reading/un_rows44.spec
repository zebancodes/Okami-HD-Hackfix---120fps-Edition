# 2026-10-01, fifth batch
group objects
countlast 36E425 | 36E060 (scenery tilting under the brush's wind technique): once the wind stops, its tilt +1114 decays x0.7 a tick: only on the last tick of each stock period.
count 1D2478 | 1D2130 (from 1D2060): pace the 45-tick count +1C while state +57 is 1.
count 1B033B | Stream loader 1B0210: pace the 30-tick retry delay +70 after a read error.
count 1B06E1 (0x1B06DA,0x1B06E3,(0x1B06DA,0x1B06DD,0x1B06DF,0x1B06E1),None) | Stream loader 1B0670: pace the wait +70 before it proceeds.
callscale 32EFAC | 32EF40, sub-state 1 (20 ticks): turns toward B66380 by at most 10 degrees a tick through 20E030.
gatefn 281470 | The twin enemy's orbit 281470 (from its state handlers 27C240..280610): the shared orbit angle 9C4780 (+0.01 or +0.005 a tick), the circle offsets from the distance, and the approach of the position to its circle point by param_2^2 a tick, together at stock cadence.
group actor
lin 205505 | Animal 205310's knockback slide on the ground: x += +E10 x 0.4 a tick (+E10 damps x0.97, a decay_factors row).
lin 205524 | Animal 205310's slide on the ground: z += +E18 x 0.4 a tick.
src 205537 | Animal 205310's slide in the air: x += +E10 a tick.
src 20554F | Animal 205310's slide in the air: z += +E18 a tick.
callscale 1ED84D | Animal 1ED4C0: within 10 of its target it turns by at most 3 degrees a tick through 20E030 (the 20E210 path beside it is the turn group's).
callscale 1EF0DA | Animal 1EEF50: the same turn through 20E030.
callscale 1EF2B8 | Animal 1EF120: the same turn through 20E030.
count 2432A5 | Imp state 243180 (from 242060): pace the countdown +E3C.
group player
count 165F87 (0x165F6C,0x165F8A,(0x165F6C,0x165F70,0x165F73,0x165F87),None) | Brush 165BD0 (from the brush update 16C7E0): pace the countdown +60 (reloaded by 1695D0 when it runs out).
group objects
count 313A80 (0x313A72,0x313A83,(0x313A72,0x313A76,0x313A79,0x313A7B,0x313A80),None) | 3135B0's state 1 (313A60, from the main tick through 3134A0): pace the delay +40 before its check.
count 467D23 | 467CA0 (from the main tick): pace its countdown byte while +1 is set.
notyet 467D25 notyet:467D6B | 467CA0: the end test reads the old count (cl); between stock ticks take the not-yet path.
srcblend 469BE8 | Camera mode 4697B0: z approaches its target by +260 a tick (an approach that speeds up: +260 grows 0.01 a tick to 0.3).
lin 469BEC | Camera mode 4697B0: the approach factor +260 grows by 0.01 a tick.
srcblend 46BF18 | Camera mode 46BCD0: z approaches its target by +260 a tick.
lin 46BF1C | Camera mode 46BCD0: +260 grows by 0.01 a tick up to 0.3.
srcblend 46C792 | Camera mode 46C370: z approaches its target by +260 a tick.
lin 46C796 | Camera mode 46C370: +260 grows by 0.01 a tick.
count 4761B1 | Camera 4760E0 (from 476B00): pace the count +47C of ticks the camera button is held (past 10, a long press).
group actor
count 2A1073 | 2A0F40 sub-state 3: pace the 150-tick countdown +13BA.
group human
count 3179BA (0x3179AC,0x3179BD,(0x3179AC,0x3179B0,0x3179B3,0x3179B5,0x3179BA),None) | Villager 317870 (from 317020, cHuman's update 305840): pace the countdown +14.
group player
callblend 39F848 | Weapon aim 39F770 (from 39E790, 39EAC0, 39EE30): the pitch +B0 approaches the angle to the player by 0.15 a tick within a limit of the slow-motion factor x the caller's rate.
callscale 39F86F | Weapon aim 39F770: the heading turns toward the player within the same limit.
