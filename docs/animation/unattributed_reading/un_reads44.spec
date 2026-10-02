# 2026-10-01, fifth batch (rows in un_rows44.spec)
once | Imp states 2488B0, 249A90, 247900 (from 2422E0): the speed +E48 is set once on entry (a random speed times the port's time scale B6AC38), then its sign flipped at random. | 2489E7 249BBF 247A08
follows | Imp states 2488B0, 249A90: the root step +EC0 gains +1080 x +E48 a tick, and +E48 already carries the port's time scale B6AC38 (0.25 at 120 in play). | 248AFF 249CD7
once | 24A340, 2543B0, 2A0190, 2A0D00, 2462C0, 249960: one-time work on a state's entry or end (a jump count +14A9 spent, a heading snap with a 2 pi limit, the sub-state +E36 advanced after a motion starts or the death fade ends). | 24A3F7 24A40D 25453F 254545 2A035C 2A0DA3 246678 2499ED
once | 25E3B0 and its copy 272DA0 run on events (a timer's expiry, an animation's end, a state change): they place +1370 ahead, snap the heading +1380 toward the player (2 pi limit) and add a random bit to +11B3/+11B0. | 25E48B 25E4A2 272E7B 272E92
once | 283DA0 is a damage handler: +2430 accumulates the hit's damage, +11B8 counts hits. | 283E0B 283FAF
once | 2A53F0 (from 29F770): a state's entry sets the heading +E14 with a random 10 degrees and advances +E36. | 2A5542 2A5573
fixed | 2A58A0: the heading's approach goes through 2DA510, whose k the FixTurnRate hook converts. | 2A5AE6
once | 2A58A0: +E37 counts the animation's loops down when one ends. | 2A5AFE
fixed | 36E060: the tilt's x0.7 decay is countlast row 36E425. | 36E42D
once | 36E060: the tilt is zeroed once it is below the threshold. | 36E441
fixed | 3BFEC0 damps +B8 and +E48 by the port's mode tables (7A8240 and 7A8218, by the mode byte), which mode_constants.h rewrites for the running rate. | 3BFEF8 3C0091
stock | 1417A0, 141D00, 142890: the sound streamer's worker threads (OSSignalSemaphore, OSYieldThread): job queue and slot counts, not ticks. | 141A1F 14200D 142A83
stock | 14D510 is a thunk into library code (A5100, its jump table): this candidate is the library's, which the library group excludes. | 0A5357
fixed | Brush 165BD0: the countdown +60 is count row 165F87. | 165F8A
once | 1989F0 spawns an effect and records its slot in +4F. | 198B42
stock | 1AE440 reads a resource stream (StreamBuffer): offsets into the data, not ticks. | 1AEB85
fixed | Stream loader 1B0670: the wait +70 is count row 1B06E1. | 1B06E3
once | 1B0C50 parses a resource's records (0x78 bytes each, up to 0x27) and counts them in +12C8. | 1B0E6B
fixed | 1BFCB0 sets the mode byte for its 60 Hz screen (1BFD93) and restores it (1BFDD1): both are the shadow family's (shadow_mode.h); the candidate is the decompiler's merge of those writes. | 1BFE9A
fixed | Animal 205310's slide: lin rows 205505/205524 and src rows 205537/20554F scale its moves. | 205511
once | 2073D0 (from cKihonObj's update 207760) lowers the object by a byte offset once, flagged in +10EC. | 207482
once | 20D310 (from 20CF80 and 20B810) unlinks an attachment and keeps the list's count +D75. | 20D337
fixed | 20E030 (heading toward a point by at most a limit, its third argument): its four calls are callscale rows (1ED84D, 1EF0DA, 1EF2B8, 32EFAC). | 20E09F
once | 238C40 adds a hit's byte (+13 of the hit data) to +1130 when the hit carries flag 25. | 238C62
once | 239810, on an enemy's defeat, scales its reward count +112C by 3CDE70's factor. | 2398AC
follows | 23A2E0 (turn toward Amaterasu at rate x speed): the steer group scales its limit at each of its 146 calls. | 23A32E
once | 23A850 doubles the enemy's health +1020 (and sets +E44) when it is set up. | 23A8F9
once | 245E50 (from 242270) lifts the enemy by xmm7 once on a state's entry. | 245F6B
once | 246C20: +E37 (0 to 3 at random) counts the motion's loops down when one ends. | 246CF1
once | 24F9C0 spawns an object (2DA050) and counts the spawns in +14C1. | 24FACE
once | 2597C0 (from 23B790) turns the heading half around once. | 2598AA
fixed | The twin enemy's orbit 281470 is gatefn row 281470 (+2454 is also set afresh each call). | 2815DC
once | 2A0E20, 2A1130, 2A2090, 2A21C0, 2A2800, 2A4BA0, 2A5730 (from 29F500, 29F710, 29F770): one-time work on a state's entry (effects spawned, a motion played, the sub-state +E36 advanced, +1390 lowered by 600). | 2A0EC3 2A11E0 2A2146 2A2239 2A28AD 2A4C7B 2A580F
once | 2A5190 and 2A5CA0: +E37 counts the motion's loops down when one ends. | 2A533B 2A6177
fixed | 2A0F40 sub-state 3: the 150-tick countdown +13BA is count row 2A1073. | 2A1073
stock | 2E48D0 scales the motion factor +F54 by the slow-motion factor only around its motion advance call, then restores it. | 2E4904
stock | 2EB0E0 puts the object at another's position plus 20 each call: nothing accumulates. | 2EB122
fixed | 313A60 (3135B0's state 1): the delay +40 is count row 313A80. | 313A83
fixed | Villager 317870: the countdown +14 is count row 3179BA. | 3179BD
once | Villager 317BB0 returns unless its mood changed; then it swaps the mood bubble effect (1989F0) and cycles its index +C. | 317D53
once | 3599D0 creates an enemy and gives it the next id from 9C6A80. | 359BA0
stock | 35AE10 appends to a vector (+8 is its end pointer). | 35AE90
fixed | Weapon aim 39F770: its approaches are callblend row 39F848 and callscale row 39F86F. | 39F860
follows | 3D9C10 wraps an angle +C that is set elsewhere. | 3D9C8F
stock | 3E5590 is a bump allocator (+10 advances by 0x60 per allocation). | 3E55AF
stock | 40F470 (UI pages 423EE0, 425A20, 425B20) adds the offset between two layout nodes to an element after the layout sets it each update. | 40F560
once | 445540 counts a looping sound's plays (+28 of its voice, against its limit) as each starts. | 4455CE
once | 4457C0 lowers a voice's volume +1C by 0x500 once with its stop request (flag 2). | 445A82
once | 44DC20 counts a sound's references (+60) as it is requested. | 44DDF5
stock | 456600 is the task manager's own wait counter (+12), decremented once a tick; task_waits.h scales the waits' lengths. | 4566CB
fixed | 467CA0's countdown is count row 467D23 with notyet 467D25. | 467D23
fixed | 468FF0 (the camera's stick velocities): its 0.9 and 0.96 dampings are root rows 468FFF and 469007 on their loads. | 469062
fixed | Camera modes 4697B0, 46BCD0, 46C370: the speeding-up approach factor +260 steps by lin rows 469BEC, 46BF1C, 46C796 and is blended at its use by srcblend rows 469BE8, 46BF18, 46C792. | 469BF8 46BF35 46C7A2
fixed | Camera 4760E0: the held-button count +47C is count row 4761B1. | 4761B1
fixed | 4818E0: +3AC approaches by the 7A82C0 mode-table value minus one, which mode_constants.h rewrites for the running rate. | 481995
