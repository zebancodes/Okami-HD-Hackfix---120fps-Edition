stock | pl00 (3BC710): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3BC788
once | pl00 (3BC710, sub-state 0): +B4/+B0 receive 2DE0A0's pi/pi-over-two turn once as the state advances to 1 | 3BC8E3 3BC8FF
fixed | pl00 (3BC710, sub-state 1): +B4/+B0 receive 2DE0A0's continuous changes with the caller-local 9/16-degree limits s-scaled at 3BCA39/3BCA47 | 3BCA8A 3BCAA6
once | pl00 (3BC710, transition from sub-state 1): +B4/+B0 receive 2DE0A0's pi/pi-over-two turn once as the state advances to 2 | 3BCBDE 3BCBFA
fixed | pl00 (3BC710): +1152 advances on stock ticks; its zero and every-eighth-tick sound/effect tests are gated between them | 3BCCBD
stock | pl00 (3BEEE0): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3BEF3B
once | pl00 (3BEEE0): +11EB increments only after a successful 2DC7B0 collision query; it is a connected-hit count, not elapsed time | 3BF2B2 3BF35C
fixed | pl00 (3BEEE0): +E54 halves once per stock tick while the five-tick hit cooldown +11E9 is active | 3BF3D7
once | pl00 (3BEEE0, sub-state 0): +B4 turns toward the target with a pi-radian limit once as the state advances to 1 | 3BF4EC
fixed | pl00 (3BEEE0, sub-state 7): +E3E loses one on stock ticks and its zero-time transition is held between them | 3BFB9C
stock | pl00 (3BEEE0): +E48 damping uses port mode table 7A8218, already rewritten for the current rate by mode_constants.h | 3BFBC9
fixed | pl00 (3BEEE0): the common-tail 2DDF90 turn's 16-degree per-tick limit is s-scaled at call 3BFC4E | 3BFC61
fixed | pl00 (3A80F0, first path): +D20/+D24/+D28 approach 1 with the shared factor converted at 3A81AB to 1-(1-0.05)^s | 3A81C5 3A81ED 3A81FD
fixed | pl00 (3A80F0, fallback path): +D20/+D24/+D28 approach 1 with the shared factor converted at 3A8296 to 1-(1-0.05)^s | 3A82B0 3A82D8 3A82E8
fixed | pl00 (3A80F0): +115A's ordinary -1 and conditional extra -5 countdown steps commit only on stock ticks | 3A835F 3A8378
stock | pl00 (3CA320): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3CA399
once | pl00 (3CA320, sub-state 0): +B4's conditional 16-degree 2DDF90 turn happens once as the state advances to 1 | 3CA4D0
once | pl00 (3CA320, sub-state 4): +B4 turns toward the target with a 60-degree limit once as the state advances to 5 | 3CA8D6
fixed | pl00 (3CA320, sub-state 5): +E48 is multiplied by 0.1 only on stock ticks before the current-rate move | 3CA9B9
once | pl00 (3CA320, sub-state 6): +B4 turns toward the target with a 60-degree limit once as the state advances to 7 | 3CAA58
once | pl00 (3CA320): +E48 is multiplied by 0.7 only in the successful-hit block after 2DC7B0, as a connected-hit response | 3CACCF
stock | pl00 (3CA320): root-motion step +EC8 gains +E48, which is already a per-tick displacement at the current rate, before 2DA3D0 applies it | 3CACEA
stock | pl00 (3C05C0): +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3C0619
once | pl00 (3C05C0, sub-states 0/2/4): +B4 turns toward the target with a pi-radian limit once as each state advances | 3C06D0 3C083D 3C09A3
stock | pl00 (3C05C0): +E48 damping uses port mode table 7A8218, already rewritten for the current rate by mode_constants.h | 3C0B47
fixed | pl00 (3C05C0): the common-tail 2DDF90 turn's 16-degree per-tick limit is s-scaled at call 3C0BCF | 3C0BE1
