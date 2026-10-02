group player
# plwpsub/wp shared fade (3D27F0)
count 3D2863 | pl weapon sub-object update (3D27F0): +1070 fades down by 10 toward 0; commit the clamped byte only on stock ticks
count 3D2878 | pl weapon sub-object update (3D27F0): +1070 fades up by 10 toward 255; commit the clamped byte only on stock ticks
# pl00 pose wobble and ground slide (3C43C0)
count 3C465B | pl00 (3C43C0): +E3C is the phase of the submodel-y sine wobble and advances by 8 degrees once per stock tick
pre 3C497F | pl00 (3C43C0), grounded slide: persistent stock-valued +10B0 gains s of the 0.1-scaled ground-vector x acceleration
pre 3C499D | pl00 (3C43C0), grounded slide: persistent stock-valued +10B8 gains s of the 0.1-scaled ground-vector z acceleration
pre 3C49B4 | pl00 (3C43C0), grounded slide: position.x gains s of the resulting stock-valued +10B0 velocity before its existing 0.9^s damping
pre 3C49CB | pl00 (3C43C0), grounded slide: position.z gains s of the resulting stock-valued +10B8 velocity before its existing 0.9^s damping
# pl00 sibling grounded slide (3C4D90)
pre 3C513C | pl00 (3C4D90), grounded slide: persistent stock-valued +10B8 gains s of the 0.1-scaled ground-vector z acceleration
pre 3C5144 | pl00 (3C4D90), grounded slide: persistent stock-valued +10B0 gains s of the 0.1-scaled ground-vector x acceleration
pre 3C515C | pl00 (3C4D90), grounded slide: position.x gains s of the resulting stock-valued +10B0 velocity before its existing 0.9^s damping
srcx 3C5170 | pl00 (3C4D90), grounded slide: position.z gains s of source +10B8 while the destination register already holds position.z
# held UI-state braking (3C5350, 3C57A0)
count 3C567C factor | pl00 (3C5350): while held UI-state global B6B2AC bit 30 is set, keep the +E48 factor 0.1 only on the first tick of each stock period
# 3C57A0 has three 2DDF90 turn calls: the state-0 call at 3C5C9D is one-shot and intentionally remains full-sized
callscale 3C5A87 (0x2DDF90,"xmm3") | pl00 (3C57A0), sub-state 3: turn continuously toward the linked actor by at most 0.139626 radians per tick; scale the call's limit
callscale 3C5D14 (0x2DDF90,"xmm3") | pl00 (3C57A0), sub-state 1: turn continuously toward the linked actor by at most 0.279253 radians per tick; scale the call's limit
count 3C5E72 factor | pl00 (3C57A0): while held UI-state global B6B2AC bit 30 is set, keep the +E48 factor 0.1 only on the first tick of each stock period
