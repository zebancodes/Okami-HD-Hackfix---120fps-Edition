group player
# wp06 guided flight (385A60)
pre 385B49 | wp06 (385A60): position.x gains s of the persistent stock-valued +E10 velocity
pre 385B60 | wp06 (385A60): position.y gains s of the persistent stock-valued +E14 velocity
pre 385B79 | wp06 (385A60): position.z gains s of the persistent stock-valued +E18 velocity
# wp03 movement and spin (383AB0)
callscale 383CF7 (0x2DDF90,"xmm3") | wp03 (383AB0), state 1: turn continuously toward the owner by at most one degree per tick; scale the call limit
callscale 383D1F (0x2DA460,"xmm1") | wp03 (383AB0), state 1: 2DA460 adds the stock-valued +E28 forward speed directly to position; scale its xmm1 argument
lin 383D2C | wp03 (383AB0), state 1: +B0 spins by 15 degrees per tick; add s of the phase step
callscale 383EA6 (0x2DA460,"xmm1") | wp03 (383AB0), state 4: 2DA460 adds the random per-tick forward speed directly to position; scale its xmm1 argument
count 383ED6 | wp03 (383AB0), state 4: commit +B0's changing +E3C-degree spin step once per stock tick, before +E3C decrements
count 383EDE | wp03 (383AB0), state 4: commit +E3C's decrement once per stock tick after the spin step
notyet 383EE5 notyet:383F2B | wp03 (383AB0), state 4: while +E3C's store is held, keep its terminal effect and state transition on stock ticks
# wp0d cyclic scale phase (388FD0)
count 3891A2 | wp0d (388FD0): +E3C advances the two cyclic sine-scale waveforms by one count per stock tick
# wp04 post-motion wait (384BE0)
notyet 384CFC notyet:384D04 | wp04 (384BE0), state 3: while +E37 is held at zero between stock ticks, defer the state transition to its next stock tick
count 384D06 | wp04 (384BE0), state 3: commit the optional three-tick post-motion +E37 countdown once per stock tick
# pl03 shared scale approach (3A4DF0)
blend 3A4E3C | pl03 (3A4DF0): +D20/+D24/+D28 approach 1 by the shared 0.05 factor each tick; use 1-(1-0.05)^s
