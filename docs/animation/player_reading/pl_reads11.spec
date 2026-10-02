once | pl00 (3D0440): position target +E24 gains its initial vertical offset once in state 0 | 3D06ED
fixed | pl00 (3D0440): +E10/+E14/+E18 hold the normalized target-direction step at stock value for the arrival distance check, while pre 3D07A0/3D07B7/3D07D0 scale only their movement | 3D0788 3D0794 3D0798 3D07A4 3D07BC 3D07D5
fixed | pl00 (3D0440): the +E3C active-state countdown decrements on stock ticks at count 3D08A7 and its zero-time exit waits at notyet 3D0895 | 3D08A7
