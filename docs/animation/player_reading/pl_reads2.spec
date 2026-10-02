# pl00's charge state (3C7880)
stock | pl00 charge: +B8 damping uses mode table 7A8240, which mode_constants.h rewrites for this frame rate | 3C78F5
once | pl00 charge, sub-state 0: first face the target by at most pi radians as the charge starts | 3C79E6
fixed | pl00 charge, sub-state 1: turn limit of eight degrees scaled at its load 3C7A20 | 3C7A4C
fixed | pl00 charge: +1152 increments on stock ticks; its sound and effect tests are gated between them | 3C7BBE
fixed | pl00 charge, sub-state 3: turn limit of two degrees scaled at its load 3C7E71 | 3C7E9D
stock | pl00 charge: +E48 damping uses mode table 7A81E8, which mode_constants.h rewrites for this frame rate | 3C80AE
stock | pl00 charge: root-motion step +EC0..+EC8 is written by the rate-adjusted motion advance each tick and conditionally zeroed or halved before it is applied | 3C8100 3C8114 3C811C 3C816D 3C8181 3C8189
