group player
# --- wp1a's launched piece (38D880, from 38DFF0) ---
count 38D8D8 | wp1a piece: the 90-tick wait in state 4, set as state 3 ends, counts down once each stock tick
pre 38D931 | wp1a piece in flight: x += v.x each tick; scale the old velocity in xmm0 for this move while keeping +C0 in stock units
countlast 38D939 | wp1a piece in flight: v.x x 0.9 after its move, on the last tick of each stock period
pre 38D959 | wp1a piece in flight: y += v.y each tick; scale the old velocity in xmm0 for this move while keeping +C4 in stock units
countlast 38D961 | wp1a piece in flight: v.y -= 1 after its move, on the last tick of each stock period
countlast 38D978 | wp1a piece in flight: v.z x 0.9 after its move, on the last tick of each stock period
pre 38D980 | wp1a piece in flight: z += v.z each tick; scale the old velocity in xmm0 for this move while keeping +C8 in stock units
lin 38D998 | wp1a piece in flight: rotate its matrix about X by three degrees each tick; scale the angle
lin 38D9AE | wp1a piece in flight: rotate its matrix about Y by seven degrees each tick; scale the angle
count 38DA8C | wp1a piece: the 60-tick flight wait at +1124 counts down once each stock tick, with the zero test reading not finished on skipped ticks
