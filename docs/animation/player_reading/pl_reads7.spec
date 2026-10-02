# pl00 linked attack (3B9A70)
stock | pl00 linked attack: +B8 damping uses mode table 7A8240, rewritten for this rate by mode_constants.h | 3B9AEB
fixed | pl00 linked attack: +11E9 cooldown loses one only on stock ticks (count 3B9B95) | 3B9B95
once | pl00 linked attack: the connected hit adds the input-built +11EA to +11E9 and increments the hit count +11EB; these happen per successful collision | 3B9BEF 3B9C13
once | pl00 linked attack: the 0.279253-radian turn toward the target happens after 3BBC90 reports a connected hit, the same event that adds +11EA to the cooldown and increments +11EB | 3B9CCF
once | pl00 linked attack: the pad's press bits B6B0D0/A0 add 3 or 2 to +11EA per press; this is part of the hit cooldown built from inputs, not an elapsed-tick count | 3B9D51 3B9E7D
fixed | pl00 linked attack: her +F48 loses s of 1 per tick through srcx 3B9DFD while in the target-speed window | 3B9E01
fixed | pl00 linked attack: the partner's +F48 loses s of 2 per tick through lin 3B9E98 | 3B9EA0
fixed | pl00 linked attack: +E3C's countdown is paced by count 3BB677 and its zero-time effect check by notyet 3BB625 | 3BB677
