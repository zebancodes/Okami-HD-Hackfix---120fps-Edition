once | 242CB0 phase 0 initializes a newly normalized launch direction, multiplies E10/E18 by the chosen speed, then switches E36 to 1; these are launch settings, not accumulated movement. | 242DC5 242DF0 242E04
once | 242760 phase 0 normalizes and doubles the launch direction once, then sets E36 to 1; 239420 performs the following time-correct movement. | 242913 24291B
once | 2453B0 phase 0 normalizes and doubles the launch direction once, then sets E36 to 1 before the motion loop. | 2455A6 2455AE
once | 245660 phase 0 normalizes and doubles the launch direction once, then sets E36 to 1 before the motion loop. | 245843 24584B
once | 245900 phase 0 normalizes and doubles the launch direction once, then sets E36 to 1 before the motion loop. | 245AE3 245AEB
once | 245BA0 initializes the normalized launch direction, doubles it, loads the 70-tick wait and sets E36 to 1; later calls bypass these stores. | 245D8A 245D92
once | 40B1E0 constructs/reloads the menu resource through 1B5380 before applying the mode-3 layout offsets to four fresh element positions; each offset is a spatial layout adjustment. | 40B2F0 40B30B 40B326 40B33E
once | 40F820 runs from 40F5D0's mode-initialization setter when mode 2 is selected; it selects frame 0 and applies the three 25-pixel layout offsets. | 40F859 40F887 40F8B1
once | utf6 236A50 applies the submodel height offset on phase entry/activation and restores it on phase completion; E36 changes immediately, so these offsets are event mutations. | 236BDA 236C6E 237364
once | utf6 activation changes E36 from 1 to 2 and increments the activation count 1118 once, clamped to 100. | 236D16
once | utf6 activation increments one of the two saved event-completion totals, and only for the corresponding C8/C9 variant; the state has already changed to 2. | 236D94 236E30
once | cKiType036 phase 2 adds the object's height to world Y and E50 once, then advances to phase 3 and plays the landing event. | 36C350
stock | cBallObj applies coefficient 1134 to vertical velocity only in the ground-contact response, alongside the floor clamp, low-speed stop and bounce sound latch; preserve the impact coefficient in stock units. | 33B0C7
