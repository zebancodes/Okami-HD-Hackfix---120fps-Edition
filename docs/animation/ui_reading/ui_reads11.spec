fixed | cOptionScreenSetting 14C450: +B0 input lockout now decrements once per stock tick before settings controls are accepted | 14C46C
once | cOptionScreenSetting 14C450: the global change flag is set after a settings input action, and this branch advances +B8 to state 2 before it can run again | 14C514
stock | cMcLoad/cMcSave 1BE750: +D4 and +D0 are selected memory card row and page indices, changed only after LargeBitElement navigation action bits and wrapped against slot count | 1BE95F 1BE967 1BEA55
fixed | cCockEventEdge 3FC430: the +68 HUD edge counter changes at stock cadence in each of its three branches, retaining the zero-to-six clamp | 3FC45B 3FC467 3FC46D
fixed | cCockInkGauge 3FE260: +7C ink recovery cooldown now decrements once per stock tick, with its threshold and refill call following the stored value | 3FE52A
once | cCockInkGauge 3FE260: the sprite Y offset changes by 62 only when the observed global ink mode changes from the value cached at +91 | 3FE5A7 3FE5C4
