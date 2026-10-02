group player

# Completed six-function batch.
# pl00 all-slot auxiliary projectile/effect update (3CCC50)
pre 3CCDAD | pl00 all-slot auxiliary update (3CCC50): position.x gains persistent stock-valued velocity.x each tick; scale the velocity copy for this move
pre 3CCDC4 | pl00 all-slot auxiliary update (3CCC50): position.z gains persistent stock-valued velocity.z each tick; scale the velocity copy for this move
pre 3CCDD5 | pl00 all-slot auxiliary update (3CCC50): position.y gains persistent stock-valued velocity.y each tick; scale the velocity copy for this move
countlast 3CCDDE | pl00 all-slot auxiliary update (3CCC50): vertical velocity loses 0.6 once per stock period, after the period's scaled position move
count 3CCE52 | pl00 all-slot auxiliary update (3CCC50): +15B8[slot] lifetime decrements once per stock tick
notyet 3CCE59 notyet:3CCE65 | pl00 all-slot auxiliary update (3CCC50): hold the lifetime's old-value zero test and state-3 transition between stock ticks

# pl00 state handler (3BDCB0)
lin 3BE1E7 | pl00 state handler 3BDCB0, sub-state 1: position.y gains 0.68 per tick; scale the spatial step by s
lin 3BE1FC | pl00 state handler 3BDCB0, sub-state 1: vertical speed +E54 gains 0.306 per tick; scale the acceleration step by s

# pl00 ground-motion state (3C3C70)
count 3C3F3B | pl00 state 3C3C70: +E3C's eight-degree sine-wobble phase step advances once per stock tick
pre 3C4122 | pl00 state 3C3C70: persistent ground-drift velocity +10B0 gains the computed 0.1 x ground-vector x push each tick; add s of the push
pre 3C4140 | pl00 state 3C3C70: persistent ground-drift velocity +10B8 gains the computed 0.1 x ground-vector z push each tick; add s of the push
pre 3C4157 | pl00 state 3C3C70: position.x gains persistent stock-valued +10B0 each tick; scale the velocity copy for this move
srcx 3C416B | pl00 state 3C3C70: position.z in xmm0 gains persistent stock-valued +10B8 from memory each tick; scale only the source velocity

# pl00 state handler (3CC270)
count 3CC466 | pl00 state 3CC270: persistent forward speed +E48 is multiplied by 0.4 once per stock tick

# pl00 paired byte-timer state machine (3CD1A0)
count 3CD1DF | pl00 timer helper 3CD1A0, +115D mode 2: +115C decrements once per stock tick
notyet 3CD1E5 notyet:3CD446 | pl00 timer helper 3CD1A0, +115D mode 2: hold the old-value zero test and its effect transition between stock ticks
count 3CD2D9 | pl00 timer helper 3CD1A0, +115D mode 1: +115C decrements once per stock tick
notyet 3CD2DF notyet:3CD446 | pl00 timer helper 3CD1A0, +115D mode 1: hold the old-value zero test and its effect transition between stock ticks

# pl00 common tick/effect sequencer (3CD460)
count 3CD583 | pl00 sequencer 3CD460: +114A's elapsed-tick count increments once per stock tick
notyet 3CD593 notyet:3CD5CF | pl00 sequencer 3CD460: let the +114A == 1 first-tick effect fire only on a stock tick
count 3CD5CF | pl00 sequencer 3CD460: +1150's eight-tick phase counter increments once per stock tick
notyet 3CD5DE notyet:3CD696 | pl00 sequencer 3CD460: let the (+1150 & 7) == 1 periodic effect fire only on a stock tick
notyet 3CD6AA notyet:3CD6F8 | pl00 sequencer 3CD460: hold the +114A + 1 threshold effect between stock ticks
notyet 3CD70C notyet:3CD761 | pl00 sequencer 3CD460: hold the second +114A + 1 threshold effect and +1150 reset between stock ticks

# Dormant sibling of 3CCC50 (3CCEA0).
# No code/data-pointer/export call path exists in this build. These rows are safe today
# because the helper is unreachable; a future caller must invoke it as a per-frame slot update.
pre 3CCFB5 | pl00 dormant single-slot auxiliary update (3CCEA0): position.x gains persistent stock-valued velocity.x each tick; scale the velocity copy for this move
pre 3CCFC4 | pl00 dormant single-slot auxiliary update (3CCEA0): position.z gains persistent stock-valued velocity.z each tick; scale the velocity copy for this move
pre 3CCFD6 | pl00 dormant single-slot auxiliary update (3CCEA0): position.y gains persistent stock-valued velocity.y each tick; scale the velocity copy for this move
countlast 3CCFE0 | pl00 dormant single-slot auxiliary update (3CCEA0): vertical velocity loses 0.6 once per stock period, after the period's scaled position move
count 3CD076 | pl00 dormant single-slot auxiliary update (3CCEA0): +15B8[slot] lifetime decrements once per stock tick
notyet 3CD07C notyet:3CD087 | pl00 dormant single-slot auxiliary update (3CCEA0): hold the old-value zero test and state-3 transition between stock ticks
