fixed | UI event iterator 3EC840: +F8 waits while the conditional event is active and is now decremented on stock ticks | 3ECA47
fixed | UI event manager 3F3A10: +340 is an active wait decremented on stock ticks | 3F3B19
stock | cCockBattleResult 3F69F0: +168 is a sum of result entries traversed in this call, using each entry's score once during tally recomputation | 3F6B62
fixed | cCockBattleResult 3F9800: the +198 result wait now decrements on stock ticks in this input branch | 3F98AE
once | cCockFudeWnd 3FCB00: +61 advances its stage after initializing the new popup and its sound, then this stage cannot execute again | 3FCBDC
fixed | cCockGameOver 3FD160: the +7C repeating flash wait now decrements on stock ticks | 3FD1C4
once | cCockGetItemInfo 3FD6F0: +C8 is the number of occupied reward slots and decreases only when this call removes one entry | 3FD753
fixed | cCockHappyPoint 3FE1C0: the +68 reward delay now decrements on stock ticks; its later helper 3FDB40 is separately gated for the tally update | 3FE1F0
