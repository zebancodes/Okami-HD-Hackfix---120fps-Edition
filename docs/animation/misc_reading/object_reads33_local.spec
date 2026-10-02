once | ut2a state 2 lowers Y by two units then changes +E36 to state 3 in the same call; later calls only maintain the half scale. | 58391B
once | cGear initialization vtable slot 6 adds the fixed initial yaw for types 8C0/8D5 while creating attachments and initializing phase fields. | 495704
once | cCarryObj halves +E54 only on the 20F6C0 impact result with the designated collision kind, then performs bounce response 33EAD0/33E620. | 33DAF2
once | cKi type response negates +1130 only after 45A7C0 reports a contact; this is collision direction reversal. | 209B1F
once | utbc reflects X/Z velocity only when wall-contact bit F90.80 and the incoming-angle test succeed; the 0.95 factor is impact energy retention. | 22D5FA 22D63A
