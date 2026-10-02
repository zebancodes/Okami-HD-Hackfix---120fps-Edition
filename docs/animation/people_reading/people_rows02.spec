group actor
# hm27's +1315 byte clock governs how long each flying target phase lasts.
count 322567 | hm27 phase 1: step the +1315 countdown once per stock tick
count 32276A | hm27 phase 3: step the +1315 countdown once per stock tick

# hm27's three stored byte velocities are divided by 100 and added to the
# submodel position. Scale those displacement terms before the addition.
pre 322714 | hm27 submodel X: scale the byte-derived displacement
pre 322731 | hm27 submodel Y: scale the byte-derived displacement
pre 322754 | hm27 submodel Z: scale the byte-derived displacement
