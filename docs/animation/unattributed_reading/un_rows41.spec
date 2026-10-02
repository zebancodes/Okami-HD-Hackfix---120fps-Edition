# 2026-10-01: the weapons' falls. 20EA30 (y += dt x vy, vy -= g x dt, dt read nowhere
# else) takes dt in xmm2; these slot-8 updates pass their slow-motion factor (23AD90's
# 0.25 or 1, kept in xmm6/xmm7 or passed from xmm0) unscaled. The enemies' calls pass
# +1080, whose loads are step rows already; no weapon here has a slowmo row.
group player
callscale 37ED84 | Weapon update 37EC90 (vt6AD470[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 383814 | Weapon update 383750 (vt6AD5D0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 3845DA | Weapon update 3844F0 (vt6AD6D0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 385698 | Weapon update 3855D0 (vt6AD868[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 386409 | Weapon update 386320 (vt6AD980[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 386BFE | Weapon update 386AE0 (vt6ADA30[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 3881BA | Weapon update 3880C0 (vt6ADAE0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 3897F7 | Weapon update 389730 (vt6ADC20[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 389E65 | Weapon update 389D50 (vt6ADCE0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 38B3AF | Weapon update 38B280 (vt6ADDE0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 38BF45 | Weapon update 38BE70 (vt6ADEE8[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 38C91B | Weapon update 38C810 (vt6ADFF0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39A5B3 | Weapon update 39A520 (vt6AE5C0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39AAFB | Weapon update 39AA10 (vt6AE6C0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39CB75 | Weapon update 39CA60 (vt6AE770[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39D3F9 | Weapon update 39D2E0 (vt6AE820[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39D42B | Weapon update 39D2E0 (vt6AE820[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39DA47 | Weapon update 39D990 (vt6AE8D0[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39E2C6 | Weapon update 39E1E0 (vt6AE980[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 39FBDB | Weapon update 39FAB0 (vt6AEA38[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 3A0A25 | Weapon update 3A0940 (vt6AEB38[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 3A1641 | Weapon update 3A1540 (vt6AEBE8[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
callscale 3A2372 | Weapon update 3A2290 (vt6AEC98[8]): its gravity fall's dt, the slow-motion factor, is a per-tick share: scale it at the call.
# 2026-10-01, second batch
group objects
# 47FF90, a camera mode (dispatched by 475C70): the request approaches of the other modes
callblend 4803FC | Camera mode 47FF90: yaw +1B4 toward the request +39C plus pi: constant 0.1 approach and its 0.1396 limit.
count 480401 | Camera mode 47FF90: pace the yaw request's duration +398.
callblend 480436 | Camera mode 47FF90: pitch toward +3A4: constant 0.2 approach and its 0.279 limit.
count 48043B | Camera mode 47FF90: pace the pitch request's duration +3A0.
# 472E80 (camera mode 8 path of 4760E0): the drop while the player falls, 2 x +290 below the view
count 472F4F | Camera 472E80: +290 grows by 2 a tick while the player falls (vy below -2, off the ground): pace it; the drop is recomputed from it each tick.
count 472F83 | Camera 472E80: the undo of that +2 when the drop passes -20 (sub cx, 2; store): skip it with the add between stock ticks.
count 472F90 | Camera 472E80: +290 shrinks by 1 a tick back to 0 once the player lands: pace it.
# the moving platforms (vt7AA108's states; ids 0x819, 0x82E, 0x842)
pre 489E36 | Platform state 489DD0: y += the speed +1080 a tick (rising): scale the step first.
src 489E4E | Platform state 489DD0: y -= the speed +1080 a tick (sinking): scale the step.
lin 48A017 | Platform 0x82E (489FE0, phase 4): its speed loses 0.1 a tick.
lin 48A080 | Platform 0x82E (489FE0, phase 1): its speed gains 0.02 a tick.
count 48A05B | Platform 0x82E (489FE0, phase 3): pace the 5-tick pause +10A0 with the speed at 0.
notyet 48A061 notyet:48A0A5 | Platform 0x82E: the pause's end test reads the old count (ecx); between stock ticks take the not-yet path.
count 489D93 | Platform state 489C60: pace the 5-tick shake +10A0 (its random +-0.6 jitter is resampled each tick at stock amplitude) before the next state.
count 489F8F | Platform state 489F20: pace the 5-tick shake +10A0 before it stops.
gatefn 48DED0 | Treasure fanfare 48DED0 (from 48DA60 and 48ECA0): its count-up +8F (sound 0x1BC at 23), the per-tick fade of 18EB20's +1D0 and the wait for its message to close run together at stock cadence.
group actor
# 2A2B40 (an enemy's circling, from 29F770, sub-state 1)
lin 2A2C14 | 2A2B40: the circling radius +13B4 shrinks by 4 a tick (beyond 200 from the player).
lin 2A2C26 | 2A2B40: the radius +13B4 shrinks by 6 a tick (flag +13C9).
lin 2A2C43 | 2A2B40: the radius +13B4 grows by 2 a tick up to 110 + 22 x +1146.
lin 2A2C8F | 2A2B40: the circling angle +13B0 turns by -0.0436 a tick.
lin 2A2C99 | 2A2B40: the circling angle +13B0 turns by 0.0436 a tick.
group menu
# the item shop's panels (globals 7A9C50, 7A9D30, 7A9E10, updated by 4BA500): their drop-in bounce
gatefn 43C010 | Shop panel 43BF40's drop-in (state 1): v += 6, y += 2v, a bounce at 0 by -0.47 until |v| < 3, together at stock cadence (its tail-jump target; the panel's pad-reading states stay per tick).
gatefn 43F6B0 | Shop panel 43F610's drop-in, the same bounce at stock cadence.
gatefn 442790 | Shop panel 4426F0's drop-in, the same bounce at stock cadence.
countlast 43E1D1 | Shop panel 43BF40's exit (state 2, sub-state 1): its speed +B8 grows x1.7 a tick: only on the last tick of each stock period.
srcx 43E1E1 | Shop panel 43BF40's exit: y -= the speed +B8 a tick, up to -512: scale the step.
