group objects
count 217FE4 | ut1e 217F20: phase-three wait counts 15 stock ticks before one motion setup and state transition
count 2180D6 | ut1e 217F20: phase-one wait counts 30 stock ticks before the phase-two sound and transition
count 21806F (0x218069,0x218071,(0x218069,0x21806F),None) | ut1e 217F20: phase-two +107C period increments before the modulo-30 event test; preserve the loaded register on held ticks
notyet 218084 notyet:21816D | ut1e 217F20: held modulo-30 ticks skip the recurring sound event even when the counter is divisible by 30
count 21ABD0 | ut36 21AA80: positive byte cooldown +10E1 delays reactivation; computed AL is discarded before the sound mask test
count 21AC12 | ut36 21AA80: phase-one recurring sound period +10E0 advances after its old-value test
notyet 21ABD6 notyet:21AC12 | ut36 21AA80: held phase-one sound period skips the modulo-32 trigger
count 21AD62 | ut36 21AA80: phase-three recurring sound period advances after the old-value test
notyet 21AD25 notyet:21AD62 | ut36 21AA80: held phase-three sound period skips the modulo-32 trigger
count 21AA6C | ut36 21A970: recurring sound period +10E0 advances after its old-value test
notyet 21AA30 notyet:21AA6C | ut36 21A970: held sound period skips the modulo-32 trigger
count 21A5F3 | ut36 219F90: phase-three sound-trigger branch advances the shared +10E0 period
notyet 21A59F notyet:21A85A | ut36 219F90: held +10E0 ticks skip the phase-three recurring sound trigger across two flag-neutral register reloads
count 21A85A | ut36 219F90: other branches advance the shared recurring sound period
notyet 21A81E notyet:21A85A | ut36 219F90: held +10E0 ticks skip the recurring sound trigger in the common phase-one branch
count 2202E7 | ut60 220270: recurring sound period +10F8 advances after copying its old byte to AL
notyet 2202ED notyet:220317 | ut60 220270: keep the masked old AL but skip its modulo-32 sound event on held ticks
count 220815 | ut61 2205B0: recurring sound period +10F8 advances after copying the old byte to AL
notyet 22081B notyet:220845 | ut61 2205B0: held sound-period ticks skip the old-value modulo-32 sound event
count 226F12 | ut88 226E40: +E42 counts stock ticks until the placement-dependent initial delay has elapsed
notyet 226EFC notyet:226F07 | ut88 226E40: a held delay tick skips the equality transition based on the old +E42 value
count 22708D | ut88 226E40: +10F8 sound period increments with computed AL discarded before its old CL test
notyet 227093 notyet:22713F | ut88 226E40: held sound-period ticks skip the old-zero sound event, including wraparound
count 22116A | ut65 221070: +1138 is the common elapsed phase read modulo 120 or 140 by child helpers; each child sound also sets a latch to prevent replay while the phase is held
count 22C0C0 float | utbb 22C000: change Y velocity by the stock gravity step on the first tick of each stock period, before integrating it
pre 22C0D7 | utbb 22C000: integrate the complete Y velocity at stock speed after writing the velocity back, preserving the unscaled velocity field
count 22C41E | utbb 22C3D0: bounded 0-to-5 reactivation debounce counts stock ticks before enabling the object
count 22C902 | utbc 22C880: positive +1106 cooldown decrements with AL discarded before return
count 22CF32 | utbc 22CED0: positive +1100 debounce decrements and returns before the action-selection path
count 22F646 down | utcb 22F640: five-tick wait before restoring placement and opening the selected dialogue; expiry leaves this phase
count 232798 | utdb 232680: recurring phase-five sound period +1100 advances after computing the old-byte quotient; R8 is not read after its store
notyet 2327A4 notyet:2326C5 | utdb 232680: held modulo-six ticks skip the old-counter sound event
count 238436 | utfb 238380: positive three-tick spawn cooldown decrements and returns before the spawn/reload path
count 33D38C | cCarryObj 33D360: positive seven-tick attached-effect cooldown decrements with AL discarded before the effect-state test
count 3672DC (0x3672D0,0x3672E0,(0x3672D0,0x3672D7,0x3672DA,0x3672DC),None) | cKiType011: positive +11B0 countdown controls one cleanup at zero, preserving not-finished flags on held ticks
count 3678E9 (0x3678DD,0x3678ED,(0x3678DD,0x3678E4,0x3678E7,0x3678E9),None) | cKiType012: positive +11B0 countdown controls one cleanup at zero, preserving not-finished flags on held ticks
count 4985A6 | cItemObj 4984E0: positive +11B6 pickup cooldown decrements with AL discarded before the enable test reloads the field
count 4985F0 (0x4985E5,0x4985F2,(0x4985E5,0x4985EC,0x4985EE,0x4985F0),None) | cItemObj 4984E0: +11B7 attached-effect cooldown decrements once per stock tick; its JNE cleanup uses not-finished flags on held ticks
count 49861D | cItemObj 4984E0: positive +11B8 cooldown decrements with AL discarded before the next cooldown load
count 498630 | cItemObj 4984E0: positive +11B5 cooldown decrements with AL discarded before return
count 61FBC2 | et26 61FB30: +1148 counts elapsed phase-four model ticks while motion advances independently
count 61FC53 | et26 61FB30: +1148 counts a 600-stock-tick attached-state timeout before one motion/state transition
count 6519B5 | ut35 6518E0: positive +E3E motion-phase duration decrements with AX discarded before the next speed calculation
count 651C15 | ut35 651B40: positive +E3E motion-phase duration decrements with AX discarded before the next speed calculation
count 552CCA | ut47 552B70: +1078 counts 13 consecutive stock ticks of negligible movement before the stuck phase; threshold changes E35 out of this branch
count 560CA2 | uta4 560BD0: +E3E recurring 120-tick effect period advances after deriving the old signed quotient; CX is discarded before the old-value event comparison
notyet 560CB1 notyet:560D24 | uta4 560BD0: held modulo-120 ticks skip the effect trigger based on the old period value
