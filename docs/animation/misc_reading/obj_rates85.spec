group objects
count 229F07 | ut9a: pace the E3C sine-wave sample clock; its temporary DI is discarded immediately and the later branch uses the preserved 1090 comparison.
lin 22A05D | ut9a: scale the 1.5 growth of the bounded player-relative radial offset; the resulting X/Z positions are rebuilt from the player's position each update.
count 22A289 | ut9a alternate: pace its E3C sine-wave sample clock.
lin 22A2C0 | ut9a alternate: scale the continuous two-degree yaw step before wrapping.
lin 21D835 | ut52: scale the one-unit upward movement before its ceiling clamp.
count 21D9E7 | ut52: pace the recurring sound delay and preserve the JNS continuation on held ticks.
count 21DA75 | ut52: pace the post-impact wait, preserving JNS on held ticks.
count 21DC02 | ut52: pace the descending-phase timeout and retain its JNS continuation.
count 21DCC8 | ut52: pace the alternate recurring sound delay with JNS continuation.
lin 56E68A | utb5: scale the half-unit rise while every linked input state is complete.
count 56E72F | utb5: hold the 300-tick delay store; the pre-decrement zero test drives the phase change.
lin 56E74C | utb5: scale the half-unit reset rise before the saved-height clamp; motion advancement stays time corrected.
count 4FFBEA (0x4FFBDF,0x4FFBED,(0x4FFBDF,0x4FFBE6,0x4FFBE8,0x4FFBEA),None,-1) | cBamboo: BPL is the callee-saved positive unit set in the prologue; pace the five-tick register decrement and synthesize not-complete JNE flags on held ticks.
count 56C05A | utaf: pace the E3C fifteenth-tick sound clock.
notyet 56C067 0x56C08A | utaf: suppress the fifteenth-tick sound equality on held clock ticks.
count 57DC05 | ut32: hold the forty-tick fast-motion duration store; the old-zero test selects the normal speed.
count 583C38 | utcc: pace the seven-tick effect interval's byte clock.
notyet 583C45 0x583C83 | utcc: suppress the modulo-seven event on held clock ticks.
count 62FB76 | et30: pace the one-to-eight-tick randomized effect cooldown; AL is then overwritten with the false return.
count 4980BE | cItemObj: pace the byte UV phase; material UV is freshly calculated from view direction plus this clock.
count 497F29 | cItemObj: commit the countdown-coupled alpha decrement only at stock cadence, using the original remaining-duration formula.
count 497F4E | cItemObj: hold the remaining alpha duration store to match its dependent alpha decrement.
blend 56598A | uta8: correct the 0.1 X-position approach coefficient.
blend 5659AE | uta8: correct the 0.1 Z-position approach coefficient.
count 56D377 | utb2: commit the selected downward force only on stock ticks as part of its coupled spring update.
count 56D3A4 | utb2: commit the spring force and 0.96 damping together at stock cadence.
count 56D3B1 | utb2: commit the dependent Y integration at the same stock cadence as its velocity.
zfirst 22EC9B | utbe: zero the acceleration step between stock ticks before velocity accumulation and its terminal-speed clamp.
srcx 22ECD7 | utbe: integrate the resulting velocity as a per-frame Y movement step.
dst 2E38E4 | et08: scale the selected table acceleration after loading it and before adding to the 1144 rise rate.
pre 2E3934 | et08: scale the complete rise-rate movement step before accumulating the submodel height.
count 2EC719 | et41: commit the selected 0.2/0.8 vertical acceleration only at stock cadence; the motion consumer already scales velocity integration.
count 2ECCC9 | et42: commit the corresponding selected vertical acceleration only at stock cadence.
src 49FDCA | cKakejiku: scale the animation-switch elapsed frame clock's unit increment; XMM6 remains the stock constant used elsewhere.
count 4E4106 | ut0a: pace each of the four ninety-tick linked interaction delays while retaining the per-update target census.
zfirst 4F08A0 | ut21: zero the angular acceleration between stock ticks before the speed cap.
src 4F08D5 | ut21: integrate the resulting angular velocity as a time-scaled yaw step.
count 4F08F4 | ut21: pace the E3C forty-five-tick positional sound clock.
notyet 4F0928 0x4F0879 | ut21: suppress the periodic sound equality between stock clock ticks.
src 2360B2 | utf6: scale the complete turn step of one revolution per E3E stock duration before wrapping.
count 236121 (0x236115,0x236125,(0x236115,0x23611C,0x23611F,0x236121),None,-1) | utf6: R14W is the positive unit initialized in the prologue; pace the E3C register countdown and preserve its JNE continuation.
notyet 236193 0x2361C0 | utf6: prevent the thirty-tick sound equality from recurring while the already gated E40 clock is held.
notyet 23623C 0x23627B | utf6: emit the ninety-tick sound only on a stock timer tick.
notyet 23627B 0x2362BC | utf6: emit the sixty-tick sound only on a stock timer tick.
notyet 2362BC 0x236814 | utf6: emit the thirty-tick sound only on a stock timer tick.
group flag
count 4BDA0A | Movie continuous rumble PWM: pace the phase increment in the port's 60-Hz context. Its initial phase is zero, intensity is a byte or its interpolation, and every crossing subtracts 255, so a held phase remains below 255 and cannot repeat a pulse. Discrete movie keyframe events remain driven by the external playhead.
