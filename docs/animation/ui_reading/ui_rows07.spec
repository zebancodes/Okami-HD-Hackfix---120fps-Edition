group objects
# cSubScrStatus has four resource meter helpers, each called only from its
# own per-frame branch. The helper adds the requested resource transfer and
# returns a boolean before the caller subtracts the same amount from +284.
# Gate each call as one unit so both sides of the transfer keep stock cadence.
callgate 434FCC (0x433250,None) | cSubScrStatus: pace resource meter 0 transfer helper
callgate 43516F (0x4331D0,None) | cSubScrStatus: pace resource meter 1 transfer helper
callgate 435311 (0x4332E0,None) | cSubScrStatus: pace resource meter 2 transfer helper
callgate 4354B5 (0x433360,None) | cSubScrStatus: pace resource meter 3 transfer helper

# The four waiting sound flags can wrap after 256 increments. Their related
# transfer progress clock +2A4 also counts per update tick.
count 434F19 | cSubScrStatus: pace the resource transfer progress counter
count 43500D | cSubScrStatus: pace meter 0 wait flag
count 4351B0 | cSubScrStatus: pace meter 1 wait flag
count 435352 | cSubScrStatus: pace meter 2 wait flag
count 4354F6 | cSubScrStatus: pace meter 3 wait flag
