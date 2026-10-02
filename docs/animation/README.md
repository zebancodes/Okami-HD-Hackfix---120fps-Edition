Animation timing inventory
==========================

Build 6990973, main.dll. Static analysis only -- nothing here has been run in
the game yet. Produced 2026-09-18 by:

    tools/ghidra_export.py        decompiled C, one file (existing)
    tools/pcode_census.py         every self-updating store + every clock read, from Ghidra p-code
    tools/animation_inventory.py  -> sites.csv, clock_reads.csv, summary.md in this directory
    tools/ghidra_lines.py         any function with an instruction RVA on every C line

The question this answers: *what moves the pictures on screen, and what clock is
each thing counted in?* Every animation in this engine is advanced once per game
tick, so at 120 fps anything the port did not convert runs four times as fast --
the "Now Loading" sign, the menu transitions, torches and portals included. The
code below is where each one lives.

Summary
-------

1. **There is no single animation clock to fix.** The census finds 12 485
   stores whose new value is computed from their old one (bit operations and
   plain copies excluded; 1 626 of those are in linked middleware). About 1 500
   are already covered by the existing patch tables. The rest are spread over a
   handful of *shared engines* and a long tail of per-class code.
2. **The shared engines are where the leverage is.** Five of them drive most of
   what is visible:
   * the **effect engine** (`esp*`): every particle, flame, spark, glow,
     trail and scrolling-texture effect in the world -- 134 sites, 1 covered;
   * the **model material state** (`main+20CF90`): per-object UV scrolling and
     colour/alpha animation -- 473 sites in 113 functions, 137 covered;
   * the **2D layout player** (`main+1B54E0`): the keyframe tracks of every HUD
     and menu element -- lengths already x4 at 120 via `mode_multipliers.h`,
     but its sprite-sheet flipbook is not;
   * the **HUD base fade** (`cCockBase` slot 3) -- not covered;
   * the **frame counter** read as a clock: 358 reads in about a dozen
     encodings, of which the existing tables cover the two simplest.
3. **The stock game does not always tick at 30 Hz.** Six places set the mode
   byte to 1 -- the 60 fps configuration -- for the options pages, the
   memory-card screens, boot/title and the *inside* of the pause menu. In those
   contexts the stock reference speed is 60 ticks/s, so at 120 fps the correct
   slowdown is 2x, not 4x. The patch pins the mode byte to 1 and so has lost the
   information needed to tell the two apart. This also means some existing
   fixes are probably **over-corrected** (see "Stock tick rate").
4. **The port's own compensation stops at 60 fps.** Besides the two encodings
   already handled (`mode_constants.h`, `mode_multipliers.h`) there are at least
   eight more ways the port wrote "twice as long at 60": `x += mode * k`,
   `timer -= mode`, `(mode != 2) + 1`, `n / mode`, `x % mode`, a tick-parity
   gate and more. All are right at 30 and 60 and exactly 2x fast at 120.

Everything below is backed by a decompiled line and an RVA. Where something is
an inference rather than a reading, it says so.


How the game keeps time
-----------------------

| address | name | written by | meaning |
|---|---|---|---|
| main+B6AC20 | frame counter | `flower_tick` (+1 per tick), `objScroll`'s init (+1 and back, around a loop that does not read it) | the only global clock; read 358 times |
| main+B6AC38 | time scale | `flower_tick` only | 1.0 / 0.5 (patch: 0.25); consumed by the ~140 sites the port converted |
| main+B6AC3C | frame divider | `flower_tick` | no reader anywhere (settled in the main README) |
| main+B6AC40 | duration shift | `flower_tick` | `shl reg, cl` on 321 `cPad::ActSet` windows |
| main+B6AC44 | fps byte | `flower_tick` | 30 / 60 (patch: 120) |
| main+B6AC45 | mode byte | 21 writers, below | 2 = 30 fps config, 1 = 60 fps config |
| main+B20830 | world clock (time of day) | adder `4AED90` (from the advance `4AF800` and the transition `4AF910`), setter `4AFBE0` | 1 800 000 a day, +100 a tick: 10 minutes a day at 30 Hz. Found 2026-09-19; see below |

**The world clock was missing from this inventory.** The census records a
self-updating store by its field, and this one is `mov r8d, [clock]; add r8d,
edx; ...; mov [clock], r8d` inside a leaf whose step arrives in `edx` from its
callers (`mov edx, 100`, or `(target - clock) / steps`). It records neither
that store nor the caller's constant, so the tracer never instrumented it; only
the transition's step count (`4AF9B9`, `+0x28`) and the day counter showed up.
Found by a scan of the decompiled C for globals that update themselves (a
search by *shape*, not by census row), which led to the lighting update
`4AC680` keying its palettes on `clock % 1800000`. Every global of that shape
is worth a second look for the same reason: `tools/gen_day_clock.py` and
`src/day_clock.h` hold the family, `docs/animation/day_clock.csv` its evidence.

