group objects
# The cSSScroll helper is called from its per-frame state update. It only
# advances the scroll state, velocity/position and pause timer.
gatefn 414080 | cSSScroll: pace the full scroll state update on stock UI ticks

# cSubScrFude moves each queued brush sprite for ten ticks at a fixed 8.5
# pixels per stock tick, decrementing its queue timer in the same branch.
count 4234D4 | cSubScrFude: pace the first queued sprite countdown
lin 4234CC | cSubScrFude: scale the first sprite's -8.5 vertical step
count 423554 | cSubScrFude: pace the second queued sprite countdown
lin 42354C | cSubScrFude: scale the second sprite's +8.5 vertical step

# cCockLifeGauge's active pulse clock reaches 60 either one or two ticks at
# a time, depending on the HUD branch.
count 3FF7C7 | cCockLifeGauge: pace the one-step life pulse clock
count 3FF869 | cCockLifeGauge: pace the two-step life pulse clock
