group objects
lin 244DF2 | 244C80 shrinks all three persistent submodel scale channels by the same 0.03 increment per stock tick before their 0.2 clamps.
lin 2450F4 | 244C80 restores all three persistent submodel scale channels by the same 0.03 increment per stock tick before their one-unit clamps.
gatefn 623540 | Shared minigame six-object update: advance movement, target ownership timeout, random respawn and loop placement together on stock ticks.
srcx 6263C0 | Minigame backdrop scrolling: divide the speed operand by N before subtracting it from track Z; preserve the full loop length used for wrapping.
count 62668C (0x626681,0x62668E,(0x626681,0x626688,0x62668A,0x62668C),None) | Minigame close delay: count the positive 30-tick byte once per stock tick and preserve not-complete flags when held.