The day/night controller is a global object at main+B6A9B0. Once per tick the
dispatcher calls its update (`4BA589` -> thunk `4AF770` -> `4AF780`), which
records the clock as it was (`+8`, and `+4` = that % day: what "did the clock
cross X since the last update", `4AF610`, compares against), then does one of:
nothing (the frozen flag `[B205C0]+0x360 & 0x4000000`), a requested jump
(`+0x30` -> `4AFBE0(+0x2C)`), the transition (`+0x28` steps left, `+0x24`
target, `+0x34` delay; `4AF910`), or the advance (`4AF800`: after nine flag
gates, `4AF6D0`'s holds before dusk, and the same delay, `clock += 100`). The
lighting's palette boundaries are at main+7AD6B0: 02:24, 12:00, 15:36, 18:00
and 22:48 in the game's own hours (75 000 units each), each crossfaded over
90 000 units (30 s at stock); `4AF380` calls 00:00-15:36 day and the rest
night.

Scripted time-lapses go through the requested jump, which the day clock's gate
does not cover. Four task loops set `+0x30`/`+0x2C` on every pass and wait a
tick through the task wait (`4567C0`, whose countdown `4566CB` counts real
ticks). Three (`4B0010`, `4B0190`, `4B0550`) lerp on the event player's
playhead (`B661E0+0x348`) and leave on its done bit (`+0x394` & 2). Its
integrator (`476A16`, in `4763F0` of section 6 below) reads the real mode byte,
so those lapses run 2x at 120. The fourth (`4B0430`, in `4B0310` before
`4B0550`) lerps on its own count of passes, so it runs one pass a tick: 4x at
120, 2x at 60. Two of them come round every day: the controller starts
`4B00C0` (to 16:48) when its clock crosses 15:36 and `4AFF50` (to 00:00) at
22:48 (`4AEE60`). The day clock's watch times each one; none is fixed yet.

A "tick" is one call of the per-frame dispatcher `main+4BA500`, which calls
every subsystem once: the HUD manager (`3F3F70`/`3F3A10` on B1C7C0), the pause
menu (`413CC0` on B1EBA0), the options controller (`149F50` on B1E100), the scene
transition model (`4396F0` on B4DF40), the effect manager (`18E1A0`), the object
system, and so on. Its second branch (`4BA85x`) is the loading path. Nothing in
any of these consults wall-clock time.

### Stock tick rate

The mode byte decides the stock tick rate: `flower_tick` writes fps 60 and time
scale 0.5 when it is 1, and the main README measured the stock title phase at
~60 ticks/s in exactly that state, even with PS2 display mode on. Its writers:

| writes 1 | context |
|---|---|
| `149F50` case 3 | options controller, once a page is open (and restores the saved value at the end) |
| `1BFCB0`, `1BFFA0` | memory-card screens (restore the saved value afterwards) |
| `415B30` | pause menu, **when the opening drop has settled** |
| `5FE540` (`cMcBoot`[1]) | boot / title |
| `6059A0` | title-side sequence (sets 2 and 1) |

| writes 2 | context |
|---|---|
| `149F50`, `14A500` | options controller, during its enter/leave transitions |
| `4147F0` | pause menu closing (state 3) |
| `409030`, `494490`, `4B5B20`, `5FF830`, `603190`, `608F20` | option exit, title/loading task, kernel reset, `cTitle`, title-side sequences |

So in the stock game:

| context | stock ticks/s | correct slowdown at 120 |
|---|---|---|
| gameplay, HUD, world, effects | 30 | 4x |
| loading screen | 30 (the reported 4x confirms it) | 4x |
| pause menu opening drop, closing | 30 | 4x |
| pause menu interior, options pages, memory card, boot/title | **60** | **2x** |

*Inferred, needs one measurement:* the table assumes the stock pacer follows
the fps config in menus as it does in the title phase. One stock (`Passthrough=1`)
log line with an options page open settles it: `ticks/s` ~60 means the table
holds.

**Consequence for the existing patch.** `frame_phases.h` halves (at 60) or
quarters (at 120) the `sin(frameCounter * 10 % 360)` pulse in seven `cOption*`
screens, `cOption`/`cOptionEx`/`cOptionHelp`/`cOptionPairing` (`40ADB0`) and
`cMcAction` (`1C5870`). If those screens tick at 60 in stock, the patched pulse
runs at **half** the stock speed at both 60 and 120 fps. The enemy-marker and
`vt*` entries in the same table are gameplay and are right.

**What a fix needs.** Today the patch rewrites every `mov byte [mode], 2` to 1,
so nothing records which context the game is in. Retargeting the writers'
displacements at a private *shadow* byte (and the three places that save the
mode byte for a later restore) would keep the engine in its fast configuration
while preserving "stock would be at 30 / 60 here" for any fix that needs it.


The shared engines
------------------

### 1. The effect engine (`esp*`) -- torches, sparks, glows, portals

Every world effect is an `esp` instance: 1 024 slots at main+89CDD0, 0x370
bytes each, stepped by the manager `main+18E1A0` (one call of vtable slot 3 per
live slot per tick). The manager has a built-in divider -- it only runs when
`frameCounter % [main+978F50] == 0` -- but main+978F50 is zero-initialised .bss
with exactly one reader and no writer, i.e. a stripped debug knob.

Slot 3 (`1927D0`) calls slot 1, which for most types is `192830`, which calls the
common instance step `1928F0`. That step and the shared virtual slots are the
same code for all 42 effect classes:

| RVA | slot | per tick | stock meaning |
|---|---|---|---|
| 1928F6 | step | `age(+0x260)++` vs `lifetime(+0x262)` | lifetime in ticks |
| 19292C | step | `+0x277++` vs `+0x276` | second duration (fade-out window) |
| 19299A..1929BA | step | `pos(+0x160..168) += vel(+0x170..178)` | velocity in units/tick |
| 1929FF | step | `spin(+0x27C) = wrap(spin + rate/90)` | spin rate from data |
| 18FF7C | 9 | `key(+0x264)++` vs `+0x266`, loops or kills | colour/alpha keyframe index (used as an array index) |
| 190AEA | 10 | `delay(+0x113)--` | spawn delay |
| 18FBE0 | 11 | `hold(+0x26D)--`, reload `+= +0x26C`, `cell(+0x26E)++` | **sprite-sheet flipbook** -- flames |
| 190DA0 | 12 | `scale += rate; rate *= decay(+0x190)`; wobble `+0x1A0 += +0x19C` (short angle) | growth and pulsing |
| 190D00 | 13 | `rot += angvel(+0x1B4..1BC)`, wrapped | rotation |
| 191110 | 14 | turbulence: `+0x294 += d*0.001`, `*= (1 + d*0.001)`; phases `+0x288/+0x28C` | wobble |
| 191090 | 15 | `vel *= drag(+0x16C)` | drag |

*Correction, 2026-09-23:* the step's `+0x160 += +0x170` is velocity +=
acceleration, not position and velocity. The drag slot (`191090`) multiplies
`+0x160` by `+0x16C`; the emitter (`195EC0`) sets `+0x160` from a random
direction times a speed and only the y of `+0x170`. The position is `+0x60`,
moved by slot 14 (`191110`: position += velocity, plus the turbulence offset);
scale is `+0x40` (slot 12) and rotation `+0x50` (slot 13). The keyframe step
(`18FF60`) loops or kills on the old index. All of the shared step and slots
9-15 are now in `world_anims.h`.

Emitters (`espEmitter*`): spawn countdown `+0x1AA -= 2` (`1944B0`, `194300`),
per-tick velocity and scale multipliers from data (`1947A0`, `194BB0`), and a
float spawn timer `+0x19C -= 1.0` (`195198`, the one site already covered, by
`phase_steps.h`). That last site has a second branch that subtracts **0.25**
while `[B9C1F50]+0x234 == 1` -- the game's own slow-motion state (`23B750`,
41 callers across enemies, the player and effects; plausibly Veil of Mist,
unconfirmed). Any fix has to compose with those native 0.25 factors.

Texture scrollers among the effect types:

* `espStrip`/`esp38` (`1A02A0`): `+0x2EC += +0x2F0`, wrapped -- scrolling strips;
* `esp08` (`19FB20`): two UV offsets `+0x2C8/+0x2CC` += rates, wrapped to +-2;
* **`esp20` (`1A6C60`, "EFF_TEX")**: reaches into a *model* (`+0x2C0`), and
  every tick adds `+0x2D0/+0x2D4` to that model's material UV offset
  (`material+0x60/+0x64`), adds a sine wobble whose phases step
  `+0x2E8 += +0x2E0`, `+0x2EC += +0x2E4`, wraps to +-2, and drives the model's
  RGBA from the effect's keyframes. This is how the effect system animates the
  surface of a model -- swirling portals, flowing water and glowing surfaces
  are the obvious users.

None of this was covered. Because it is one engine with data-driven parameters,
converting the ~20 shared sites converts every effect in the game at once; the
per-type overrides (`esp04/05/08/10/12/13/14/17/18/20/25/27/29/31/34/35/37`) add
roughly 40 more. `sites.csv`, subsystem `effect`, lists all 134.

*Update, 2026-09-23:* `world_anims.h` now has the shared step and slots 9-15,
the emitters' ages, slots 6-9 (spin, offsets, free flight, detach) and the
spawn interval's floor, and the per-class steps of `esp20`, `esp08/40`, the
strips (`1A02A0`), `esp12`, `esp13`, `esp25` and `esp31`. What is
left is listed at the end of the second entry.

### 2. Model material state (`main+20CF90`)

`FUN_18020cf90(model, i)` returns material `i` of a model; +0x50..+0x58 is RGB,
+0x5C alpha, +0x60/+0x64 the UV offset. 113 functions write it every tick,
473 sites, mostly object classes (`et*`, `ut*`, `hm*`, `wp*`, `em*`, `es*`).
137 are covered by `phase_steps.h` (literal float steps with a limit test).

The clearest example, and a strong torch/brazier candidate, is **`et08`
(`2E2FA0`)**: every tick it scrolls six materials' V by -0.03 or -0.06 (wrapped
to +-1) -- a flowing flame or smoke texture -- and it spawns an effect every 16
or 8 ticks through `((u16)[this+0xE74] + frameCounter) & 0xF` / `& 7`. That
gate is one `frame_gates.h` does not see, because the per-object phase is added
before the mask. The six scroll rates are a `.data` table at main+7A0138..7A014C.

