# Gate the stored timer where its old register is the comparison operand.
# None is the existing audited memory-store count form; register computations
# and old-value comparisons remain intact on held ticks.
group menu
count 6074B0 | 607360 page transition: +7 advances for sixteen stock ticks; 6074B3 compares the old DL to fifteen and EAX is overwritten before any subsequent use
count 601E89 | 601D50 grow-in: +60 advances the sine phase up to ninety; the phase is read before increment and ECX is replaced with 128 immediately after the store
lin 601E7E | 601D50 grow-in: scale the shared sine-dependent 1.3 decrement used for both +2C and +30 layout scales
count 601EAD | 601D50 grow-in: alpha +5C advances by twenty-one up to 128; the following compare reloads and clamps the held field
count 601F34 | 601D50 controller wait: pace +18's 452-update timeout; the threshold comparison uses the unchanged old CX
count 50C41D | 50C350 state three: pace +1's sixteen-update slide; layout X is recomputed from the old timer and the completion test compares old DL
count 50C4C8 | 50C350 state two: pace the matching slide timer; completion compares the old CL and the calculated EAX is discarded
count 50FA6F (0x50FA67,0x50FA71,(0x50FA67,0x50FA6B,0x50FA6D,0x50FA6F),None) | 50FA50 prompt delay: decrement +38 on stock ticks, synthesizing not-finished flags for the 50FA74 branch so 50FD40 runs once on completion
group objects
count 2315E2 | utd7 231510: pace the +E3C sixty-tick shrink timeout; the old CX is retained for the later completion test and the computed EAX is discarded
