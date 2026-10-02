# Camera modes, second part (2026-09-30)
group objects
# 4797A0
blend 47983D | Camera mode 4797A0: field of view +1D0 approaches its speed-dependent target by 0.2 a tick.
blend 479A1B | Camera mode 4797A0: distance +200 approaches the global 7A7C0C by 0.1 a tick.
dst 479C99 | Camera mode 4797A0: yaw +1B4 gains the stick-driven yaw velocity 9C8718 each tick (its damping and input are the 468xxx rows): scale the step.
dst 479D2A | Camera mode 4797A0: pitch +1B0 gains the stick-driven pitch velocity 9C8714 each tick: scale the step.
# 46A090
count 46A417 (0x46A40C,0x46A419,(0x46A40C,0x46A413,0x46A415,0x46A417),None) | Camera mode 46A090: pace the 15-tick byte +413 armed when a tracked point comes close, during which it follows that point.
