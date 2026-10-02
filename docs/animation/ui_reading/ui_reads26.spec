once | cSubScrFile scene closing 4158A0: +99 advances stage after calls to deactivate all child UI controls, with +9A reset for the next stage | 41590B
fixed | cSubScrItem 40D9F0: the cursor sprite's +24 x offset now advances at scaled ten-unit steps while selection remains open | 40DCCB
fixed | cSubScrFilesInfoMess 41F5B0/4202F0: the +D4 opening and closing transition counts now decrement on stock ticks | 41F62B 42036F
fixed | cSubScrFilesInfoWanted 420BE0: +7A is the per-tick visibility countdown and now decrements on stock ticks | 420D64
once | cSubScrFilesJuzu 4212C0: +69 selects the next juzu entry only after an input action and updates the highlighted sprites in that navigation branch | 421377
once | cSubScrFilesSinan 421810: virtual slot 9 calls the screen setup helper 410C70, then offsets sprite 6E by 138 for the selected screen mode once | 421842
once | cSubScrItem 424C30: +14 advances the texture-loading stage after the texture load and assignment have completed | 424CEC
once | cSubScrItem 425070: +50 advances the initialization stage after the image and child sprite setup completes, with +51/+53 reset for the following stage | 425475
