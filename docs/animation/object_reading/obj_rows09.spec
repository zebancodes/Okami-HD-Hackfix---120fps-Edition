group objects
# ut23's three state branches accumulate a moving submodel angle from a
# per-tick +115C/+1160 rate and a +1168/+116C local angular phase.
pre 4F12EF | ut23 state 5: scale +1160 before advancing +116C
pre 4F1324 | ut23 state 5: scale +116C before rotating submodel 0
pre 4F1342 | ut23 state 3: scale +115C before advancing +1168
pre 4F137A | ut23 state 3: scale +1168 before rotating submodel 1
lin 4F13C4 | ut23 state 1: scale the 0.01 decrease of +1168
src 4F13F8 | ut23 state 1: scale +1168 before rotating submodel 1
src 4F1415 | ut23 state 1: scale +1160 before decreasing +116C
src 4F1446 | ut23 state 1: scale +116C before rotating submodel 0

# et73 damps its three velocity lanes by 0.98 and applies gravity -0.8
# before moving. The temporary height subtraction around 45FC40 cancels.
lin 2F61D1 | et73: scale the 0.8 gravity step
root 2F61E8 | et73: root the shared 0.98 velocity retention factor
pre 2F6221 | et73 X: scale the updated velocity before moving
src 2F6235 | et73 Y: scale the updated velocity before moving
src 2F624E | et73 Z: scale the updated velocity before moving