Two more model-wide clocks:

* `cModel` slot 1 (`20C620`, every model's draw submit): alpha fade-in
  `+0xD79 += 0x19` to 0xFF -- every object that pops in fades 4x fast;
* `20C220` (per-model draw): in one state it selects vertex shader 3 and
  uploads `(float)(u16)frameCounter` as its time constant (`transVectors(.., 5)`)
  -- a shader animation driven by raw tick count.

### 3. The 2D layout player (`main+1B54E0`) -- every HUD and menu element

Every `cCock*` and `cSubScr*` owns one. Per element (200-byte records) and per
tick:

| RVA | track | counter | port compensation | at 120 today |
|---|---|---|---|---|
| 1B2A50 | flipbook (sprite sheet) | `hold(+0x86)++` | counts only when `(frameCounter & 1) == phase` in mode 1 | **2x fast** |
| 1B26E0 | position | `+0x88++` | length x mode (`1B8C50`) | right (`mode_multipliers.h`) |
| 1B2940 | scale | `+0x8A++` | length x mode (`1B8CB0`) | right |
| 1B2840 | rotation | `+0x8C++` | length x mode (`1B8C80`) | right |
| 1B2530 | colour | `+0x8E++` | length x mode (`1B8C20`) | right |

The four track getters and the keyframe search/interpolation (`1B4740`,
`1B47C0`) are the six `mode_multipliers.h` sites that were labelled "esp80";
every caller is in this player, never in `esp80` (labels corrected). The
flipbook's parity gate is the remaining gap. The census cannot show these as
"covered" because the fix scales the track *length*, not the counter.

### 4. HUD base fade (`cCockBase` slot 3, `3F6660`)

`fade(+0x5A)` steps by one per tick toward `+0x58` (in) or 0 (out) and every HUD
element's position is lerped by `fade / length`. Gameplay context: 4x fast.

### 5. The frame counter as a clock

*Update, 2026-09-18:* family F5 now covers every row below
that was "no", except the layout flipbook parity (F6). The 358 here are
decompiled lines; at the instruction level there are 133 references, each
classified in `frame_clocks.csv`. The "excluded on purpose" objScroll rows were
excluded on a misreading: its ±1 bump of the counter is in its init, around a
loop that does not read the counter.

All 358 reads, from `clock_reads.csv`:

| encoding | functions | covered | examples |
|---|---|---|---|
| `test [fc], mask` gate | 31 | 24 (`frame_gates.h`) | footstep dust, sparks |
| same, but register form or `(phase + fc) & mask` | 5 | no | `22E320` utbd, `2E2FA0` et08 (x2), `3A3CA0` pl02, `5F6690` et9f |
| `fc * 10 % 360` into sin | 26 | 22 (`frame_phases.h`) | option pulses, enemy marker, `vt*` |
| `fc % (360 / 12) * 12` | 2 | no | **`432B00` pause-menu selection-arrow bob** (6 sub-screens), `1604E0` gallery |
| `fc % 3600`, `fc % 360` (objScroll) | 2 | excluded on purpose | `35CAC0`, `35D5B0` |
| raw phase: `fc*2`, `fc*4`, `(u16)fc`, `(fc & 63) + 20` | 5 | no | `20C220` shader time, `3D4830`/`3D4A40` screen wobble, `2111D0`, `35B840` |
| `fc % N == 0` gate, N = 10, 15, 60, 90 | 7 | no | **`4003D0` loading dots**, `3B18D0`/`3C3C70`/`3C43C0` pl00 (N=15), `5EB440` em89, `4CD7A0` |
| `fc >> 2 & 3` cycle | 2 | no | `1CD620`, `1CDC90` |
| `(fc - t0) < 480 / mode` | 2 | no | `437130`, `4376C0` -- port-compensated to 60 only |
| `fc - t0` elapsed | 1 | no | `437120`, loading-screen fade |
| parity with mode | 1 | no | `1B2A50` layout flipbook |
| "already ran this frame" snapshots | 25 | not a clock | leave alone |

### 6. Port compensation that is only right up to 60 fps

Beyond the `{sqrt k, k}` pool (`table[mode-1]`, 159 reads in 69 functions,
`mode_constants.h`) and `n * (mode == 1 ? 2 : 1)` (`mode_multipliers.h`):

| RVA | what | encoding |
|---|---|---|
| 3FB410 | `cCockCtrlWnd` pulse | `phase = wrap(phase + mode * k)` |
| 407C60 | `cCockTimer` pulse | same |
| 407B00 | `cCockTimer` count | `t -= mode` |
| 400A50 | loading-screen fade length | `((mode != 2) + 1) * 10` ticks |
| 437130, 4376C0 | an elapsed window | `(fc - t0) < 480 / mode` |
| 1B2A50 (+1B5380) | layout flipbook | parity gate, phase seeded from `fc & 1` |
| 13F410, 1843A0 | held-direction repeat | reload 4, `t -= mode`: 10/s at 30, 12/s at 60, 24/s at 120 |
| 187DC0 | `ControllerManager::Update(0, mode)` | mode passed in |
| 1C1660, 1C6110 | `cMcAction` | `x % mode` |
| 4763F0 | an integrator | `(float)mode * v * 0.5 ...` |
| 4B63B0 (`flower_tick`) | **total play time** `[B205C8]+0x7C` | `+= mode` per tick. Its one reader, `/60`, is the end-of-game Total Results screen (`668845` in the decompile, beside that screen's cherry-tree tests); it counts double at 120. Corrected 2026-09-23: this is not the battle results' time |
| 1825A0 | `this+0x260 = mode + x` | |

At 30 and 60 fps these are as the port intended; at 120 each runs twice as
fast as it does at 60. (The repeat timer is the exception to "exact at 60":
its reload of 4 gives 10/s at 30 but 12/s at 60, because `4 / 2` rounds.)

*Update, 2026-09-24:* family F6 now covers this table, from a classification of all 244
references to the byte (`mode_reads.csv`). Corrections to the rows above:
`4763F0` is the event camera's path player (its playhead; the time-lapses
lerp on it); `1825A0` is `cPad`'s held time; `187DC0`'s mode argument is read
by no input device; `400A50` and the `480 / mode` windows were already right
through F5's U; the repeat timer (`13F410`, `1843A0`) now runs at the stock
context's rate, 10/s in play and 12/s in the 60 Hz menus. Not in the table
and also covered: the memory card's `n / mode` waits (`1C0160`, `1C10F0`,
`1C6110`, `1C7FE0`) and the options sliders (`153F30`, `154160`). The coin's
speed ramp (`1A3CA0`) was never 2x: its 0.5 is one of `mode_constants.h`'s
selects.


