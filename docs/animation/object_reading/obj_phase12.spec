# utd2 230760 derives every submodel angle increment and the +1070 sine
# phase from fVar6, selected solely from +E35: 1, 5, or 0 per update.
group objects
lin 2307CA | normal-state per-tick phase speed 1 held in xmm7 for all five submodel angles and +1070
lin 2307D6 | state-one per-tick phase speed 5 held in xmm7 for the same paths
