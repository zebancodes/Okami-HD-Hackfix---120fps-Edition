group player
# pl00 target companions (3D0EC0, 3D1140)
pre 3D1016 | pl00 (3D0EC0): position.x gains s of +E10, rebuilt as 0.2 of the target direction each active tick
pre 3D102D | pl00 (3D0EC0): position.y gains s of the active tick's +E14 target step
pre 3D1046 | pl00 (3D0EC0): position.z gains s of the active tick's +E18 target step
notyet 3D1082 notyet:3D111C | pl00 (3D0EC0): the zero-time return and effect wait for a stock tick when the +E3C countdown is held
count 3D111F | pl00 (3D0EC0): commit the +E3C active-state decrement once per stock tick
srcx 3D1281 | pl00 (3D1140): position.x in xmm0 adds the +E10 target step from memory; scale the source step only, not the existing position
pre 3D129C | pl00 (3D1140): position.y gains s of +E14, rebuilt as 0.2 of the target direction each active tick
pre 3D12B5 | pl00 (3D1140): position.z gains s of the active tick's +E18 target step
notyet 3D12E1 notyet:3D12FE | pl00 (3D1140): the zero-time exit waits for a stock tick while +E3C is held
count 3D1301 | pl00 (3D1140): commit the +E3C active-state decrement once per stock tick
