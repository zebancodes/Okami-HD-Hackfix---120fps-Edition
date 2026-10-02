group player
# --- wp09 (387140) ---
dst 38717B ("slowmo",0x38716C) | wp09 (387140): xmm6 is 23AD90's slow-motion dt; its only readers after the copy are +E28 -= 0.1 x dt and the forward move by +E28 x dt; no animation-rate reader
# --- wp0f (38A8F0) ---
dst 38A935 ("slowmo",0x38A927) | wp0f (38A8F0): xmm7 is 23AD90's slow-motion dt; its only reader after the copy is the nearby-target sound cooldown +10FC -= dt; no animation-rate reader
# --- wp0f (38ABD0) ---
dst 38AC19 ("slowmo",0x38AC0B) | wp0f (38ABD0): xmm7 is 23AD90's slow-motion dt; every reader is a per-tick step: the +10F8 countdown on both state paths, the move by +E10 x dt, the clamped turn limit 0.10472 x dt, and the +10FC sound cooldown; no animation-rate reader
# --- wp1d (38FE50) ---
dst 38FE84 ("slowmo",0x38FE6F) | wp1d (38FE50): xmm6 is 23AD90's slow-motion dt; its only reader after the copy is the lifetime +E28 -= dt; no animation-rate reader
lin 390021 | wp1d (38FE50), flight: heading +B0 gains 0.523599 radians a tick, so s of the step
pre 3900B3 | wp1d (38FE50), flight: position.x += velocity +E10 a tick; +E10 is built once at launch and keeps its stock value, so s of it
pre 3900CA | wp1d (38FE50), flight: position.y += velocity +E14 a tick; s of the stock-valued velocity
pre 3900E3 | wp1d (38FE50), flight: position.z += velocity +E18 a tick; s of the stock-valued velocity
# --- wp1d (390490) ---
dst 3904C5 ("slowmo",0x3904BC) | wp1d (390490): xmm7 is 23AD90's slow-motion dt; every reader is a per-tick step: +1078 -= dt, the sin(+1110) x 0.7 x dt bob, +1110 += 0.24 x dt, the move by +E10 x dt, +E18 += dt, +E28 -= dt, and the clamped turn limit 0.20944 x dt; branch-local multiplies do not reach another state and there is no animation-rate reader
srcx 3904F7 | wp1d (390490), states 0-3: +D2C fades in by xmm8 = 0.05 a tick up to 1; apply s to the source step while leaving the shared xmm8 unchanged
srcx 390AE2 | wp1d (390490), state 5: +D2C fades out by xmm8 = 0.05 a tick down to 0.1; apply s to the source step
