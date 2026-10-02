follows | esp38 1A02A0: +2EC's phase addition at 1A02C0 is already scaled; these stores copy its result and wrap it by whole units | 1A02D3 1A02E1 1A02FA
once | esf1 645620: +E36 advances after starting a motion; +E10/+E18 are derived from a position difference for that motion, then normalized and scaled as setup velocity | 645696 645798 6457B4
once | esp12 1A2770: slot 2 copies the +2D8 and +2DC configuration fields and converts them to reciprocal/rate values during setup | 1A27E6 1A27FE
stock | esp35 1AB6B0: slot 4 saves original +1D0 in xmm12, applies the two visibility factors to a temporary value, then restores +1D0 at 1ABA36 | 1AB939 1AB9E4
once | esfd 363210: the 0.5 alpha multiplier follows PlayMotion while advancing to the next motion stage; it is a state event | 363680
fixed | esfd 363210: both directions of its +14F0 alpha approach use scaled 0.05 literals | 3636E3
stock | espEmitter02 1952F0: +200 is multiplied by +260 only to pass a temporary value to a virtual call and is restored from xmm6 at 1958D9 | 1958CD
fixed | esp18 1A43E0: mutable +2D8 is scaled before the first wrapped phase, and mutable +2DC before the second | 1A443F
stock | esp25 1A8C80: the linked object's +D2C is overwritten from +1D0 at 1A8E0C before the 1A8EA3 visibility multiplication on this same call | 1A8EA3
once | esp29 1A96A0 and esp37 1ABF70: slot 2 derives the initial countdown from configuration bytes and a random modulus | 1A96E1 1ABFB8
once | esp30 1A9B80: the global active-object count is decremented in the destructor before base destruction | 1A9B8A
once | esp34 1AADC0: slot 2 copies the +2C0 configuration and adds a one-time random offset | 1AADFA
stock | esp37 1AC250: +9A6B58 counts particles processed in this frame; 18E1E9 resets it at the start of each effect manager update and 18E3CF reads it afterward | 1AC2C0
fixed | es39 35FBC0: the +10E7 fade byte changes only on stock ticks; the material color is recomputed from its held value on every call | 35FBF9
fixed | ese0 3615C0/361780/361D10: the +E35 phase increments run once per stock tick in each update handler | 3616FB 3618A0 361DA7
once | esfd 362C40/362D10: +14D3 indexes a waypoint array and advances only when the distance and angle test at 362BA0 reaches a waypoint | 362C56 362DDF
stock | esf1 6453F0: the position subtracts +E54 for a collision probe at 645485 and is restored from xmm6 at 64549F | 645480
stock | 199660: the +20 word merges counts of two linked nodes only when their links match; this is event-driven list maintenance | 1996DF
stock | esp08/esp40 19E810: this adds a transformed, converted Z component to an integer cVec output during the slot 16 geometry calculation | 19EC78
stock | esp30 1A9BF0: 167DBA tallies nearby particles in a spatial cell; gtfc update 2FD27A/2FD293 clears both cell lanes through 170CD0 before the next occupancy check | 167DBA
