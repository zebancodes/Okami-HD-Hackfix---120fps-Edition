once | wp03 (384010), launch: the normalized owner-relative direction is multiplied by 5.5 into persistent velocity +E10/+E14/+E18 once as sub-state 0 advances to 1 | 3840BF 3840D3 3840DB
once | wp03 (384010), launch: position.y gains 0.5 once during the sub-state-0 placement | 3840F0
fixed | wp03 (384010, sub-state 1): position gains s of persistent stock-valued launch velocity +E10/+E14/+E18 through pre 3841E7/384203/38421C | 3841F0 384208 384221
once | wp10 (38BA10), launch: +E14 gains 125 once before the owner-relative direction is normalized | 38BA9D
once | wp10 (38BA10), launch: the normalized direction is multiplied by 25 into persistent velocity +E10/+E14/+E18 once as sub-state 0 advances to 1 | 38BAD0 38BAE4 38BAEC
fixed | wp10 (38BA10, sub-state 1): position gains s of persistent stock-valued launch velocity +E10/+E14/+E18 through pre 38BC06/38BC22/38BC3B | 38BC0F 38BC27 38BC40
once | wp12 (38CF10), launch: +E14 gains 7 once before the owner-relative direction is normalized | 38CF9D
once | wp12 (38CF10), launch: the normalized direction is multiplied by 6 into persistent velocity +E10/+E14/+E18, then +E36 advances once | 38CFCB 38CFDF 38CFE7 38CFFB
fixed | wp12 (38CF10, sub-state 1): position gains s of persistent stock-valued launch velocity +E10/+E14/+E18 through pre 38D0E1/38D0F8/38D111 | 38D0E5 38D0FD 38D116
once | wp1a (38DCB0, sub-state 1): +E54 gains twice +E48 times +E14 once, clamps at zero, then +E36 advances immediately to 2 | 38DD32
once | wp1a (38DCB0), launch: the owner-speed-derived scalar initializes +E10/+E18 and accumulates them into +E20/+E28 once; owner +E48 already carries this rate's per-tick scale | 38DF99 38DFAD 38DFB5 38DFBD
stock | pl00 (3C2E80): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3C2EEB
once | pl00 (3C2E80): +1145 increments only after an accepted input/event gate while below 2 and requests state 0x301; it is an event count, not elapsed time | 3C2FE0 3C3090
stock | pl00 (3C2E80): +E48 damping reads port mode table 7A81B8, already rewritten for the current rate by mode_constants.h | 3C335C