What was reported, traced to code
---------------------------------

### "Now Loading" at 4x

`cCockLoading` (vtable 6AFF88; update slot 3 `400370`, draw slot 4 `400A50`):

* `400370`: `phase(+0x6C) = wrap(phase + 0.3)` every tick; the draw scales the
  sign by `1 + 0.1 * sin(phase)` -- a 0.70 s pulse at 30, 0.17 s at 120;
* `4003D0`: `dots(+0x70)` advances when `frameCounter % 10 == 0` and wraps
  after 8; the draw (`400F50`) shows that many icons at x = 50 + 50i -- one
  new dot every 1/3 s at 30, every 1/12 s at 120. The same `% 10` window also
  times the button-press minigame (`fc % 10` in {0,1,8,9});
* `400A50`: a fade over `((mode != 2) + 1) * 10` ticks of `frameCounter -
  [B31984]` -- port-compensated for 60 only.

All three are 4x at 120; none is covered.

*Update, 2026-09-18:* the dots' read and the fade's are retargeted by F5
(`frame_clocks.h`); the sign's step is in `phase_steps.h` (its wrap-step rule).
The patch now watches the live instance, through slot 3 of vtable 6AFF88, and
the overlay prints the dot interval and the sign period against stock while a
loading screen is up. The first in-game run of F5 showed why that watch was
needed: the counters ran correctly (hook calls per second = ticks per second),
but the screen still looked 4x, and the sign's pulse, which F5 cannot touch,
was the most visible thing on it.

