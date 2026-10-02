stock | utb7 state 1 (570890): x/y/z set to each newly computed target by x += (target - x), a snap rather than a fractional approach or per-tick speed | 570BB0 570BCA 570BE5
stock | utb7 state 3: x/y/z again snap to the fresh target by x += (target - x); the animation transition is handled by 4B9C80 | 570D9D 570DB7 570DD2
stock | utb7 state 5: x/y/z snap to the computed target; the height target's separate +E18 rise is scaled at 570FEC and its ramp held at 570FF0 | 571012 57102C 571047
once | utb7 state 6 adds 60 to position y only on entry, then sets state 7 and falls through; subsequent updates run state 7 or later | 5710F3
