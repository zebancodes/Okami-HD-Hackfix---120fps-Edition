# 2026-10-01, fourth batch
group objects
# 4AC680 (from 4AEB70): the environment's light and fog update
count 4AD0F3 | Environment 4AC680: pace the transition count +FB0 (while it runs, the light colours B699B0.. snap toward the new ones, 0.1 of the gap left a tick).
srcx 4AD324 | Environment 4AC680: the fade +FE0 loses 1/+FE4 a tick down to 0: scale the step.
# the camera
count 476805 (0x4767E9,0x476808,(0x4767E9,0x4767F0,0x4767F3,0x4767F9,0x476800,0x476803,0x476805),None) | Camera 4763F0: pace the transition count +290 (the view and field of view are blended by +290 / +292 each tick).
count 476FCC | Camera dispatcher 476B00: pace the count +41C of ticks the camera button is held (past 10, a long press).
# 54EDC0, a cutscene task: its walk-out loop at 54F880 waits by wait(1) at 54F92D, which task_waits.h leaves per tick (DATA_LEFT: the loop reaches the root motion's patched code)
count 54F932 reg | Cutscene task 54EDC0: pace the walk-out loop's 15 passes (r14), so the five actors walk (root motion x 2, at the current rate's share) and the objects fade for 15 stock ticks.
src 54F8FE | Cutscene task 54EDC0: in the same loop, the objects' +D2C fades by 0.1 a pass: scale the step.
# the map scripts' per-tick updates (their records' +18 in 7AD9B0)
count 574148 (0x574141,0x57414B,(0x574141,0x574144,0x574146,0x574148),None) | Map 207's script (573FE0, from 579220): pace the countdown 7A8CB0+8 to its event 0x260035.
count 58BCF8 (0x58BCF1,0x58BCFB,(0x58BCF1,0x58BCF4,0x58BCF6,0x58BCF8),None) | Map 20D's script (58BB90, from 58D800): pace the countdown 7A8CB0+8 to its event 0x2C0008.
src 634F92 | Map F08's script (634E90, from 634D30): B75140's +50 fades by 0.03 a tick, in doubles: scale the step.
src 634FDE | Map F08's script: B75140's +50 grows by 0.05 a tick, in doubles: scale the step.
