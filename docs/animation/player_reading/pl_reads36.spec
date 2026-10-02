# Event-only shared helper (24F100)
once | wp51 helper 24F100: +14C1 counts live spawned parts and loses one only when an event/damage path in 39E020 retires a part; it is not elapsed time | 24F106

# Shared wp/enemy visual update (33A560)
fixed | shared wp/enemy update 33A560, type 398: +E3E's repeating effect timer decrements on stock ticks and its old-value zero effect is held between them | 33AACC

# wp09 states
once | wp09 state 387850: +E36 increments only during state-0 setup, immediately selecting state 1 for later updates | 3878F3
fixed | wp09 state 387990: +1110 loses the slow-motion dt scaled at its xmm6 copy (dst 3879B7) | 387A36

# Weapon state setup, fades, and vertical integration
once | wp0e state 389A30: +E36 increments only after the state-0 position setup | 389A85
fixed | wp12 helper 38CB10: +D2C loses s of 0.1 through srcx 38CB20 while its terminal comparison keeps the stock 0.1 threshold | 38CB27
fixed | wp1a common update 38D490: position.y gains s of stock-valued +E54 through srcx 38D5A6 | 38D5AE
fixed | wp1b common update 38E400: position.y gains s of stock-valued +E54 through pre 38E540 | 38E545

# Companion site that coverage called near only because its later damping is patched.
fixed | wp1c common update 38EEE0: position.y gains s of stock-valued +E54 through srcx 38F03F; the later 0.94^s damping remains decay_factors.h's job | 38F047

# One-shot weapon state setup / pose compensation
once | wp1d state 390110: state 0 adds the full 20-unit vertical aiming bias before normalizing the launch direction, then immediately advances +E36 | 390222
follows | wp20 visual update 393210: submodel 1 counters the wrapped change from the previous sampled player yaw; the full current-frame yaw delta already follows its source | 3934DF
once | wp48 state 39CD20: +E36 increments only after state-0 motion, effect, and linked-object setup | 39CDF9
once | wp48 state 39D0B0: +E36 increments only after state-0 motion and effect setup | 39D14A
once | wp49 state 39D560: +E36 increments only after state-0 motion setup | 39D5CF
once | wp4c state 39DB30: state 2 writes each of ten radial spawn angles in one setup loop, then immediately advances +E36 | 39DC41
once | wp51 state 39E4F0: +E36 increments only after starting the state-0 motion | 39E558
fixed | wp5a state 3A0D00: +10F0 loses the slow-motion dt scaled at its xmm6 copy (dst 3A0D44) | 3A0E91

# Player common helpers and dispatcher
stock | pl05 dispatcher 3A6FE0: the inactive-mode branch's full +1000 y displacement is an offscreen hiding correction, not elapsed-time movement | 3A7011
fixed | pl00 helper 3A7950: +1170 advances through its cyclic submodel-angle table on stock ticks through count 3A79C1 | 3A79C1
once | pl00 collision helper 3A9390: +1450 increments only after either collision query reports an accepted hit event | 3A953C
stock | pl00 dispatcher 3AF020: fallback +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3AF68B

# Player grounded drift / event latch
fixed | pl00 state 3C9940: +10B0/+10B8 gain s of ground-vector acceleration and position gains s of the resulting stock-valued velocities; their later 0.9 damping is already 0.9^s | 3C9D89
once | pl00 event helper 3CEF70: +1131 increments only after the accepted actor-range event spawns its effect; the nonzero latch prevents repeats | 3CF018

# Player linked-actor countdown states
fixed | pl00 state 3D01F0: +E3C decrements on stock ticks and its old-value zero effect/completion path is held between them | 3D0426
once | pl00 state 3D0AA0: state 0 applies the full three-unit ground-separation nudge once, after advancing +E36 to state 1 | 3D0C23
fixed | pl00 state 3D14B0: +E3C decrements on stock ticks and its old-value zero cleanup is held between them | 3D163D
fixed | pl00 state 3D1670: +E3C decrements on stock ticks and its old-value zero state transition is held between them | 3D1789
fixed | pl00 state 3D1820: +E3C decrements on stock ticks and its old-value zero state transition is held between them | 3D18A5
