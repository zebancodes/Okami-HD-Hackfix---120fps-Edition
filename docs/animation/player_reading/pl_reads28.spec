fixed | wp1d (390C00): +E18 growth, +E28/+1078 countdowns, both +B4 turns, the y move and +1110 phase all use the slow-motion dt scaled at its xmm7 copy (dst 390C2F) | 390D19 390DA0 390EF9 391132 391167 39119B 3911BF
stock | wp1d (390C00): +B0 is the result of 2DA510; FixTurnRate converts its approach factor at the helper entry | 390ED5
fixed | wp1d (391290): +E18 grows and +E28 counts down by the slow-motion dt scaled at its xmm7 copy (dst 3912C3) | 3914A1 3914C7
fixed | wp1d (391290): collision radius +E24 gains s of its 1.4-per-tick growth at lin 39151F before the collision query | 391527
fixed | wp1d (3915E0): +E18 growth, +E28/+1078 countdowns, both +B4 turns, +1090 growth, the y move and +1110 phase all use the slow-motion dt scaled at its xmm7 copy (dst 391643) | 391707 39177D 3918E3 391AEC 391B42 391B9F 391BCF 391BE5
stock | wp1d (3915E0): +B0 is the result of 2DA510; FixTurnRate converts its approach factor at the helper entry | 3918BD
fixed | wp47 (39B3D0): +10F0 and +10EC lose the slow-motion dt scaled at its xmm7 copy (dst 39B409) | 39B6A6 39B6EF
once | wp51 (39E790), state 0: +E36 advances once after initialization, then dispatches state 1 on later updates | 39E83F
fixed | wp51 (39E790): +1110's two four-degree orbit-phase steps are scaled at lin 39E935/39E93F | 39E94C
fixed | wp51 (39E790): +10F0 loses the slow-motion dt scaled at its xmm9 copy (dst 39E7C5) | 39EA0A
