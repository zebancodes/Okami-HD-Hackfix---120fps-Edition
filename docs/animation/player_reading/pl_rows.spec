group player
# --- pl00's update (3A9630, vt68B280 slot 8), Amaterasu ------------------
count 3A98E1 | pl00 update: Amaterasu's alpha +D78 near the camera, a byte set to (a + (t - a) x 0.3) x 255 a tick toward a target by distance: stored on stock ticks, stock's sequence
count 3A9920 | pl00 update: the alpha +D78 back to opaque, a + max(1/255, (1 - a) x 0.3) a tick: stored on stock ticks
count 3A9941 | pl00 update: the alpha +D78 -= 25 a tick while B664DC bit 0 fades her out: stored on stock ticks
count 3A9B7A | pl00 update: +15C2, the three ticks' grace after the B6B2A3 pause mode (3AD034 tests it): a tick each on stock ticks; skipped, the cmovs reads SF clear
count 3A9C6F | pl00 update: countdown +1178, a tick each
count 3A9D15 | pl00 update: +1176 counts the ticks a button is held, a tick each
count 3A9D28 | pl00 update: countdown +117D, a tick each
notyet 3A9E07 notyet:3A9ECA | pl00 update: the slide-off push, +10C0/+10C8 += 2 x (+FE0, +FE8) (and +1 when that is small) while she falls onto something (+1010 bit 7, near the ground, +E54 < 0), with its sound and 3A78E0: on stock ticks only, as the velocity's other changes
srcx 3A9ED5 | pl00 update: the slide, x += +10C0 a tick: s of it (the velocity keeps stock's value, its push and damping on stock ticks)
pre 3A9F09 | pl00 update: the slide, z += +10C8 a tick (xmm0 holds +10C8): s of it
countlast 3A9F37 | pl00 update: the slide's damping +10C0 x 0.9 a tick: on the last tick of each stock period, after that period's moves, as stock orders it
countlast 3A9F3B | pl00 update: the slide's damping +10C8 x 0.9 a tick, on the last tick of each stock period
countlast 3A9F55 | pl00 update: the slide's ground friction +10C0 x 0.7 a tick (on the ground), on the last tick of each stock period
countlast 3A9F5A | pl00 update: the slide's ground friction +10C8 x 0.7 a tick, on the last tick of each stock period
count 3A9FE1 | pl00 update: countdown +117A (calls 3CC950 every 8 ticks), a tick each
notyet 3A9FE8 notyet:3A9FF6 | pl00 update: +117A's every-8-ticks test reads the decremented register: between stock ticks, not yet
count 3AA01D | pl00 update: item timer B4DFB8 (900 ticks, set by 3D0050 for item type 4 in 413370, spawning effect 0x31 every 32 ticks), a tick each
notyet 3AA03D notyet:3AA0AD | pl00 update: B4DFB8's every-32-ticks effect test (the stored value): between stock ticks, not yet
count 3AA0D1 | pl00 update: item timer B4DFBA (900 ticks from 3D0000, effect 0x33 every 32 ticks), a tick each
notyet 3AA0D8 notyet:3AA14D | pl00 update: B4DFBA's every-32-ticks effect test: between stock ticks, not yet
count 3AA167 | pl00 update: item timer B4DFBC (from 3D0010, effect 0x32 every 32 ticks), a tick each
notyet 3AA174 notyet:3AA1F3 | pl00 update: B4DFBC's every-32-ticks effect test: between stock ticks, not yet
count 3AA208 | pl00 update: +117F counts up while 3CE4C0 holds, effect 0x28 every 8 ticks, a tick each
notyet 3AA20E notyet:3AA266 | pl00 update: +117F's every-8-ticks test (the stored byte): between stock ticks, not yet
count 3AA275 | pl00 update: countdown +11E6, a tick each
count 3AA437 | pl00 update: countdown +1186, a tick each
count 3AA44D | pl00 update: countdown +11E4, a tick each
count 3AA468 (0x3AA45C,0x3AA46C,(0x3AA45C,0x3AA463,0x3AA466,0x3AA468),None) | pl00 update: countdown +1188 (+118C cleared at 0), a tick each; skipped, the jne reads "not finished"
count 3AA543 | pl00 update: countdown +11EF, a tick each
count 3AA6B9 | pl00 update: the global countdown 9C8724 that holds her in its own path, a tick each
count 3AA74D | pl00 update: +117E, a material crossfade (1 - v/255, v/255), -10 a tick: on stock ticks
count 3AA814 | pl00 update: +117E, +10 a tick: on stock ticks
count 3AAD63 | pl00 update: +1144, the lock-on retarget delay (B6AC44 x 2 ticks before +1110 takes +1108), a tick each; skipped, the jne reads "not yet"
count 3AB234 | pl00 update: her speed +E48 x 0.5 when the rise meets a ceiling (+E54 > 1): once per stock tick, as stock's tick-long contact
srcblend 3AC5F6 | pl00 update: her pitch +B0 approaches the ground's slope by 0.3 a tick (xmm10 = 0.3 is also 3ACAEB's alpha threshold)
srcblend 3AC6CB | pl00 update: her pitch +B0 returns to level by 0.3 a tick in the air
# --- wp02's beads (382340, one of six per call from 3822D0): a rosary's shots
lin 3827F7 | wp02 bead, homing (state 3): its rate +1938 += 0.8 a tick up to 8 (turn in degrees x 2 and forward speed)
lin 38284D | wp02 bead, homing: the turn toward the target, rate x pi/180 x 2 a tick, passed to 2DE2A0: s of it
pre 3828BF | wp02 bead, homing: x += the forward step (rate, in the bead's frame) a tick: s of it; the velocity +16E0 keeps stock's value
pre 3828CB | wp02 bead, homing: y += the forward step's y, s of it
pre 3828E1 | wp02 bead, homing: z += the forward step's z, s of it
count 382A83 | wp02 bead, homing: its countdown (param 4), a tick each; skipped, the jne reads "not yet"
pre 382B74 | wp02 bead, bounced off (state 5): x += v.x a tick (xmm0 holds +16E0): s of it
srcx 382B8A | wp02 bead, bounced off: y += v.y a tick: s of it
pre 382BA6 | wp02 bead, bounced off: z += v.z a tick (xmm0 holds +16E8): s of it
countlast 382BBF | wp02 bead, bounced off: v.x x 0.93 a tick, on the last tick of each stock period after its moves
countlast 382BD0 | wp02 bead, bounced off: v.y -= 0.6 (gravity) a tick, on the last tick of each stock period
countlast 382BE6 | wp02 bead, bounced off: v.z x 0.93 a tick, on the last tick of each stock period
count 382C1B | wp02 bead, bounced off: its countdown, a tick each
notyet 382C1D notyet:382636 | wp02 bead, bounced off: the test of the countdown's old value (0 ends the state): between stock ticks, not yet
pre 382CDF | wp02 bead, dash (state 7): x += the step (20 forward in its frame) a tick: s of it
pre 382CEB | wp02 bead, dash: y += the step's y, s of it
pre 382D01 | wp02 bead, dash: z += the step's z, s of it
count 382D4F | wp02 bead, dash: its countdown (2), a tick each
notyet 382D51 notyet:382636 | wp02 bead, dash: the test of the countdown's old value: between stock ticks, not yet
blend 382E13 | wp02 bead, lying (state 8): y approaches its rest height +11CA by 0.2 a tick
count 382E2F | wp02 bead, lying: its countdown (60), a tick each
notyet 382E31 notyet:382E5E | wp02 bead, lying: the test of the countdown's old value: between stock ticks, not yet
lin 382FCD | wp02 bead, homing again: the turn, rate x pi/180 x 4 a tick: s of it
pre 383043 | wp02 bead, homing again: x += the forward step a tick, s of it
pre 38304F | wp02 bead, homing again: y += the forward step's y, s of it
pre 383065 | wp02 bead, homing again: z += the forward step's z, s of it
count 38317E | wp02 bead, homing again: its countdown, a tick each; skipped, the jne reads "not yet"
pre 383313 | wp02 bead, launched (state 13): x += v.x a tick (xmm0 holds +16E0): s of it
srcx 383329 | wp02 bead, launched: y += v.y a tick: s of it
pre 383345 | wp02 bead, launched: z += v.z a tick (xmm0 holds +16E8): s of it
countlast 383367 | wp02 bead, launched: v.y x 0.98 a tick, on the last tick of each stock period after its moves
countlast 38336B | wp02 bead, launched: v.x x 0.98 a tick, on the last tick of each stock period
countlast 383381 | wp02 bead, launched: v.z x 0.98 a tick, on the last tick of each stock period
count 383439 down | wp02 bead, launched: its countdown (10), a tick each: sub by r14b, which is 1 (set at 382546 before the switch, not written on this path); skipped, the jne reads "not yet"
# --- wp3a's beads (397C70, from 397B70)
pre 3981C1 | wp3a bead, homing (state 3): y += the forward step (18 in its frame, toward a jittered target) a tick: s of it
pre 3981CA | wp3a bead, homing: x += the step's x, s of it
pre 3981E1 | wp3a bead, homing: z += the step's z, s of it
count 3982E0 | wp3a bead, homing: its countdown (param 4), a tick each; skipped, the jne reads "not yet"
pre 398436 | wp3a bead, bounced off (state 5): x += v.x a tick (xmm0 holds +16E0): s of it
srcx 398447 | wp3a bead, bounced off: y += v.y a tick: s of it
srcx 398462 | wp3a bead, bounced off: z += v.z a tick: s of it
countlast 39847A | wp3a bead, bounced off: v.x x 0.93 a tick, on the last tick of each stock period after its moves
countlast 39848B | wp3a bead, bounced off: v.y -= 0.6 (gravity), on the last tick of each stock period
countlast 3984A2 | wp3a bead, bounced off: v.z x 0.93, on the last tick of each stock period
count 3984D6 | wp3a bead, bounced off: its countdown (5), a tick each
notyet 3984DA notyet:39888D | wp3a bead, bounced off: the test of the countdown's old value: between stock ticks, not yet
pre 3986AC | wp3a bead, launched (state 13): x += v.x a tick (random +-5, +-5, 15 in the owner's frame, set once): s of it
pre 3986C0 | wp3a bead, launched: y += v.y a tick, s of it
pre 3986DB | wp3a bead, launched: z += v.z a tick, s of it
count 398792 | wp3a bead, launched: its countdown (12), a tick each; skipped, the jne reads "not yet"
count 398833 | wp3a bead (state 15): its countdown, a tick each; skipped, the jne reads "not yet"
# --- wp3a's second and third bead kinds (398920, 399590, from 397B70; the same code)
lin 398D3D | wp3a bead kind 2, flight (state 3): its speed +1938 += 20 a tick from 5 up to 100
pre 398DD2 | wp3a bead kind 2, flight: y += the forward step (the speed, in its frame) a tick: s of it
pre 398DDB | wp3a bead kind 2, flight: x += the step's x, s of it
pre 398DF6 | wp3a bead kind 2, flight: z += the step's z, s of it
count 398F48 | wp3a bead kind 2, flight: its countdown (param 4), a tick each; skipped, the jne reads "not yet"
pre 39909A | wp3a bead kind 2, bounced off (state 5): x += v.x a tick (xmm0 holds +16E0): s of it
srcx 3990AB | wp3a bead kind 2, bounced off: y += v.y a tick: s of it
srcx 3990C6 | wp3a bead kind 2, bounced off: z += v.z a tick: s of it
countlast 3990DE | wp3a bead kind 2, bounced off: v.x x 0.93, on the last tick of each stock period after its moves
countlast 3990EF | wp3a bead kind 2, bounced off: v.y -= 0.6 (gravity), on the last tick of each stock period
countlast 399106 | wp3a bead kind 2, bounced off: v.z x 0.93, on the last tick of each stock period
count 399139 | wp3a bead kind 2, bounced off: its countdown, a tick each
notyet 39913C notyet:3994F5 | wp3a bead kind 2, bounced off: the test of the countdown's old value: between stock ticks, not yet
pre 3992D4 | wp3a bead kind 2, launched (state 13): x += v.x a tick (xmm0 holds +16E0): s of it
pre 3992EC | wp3a bead kind 2, launched: y += v.y a tick, s of it
pre 399307 | wp3a bead kind 2, launched: z += v.z a tick, s of it
count 399410 | wp3a bead kind 2, launched: its countdown, a tick each; skipped, the jne reads "not yet"
count 39949C | wp3a bead kind 2 (state 15): its countdown, a tick each; skipped, the jne reads "not yet"
lin 3999AD | wp3a bead kind 3, flight (state 3): its speed +1938 += 20 a tick from 5 up to 100
pre 399A42 | wp3a bead kind 3, flight: y += the forward step a tick: s of it
pre 399A4B | wp3a bead kind 3, flight: x += the step's x, s of it
pre 399A66 | wp3a bead kind 3, flight: z += the step's z, s of it
count 399B81 | wp3a bead kind 3, flight: its countdown (add 0xff), a tick each; skipped, the jne reads "not yet"
pre 399CD3 | wp3a bead kind 3, bounced off (state 5): x += v.x a tick: s of it
srcx 399CE4 | wp3a bead kind 3, bounced off: y += v.y a tick: s of it
srcx 399CFF | wp3a bead kind 3, bounced off: z += v.z a tick: s of it
countlast 399D17 | wp3a bead kind 3, bounced off: v.x x 0.93, on the last tick of each stock period
countlast 399D28 | wp3a bead kind 3, bounced off: v.y -= 0.6, on the last tick of each stock period
countlast 399D3F | wp3a bead kind 3, bounced off: v.z x 0.93, on the last tick of each stock period
count 399D72 | wp3a bead kind 3, bounced off: its countdown, a tick each
notyet 399D75 notyet:39A0FF | wp3a bead kind 3, bounced off: the test of the countdown's old value: between stock ticks, not yet
pre 399F0D | wp3a bead kind 3, launched (state 13): x += v.x a tick: s of it
pre 399F25 | wp3a bead kind 3, launched: y += v.y a tick, s of it
pre 399F40 | wp3a bead kind 3, launched: z += v.z a tick, s of it
count 39A01A | wp3a bead kind 3, launched: its countdown, a tick each; skipped, the jne reads "not yet"
count 39A0A6 | wp3a bead kind 3 (state 15): its countdown, a tick each; skipped, the jne reads "not yet"
