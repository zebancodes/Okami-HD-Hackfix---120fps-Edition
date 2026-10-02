group player
# wp1d slow-motion-paced state machines (390C00, 391290, 3915E0)
dst 390C2F ("slowmo",0x390C26) | wp1d (390C00): xmm7 is 23AD90's slow-motion dt; every live reader is a per-tick step: movement by +E10 x dt, +E18 growth, +E28 and +1078 countdowns, two clamped turns, the sin(+1110) y move and the +1110 phase step; no animation-rate reader
dst 3912C3 ("slowmo",0x3912B9) | wp1d (391290): xmm7 is 23AD90's slow-motion dt; its only live readers move by +E10 x dt, grow +E18 by dt and count +E28 down by dt; no animation-rate reader
lin 39151F | wp1d (391290): collision radius +E24 grows by 1.4 each tick before it is passed to 2DC7B0; scale the repeated spatial-size ramp step
dst 391643 ("slowmo",0x391621) | wp1d (3915E0): xmm7 is 23AD90's slow-motion dt; every live reader is a per-tick step: movement by +E10 x dt, +E18 growth, +E28 and +1078 countdowns, two clamped turns, +1090 growth, the sin(+1110) y move and the +1110 phase step; no animation-rate reader
# wp47 and wp51 countdowns / phase
dst 39B409 ("slowmo",0x39B3FB) | wp47 (39B3D0): xmm7 is 23AD90's slow-motion dt; its only live readers subtract dt from the +10F0 sound cooldown and +10EC state countdown; no animation-rate reader
dst 39E7C5 ("slowmo",0x39E7B7) | wp51 (39E790): xmm9 is 23AD90's slow-motion dt; its only live reader subtracts dt from +10F0; no animation-rate reader
lin 39E935 | wp51 (39E790): +1110 loses four degrees each tick on the reflected-orbit branch; scale the phase step
lin 39E93F | wp51 (39E790): +1110 gains four degrees each tick on the other orbit branch; scale the phase step
