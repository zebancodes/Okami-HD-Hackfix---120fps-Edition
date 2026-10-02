group menu
count 426386 | 426310 asynchronous menu fade: +1AE advances a six-update alpha phase, derived from the stored phase and fixed endpoints, then marks +1AD inactive on completion
gatefn 48BEB0 | 48BEB0: stock-cadence void startup helper keeps its eight-update wait and load-completion event together; the only caller ignores RAX and the body has no other paced steps
group actor
gatefn 4486D0 | 4486D0 deferred cleanup: stock-cadence void helper keeps the +C98 two-to-three delay step and cleanup event together; no other paced update is in its body
count 4893C8 (0x4893C0,0x4893CB,(0x4893C0,0x4893C3,0x4893C6,0x4893C8),None) | 4893C0 transition dispatcher: pace the positive startup hold counter while preserving event and input processing on every update
count 48FFD4 | 48FFD0: pace the nine-update particle period; completion immediately resets +155 to zero, preventing repeated spawn events on held ticks
count 5F6729 | et9f 5F6690: pace the thirty-one-update inactive-player delay before spawning its once-latched +1078 effect; copying the player's model remains on every update
count 5FC892 | ut9c 5FC850: hold the positive +1088 cooldown decrement store; computed AL is discarded and subsequent logic reads the stored field
count 651767 | ut35 651750: hold the +11AA countdown store for the +11AC high-bit delay; completion tests the old DL
notyet 65176D notyet:65179E | ut35 651750: clear the +11AC high bit only on a stock tick, including the old-count-negative invocation after the last decrement
count 6521BD | ut35 652160: pace the +11B0 scripted motion-change delay while keeping attachment matrix copies and input processing on every update
notyet 6521C3 notyet:6521F0 | ut35 652160: fire the seventy-two-remaining motion-change event only on stock ticks so a held delay cannot restart the motion repeatedly
notyet 6521F0 notyet:65221D | ut35 652160: fire the fifty-seven-remaining motion-change event only on stock ticks so a held delay cannot restart the motion repeatedly
count 443E44 | 443DF0 sound-volume dispatcher: hold the positive +37C start delay while the waiting branch continues returning before sound start
count 444301 | 4442A0 sound-volume dispatcher: hold the positive +398 sixty-update stop delay; computed EAX is discarded and the stored delay is tested on the next invocation
count 444559 | 444450 sound-volume dispatcher: pace the shared +398 reload/decrement store; completion consumes the previous field before this store and computed EAX is discarded by 4516E0
count 444714 | 444650 sound-volume dispatcher: hold the positive +398 sixty-update stop delay; computed EAX is discarded and the stored delay is tested on the next invocation
