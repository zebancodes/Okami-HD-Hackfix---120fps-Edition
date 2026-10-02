group player
# wp03 launch/move (384010)
pre 3841E7 | wp03 (384010, sub-state 1): position.x gains persistent launch velocity +E10 each tick; scale the copied velocity for this move while leaving the stored velocity stock-valued
pre 384203 | wp03 (384010, sub-state 1): position.y gains persistent launch velocity +E14 each tick; scale the copied velocity for this move
pre 38421C | wp03 (384010, sub-state 1): position.z gains persistent launch velocity +E18 each tick; scale the copied velocity for this move
# wp10 launch/move (38BA10)
pre 38BC06 | wp10 (38BA10, sub-state 1): position.x gains persistent launch velocity +E10 each tick; scale the copied velocity for this move while leaving the stored velocity stock-valued
pre 38BC22 | wp10 (38BA10, sub-state 1): position.y gains persistent launch velocity +E14 each tick; scale the copied velocity for this move
pre 38BC3B | wp10 (38BA10, sub-state 1): position.z gains persistent launch velocity +E18 each tick; scale the copied velocity for this move
# wp12 launch/move (38CF10)
pre 38D0E1 | wp12 (38CF10, sub-state 1): position.x gains persistent launch velocity +E10 each tick; scale the copied velocity for this move while leaving the stored velocity stock-valued
pre 38D0F8 | wp12 (38CF10, sub-state 1): position.y gains persistent launch velocity +E14 each tick; scale the copied velocity for this move
pre 38D111 | wp12 (38CF10, sub-state 1): position.z gains persistent launch velocity +E18 each tick; scale the copied velocity for this move