### Menu changes at 4x

*Update, 2026-09-23:* M2's first family (`menu_transitions.h`) covers
the scene transition, the pause menu's opening drop and the HUD fade below,
plus the pause menu's page-icon pulse. The pause menu's close slide turns out
to be one tick long (it starts at p = 0 and ends at p > -512). Its visible
close is `414026`'s 10-tick interpolation (F1). List scrolling, the cursor
repeat and the layout flipbooks remain.

The transitions the eye sees when entering, leaving and switching menus:

* **scene transition model** (`4396F0` on B4DF40, started by `439D60`,
  reversed by `439E90`; about 130 call sites use it -- area exits, events,
  the memory card, the options controller around every page change): a model
  slides in `x += -4.25` per tick until x <= 25, glides with `v *= 0.936` for
  28 ticks while its animation rate (`+0xF54`) is driven off the velocity, then
  fades `alpha -= 0.056` per tick while another field steps `+= 14` to 64. The
  options controller holds the mode at 2 through these phases, so this is
  stock-30 and **4x** today -- the best match for "menu changes run at 4x", and
  very likely what area changes look like too;
* **held-direction cursor repeat** (`1843A0`, and `13F410` for the navigation
  controller): the repeat timer reloads with 4 and counts down by `mode` per
  tick, so it fires every 3 ticks at 30 fps (10/s), every 5 at 60 (12/s) and
  every 5 at 120 (**24/s**) -- scrolling through a menu by holding a direction
  is about 2.4x stock speed;
