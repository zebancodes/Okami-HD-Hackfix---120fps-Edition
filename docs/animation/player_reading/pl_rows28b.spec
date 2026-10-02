group player
# pl03 every-eighth-tick sound (3A4DF0)
count 3A4EE4 | pl03 (3A4DF0): commit +2250's increment once per stock tick; cl keeps the old count for the following modulo-eight event test
notyet 3A4EEA notyet:3A4F14 | pl03 (3A4DF0): on held ticks still apply `and cl, 7`, then force its jne down the no-sound path so sound 0x40B fires only on stock ticks
