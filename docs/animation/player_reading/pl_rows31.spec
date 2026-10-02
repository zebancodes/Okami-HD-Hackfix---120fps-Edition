group player

# wp00 state handler (37F1E0)
lin 37F494 | wp00 state 37F1E0: +B0's continuous 30-degree spin step advances every rising update; scale the angular step by s

# wp1b grounded-flight helper (38E720)
dst 38E792 | wp1b helper 38E720: load grounded slope +FE0 and scale it once toward the s^2 change of persistent per-current-rate velocity +E20
dst 38E79A | wp1b helper 38E720: load grounded slope +FE8 and scale it once toward the s^2 change of persistent per-current-rate velocity +E28
pre 38E7A2 | wp1b helper 38E720: scale the already s-scaled slope in xmm0 again before adding it to +E20, giving an s^2 velocity change
pre 38E7AA | wp1b helper 38E720: scale the already s-scaled slope in xmm1 again before adding it to +E28, giving an s^2 velocity change

# wp1c grounded-flight helper (38F240)
dst 38F2BA | wp1c helper 38F240: after multiplying grounded slope +FE0 by 0.5, scale the resulting push once toward the s^2 change of persistent per-current-rate velocity +E20
pre 38F2C2 | wp1c helper 38F240: after the 0.5 slope factor, scale xmm0 again before adding it to +E20, giving an s^2 velocity change
dst 38F2DA | wp1c helper 38F240: after multiplying grounded slope +FE8 by 0.5, scale the resulting push once toward the s^2 change of persistent per-current-rate velocity +E28
pre 38F2E2 | wp1c helper 38F240: after the 0.5 slope factor, scale xmm0 again before adding it to +E28, giving an s^2 velocity change

# wp47 common state handler (39A840)
count 39A89F | wp47 state 39A840: first of the normal two +10F6 countdown decrements commits once per stock tick
count 39A8C5 | wp47 state 39A840: second +10F6 decrement commits on the same stock tick; the special global path can still force zero immediately

# pl00 state handlers (3BC300, 3C1010)
notyet 3BC4C4 notyet:3BC4D0 | pl00 state 3BC300, state 3: hold +E3C's old-value zero transition between stock ticks
lin 3C10FD | pl00 state 3C1010, state 1: scale the continuous 10-degree per-tick target-turn limit before 2DDF90
