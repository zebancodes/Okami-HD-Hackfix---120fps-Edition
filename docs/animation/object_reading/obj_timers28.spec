group objects
count 4D1156 | et69 4D1000: +10E0 advances the 100-tick recurring sound delay with AL discarded before return
count 4FEC7D | ut16 4FEC40: positive +E35 counts the stock duration of temporary extra model-motion advances; all three motion calls already use the common motion pacing
count 4FF19B (0x4FF190,0x4FF19D,(0x4FF190,0x4FF197,0x4FF199,0x4FF19B),None) | ut17 4FF080: positive five-tick motion-start delay counts down with JNE completion suppressed on held ticks
count 50E8E0 down | cDigObj 50E810: scripted effect waits 75 or 210 stock ticks before changing E34 out of the wait phase
count 50E954 | cDigObj 50E900: positive eight-tick effect cooldown decrements and returns before the next spawn/reload
count 517319 | ut28 517200: +E36 is a 16-tick quantized alpha phase; alpha is recomputed from the held phase and phase sixteen immediately exits this state
count 523FC3 down | ut58 523FA0: phase-four +E3C counts down from 30; CX equals one on this dispatch branch and JNS suppresses completion between stock ticks
count 55233B | ut43 5522E0: +1070 is a 360-tick recurring sound cooldown; store the decremented or freshly reloaded value only on stock ticks
group menu
count 13A8D3 ("block",0x13A8B8,0x13A8D6) | 13A7D0: byte +4 measures a 150-stock-tick timeout between button transitions; the complete branch block keeps +3 as an actual button event count
