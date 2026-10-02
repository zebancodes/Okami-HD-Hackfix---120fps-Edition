# 2026-10-01, sixth batch (rows in un_rows45.spec)
once | Screen transition 48A920: B65E88 is cleared with the rest of the transition's state when it ends (mode 3, its last step). | 48AB1B
fixed | Screen transition 48AD20: the 6-tick count +1C is count row 48AD2C. | 48AD5B
once | 48DA90 (from 48ECA0): +8C drops once when its message closes (guarded by +157, set at once). | 48DAE0
fixed | 48DCE0: the approach of +EC by a third a tick is srcblend row 48DD9A. | 48DDA6
once | 48F3A0 (the menu pages 6097E0..60A220) shifts a layout element by 64 when the page is built. | 48F4E1
once | 490840 (from 4900F0): +31 changes once per accepted press. | 490978
stock | 4934D0 subtracts the real time elapsed since a stamp (OSGetTick/OSDiffTick) from B6C47C: wall-clock time, not ticks. | 493564
once | 49D0C0 sets a voice up: +28 is its starting level plus 0x50 when asked, once. | 49D1AB
once | 4A0900, the event sequencer's command step: +8 counts the commands it runs (its loops pass once a stock tick, task_waits.h). | 4A100F
once | 4A3AD0 (from 1ACD10, 3F1830, 6018A0) numbers a new entry from the count +10. | 4A3CAC
once | 4AA900, 4AADC0, 4AB000, 4AB0C0, 4AB160, 4AB260, 4AC090 (villager states from 3087E0..30E110): the sub-state +E36 advances once, after a motion starts, an effect is spawned or a check passes. | 4AA9D9 4AAE90 4AB095 4AB111 4AB1E8 4AB2F5 4AC119
fixed | Villager 4ABA90: the 15-degree turn a tick is lin row 4ABC08. | 4ABC15
once | 4B2F30 runs when the object 0xA25 is struck (498330, from 498AF0's hit test): B6B328+1B counts the hits to 10. | 4B2F8B
fixed | Map 103's script 4D2600: the double-precision fade of +D2C is src row 4D2644. | 4D2650
once | 4F3540 and 4F5540 (the +0 slots of event tables 7B53C0.., 7B4D48) count events in B6D778+24 and +21. | 4F3665 4F5698
