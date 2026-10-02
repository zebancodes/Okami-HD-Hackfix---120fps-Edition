group player

# Shared wp/enemy visual update (33A560)
notyet 33AA89 notyet:33AAC9 | shared wp/enemy update 33A560, type 398: hold +E3E's old-value zero effect between stock ticks
count 33AACC | shared wp/enemy update 33A560, type 398: +E3E's repeating two-count effect timer decrements once per stock tick

# wp09 slow-motion-paced state (387990)
dst 3879B7 ("slowmo",0x3879A9) | wp09 state 387990: xmm6 is 23AD90's slow-motion dt; its only live readers count +1110 down and move forward by 6.5 times dt, both per-tick steps

# Weapon fades and stock-valued vertical movement
srcx 38CB20 | wp12 helper 38CB10: +D2C loses s of the 0.1 fade step while xmm0 retains the stock 0.1 terminal threshold used by the following comparison
srcx 38D5A6 | wp1a common update 38D490: position.y in xmm0 gains s of stock-valued vertical speed +E54
pre 38E540 | wp1b common update 38E400: +E54 in xmm0 is stock-valued vertical speed; scale it before adding the existing position.y from memory

# Companion hidden by decay_factors.h proximity in coverage.
srcx 38F03F | wp1c common update 38EEE0: position.y in xmm0 gains s of stock-valued vertical speed +E54 before its 0.94^s damping

# wp5a slow-motion-paced state (3A0D00)
dst 3A0D44 ("slowmo",0x3A0D1E) | wp5a state 3A0D00: xmm6 is 23AD90's slow-motion dt; its only live readers count +10F0 down and drive the forward move, both per-tick steps

# pl00 common visual sequencer (3A7950)
count 3A79C1 | pl00 helper 3A7950: +1170 advances through its cyclic submodel-angle table once per stock tick

# pl00 grounded drift state (3C9940)
pre 3C9D81 | pl00 state 3C9940: persistent ground-drift velocity +10B0 gains s of the computed 0.1 times ground-vector x push
pre 3C9D9F | pl00 state 3C9940: persistent ground-drift velocity +10B8 gains s of the computed 0.1 times ground-vector z push
pre 3C9DB6 | pl00 state 3C9940: position.x gains s of the resulting stock-valued +10B0 velocity
srcx 3C9DCA | pl00 state 3C9940: position.z in xmm0 gains s of stock-valued +10B8 from memory

# pl00 linked-actor countdown states
notyet 3D03F0 notyet:3D0420 | pl00 state 3D01F0: hold +E3C's old-value zero effect and completion path between stock ticks
count 3D0426 | pl00 state 3D01F0: +E3C decrements once per stock tick
notyet 3D1624 notyet:3D163A | pl00 state 3D14B0: hold +E3C's old-value zero cleanup between stock ticks
count 3D163D | pl00 state 3D14B0: +E3C decrements once per stock tick while the linked actor remains valid
notyet 3D1778 notyet:3D1786 | pl00 state 3D1670: hold +E3C's old-value zero state transition between stock ticks
count 3D1789 | pl00 state 3D1670: +E3C decrements once per stock tick while the linked actor remains valid
notyet 3D1895 notyet:3D18A2 | pl00 state 3D1820: hold +E3C's old-value zero state transition between stock ticks
count 3D18A5 | pl00 state 3D1820: +E3C decrements once per stock tick while the linked actor remains valid
