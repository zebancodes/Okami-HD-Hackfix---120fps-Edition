once | ut9a phase-zero entry computes its initial orientation once, then advances E36 to one before subsequent updates. | 229DBE
stock | ut9a's repeated orientation approach is the globally time-corrected 2DA510 turn helper. | 22A013
stock | ut9a copies the player's X/Z into its own position each update before adding the normalized radial offset; these are fresh position construction, not integrated velocity. The bounded radial offset's growth is corrected separately at 22A05D. | 22A0D8 22A0F6
once | utf6 lowers the linked model four units on entry into a new attempt, advances E36, and raises it again on phase-six completion or cancellation while resetting E36 to zero. These are paired fixed spatial offsets. | 235D1B 235E60 236431 236468
once | utf6's capped 1118 field counts attempts: the case-one proximity event increments it once after setting E36 to two and initializing that attempt's E3C/E3E duration. | 235F14
once | utb5's case-two entry sets E37 to three and lowers its model fifty units once before initializing the linked states. | 56E63D
stock | uta8's orientation result comes from the globally corrected 2DA510 approach helper. | 5659D8
once | et41/et42 release impulse runs only when the player leaves its captured E35/E34 state, and sets E36 to four before adding the fixed launch impulse; this is not a repeated blend. | 2EC789 2ECD39
once | Brush tutorial completion counter: 1690C0 status two reads the completed-command pulse at brush+110. 16C7E0 clears that pulse each active update and sets it when its countdown moves C80 from four to five; recognized stroke completion increments the tally once. | 4C1263 4C19A6
once | Brush tutorial +C counts button press events selected by B6B0D0 input bits, stopping after three presses; it is not elapsed frame time. | 4C133F
follows | Brush tutorial +4 counts completed timeout attempts; the event resets the separately paced +8 clock to zero immediately, then starts the next attempt. | 4C16D4
fixed | ut9 vertical motion stores the values corrected by lin steps 566398, 5663C3 and 566725. The E40 word store is gated directly at 566801; duplicate decompiler ownership does not create a second physical update. | 5663A0 5663CB 56672D 566801
