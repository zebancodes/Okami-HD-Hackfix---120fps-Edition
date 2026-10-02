fixed | cCockBattleResult 3F8740: both the +194 result transition wait and +198 post-result wait now change on stock ticks | 3F877A 3F896C
fixed | cCockGameOver 3FD0E0: +7E counts up to 30 only on stock ticks before changing the game-over stage | 3FD0E6
once | cCockGameOver 3FD0E0: +61 advances only after the +7E counter exceeds 30 and this stage hands off to the next state | 3FD11C
fixed | cCockHappyPoint 3FDB40: its +168 tally and +16C remaining count advance together on stock ticks while +16C is positive | 3FDB53 3FDB5D
fixed | cCockLoading 4003D0: +39C and +70 advance only on stock ticks, retaining their respective limit checks | 4004F1 40059A
stock | cOption/cOptionEx 409070: +78 is a selected options row changed only by controller navigation action bits, with wrap against three rows | 409182 409192
