# wp00 weapon pieces (37F790..3803A0)
fixed | wp00 (37F9C0): +E28 loses the slow-motion dt each tick, scaled at xmm7's copy (dst 37F9EB) | 37FB5A
fixed | wp00 (37FFC0): the hit radius +E18's +3/-6 per-tick steps are s-scaled at 3800B1 and 3800E5 | 3800C0 3800F8
fixed | wp00 (37FFC0): +10FC's sound countdown loses the slow-motion dt, scaled at xmm6's copy (dst 37FFF0) | 3801C1
fixed | wp00 (3803A0): +10FC's sound countdown loses the slow-motion dt, scaled at xmm6's copy (dst 3803DF) | 38058D
# wp06 (385C50)
once | wp06 (385C50), launch: the normalized direction becomes the persistent velocity +E10/+E14/+E18 (x5, x10, x5) once as sub-state 0 starts; the per-tick moves are scaled separately | 385D93 385D9F 385DB7
once | wp06 (385C50), launch: position gains 10 times the three launch-velocity components and an 80-unit forward placement once, then +E36 advances to sub-state 1 | 385DC3 385DDF 385DFC 385E06
fixed | wp06 (385C50), sub-state 1: position gains s of persistent velocity +E10/+E14/+E18 each tick (pre 385E23/385E3A/385E53) | 385E27 385E3F 385E58
fixed | wp06 (385C50): the bob and its phase use the slow-motion dt scaled at xmm6's copy (dst 385C88) | 385F2C
