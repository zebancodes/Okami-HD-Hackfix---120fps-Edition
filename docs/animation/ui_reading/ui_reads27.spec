fixed | cSubScrItem 425650: the active item's sprite x offset now changes by a scaled 40-unit step | 42592F
stock | cSubScrStatus 433AD0: +5C is computed afresh from an integer status byte +7F and a scale factor in xmm1; it does not multiply an earlier +5C value | 434108
once | cSubScrStatus 434160: +50 advances the opening stage after the screen and controller glyphs are initialized, with +51/+53 reset | 434481
once | cSubScrStatus 4348A0: +52 advances after 435DE0 finishes the current status-screen action, with +53 reset | 43497F
once | HUD value animation 439910/439A50: +29 advances stage after its sound/effect setup and again when the value reaches the 25-unit threshold | 439A38 439AC4
stock | cSubScrMap 426DD0: +D4 is an OR of map-state flag words from two entries, so these writes combine masks during a merge | 426EC3 426ECF
stock | cMcBoot 5FDFB0: +68 is the calculated free-space shortfall, required size minus current free HDD kilobytes, for a disk-space request | 5FE299