* **pause menu opening** (`415B30`): a bounce, `v(+0x90) += 6`, `p(+0x8C) += 2v`,
  restitution -0.43, settles when |v| < 3 and only then switches to mode 1:
  stock-30, 4x, and its settle test is a per-tick threshold, so the shape
  changes as well as the speed;
* **pause menu closing** (`414080`, `413F70`): slide-out `p -= v` to -512,
  a 10-tick interpolation on `+0xA4` (`t/9`), a 15-tick countdown on `+0xA6`;
* **list scrolling** (`cSSScroll`, `4111D0`/`4113A0`): rows move
  `spacing / N` per tick for N+1 ticks, N = `[main+7A90B0]` = 3 (a .data
  constant) -- inside the menu, so stock-60 and 2x;
* **selection arrow** (`432B00`, six sub-screens): `sin(fc % 30 * 12 deg)` --
  stock-60, 2x;
* layout flipbooks in every menu: 2x (parity gate above);
* HUD fade (`3F6660`): 4x.

### Torches, the portal, "everything else" in the world at 4x

No single object was identified by name -- that needs the game running to see
which class is placed at the start. What the code establishes:

* any fire, spark, glow or scrolling-texture **effect** is an `esp` instance and
  runs on the uncovered engine above: flipbook frames, lifetimes, velocities,
  spin, pulsing and texture scroll all per tick;
* object-owned surface animation goes through **material state**: `et08` is
  the clearest flame (six scrolling fire/smoke layers plus a periodic spark
  spawn), and 112 other functions animate materials the same way;
* a **portal**-like swirl is most likely an `esp20` model-texture effect, a
  material scroller like `et08`, or the frame-counter shader constant
  (`20C220`) -- all three uncovered.

### Villagers, their emotion bubbles, the sky's wind

*2026-09-23*:

* the villagers' body animation is right (`4B9C80` on the retargeted 0.5);
  what ran fast is layered on it: the swinging bones (`1BA350`, `1BAA20`:
  sleeves, hair, sashes; about 100 callers, mostly `hm*`), the talk head-bob
  (`3043C0`) and the mood-particle spawner (`30EB40`, effect set 100). All
  three are now in `world_anims.h`;
* the bubbles' spawn rate is fixed there, and the particles' own motion is
  the effect engine's shared step, also in `world_anims.h` since the same
  day, as are most per-class steps;
* the sky's scrolling layers are `objScroll` models, scrolled per tick by
  `35D5B0` (placement bytes `+0x14/+0x15` x 0.001 a tick): in `world_anims.h`;
* walking villagers turn through `20E210` (turn toward a point, 439 calls
  across villagers, animals and enemies) or `20E290` (toward an angle, 15):
  heading `+0xB4` moves by at most a limit a tick. The limit is scaled inside
  the two functions, after `tools/survey_turn_limits.py` showed every caller
  passes it in stock units. The waypoint follower (`3049D0`) also raises its
  limit with the ticks a villager has been stuck (`+0x1272`), now counted on
  stock ticks.

### "Everything else so far"

Counts by subsystem, from `summary.md`:

| subsystem | candidate sites | covered today |
|---|---|---|
| objects (em, an, ut, wp, pl, et, hm, ...) | 6 525 | 1 143 |
| unattributed engine code | 3 182 | 179 |
| UI classes and menu managers | 514 | 18 |
| model material state | 473 | 137 |
| effect engine | 134 | 1 |
| layout player | 31 | lengths covered, flipbook not |
| linked middleware (CRI, CRT) | 1 626 | -- not game time |

