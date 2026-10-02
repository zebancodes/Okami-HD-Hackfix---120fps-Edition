# 2026-10-01, seventh batch (rows in un_rows46.spec)
fixed | Map scripts 5443F0 and 590F10: their countdowns are count rows 54447A and 590FF5. | 54447A 590FF7
fixed | Map scripts 59ABA0, 5BC850, 5C22D0, 622D00 and the task 5F8190: their fades and the clamped turn are src rows 59AC5B, 5F81F0 and lin rows 5BCA47/5BCA54, 5C24A9/5C24B6, 622D84. | 59AC5F 5BCA82 5C24E4 622E05 5F81F8
fixed | Menu 601D50: the alpha byte +3B's fade is count row 60216A (its subtraction, in ecx). | 6021CD
once | 50B490 (from 50B6D0's setup) shifts a layout element by 64. | 50B549
once | 50BDA0 (from 50AF10, 50B6D0) adds an entry and counts the entries in +106. | 50C047
once | 511020 runs once, at the end of the task 512910: B71B50+14 advances. | 511179
once | 513610 (from the minigame tasks 5129B0, 512D00, 513010, 512890): B71B50+15 cycles 1..3 once per round. | 513A17
once | 53A370, 544790 (event tables' +0 slots and their callers): B71D68+8/+C count events. | 53A410 5447F2
follows | 5887E0 and 627F70 are tasks: their fade loops (task_waits.h 588FE0, 628640) pass once a stock tick; these are the first pass's steps. | 588F91 6285EA
stock | 5E1440 scales the motion factor +F54 by the speed +1080 only around its three motion advances, then restores it. | 5E1468
once | 5EA3B0 (from 5DEED0, 5DF5F0, 5EA530) adds a hit's amount (edx) to +3850. | 5EA3EE
once | 6018A0 (from 600FF0): +16 advances once when its check passes. | 6019CF
once | 602D80, 6058A0, 606530, 606760: menu pages' layout setup (an element +5C moved by 135 when the page is built). | 602DDE 605952 606625 606869
once | 6111E0 (from 610D30) sets a scene up: the object 0x39 turns half around once. | 61127C
once | 618E90, 626A00, 629610, 643390, 63E4A0: counts of plays, rounds and events in the minigames' globals (B75028+D8, B75110+1B8, B75168+3, B75160+140), once per event. | 618FAD 626D9A 629680 6433DC 63E549
follows | 61A550 is a task: its loops at 61AB50 and 61AD11 are task_waits.h loops; this +D0 step is the first pass's, before them. | 61AA99
once | 635950 (from 637690): +11A6 counts state changes up to 5. | 635B47
once | 63A850 (from 63A670) lifts the player by 30 once before placing it (20F9F0). | 63A8F4
once | 658330 is an event callback: for object 0x40D and event 0x5C it moves the object's z by its argument once. | 658381
stock | 65CF74 is C runtime code (the TLS/atexit callback walk; E68EA4 counts the callbacks). | 65D07E
once | et47 (2EE660, from 2EE520): +1100 counts its hits (up to 3) on the hit flags +10E8 and counts them back down on another flag, each step with a 10..60-tick cooldown +1070. | 2EE6E9 2EE761
once | ut51 (21D230, from 21D0E0): +10F0 tallies discrete brush hits, with a sound and a state change. | 21D44D
