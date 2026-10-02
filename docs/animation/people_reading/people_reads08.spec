stock | cHumanLotus 312790: slot 15 copies a target's current angle difference into +B4 and saves that target angle at +1318; this follows the target rather than advancing by a per-tick rate | 312A36
once | cHumanLotus 312790: slot 15 adds a fixed 1.5 Y offset while setting up the target-relative pose | 312A83
once | hm07 319680 and hm08 31AE10: slot 24's action 0x200 copies a reference transform and adds its rotated +EA0 offset once on entering that action | 3197A3 3197B9 3197D0 31AF33 31AF49 31AF60
once | hm07 319C40: slot 26's action-0x1d handler copies a reference position, adds a fixed 18 Y offset, then dispatches the action | 319CE8
fixed | hm19 31EDD0: both state-specific +Y additions use scaled vertical displacements | 31EEA4 31EF06
once | hm19 31EDD0: -1000 from +E24 is applied while entering state 2, immediately before the state byte advances | 31EF65
stock | hm19 31EDD0: X/Z at 31F01C are computed from saved +E10/+E18 and the target vector using the current motion playhead +F48; no previous output position feeds the blend | 31F01C
fixed | hm27 323240: +E3C is already a paced remaining-tick count, and its per-call target blend is compounded from 1/(remaining+1) | 32338F
fixed | hmbd 335530: +E3C is already a paced remaining-tick count, and its per-call target blend is compounded from 1/(remaining+1) | 3356BB
fixed | hm48 32A910: each computed XYZ step is scaled before addition to position, and the 0.2 FixTurnRate factor is compounded | 32AC36 32AC4B 32AC61 32AD38
fixed | hmce 3370B0: X/Z 0.05 target blends and the yaw 0.1 turn blend use per-tick compounded factors | 337196 3371B9 3371D1
fixed | hm68 32FE00: the +B4 yaw phase uses a scaled 0.9599311 step before angle wrapping | 32FE7A
once | hm07 hm2d hm32 hm68 hmbd: these +E37 increments occur only in stage-zero action branches, after turning, motion setup, or a one-time effect; the new stage suppresses the same branch on the next tick | 30C084 3244E3 325D3C 32F09E 32F546 3303F8 3310F2 3355EB
once | hm36 326340: +1310 advances once while entering stage zero; the +1311 countdown that follows is paced separately | 326399
once | hm68 3303B0: +1310 becomes the remainder of an action-index increment only when a distance threshold is reached; the same branch also switches +E36 and resets +E37 | 330490
fixed | hm27/hmd1 slot 18: +1316 toggles the submodel pose only on stock ticks | 322B39 337EE1
fixed | hm30 hm31 hm3a hm3b slot 18: their +1810/+1770/+1814 clocks advance once per stock tick | 32501E 3255A7 326B3E 327136
fixed | hm36 326340: the +1311 wait decrements only on stock ticks after its stage-zero reload of 90 | 3263A6
fixed | hm3b 327180: the 60-step +1818 wave counter advances only on stock ticks | 327186
fixed | hm48 32B190 and hm52 32BD80: the +13B2 wait and 240-step +16D0 phase advance only on stock ticks | 32B2DB 32BDF3
fixed | hm62 32D910: +1310 increments once per stock tick, and the conditional subtraction of 240 at 32D938 only wraps that paced phase | 32D91A 32D938
