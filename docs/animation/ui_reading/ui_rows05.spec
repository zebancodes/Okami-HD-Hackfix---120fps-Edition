group menu
# cCockGetItemInfo slot 3 integrates the item position and velocity. The
# constant 1.5 is the acceleration used by every item in this loop.
count 3FD3F3 | cCockGetItemInfo: decrement item timer on stock ticks
lin 3FD3DC | cCockGetItemInfo: scale the per-tick 1.5 velocity increment
pre 3FD405 | cCockGetItemInfo: scale updated velocity before position addition
