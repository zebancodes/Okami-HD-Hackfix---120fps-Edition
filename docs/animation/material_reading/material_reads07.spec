stock | em29 239DD0 takes new U/V offsets in xmm2/xmm3, writes them directly to material +60/+64, then these two stores only add or subtract whole units to normalize V to its -1..1 range | 239E49 239E5C
once | et11 2E6A90 and et12 2E6D40 are their vtable slot 9 event handlers; each increments material 0 U by 0.24 once then sets +E34 to state 3 and returns | 2E6B7B 2E6E03
