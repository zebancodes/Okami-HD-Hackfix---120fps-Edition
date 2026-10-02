stock | pl00 state 3C6750: +B8 damping is looked up from the port's already rate-adjusted mode table 7A8240 | 3C678F
fixed | pl00 state 3C6750: the 2DA510 angular approach uses the existing FixTurnRate hook, which converts its caller factor for the current rate | 3C67F6
fixed | pl00 state 3CA160: the two continuously executed target-heading turns use their callsite-scaled 0.279253-radian limits | 3CA235 3CA2E8
stock | pl00 initializer 3CEBB0: both divisions normalize fixed arrays of 64 and 32 generated random weights to sum to one; the function initializes lookup probabilities, and no elapsed-time quantity is involved | 3CEC2F 3CEC8F
