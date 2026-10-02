fixed | es11 2C06D0: the random 0.02 component and mutable 0.05 base step are both scaled before adding to +1084 | 2C0772
follows | es11 2C06D0: this store subtracts a whole unit only after the scaled +1084 phase crosses one | 2C079D
fixed | esf2 5BB320: the +1124 eight-tick cooldown write is skipped between stock ticks | 5BB382
once | es78 590130/5901C0: each +E36 increment follows a one-time play-motion call on state entry, then the branch tests the active motion's end | 590190 590219
fixed | esp27 1A9020: slot 1 adds matrix-transformed velocity to XYZ every tick; all six velocity products use scaled sources before the three stores | 1A9165 1A9194 1A919C
