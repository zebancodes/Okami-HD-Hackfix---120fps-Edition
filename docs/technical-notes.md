Okami HD High-FPS Patch: technical notes
========================================

The long-form record of the patch, bug by bug, with the measurements behind
each fix. The project's introduction is the [README](../README.md); the
animation work's census and reading records are in [animation/](animation/).

Unlocks the Steam PC release of Okami HD (大神絶景版) from its 30 fps
presentation lock, with an in-game hotkey to switch between stock 30 fps
and the engine's 60 fps configuration. Built and tested against build
6990973 (buildid from `appmanifest_587620.acf`, latest as of 2026-09).

**Status (2026-09): movement and jumping run at real time in 60 fps mode.**
The engine ticks at a rock-solid 60 Hz with its own 60 fps configuration, and
the patch fixes the movement code the port left in 30 fps units, so Amaterasu
covers the same ground per second in both modes and her animation matches.
The jump and wall jump reach their proper height too, which removes the
long-standing reason to drop to 30 fps to scale a wall - that turned out to be
three frame-rate bugs in one action, not the unauthored data the original
investigation suspected. This was verified by
measurement, not by feel: see "Movement at 60 fps" and "Jump height at
60 fps" below.

Beyond movement, the patch also corrects the engine's *durations*. The port
compensates per-tick physics by the time scale and doubles input windows for
60 fps, but it leaves almost every object state duration alone, so action
timers, effect spawn rates, lifetimes, fade meters, damping factors and the
interface's own oscillators all ran at double speed. 1435 sites are converted
in seven families; see "Durations at 60 fps" below.

Features
--------

- 60 fps by default: the frame pipeline runs at an evenly paced 60 Hz with
  the engine's own 60 fps configuration (fps=60, timeScale=0.5). **F9**
  cycles 30 / 60 / 120 fps instantly, in-game, without restarting, and the
  last choice is kept for the next start.
- Real-time movement at 60 fps: the jog, run and dash speeds and their
  animation rates are corrected to their 30 fps values (**F8** A/Bs the fix).
- Full-height jumps at 60 fps, including the wall jump, which the port left
  at a quarter of its proper height (**F7** A/Bs the fix).
- Real-time durations at 60 fps: action and recovery windows, effect spawn
  rates, lifetimes, fades, scrolls, damping and the interface's own pulse all
  last as long as they do at 30 fps -- 1435 sites in seven families
  (**F6** and **F5** A/B the two halves of this).
- Everything the patch resolves and verifies is logged to
  `okami_hackfix.log`, and an optional on-screen overlay shows the mode, the
  movement fix state and live walking speed.
- Runtime-only patch: nothing on disk is modified, Steam validation is
  unaffected, uninstall = delete the two files.
- Self-verifying: every engine symbol is resolved by export name and every
  code site is checked before it is written. On an unknown game build the
  patch logs the mismatch and leaves the game completely stock instead of
  corrupting it.
- Configurable through an optional `okami_hackfix.ini` (start rate, hotkey,
  focus requirement, beep, present sync interval, draw distance, chaining to
  another `dinput8` proxy); the development-era `okami.ini` is still read
  when it is the only one, with the development features on.
- Experimental UI integer-clock prototype: `FixIntegerSkips=1` enables the
  audited sites in [integer_skips.csv](animation/integer_skips.csv), with
  **F4** for independent A/B comparison (`IntegerToggleKey`). Off by default.
  Counters keep whole stock steps: 30 Hz in gameplay and 60 Hz in stock menus,
  at either a 60 or 120 fps target. Offline verified; in-game validation is
  still pending. F9 stock mode and F4 mute execute the original instructions.
- Coexists with ReShade (and its add-ons such as RenoDX or ReLimiter), the
  Steam overlay and NVIDIA's driver present layer (`NvPresent64.dll`).

The integer prototype is generated with
`.venv/Scripts/python tools/gen_integer_skips.py` and checked with
`.venv/Scripts/python tools/verify_integer_skips.py` after building the DLL.
The generator uses the installed `main.dll` and the recorded classification;
it records a reason for every refused UI integer candidate. The verifier
maps the game DLL without running it, checks the actual installed bytes,
emulates stock and skipped ticks, and tests mode changes and failed installs.

What 60 fps mode actually does
------------------------------

The M2 port wrapper (`main.dll` + `flower_kernel.dll`) has a genuine 60 fps
configuration: `flower_tick` writes `fps=60, timeScale=0.5` when its mode
byte is 1, `timeScale` is consumed at ~140 code sites, a 60 fps flag is used
as a shift at ~320 sites to double frame-count durations, and the input
key-repeat timers decay by `mode` per tick. The stock game uses this
configuration itself for a few seconds during the title sequence, ticking
at 60 Hz there.

What the port did **not** do is convert every per-tick quantity. Speeds and
timers are stored per tick, so anything the port missed covers twice the
ground, or counts down twice as fast, per second at 60 fps. The compensation
it did apply is easy to spot in the disassembly: the 60 fps flag used as a
shift (`shl reg, cl`) to double a duration, or a constant multiplied by
`timeScale` before use. Whole subsystems have none of it: the HUD classes
(`cCock*`), the sub-screens (`cSubScr*`) and the effect system (`esp*`)
contain no such site at all, while the player and character code is full of
them.

Movement at 60 fps
------------------

Amaterasu's speed lives at `pl00+0xE48` in units per tick. The port scaled
the top dash stage by `timeScale` (at main+0x3B3826) but left the jog and
run states in 30 fps units, which is why the flower dash felt *slower* than
a plain run: it was the only stage that was correct.

Measured with the patch's 10 Hz player probe (`SpeedLog=1`), units per
second on flat ground:

| Stage | 30 fps (stock) | 60 fps before | 60 fps with the fix |
|-------|----------------|---------------|---------------------|
| jog   | 123 | 232 | 126 |
| run   | 158 | 324 | 162 |
| dash (flowers) | 206 | 207 | 207 |

The fix mirrors what the port already does for the dash:

- **Run.** The target speed is the raw 5.4 (or 2.7) constant. A detour at
  main+0x3B351C multiplies that target by the engine's `timeScale` just
  before it is used. The same constant in `xmm6` is left alone because it is
  also the divisor for the animation rate, which stays in per-tick units.
- **Jog.** Its parameters are a private block in `.data`, and the speed there
  is an equilibrium between a per-tick acceleration and two damping terms,
  so the target alone is not enough. For `dv/dtick` at 60 fps to be half of
  30 fps with `v` halved, the acceleration must be halved and the quadratic
  damping coefficient doubled. The patch scales the target (4.2 -> 2.1), the
  dash-charge threshold (2.7 -> 1.35), the accelerations (0.2 -> 0.1,
  0.4 -> 0.2), the damping coefficient (0.01 -> 0.02) and the charge frame
  count (200 -> 400) while 60 fps mode is on, and restores them on the way
  back. The game reloads that block on some transitions, so the patch keeps
  the values applied rather than writing them once.
- **Animation.** The playback rate is `speed / k` with a floor, so halving
  the speed also halved the leg cycle. Three detours (jog, run, dash) scale
  the numerator back up, which puts the rate at its 30 fps value: measured
  1.08 / 1.00 / 1.28 at 60 fps against 1.06 / 0.99 / 1.27 at 30 fps.

`FixRunSpeed` and `FixAnimRate` control these, and **F8** switches them off
and on in-game for comparison. They are independent of the experimental
`Fixes` toggle on F10 so they cannot be disabled by accident.

Jump height at 60 fps
---------------------

At 60 fps the jump reached a fraction of its proper height, and the wall jump
barely left the wall at all. It is three separate frame-rate mistakes in the
same action, and all three had to be fixed before the heights matched.

Vertical motion itself is one of the places the port got the hard part right.
The player's update integrates it in real time:

```
pl00+0xE54   -= timeScale * 0.7        gravity    (main+3AB636)
transform.y  += timeScale * pl00+0xE54  position  (main+3AB66B)
```

Both the velocity and the acceleration carry the time scale, which makes that
an ordinary Euler step with `dt = timeScale`. A jump then reaches the same
height at either frame rate - provided nothing else in the action is counted
in raw ticks. Three things were.

### 1. The launch velocity was scaled twice

The jump state (`E35 = 03`, handler main+0x3B3FF0) seeds its launch
accumulator with

```
pl00+0xE14 = timeScale * 5.0         main+3B4447
```

That is the right conversion for the horizontal speed field `+0xE48`, which
really is a per-tick displacement, and the wrong one for a velocity the
integrator is about to scale a second time. Apex height goes as the square of
the launch velocity, so halving it left a quarter of the height. A detour
multiplies that store by `1/timeScale`, undoing the one multiply that should
not be there.

### 2. The charge window was counted in ticks

Holding the button grows the same accumulator by `timeScale * 0.9 * modifier`
per tick (main+0x3B4614) for as long as the wind-up timer `pl00+0xE3C` runs.
The increment is a correct per-tick quantity; the window is not, because it is
seeded with a hard-coded 5 (`mov r9d, 5`, main+0x3B4407). Five ticks is 167 ms
at 30 fps but only 83 ms at 60, so a jump accumulated half the charge. Doubling
that window restored the peak accumulator to the 30 fps value of 8.60 exactly.

### 3. The float was counted in ticks

This one is most of the height. While the button is held and `pl00+0xE3C` is
still running, the handler adds `timeScale * 0.5` back to the velocity every
tick (main+0x3B4B4F), cancelling most of the 0.7 gravity. That is the jump's
float, and its window is a *second* hard-coded 5 seeded just after the launch
(`mov r9d, 5`, main+0x3B480D). The climb trace shows it plainly - the velocity
falls by 0.20 per tick while the float lasts and by 0.70 after it:

```
30 fps  per-tick drop:  0.20 0.20 0.20 0.20 0.70 0.70 0.70 ...   4 float ticks
60 fps  per-tick drop:  0.10 x8                0.35 0.35 ...     8 float ticks
```

Both windows are the action timer `pl00+0xE3C`, and **neither is patched here
any more**. Doubling the two seeds by hand worked but needed different
arithmetic for each -- the charge tests the timer before decrementing so it
wants `2*N`, the float decrements first so it wants `2*(N-1)+1`, and using
`2*N` for the float gave a ninth lift tick and overshot the 30 fps height by
about 9%. Both were instances of a fault the whole character state machine has,
so they are now covered by the general action timer fix, which has no such
asymmetry because it slows the countdown instead of enlarging the seed. See
"Durations at 60 fps".

### Result

Measured with the patch's jump probe, matched by the peak launch accumulator
(units of height, launch velocity in units per tick):

| | accumulator | launch | rise | climb |
|---|---|---|---|---|
| 30 fps | 8.60 | 8.40 | 69.1 | 508 ms |
| 60 fps before | 8.60 | 4.92 | 17.3 | - |
| 60 fps fixed | 8.60 | 8.50 | 72.6 | 498 ms |

The wall jump is where this was felt, because it *adds* the impulse to the
velocity already present (main+0x3B47C7, when the sub-action byte `+0x1145` is
`0x1E`) rather than replacing it: at a quarter strength, applied part-way
through a fall, it barely lifted her - which is exactly the "plays the
animation, gains no height" behaviour the original investigation recorded and
blamed on an unauthored entry in the encrypted motion data. It is not a data
problem.

`FixJumpHeight` controls all three parts and **F7** switches them off and on
in-game.

**A residual 5%.** The fixed 60 fps jump rises about 5% higher than the 30 fps
one (72.6 against 69.1) from the same launch velocity. That is not a scaling
error left over: it is the integrator's own discretisation. Summing the same
trajectory in 28 half-size steps loses less height to staircase error than
summing it in 14 full ones, and working the sums through by hand predicts
+2.9% of it. The 60 fps arc is the more accurate one; 30 fps is the outlier.
It could be tuned away by shortening the float window by one tick, at the cost
of hard-coding a correction for one launch velocity, so it is left alone.

