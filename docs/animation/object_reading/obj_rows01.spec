group objects
# uta4's four-part state machine 55F120 (states in +1300+i), called for each
# part by 55F0A0 and 55FFF0. It mirrors em8f's proven 2D79F0 update.
blendr 55F1A8 | uta4 part: case 1's anchor-approach factor is 0.02 times part index, applied to all three position lanes each update
lin 55F260 | uta4 part case 0/1: +5C alpha linearly approaches one; scale this instruction's 0.1 literal
ufirst 55F2B6 | uta4 part case 1: the three velocity lanes' 0.96 damping runs once per stock tick before the next move
zfirst 55F2C9 | uta4 part case 1: spring vx gains 0.002 times anchor-to-part x on the first tick of each stock period
zfirst 55F2E7 | uta4 part case 1: the same spring vy
zfirst 55F30F | uta4 part case 1: the same spring vz
count 55F334 | uta4 part case 1: +1304 phase increments once per stock tick, before its eight-degree sine wobble
zfirst 55F383 | uta4 part case 1: the sine wobble adds its y velocity impulse once per stock tick
scaledadd 55F3C1 | uta4 part case 1: position += persistent part velocity by cVec::operator+=; move by s of the vector each tick

scaledadd 55F499 | uta4 part case 3, knocked loose: position += the current velocity each tick, scaled by s
lin 55F4AF | uta4 part case 3: gravity subtracts s of the stock 0.1 literal from vy after the move
countlast 55F4C9 | uta4 part case 3: vx multiplies by negative 0.7 only on the last tick of each stock period, after the move
countlast 55F4DF | uta4 part case 3: the same alternating decay for vz
count 55F4FC | uta4 part case 3: +130C countdown steps once per stock tick
notyet 55F505 notyet:55FD04 | uta4 part case 3: the test reads the old countdown, so defer the zero transition between stock ticks
count 55F546 | uta4 part case 5: the hidden-state +130C countdown steps once per stock tick
notyet 55F54F notyet:55FD04 | uta4 part case 5: defer the zero transition while the countdown is held

ufirst 55F5EB | uta4 part case 7: the three velocity lanes' 0.96 damping runs once per stock tick
zfirst 55F60B | uta4 part case 7: spring vx gains its target-position error times 0.002 once per stock tick
zfirst 55F629 | uta4 part case 7: the same spring vy
zfirst 55F64B | uta4 part case 7: the same spring vz
count 55F670 | uta4 part case 7: +1304 wobble phase increments once per stock tick
zfirst 55F6BF | uta4 part case 7: the sine wobble's y velocity impulse runs once per stock tick
scaledadd 55F6FD | uta4 part case 7: position += s of persistent velocity

blend 55F7B2 | uta4 part case 9: the three coordinates approach the body and offset at 0.3 per stock tick
count 55F849 | uta4 part case 9: +130C countdown from ten steps on stock ticks while nonzero
blend 55F906 | uta4 part case 11: position x approaches body plus offset by 0.4 per stock tick
blend 55F928 | uta4 part case 11: the same for position z
lin 55F943 | uta4 part case 11: gravity subtracts s of the 0.9 literal from vy before the y move
pre 55F963 | uta4 part case 11: position y adds s of the just-updated stock-valued vy

ufirst 55FA8A | uta4 part case 13: the three velocity lanes' 0.96 damping runs once per stock tick
zfirst 55FA9D | uta4 part case 13: spring vx gains 0.001 times anchor-position error once per stock tick
zfirst 55FABB | uta4 part case 13: the same spring vy
zfirst 55FAE3 | uta4 part case 13: the same spring vz
count 55FB08 | uta4 part case 13: +1304 wobble phase increments once per stock tick
zfirst 55FB57 | uta4 part case 13: the sine wobble's y velocity impulse runs once per stock tick
scaledadd 55FB95 | uta4 part case 13: position += s of persistent velocity
count 55FBA7 | uta4 part case 13: +130C countdown steps once per stock tick
notyet 55FBB0 notyet:55FD04 | uta4 part case 13: the test reads the old countdown; hold its zero transition between stock ticks

blend 55FC19 | uta4 part case 15: +5C alpha fades toward zero at 0.1 per stock tick
scaledadd 55FC32 | uta4 part case 15: position += s of its thrown velocity
lin 55FC48 | uta4 part case 15: gravity subtracts s of the 0.1 literal from vy after the move
countlast 55FC62 | uta4 part case 15: vx's negative-factor damping runs after the move on the last stock-period tick
countlast 55FC78 | uta4 part case 15: the same for vz
count 55FC95 | uta4 part case 15: +130C countdown steps once per stock tick
notyet 55FC9E notyet:55FCB3 | uta4 part case 15: hold the old-countdown branch on intermediate ticks
count 55FE62 | uta4 part: the 60-tick post-hit +1314 countdown steps once per stock tick while nonzero
