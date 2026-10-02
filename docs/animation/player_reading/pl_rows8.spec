group player
# --- pl00's linked attack state (3B9A70) ---
count 3B9B95 | pl00 linked attack: +11E9 is the per-tick cooldown that suppresses another hit effect; decrement once on each stock tick
srcx 3B9DFD | pl00 linked attack: when the partner's +F48 is in 10..14, her +F48 loses 1 each tick; scale this subtraction while xmm6 stays 1 for the threshold and later motion arguments
lin 3B9E98 | pl00 linked attack: the partner's +F48 loses 2 per tick while linked; scale the subtract literal
notyet 3BB625 notyet:3BB674 | pl00 linked attack, state 11: the +E3C zero-time effect check must wait for a stock tick while the countdown is held
count 3BB677 | pl00 linked attack, state 11: +E3C counts down from 5 once each stock tick
