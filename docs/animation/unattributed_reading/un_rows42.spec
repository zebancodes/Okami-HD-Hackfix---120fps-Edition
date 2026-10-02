# 2026-10-01, third batch
group menu
# 601170: the menu background shared by the screens 600040, 5FF5E0, 5FFF50, 601B70, 601CA0, 5FF790, 601D50
lin 6011AD | Menu background 601170: its alpha +8 gains 0.003 a tick up to the layout's maximum.
lin 6011ED | Menu background 601170: its offset +C loses 0.125 a tick down to -190.
lin 601223 | Menu background 601170: its angle +10 gains 0.0007 a tick (wrapped).
group objects
# 52EE10 (from 531F50), a map script's tick routine on the script manager 7A8CB0
count 52EE71 | Map script 52EE10: pace its tick count 7A8CB0+8 (event 0x1E0023 after 300) while the save flag +71C bit 1 holds.
count 52F042 (0x52F03B,0x52F045,(0x52F03B,0x52F03E,0x52F040,0x52F042),None) | Map script 52EE10: pace the countdown 7A8CB0+C to its event 0x1E0030.
# 13B250 (from 13B130, the event camera 48C280): a keyframed rumble
count 13B3A7 | Event camera rumble 13B250: pace its pulse accumulator +20 (+= the key's intensity each tick, a pulse on the other motor at each 255) to once a stock tick.
# 20E130 (obj, d): x, z += R(+B0) x (0, 0, d), a forward step
callscale 22FF46 | 22FE00 (from 22FDB0): its walk by the speed +11F4 a tick through 20E130.
callscale 307C57 | 307B90 (from 307B10): steps back 2 (or 1.5) a tick through 20E130.
callscale 307EE4 | 307B90: the same back step, its other state.
callscale 308408 | 308340 (from 307B10): steps back 2 (or 1.5) a tick through 20E130.
callscale 30854A | 308340: steps by xmm6 (-0.3 once +E3C passes 10) a tick through 20E130.
callscale 3086FA | 308340: steps back 2 (or 1.5) a tick, its other state.
# 21EBD0 and 21EF90: copies of vt79E318's sub-state updates 21F340/21F6D0 that no vtable, call or pointer names (their .rdata words are their own IP-to-state map entries); rows in them are harmless
blend 21ED91 | 21EBD0: +D2C fades toward 0 by 0.3 a tick.
count 21EDCC | 21EBD0: pace the wait +13F0 (+D2C re-flashes to 1 at 7 and 4).
blend 21F151 | 21EF90: +D2C fades toward 0 by 0.3 a tick.
count 21F18C | 21EF90: pace the wait +13F0.
