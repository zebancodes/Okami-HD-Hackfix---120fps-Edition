group player
dst 39B98A ("slowmo",0x39B976) | wp47 (39B950): cache the current-rate delta in callee-saved xmm6; its only live reader subtracts it from the +10EC sound/effect cooldown, and no animation-rate reader consumes this copy
lin 39C3AD | wp47 (39C0B0): scale the repeated +3 growth step of collision radius +E18; the 53-unit clamp remains spatial
lin 39C3E1 | wp47 (39C0B0): scale the repeated -6 shrink step of collision radius +E18; the 21-unit clamp remains spatial
lin 39C78F | wp47 (39C540): scale the repeated +3 growth step of collision radius +E18; the 53-unit clamp remains spatial
lin 39C81F | wp47 (39C540): scale the repeated -6 shrink step of collision radius +E18; the 21-unit clamp remains spatial
count 39C8C5 | wp47 (39C540): +E3C is initialized to 10 then decremented once per stock tick before the terminal state transition
pre 39D697 | wp49 (39D600): scale the random per-tick +B0 perturbation before accumulating it
pre 39D6C9 | wp49 (39D600): scale the random per-tick +B8 perturbation before accumulating it
pre 39D763 | wp49 (39D600): scale the alternate random per-tick +B0 perturbation before accumulating it
