fixed | ut6f 224AB0: the +60 addition in the six-material loop scales each table rate at 224B03 | 224B0B
follows | ut6f: this store subtracts a whole unit only when the scaled U offset crosses +1 | 224B16
fixed | em2c 279AE0: two material RGB channel additions scale the shared 0.05 in xmm8 at their arithmetic sites | 279B76 279B91
fixed | hm10 31D560 and hm6e 331D00 and hm6f 331EE0: their alpha +5C additions and subtractions use separate scaled 0.05 RIP rates | 31D5C3 31D5FB 331D63 331D9B 331F43 331F7B
fixed | hm19 31E8A0: the two alpha +5C stores use separate scaled -0.05 and +0.05 steps | 31E8EF 31E901
fixed | et24 2E83E0 and es13 515970: material +60 receives its scaled -0.01 U step before wrapping | 2E8509 515A9C
follows | et24 and es13: these stores normalize the scaled U phase by a whole unit only after it crosses its bound | 2E8514 2E8527 515AA7 515ABA
fixed | utf0 5A9750: the two state-dependent material +60 steps of 0.002 and 0.01 are each scaled before this store | 5A979C
follows | utf0: this store subtracts one unit only after the scaled U offset crosses +1 | 5A97A7
