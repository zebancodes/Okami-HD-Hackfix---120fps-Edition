once | cCarryObj ground impact restitution: 33DA50 calls 33DBE0 only after the ground contact reported by 20F6C0; rebound reverses/halves the incoming vertical speed and halves the horizontal speed for that impact. | 33DC77 33DC97
once | cCarryObj wall impact: 33DA50 calls 33DD10 only for the +F90 wall-contact bit; it reflects the incoming XZ direction about the contact normal while retaining its magnitude. | 33DE10 33DE24
stock | cKiType002 brush wobble stop: the below-threshold branch multiplies +1114 by exactly zero, clearing the angular impulse instead of applying a time-dependent decay. | 3659A1
once | ut12 ground contact: the -0.2 restitution at 2172F0 is followed immediately by changing +E36 from the falling phase to phase 4; this rebound executes once at the impact. | 2172F0
