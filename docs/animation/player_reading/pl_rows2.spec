group player
# --- pl00's attack lunge (3B8540, called by the dispatcher 3AF020) ----------
lin 3B884A | pl00 lunge (3B8540, sub-state 2): the speed +E48 = (+F48 - 0.5) x 0.2 as it starts, a displacement per tick: +E48 is the port's per-tick-at-this-rate speed (README), so s of it
lin 3B91E3 | pl00 lunge (3B8540, sub-state 8): +E48 = (+F48 - 0.5) x 0.2 as it starts: s of it
lin 3B96AF | pl00 lunge (3B8540, sub-state 11): +E48 = (+F48 - 0.5) x 0.2 as it starts: s of it
countlast 3B8FA3 | pl00 lunge (3B8540): +E48 x 0.75 a tick after it moves her (added to the root step +EC8): on the last tick of each stock period, so the s-sized moves sum to stock's per stock tick
# --- pl00's state 3AFA90 (the fall to defeat; sub-state 2 counts +E3E up) ---
count 3AFEAD | pl00 state 3AFA90, sub-state 2: +E3E counts up a tick each (sounds at 0x6F and 0x8E, +D40 bit 1 at 0xA3): on stock ticks
notyet 3AFE23 notyet:3AFE55 | pl00 state 3AFA90, sub-state 2: the sound at +E3E = 0x6F: between stock ticks, not yet (the count holds its value for the stock tick's other ticks)
notyet 3AFE5A notyet:3AFE8F | pl00 state 3AFA90, sub-state 2: the sound at +E3E = 0x8E: between stock ticks, not yet
# --- wp1c (38F400, from 38EEE0): a thrown piece that rolls -----------------
lin 38F438 | wp1c (38F400): xmm6 = 0.5, the slope push's factor (+FE0/+FE8): its velocity +E20/+E28 is per tick at this rate (built from the owner's +E48; x += v unscaled, the damping 0.94^s by decay_factors), so the push added at the throw is s of stock's
pre 38F714 | wp1c rolling (sub-state 1): v.x += 0.5 x +FE0 a tick on the ground (xmm0 holds it, 0.5 s by the lin): s of it again, a per-tick-at-this-rate velocity gains s^2 of stock's push a tick
pre 38F71C | wp1c rolling: v.z += 0.5 x +FE8 a tick on the ground: s of it again (s^2 in all)
# --- wp1d (391D60, from 38FDF0) --------------------------------------------
dst 391DD3 ("slowmo",0x391DB2) | wp1d (391D60): xmm7 = the slow-motion factor (23AD90), the function's dt; its readers, all per-tick steps: the spin +B4 += 6 deg x dt, +1090 += dt, the bob y += sin(+1110) x 0.7 (1.7) x dt, its phase +1110 += 0.24 dt, the countdown +1078 -= dt, the turn min(+1078, 10) deg x dt, the flight's velocity +E18 += dt and the move by +E10 x dt, the countdown +E28 -= dt
