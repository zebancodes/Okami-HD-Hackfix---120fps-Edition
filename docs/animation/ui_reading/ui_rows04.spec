group objects
# cCockInkGauge's visual-state update is called from the gameplay HUD tick.
# Its color-byte state machine and nine-tick counter run as one unit at the
# game's stock 30 Hz cadence; the layout retains its last sprite values.
gatefn 3FE5D0 | cCockInkGauge: run the ink-gauge visual state update on stock ticks
