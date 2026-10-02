group objects
# Division easing: preserve stock DIVSS at N=1 and the source denominator.
srcblend 4BCA48 | sg00 4BC9F0: horizontal input angle approaches its target by one tenth per stock tick before rebuilding the model matrix
srcblend 4BCA68 | sg00 4BC9F0: vertical input angle approaches its target by one tenth per stock tick; fixed matrix offsets remain geometric
srcblend 4BCF1A | sg00 4BCEB0: horizontal input angle eases by one tenth toward the half-input target
srcblend 4BCF3A | sg00 4BCEB0: vertical input angle eases by one tenth toward the 0.36-input target
srcblend 62F828 | et2f 62F700: X approaches the selected target by one over the remaining stock ticks; use a rooted copy of the divisor, shared by XYZ
srcblend 62F845 | et2f 62F700: Y uses the same remaining-ticks easing divisor as X
srcblend 62F864 | et2f 62F700: Z uses the same remaining-ticks easing divisor as X
count 62F872 down | et2f 62F700: remaining target-approach ticks at +1158 decrement after XYZ, with JNE completion and one E34 transition on expiry
srcblend 63236B | et30 632230: X approaches the selected target by one over remaining stock ticks at +11A4
srcblend 632396 | et30 632230: Y uses the same remaining-ticks easing divisor as X
srcblend 6323C3 | et30 632230: Z uses the same remaining-ticks easing divisor as X
count 6323D1 down | et30 632230: remaining target-approach ticks decrement after XYZ and change E34 out of this phase on expiry
# Quantized vertex-color easing must execute the byte store at stock cadence.
count 3DD9D6 | objScroll 3DD830: byte green approaches 255 with a distance-derived coefficient; discard the computed AL before the next channel load
count 3DD9F7 | objScroll 3DD830: byte red approaches zero with the same distance-derived coefficient; computed AL is discarded by the next channel load
count 3DDA15 | objScroll 3DD830: byte blue approaches zero with the same distance-derived coefficient; computed AL is not consumed after this store
count 3DDA50 | objScroll 3DD830: byte alpha approaches zero in the inner distance band; computed AL is discarded before the loop advances
count 3DD6F1 | objScroll 3DD580: byte alpha fades with a distance-derived coefficient; hold the quantized store between stock ticks
# ut89's angular velocity changes before each angle integration.
count 652964 float | ut89 652910: increase each angular velocity toward its target only on stock ticks, before the following clamp and angle integration
count 652976 float | ut89 652910: decrease each angular velocity toward its target only on stock ticks, before the following clamp and angle integration
pre 65298D | ut89 652910: scale the complete angular velocity immediately before adding the old angle; clamp targets retain their units
srcx 553603 | ut91 5534A0: animation decision phase +1080 advances one per stock tick in modes 1 and 3, independently of the already-paced model motion
count 55361C | ut91 5534A0: positive byte cooldown +1070 counts down; AL is discarded before return
# The coupled sound phase uses signed-positive completion tests.
lin 548225 | ut9d 5481E0: sound phase amplitude rises 1.333333 per stock tick toward the fixed 60 limit
count 548253 | ut9d 5481E0: sound phase countdown at +1070 controls a single stop/reload event
notyet 548259 notyet:5482C0 | ut9d 5481E0: a held countdown tick takes JG past the sound-stop and random-reload event, preserving stock cadence
lin 548362 | ut9d 5481E0: sound phase amplitude falls 1.333333 per stock tick toward zero
count 54838B | ut9d 5481E0: sound phase countdown controls one transition out of the falling phase
notyet 548391 notyet:5482C5 | ut9d 5481E0: a held countdown tick takes JG past the phase transition
pre 509EE5 | ut1b 509EB0: add the complete Y velocity +1098 to old height at stock speed before clamping to the fixed starting-height-plus-90 target
src 50EF63 | et7d 50EF30: scale the double-precision alpha decrement before conversion back to float; completion exits the fade phase once
count 50EFB1 | et7d 50EF30: wait 60 stock ticks after model-motion completion before entering the alpha fade phase
lin 583D07 | utcc 583C90: height rises 0.4 per stock tick toward starting height plus 220
lin 583DAC | utcc 583C90: height falls two units per stock tick toward starting height
lin 57CB2F | ut2c 57CA00: height rises 0.2 per stock tick toward the fixed +E14 target before phase 3 changes to 4
srcx 552E57 | ut47 552CF0: scale the complete vertical move at the position subtraction, retaining the unscaled vertical component used to derive horizontal movement
srcx 552F45 | ut47 552CF0: scale the complete sine-directed horizontal X move before subtracting it from the old position
srcx 552F7B | ut47 552CF0: scale the complete cosine-directed horizontal Z move before subtracting it from the old position
src 552FB8 | ut47 552CF0: scale the live +1088 rate increase read from the mutable speed table, consistent with the already-scaled rate decrease in the earlier branch
srcx 55298F | ut47 552950: scale the negative height step while preserving XMM7 as the completion threshold source
srcx 55299D | ut47 552950: scale the positive height step while preserving XMM7 as the completion threshold source
pre 5529F1 | ut47 552950: scale the complete per-tick height limit immediately before comparing it against absolute remaining height distance, so the snap uses the scaled step
