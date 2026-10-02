# 2026-10-01, second batch (rows in un_rows41.spec)
follows | 20EA30, the fall (y += dt x vy, vy -= g x dt; dt, its third argument, read nowhere else): every call scales dt. The enemies' calls load the speed +1080 under step rows (241405, 251519, 25A041, ... 5ECBA4); the weapons' slot-8 updates (37EC90 .. 3A2290, 23 calls) pass their slow-motion factor, scaled at the call by the callscale rows of un_rows41.spec. | 20EBFD 20EC50
once | 20EA30: vy x 0.1 when the ground query after the move finds a ceiling (a collision). | 20ED13
follows | 20E960 moves the position by the root-motion step +EC0..+EC8 (times the model scale, through the model's rotation), which the motion advance rewrites every tick at the current rate's share. | 20E9F1 20EA07 20EA1E
fixed | 243630, 243EE0, 2A1710, 2A1E90 (the imps' and their kin's knockback states, from 242060 and 29F500): the heading +B4 approaches its target through 2DA510, whose k the FixTurnRate hook converts at its entry for every caller. | 24375B 24388C 243A1A 243FB9 2440BE 2A17F9 2A193F 2A1A9E 2A1F76 2A2030
once | 287D70 (from 28DBE0, 28E120, 28FAA0, each right after playing a motion on a state's entry) rearms the timer +124C to 90 plus a random 30 (halved in one mode) and counts the rearms in +1248. | 287D98 287DB2 287DBA
fixed | 2A2B40's circling: the radius +13B4 and angle +13B0 steps are lin rows 2A2C14, 2A2C26, 2A2C43, 2A2C8F, 2A2C99. | 2A2C31 2A2C59 2A2CA1
once | 2B5D80 (from 2A8D20, 2AE060, 2ADB10, 2B1E50) arms a knockback: for kind 0x224 in mode 1 it scales the push vector by (0.6, 0.7, 0.6), then sets state 0x301 and copies it to +1590. | 2B5DE6 2B5DF7 2B5DFC
fixed | The shop panels' drop-in bounces are gatefn rows 43C010, 43F6B0, 442790 (each the tail-jump target of its panel update). | 43C02F 43C046 43C063 43F6CF 43F6E6 43F703 4427AF 4427C6 4427E3
fixed | The shop panel's exit 43E1B0: its x1.7 speed is countlast row 43E1D1 and its step srcx row 43E1E1. | 43E1E5 43E1F4
fixed | 472E80's camera drop: +290's steps are count rows 472F4F, 472F83, 472F90. | 472F4F 472F83 472F90
fixed | Camera mode 47FF90: its approaches are callblend rows 4803FC/480436 and its request durations count rows 480401/48043B. | 480408
fixed | The moving platforms: the 5-tick shakes +10A0 are count rows 489D93/489F8F, the move by the speed is pre/src rows 489E36/489E4E, and 0x82E's speed ramp and pause are lin rows 48A017/48A080 and count row 48A05B with notyet 48A061. | 489D93 489F8F 48A01F 48A05B 48A088
once | Platform state 489DD0: +10A4 advances once when the platform reaches an end of its travel (with a sound and the 10-tick wait +10A0). | 489EBE
fixed | 48DED0, the treasure fanfare, is gatefn row 48DED0: its count-up +8F, the fade of 18EB20's +1D0 and the collected count +E2 run at stock cadence. | 48E00D 48E07A 48E227
once | 4965D0 adds an amount to an item or resource count in the save data (B205C0), capped: called when something is collected or bought. | 496706 49671A 4967DD
