group player
count 459DA1 | pl00 3C1830 calls this selected-subactor updater on held input every update (372 of 372 traced ticks); the selected actor's +E3E animation count gains state-derived 2 or 6 once per stock tick
count 459DBE | pl00 selected-subactor updater 459D90: the same actor's +E3C animation phase gains 20 times the state-derived step once per stock tick, before its 0x384 cap

# Pl00 linked-actor state 3D1330.
count 3D13F4 | pl00 state 3D1330: while held input bitset B6B0D0 or its companion global is active and +E3C exceeds 5, commit the conditional two-count decrease on stock ticks
notyet 3D145C notyet:3D148C | pl00 state 3D1330: when +E3C is held at zero between stock ticks, defer its cleanup/transition until the next stock tick
count 3D1492 | pl00 state 3D1330: commit the ordinary one-count +E3C decrease on stock ticks after the zero test
