stock | wp06 (385A60): +E10/+E14/+E18 are refreshed as the normalized target direction times stock speed 9; keep that velocity stock-valued because its three position uses are scaled through pre 385B49/385B60/385B79 | 385B16 385B2A 385B32
fixed | wp06 (385A60): position gains s of persistent stock-valued +E10/+E14/+E18 through pre 385B49/385B60/385B79 | 385B4D 385B65 385B7E
stock | wp03 (383AB0), state 0: +E28 is initialized once to owner distance divided by 23, 22 or 30 as a stock-valued forward speed; callscale 383D1F scales it only when 2DA460 moves position | 383B87 383BC7 383C3E
fixed | wp03 (383AB0), state 1: +B0's continuous 15-degree spin step is scaled by lin 383D2C | 383D4F
fixed | wp03 (383AB0), state 4: +B0 commits its changing +E3C-degree spin once per stock tick through count 383ED6; count 383EDE and notyet 383EE5 pace the following countdown and terminal event | 383ED6
once | wp0d (388FD0), state 0: the target-relative +B0/+B4 orientation correction runs only while initialization advances immediately to state 1; keep the full one-shot correction | 3890C2 3890E0
fixed | wp0d (388FD0): +E3C's two sine-scale waveform phase counts advance once per stock tick through count 3891A2 | 3891A2
stock | wp0d (388FD0): both continuous +B0/+B4 approaches use 2DA510, whose FixTurnRate hook already converts the 0.2 factor | 3892A9 3892CD
fixed | wp04 (384BE0), state 3: +E37's optional three-tick post-motion wait is paced by count 384D06 and its old-value zero transition by notyet 384CFC | 384D06
follows | wp04 (384BE0): after motion advance refreshes root rotation, +B0/+B4/+B8 gain the full current-rate +EF0/+EF4/+EF8 rotation deltas | 384DB9 384DD6 384DF6
fixed | pl03 (3A4DF0): +D20/+D24/+D28 approach 1 with their shared rate-converted 0.05 factor from blend 3A4E3C | 3A4E60 3A4E88 3A4E98
left | pl03 (3A4DF0): +2250 counts stock ticks and plays sound 0x40B when the old count is divisible by eight; count 3A4EE4 alone would repeat the sound on held ticks because the old value is copied to cl before the store, and the following `and cl, 7` cannot yet use notyet. This needs an AND-capable notyet form (with count 3A4EE4 and notyet 3A4EEA -> 3A4F14) or an ignored-return call-site gate at 3A4F0F | 3A4EE4
once | pl00 (3CB300), state 3: +1155 increments only on the +E72 bit-12 event after +E36 is changed to state 6, so it cannot repeat on the next update | 3CB575
once | pl00 (3CB300), state 6: +E37 increments after +E36 has already advanced to state 7 at 3CB6A2 | 3CB908
once | pl00 (3CB300), state 7: +1155 increments only on the +E72 bit-12 event after +E36 is changed back to state 6 | 3CBA29
