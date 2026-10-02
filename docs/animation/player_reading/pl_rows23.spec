group player
# pl00 ground drift copies (3B1560, 3B18D0, 3B2620)
pre 3B184B | pl00 sub-handler 3B1560: persistent ground-drift velocity +10B8 gains the computed 0.1 x ground-vector z push each tick; keep the velocity in stock units and add s of the push
pre 3B1853 | pl00 sub-handler 3B1560: persistent ground-drift velocity +10B0 gains the computed 0.1 x ground-vector x push each tick; add s of the push
pre 3B186B | pl00 sub-handler 3B1560: position.x gains persistent stock-valued +10B0 each tick; scale the velocity copy for this move
pre 3B1882 | pl00 sub-handler 3B1560: position.z gains persistent stock-valued +10B8 each tick; scale the velocity copy for this move
lin 3B210A | pl00 state 0 (3B18D0): +E48 is a displacement per current-rate tick, so scale its stock 0.05 stopping threshold by s before the ordered compare
pre 3B2282 | pl00 state 0 (3B18D0): persistent ground-drift velocity +10B8 gains the computed 0.1 x ground-vector z push each tick; add s of the push
pre 3B228A | pl00 state 0 (3B18D0): persistent ground-drift velocity +10B0 gains the computed 0.1 x ground-vector x push each tick; add s of the push
pre 3B22A2 | pl00 state 0 (3B18D0): position.x gains persistent stock-valued +10B0 each tick; scale the velocity copy for this move
srcx 3B22B6 | pl00 state 0 (3B18D0): position.z in xmm0 gains persistent stock-valued +10B8 from memory each tick; scale only the source velocity
pre 3B2A6F | pl00 state 1 (3B2620): persistent ground-drift velocity +10B8 gains the computed 0.1 x ground-vector z push each tick; add s of the push
pre 3B2A77 | pl00 state 1 (3B2620): persistent ground-drift velocity +10B0 gains the computed 0.1 x ground-vector x push each tick; add s of the push
pre 3B2A8F | pl00 state 1 (3B2620): position.x gains persistent stock-valued +10B0 each tick; scale the velocity copy for this move
srcx 3B2AA3 | pl00 state 1 (3B2620): position.z in xmm0 gains persistent stock-valued +10B8 from memory each tick; scale only the source velocity
