fixed | hm0f 31D420: +14E0 is a 240-tick periodic clock, incremented at stock pace | 31D436
once | hm3c 306E30: the random 2..5 motion repetition count is chosen only at a motion-state transition | 306EA7
once | hm49/hm78 3146B0, hm01 318210, hm02 3186B0, hm03 3188A0: +E36 enters the next motion state after the first motion/play callback, not on every update of that state | 314715 318277 318704 3188F5
once | hm07 3198C0/319E20 and hm08 31B570/31B9B0: +E36/+E37 increments after starting a motion or completing a motion cycle, and the later 307840 motion-advance call decides when to reset | 319930 319E75 31B5B2 31B9F2
once | hm0a 31C250, hm0c 31C5F0/31C740, hm11 31D6C0, hm12 31D770, hm15 31DCB0: these +E36 transitions occur on motion entry or completion, with the following 307840 call testing motion end | 31C2A4 31C65E 31C795 31D72E 31D7DE 31DD1E
once | hm18 31E400, hm19 31EA20/31F160/31F1F0: these +E36/+E37 transitions follow a motion start or the 30F230/307840 completion result | 31E47C 31EA89 31F1A4 31F298
once | hm1d 31F7A0/31F860 and hm1e 31FAC0: the +E36 state moves from 0 to 1 when 30F0B0 starts its motion, then 307840 can reset it after motion completion | 31F810 31F8CE 31FB30
