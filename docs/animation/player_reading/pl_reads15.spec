once | pl03 (3A51F0): the selected target's +1147 byte increments only when still zero, as the terminal path-point event is processed; it is not an elapsed-tick counter | 3A5473
fixed | pl03 (3A51F0, sub-state 3): +B4's per-tick turn limit is s-scaled at the 2DDF90 call 3A57A2 | 3A57B9
fixed | pl03 (3A51F0, sub-state 3): all three position coordinates use dynamic approach factor +E10, converted independently at 3A57E1/3A5812/3A5845 to 1-(1-k)^s | 3A57ED 3A581F 3A5852
fixed | pl03 (3A51F0, sub-state 3): +E10 gains s of 0.02 a tick at 3A5937 | 3A5959
fixed | pl03 (3A51F0, sub-state 5): +B4's per-tick turn limit is s-scaled at the 2DDF90 call 3A5AC6 | 3A5AD8
stock | pl00 wall recoil (3C20E0): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3C2136
once | pl00 wall recoil (3C20E0): +1145 increments once per accepted input event, capped at 2; it is not an elapsed-tick counter | 3C222D
once | pl00 wall recoil (3C20E0), sub-state 0: position.y gains 3 once during the initial placement | 3C22AE
stock | pl00 wall recoil (3C20E0): +E48 and +10E8 use port mode table 7A81B8, whose decay is already rewritten for the current rate; the stick term added to +10E8 is separately fixed by kStickDriftSites | 3C22F0 3C231A
stock | pl00 wall recoil (3C20E0): position.x/z gain the rotated +10E8 step, already a current-rate displacement through mode_constants.h and the verified stick-drift gain | 3C23C4 3C23F1
stock | pl00 (3C6080): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3C60B4
fixed | pl00 (3C6080, sub-states 2/3): +B4 and +B0 receive 2DE0A0's changes with the caller-local 8/4-degree limits s-scaled at 3C615C/3C616C | 3C61CB 3C6203
fixed | pl00 (3C6080, sub-state 1): +B4 and +B0 receive 2DE0A0's changes with the caller-local 8/4-degree limits s-scaled at 3C64F4/3C6504 | 3C6563 3C659B
fixed | pl00 (3C6080, sub-state 0): +11F0 advances only on stock ticks and the transition at 10 is held between them | 3C66C9
stock | pl00 (3C84B0): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3C8534
fixed | pl00 (3C84B0): +1152 advances on stock ticks; its zero, threshold and every-eighth-tick sound/effect tests are gated between them | 3C876B
fixed | pl00 (3C84B0): +B4's 32-degree per-tick turn limit is s-scaled at the 2DDF90 call 3C8FE1 | 3C8FF4
stock | pl00 (3C84B0): root-motion step +EC0/+EC8 is rewritten by the rate-adjusted motion advance every tick, then conditionally zeroed or halved before 2DA3F0 applies it | 3C945D 3C9466 3C94AA 3C94C4
