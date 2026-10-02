group player
# --- pl00's state 3C7880: charging while locked on to a target ---
lin 3C7A20 | pl00 state 3C7880, sub-state 1: turn toward the locked target by at most 8 degrees a tick; scale the limit before 2DDF90
lin 3C7E71 | pl00 state 3C7880, sub-state 3: turn toward the locked target by at most 2 degrees a tick; scale the limit before 2DDF90
notyet 3C7B0D notyet:3C7B7D | pl00 charge: the effect spawned at every eighth +1152 tick must wait for a stock tick while the counter is held
notyet 3C7B7D notyet:3C7BBE | pl00 charge: the sound at +1152 = 0 must not repeat between stock ticks
count 3C7BBE | pl00 charge: +1152 counts the ticks spent charging; its threshold changes the charge tier, sound and effect sequence
notyet 3C7BE5 notyet:3C7C39 | pl00 charge: the paired sounds near tick 30 or 15 must play once on the counter's stock tick
notyet 3C7C59 notyet:3C7CAD | pl00 charge: the paired sounds near tick 60 or 30 must play once on the counter's stock tick
notyet 3C7CF2 notyet:3C80B6 | pl00 charge: the repeated sound every eight ticks after the full-charge threshold must wait for a stock tick
