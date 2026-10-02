group player
# pl00 turn/charge state (3BC710)
lin 3BCA39 | pl00 (3BC710, sub-state 1): 2DE0A0's first continuous angular limit is 9 degrees a tick: pass s of the caller-local limit
lin 3BCA47 | pl00 (3BC710, sub-state 1): 2DE0A0's second continuous angular limit is 16 degrees a tick: pass s of the caller-local limit
notyet 3BCC0F notyet:3BCC7B | pl00 (3BC710): the sound/effect on every eighth +1152 charge tick must wait for a stock tick while the counter is held
notyet 3BCC7B notyet:3BCCBD | pl00 (3BC710): the event at +1152 = 0 must not repeat between stock ticks
count 3BCCBD | pl00 (3BC710): +1152 counts charging time once per stock tick; its thresholds choose the charge tier, sounds and effects
notyet 3BCE10 notyet:3BD7A0 | pl00 (3BC710): the repeated event every eight ticks above the full-charge threshold must wait for a stock tick
# pl00 linked attack/state (3BEEE0)
count 3BF3D7 | pl00 (3BEEE0): while the five-tick hit cooldown +11E9 is active, stock-valued vertical speed +E54 halves once per stock tick
notyet 3BFB76 notyet:3BFB99 | pl00 (3BEEE0, sub-state 7): +E3E's zero-time transition must wait for a stock tick while the countdown is held
count 3BFB9C | pl00 (3BEEE0, sub-state 7): +E3E's six-tick countdown loses one once per stock tick
callscale 3BFC4E (0x2DDF90,"xmm3") | pl00 (3BEEE0): the common tail turns +B4 toward the current target every tick with xmm3's 16-degree limit: pass s of the per-tick limit
# pl00 common update (3A80F0)
blend 3A81AB | pl00 (3A80F0, first path): +D20/+D24/+D28 approach 1 with the shared 0.05 factor each tick: use 1-(1-0.05)^s
blend 3A8296 | pl00 (3A80F0, fallback path): +D20/+D24/+D28 approach 1 with the shared 0.05 factor each tick: use 1-(1-0.05)^s
count 3A835F | pl00 (3A80F0): +115A's ordinary decrement commits once per stock tick
count 3A8378 | pl00 (3A80F0): +115A's conditional extra -5 acceleration also commits only on stock ticks
# pl00 state handlers (3CA320, 3C05C0)
count 3CA9B9 | pl00 (3CA320, sub-state 5): persistent speed +E48 is multiplied by 0.1 once per stock tick before the current-rate move
callscale 3C0BCF (0x2DDF90,"xmm3") | pl00 (3C05C0): the common tail turns +B4 toward the current target every tick with xmm3's 16-degree limit: pass s of the per-tick limit
