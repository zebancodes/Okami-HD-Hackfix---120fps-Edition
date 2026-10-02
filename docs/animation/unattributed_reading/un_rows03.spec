# 2026-09-30: map 312's script, the vt79E318 sub-state updates, the 23C420 sequencer
group actor
gatefn 5FB060 | Map 312's script update (the +18 field of its 7AD9B0 record, called only by 3F3A10's `call rcx`, which ignores rax): its 300-tick sequence +6D8/+6DC, the actor's rise (+6D4 -= 1.2, +6D0 += +6D4, y += +6D0), counters and sounds together at stock cadence.
count 23D0AA (0x23D09E,0x23D0AD,(0x23D09E,0x23D0A1,0x23D0A4,0x23D0A6,0x23D0AA),None,-1) | 23C420 sequencer: pace the positive wait +1C (decremented by setg's 0 or 1) before its poll of 4484F0.
count 23D1D1 | 23C420 sequencer: hold the wait +1C between stock ticks; the following test reads the old ECX.
count 23D293 | 23C420 sequencer: hold the 30-tick wait +1C; the following test reads the old ECX.
count 23D2C7 | 23C420 sequencer: hold the wait +1C; the following test reads the old ECX.
count 23D446 | 23C420 sequencer: hold the wait +1C; the following test reads the old ECX.
group objects
count 21F4CA | vt79E318 sub-state 1: pace the 10-tick wait +13F0.
count 21F5B9 | vt79E318 sub-state 3: pace the 20-tick (then 5 to 36) wait +13F0.
lin 21F65B | vt79E318 sub-state 3: +D2C loses 0.05 a tick while the wait runs.
count 21F66D | vt79E318 sub-state 4: pace the wait +13F0.
count 21F85A | vt79E318 slot 5 copy, sub-state 1: pace the 10-tick wait +13F0.
count 21F905 | vt79E318 slot 5 copy, sub-state 3: pace the wait +13F0.
lin 21F96B | vt79E318 slot 5 copy, sub-state 3: +D2C loses 0.05 a tick.
count 21F97D | vt79E318 slot 5 copy, sub-state 4: pace the wait +13F0.
