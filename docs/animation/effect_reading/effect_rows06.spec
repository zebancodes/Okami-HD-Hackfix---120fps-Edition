group effect
# The shared effect manager ages live entries, and esp18's slot 1 advances
# two wrapped phases using mutable steps. Its third phase is already patched.
count 19C3C5 | shared effect manager: advance +22 age on stock ticks
src 1A442A | esp18: scale the +2D8 phase step before wrapping +2D0
src 1A4470 | esp18: scale the +2DC phase step before wrapping +2D4

group actor
# es39's 0..15 byte fade drives color interpolation. Only the byte's write
# needs to wait; each update can still render from the held value.
count 35FBF9 | es39: advance the 15-step color fade on stock ticks
# ese0's separate handlers advance +E35 per tick. One handler contains no
# earlier patch and can be gated as a whole.
count 3616FB | ese0: advance its first +E35 phase on stock ticks
gatefn 361780 | ese0: advance its second +E35 phase on stock ticks
count 361DA7 | ese0: advance its final +E35 phase on stock ticks
# esfd approaches a state-selected alpha target by 0.05 in both directions.
lin 3636C6 | esfd: scale the +0.05 alpha approach
lin 3636D8 | esfd: scale the -0.05 alpha approach
