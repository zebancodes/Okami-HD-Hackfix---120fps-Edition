# 2026-10-01 evening: rows of a875edd1 taken out after two play sessions
# (slow splash and title, slow loads, and both quits hung): double pacing
# and spin waits.

# The loader's bookkeeping, paced in a875edd1 and taken out. Each is a delay or
# barrier counted in updates; at 120 it only shortens loads. Pacing it on the
# frame counter's phase hangs any loop that waits for it inside one tick:
# 4B69A0 (the exit) spins `while (B661D8) 494120()`, 4B5CD0 (a scene load)
# `while (B661D8) 493E20()`, 1BFB80 `do 1C81F0 while (!493640())`, 1AF620
# `while (1AF560) 1AFB40`, 4110F0 `while (!432A70)`. Both 10-01 sessions hung
# on quit in 494120 (49DCFE at 291,670 passes a tick, then no ticks).
stock | Resource barriers 210580 and 210640 and the resource manager's stability barrier 3132C0: consecutive idle updates before the loader reports idle; latency, not motion, and polled by the load and exit spins (493640, 493E20, 494120) inside one tick | 2105D8 2106B1 31331B
stock | Resource manager 49DC70's five-update readiness delay, a resource instance's 90-update timeout (49DD20) and the 30-update retry delays (49DE70, 49E090), the resource record's eight-update retry cooldown (313710): loader latency; the exit spin 4B69A0 hung on 49DD00 | 49DD00 49DD33 49DE86 49E0A6 313731
stock | Spawn manager 210870's retry cooldown, under the resource update 210000 that both scene spins call: latency | 210BB9
stock | Scene teardown 494120's two empty update barriers (B661D1 cases three and four): the exit spin 4B69A0 runs 494120 until B661D8 clears, inside one tick | 49430B
stock | Stream loader 1B0210's read-error retry delay and 1B0670's wait before it proceeds: polled by 1AF620's spin `while (1AF560) 1AFB40` | 1B033B 1B06E3
stock | Menu resource shutdown 432A70's +34 countdown: 4110F0 spins `while (!432A70())` on it | 432A87
stock | 23C420, the battle list's sound-bank sequencer (polls 4484F0's slots after its +1C waits), under 23D700 and 23B9F0, which both scene spins call: load latency | 23D0AD 23D1D1 23D293 23D2C7 23D446
stock | Movie volume fade 4BE300: reached from 4A3F10, the movie idle test both scene spins wait on (4A3F10 -> 4A38E0 -> 4BE300) | 4BE6DB 4BE6E3
stock | 4486D0 deferred cleanup (+C98 delay) in the scene path 4BA500 -> 4934D0 -> 492B40: resource release latency | 44870C

# Double compensation: the length is already scaled to real time by another
# family, so pacing the counter too made it N times its stock time.
follows | 3E2B60 screen colour fade (68 callers: logos, title, every load's fade out and in): its length +C is (1 << flag) x n x N already (3E2ACE, flag group), so +E stepping once a tick reaches it in stock time; pacing +E as well made every fade 4x long (the 18:06 boot reached the title at 91 s, stock 27 s, a0a27259 29 s) | 3E2C38
stock | UI element helpers 1B2530/1B26E0/1B2840/1B2940: each counter runs to a track length from 1B8C20/1B8C50/1B8C80/1B8CB0, which mode_multipliers.h makes x4 at 120 and x2 at 60, so a count a tick is real time; pacing the counters as well ran every HUD, menu and title layout track 4x long (since 09-26) | 1B2587 1B2736 1B2897 1B2997
stock | cOptionScreenSetting +B0: its length is stored x N (flag mulstore 14C5F8 and its nine siblings), so the per-tick countdown is real time; pacing it as well made the input lockout 2 s instead of 0.5 | 14C46C
follows | 13A7D0's +4 window: its per-tick caller 3F25F0 already calls it once a stock tick (skip callgate 3F2635); the other path, 4A0900 in task loops task_waits.h runs once a stock tick at a fixed phase (4BB1C0), would count on every pass or on none | 13A8D3

# Gates taken out, their functions back to a0a27259's (unpaced, 4x fast at 120)
# until they get rows that do not also gate a callee another family scales.
left | 1C8D80 HUD number transition: its ten-step +48 slide runs 4x fast at 120. The gatefn also gated the layout update 1B54E0 it calls, whose tracks mode_multipliers.h already scales (4x slow); a count on the +48 store does not fit (1C8DC5 and 1C8DC8 are both branch targets) | 1C8DC5
left | cCarryObj 33DE40 floating physics runs per tick (4x fast at 120). The gatefn also gated 4B9B70, which tail-jumps into the motion advance 4B9C80 whose step mode_constants.h scales (its animation 4x slow); needs rows on its own fields | 33DF15 33DF34 33DF49
left | vtca 375FF0's phase duration runs per tick (4x fast at 120). Its gatefn also gated 375C40 -> 4B9B70 -> the motion advance 4B9C80 (animation 4x slow); needs a count on its own counter | 37613B 376141
left | Event camera 4763F0's +290 transition count runs per tick (4x fast at 120). 4A0900's task loops (task_waits.h 4BB1C0) call 4763F0 once a stock tick at a fixed phase, where a count gated on the frame counter's phase counts every pass or never | 476808
