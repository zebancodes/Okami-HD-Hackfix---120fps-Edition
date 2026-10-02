group player
# pl00 target move (3D0440)
pre 3D07A0 | pl00 (3D0440), active state: move x by s of the normalized target-direction step; leave +E10 stock-valued for the arrival distance check
pre 3D07B7 | pl00 (3D0440), active state: move y by s of the normalized target-direction step; leave +E14 stock-valued for the arrival distance check
pre 3D07D0 | pl00 (3D0440), active state: move z by s of the normalized target-direction step; leave +E18 stock-valued for the arrival distance check
notyet 3D0895 notyet:3D08A4 | pl00 (3D0440): zero-time exit must wait for a stock tick while +E3C is held
count 3D08A7 | pl00 (3D0440): +E3C loses one per stock tick in active state
