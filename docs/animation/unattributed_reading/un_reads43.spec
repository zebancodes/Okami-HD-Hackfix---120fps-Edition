# 2026-10-01, fourth batch (rows in un_rows43.spec)
follows | Camera modes 46AA00, 46CC50, 46F2D0: yaw and pitch +1B0/+1B4 are recomputed from the eye and view points (atan2) and wrapped to +-pi; the wrap adds or removes whole turns. | 46AD59 46ADA0 46CE36 46CE63 46F5CC 46F5E4
follows | Camera modes 46E890 and 474350: the wraps of +1B0/+1B4 after 468070, whose stick-driven turn is already patched (468224..46836D). | 46EC3E 46EC56 4746E4 4746F9
follows | Camera mode 46EF40: +1B0/+1B4 are copied from the camera state B65C00, then wrapped. | 46F0E1 46F0F9
fixed | Camera 4763F0: the transition count +290 is count row 476805. | 476808
stock | Camera 4763F0: the field of view +1D0 is blended from the old and new modes by +290 / +292 each tick, from the paced count. | 4769C0
once | Camera dispatcher 476B00: +39A cycles the camera mode once per accepted press. | 476D07
stock | Camera finish 4831B0: the sine shake offsets go into +170/+174 of the view matrix +140, which 472D90 rebuilds from the eye and view points every tick. | 4832D2 483300
fixed | Environment 4AC680: the fade +FE0's step is srcx row 4AD324. | 4AD32C
follows | 4CBB70 is a task like 507080: its two wait(1) loops (task_waits.h 4CBC20, 4CBD72) pass once a stock tick; these are the first pass's steps. | 4CBBB1 4CBBC9
once | 5144B0, an event callback: B71B64 and B71B68 count only when its progress argument is 0.0, at an event's start. | 514DCE 514E29
once | 520510, a task: its two objects drop by 30 once, between timed waits and outside its loops. | 520742 52075B
follows | 520F90 is a task: its +D2C fade loops wait by wait(1) at 521150 and 521260, task_waits.h loops; these are the first pass's steps. | 521105 52120E
once | Map scripts 521400 and 5A11E0: their counts (B71BF0+388/+38C, B73028+6/+7) tally brush techniques as they are recognized. | 52144F 52147F 5A1273 5A129D
once | 53A200 (the +0 slot of eight event tables) counts events in B71D68+8/+9. | 53A2C4 53A2D3
stock | Map 201's script (544060, from 547980): B71D60+250 is recounted from zero on every call (the set flags 5..23 and one more). | 5440B9 5440DE
follows | Cutscene task 54EDC0: in the walk-out loop, the actors' root-motion step +EC8 (the current rate's share) is doubled and moved by 2DA3D0 once a pass, a pass a tick for 15 stock ticks (count row 54F932). | 54F8AB
fixed | Cutscene task 54EDC0: the 0.1 fade a pass is src row 54F8FE. | 54F903
once | Map scripts 573FE0 and 58BB90: 7A8CB0+4 counts accepted brush attempts. | 5740CA 58BC77
fixed | Map scripts 573FE0 and 58BB90: their countdowns 7A8CB0+8 are count rows 574148 and 58BCF8. | 57414B 58BCFB
once | 61EFE0 (from 6221A0's setup) shifts two layout elements by 64 when the screen opens. | 61F047 61F05E
fixed | Map F08's script 634E90: the double-precision fades of B75140+50 are src rows 634F92 and 634FDE. | 634FA4 634FF1
follows | 63FAD0 is a task: its fades of +D2C sit in loops whose wait(1) at 63FDD9 and 640188 are task_waits.h loops, once a stock tick. | 63FD87 640147
