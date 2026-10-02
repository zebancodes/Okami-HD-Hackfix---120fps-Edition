group player
# wp1b (38E8D0)
srcx 38EAD0 | wp1b (38E8D0), launch: grounded slope +FE0 contributes to the persistent per-tick-at-this-rate x velocity; add s of the stock launch push
srcx 38EAD8 | wp1b (38E8D0), launch: grounded slope +FE8 contributes to the persistent per-tick-at-this-rate z velocity; add s of the stock launch push
dst 38EB8E | wp1b (38E8D0), flight: xmm0 loads grounded slope push +FE0; scale it once toward the s^2 change of a persistent per-tick-at-this-rate velocity
dst 38EB96 | wp1b (38E8D0), flight: xmm1 loads grounded slope push +FE8; scale it once toward the s^2 velocity change
pre 38EB9E | wp1b (38E8D0), flight: the already s-scaled slope push in xmm0 is scaled again before it is added to persistent x velocity +E20, giving s^2
pre 38EBA6 | wp1b (38E8D0), flight: the already s-scaled slope push in xmm1 is scaled again before it is added to persistent z velocity +E28, giving s^2
# pl02 (3A2C70)
srcblend 3A2FE5 | pl02 (3A2C70), state 5: position.x repeatedly approaches the sampled target with dynamic factor +E10; convert it to 1-(1-k)^s
srcblend 3A3006 | pl02 (3A2C70), state 5: position.y uses the same dynamic +E10 approach factor
srcblend 3A3029 | pl02 (3A2C70), state 5: position.z uses the same dynamic +E10 approach factor
srcblend 3A3324 | pl02 (3A2C70), state 9: position.x approaches submodel 7 with dynamic factor +E10
srcblend 3A3345 | pl02 (3A2C70), state 9: position.y uses the same dynamic approach factor
srcblend 3A3368 | pl02 (3A2C70), state 9: position.z uses the same dynamic approach factor
# wp11 (38C430)
count 38C553 | wp11 (38C430): lower +E3C is the 30-tick interval that holds +E54 at zero; commit its decremented register value only on stock ticks
pre 38C613 | wp11 (38C430), flight: position.x gains s of persistent stock-valued launch velocity +E10
pre 38C634 | wp11 (38C430), flight: position.y gains s of persistent stock-valued launch velocity +E14
pre 38C64D | wp11 (38C430), flight: position.z gains s of persistent stock-valued launch velocity +E18
# pl00 attack combo (3B7320)
callscale 3B7EB5 (0x2DDF90,"xmm3") | pl00 attack combo (3B7320), state 7: turn toward the locked target by at most 0.279253 radians a tick; scale this continuous call's limit
callscale 3B81DA (0x2DDF90,"xmm3") | pl00 attack combo (3B7320), state 9: turn toward the locked target by at most 0.279253 radians a tick; scale this continuous call's limit
count 3B849A | pl00 attack combo (3B7320): while +D40 bit 3 is set, commit +E48 x 0.5 once per stock tick
count 3B84E3 | pl00 attack combo (3B7320): while +E58 has collision bits 0x14000, commit +E48 x 0.1 once per stock tick
# pl02 (3A4480)
blend 3A4676 | pl02 (3A4480): +2110/+2114/+2118 approach +2120/+2124/+2128 by the shared 0.05 factor each tick; use 1-(1-0.05)^s
pre 3A473D | pl02 (3A4480): position.x gains s of the normalized horizontal direction times stock-valued speed +2108
pre 3A475A | pl02 (3A4480): position.z gains s of the normalized horizontal direction times stock-valued speed +2108
countlast 3A4779 | pl02 (3A4480): +2108 gains 2 after the move, up to 60; change it on the last tick of each stock period so that period's moves use one stock speed
blend 3A4937 | pl02 (3A4480): when below the ground target, y approaches it by 0.6 a tick; use 1-(1-0.6)^s
blend 3A4941 | pl02 (3A4480): otherwise y approaches the ground target by 0.1 a tick; use 1-(1-0.1)^s
