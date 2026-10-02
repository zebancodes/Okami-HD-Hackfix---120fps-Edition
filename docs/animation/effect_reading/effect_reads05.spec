follows | esp08/esp40 19FB20: these stores only normalize the already-scaled +2C8/+2CC phases by the whole-unit period of 2 | 19FB93 19FBAC
fixed | esp14 1A34F0: slot 1 increments the +2D8 age once per stock tick and scales the +174 displacement before adding it to +164 | 1A3502 1A3579
fixed | esfd 362E20/362F50: four separate 0.05 alpha approach additions/subtractions use scaled literals and then clamp to the target | 362F14 363072
fixed | es13 515970: the random 0.02 and mutable 0.05 material phase components are each scaled before addition to +10DC | 515A22
fixed | es49 4A9DD0: two FixTurnRate calls receive compounded 0.05 blend factors, one on each copied xmm2, before approaching +E0/+108 | 4A9EFB 4A9F15
fixed | es49 4A9DD0: the +10E8 lifetime countdown write executes once per stock actor tick | 4A9F31
