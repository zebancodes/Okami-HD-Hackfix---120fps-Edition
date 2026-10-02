group actor
# hm19's two vertical state branches add a per-tick vertical displacement.
pre 31EE9F | hm19 state 2: scale +1314 times +EC4 before Y addition
pre 31EF01 | hm19 state 1: scale the table-derived +EC4 Y step

# hm27 and hmbd move a position toward a target over a remaining-tick count.
# Their +E3C countdown is already paced; compound the runtime blend factors.
blendr 323380 | hm27: compound the 1/(remaining+1) target blend
blendr 3356AF | hmbd: compound the 1/(remaining+1) target blend

# hm48 moves by a computed XYZ displacement and turns by a 0.2 approach.
pre 32AC32 | hm48: scale the X displacement before position addition
pre 32AC46 | hm48: scale the Y displacement before position addition
pre 32AC5C | hm48: scale the Z displacement before position addition
blend 32AD23 | hm48: compound the 0.2 turn approach

# hmce approaches an X/Z target by 0.05 and a yaw target by 0.1.
blend 33718A | hmce: compound the X 0.05 target blend
blend 3371AC | hmce: compound the Z 0.05 target blend
blend 33717E | hmce: compound the 0.1 FixTurnRate blend

# hm68 repeatedly turns by 0.9599311 then wraps.
lin 32FE6A | hm68: scale the wrapped yaw step

# Tick counters and animation phase clocks.
count 322B39 | hm27: alternate its submodel pose once per stock tick
count 32501E | hm30: advance +1810 on stock ticks
count 3255A7 | hm31: advance +1770 on stock ticks
count 3263A6 | hm36: decrement the +1311 countdown on stock ticks
count 326B3E | hm3a: advance +1810 on stock ticks
count 327136 | hm3b: advance +1814 on stock ticks
count 327186 | hm3b: advance the 60-step +1818 wave on stock ticks
count 32B2DB | hm48: decrement the +13B2 wait on stock ticks
count 32BDF3 | hm52: advance the 240-step +16D0 phase on stock ticks
count 32D91A | hm62: advance the wrapped 240-step +1310 phase on stock ticks
count 337EE1 | hmd1: alternate its submodel pose once per stock tick
