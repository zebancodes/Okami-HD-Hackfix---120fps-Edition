once | wp5e (3A1B50), sub-state 0: +B4 turns toward Amaterasu with a 120-degree limit once, then +E36 advances to sub-state 1 | 3A1D24
fixed | wp5e (3A1DF0): lifetime +1108 loses the slow-motion dt, scaled at xmm7's copy (dst 3A1E16) | 3A1EAA
fixed | wp5e (3A1EF0): +D2C loses 0.03 x the slow-motion dt, scaled at xmm6's copy (dst 3A1F11) | 3A1F9D
fixed | wp5f (3A2530): +1108's two slow-motion-dt decrements are scaled at xmm7's copy (dst 3A2551) | 3A25B2 3A26D2
once | wp5f (3A2700), launch: +E14 gains 15 once before the direction to the owner is normalized | 3A2783
once | wp5f (3A2700), launch: the normalized direction is multiplied by 15.5 and stored as persistent velocity +E10/+E14/+E18 once as sub-state 0 starts | 3A27B8 3A27CC 3A27D4
once | wp5f (3A2700), launch: position.y gains 0.5 once during the sub-state-0 placement | 3A27E9
