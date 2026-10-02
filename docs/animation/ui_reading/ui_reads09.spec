fixed | cCockGameOver 3FCC40: the +7E and +7C transition waits now count down once per stock HUD tick before advancing to the next game-over state | 3FCE4E 3FCE9C 3FCED3
fixed | cSubScrFilesInfoWanted 4207D0: +7B in state 1 now counts down only on stock UI ticks | 4207FD
stock | cSubScrFilesInfoWanted 4207D0: +64 is the selected file row and changes only after controller LargeBitElement action tests, one row at a time | 420937 4209C0
fixed | cSubScrItem 40D9F0: while state 1 is active, the selected sprite alpha now rises by 16 only on stock UI ticks before the 0x80 threshold test | 40DA2A
stock | cSubScrItem 40D9F0: +39 is the selected item row and increments only after the controller action test and its associated navigation sound | 40DB64
once | cCockMoney 402B00: the +70/+74 sign randomization and +7C 0.8 spin kick occur only in the money-change branch after the HUD value increases; +70/+74 are freshly seeded from RNG immediately before the sign flips | 402C8B 402CA6 402CBD
once | hm07 placement helper 33E370: X/Y/Z +E10/+E54/+E18 are adjusted from a reference transform during an action setup that also sets +11C4 to stage 4 | 33E448 33E46C 33E490
