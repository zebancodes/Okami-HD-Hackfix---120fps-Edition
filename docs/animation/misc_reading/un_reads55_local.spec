stock | Dormant debris helper: generator49 proves the entire function has no external direct entry, actual data/switch/LEA address reference or physical fallthrough; unwind descriptions cannot invoke it. This exclusion is rechecked on every generation. | 207BF1 207C42 207C5D 207C65 207C80 207C88 207C98 207D0B 207D23 207D2B 207D9A 55C081 55C0DE 55C0F9 55C101 55C11C 55C124 55C134 55C18E 55C1A6 55C1AE 55C1C7 56BCE1 56BD3E 56BD59 56BD61 56BD7C 56BD84 56BD94 56BDEE 56BE06 56BE0E 56BE27 56E161 56E1BE 56E1D9 56E1E1 56E1FC 56E204 56E214 56E26E 56E286 56E28E 56E2A7
stock | 20F450 calls corrected common motion advance 4B9C80 first; +EF0/4/8 are fresh differences ED0 minus EE0 for the corrected animation fraction, so their pitch/yaw/roll additions already represent this current tick's displacement. | 20F4EE 20F50B 20F52B
stock | 315E60 calls 307840, which calls corrected common advance 4B9C80, before multiplying its fresh root-motion EC4 delta by 0.2. This shapes the current tick's animation displacement. | 31621D
once | 6262D0 removes a point only when input/event query 1690C0 reports action 2; this is an action penalty. | 6264EB
follows | 6262D0 settles a newly completed target only while observed live completion count exceeds the stored count; this is target accounting. | 626518
once | 6262D0 awards five points when settling a newly completed target, with the input-action total determining the reward. | 626524
follows | 6262D0 wraps track Z by one full loop length only after the corrected scrolling step crosses its lower boundary. | 6263EE
once | 244C80 increments the entry latch from phase zero to phase two during shrink-state initialization before setting the animation and timer. | 244DCC
follows | 244C80 consumes its finite animation-repeat count only when motion-completion query 239420 returns true. | 244F2F
once | 242A20 phase-zero launch setup computes initial turn, jitter and normalized direction times launch speed; the same branch then sets phase one. | 242B20 242B57 242BA8 242BB0
once | 315E60 increments the zero entry latch during its stage initialization, changing that stage to initialized. | 315EB6 3161E7
