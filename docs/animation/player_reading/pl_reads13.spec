once | wp1b (38E8D0), launch: the owner-speed-derived direction initializes +E10/+E18 and is accumulated into +E20/+E28 once; owner +E48 already carries this rate's per-tick scale | 38EA9A 38EAAA 38EABA 38EAC2
fixed | wp1b (38E8D0), launch: grounded slope contributes s of +FE0/+FE8 through srcx 38EAD0/38EAD8 | 38EAE0 38EAE8
once | wp1b (38E8D0), launch: +E54 is assembled once from the launch direction, owner rise and existing rise | 38EB20
once | wp1b (38E8D0), launch: the vector returned by the same 671248 helper used in wp1c is the last move, already per-rate; 0.2 of it is accumulated once into +E20/+E28 | 38EB44 38EB62
fixed | wp1b (38E8D0), flight: grounded slope changes the per-tick-at-this-rate +E20/+E28 velocity by s^2 through dst/pre pairs | 38EBAE 38EBB6
stock | wp1b (38E8D0), flight: position gains +E20/+E28 directly; those velocities are already per tick at the current rate | 38EBD2 38EBEA
fixed | wp1b (38E8D0), flight: +E20/+E28 damping is already 0.97^s through decay_factors.h | 38EC17 38EC26
fixed | pl02 (3A2C70), states 5 and 9: all three position coordinates use +E10 as a repeated approach factor converted by srcblend | 3A2FF1 3A3013 3A3036 3A3330 3A3352 3A3375
stock | pl02 (3A2C70): y += 40 before each 45FC40 ground query and y -= 40 immediately after; these are temporary query offsets with no elapsed-time meaning | 3A30AA 3A30C4 3A31EB 3A3205 3A33B7 3A33D1
once | wp11 (38C430), state 0: +7 biases the launch direction before normalization, the normalized vector is multiplied by 8 into +E10/+E14/+E18, and +E36 advances once | 38C4C9 38C4F7 38C50B 38C513 38C527
fixed | wp11 (38C430): lower +E3C counts the 30-tick interval on stock ticks through count 38C553; the intervening +E54 zero store may harmlessly repeat | 38C553
fixed | wp11 (38C430), flight: position gains s of persistent stock-valued +E10/+E14/+E18 via pre 38C613/38C634/38C64D | 38C621 38C639 38C652
stock | pl00 attack combo (3B7320): +B8 is multiplied by port mode table 7A8240, already rewritten for the current mode | 3B7379
once | pl00 attack combo (3B7320): state-start target turns occur once; the pi turn also clears its 0x400 trigger bit in the same invocation | 3B7552 3B75A6 3B7E56 3B8134
left | pl00 attack combo (3B7320), state 0: +E48 is per-current-rate but the code computes min(+E48 + 2, 3); scaling only the +2 leaves the compare and immediate cap at unscaled 3, while keeping +E48 stock-valued locally cannot be proven correct for a low nonzero per-rate entry value. This needs a compound/new immediate-cap form equivalent to min(E48/s + 2, 3) * s | 3B75CF
fixed | pl00 attack combo (3B7320), states 7 and 9: only the continuous 0.279253-radian 2DDF90 calls have their limit scaled at their call sites | 3B7EC7 3B81EC
stock | pl00 attack combo (3B7320): fresh root-motion +EC8/+EC0 x 0.2 is per-current-step shaping, and +E48 already carries the current-rate displacement when added to +EC8 | 3B8482 3B84A2 3B84BD
fixed | pl00 attack combo (3B7320): conditional +E48 factors 0.5 and 0.1 are committed once per stock tick by count rows | 3B849A 3B84E3
fixed | pl02 (3A4480): +2110/+2114/+2118 use the shared 0.05 approach factor converted at blend 3A4676 | 3A46B9 3A46D9 3A46F5
fixed | pl02 (3A4480): horizontal position gains s of direction times +2108, while +2108 gains 2 on the last tick after the period's moves | 3A4741 3A475F 3A477D
stock | pl02 (3A4480): y += 40 before 45FC40 and -= 40 immediately after; this is a temporary ground-query offset | 3A48B4 3A48CE
fixed | pl02 (3A4480): vertical ground following converts branch factors 0.6 and 0.1 with blend rows | 3A494D
