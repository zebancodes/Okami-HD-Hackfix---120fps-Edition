fixed | pl weapon sub-object update (3D27F0): material fade byte +1070 changes by 10 once per stock tick through count 3D2863/3D2878 | 3D2863 3D2878
follows | pl weapon sub-object update (3D27F0): +D2C is copied fresh from the owner, then multiplied by the rate-correct held +1070/255 fade rather than accumulated | 3D28A5
follows | pl00 (3C43C0): after motion advance refreshes the pose, submodel 0 y gets the full sin(+E3C degrees) x 0.8 pose offset; its phase is paced by count 3C465B | 3C4656
fixed | pl00 (3C43C0): +E3C's eight-degree sine-wobble phase step runs once per stock tick through count 3C465B | 3C465B
fixed | pl00 (3C43C0): +10B0/+10B8 gain s of ground-vector acceleration and position gains s of the resulting stock-valued velocities through pre 3C497F/3C499D/3C49B4/3C49CB; their subsequent 0.9 damping is already rewritten | 3C4987
once | pl00 (3C4D90), sub-state 0: +E48 is reduced to 0.6 of its incoming speed once while the state initializes and advances immediately to sub-state 1 | 3C4F2C
stock | pl00 (3C4D90): +E48 damping uses mode table 7A8178 and, on terrain type 0xF, the additional mode table 7A8198; both are rewritten by mode_constants.h | 3C4FDD 3C4FFE
stock | pl00 (3C5350): +B8 damping uses mode table 7A8240, rewritten by mode_constants.h | 3C5389
fixed | pl00 (3C5350): while held UI-state global B6B2AC bit 30 is set, the conditional +E48 x 0.1 damping runs on the first stock-period tick through count 3C567C | 3C5684
stock | pl00 (3C5350): +E48 damping selects mode table 7A8170 when +E3E is zero and 7A8158 otherwise; both are rewritten by mode_constants.h | 3C56BE
stock | pl00 (3C57A0): +B8 damping uses mode table 7A8240, rewritten by mode_constants.h | 3C57FF
once | pl00 (3C57A0), sub-state 0: the linked-actor turn at 3C5C9D runs once after advancing immediately to sub-state 1; keep its full 0.279253-radian limit | 3C5CAF
stock | pl00 (3C57A0), terrain type 8: +E48 damping uses mode table 7A8238, rewritten by mode_constants.h | 3C5DD3
fixed | pl00 (3C57A0): while held UI-state global B6B2AC bit 30 is set, the conditional +E48 x 0.1 damping runs on the first stock-period tick through count 3C5E72 | 3C5E7A
