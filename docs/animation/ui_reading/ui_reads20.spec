once | cCockCombo 3FA8A0: the selected view changes only when global screen-mode byte B6AC5C differs from its cached +7D value; the sprite x offset is then moved by 76 once for that transition | 3FAA23 3FAA40
once | cCockEmLifeGauge 3FBE70: the global screen-mode byte B6AC5C changes the cached +8B value and moves the sprite x offset by 60 once per mode transition | 3FC12F 3FC14C
once | cCockLoading 400710: the global screen-mode byte B6AC5C changes the cached +3A8 value and moves the sprite x offset by 64 once per mode transition | 400824 400846
once | cOptionHelp 1492B0: +EC is the highlighted help page index; these wraparound changes require a fresh controller action bit and are navigation events | 1493E6 149411
once | cCock reward display 3FD760: +C8 is the occupied entry count in a four-slot pickup list; insertion comes from the item acquisition callback 499950 through 404450 | 3FD8BD 3FD8E8
fixed | cSSScroll opening 410540: its existing function-entry gate paces the +D0 fade count and the five row shifts together | 410739 410796
fixed | cSSScroll up 4111D0: its existing function-entry gate paces both the row movement and +D0 step count | 411299 4112AD
fixed | cSSScroll down 4113A0: its existing function-entry gate paces both the row movement and +D0 step count | 411465 411479
fixed | cSSScroll closing 411570: its existing function-entry gate paces the +D0 fade count and row movement together | 4116EF 41177B
