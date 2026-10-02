fixed | pl01 (3B2CF0): the mode-8 +E48 damping of 0.94 runs once at the start of each stock period through count 3B3318; other modes use the rewritten 7A81B8 table | 3B333F
fixed | pl01 (3B2CF0): global B6B2AC bit 30 is held through the UI/load operation, so the extra 0.4 +E48 damping runs on the first stock-period tick through count 3B3354 | 3B335C
stock | pl01 (3B2CF0): state 7 damps +E48 with mode table 7A8198, already rewritten for this rate | 3B36CB
once | pl01 (3B2CF0): state 9 multiplies +E48 by 0.4 only when +10E0 bit 0x10 triggers an immediate transition back to state 0 | 3B3990
fixed | pl01 (3B2CF0): the conditional +10B8 acceleration and x/z moves are s-scaled through pre 3B3B8B/3B3B93/3B3BAB/3B3BC2; subsequent 0.9 damping is already rewritten by decay_factors.h | 3B3B9B
