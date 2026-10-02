# 2026-10-01, third batch (rows in un_rows42.spec)
follows | 507080 is a task: its two wait(1) loops (task_waits.h 507130, 50726A) pass once a stock tick; these are the first pass's steps (+0.5 to the colour +D20..+D28 of B6D788's object), before the first wait. | 5070C0 5070D7 5070EE
once | 511670 sets up a scene (from 513A80's setup, once): it lifts objects out of the way (y += 1000) and spawns the scene's objects by state +40. | 51173B 511779 51186B
once | 51BA80, a cutscene task, places four objects at its leader's position plus the offsets at 7BA234 (a loop of 4 with no wait). | 51C021 51C035 51C04F
once | Map script 52EE10: +4 of the script manager 7A8CB0 counts accepted brush attempts (1690C0 returning 2). | 52EF11
fixed | Map script 52EE10: the countdown 7A8CB0+C is count row 52F042. | 52F045
fixed | Menu background 601170: its alpha, offset and angle steps are lin rows 6011AD, 6011ED, 601223. | 6011BC 6011F5 601235
once | 6036E0 and 6037C0 lay out a menu page when it opens (6049F0's setup): fixed offsets added to its elements. | 603851 603934 603950 603798
stock | 623000 (from the minigame loops 6262D0 and 626A00) re-copies the puppet's position and heading from the minigame's object each call before adding the motion's root offset +EA0 (sampled at its time +F48): nothing accumulates. | 6230AD 6230C3 6230DA
once | 652BE0 and 652C70 (a map script's table entries) lift or lower the three objects of id 0x85C by 10000: a hide or show. | 652C0F 652C37 652C57 652CD8 652D00 652D20
fixed | Event camera rumble 13B250: the pulse accumulator +20 is count row 13B3A7; the subtraction of 255 follows a crossing on that tick. | 13B3BE
stock | 168140 (the objects' updates ask whether the brush strokes touch their points) counts this tick's touched targets in the brush's +E20, which the brush update 16C7E0 clears every tick: a per-tick tally. | 168217 16827A
stock | cPad::setJoyLStickWork (1877E0, exported) merges one pad's left-stick axes +170/+174 into another's this tick's reading; both are fresh each tick. | 187845 18785F
once | 195EC0 initializes an emitter from its data (called by its creators 197750, 19D0F0, 1A5D00): the spawn's scale +40 multiplies +180 and +294 once. | 1967E7 196F17
once | 1C8F90 (from 1C86D0) stores a new allocation's pointer and bumps the generation count +2C8 per allocation. | 1C8FD0 1C8FF9
once | 20D770 links or unlinks an attachment and keeps the list's count +D75. | 20D91A 20DA46
once | 2389F0, an enemy's removal, tallies the kill on its spawner through 23D900 (+10 and the per-type table 9C4730). | 23D900 23D90D
fixed | 21EBD0 and 21EF90 (unreferenced copies of vt79E318's sub-state updates): the 0.3 fade of +D2C is blend rows 21ED91/21F151. | 21ED9D 21F15D
left | 20E130 (x, z += R(+B0) x (0, 0, d)): the per-tick callers' d is scaled at the call (callscale rows 22FF46, 307C57, 307EE4, 308408, 30854A, 3086FA); 62EC80's and 631700's calls are their phase-zero entries (once) and 5355E0's is a snap to 130 from its target. Left: 5BB550 (state 3 of 5BB270's object) walks 1.0 a tick by a tail jump into 20E130, which a callscale (an E8 call) cannot retarget. | 20E185 20E19B