### The same mistake elsewhere

An absolute vertical velocity assigned as `timeScale * constant` appears at
23 further sites in the player and enemy state handlers - knockback and various
special moves. They are the same bug as part 1, so those actions were launching
short at 60 fps too, and they are now fixed the same way; see "Launch
velocities" under "Durations at 60 fps".

Durations at 60 fps
-------------------

The port compensates for 60 fps in exactly two ways: it multiplies per-tick
quantities by the time scale (137 reads), and it doubles durations by shifting
them with the 60 fps flag (322 reads). Of those 322, **321 feed `cPad::ActSet`**
and the last scales a duration into a pad-effect structure. The input windows
are compensated and **almost no object state duration is**.

The exceptions are worth naming, because they are what makes the rest an
oversight rather than a design. Four times the port works out the right
conversion and applies it in one place only: a per-mode table of damping
factors that stores 0.9274 for 60 fps where 30 fps has 0.86, and 0.9274 is
exactly the square root of 0.86; two effect throttles in `pl01` written as
`frameCounter % (fps / 2)` where thirty-odd siblings use a fixed mask; a
handful of byte timers seeded from the fps byte itself; and that one pad-effect
duration. Everything else that measures time in ticks simply runs at double
speed.

That is a large share of how the game feels: attack and recovery windows,
stagger and invulnerability, effect spawn rates, lifetimes, screen fades, menu
and gauge animation, the interface's own pulse, and every smoothing filter. The
jump was simply the case that happened to be measurable -- its wind-up and
float windows were two instances of a fault the whole engine has.

Seven shapes cover it, 1435 sites in all. Six are found by a tool in `tools/`
that writes a table into `src/`, so they can be regenerated against another
build; the seventh is ten hand-identified sites listed in the patch source.

### Action timers (787 sites, three encodings)

Durations live in five fields of the shared character object -- `+0xE3C`,
`+0xE3E`, `+0xE40`, `+0xE42` and `+0xE76` -- and are always counted a tick at a
time. The compiler emits that count three different ways, and each has to be
searched for separately. When the new value is wanted afterwards it goes
through a register:

```
movzx eax, word ptr [rsi+0xE3C]
test  ax, ax
je    done
dec   ax                          <- 3 bytes
mov   word ptr [rsi+0xE3C], ax    <- 7 bytes
```

When it is not wanted at all, it counts straight against memory, with no load
and no store to recognise:

```
dec   word ptr [rsi+0xE3C]
cmp   word ptr [rsi+0xE3C], 0
jg    still_running
inc   byte ptr [rsi+0xE36]        ... otherwise advance the sub-state
```

And when the handler needs the value from *before* the count, `dec` is no use
-- it would clobber the flags the code is about to branch on and overwrite the
value it still needs -- so the compiler reaches for `lea`:

```
movzx eax, word ptr [rdx+0xE3C]
lea   eax, [rcx - 1]              <- new = old - 1, flags untouched
mov   word ptr [rdx+0xE3C], ax
test  cx, cx                      <- ... and the branch tests the OLD value
jne   still_running
```

That is 259, 422 and 106 sites. The first table alone was less than a third of
them, which is why so much of the game still ran fast after it was patched.
Roughly a seventh of the total count *up* toward a limit rather than down; that
is the same thing and is treated the same way.

Doubling every seed is impractical -- most are registers or come from data --
so the patch skips the count on alternate ticks instead, which makes every one
of these timers last twice as many ticks and so the same real time. Parity
comes from the engine's own tick counter, so the stub needs no per-frame
upkeep, and one mask byte switches all 787 off at once.

It also gets the boundaries right for free. Hand-doubling the jump's two seeds
needed `2*N` for one window and `2*(N-1)+1` for the other, because they test
the timer on opposite sides of the decrement, and getting that wrong was a
visible 9% error in jump height. Skipping the count has no such asymmetry, so
the general fix replaced both hand-tuned patches.

The three encodings need three different things of the skip path, and getting
any of them wrong would be a crash or a stuck state rather than a wrong number:

- **register form** -- patch the decrement rather than the store, so the
  register and the field stay in agreement; 72 of these sites go on to use the
  register. Flags are preserved across the parity test, because the displaced
  store does not touch them.
- **memory form** -- here the count *is* the flag producer: 159 sites are a
  `dec` read directly by `jne`, plus seven `jns` and five `je` (and nothing
  else, checked by walking forward through unconditional jumps rather than
  stopping at them). Restoring the flags the site was entered with would be
  meaningless, but what every one of those consumers wants on a skipped tick is
  the same answer, "not finished yet", so the skip path publishes exactly that
  with `test rsp, rsp` -- ZF=0, SF=0, and the field untouched.
- **lea form** -- neither instruction touches the flags, so preserving them is
  enough; but the `lea` writes a *different* register from the one it reads, at
  all 106 sites, and at a few of them the branch tests that destination rather
  than the load register. Leaving it alone on a skipped tick would compare
  stale contents, so the skip path copies the old value into it with a
  synthesised `mov dst, src`.

A timer sitting at zero therefore survives one more tick and expires on the
next real count, which is precisely the one-tick-later behaviour the fix exists
to produce.

One site is excluded by name. `hm68` steps `+0xE3C` for sixty ticks and then
uses `+0xE3E` to pick the next of its sub-objects out of a pointer array. That
field is a sequence position, not a duration, and slowing it would change which
object is addressed rather than how long anything lasts. The generators find
that case by looking for the field being used as an array index inside the same
function, with function bounds taken from the PE exception table so the test is
exact.

### Effect rate gates (33 sites)

Repeating effects are not timed by a countdown at all. They are gated straight
off the global frame counter:

```
test byte ptr [rip+frameCounter], 7
jne  skip
...                          ; every eighth frame: spawn the dust, the spark
skip:
```

That is how footstep dust, trail sparks, ripples and aura pulses are rated, and
the mask is a tick count like any other, so every one of them appeared twice as
often at 60 fps. Widening the mask is the whole fix, one byte per site: 7
becomes 15 at 60 fps and 31 at 120. Every site taken is the memory form, whose
only effect is on the flags the `jne` reads, and every one is a `jne` -- a
plain guard, never an if/else pair that would change meaning when the period
changes. Four further sites load the counter into a register and go on to use
it for something else; those are left alone.

### Interface oscillators (22 sites)

The other way the frame counter is read is as an angle:

```
mov  eax, dword ptr [rip+frameCounter]
lea  ecx, [rax + rax*4]
add  ecx, ecx                       ; ecx = frame * 10
...                                 ; ecx % 360
cvtsi2ss xmm0, rax
call sin
```

Ten degrees a frame is a 36-frame cycle: 1.2 s at 30 fps, 0.6 s at 60. This is
most of what was left of "the interface still looks hurried" -- the option
screens, the save screen, the treasure and vital pickups and the enemy marker
all wobbled at double speed.

Widening a mask does not work here, because the value is used rather than
tested, so these reads are retargeted at a private copy of the counter that the
patch keeps at `frameCounter >> shift`. It is *derived* rather than
accumulated, so it is right whenever it is written and cannot drift. Nothing
else that reads the counter is affected: not the rate gates above, not the
`frame % (fps / 2)` throttles, and not the "have I already run this frame"
comparisons, which must keep seeing the real value.

`objScroll` is deliberately excluded. It bumps the counter by one around a
nested update so that its second scroll layer runs a frame out of phase with
the first, and a counter sampled once per frame cannot reproduce that -- both
layers would come out identical, which would look worse than the speed does.

### Doubly-compensated input windows (10 sites)

The port's usual way of writing a frame-rate-independent input window is a raw
constant shifted by the 60 fps flag. Ten sites in the player code build the
same window arithmetically instead, and then shift it as well:

```
movzx ecx, byte ptr [fps]    ; 30 or 60
mov   eax, 0x88888889
mul   ecx
mov   ecx, dword ptr [shift]
shr   edx, 4                 ; edx = fps / 30
lea   ebx, [rdx + rdx*2]     ; ebx = 3 * (fps / 30)   <- already scaled
shl   ebx, cl                ;                        <- scaled again
```

Three ticks at 30 fps become twelve at 60, which is twice the real time, and
would be forty-eight at 120. The `fps / 30` term is the correct conversion on
its own, so the fix is to drop the shift: two bytes per site, `shl ebx, cl`
becomes a `nop`.

### Float phase steps (366 instructions)

The float equivalent: a field stepped by a literal every tick, then checked
against a limit.

```
movss  xmm0, dword ptr [rbx+0x19C]
subss  xmm0, dword ptr [rip+...]      ; = 1.0
movss  dword ptr [rbx+0x19C], xmm0
comiss xmm3, xmm0                     ; espEmitter lifetime, ticking out
```

698 sites step a field by a literal and two of them consult the time scale.
Here the step is *halved* rather than skipped, so the motion stays smooth: 60
half-size steps a second instead of 30 full ones.

Not every such site is per-tick -- a one-off nudge in an event handler looks
identical in isolation -- and the limit check is what separates them. The split
is clean: clamped sites step by 0.05, 0.1, 0.02 and 0.01, unclamped ones by 10,
20, 40, 64 and 100. Only the clamped sites with a step of at most 1.0 are taken.

A phase kept inside +-pi goes through the engine's angle wrap (`13F2E0`) before
it is stored, so it has a call where the others have a compare. The same shape
also turns an object round by pi once, so the shape alone is not enough: a wrap
step is taken only where the tracer session saw the store change its field on
every execution in a stock 30 Hz context (`docs/animation/classification.csv`).
One site qualifies so far, the "Now Loading" sign's pulse (`4003AF`, +0.3 a
tick). Five more of the shape are listed by the tool and left alone.

