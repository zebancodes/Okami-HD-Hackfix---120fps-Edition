# The large 17CE00 sweep reconstructs scratch geometry and statistics from
# the current 0x600 records. Only the sites with a visible same-call reset or
# pure geometric derivation are settled here.
stock | 17CE00 clears the paired 888C54 and 888C58 tally at entry; this increment counts qualifying records in the current sweep | 17CF46
stock | 17CE00 writes this angle-derived geometric value from the current three-point record, not from prior-frame state | 17D04A
stock | 17CE00 clears 888C64 at entry, then adds the current segment lengths to that scratch tally | 17D25A
stock | 17CE00 clears the 888D4C per-segment count through puVar17[-0x100] before this segment-pass increment | 17D844
stock | 17CE00 clears 890934 and 890938 before its final 0x600-record sweep; these increments count records and non-null pointers in that sweep | 17DB85 17DB97
stock | 17CE00 converts the current 890934 pointer count to float for its end-of-sweep proportion calculation; this read does not advance a timer | 17DC1E
stock | 17CE00 zeroes the 8908B0 count array before its pointer-group sweep; this increment counts matching pointers, not elapsed ticks | 17DC78
