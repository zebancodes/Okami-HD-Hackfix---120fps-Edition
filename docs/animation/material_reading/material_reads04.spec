fixed | cBallObj et9a wp1e 33A560: 33A875 loads the shared 0.05 step in xmm7; all four material +60 additions use it | 33A889 33A8B2 33A8D9 33A90A
follows | cBallObj et9a wp1e: these stores subtract 1 only after the scaled U offset crosses +1 | 33A894 33A8BD 33A8E4 33A915
fixed | wp20 393210: each material +60 subtraction uses the stock 0.05 in xmm8, scaled separately at 3933E8, 393412, 39343C and 393466 | 3933F0 39341A 393444 39346E
follows | wp20: these stores add 1 only after the scaled U offset crosses -1 | 3933FB 393425 39344F 393479
fixed | wp35 397310: each material +60 addition uses the stock 0.05 in xmm8, scaled separately at 3973F2, 39741C, 397558 and 397582 | 3973FA 397424 397560 39758A
follows | wp35: these stores subtract 1 only after the scaled U offset crosses +1 | 397405 39742F 39756B 397595
fixed | et69 4D1180: 4D11A6 loads the shared 0.05 step in xmm7; all four material +60 additions use it | 4D11C2 4D11EB 4D1214 4D123D
follows | et69: these stores subtract 1 only after the scaled U offset crosses +1 | 4D11CD 4D11F6 4D121F 4D1248
fixed | 598B10: 598B56 loads the shared 0.05 step in xmm7; all four material +60 subtractions use it | 598CBE 598CE8 598D18 598D46
follows | 598B10: these stores add 1 only after the scaled U offset crosses -1 | 598CC9 598CF3 598D23 598D51