**The step follows the stock context, not the time scale alone.** The stock
game does not always tick at 30: in its mode-1 contexts (the options pages, the
memory-card screens, the pause menu's interior, the title) it ticks at 60, so a
per-tick step there runs 60 times a second in the stock game too. Scaled by the
time scale alone, those sites ran at half their stock speed at both 60 and 120
fps. The tracer session saw four of them there: the save screen's wave
(`1C5059`), the pause menu's `42EEDC` and `42EF08`, and the scene transition's
`439B48` (in both contexts). So in a stock 60 Hz context a tick is worth twice
the time scale: the step is halved at 120 fps and left as shipped at 60. The
context is the shadow mode byte, read by the per-tick hook on `flower_tick`'s
counter increment, which rewrites the private copies on the very tick the
context changes (the watcher does it instead if that hook is not installed). The
decay factors below follow the same rule. `tools/verify_const_pools.py` runs the
real install on a mapped main.dll, checks every copy on every tick through
every change of fps, context and A/B key, and emulates all 561 instructions:
N patched ticks against one stock tick.

### Decay factors (195 instructions)

Smoothing is a per-tick multiply, and applied twice as often it decays twice as
fast, so velocities bleed off early and camera smoothing snaps. The correct
conversion is not `k/2` but

```
k' = k ** timeScale
```

which is exactly what the engine's own per-mode table at main+0x7A81B8 does: it
holds 0.86 for 30 fps and 0.9274 for 60, and 0.9274 is the square root of 0.86.
That table is one of the three places the port got a duration right; it built
it for one pair of constants and left every other decay alone. Only factors in
[0.8, 1) are taken -- a multiply that close to 1 is
pointless unless it repeats, which makes it a safe signature, while 0.5 and 0.2
are usually a one-shot "halve it on impact".

### Launch velocities (23 sites)

The jump bug at every other site that has it: an absolute vertical velocity
assigned as `timeScale * constant`, which the integrator then scales a second
time. Knockbacks, pounces and special-move launches all reached a quarter of
their height. The gravity steps look similar (`v = v - timeScale * 0.7`) but
read the field first, and the generator excludes them on exactly that basis --
getting that wrong would have broken gravity everywhere.

### The mode byte (60 float sites + 6 integer sites)

This family only matters at 120 fps, and it is the reason 120 fps was not
merely fast but wrong.

The engine does not always ask the time scale what frame rate it is running at.
Very often it tests the **mode byte** at `main+0xB6AC45`, which is `2` for the
30 fps configuration and `1` for the fast one. The patch's 120 fps mode leaves
that byte at `1`, because `1` is what selects the fast configuration at all --
so every site that reads the mode byte and picks a hard-coded 60 fps constant
keeps handing out the 60 fps value at 120 fps.

**The float half.** The port ships a pre-computed damping pool at
`main+0x7A8150`: pairs of `{k**0.5, k}` for k = 0.99, 0.98 ... 0.05 and the
matching growth factors up to 1.9, each read as `pair[mode - 1]`. It is the same
square root this patch derives for its own decay factors -- the engine did it
for itself, for every constant it uses, and then only for two frame rates. Of
the 60 pairs, 20 are actually reached; all 20 are genuinely `{sqrt(k), k}`, and
no instruction anywhere reads one of the rewritten slots as a plain scalar, so
rewriting them has no collateral effect. Six further sites select a hard-coded
`0.5` against `1.0` off the same byte -- the per-tick time step, including the
motion advance in `sub_4B9C80`, which is why Amaterasu covered ground twice as
fast as her legs moved. That `0.5` is shared `.rdata` that hundreds of unrelated
instructions read, so those six are retargeted at a private copy rather than the
constant being rewritten.

Both are corrected with the exponent the engine's own table implies,
`k ** timeScale`, which reproduces the shipped value exactly at 60 fps.

**The integer half**, which a float scan can never find, because the per-mode
table is the instruction itself:

```
    cmp   byte ptr [B6AC45], 1
    ...
    jne   skip
    add   eax, eax          <- the entire table, as one instruction
  skip:
    ret
```

and, branchless,

```
    cmp   byte ptr [B6AC45], 1
    sete  al
    inc   eax               <- eax = 1 or 2
    imul  eax, <n>
```

Both are `n * (mode == 1 ? 2 : 1)`, and at all seven sites `n` is a duration in
ticks: the four track-length getters of the 2D layout player that animates every
HUD and menu element (colour, position, rotation and scale tracks -- earlier
versions of this README called them `esp80` keyframes, but every caller is in
the layout player at main+1B2530..1B6A40), the compare that finds the current
keyframe, the span a keyframe interpolates over, and the length of a motion
blend in the player's own animation handler (`cKamikiFree +0xF50`). At 120 fps each still
doubles where it needs to quadruple, so everything they time runs at exactly
twice the speed it should.

The hard-coded `2` becomes a dword the patch holds at 2 below 120 fps, so the
patched code is bit-for-bit stock at 60 fps, at 30, and whenever the timer A/B
key has the family muted -- which is why these detours are left installed rather
than toggled in and out of the code.

`FixModeConstants` and `FixModeMultipliers`; generated by
`tools/find_mode_constants.py` and `tools/find_mode_multipliers.py`.

### The movement speed target (2 sites)

The run fix scaled the target speed, but the target is a *sum* and only one of
its two terms was ever scaled:

```
run   main+3B34FC   movss xmm1, [pl+0xB0]     <- this term
                    mulss xmm1, 1.3 or 1.1
                    movss xmm0, [pl+0xE48]    <- the run fix detours here,
                    addss xmm1, xmm2             scaling xmm2 (5.4 or 2.7)

dash  main+3B381A   movss xmm1, [pl+0xB0]     <- the same term
                    movss xmm0, [timeScale]   <- the engine scales its own
                    mulss xmm0, 6.9              base, correctly
                    mulss xmm1, 1.3 or 1.1
                    addss xmm1, xmm0
```

`pl+0xB0` is dimensionless -- it holds `1.0`, or `0x3F32B8C2` (0.698 rad, 40
degrees) -- so `[0xB0] * 1.3` is a speed contribution in per-tick units and has
to carry the time scale exactly like the base. Nothing scales it, at either
site, in stock or patched code.

The arithmetic is why this survived so long. With `[0xB0] = 1` the dash target
is `1.3 + timeScale * 6.9`:

| | 30 fps | 60 fps | 120 fps |
|---|---|---|---|
| correct target (per tick) | 8.2 | 4.10 | 2.05 |
| what the game computes | 8.2 | 4.75 | **3.025** |
| overspeed | -- | 16% | **48%** |

and on flat ground `[0xB0]` contributes nothing at all, so the measurements that
established "60 fps movement is correct" were all taken in the one case where
the bug is silent. The 120 fps log measured 3.030 per tick against the 3.025
this predicts.

Both sites are fixed by scaling `xmm1` where it is loaded, before the 1.3/1.1
multiply. The branch that chooses between 1.3 and 1.1 tests the *sign* of
`[0xB0]` and the time scale is positive, so it is unaffected.

`FixSlopeTerm`. Found by reading Ghidra's decompilation of `FUN_1803b2cf0`,
where both targets are two lines of C; in the disassembly they are forty
instructions apart in different branches of a state machine.

### Per-tick speed thresholds in the jump path (4 sites)

`pl00+0xE48` is a displacement *per tick*, so any constant compared against it
is also per tick and stands for a different real speed at every tick rate. All
of the engine's are written for 30 fps, where a full run is about 3.05 per
tick. At 120 fps the same run is 0.76 per tick, and three comparisons in the
jump path fall on the other side of their constant:

```
main+3B4149   if (v < 3.5 && slope < 0) v += slope * 8.0    // clamped at 0
main+3B41E6   if (2.0 <= v) launch = 5.4; else launch = 4.2
main+3B5466   if (v < 3.0) { v += ts*a; v *= k^ts; }
```

The first is an uphill penalty applied once at takeoff. The increment is a
per-tick velocity carrying no time scale, so at 120 fps it is four times too
large -- a slope of `-0.1` takes 0.8 off a speed of 0.76 and the clamp just
below turns that into a dead stop.

The second picks the running jump over the standing one, with its own animation
and its own launch velocity into `pl00+0xE14`. A 30 fps run clears 2.0 and a
120 fps run never does, so above 30 fps the fast variant is unreachable. This
one is visible in any test log with both modes in it, as the `want` figure:

| | 30 fps | 120 fps | ratio |
|---|---|---|---|
| measured `want` | 42.6 | 34.4 | 1.24 |
| 5.4 / 4.2 predicts | | | 1.29 |

The third gates the airborne steering block, and it is what makes a jump keep
its momentum. The block is a leaky integrator whose equilibrium is the
*steering* speed, not the run speed. At 30 fps a run launches above the gate,
the block never runs, and the launch speed survives the whole jump. At 120 fps
a run launches below it, the block runs every tick, and it drags the launch
speed down to the steering speed with a 0.22 s time constant -- so a jump out
of a dash loses most of its speed before the apex.

Each fix scales the constant rather than the field, so the comparison keeps its
exact form. `main+3B41E6` is the exception: its constant is handed to
`FUN_1804ba080` as an animation blend length a few instructions later, so
scaling it there would change the animation too. That site scales the field
into `xmm1` instead, which is dead -- both branches reach a call four
instructions on, and it is volatile across that call.

`FixAirGates`.

### A decay the finder could not see (8 sites)

`tools/find_decay_factors.py` matches the damp that reads its constant inline:

```asm
movss xmm0, [rsi+0xE48]
mulss xmm0, dword ptr [rip+K]      ; <- it sees this
movss [rsi+0xE48], xmm0
```

When a function uses the same constant more than once, the compiler hoists the
load into a callee-saved register and the damp loses its `rip` operand:

```asm
movss xmm6, dword ptr [rip+K]      ; ... hundreds of bytes earlier
mulss xmm0, xmm6                   ; <- identical arithmetic, nothing to match
```

`main+3B55C0` is one of these: `hspeed *= 0.1`, once per tick, in the jump
wind-up. The first harness run at 120 fps caught it exactly:

```
tick   ms       hspeed    state/sub
264    2206.65  1.05917   02/01
265    2214.73  0.10592   03/01   <- x0.100003
266    2223.15  0.01319
267    2231.38  0.00426
271    2264.72  0.00330
272    2273.00  0.00330   03/03   <- y finally leaves 0.500
```

`y` does not move until tick 272, so all of that happens while she is standing
on the ground. She launches with a third of a percent of her run speed. At
30 fps the same line runs a quarter as often, which is the whole difference.

All eight sites damp the one field, `pl00+0xE48`. The factor is a surviving
fraction, so it takes the exponent directly: `k^ts`, and 0.1 becomes 0.562 at
120 fps.

The load is verified and left alone, because it may feed other things. What
gets replaced is the multiply *and the store after it*, by a detour that
multiplies by a private `k^ts` slot. The register is never assumed to survive
the detour -- only to have held `k` at the moment of the multiply.

That last point is what `tools/find_hoisted_decay.py` has to prove, and the
test is local rather than whole-function. A callee-saved register is loaded
with one constant, used, then loaded with another, so asking "is it written
once in this function" rejects every real site -- the first version of the
tool found zero. What actually has to hold is:

* the **nearest preceding** definition of the register is a rodata load of a
  float strictly between 0 and 1, and
* control cannot reach the multiply without passing through that load, which
  is checked as: no branch **from outside** the interval lands inside it.

A branch that both starts and ends inside the interval is harmless, because
the only way to be executing in there at all is to have fallen through the
load. Allowing that took the count from 2 to 8.

`FixHoistDecay`, and `src/hoisted_decay.h` is generated.

### How everything in the game turns (163 call sites)

`main+2DA510` is the angular approach:

```
facing = wrap(facing + k * wrap(wrap(target) - wrap(facing)))
```

with `main+13F2E0` as the wrap to `(-PI, PI]`. `k` arrives in `xmm2` and is a
per-tick blend, so the fraction of the gap that *survives* a tick is `1 - k`,
and that is the quantity carrying the exponent:

```
k' = 1 - (1 - k)^ts          0.6 -> 0.205 at 120 fps
```

The player's ground turn passes 0.6 (`main+3A7390`), so unpatched she reaches
the target heading three to four times too quickly at 120 fps.

About half the 163 call sites pass `k` in a register rather than a constant,
so there is nothing to retarget at the call sites and the fix has to go on the
one function they all funnel through. `ts` is only ever 1, 1/2 or 1/4, so the
exponent is a chain of `sqrtss` -- none, one or two -- rather than a call to
`powf`, which matters when this runs for every actor every tick.

The transform is skipped unless `0 < k < 1`. Outside that range `(1-k)^ts` is
a NaN or a sign flip, and a caller passing `k >= 1` means "snap to the target",
which is already rate-independent.

`FixTurnRate`. It touches every actor and the camera, not only Amaterasu,
which makes it the one most worth A/B-ing with F8.

#### Not every caller passes a stock per-tick blend

The conversion is right only for a `k` in stock units, and funnelling every
caller through one hook converts all of them. `tools/gen_turn_callers.py`
slices the coefficient of each of the 163 calls back through its function's
control flow to its leaves (`docs/animation/turn_callers.csv` has every one):

* **122 pass a stock per-tick blend** -- a constant (0.05 to 0.6, or 1 for a
  snap), or a field whose writers were read and found to hold one. The hook
  is right for these.
* **37 build `k` from the engine's own per-mode table**: `g - 1`, with `g`
  from a `{g^0.5, g}` pair that `FixModeConstants` already rewrites to
  `{g^ts, g}`. The jump handler's airborne steering (`main+3B5530`) passed
  `1.1^0.25 - 1 = 0.0241` at 120 fps and the hook converted it again, to
  `0.0061`: a quarter of the stock steering, where stock wants
  `1 - 0.9^0.25 = 0.0260`. Excluding these from the conversion would not do
  either: `g^ts - 1` is the engine's approximation, and a poor one for large
  `g` (the 1.9 entry would leave 4.6 times the stock gap). So each table read
  is retargeted at a private `{fast, stock}` pair (`src/turn_callers.h`) whose
  fast slot holds the stock `g` while the hook converts -- the caller passes
  the stock coefficient and the hook converts it once -- and the real table's
  value while it does not.
* **4 pass something that is not a per-tick blend at all**: the keyframe
  interpolator's fraction between two keys (`main+4B7575`), and the motion
  blend-in's `1/n` (`main+4B7700`), which lerps the other channels with the
  same weight unconverted. Those calls go to the relocated prologue at the end
  of the stub, past the conversion.

A slice follows data, not control, so every function that holds a converted
call and reads the mode byte, the fps flag or the time scale anywhere was also
read by hand (`RATE_REVIEWED`): none picks its turn coefficient by mode. The
retargets and bypasses go in with the hook or not at all.

`tools/verify_turn_callers.py` runs the DLL's own install on a mapped
`main.dll` and emulates the result under Unicorn: from a fixed facing and
target, 1/`ts` updates at 30, 60 and 120 fps must leave the gap one stock
update leaves, for all 37 table reads, every distinct constant, the jump
handler and the ground turn end to end (from building `k` to storing the
facing), and every bypassed call must return the unconverted result.
`--break table` puts the double scaling back: the jump handler's gap after
four 120 fps updates goes from 2.160 (stock) to 2.342.

#### Verifying a stub that is emitted, not declared

`installTurnRate` writes its bytes one at a time with two `rip` displacements
and four `rel8` fixups. A wrong fixup builds fine, installs fine, logs fine,
and then crashes inside the function every actor turns with.

`tools/verify_turn_stub.py` mirrors the emitter, lays the result out at a
plausible address and disassembles it. It caught a real one on the first run:
`cmp byte [rip+d], imm8` carries an immediate *after* the displacement, so
`rip` is one byte further along than the other forms and the displacement has
to be one smaller. Unfixed, the stub reads the byte after the counter.

The lesson generalises, and it is why the check exists at all: a displacement
helper that assumes the displacement is the last field of the instruction is
wrong for every opcode with a trailing immediate.

### Relocating a displaced instruction

`installScaleDetour` rewrites a site by copying its instruction into a code
cave and jumping there. The cave is wherever `allocNear` found a free page, so
**an instruction that addresses memory relative to `rip` reads from a different
address once it moves.**

Every site patched before this was `[reg+disp32]`, which relocates unchanged,
so it never came up. The airborne acceleration site is not:

```
main+3B547C   mulss xmm0, [rip+0x7B57B4]      ; the time scale
```

Copied verbatim into the cave, that read whatever lay 8 MB past the cave
instead of the time scale, and the detour multiplied the airborne acceleration
by an arbitrary float -- close enough to zero that Amaterasu lost all
horizontal control the moment she left the ground. The fix it was meant to
apply never ran at all.

`copyDisplaced` now finds the ModRM byte past any prefixes and rewrites the
displacement when `mod=00, rm=101`. `tools/check_patch_sites.py` reports which
displaced instructions are rip-relative and fails if the fixup is ever removed.

### Passthrough: the control

Every measurement in this project has been taken against "30 fps mode", which is
**not the stock game** -- it is the patched DLL with its fixes restored and its
mode-byte writers still rewritten. If that restore is incomplete in any way then
the baseline itself is wrong, and every delta measured against it inherits the
error silently.

`Passthrough=1` forwards `DirectInput8Create`, installs the harness and the
overlay, and does nothing else: no fps ladder, no fixes, no mode pinning, and F9
says so rather than pretending to work. It is the real game measured with the
same instrument.

A passthrough run is kept in its own slot and its own file
(`okami_harness_stock.csv`), because a stock run and a patched 30 fps run are
different experiments and must never share a column. The overlay says
`OKAMI PASSTHROUGH -- STOCK GAME, NO PATCHES` so a control run cannot be
mistaken for a patched build with everything muted.

### A test you can change without rebuilding

The input script is data. Omit it and the built-in one runs; otherwise:

```
Step1=600,0,0,none,settle
Step2=1600,0,1,none,run
Step3=300,0,1,jump,jump
Step4=500,0,1,none,airborne
Step5=900,1,0,none,steer across
Step6=600,0,0,none,stop
```

`<ms>,<dirX>,<dirY>,<action>,<label>` -- durations are wall-clock, which is what
makes one script mean the same thing at every frame rate. Steps run from `Step1`
and stop at the first one missing, up to 16. A malformed step anywhere (a bad
field, an unknown action, a zero length) discards the whole custom script,
the steps before it included, and the complete built-in one runs instead, with
its own length -- and the log says so, rather than running half a test.
`tools/verify_harness_script.py` loads the script through the DLL for each of
those cases and for valid and absent scripts.

This matters because the two things most worth testing next need a different
script and nothing else: a **dash** (hold longer before jumping) and a **slope**
(the same script, run on a hill). The report already tells you whether
`pl00+0xB0` ever left zero -- that is, whether the slope terms were exercised at
all -- and the answer on flat ground is no.

Runs taken with different scripts are not comparable. The script length goes
into the record, and the report calls it out rather than lining the columns up
as though they were the same experiment.

#### A note on ini sections

`Passthrough`, `Harness`, `HarnessKey` and `HarnessStick` live in `[Harness]`,
not `[Main]`. They were briefly read from the wrong section, which failed
completely silently -- every default equalled the documented value, so the keys
looked like they worked and simply ignored whatever you set them to. All four
are now echoed into the log at startup for exactly that reason.

### Reading a harness run

Two files land in the game directory after a run:

```
okami_harness.csv            one summary line per rate -- the baseline store
okami_harness_<N>fps.csv     the full per-tick trace of the last run at <N>
```

`tools/harness_report.py` reads the traces and takes a run apart. The in-game
report answers "do these two rates move her the same distance"; this answers
*where* they stopped agreeing:

```
==== 30 fps vs 120 fps ====
  t(ms)        dist30    dist120     delta
  1800          112.8      110.6     -2.0%
  2200          149.4      146.9     -1.7%
  2600          186.1      168.8     -9.3%    <- the jump starts here
  3400          259.2      212.7    -17.9%
  TOTAL         303.5      251.1    -17.3%
  launch         5.40       4.20   <- 5.4 is the running jump, 4.2 the standing one
```

#### The run that looks perfect and is worthless

The first real session produced two runs that every number said were fine --
120.0 ticks/s, 0.10 ms standard deviation, every sub-state reached, the fast
jump variant selected, the slope terms exercised -- and both were useless,
because Amaterasu was pressed against geometry.

Nothing in the run shows it. The speed field is the *requested* velocity and a
wall does not change what the controller asks for, so `hspeed` reads a healthy
130 units/s while she covers 26 units in four and a half seconds.

The check is that `pl00+0xE48` **is** the per-tick displacement the movement
code intended. Measured against what she actually covered:

```
        ratio    what it means
free    1.00     tracking exactly
30 fps  0.10     pinned for essentially the whole run
120 fps 0.78     ran free for 1.3 s, then hit something at ~1900 ms
```

So the harness reports `moveEff`, refuses to let a blocked run be read as a
result, and says which millisecond she was first pinned at. Below 0.70 the
overlay says `HARNESS BLOCKED -- MOVE TO OPEN GROUND` and the comparison
refuses to print a delta; between 0.70 and 0.92 it notes she brushed
something.

The per-tick *speed* data from a blocked run is still good -- that is how the
`main+3B55C0` decay was found in a run whose distances were all wrong.

#### What makes a run invalid

A number is worthless if the run that produced it was not the run you thought
you were doing, so both the in-game report and the offline tool refuse to be
quiet about it:

* **she never moved** -- two such runs compare as a perfect 0% match, which
  reads as a pass. Any run under 5 units is declared invalid and discarded.
* **the rate missed its target** -- a 120 fps run that only achieved 95 is not a
  120 fps measurement. The achieved rate is computed from the samples, not
  assumed from the mode, and the overlay carries a live `120/120 Hz` readout so
  you can see it before committing to a run.
* **a stall** -- one long tick invalidates a comparison the totals will not show.
* **the target heading differed between runs** -- `main+B6B134` is the direction
  the stick is asking for, stick deflection combined with camera. The airborne
  acceleration is scaled by how well the facing matches it, so the same script
  under a different camera is a different experiment. It is sampled on the first
  tick the script deflects the stick, not on the first tick of the run: with the
  stick centred the field still holds whatever it last held.
* **no repeat run** -- two runs at the *same* rate give the noise floor, and a
  cross-rate delta smaller than that floor means nothing. The report says so
  until a repeat exists.

#### What a run did and did not cover

Every fix in this patch has a condition under which it does nothing, so the
report says what the run actually reached:

* `pl00+0xB0` stayed at 0 -> the run was entirely on flat ground and
  **FixSlopeTerm was not tested at all**. Repeat on a hill for that one.
* `pl00+0xE14` peaked at 4.2 rather than 5.4 -> she only ever got the *standing*
  jump, which above 30 fps is the `main+3B41E6` bug itself.
* sub-states visited, airborne tick count, and peak per-tick speed, so "we
  tested it and it was fine" can be checked against what the code actually saw.

The script deliberately steers across in mid-air rather than holding one
direction, because the airborne accelerate block and its `v < 3.0` gate are only
exercised with a large camera-alignment term.

### Finding every copy of a bug

The airborne acceleration bug was found with a hardware watchpoint, which can
only ever see the copy that is executing. Searching for the *shape* instead --
a multiply by the time scale whose result is added into `obj+0xE48` within ten
instructions -- finds **fourteen copies of that block in the binary**, four of
them in the player:

| site | state | form |
|---|---|---|
| `main+3B547C` | jump (`main+3B3FF0`) | `v += ts*a; v *= k^ts` (table `7A81B8`) |
| `main+3C32F9` | `main+3C2E80` | identical, same 3.0 gate, same table |
| `main+3C9BE0` | `main+3C9940` | `v += ts*a; v *= k^ts` (table `7A8160`) |
| `main+3BE265` | `main+3BDCB0` | `v = v*k^ts + ts*a` (table `7A8218`) |

The last applies its decay before the increment rather than after, which changes
nothing that matters: the equilibrium is `ts*a / (1 - k^ts)` either way, and
`1 - k^ts` is about `-ts*ln k`, so the `ts` cancels and the real speed goes as
`1/ts` exactly as it does in the measured copy. `main+3C2E80` also carries its
own copy of the `v < 3.0` gate, loading the *same constant address*
(`main+674F58`) as the jump handler -- so it is fixed as a fourth `FixAirGates`
site.

The remaining ten copies are in `main+246E60`, `main+2488B0` and `main+249A90`,
which are not player code. They are the same bug and very probably make those
actors four times too fast at 120 fps, but there is no test for them yet, so
they are reported and left alone.

#### Swimming (4 sites, 2026-10-02)

The water states 0x3B (`main+3C3C70`) and 0x3C (`main+3C43C0`, swimming) have
the same block, with k = 0.97 from table `7A8160`, but they *load* the time
scale (`movss xmmN, [timeScale]`) and multiply by the constant after, so the
search above, which looks for a multiply by it, missed them. Swimming settled
at 309 units/s at 120 fps against 98 at 30. `kSwimAccelSites` gives the four
increments (`3C401A`, `3C4048`, `3C467D`, `3C47D6`) the second factor of ts.

The speed `+0xE48` has to stay a per-tick value here, as on the ground and in
the air: the ground enters 0x3B, a jump or fall enters 0x3D, and swimming hands
its speed to the stroke 0x54 and back. A first attempt scaled the water states'
moves instead. Swimming came out at the right speed, but every one of those
switches started at 4x or a quarter of the right speed, and with k = 0.97 a
switch took about a second to settle.

#### The stick drift (3 sites, 2026-09-23)

The same steering, with the time scale missing entirely, sat in three more
player states that the search above could not see, because they store to
`+0x10E8`, not `+0xE48`. When an attack hits a wall she recoils (state 0x2B,
`main+3C20E0`, then 0x2C, `main+3C2430`). While she recoils, and in state 0x48
(`main+3C70C0`), the stick steers her each tick:
`v = v * table7A81B8[mode-1] + |stick| * 1.7/1024`, then `position += v`
along her heading. The decay is k^ts through the mode constants. The stick
term has no factor of ts at all, so with the stick held she settled at 15x
stock at 120 fps (4x at the port's own 60): the "pinball" off the walls of a
small room.

The fix (`FixStickDrift`) multiplies the stick term by
`ts * (1 - k^ts) / (1 - k)`. With v stored per tick at the current rate, that
keeps both her settled speed and her rise to it exactly stock's, and it is 1
at 30 fps. The ts^2 the airborne sites use would settle 5.6% slow here. The
search for this shape (a multiply by the 1/1024 stick constant stored to
`+0x10E8`, with no time-scale multiply) finds exactly these three.
`tools/verify_stick_drift.py` checks the installed detours, the gain in every
state, the three sites under Unicorn, and the motion against stock (within 0.7%
of stock's distance; settled speed equal).

`tools/find_tick_thresholds.py` prints all of this, along with every constant
compared against a per-tick velocity, resolved by tracking xmm definitions
rather than by proximity -- the naive version over-reports by about four to one.
It also flags which findings sit inside one of the 56 player state handlers
reachable from the dispatcher at `main+3AF020`, because those are the ones the
harness can actually exercise.

### The scripted input harness

Every measurement in this project came from playing the game and reading the
log, and the noise in that is larger than most of the effects being chased.
Three consecutive 30 fps jumps in one log launched at `3.049`, `1.793` and
`3.373` per tick -- a **1.9x spread from human variation alone** -- against bugs
that are 20-50% effects. Two of three diagnoses made against that baseline were
wrong, and one "confirmed" fix turned out to be a detour that had never executed
correctly at all.

The harness removes the player from the measurement. It writes the analog stick
(`main+B6B128/B6B129`) and the action bits (`main+B6B0A8` held,
`main+B6B0D8` edge) directly, on a fixed script measured in **milliseconds**, and
samples the player once per tick. Because the script is wall-clock, it means the
same thing at every frame rate -- which is precisely the property the patch is
trying to establish -- so two runs can be diffed directly.

```
harness: ==== 30 fps vs 120 fps ====
harness:    t(ms)  dist30    dist120    delta   height30  height120
harness:      200       0.0       0.0    +0.0%       0.0        0.0
harness:     1000      41.2      40.9    -0.7%       0.0        0.0
harness:     2200      88.3      71.0   -19.6%      31.4       26.8
harness:   TOTAL      147.6     121.2   -17.9%   <- 0% means the two rates match
```

#### Where it hooks and why there

`main+3AF020` is the player's per-tick state dispatcher: a jump table at
`main+3AF8A0` over `pl00+0xE34` that calls `main+3B2CF0` for ground movement,
`main+3B3FF0` for the jump, and so on. Its first five bytes are one relocatable
instruction with no branch target inside, and `rcx` holds the player object.

Hooking that entry is the only place an injected input is deterministic: it is
after the pad update for the tick and before anything reads the stick. An
external input tool -- AutoHotkey, a virtual pad driver, a Cheat Engine timer --
cannot get that ordering, and could not do the sampling half at all, because
only code inside the tick can sample exactly once per tick. Given the sampler
has to live here regardless, driving the input from the same place is free.

For the same reason the general-purpose options were rejected:
[libTAS](https://clementgallet.github.io/libTAS/) is Linux-only and
[Hourglass](https://tasvideos.org/EmulatorResources/Hourglass) is 32-bit and
unmaintained, so neither covers a Windows x64 title.

#### Cost control

The hook does no I/O and takes no locks -- it writes into a static array and
returns -- so a run is not perturbed by its own measurement. The report is
written afterwards from the watcher thread. A run aborts and is discarded if the
frame rate changes underneath it, because a run that spans a toggle cannot be
compared with anything.

The stub is hand-assembled into a code cave rather than written as a naked
function, so unlike the older trace hooks the harness works in the MSVC build
too.

`Harness`, `HarnessKey`, `HarnessStick`.

### Reading a test log

Every A/B key reports, and the full state is dumped on each fps change:

```
fix state (fps mode): fps=120 | movement=on jump=on timers=MUTED phase=on | mask=0 speed=x0.250 jump=x4.000
```

This exists because a session was silently invalid without it. The timer A/B key
had no log line of its own -- its only output came from the mask byte changing,
and in 30 fps mode that byte is `0` whether the fix is muted or not. Pressing the
key there flipped the mute and printed nothing at all, the three timer families
never re-armed on the way back to 120 fps, and every measurement taken afterwards
was of a 120 fps game running stock 30 fps timer semantics. Any status line with
a `MUTED=` field describes a measurement that cannot be compared with a clean one.

### How these are patched

Only the action timers need a real detour, and they get one: a stub that tests
the tick parity and either runs the displaced count or skips it.

Everything else is patched in place. The float phase steps, the decay factors
and the interface oscillators are all the plain rip-relative form, so only the
4-byte displacement is rewritten, to point at a private copy the patch keeps
scaled. Constants are shared -- one address holds the 1.0 that hundreds of
instructions read -- but retargeting a single instruction cannot disturb any
other reader, and switching a fix off just writes the stock value back into the
private copy. The rate gates and the doubly-compensated windows are smaller
still: one immediate byte and two bytes of `nop` respectively.

`tools/check_patch_sites.py` checks all 1435 together: every `orig` byte string
is still what the game ships, no two patched ranges touch, so no detour can
land inside another patch's instruction, and none of the 9341 destinations of
the game's 903 switch tables lands part-way through a relocated one. Fourteen
destinations land exactly *on* a patched site, which is fine -- the jump enters
the stub at its first byte.

What is still wrong at 60 fps
-----------------------------

A whole-program inventory of what still animates per tick -- the effect engine
(every flame, spark and glow), per-object texture scrolling, the HUD fade, the
loading screen, the scene transitions, and the port's own compensations that
stop at 60 fps -- is in [docs/animation/README.md](animation/README.md),
with every candidate site in `docs/animation/sites.csv`. It also records that
the stock game ticks at 60, not 30, inside the options, memory-card and
pause-menu screens, which the table below does not yet take into account.

| System | Behaviour | Notes |
|--------|-----------|-------|
| **Class-specific countdowns** | still run at double speed | **the largest identified gap.** 156 sites use the same `dec`/`cmp`/`jg` countdown, but on a field of their own class rather than one of the five shared character fields -- `cCockInkGauge+0x7C`, `cTitle+0x1B`, `cOptionSoundSetting+0x94`, `et0f+0x1138` and so on. They are deliberately not patched: they are spread over roughly eighty classes and a hundred-odd offsets with no shared structure to reason from, nothing to measure any of them against, and 42 of them are shorter than the five bytes a detour needs. The character-object timers were safe to sweep because they are one field of one base class with a measurable ground truth; these are eighty separate guesses |
| One-shot float nudges | unchanged by design | 285 sites step a field by 10, 20, 40 or 100 with no limit check; they look like event handlers, not per-tick phases, so they are left alone. 56 more step by 1.0 or less with no limit test either way, and 50 step by more than 1.0 *with* a limit test -- the ink gauge's slide-in is one of those, at 62 units a tick |
| Aggressive damping (`k` < 0.8) | unchanged by design | 76 sites; a factor of 0.5 or 0.2 a tick is more likely a one-shot "halve it on impact" than smoothing |
| 15 register-form action timers | unchanged | their decrement and store are not adjacent, so there is no room to relocate them |
| 4 frame-counter gates | unchanged | they load the counter into a register and then reuse that register, so widening the mask is not provably side-effect free |
| `objScroll`'s two layers | unchanged | it desynchronises them by bumping the global frame counter by one, which a counter sampled once per frame cannot reproduce |
| Per-object rates (`field += obj->speed`) | not investigated | the port's 137 time-scale multiplies are meant to cover these; a blanket sweep would include position integration and is too dangerous to attempt by pattern |

Three things that sound like they should be bugs were checked and are not:

- **Per-tick exponential growth.** 18 sites multiply a field by a factor between
  1 and 2, which would compound twice as fast at 60 fps -- but nine of them are
  `+0xF54`, the animation rate, and the rest are `+0xE10`/`+0xE18` velocity
  components. A factor of 1.3 applied every tick would run away inside a second,
  so these are one-shot boosts, not per-tick growth.
- **Integer angle accumulators.** None exist. Every rotation in this engine is a
  float, so it is already covered by the phase step family.
- **Time-scale abuse.** The time scale at main+0xB6AC38 is written by
  `flower_tick` and by nothing else in the image, so no cutscene, brush mode or
  slow-motion effect manipulates it behind the patch's back. It is also only
  ever multiplied -- never divided by, never compared against a literal -- which
  is what makes 0.25 safe at 120 fps.

The patch ships the tools used to find the movement bug (see
"Diagnostics") plus experimental per-group gating (`FixMenus`, `FixHud`,
`FixEffects`), all off by default: half-rating the effect system was
measured to slow the game down, and gating anything that also draws can make
it flicker. The same method that fixed movement applies here, one subsystem
at a time.

### Engine structure notes (build 6990973)

- `flower_tick` (exported) runs one frame: Steam callbacks, the frame
  configuration, the game's update-message callback (stored at
  main+0xB6C570/+0xB6C578 by the exported
  `flower_set_update_message_function`), render packet update, then the
  task manager step, pad update and system events.
- `cTaskManager::run` (main+0x456530) steps every task once per tick through
  `cTaskManager::step(entry)` (main+0x456600). Entries are 0x70 bytes; the
  task object is at +0x18 and is a `hdlr::Handler` wrapping the task's
  entry function at +0x10; each task is an OS thread woken for one frame.
  The patch detours `step` to log each distinct task function and to
  optionally skip listed ones on odd ticks (`HalfRateTasks`).
- Only seven long-lived tasks exist in play: boot (fn main+0x436180),
  kernel (main+0x4B52C0, main+0x437360), title/loading (main+0x492B40,
  main+0x5FE8C0), HUD (main+0x1C1DB0, references `cCockBase`) and the main
  game control task (main+0x531260, a coroutine yielding through
  main+0x4567C0). Opening the pause menu or the Celestial Brush creates no
  new task; both run inside the main game task, so gating a whole task
  does not isolate them.
- The player is class `pl00`; its setup method stores the instance in
  main+0xB6B2D0. Its transform is at `[pl00+0xA8]` with x/y/z at +0/+4/+8
  (the `status:` probe reads it); state bytes at +0xE34/+0xE35; the movement
  sub-state at +0xE36 (1 jog, 3 turn, 5 run, 7 skid, 9 dash); horizontal
  speed per tick at +0xE48; vertical velocity at +0xE54 (correctly
  time-scaled by the engine); the dash charge counter at +0x1174; the
  animation playback rate at +0xF54. The movement handlers are at
  main+0x3B3183 (jog), main+0x3B34C8 (run) and main+0x3B381A (dash), and
  their speed targets are the subject of the movement fix above. Enemy
  classes are `em00`..`em60`, objects derive from `cObjBase` (transform
  pointer likewise at +0xA8).
- Per-mode constant tables exist: main+0x7A81B8 is indexed by the frame-rate
  mode byte and holds pairs of per-tick decay factors where the 60 fps entry
  is the square root of the 30 fps one (0.9274 against 0.86). Finding more
  of these is a good way to spot what the port did and did not convert.
- Menu screens are global instances built by static initializers
  (main+0x12CFC0 ff.): the brush HUD window `cCockFudeWnd` at
  main+0xB1CC20, the brush screen `cSubScrFude` at main+0xB1EBA0, further
  `cSubScrBase` screens at main+0xB1E100, +0xB1F240, +0xB1F510,
  +0xB200A0. Their per-frame update is dispatched from inside the main
  game task; locating that dispatch (and the effect system `espSys`) is the
  next step toward real-time menus and brush at 60 fps.

Turning the PS2 display mode off is unrelated to game speed: the game code
consults `IsPs2DispMode` for UI/framing offsets only.

Usage
-----

1. Copy `DINPUT8.dll` into the game folder (`<Steam>\steamapps\common\Okami\`,
   next to `okami.exe`). A settings file is optional: `okami_hackfix.ini`
   (the player's keys, `release/okami_hackfix.ini`), or the development-era
   `okami.ini` (every key, this folder's), read when `okami_hackfix.ini` is
   absent.
2. Start the game from Steam. It boots at `DefaultFps` (60 by default) with
   every fix applied, and a notice at the top left shows the rate.
3. **F9** cycles 30 -> 60 -> 120 -> 30 (120 only where `checkFpsImms` passes),
   with a notice and a beep each press. The choice is saved as `DefaultFps`
   in `okami_hackfix.ini` (created if absent), never in `okami.ini`.
4. With `Developer=1` (the default when the file is `okami.ini`) the A/B keys,
   the harness (F3), the brush and enemy watches and the 5 s `status:` lines
   are on, as before; `Overlay=1` shows the current state, the live walking
   speed and the height of the last jump on screen.

   | Key | Switches |
   |-----|----------|
   | **F9** | 30 / 60 / 120 fps |
   | **F8** | the movement fixes (speed and animation rate) |
   | **F7** | the jump and launch velocity fixes |
   | **F6** | the duration fixes: action timers, effect rates, interface pulse, input windows |
   | **F5** | the float phase step and decay fixes |
   | **F10** | the experimental interface gating (off by default) |
5. `okami_hackfix.log` next to the game records which settings file was
   read, what the patch resolved and installed, and each toggle.

To uninstall, delete `DINPUT8.dll`, the ini and `okami_hackfix.log`. The
player's package is built by `tools/make_release.py` (`release/README.txt`).

Why `DINPUT8.dll`? `flower_kernel.dll` imports `DirectInput8Create` by
name, so a proxy DLL placed in the game folder is loaded by the system
loader and forwards to the real `%SystemRoot%\System32\dinput8.dll` while
applying the runtime patches from a watcher thread. Same technique as the
DGS (The Great Ace Attorney) high-FPS patch this project is modeled on.

Configuration (`okami_hackfix.ini` or `okami.ini`, section `[Main]`)
--------------------------------------------------------------------

`okami_hackfix.ini` is read when present, else `okami.ini`; without either
the defaults apply with `Developer=0`.

| Key | Default | Meaning |
|-----|---------|---------|
| `Developer` | `0` (`1` in `okami.ini`) | The development features' defaults: the A/B keys F4..F8 and F10, the harness and F3, `BrushWatch`, `EnemyWatch`, `StatusInterval=5`. Each key below still overrides. |
| `DefaultFps` | `60` | Rate the game starts at: `30` (stock), `60` or `120`. F9 saves it in `okami_hackfix.ini`. |
| `ToggleKey` | `F9` | Hotkey: `F1`..`F24`, a letter/digit, `Home`, `End`, `Insert`, `Delete`, `Pause`, `ScrollLock`, `Numpad0`..`Numpad9`, a hex virtual-key code (`0x78`), or `None` to disable. |
| `RequireFocus` | `1` | Only react to the hotkey while the game window is in the foreground. |
| `Beep` | `1` | System beep on each switch. |
| `SyncInterval` | `0` | DXGI present sync interval in 60 fps mode. `0` presents immediately and the patch paces frames itself (recommended, ideal with G-Sync / FreeSync). `1` waits for vblank; only useful on a fixed 60 Hz display in borderless or windowed mode to avoid tearing. |
| `FixRunSpeed` | `1` | Correct the jog, run and dash speeds in 60 fps mode (see "Movement at 60 fps"). |
| `FixAnimRate` | `1` | Keep the jog, run and dash animation playback rates at their 30 fps values. |
| `SpeedToggleKey` | `F8` | Hotkey that switches the two fixes above off and on, for A/B comparison. |
| `FixJumpHeight` | `1` | Make jumps and the wall jump reach their 30 fps height in 60 fps mode (see "Jump height at 60 fps"). |
| `JumpToggleKey` | `F7` | Hotkey that switches the jump fix off and on. Separate from `SpeedToggleKey` so a movement test cannot change the jump by accident. |
| `FixActionTimers` | `1` | Make character action durations last the same real time at 60 fps (682 sites, register and memory form; see "Durations at 60 fps"). |
| `FixInputWindows` | `1` | Undo the ten input windows that are compensated twice, once from the fps byte and again by the duration shift. |
| `FixFrameGates` | `1` | Make repeating effects -- footstep dust, sparks, ripples, aura pulses -- appear at their 30 fps rate (33 sites). |
| `FixFramePhases` | `1` | Slow the interface oscillators to real time: option screens, the save screen, pickups and the enemy marker (22 sites). |
| `TimerToggleKey` | `F6` | Hotkey that A/Bs the four fixes above together. |
| `FixPhaseSteps` | `1` | Halve per-tick float steps: effect lifetimes, fades, scrolls, oscillator phases (366 instructions). |
| `FixDecay` | `1` | Raise per-tick damping factors to the time scale instead of applying them twice as often (195 instructions). |
| `PhaseToggleKey` | `F5` | Hotkey that A/Bs the two fixes above. |
| `FixLaunchVelocity` | `1` | Undo the double-scaled vertical launch velocities for knockbacks and special moves (23 sites). |
| `Fps120` | `0` | Move the engine's frame ladder to its next rung: timeScale 0.25, duration shift 2, fps 120, and the frame limiter's cap from 60 to 120. Measured working; see "What is still wrong" for the headroom and frame-generation caveats. Needs a display that can run at 120 and nothing capping or synthesising frames. |
| `Overlay` | `0` | Draw a status line over the game: mode, movement and jump fix state, live walking speed, height of the last jump, active gate set. |
| `StatusInterval` | `5` | Seconds between `status:` lines in the log (`0` = off). Each line includes the player position, path length per second and peak speed with the player state byte. |
| `SpeedLog` | `0` | Log every 100 ms player sample: speed, movement sub-state, dash charge and animation rate. |
| `Fixes` | `1` | Master switch for the experimental interface gating below. |
| `FixToggleKey` | `F10` | Hotkey toggling `Fixes` in-game (same key names as `ToggleKey`). |
| `FixMenus`, `FixHud`, `FixEffects` | `0` | Step the sub-screen, HUD or effect classes every other tick in 60 fps mode. Experimental: gating something that draws can make it flicker, and `FixEffects` was measured to slow the game down. |
| `HalfRateTasks` | (empty) | Game tasks stepped every other tick while fixes are active in 60 fps mode, as comma-separated prefixes of the names logged as `task: ...`. |
| `JumpTrace` | `0` | Log every 10 ms sample of a jump's climb (height, vertical velocity, physics flags). Noisy; for working on the jump. |
| `Probes`, `ExtraGates`, `GateSets`, `GateSetNames`, `SetKey`, `MarkKey`, `GateTrace`, `WatchBytes` | (empty / off) | Diagnostics, see below. |
| `ProxyDll` | (empty) | Forward DirectInput to another `dinput8` proxy instead of the system DLL, so this patch can coexist with mods that also ship a `DINPUT8.dll` (rename theirs and point at it here). |

An existing `okami.ini` in the game folder is never overwritten by
`tools/deploy.py`.

Diagnostics
-----------

The movement bug was found by measuring the running game, not by reading
code alone, and the instrumentation that did it ships with the patch. All of
it is off by default and costs nothing when unused.

- **Player probe.** Every `status:` line carries the player's position, path
  length per second and peak speed. `SpeedLog=1` adds a line per 100 ms
  sample with the movement sub-state, the dash charge counter and the
  animation rate, which is what produced the speed tables above.
- **Jump probe.** The watcher samples the player at 100 Hz and measures every
  jump as the rise from the sample where the vertical velocity turns positive
  to the one where it turns negative, which also captures a wall jump landing
  part-way through a fall. Each one is logged as a `jump:` line with the rise,
  the launch velocity implied by it, the player state and whether the fix was
  active, and the last rise is shown on the overlay. `JumpTrace=1` adds a line
  per 10 ms sample of the climb, with the height, the vertical velocity and the
  physics flags; collapsing those samples to one per tick is what exposed the
  float window, since it shows the per-tick gravity directly.
- **Probes.** `Probes=cs:<rva>` patches one `call rel32` site to count how
  often that call runs; `Probes=fn:<rva>:<len>[:<fixup>/...]` detours a whole
  function the same way (`len` is the number of prologue bytes to relocate,
  each `fixup` the byte offset of a rip-relative or rel32 field inside them).
  Counts appear in the log as `gates:` lines. This is how the per-frame
  dispatcher at main+0x4BA500 was mapped subsystem by subsystem.
- **Gate sets.** `GateSets` takes `|`-separated groups of probe names to run
  at half rate, `GateSetNames` labels them, and `SetKey` cycles through them
  in-game. With `Overlay=1` naming the active set, several hypotheses can be
  compared in a single play session.
- **Marks.** `MarkKey` writes a labelled snapshot of every probe counter to
  the log, so a session can be split into phases (walking, menu, brush)
  without guessing from timestamps.
- **Watches.** `WatchBytes=<rva>,<rva>` appends those bytes of `main.dll` to
  each status line, for watching game state flags change.
- **Caller traces.** `GateTrace=N` logs the return-address chain for the
  first N calls of each probe, which identifies who drives a subsystem.

`tools/` holds the offline counterparts (pefile + capstone): RTTI vtable and
class dumping, cross-references, disassembly by range and import/export
summaries.

Seven of them are generators. Each one scans `main.dll` for one bug shape and
writes a table into `src/`, so every patched site is reproducible from the game
binary rather than hand-collected, and the whole set can be rebuilt against
another build of the game:

    tools/find_action_timers.py      the register-form action countdowns
    tools/find_memory_timers.py      the memory-form encoding of the same
    tools/find_lea_timers.py         the lea-form encoding of the same
    tools/find_frame_gates.py        effect rate gates on the frame counter
    tools/find_frame_phases.py       interface oscillators on the frame counter
    tools/find_phase_steps.py        float per-tick steps with a limit check
    tools/find_decay_factors.py      per-tick damping multiplies
    tools/find_launch_velocities.py  double-scaled vertical launches

`tools/check_patch_sites.py` validates all seven together: that every `orig`
byte string still matches the shipped binary, that no two patched ranges
overlap, and -- the one a generator cannot see on its own -- that none of the
9341 destinations of the game's 903 image-base-relative switch tables lands
part-way through a relocated instruction. Run it after regenerating anything.

How the 30 fps lock works (reverse-engineered)
----------------------------------------------

- The game boots with its "PS2 display mode" flag enabled, which drives the
  whole presentation pipeline at 30 fps.
- Every frame, `flower_tick` (exported from main.dll) writes the engine's
  frame configuration: `fps = 30`, `timeScale = 1.0` unless the mode byte
  next to it equals `1`, in which case it writes `fps = 60`,
  `timeScale = 0.5` (the engine's native 60 fps mode, also used by menus).
- The game host loop only drains `flower_tick()`, and the render packet
  update inside it presents the swap chain (`SwapChain::swap` in
  flower_kernel.dll, `IDXGISwapChain::Present` on the pointer stored in a
  flower_kernel global). The present cadence *is* the game step rate. On a
  fixed 60 Hz display in exclusive fullscreen the swap chain targets a 30 Hz
  mode so each synchronous present blocks 33.3 ms; in PS2 display mode the
  engine paces to 30 steps/s regardless of display mode.

Implementing 60 fps
-------------------

The patch applies five coordinated fixes at runtime (in memory only):

1. **Disable PS2 display mode** - calls the engine's own exported
   `SetPs2DispMode(false)` once the engine DLLs are loaded.

2. **Pin the engine's 60 fps configuration byte to 1.** The address of the
   byte is read out of `flower_tick`'s own code (its
   `cmp byte ptr [mode], 1`). The game's system-state machine rewrites the
   byte to 2 (30 fps semantics) throughout gameplay, so the patch scans
   main.dll's code for every `mov byte ptr [mode], 2` whose target is that
   byte (11 sites on build 6990973) and rewrites their immediate to 1, so
   the engine's own writers emit the 60 fps configuration. The watcher
   thread also re-asserts the byte as a safety net.

3. **Decouple the game step rate from the swap chain's present** - hook
   `IDXGISwapChain::Present` (vtable slot 8 of the object stored in the
   flower_kernel global, located by parsing `SwapChain::swap`). The shim
   presents with `SyncInterval` (default 0, no vblank wait) and then waits
   on a drift-free 60 Hz grid using a high-resolution waitable timer with a
   short final spin, so frame times are 16.667 ms to within tens of
   microseconds. Overlays and drivers wrap the swap chain in proxy objects
   (ReShade, NVIDIA `NvPresent64.dll`), so the patch keeps a table of every
   vtable it has hooked with its original `Present`, and a per-thread
   re-entrancy guard makes sure a game frame that passes through several
   hooked layers is paced exactly once. Resolution changes and swap chain
   recreation are handled by re-checking the hook every 50 ms.

4. **Set the config refresh rate to 60** via the engine's own exported
   `SystemConfig::SetRefleshRate(60)`.

5. **Convert the player movement code the port left in 30 fps units** -
   a detour on the run handler's target speed, scaled parameters for the
   jog handler, and three detours keeping the animation playback rates at
   their 30 fps values. See "Movement at 60 fps"; every site is verified
   against its expected bytes before it is written, and everything is
   restored when switching back to 30 fps.

Together these make the game run at 60 steps/s with the engine's correct
60 fps frame configuration, with movement at real speed while animation and
input run twice as smoothly.

Hotkey toggle (F9)
------------------

Press **F9** in-game to cycle 30 -> 60 -> 120 fps live (120 is the `Fps120`
rung below, offered only where `checkFpsImms` passes). The two engine modes:

| Mode  | Engine config          | Step rate | Behavior |
|-------|------------------------|-----------|----------|
| 60 fps (default) | fps=60, timeScale=0.5 (mode byte pinned to 1), PS2 disp off | 16.667 ms (paced by the patch) | evenly paced 60 Hz, movement at real time, interface faster than stock |
| 30 fps | fps=30, timeScale=1.0 (mode byte 2), PS2 disp on | stock present cadence | stock game, untouched |

Switching to 30 fps restores every hooked `Present` slot to its original
implementation, restores the mode-writer immediates from 1 back to 2 and
re-asserts mode=2, and re-enables PS2 display mode. Switching back to 60 fps
re-applies all four fixes. The switch takes effect on the next frame; a beep
plays and the choice is logged.

The key is polled with `GetAsyncKeyState` (edge-triggered on the physical
key state) from the patch's own thread, so it works with any input method;
by default it only fires while the game window is in the foreground.

What the log tells you
----------------------

`okami_hackfix.log` (next to the game) is the first thing to look at when
something is off:

- `resolved:` lines show where the patch found the mode byte, the writer
  sites and the swap chain slot; `verify:` / `FATAL:` lines mean the game
  build did not match and nothing was patched.
- `present hooked: vtable <module> orig <module>` names the layer whose
  swap chain proxy the engine is presenting through (ReShade's `dxgi.dll`,
  NVIDIA's `NvPresent64.dll`, the system `dxgi.dll`, ...).
- `swapchain:` shows the swap chain the game created (size, refresh,
  windowed, swap effect) and `present:` the sync interval the game asked for.
- `status: N ticks/s, M presents/s (cfg fps=.. tscale=.. mode=.. ps2=..)`:
  `ticks/s` is the engine's own frame counter (game speed), `presents/s`
  the frames the patch paced. Both should read ~60 in 60 fps mode and
  ticks/s ~30 in 30 fps mode.
- `EXCEPTION ... at <module+offset>` is logged for the first hard faults in
  the process, so a crash report can say which module faulted.

Verified on build 6990973 with ReShade 6.8 + RenoDX + ReLimiter and the
NVIDIA present layer active (borderless window, 160 Hz VRR display):

| Run | ticks/s | presents/s | engine config |
|-----|---------|------------|---------------|
| stock (`DefaultFps=30`, nothing patched) | 29.9 | - | fps=30, tscale=1.0, mode=2, ps2=1 |
| stock, title phase (game's own switch) | ~60 | - | fps=60, tscale=0.5, mode=1, ps2=1 |
| 60 fps mode | 59.8 - 60.2 | 59.7 - 60.2 | fps=60, tscale=0.5, mode=1, ps2=0 |
| after F9 back to 30 | 29.9 | - | fps=30, tscale=1.0, mode=2, ps2=1 |

The stock game briefly runs its own 60 fps configuration outside gameplay
(title / menus), which is why 30 fps mode leaves the mode byte entirely to
the game instead of forcing it.

Movement speeds, measured the same way (units per second, flat ground):

| Stage | 30 fps | 60 fps with the fix |
|-------|--------|---------------------|
| jog   | 123 | 126 |
| run   | 158 | 162 |
| dash  | 206 | 207 |

Animation playback rates over the same runs were 1.06 / 0.99 / 1.27 at
30 fps against 1.08 / 1.00 / 1.28 at 60 fps.

Build
-----

Any of these toolchains works; the result is a single static `dinput8.dll`
with no runtime dependencies beyond `user32`/`winmm`.

**LLVM clang + Ninja** (needs the Windows SDK and MSVC headers from Visual
Studio or the Build Tools; `clang` auto-detects them):

    cmake --preset clang
    cmake --build --preset clang
    python tools/deploy.py        # copies DINPUT8.dll (+ okami.ini) into the game

**Visual Studio 2026** (`cl.exe`):

    cmake --preset msvc
    cmake --build --preset msvc

**MinGW via [pixi](https://pixi.sh)** (conda-forge toolchain, no Visual
Studio needed):

    pixi run -e build configure
    pixi run -e build build
    pixi run -e build deploy

GCC has no `__try`/`__except`, so the few callbacks that must survive a fault
in game memory go through `guardedCall`, which is `__try` on the MSVC-ABI
compilers and a vectored exception handler on GCC.
`tools/verify_fault_guard.py --dll <dll>` checks either; define
`OKAMI_VEH_GUARD` to build the GCC path with clang.

Output lands in `.build/bin/` (`.build-msvc/bin/Release/` for the VS
preset). `tools/deploy.py` finds the game through the Steam library list
(`libraryfolders.vdf`); override with `--game-dir` or the `OKAMI_DIR`
environment variable, and use `--uninstall` to remove the deployed files.

A tracing variant (per-frame instrumentation for reverse engineering,
gcc/clang only, hard-coded build 6990973 offsets) builds with the
`clang-trace` / `mingw-trace` presets into `.build-trace`.

Notes / limitations
-------------------

- Movement is real time in 60 fps mode, but the interface is not: menus,
  parts of the HUD and some effects animate faster than on the stock game.
- The movement and jump fixes cover Amaterasu. Other characters have their
  own speed code and have not been audited the same way.
- The duration fixes are found by pattern, not by understanding each site.
  They are backed by measurement on the jump and by a clean structural
  signature everywhere else, but 842 patched sites is a wide net: if something
  behaves oddly, **F6** and **F5** narrow it down quickly.
- 120 fps (`Fps120=1`) **runs**. Measured on a 4K 160 Hz display: a steady
  120.0 ticks/s with presents tracking ticks exactly, sustained dash speed of
  209.5 units/s against 206.8 at 60 fps and a 206 reference at 30, and a jump
  whose rise/want ratio is 1.46-1.51 against 1.48-1.50 at 60 fps. The whole fix
  stack follows the time scale down to 0.25 on its own, and the action timer
  mask widening to 3 -- counting once every four ticks -- lands the jump in the
  same regime as 60 fps. It is still only about eighty seconds in one area with
  no combat, so treat it as working rather than verified. Every reader
  of the four frame-config fields has been checked: the duration shift is only
  ever loaded into `ecx` and used as `shl reg, cl`, so a 2 quadruples a window
  as cleanly as a 1 doubles it; the fps byte is only ever halved, divided by 30
  or doubled, all of which stay exact at 120, and its largest consumer reaches
  240 in a byte field; the time scale is only ever multiplied, never divided by
  or compared against; and the frame divider at main+0xB6AC3C has **no reader at
  all** -- no rip-relative access outside the two writes, and its address
  appears nowhere in the image, so nothing can be reading it indirectly either.
  The one thing that would have broken it is now handled: the game paces itself
  in `sub_4B6BF0`, the wait callback `GXPacket::update` runs each frame, and
  that starts from a hard-coded `mov r8d, 60`. Left alone it would have held
  the engine to 60 frames a second while the config told every timer a frame
  was worth a quarter of a step, and the game would have run at **half speed**.
  It is retuned with the rest of the ladder.
- **120 fps leaves very little headroom, and a shortfall slows the game rather
  than making it choppy.** The engine advances game time by the time scale once
  per rendered frame, so at `tscale=0.250` anything under 120 fps is game time
  running slow in proportion: 90 fps is 75% speed. This is true at 60 fps too,
  but there the same machine holds 59.4/60 with room to spare, where at 120 it
  dipped to 107-114 several times in a short session. Check `ticks/s` in the
  log rather than any external frame counter.
- **Frame generation and frame-rate limiters must be off.** NVIDIA Smooth
  Motion held the render rate at 75 fps, which the patch faithfully turned into
  62% game speed. Anything that caps or synthesises frames will do the same.
- The ladder only has power-of-two rungs: 30, 60, 120, 240. There is no 90 fps
  option, because the duration shift has to be an integer shift count and the
  action timer mask has to be a power of two minus one.
- Frame pacing in 60 fps mode is a fixed 16.667 ms step enforced by the
  patch. A machine that cannot sustain 60 fps will show dropped steps rather
  than smooth 30 fps.
- Presentation in 60 fps mode is asynchronous by default (`SyncInterval=0`).
  On a variable-refresh display (G-Sync / FreeSync) this is tear-free and
  perfectly smooth. On a fixed-refresh display a tear line may occasionally
  be visible; on a 60 Hz display in borderless/windowed mode try
  `SyncInterval=1`. 30 fps mode always uses the stock (vsync'd) present.
- `SetRefleshRate(60)` goes through the game's own config manager, so the
  game persists it into `%APPDATA%\OKAMI HD\okami_cnf.ini` when it saves
  its settings (stored scaled, as `RefleshRate=6000000`, read back as
  60 Hz). The stock 30 fps pacing does not depend on this value (measured
  29.9 ticks/s in stock mode with it set), so it is harmless to leave.
- Only one `DINPUT8.dll` can sit in the game folder. To combine with
  another dinput8-based mod (e.g. the CrashFix DirectInput enumeration fix),
  rename that mod's DLL and set `ProxyDll=` to it.

Project layout
--------------

    CMakeLists.txt          builds the proxy DLL with clang, MSVC or MinGW
    CMakePresets.json       clang / msvc / mingw (+ -trace, clang-tracer) presets
    pixi.toml               pixi workspace for the MinGW route + tasks
    src/dinput8_proxy.cpp   proxy + runtime patch engine (60/30 fps toggle)
    src/mingw_guard_fix.c   MinGW CRT stack-canary workaround (MinGW only)
    src/*.h                 generated patch site tables (see tools/find_*.py)
    tools/gamedir.py        locates the game through the Steam library list
    tools/deploy.py         copies the build into the game folder
    tools/find_*.py         generate the patch site tables from main.dll
    tools/check_patch_sites.py  validate every table against the game binary
    tools/pcode_census.py   Ghidra p-code census: every self-updating store and clock read
    tools/animation_inventory.py  census -> docs/animation/{sites,clock_reads}.csv, summary.md
    tools/ghidra_lines.py   decompile functions with an instruction RVA on every line
    tools/gen_tracer.py     tracer stub pool for every candidate -> src/generated/tracer_sites.h
    tools/verify_tracer.py  emulate every tracer stub against the original bytes (Unicorn)
    tools/tracer_selftest.py  run the tracer DLL's install outside the game and check it
    tools/tracer_report.py  tracer session + static classes -> docs/animation/classification.csv
    tools/verify_tracer_report.py  which phase file the report reads, per case (finished, autosave, exit, cut short, restarted runs)
    tools/gen_turn_callers.py  where each turn caller's coefficient comes from -> src/turn_callers.h
    tools/verify_turn_callers.py  the turn fix's heading gap against stock, emulated (Unicorn)
    tools/verify_install_failure.py  the turn and frame-clock installs failing at each write: undone, or left stock
    tools/verify_harness_script.py  which script F3 runs for every shape of Step<n>
    tools/verify_fault_guard.py  the fault guard in a built DLL (either implementation)
    tools/site_facts.py     classify every candidate from the code (Ghidra p-code)
    src/tracer_runtime.h    tracer install, dump, shedding, route overlay (tracer build only)
    docs/animation/         what still animates per tick at 120 fps, and where (README.md)
    tools/*.py              RE + analysis scripts (pefile/capstone)
    okami.ini               user settings (documented inline)

Changelog
---------

**1.0.0** - the first public release.
- 30, 60 and 120 fps, cycled in game with F9; the choice is kept for the next
  start. 30 fps is the game as shipped.
- Movement, jumps, swimming, action timers, effects, menus, the day clock,
  scripted pauses and the world's animations run at their stock real-time
  speed at 60 and 120: every one of the 12,485 candidate sites in the census
  is patched or excluded with a recorded reason (`docs/animation`).
- Optional `okami_hackfix.ini` with the player's settings (start rate, key,
  sync interval, draw distance, `ProxyDll`); the development features (A/B
  keys, harness, watches, status lines) are off unless `Developer=1`.
- An on-screen notice at start-up and on each F9 press; a red one when part of
  the patch did not go in or the game version is not recognised, in which case
  the game runs as shipped.

Development versions
--------------------

The versions below are the development builds before the public release,
numbered on from Enaium's original patch; public numbering starts at 1.0.0
above.

**dev 1.5.0**
- Fixed: the other two encodings of the action timers. The 1.4.0 table only
  covered the form that counts through a register, which is 259 of 787 sites.
  When the compiler has no further use for the value it counts straight against
  memory (422 sites), and when the handler needs the value from before the count
  it uses `lea` instead of `dec` so as not to clobber the flags (106 sites).
  Neither was visible to a pattern written around a load/store pair, and between
  them they are why so much of the game still ran at double speed. Each needs a
  different skip path: the memory form publishes its own "not finished yet"
  flags, because there the count *is* what the following `jne` reads, and the
  lea form copies the old value into the register the `lea` would have written.
- Fixed: one site in `hm68` was in the memory-timer table by mistake. It steps
  `+0xE3E` to select the next of a set of sub-objects from a pointer array, so
  it is a sequence position rather than a duration. The generators now exclude
  any field used as an array index inside the same function.
- Fixed: effect spawn rates. 33 sites gate repeating effects straight off the
  frame counter with `test byte ptr [frameCounter], N`, so footstep dust, trail
  sparks, ripples and aura pulses all appeared twice as often at 60 fps. The
  mask is widened instead, one byte per site.
- Fixed: the interface oscillators. 22 reads feed the frame counter into a sine
  at ten degrees a frame, which is what made the option screens, the save
  screen, pickups and the enemy marker pulse at double speed. They are
  retargeted at a halved copy of the counter; nothing else that reads it is
  touched.
- Fixed: ten input windows in the player code that are compensated twice, once
  as `3 * (fps / 30)` and again by the duration shift, making them twice as long
  in real time at 60 fps as at 30.
- Fixed: `Fps120` would have run the game at half speed. The engine's own frame
  limiter starts from a hard-coded `mov r8d, 60`, so the config would have asked
  for quarter-sized steps while the limiter still delivered 60 of them a second.
  It is now part of the ladder.
- Settled: the frame divider at main+0xB6AC3C, the last documented unknown about
  120 fps, has no reader anywhere in the image.
- Changed: the overlay now reports how many sites each toggle is holding.
- Added: `tools/find_memory_timers.py`, `tools/find_lea_timers.py`,
  `tools/find_frame_gates.py` and `tools/find_frame_phases.py`, and
  `tools/check_patch_sites.py`, which validates all seven tables against the
  shipped binary -- bytes, overlap, and whether any switch-table destination
  lands inside a relocated instruction.

**dev 1.4.0**
- Fixed: the engine's durations. The port doubles input windows for 60 fps but
  no object state duration anywhere, so every action window, effect lifetime,
  fade, scroll and damping factor ran at double speed. Four families are now
  converted: 259 character action timers, 365 float phase steps, 195 per-tick
  decay factors and 23 double-scaled launch velocities. See "Durations at
  60 fps" for how each is found and patched.
- Changed: the jump's wind-up and float windows are no longer patched by hand.
  They were two instances of the general action timer fault, and the general
  fix covers them without the boundary asymmetry that the hand-tuned seeds
  needed (`2*N` for one window, `2*(N-1)+1` for the other).
- Added: `tools/find_action_timers.py`, `tools/find_phase_steps.py`,
  `tools/find_decay_factors.py` and `tools/find_launch_velocities.py`, which
  generate the four tables in `src/` so they can be rebuilt against another
  build of the game.
- Added: `Fps120`, a move to the next rung of the
  engine's frame ladder (timeScale 0.25, duration shift 2). Every fix in the
  patch is expressed in terms of the engine's time scale, so they follow it.
- Fixed: `gateSetLabel` formatted `"set %d"` with no argument, reading a
  missing vararg whenever an unnamed gate set was shown on the overlay.

**dev 1.3.0**
- Fixed: jumps fell far short of their proper height in 60 fps mode, from
  three independent frame-rate mistakes in the same action. The vertical
  integrator is already time-scaled on both the velocity and the gravity, so
  a jump is frame-rate independent, but (1) the jump state seeds its launch
  velocity with `timeScale * 5.0` and so scales it twice, (2) the window in
  which holding the button charges that velocity is a hard-coded 5 ticks, and
  (3) so is the window in which the jump floats by adding `timeScale * 0.5`
  back to the velocity each tick. The patch undoes the double scaling and
  makes both windows last the same real time as at 30 fps. Measured rise from
  the same launch: 17.3 before, 72.6 after, against 69.1 at 30 fps.
- Fixed, as a consequence: the wall jump. It adds its impulse to a fall in
  progress, so at half strength it gained almost nothing - the "spins in
  place and gains no height" behaviour that previous versions worked around
  by telling you to drop to 30 fps. The earlier diagnosis (an unauthored
  60 fps entry in the motion data) was wrong; it is a code bug and the data
  is not involved.
- Added: `FixJumpHeight` and a dedicated **F7** A/B key, kept separate from
  the movement fixes on F8.
- Added: jump measurement. The player is now sampled at 100 Hz, every jump is
  logged with its rise, launch velocity, climb time and wind-up, and the
  overlay shows the height of the last one. `JumpTrace=1` traces the whole
  climb sample by sample, which is what made the per-tick gravity visible.
- Fixed: `gateSetLabel` formatted `"set %d"` with no argument, reading a
  missing vararg whenever an unnamed gate set was shown on the overlay.
- Documented: 23 further sites in the player state handlers (knockback and
  special moves) that make the same mistake and are left unpatched.

**dev 1.2.0**
- Fixed: Amaterasu's jog and run were roughly twice as fast in 60 fps mode
  while the top dash stage was correct, so the flower dash was slower than a
  plain run. The port scales the dash target by `timeScale` and misses the
  other two; the patch now scales the run target the same way and converts
  the jog's acceleration, damping, target, dash-charge threshold and charge
  frame count. Measured against 30 fps: 126/162/207 against 123/158/206
  units per second.
- Fixed: the run, jog and dash animation playback rates are kept at their
  30 fps values, so the leg cycle matches the ground speed.
- Changed: the game starts in 60 fps mode again, now that movement is real
  time there. The interface layer is still faster than stock.
- Changed: the movement fixes are independent of the experimental `Fixes`
  toggle and have their own key (**F8**), so they cannot be switched off by
  accident.
- Added: an optional on-screen overlay (`Overlay=1`) showing the mode, the
  movement fix state, live walking speed and the active gate set.
- Added: diagnostics used to find the bug and kept for the interface work
  still outstanding: call-site and function probes, gate sets cycled
  in-game, log marks, byte watches and caller traces.
- Added: task and virtual-slot gating for the interface classes
  (`FixMenus`, `FixHud`, `FixEffects`), off by default and unproven.

**dev 1.1.0**
- Changed: the game starts in stock 30 fps mode; 60 fps mode is opt-in and
  documented as double-speed gameplay (the engine's 60 fps configuration
  does not slow down the game logic). The previous README's claim that
  movement and combat behave correctly at 60 fps did not hold up in testing.
- Fixed: 30 fps mode no longer forces the mode byte to 2 every 50 ms; the
  stock game uses its 60 fps configuration itself during the title sequence.
- Fixed: the watcher thread stopped after 10 minutes, taking the hotkey, the
  mode-byte safety net and swap chain re-hooking with it.
- Fixed: hooking through layered swap chain proxies (ReShade, NVIDIA
  NvPresent64) crashed the game or paced it twice (30 ticks/s at "60 fps").
  The hook now keeps a per-vtable table of originals and paces once per
  frame.
- Fixed: the hotkey read `GetAsyncKeyState`'s unreliable "pressed since last
  call" bit; it now edge-detects the real key state and, by default, only
  fires while the game is focused.
- Improved: frame pacing uses a high-resolution waitable timer and a
  drift-free 60 Hz grid instead of `Sleep()` at the default 15.6 ms timer
  resolution (a source of uneven 55-58 fps and stutter).
- Improved: engine symbols resolved by export name; mode byte, writer sites
  and swap chain global located by code scanning and verified before
  patching. Found 11 mode-writer sites; the previous release patched 4.
- Added: `okami.ini` settings, log diagnostics (swap chain, present layers,
  exceptions), `ProxyDll` chaining, Steam-library auto-detection in the
  tools, clang and MSVC build presets.

**dev 1.0.0** - Enaium's original patch: the 60 fps unlock and the F9 30/60 toggle.

License: MIT (see LICENSE).
