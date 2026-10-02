group player
# Pl00 shared +1156 normal-update clock. Each state owns one increment path;
# the 0x1C2/0x1C3 limit readers compare the same stored clock after it advances.
count 3C422F | pl00 state 3C41F0: advance +1156 once per stock tick when the action is active and the two input-block bits are clear
count 3C4A78 | pl00 state 3C4A30: the sibling normal-update +1156 advance has the same gated stock-tick cadence
count 3C521F | pl00 state 3C51E0: advance +1156 once per stock tick before the 0x1C2 timeout comparison
count 3C9E82 | pl00 state 3C9E30: advance +1156 once per stock tick before the 0x1C2 timeout comparison
count 3CD97D | pl00 shared helper 3CD950: advance +1156 once per stock tick while its pause and input-block gates are clear
count 3CD9DD | pl00 shared helper 3CD9B0: advance +1158 once per stock tick while its pause and input-block gates are clear; +1158 is compared with +1156 and the 0x12C event threshold
