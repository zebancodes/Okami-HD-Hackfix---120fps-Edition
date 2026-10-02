# 2026-10-01: the remaining unattributed candidates, first batch
group menu
# 4902F0 (called by 4900B0): a two-entry widget whose states 2 and 3 slide the page over 16 ticks
count 490394 | 4902F0 state 2: hold the slide's tick count +1 (0 to 15) between stock ticks; the page offset is recomputed from it each tick.
notyet 490397 notyet:49061F | 4902F0 state 2: the end test reads the old count (dl); between stock ticks take the not-yet path, so the slide ends on its stock tick.
count 49041C | 4902F0 state 3: hold the opposite slide's tick count +1 between stock ticks.
notyet 49041F notyet:49061F | 4902F0 state 3: the same end test on the old count.
# 600190 (called by 600040): a menu whose unselected entries shrink back
root 600647 | 600190: the unselected entries' scales +2C/+30 shrink by 0.98 a tick down to their base (the max with it): take the factor's N-th root.
group actor
# 5CBAD0 (called by nine state handlers 5C8160..5CB850): the swimmer's approach and its speed
count 5CBDF2 | 5CBAD0: hold the 40-tick countdown +3417 (rearmed while the player is beyond 400 or +D40 bit 3 is set) between stock ticks; each tick it is nonzero, 5CDBA0 turns the heading toward +1340.
blend 5CBDDE | 5CBAD0: 5CDBA0's heading approach toward +1340 by 0.15 a tick.
root 5CBE8E | 5CBAD0: the speed +343C damps by 0.98 + 0.02 sin^2 of its clock phase (a factor in [0.98, 1]) a tick: take the factor's N-th root.
root 5CBF2E | 5CBAD0 (+340C set): the same damping.
srcblend 5CBFA9 | 5CBAD0: the heading +B4 approaches the bearing to +1340 by xmm7 (0.035 or 0.055, times 0.7 to 1.5 by the player's distance) a tick.
dst 5CBFB6 scale:5CBFD0 | 5CBAD0: the forward move (0, 0, 50 x +343C), times the speed +1080 and +F54, goes to 2DA3F0: scale the speed as read.
