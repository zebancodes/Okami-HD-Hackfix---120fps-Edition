group actor
# Shared enemy update 241180 calls 23F8D0, which passes the sole xmm6 step
# to ten helper calls (two each of 23F9F0, 23FB70, 23FD00, 23FE90, 240020).
# Each helper uses argument xmm3 only for the three colour-channel additions
# or subtractions in its state 1 and state 3 paths, then clamps the result.
lin 23F8E4 | common em00.. enemy material fade: scale the caller's shared xmm6 step passed as xmm3 to all ten RGB helper calls
