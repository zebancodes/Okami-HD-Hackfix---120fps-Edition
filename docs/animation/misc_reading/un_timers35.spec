group objects
count 160348 | selection dialog exit phase 3: consume the positive byte +44 animation-close delay at stock cadence before returning to the owner state.
count 160384 | selection dialog exit phase 2: consume the positive byte +44 animation-close delay at stock cadence before selecting the next action.
count 1D0500 | text box exit interpolation: advance the six-step +1C clock at stock cadence; scale fields derive directly from that clock.
count 1D2817 | dialogue response phase 1: pace the fifteen-tick +1C delay before advancing +57.
count 1D2840 | dialogue response phase 3: pace the forty-five-tick +1C delay before advancing +57.
count 1D28D2 | dialogue response phase 5: pace the final fifteen-tick +1C delay before reporting completion.
count 1D0EFB | dialogue text reveal: add the integer reveal-speed amount to +7C once per stock tick, including the input-selected tenfold acceleration.
count 1D1B9C | text box entrance interpolation: advance its six-step +1C clock once per stock tick; scale fields derive directly from that clock.
count 13F1C1 | controller reassignment: consume the thirty-tick +18 delay after the active input mode closes.
count 14ADDE | asynchronous UI operation: advance bounded +18 progress at stock cadence until +1C; the displayed progress ratio follows this count.
count 15FDA5 | audio playlist: pace the 1320-tick inter-track wait after playback completes; immediate failure initializes the threshold and remains immediate.
count 186469 | cPad movement chord: require five stock ticks of the held action before changing its combined-action bits; releasing the action resets +248.
count 1866EB | cPad update input blackout: consume positive +264 at stock cadence; hardware updates and actuator calls continue normally.
count 186F64 | controller recovery: consume the positive sixty-tick +10 delay before reporting a connection/reassignment outcome.
