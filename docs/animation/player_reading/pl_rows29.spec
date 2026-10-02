group player
# pl00 attack-combo speed cap (3B7320), state 0: E48 is a displacement at this rate.
# The three sites jointly implement min(E48 + 2*s, 3*s), equivalent to
# min(E48/s + 2, 3)*s in stock-tick units. Their compound check lives in
# verify_world_anims.py as well as the ordinary per-window check.
lin 3B75C0 | pl00 combo state 0: add s of the stock +2 acceleration to the already current-rate +E48 displacement
srcx 3B75C8 | pl00 combo state 0: compare the accelerated current-rate +E48 with s of the stock 3 cap; preserve the original branch flags
immstore 3B75D9 | pl00 combo state 0: when the cap branch is taken, write the immediate stock 3 as a current-rate displacement 3*s
