stock | 301980 clamps an actor back to a circle: distance minus allowed radius is the fresh correction along its normalized separation. Caller 301890 selects geometric exclusion circles, not elapsed movement. | 301A34 301A44
once | 30D650 increments E36 on phase-zero motion setup, then again only when 4B9C80 reports its motion has finished. | 30D97E 30D9DC
once | 316490 changes 1324 only in phase zero, then writes E36=1 before the persistent update. | 3165AA
stock | 316490 calls 30F230, which advances 4B9C80 and refreshes EC8 root motion, before applying spatial factor 3.5. The factor is independent of elapsed time. | 316646
stock | 317080 returns two freshly computed atan2 headings through output parameters, with fixed angle offsets and wrapping. Neither output is an accumulated phase. | 317175 317182
once | Menu row offsets change by five only under a new B6AD58 command to select the adjacent row; they encode row spacing, not an animation clock. | 40F989 40FA7F
stock | 445540 applies the fixed pitch offset to a temporary record freshly copied by caller 444DE0 through 454F00. The record is not persistent state. | 445690
stock | Sound resource +60 is a reference total decremented on releasing a resource slot. 44DE40 immediately detaches its aliases with 44F1B0 and 44F460; reaching zero releases the remaining aliases. | 44DEE9 44DF36
stock | Both 455980 callers first copy new requested volume values into a mixer slot: 454B80 replaces them from param2+10/+12; 454C70 initializes them from the new play record. Multiplying by bank volume/127 converts those fresh values, not a fade. | 4559DA 4559F8
