group objects
# cBallObj update 33BB20: +E20/+E28 are horizontal velocity and +A8 points
# to position. The position additions run each update, while +1128 damps the
# velocities after their move. +E42 and +E40 are already stock-gated by
# memory_timers.h; the shake impulses still need per-tick scaling.
pre 33BC15 | cBallObj: scale the per-tick x acceleration from +1130 times +FE8 before adding it to persistent +E28
pre 33BC1D | cBallObj: scale the per-tick z acceleration from +1130 times +FE0 before adding it to persistent +E20
pre 33BDA8 | cBallObj shake, phase 0-9: scale the sine impulse before adding it to persistent +E20
pre 33BDC8 | cBallObj shake, phase 0-9: scale the cosine impulse before adding it to persistent +E28
pre 33BE52 | cBallObj shake, phase 11-19, odd cycle: scale the cosine impulse before adding it to +E20
src 33BE5A | cBallObj shake, phase 11-19, odd cycle: scale the sine impulse in xmm8 before subtracting it from +E28
pre 33BE79 | cBallObj shake, phase 11-19, even cycle: scale the sine impulse before adding it to +E28
src 33BE82 | cBallObj shake, phase 11-19, even cycle: scale the cosine impulse in xmm1 before subtracting it from +E20
pre 33BECE | cBallObj shake, phase 21-29: scale the sine impulse before adding it to +E20
pre 33BEE6 | cBallObj shake, phase 21-29: scale the cosine impulse before adding it to +E28

# Both movement branches use the same stock-valued horizontal velocity.
src 33BFF7 | cBallObj airborne branch: move x by one high-rate share of persistent +E20
src 33C00F | cBallObj airborne branch: move z by one high-rate share of persistent +E28
src 33C030 | cBallObj grounded branch: move x by one high-rate share of persistent +E20
src 33C048 | cBallObj grounded branch: move z by one high-rate share of persistent +E28

# +116C counts frames while horizontal speed stays above the sound threshold.
# The modulo test reads the old count: suppress its sound between stock ticks
# as well as gating the increment, so a held multiple of ten cannot retrigger.
notyet 33C09D notyet:33C0E3 | cBallObj moving sound: a held +116C multiple of ten must not play again between stock ticks
count 33C0E3 | cBallObj moving sound: advance +116C once per stock tick after the modulo test

# The shared +1128 factor is copied to xmm3 for x and kept in xmm1 for z.
# Both velocity lanes damp after the move, on the last tick of a stock period.
ulast 33C0F4 | cBallObj: hold dynamic +1128 drag until the last tick before damping both +E20 and +E28
