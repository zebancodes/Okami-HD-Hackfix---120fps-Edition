group player
# wp09 launch/move (3875B0)
pre 387802 | wp09 (3875B0), sub-state 1: position.x gains persistent launch velocity +E10 each tick; scale the copied velocity for this move while leaving the stored velocity stock-valued
pre 387823 | wp09 (3875B0), sub-state 1: position.y gains persistent launch velocity +E14 each tick; scale the copied velocity for this move
pre 38783C | wp09 (3875B0), sub-state 1: position.z gains persistent launch velocity +E18 each tick; scale the copied velocity for this move
# wp0d colour phase (388B50)
count 388D63 | wp0d (388B50): +E3C advances the cyclic colour waveform one count per stock tick; skip the incremented word store between stock ticks
# wp30 two-joint angular spring (397050)
dst 39710A | wp30 (397050), first joint spring: angular velocity +1C68 loses joint angle x 0.05 each tick; scale the computed pull before it accumulates
srcx 397140 | wp30 (397050), first joint spring: the joint angle gains angular velocity +1C68 each tick; add s of the stock-valued velocity
countlast 397158 | wp30 (397050), first joint spring: +1C68 is damped x 0.7 after the move, on the last tick of each stock period
dst 3971BA | wp30 (397050), second joint spring: angular velocity +1C6C loses joint angle x 0.05 each tick; scale the computed pull before it accumulates
srcx 3971ED | wp30 (397050), second joint spring: the joint angle gains angular velocity +1C6C each tick; add s of the stock-valued velocity
countlast 397205 | wp30 (397050), second joint spring: +1C6C is damped x 0.7 after the move, on the last tick of each stock period
# pl00 state 2C conditional forward push (3C2430)
pre 3C2A38 | pl00 state 2C (3C2430): the conditional rotated two-unit forward push is added to position.x every tick; scale the copied step
pre 3C2A4C | pl00 state 2C (3C2430): the same rotated forward push, position.y component
pre 3C2A62 | pl00 state 2C (3C2430): the same rotated forward push, position.z component
