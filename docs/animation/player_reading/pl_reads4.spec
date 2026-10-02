# wp09 (387140)
fixed | wp09 (387140): +E28 loses 0.1 x the slow-motion dt and the forward move uses +E28 x that dt; dst 38717B scales both readers | 387498
# wp0f (38A8F0)
fixed | wp0f (38A8F0): the +10FC sound cooldown loses the slow-motion dt scaled at dst 38A935 | 38AAE2
# wp0f (38ABD0)
fixed | wp0f (38ABD0): the +10F8 countdowns, clamped turn and +10FC sound cooldown use the slow-motion dt scaled at dst 38AC19 | 38AC7F 38AD3B 38AE99 38AF30
stock | wp0f (38ABD0): +B0 is the result of 2DA510; FixTurnRate converts its 0.4 blend factor at the helper entry | 38AE78
# wp1d (38FE50)
once | wp1d (38FE50), state 0: position.y += 1.5 once while the flight is initialized, then the state advances | 38FFC6
fixed | wp1d (38FE50): +B0's rotation step is scaled by lin 390021 and +E28 loses the slow-motion dt scaled at dst 38FE84 | 39003A 390048
fixed | wp1d (38FE50): the flight position gains s of its stock-valued +E10/+E14/+E18 velocity through pre 3900B3/3900CA/3900E3 | 3900B7 3900CF 3900E8
# wp1d (390490)
fixed | wp1d (390490): +D2C's 0.05 fade-in and fade-out steps are scaled at srcx 3904F7 and 390AE2 | 390503 390AEA
stock | wp1d (390490): +B0 is the result of 2DA510; FixTurnRate converts its 0.05 and 0.2 blend factors at the helper entry | 390720 3909EC
fixed | wp1d (390490): the +1078 countdown, bob, +1110 phase, flight acceleration, +E28 countdown and clamped turn all use the slow-motion dt scaled at dst 3904C5 | 39074E 39078E 3907A4 390820 3908AC 390A12
