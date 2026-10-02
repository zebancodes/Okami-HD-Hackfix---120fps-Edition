fixed | cSSScroll 414080: the state helper is called by the per-frame scroll update and now runs once per stock UI tick, including its velocity, position and pause timer | 4140F4 414103 414111 414138
fixed | cSubScrFude 423360: the two queued brush sprite branches now pace their ten-step countdown and 8.5 vertical displacement together | 4234D4 4234DA 423554 42355A
fixed | cCockLifeGauge 3FF720: the active life pulse counter now advances at its stock one- or two-step rate | 3FF7C7 3FF869
once | cCockLifeGauge 3FF720: sprite +20 gets a one-time 62-pixel offset when the life state changes and the branch returns immediately after saving +70 | 3FF9C2 3FF9E5
