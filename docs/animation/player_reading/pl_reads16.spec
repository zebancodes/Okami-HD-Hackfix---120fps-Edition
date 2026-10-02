once | wp09 (3875B0), launch: the target offset (+7 y), normalized direction x 6.5 stored in +E10/+E14/+E18, and +0.5 y placement happen once as sub-state 0 advances to 1 | 387685 3876B2 3876C6 3876CE 3876E3
fixed | wp09 (3875B0), sub-state 1: position gains s of persistent launch velocity +E10/+E14/+E18 through pre 387802/387823/38783C | 387810 387828 387841
once | wp0d (388B50), sub-state 0: +B0/+B4 take the initial target-relative orientation once before +E36 advances to 1 | 388C5C 388C78
fixed | wp0d (388B50): the +E3C colour-wave phase advances once per stock tick through count 388D63 | 388D63
stock | wp0d (388B50): the +B0/+B4 approaches use 2DA510, whose FixTurnRate entry converts their 0.2 coefficient for the current rate | 388E1F 388E43 388F15 388F48
stock | wp0d (388B50): the owner transform is copied fresh at 388F99, then position.y gains the fixed 10-unit placement offset rather than accumulating motion | 388FBE
stock | wp30 (397050): +1C64 is replaced with the current target heading at the end of every update, so the next heading difference is already a per-update delta; 0.4 and 0.2 only distribute that delta across the two joints | 3970ED 39719D
fixed | wp30 (397050), two-joint spring: pull, angular move, and post-move damping are rate-corrected by dst/srcx/countlast at 39710A/397140/397158 and 3971BA/3971ED/397205 | 397120 397148 397160 3971D0 3971F5 39720D
stock | pl00 jump (3B3FF0): the +B4 stores are results of 2DA510 with coefficient 1, a snap that FixTurnRate correctly leaves at 1 | 3B4544 3B46E7
once | pl00 jump (3B3FF0), sub-state 2: variant 30 adds launch +E14 to +E54 once (other variants assign +E54), then +E36 advances immediately to 3 | 3B47D7
once | pl00 jump (3B3FF0): +1145 increments only on a successful collision/input gate while below 2 and simultaneously requests state 0x301; it is an event count, not elapsed time | 3B48F5 3B4CB4 3B4EE8 3B50BE
stock | pl00 jump (3B3FF0): +E48 damping reads mode table 7A81B8, rewritten by mode_constants.h for the current rate | 3B54E2
stock | pl00 state 2C (3C2430): +B8 uses mode table 7A8240 and +E48/+10E8 use mode table 7A81B8, both rewritten by mode_constants.h for the current rate | 3C249A 3C28AA 3C28D0
fixed | pl00 state 2C (3C2430): +10E8 is a per-tick displacement at the current rate through the existing stick-drift gain fix at 3C2913; rotating it and adding it directly to the transform needs no second scale | 3C2992 3C29BD
fixed | pl00 state 2C (3C2430): the conditional rotated two-unit forward push is scaled at pre 3C2A38/3C2A4C/3C2A62 | 3C2A3C 3C2A51 3C2A67