By object family: enemies 1 586, animals 1 382, `ut` objects 927, weapons 695,
player 691, `et` 313, humans 244.

A candidate is not yet a bug. The census cannot tell a timer counted every tick
from a state index advanced once per transition, or an init-time offset from a
per-tick one -- the UI review below found roughly a third of UI candidates to
be state indices, cursor moves or one-shot layout offsets.


UI, class by class (read by hand)
---------------------------------

Stock context in brackets: [30] gameplay/mode 2, [60] menu interior/mode 1.

| class / owner | RVA | what animates | step |
|---|---|---|---|
| cCockLoading [30] | 4003BC, 40059A, 400A50 | sign pulse, progress dots, fade | above |
| cCockBase [30] | 3F66A2/3F66BD | HUD element fade in/out | +-1 to `+0x58` |
| HUD manager (B1C7C0) [30] | 3F3B0D | `+0x340` countdown | -1 |
| cCockCtrlWnd [30] | 3FB4AE | pulse | `+= mode * k` (60-only) |
| cCockTimer [30] | 407BB2, 407D66 | countdown, pulse | `-= mode`, `+= mode * k` |
| cCockMoney [30] | 402BE4..402CBD | roll-up `x += 1 + (target - x)/30`; shake `+0x70, +0x74 *= -1` (sign flip every tick); pulse `wrap(+0x7C + 0.8)` | per tick |
| cCockCombo [30] | 3FAB26..3FAB45 | `+0x74 += 1.0`, `+0x78 *= 0.2`, countdown `+0x71` | per tick |
| cCockStamp [30] | 406D0E, 406D2D | countdown `+0x7C`, `+0x6C *= 0.7` | per tick |
| cCockInkGauge [30] | 3FE356, 3FE52A, 3FE9BC..3FEA90, 3FEC77 | countdowns, colour cycling in steps of 15, counter | per tick |
| cCockLifeGauge [30] | 3FF7C7, 3FF869, 3FF960, 3FFC39 | flash/shake counters | +1/+2/-1 |
| cCockCompas [30] | 3FAE87..3FAEE3 | 4-channel colour cycling by +-15 | per tick |
| cCockGameOver [30] | 3FCE4E..3FD282 | countdowns, four float slides | per tick |
| cCockBattleResult [30] | 3F77ED..3F9E5E | timers `+0x194`, `+0x198` (seeded 30), roll-up; many state indices | per tick |
| cCockEmLifeGauge [30] | 3FC00F, 3FC06B | countdowns (`3FC12F`/`3FC14C` move an element by +-60, per-tick status unverified) | per tick |
| cCockStomachGauge, cCockSgStmcGauge [30] | 407188, 405EF8 | `+0x68, +0x6C += 0.5` | per tick |
| cCockMap [30] | 401ACB, 401E69, 401E8C | pulse `+0xA8 += 0.3`; map-screen fields `+= 0.1`, `+= 0.15` | per tick |
| cCockEventEdge, cCockMapTitle, cCockRemain, cCockFudeWnd [30] | 3FC45B.., 4022BA, 40524C, 3FCACB | fade/slide counters | +-1, -2 |
| scene transition model (B4DF40) [30] | 4397F4..439B5A | slide, glide, fade, scale | above |
| pause menu (B1EBA0) [30 open / 60 inside] | 415BB3, 414026, 4140F4, 414138 | drop-bounce, close slide, countdown | above |
| cSSScroll [60] | 411299, 411465, 411D92, 411E55 | list scroll | spacing / 3 |
| cSubScr* (6) [60] via 432B00 | -- | selection arrow bob | fc-derived |
| cSubScrFude [60] | 4234DA, 42355A | slide `+0xFC -+= 8.5` with countdown `+0x100` | per tick |
| cSubScrMap [60] | 42EEEF, 42EF13 | pulses | `+= 0.05`, `+= 0.075` |
| cSubScrItem [60] | 40DCCB, 40E07E.. | `+= 10` slides, colour steps of 16 (`40D98D`/`40D9D8` scale an alpha by n/128, per-tick status unverified) | per tick |
| cSubScrStatus [60] | 4331E4..4354F6 | count-ups of stats toward targets | per tick |
| cSubScrFilesEnemy/Info* [60] | 41BBC4.., 41C2FF.., 41E1F2, 41F62B | slides, 20-tick blinks, countdowns | per tick |
| cMcAction [60] | 1C5032, 1C5068, 1C595A | fade `+0.1`, phase `+0.628` to 4 pi, decay `*0.95` | per tick |
| cMcLoad/cMcSave [60] | 1BE95F..1BEB30 | slide +-1 to +-100, frame counters | per tick |
| cOptionCalibration [60] | 14635C..146E63, 147776 | timeouts 300/180/30/16 ticks, pulse `+5 deg` | per tick |
| cOptionControllerSelect/Pairing [60] | 147D17, 149941 | timeouts 480 and 1200 ticks | per tick |
| cOptionControllerSettingPC [60] | 153F8B..1542CF | hold-to-accelerate value change | per tick while held |
| other cOption* | 1487ED, 14C45D, 14C679 | countdowns | -1 |

