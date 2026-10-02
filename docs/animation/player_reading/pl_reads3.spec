# wp1a's launched piece (38D880)
fixed | wp1a piece: position x/y/z uses a scaled copy of the old velocity (pre 38D931, 38D959, 38D980) | 38D94E 38D96D 38D9A0
fixed | wp1a piece: velocity damping and gravity run on the last tick of each stock period (countlast 38D939, 38D961, 38D978) | 38D965 38D988 38D990
once | wp1a piece: when it hits the floor, the y velocity rebounds by -0.2 and the horizontal velocity halves, once per collision | 38DA10 38DA28 38DA30
