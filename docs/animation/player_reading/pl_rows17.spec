group player
# pl03 path following (3A51F0)
notyet 3A5525 notyet:3A5553 | pl03 (3A51F0, sub-state 1): the effect at every eighth +E3E tick must wait for a stock tick while the already-covered counter is held
notyet 3A5742 notyet:3A5770 | pl03 (3A51F0, sub-state 3): the effect at every eighth +E3E tick must wait for a stock tick while the already-covered counter is held
callscale 3A57A2 (0x2DDF90,"xmm3") | pl03 (3A51F0, sub-state 3): turn +B4 toward the selected model every tick with the xmm3 limit: s of the per-tick turn limit
srcblend 3A57E1 | pl03 (3A51F0, sub-state 3): position.x approaches the selected model by dynamic factor +E10 each tick: use 1-(1-k)^s while +E10 itself stays stock
srcblend 3A5812 | pl03 (3A51F0, sub-state 3): position.y approaches the selected model by dynamic factor +E10 each tick: use 1-(1-k)^s
srcblend 3A5845 | pl03 (3A51F0, sub-state 3): position.z approaches the selected model by dynamic factor +E10 each tick: use 1-(1-k)^s
lin 3A5937 | pl03 (3A51F0, sub-state 3): the dynamic approach factor +E10 grows by 0.02 a tick from 0.1 to 1: s of the step
callscale 3A5AC6 (0x2DDF90,"xmm3") | pl03 (3A51F0, sub-state 5): turn +B4 toward +2100's model position every tick with the xmm3 limit: s of the per-tick turn limit
# pl00 turn and charge (3C6080, 3C84B0)
lin 3C615C | pl00 (3C6080, sub-states 2/3): 2DE0A0's first continuous angular limit is 8 degrees a tick: pass s of the caller-local limit
lin 3C616C | pl00 (3C6080, sub-states 2/3): 2DE0A0's second continuous angular limit is 4 degrees a tick: pass s of the caller-local limit
lin 3C64F4 | pl00 (3C6080, sub-state 1): 2DE0A0's first continuous angular limit is 8 degrees a tick: pass s of the caller-local limit
lin 3C6504 | pl00 (3C6080, sub-state 1): 2DE0A0's second continuous angular limit is 4 degrees a tick: pass s of the caller-local limit
notyet 3C668F notyet:3C66C7 | pl00 (3C6080, sub-state 0): the transition at +11F0 = 10 must wait for a stock tick while the counter is held
count 3C66C9 | pl00 (3C6080, sub-state 0): +11F0 advances once per stock tick from 0 to 10 before entering sub-state 1
notyet 3C86CD notyet:3C8729 | pl00 (3C84B0): the effect on every eighth +1152 tick must wait for a stock tick while the charge counter is held
notyet 3C8729 notyet:3C876B | pl00 (3C84B0): the event at +1152 = 0 must not repeat between stock ticks
count 3C876B | pl00 (3C84B0): +1152 counts charging time once per stock tick; its thresholds choose the charge tier, sounds and effects
notyet 3C8788 notyet:3C87DC | pl00 (3C84B0): the first threshold's paired events must play only on the counter's stock tick
notyet 3C87F1 notyet:3C8845 | pl00 (3C84B0): the second threshold's paired events must play only on the counter's stock tick
notyet 3C8879 notyet:3C8F60 | pl00 (3C84B0): the repeated event every eight ticks above the full-charge threshold must wait for a stock tick
callscale 3C8FE1 (0x2DDF90,"xmm3") | pl00 (3C84B0): turn +B4 toward the current target every tick with the 32-degree xmm3 limit: s of the per-tick turn limit