Not timers (excluded after reading): the `+0x54`, `+0x88`, `+0x8C`, `+0x9C`
cursor moves in the option screens (input-driven), every `+0x50..+0x53`,
`+0x61/+0x62`, `+0x99/+0x9A` increment that is followed by resetting a timer
(state indices), and the `+= 11` / `+= 64` / `+= 160` layout offsets applied
once at init (`146F40`, `14B970`, `400710`, `400980`, `1C7150`).


How these could be fixed (not implemented)
------------------------------------------

The staged plan -- infrastructure, classification, families, roll-out
order and verification -- in short, in order of leverage:

1. **Shadow mode byte** (prerequisite for UI): retarget the 21 mode writers and
   4 save sites at a private byte, keep main+B6AC45 pinned. Every UI fix can then
   pick 2x or 4x from the stock context, and `frame_phases.h` can stop
   over-correcting the option screens.
2. **Effect engine**: convert the ~20 shared sites (integer counters by skipping
   ticks, as `action_timers.h` does; `pos += vel*ts`; `vel *= k^ts`;
   `rate *= decay^ts`; spin, wobble and turbulence steps `*ts`) and the per-type
   overrides. One engine, every effect. The emitter's native 0.25 slow-motion
   factor composes by multiplication.
3. **Material state**: the 473 sites are ordinary float steps and wraps; the
   `phase_steps.h` machinery (retarget the literal at a scaled private copy)
   covers most of the literal ones. The data-driven rates (`et08`'s table,
   `esp20`'s `+0x2D0`) need the step scaled where it is added.
4. **Frame-counter families**: widen the modulo gates (`% 10` -> `% 40` at 120
   for stock-30 contexts), give the offset mask gates the same treatment as
   `frame_gates.h`, and point the raw-phase and `% 30` reads at the scaled
   counter `frame_phases.h` already maintains.
5. **Mode-as-quantity sites** (list above): replace `mode` with a patch-held
   value, as `mode_multipliers.h` already does for its seven.
6. **Decimation** as an alternative for whole UI objects (run an update only on
   stock ticks, keep drawing every tick): exact stock behaviour by construction,
   but a UI update skipped on the tick a button edge arrives loses the press,
   and an effect updated at 30 Hz lags anything it is attached to that moves at
   120. Both would need handling first.

A measurement plan once the game can be run: the loading screen (sign period,
dot interval), a pause-menu open/close, and a `Passthrough=1` log line with an
options page open (stock ticks/s there). The harness hook point (`3AF020`) is
per tick and could timestamp any of these fields directly.


Open questions
--------------

* The stock tick rate in menus (above) -- inferred, not measured.
* Which classes are the torches and the portal in the first area. Candidates
  are named above; a runtime class dump of the area settles it.
* `main+3ED1C0` does not decompile ("flow exceeded maximum allowable
  instructions"); it is called by ~35 object routines and is not in the census.
* `unattributed` (3 182 sites) is engine code reached only through pointers the
  static call graph cannot follow (task handlers, member-function pointers).
  It includes the camera and much of the kernel; `root` and `owners` in
  `sites.csv` are empty for these.
* Which of the ~130 scene-transition callers run in a stock-60 context (a
  transition started from inside a mode-1 screen would be 2x, not 4x).


Reproducing
-----------

    .venv/Scripts/python tools/ghidra_export.py          # only if the binary changed
    .venv/Scripts/python tools/pcode_census.py           # ~8 min -> ~\tools\pcode_census.jsonl
    .venv/Scripts/python tools/animation_inventory.py    # seconds -> docs/animation/*
    .venv/Scripts/python tools/ghidra_lines.py --out f.c 400370,1928F0

Set JAVA_HOME to the Temurin 21 JDK first. The census walks through phi nodes:
the first version stopped at them and missed every conditionally-stepped timer,
including the one effect site already covered (`195198`). `sites.csv` columns:
`site` (store RVA), `load`, `function`, `subsystem`, `owners` (RTTI classes),
`vtable` (slots it occupies), `root` (dispatcher entry), `shape`, `size`,
`field`, `step` (resolved constants), `clocks` (engine clocks read in the value),
`covered_by` (existing table), `expr` (p-code expression, constants resolved).
