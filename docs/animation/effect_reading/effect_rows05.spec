group actor
# es7e vtable slot 8 advances the same +1074 stage counter in five branches.
count 5F5E73 | es7e: advance stage 3 counter on stock ticks
count 5F5F87 | es7e: advance stage 6 counter on stock ticks
count 5F6052 | es7e: advance stage 9 counter on stock ticks
count 5F6241 | es7e: advance stage 13 counter on stock ticks
count 5F6353 | es7e: advance stage 16 counter on stock ticks

# esp17 slot 1 multiplies the three position axes by two damping factors.
# +2C8 controls Y; +2CC controls X and Z through the subsequent xmm1 copy.
root 1A3DBC | esp17: take the per-tick root of the Y damping factor
root 1A3DCC | esp17: take the per-tick root of the X/Z damping factor
count 1A3E3F | esp17: advance the +2D8 age on stock ticks

# ese0 called from 3613B0: two exclusive +E35 opacity ramp branches and
# the shared +E36 trigger clock advance once per stock tick.
count 361AD4 | ese0: advance the +E35 opacity ramp on stock ticks
count 361B29 | ese0: advance the alternate +E35 opacity ramp on stock ticks
count 361B86 | ese0: advance the +E36 trigger clock on stock ticks
