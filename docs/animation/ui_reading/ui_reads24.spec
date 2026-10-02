fixed | cCockLifeGauge 3FFA00: the +78 life display wait is decremented on stock ticks by the hook at 3FFC36 | 3FFC39
once | cCockLoading 4005E0: +39C increments only after its 60-element loading array has been filled, then a loading stage changes | 4006E5
once | cCockLoading 400980: its sprite x offset is shifted by 64 during virtual slot 1 setup, called by initializer 400920 | 4009C7
fixed | cCockMapTitle 4022A0: the +68 title countdown's decrement and jns continuation now occur on stock ticks | 4022BA
fixed | cCockRemain 405210: the +68 remainder countdown now decrements on stock ticks; skipped ticks preserve a nonzero cmove condition | 40524C
once | HUD reward total 407AD0: +84 is a clamped accumulation of the edx amount passed by pickup and reward event callers | 407AD0
once | cOption/cOptionEx 409280: +54 is a navigation selection index, decremented only after a fresh controller action, with wrap at the start of the list | 409A93
