fixed | pl02 (3A3550), first steering path: +E20/+E24/+E28 gain s of their acceleration, keep the 0.95 damping for the last tick, and move position by s of the resulting persistent velocity | 3A379B 3A379F 3A37A7
fixed | pl02 (3A3550), second steering path: +E20/+E24/+E28 gain s of their acceleration, keep the 0.95 damping for the last tick, and move position by s of the resulting persistent velocity | 3A3981 3A3985 3A398D
once | pl02 (3A3CA0): the selected target's +1147 byte increments only when it is still zero, as the terminal path-point event is processed; it is not an elapsed-tick counter | 3A3F69
fixed | pl02 (3A3CA0, sub-states 2/3): +B4's per-tick turn limit is s-scaled at the 2DDF90 call 3A4179 | 3A4190
fixed | pl02 (3A3CA0, sub-state 3): all three position coordinates use dynamic approach factor +E10, converted independently at 3A41B8/3A41E9/3A421C to 1-(1-k)^s | 3A41C4 3A41F6 3A4229
fixed | pl02 (3A3CA0, sub-state 5): +B4's per-tick turn limit is s-scaled at the 2DDF90 call 3A440A | 3A441C
