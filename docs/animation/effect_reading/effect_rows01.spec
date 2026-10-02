group actor
# es17 chooses one of three +1078 opacity changes, and rotates +107C.
lin 35E2EC | es17 state 2: scale the fixed 4.396552 opacity step
lin 35E311 | es17 state 1: scale the sinusoid-derived opacity fall
lin 35E359 | es17 state 0: scale the sinusoid-derived opacity rise
lin 35E39A | es17: scale the 0.5 wrapped angle step

# esp04 samples a random displacement for each axis on its slot 14 tick.
# The pre hooks scale each sample after its speed multiplication.
pre 19E26F | esp04 X: scale the random displacement before adding it
pre 19E294 | esp04 yaw: scale the random rotation before wrapping
pre 19E2E0 | esp04 Z: scale the random displacement before adding it
