stock | pl00 sub-handler 3B1560: +E48 damping uses port mode tables 7A8160 and, for equipment kind 0F, 7A8170; both tables are already rewritten as k^s by mode_constants.h | 3B175B 3B177C
fixed | pl00 sub-handler 3B1560: +10B0/+10B8 receive s of the ground-vector acceleration and contribute s of their stock-valued velocity to position; their later 0.9^s decay remains covered by decay_factors.h | 3B185B
stock | pl00 state 0 (3B18D0), equipment kind 8: +E48 damping uses port mode table 7A8238, already rewritten as k^s by mode_constants.h | 3B208E
fixed | pl00 state 0 (3B18D0), other equipment kinds: +E48 damping uses rewritten mode table 7A8238, and its current-rate displacement is compared against the s-scaled 0.05 cutoff loaded at lin 3B210A | 3B212B
fixed | pl00 state 0 (3B18D0): +10B0/+10B8 receive s of the ground-vector acceleration and contribute s of their stock-valued velocity to position; their later 0.9^s decay remains covered by decay_factors.h | 3B2292
stock | pl00 state 1 (3B2620): +B8 damping uses port mode table 7A8240, already rewritten as k^s by mode_constants.h | 3B2824
stock | pl00 state 1 (3B2620), equipment kind 8: +E48 damping uses port mode table 7A8238, already rewritten as k^s by mode_constants.h | 3B296F
fixed | pl00 state 1 (3B2620): +10B0/+10B8 receive s of the ground-vector acceleration and contribute s of their stock-valued velocity to position; their later 0.9^s decay remains covered by decay_factors.h | 3B2A7F
stock | pl00 state 21 (3C0340): +B8 damping uses port mode table 7A8240, already rewritten as k^s by mode_constants.h | 3C037A
stock | pl00 state 21 (3C0340): the area-specific branch deliberately zeroes the freshly generated +EC0/+EC4/+EC8 root-motion step before the conditional 2DA3D0 application; multiplying a current-rate spatial step by zero needs no cadence conversion | 3C048C 3C04A0 3C04A8
