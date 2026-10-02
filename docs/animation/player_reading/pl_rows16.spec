group player
# pl02 steering (3A3550) and target follow (3A3CA0)
ulast 3A373B | pl02 (3A3550, first steering path): xmm0 = the 0.95 damping applied to all three persistent velocity lanes after their acceleration; keep 1 between stock ticks and apply 0.95 on the last tick
pre 3A3771 | pl02 (3A3550, first steering path): persistent velocity +E20 gains this tick's x acceleration: add s of the acceleration
pre 3A377A | pl02 (3A3550, first steering path): persistent velocity +E24 gains this tick's y acceleration: add s of the acceleration
pre 3A3787 | pl02 (3A3550, first steering path): persistent velocity +E28 gains this tick's z acceleration: add s of the acceleration
scaledadd 3A37AF | pl02 (3A3550, first steering path): position += persistent velocity +E20/+E24/+E28 each tick; add s of the vector while its value stays stock
ulast 3A3921 | pl02 (3A3550, second steering path): xmm0 = the 0.95 damping applied to all three persistent velocity lanes after their acceleration; keep 1 between stock ticks and apply 0.95 on the last tick
pre 3A3957 | pl02 (3A3550, second steering path): persistent velocity +E20 gains this tick's x acceleration: add s of the acceleration
pre 3A3960 | pl02 (3A3550, second steering path): persistent velocity +E24 gains this tick's y acceleration: add s of the acceleration
pre 3A396D | pl02 (3A3550, second steering path): persistent velocity +E28 gains this tick's z acceleration: add s of the acceleration
scaledadd 3A3995 | pl02 (3A3550, second steering path): position += persistent velocity +E20/+E24/+E28 each tick; add s of the vector while its value stays stock
callscale 3A4179 (0x2DDF90,"xmm3") | pl02 (3A3CA0, sub-states 2/3): turn +B4 toward the selected model every tick with the xmm3 limit: s of the per-tick turn limit
srcblend 3A41B8 | pl02 (3A3CA0, sub-state 3): position.x approaches the selected model by dynamic factor +E10 each tick: use 1-(1-k)^s while +E10 itself stays stock
srcblend 3A41E9 | pl02 (3A3CA0, sub-state 3): position.y approaches the selected model by dynamic factor +E10 each tick: use 1-(1-k)^s
srcblend 3A421C | pl02 (3A3CA0, sub-state 3): position.z approaches the selected model by dynamic factor +E10 each tick: use 1-(1-k)^s
callscale 3A440A (0x2DDF90,"xmm3") | pl02 (3A3CA0, sub-state 5): turn +B4 toward +2090's model position every tick with the xmm3 limit: s of the per-tick turn limit
