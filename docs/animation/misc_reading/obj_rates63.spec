group objects
lin 364F82 | cKiType019 death rise: scale the constant half-unit ascent per stock tick; motion advance remains independently time-correct.
pre 365008 | cKiType019 death rise: the first operand is the complete (E3C-30)*0.3 ascent step; scale it before adding old Y.
count 364FB1 | cKiType019 death jitter: commit the positive random displacement only on stock ticks, preserving its amplitude and sample cadence.
count 364FDC | cKiType019 death jitter: commit the negative random displacement only on stock ticks; later height tests reload Y from memory.
lin 36CDE2 | cKiType041 death rise: scale the half-unit ascent separately from the already corrected motion clock.
pre 36CE68 | cKiType041 death rise: scale the complete elapsed-count ascent step before adding old Y.
count 36CE11 | cKiType041 death jitter: commit the positive random displacement only on stock ticks; the following join reloads Y.
count 36CE3C | cKiType041 death jitter: commit the negative random displacement only on stock ticks; its arithmetic result is not reused.
count 2E1A48 | et04 linked model settling: commit the -0.5 X rotation recurrence on stock ticks; retain sign reversal and amplitude together.
count 2E1A5C | et04 linked model settling: commit the matching -0.5 Y rotation recurrence on the same stock ticks.
count 2E1A64 | et04 linked model settling: commit the matching -0.5 Z rotation recurrence on the same stock ticks.
src 2F2C82 | cObj appearance: scale the double-precision D20 alpha increment from the shared XMM1 step, preserving the source and narrowing once.
src 2F2C9D | cObj appearance: scale the double-precision D24 alpha increment, preserving the shared XMM1 step for the other channels.
src 2F2CB8 | cObj appearance: scale the double-precision D28 alpha increment before its original float conversion and unit clamp.
srcx 33B052 | cBallObj ballistic motion: scale persistent E54 vertical velocity when adding it to world Y; the port gravity update stays separate.
count 33B085 | cBallObj spin-rate settling: commit the complete (1140-0.2)*double damping recurrence only on stock ticks, preserving its coupled stock update.
