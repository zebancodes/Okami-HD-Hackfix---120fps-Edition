group objects
# ut63 update 2209E0: the two repeated states use one shared fade step each.
# In state 3, xmm6 steps all four material channels and the +D20/+D24/+D28
# object colour channels; in state 1, xmm2 steps the four material channels.
lin 220A3F | ut63 states 3 and colour fade: scale the sole xmm6 step used by material +50/+54/+58/+5C and object +D20/+D24/+D28
lin 220AED | ut63 state 1: scale the sole xmm2 step used by the four material channels before their clamp to one
