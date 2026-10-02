group objects
count 22A754 | ut9e 22A6C0: hold the positive +1152 cooldown decrement store; AX is discarded before loading the independent +1150 cooldown
count 22A76A | ut9e 22A6C0: hold the positive +1150 cooldown decrement store; AX is discarded before the state dispatcher
count 22FF34 | utd1 22FE00: hold the positive +1200 turn cooldown decrement store; AX is discarded before the movement helper
count 234690 (0x234680,0x234694,(0x234680,0x234687,0x23468A,0x234690),None) | utf2 234640: pace the positive +1120 countdown and synthesize not-finished flags so its zero event and scenario flag occur exactly once
count 23472A (0x23471A,0x23472E,(0x23471A,0x234721,0x234724,0x23472A),None) | utf2 234640: pace the positive +1122 countdown and synthesize not-finished flags before its zero event resets scale and scenario flag
count 235859 | utf6 235820: hold the positive +E76 collision cooldown decrement store; CL is not read after this store
count 23590B | utf6 235820: hold the +111A seven-update particle period store; quotient and completion use the old phase
notyet 235918 notyet:235969 | utf6 235820: fire the old-phase modulo-seven particle event only on a stock tick, preventing repeats while the phase is held
gatefn 375FF0 | vtca 375FF0: stock-cadence void helper keeps +E36 duration, +1070 phase, motion setup and phase-specific sound events together; caller 375AA0 discards RAX and the body has no other paced steps
gatefn 632E90 | et30 632E90: stock-cadence void selection controller keeps parent +11EB wait, child 62FB60 cooldowns, random target selection and reservation resets together; its helpers perform selection rather than movement and caller 630480 ignores RAX
lin 22F43B | utcb 22F3F0: scale the negative submodel-one angular rate before subtracting its previous angle and wrapping
lin 22F479 | utcb 22F3F0: scale the negative submodel-two angular rate before subtracting its previous angle and wrapping
lin 22F497 | utcb 22F3F0: scale the positive submodel-one angular rate before adding its previous angle and wrapping
lin 22F4D1 | utcb 22F3F0: scale the positive submodel-two angular rate before adding its previous angle and wrapping
blend 220213 | ut60 220180: alpha eases twenty percent toward the visibility target 0.3 or one
blend 220533 | ut61 2204A0: alpha eases twenty percent toward the visibility target 0.3 or one
blend 222B49 | ut66 222B30: shared ten-percent coefficient returns all three scale axes toward one after a hit
blend 2251C4 | ut83 225140: alpha eases twenty percent toward 0.5 or one according to player height
blend 21B732 | ut37 21B6B0: alpha eases thirty percent toward 0.2 or one according to visibility
blend 21B923 | ut37 21B760: submodel vertical offset eases twenty percent toward the player's relative height before fixed bounds
blend 229B5E | ut9a 229A20: alpha eases five percent toward the fixed no-ground target 0.1
blend 229B87 | ut9a 229A20: alpha eases twenty percent toward one when ground was found
srcblend 229BB8 ('block',0x229BAF,0x229BC6) | ut9a 229A20: vertical position eases sixty percent toward the higher ground target before the player-ground clamp
srcblend 229BC2 ('block',0x229BAF,0x229BC6) | ut9a 229A20: use a rooted copy of the ten-percent coefficient for downward vertical easing; preserve XMM2 because it also provided an alpha target earlier
blend 231C73 | utd9 231A80: shared ten-percent coefficient returns all three scale axes toward one during the motion-completion state
