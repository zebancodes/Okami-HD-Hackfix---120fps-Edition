stock | pl00 state helpers 3B71B0/3B5B50/3BE480: +B8 damping is selected by the current mode-byte lookup of the port's 7A8240 table, which mode_constants.h already rewrites for the current rate | 3B72B4 3B5B80 3BE838
once | pl00 3B5D40: +B4 heading is changed toward +1110 only on a successful input-event query at 3B5DFA, immediately followed by setting +10E0 bit 0x400; the ordinary update path bypasses it | 3B5E40
once | pl00 3B5710: +1145 is a discrete input-command counter gated by sampled 0x80000000 event flags and action state 2..7, not an elapsed-time clock | 3B580A
fixed | pl00 3BEB40: +E48 approaches the held +E18 speed with the 0.2 gap factor transformed at 3BEC87 into its current-rate equivalent | 3BEC93
left | pl00 collision/attack helper 3BBC90: successful 2DC7B0 contact at 3BBD7C multiplies persistent +E48 by 0.7 at 3BBE4D; its cadence under sustained contact is unclear, and the factor is not covered by the port's mode table, so do not assume either one-shot or per-update scaling yet | 3BBE55
stock | pl00 state 3C0DA0: +B8 damping uses the port's current-rate mode table 7A8240 through the mode-byte lookup | 3C0E04
once | pl00 states 3C11F0 and 3C3470: both +B4 heading stores belong to state-0 initialization; each changes +E36 to 1 immediately beforehand and no ordinary state-1 update repeats the turn | 3C12D4 3C355E
once | pl00 state 3C13F0: +B4 heading store occurs only after the state-0 target-contact query succeeds and advances +E36 to 1; it is a contact acquisition turn, not a per-update rotation | 3C1690
fixed | pl00 state 3C38C0: +E48 approaches held +E18 with its 0.2 gap factor rate-converted at 3C39FA | 3C3A06
