#!/usr/bin/env python3
"""Generate the first world-animation family: what was still seen running fast
at 120 fps on 2026-09-23 -- the villagers' animation, their emotion bubbles
and the black wind in the sky.

Twelve groups, each read from the code and each behind its own ini key:

  sky    objScroll's UV scroll (35D5B0): every tick each material's U and V
         offset gain (signed byte from the placement data) x 0.001 x (1 or
         0.1), wrapped to +-1. The scrolling layers of the sky, clouds and
         water are objScroll models, so all of them ran 4x at 120.
  swing  the swinging-bone step (1BA350, and its sibling 1BAA20), called by
         about 100 functions, most of them villagers' (hm*) updates: sleeves,
         hair, sashes. A Verlet step whose velocity is a displacement per
         tick. The port scaled its gravity by the time scale once (it needs
         ts^2), left the wind push unscaled (needs s^2) and the velocity's
         per-tick damping (needs f^s). At 120 the pendulum had 4x the gravity
         in real time (2x the swing frequency), 16x the wind and damping
         applied four times per stock tick.
  human  cHuman's own clocks: the talk head-bob (3043C0: an additive keyframe
         animation on the head, frame +1 a tick, weight +1 in and -0.2 out a
         tick) and the mood-particle spawner (30EB40: while a villager plays
         its mood idle, it spawns its effect set 100 every 4-7 ticks).
  effect the effect engine's shared particle step (1928F0) and espBase's
         slots 9-15, which almost every effect class inherits, and what the
         classes seen running add in their own step (esp20's model UV scroll,
         esp08/40's UV offsets, the strips' scroll, esp25/12/13's progress,
         esp31's phase): age, fade
         window, velocity += acceleration, spin, keyframe index, spawn delay,
         flipbook, scale growth and its wobble, rotation, position += velocity
         and its turbulence, drag. Rates (velocity, scale rate, turbulence
         rate and amplitude) keep stock's values: they change once per stock
         period, on the tick that puts them where stock's order does (after
         their use for velocity and scale rate, before it for turbulence).
         What integrates them (position, scale, phases) moves every tick by
         s of the rate, so it passes through stock's values at every stock
         tick and moves in straight lines between them.
  turn   the two "turn toward" helpers every walker and enemy steers with,
         20E210 (toward a point) and 20E290 (toward an angle): the heading
         moves by at most a limit a tick, and all 454 calls pass that limit
         in stock units (docs/animation/turn_limits.csv, from
         tools/survey_turn_limits.py): so they turned 4x as fast at 120.
  emitter the emitters' two ages (195A20, 1952F0): how long they wait, live
         and emit; and, for the free emitters (data flag 0x80), their own
         motion in vtable slots 6-9: spin, position offsets, free flight and
         the countdown to leaving their parent. Their spawn interval is phase_steps.h's already, except a
         reload below one tick, raised to one here (1950D0).
  scenery the sway of trees, bushes and the other placed scenery: cKihonObj
         (every cKiType* and most vt* classes, 122 in all, through its
         update 207760), cEnemyObj, vt2b, vt16 and vt21 keep a phase
         counter (+1112, seeded at random) that gains 1 a tick; 20A460 (or
         the class's copy) turns it into a sway angle, sin(+1110 x phase
         deg), and a scale pulse, sin(4 x phase deg), and the vt* sways
         that add the frame counter (frame_phases.h's already) add it too.
         Integers step on stock ticks, as F1: the phase and the hit
         cooldowns (+11A8, and cEnemyObj's +1298/+1299).
  objects what objects animate in their own update: wp20 (the reflector, a
         weapon Amaterasu carries) scrolls three materials' U and pulses
         their colour by constant steps; an item pickup (cItemObj) fades its
         alpha and a second fraction in by steps of 0.1 a tick.
  mode   F6: the port's own compensation through the mode byte,
         "a step times the mode" or "n / mode" (the byte is 2 at 30 fps and 1
         at 60), which is right at 30 and 60 and 2x at 120, where the patch
         keeps the byte at 1. Every read of the byte was classified
         (docs/animation/mode_reads.csv); these are the ones nothing else
         covers: the event camera's playhead (the time-lapses run on it), the
         play-time clock, the HUD timer's count and pulse, the control
         window's pulse, how long a pad input has been held, the layout
         flipbook's parity gate, the memory card's waits and the options
         sliders. This group's N is fps / 60 while the real byte reads 1 (2
         at 120, 1 at 60 and in the stock 30 fps mode): at 120 each runs
         exactly as the port runs it at 60, which is stock's real-time rate.
  repeat the held-direction repeat of the menus (13F410, hxNavigation, and
         1843A0): a byte counter is reloaded with 4 when it fires and loses
         `mode` a tick otherwise, so stock repeats 10 times a second in a 30
         Hz context and 12 in the 60 Hz menus, and the patch 24 at 120. With
         the stock context's N, the counter loses the stock context's mode
         on stock ticks only, and between them its test reads "not yet"
         (fire bits cleared, as stock clears them on a tick that does not
         fire): stock's repeat rate in each context.

  actor  the enemies' own clocks (tools/find_actor_clocks.py): every em* class
         keeps its speed in +1080 (1.0, less while slowed) and counts its
         state timers in its own time, field -= speed (or += speed x its
         motion factor +F54) a tick: wind-ups, stuns, how long it hides. The
         finder proves each read-modify-write; the speed (src) or the step
         (dst) is scaled by s, so each state lasts its stock time. And every
         other step an enemy paces by its speed alone (Steps: a spin or bob
         phase, a hover, a fade, a timer on a sub-object): the speed as read
         (step), when its value is on every path only one field's step.
         And its motion (tools/find_actor_motion.py): the speed as read
         (step) where it only moves something, through the kernel's vectors
         (tools/vec_flow.py): the model by its matrix (2DA3F0, or Apply on a
         child model), forward (2DA410), a fall (20EA30/20ED50: position.y +=
         dt * vy, vy -= g * dt, dt the speed), a piece's position += its
         velocity * speed. A velocity that changes every tick (the pieces'
         acceleration, pull toward a joint, damping) changes once per stock
         period, as the effect group's particles do: zfirst/zlast on the
         change's scalar, ufirst/ulast on a damping factor, placed by stock's
         order around the move that uses the velocity.

  steer  the turn steps (tools/survey_turn_steps.py): the clamped angle to a
         point (2DDF90) and the clamped approach (2DA570), the enemies'
         "turn toward Amaterasu at rate x speed" (23A2E0) and the other
         callers turning a heading or a joint by them every tick with a limit
         in stock units. Their calls' rel32 point at stubs that scale the
         limit (callscale), and for 2DA570 make the per-tick blend k into
         1 - (1 - k)^(1/N) (callblend), then jump on.

  flag   the port's other 60 fps quantities (tools/survey_flag_reads.py): a
         length written `n << (the 60 fps flag)` (n stock ticks, 2n at 60,
         so half the time at 120, where the flag stays 1). Every rumble's
         length and delay go to cPad::ActSet that way, and cPad::Actuater
         (1825A0) counts them down once a tick: it runs on the port's 60 Hz
         ticks only (gatefn). The screen fade's length (1 << flag) x n is
         multiplied by N where it is set (mulflag). The fps byte's
         half-second waits in the options and memory-card screens, `fps / 2`
         ticks counted down once a tick: the value stored times N
         (mulstore). N is the mode group's: fps / 60 while the mode byte
         reads 1.

  skip   the skip prompt's window (13A7D0, the check behind the event skip,
         the movie skip and the event camera sequencer): once armed, it
         drops the prompt after 150 calls without a second press, 5 s at 30
         where it is called once a tick. The event skip (3F25F0), the movie
         skip (135B00) and 3F1830's poll call it every tick, 1.25 s at 120:
         their calls answer "no" between stock ticks (callgate), so it runs
         once a stock tick for each, as at 30. The sequencer's own check
         (4A0B45) already runs once a stock tick: every loop that calls it
         passes once a stock tick (task_waits.h). The skip latch
         (task_waits.h) keeps the presses of the ticks between.

  player Amaterasu's own update (pl00, 3A9630) and her weapons' pieces (wp*):
         what the movement fixes and the other families do not cover, read
         site by site: her countdowns
         and item timers, her alpha near the camera, the slide off something
         she lands on, her pitch on slopes, the rosary beads' flights. Its
         stock context is the world's (30 Hz), as the actor group's.

  menu   the sub-screens' list (cSSScroll, the Files menus' story and
         technique lists): a one-row scroll moves the rows by a spacing / 3
         a tick for 4 ticks (4111D0, 4113A0: a count the port never
         changes), and opening and closing a list fades it over 20 ticks
         and slides its rows 50 a tick (410540, 411570). Stock runs them
         in a 60 Hz context, so they ran 2x at 120; each whole function
         runs on stock ticks only (the stock context's N). The cursor's
         move (411C40) reads the pad's press and stays per tick.

Kinds (each proven against the binary before it is emitted):

  lin    `op xmm, [rip+K]`, 8 bytes: the displacement points at a pool slot
         holding K*s, s = 1/N the share of a stock tick one tick is worth.
  sq     the same with K*s^2: a push added to a per-tick displacement.
  blend  the same with 1 - (1 - K)^s, 0 < K < 1: the factor of a per-tick
         approach, x += (target - x) x K, toward a target the step does not
         move. The runtime takes the root as `root` does, one square root per
         halving (N = 2, 4), so it and the verifier agree bit for bit.
  src    `op xmmD, src` whose source is this tick's step: a detour runs
         `movaps/movss xmmT, src; mulss xmmT, [s]; op xmmD, xmmT`, xmmT a
         volatile register proven dead after the site on every path.
  dst    an instruction whose result is only this tick's step, and whose
         next reader accumulates it: the detour scales it right after.
         With extra ("slowmo", call): `movaps xmmD, xmm0` keeping the game's
         slow-motion factor (23AD90's 0.25 or 1.0) in a callee-saved register
         as a weapon function's dt; the manifest has read every reader of
         xmmD in the function, each a per-tick step, so the copy is scaled.
  dstn   an instruction whose result is this tick's step, made inside a loop
         task_waits.h runs once a stock tick (extra: the address of that
         loop's wait call), and only stored: the detour divides the result by
         s right after (x N; s is a power of two, so it is exact), so each
         pass uses a stock tick's step. The wait must be one task_waits.h
         takes over as a loop, the site and the wait must lie on one cycle,
         and the register must be dead after the store.
  pre    `addss xmmD, x` where xmmD holds this tick's step (the manifest
         says why): the detour scales xmmD first. addss is commutative.
  root   an instruction leaving a per-tick factor f in xmmD (movaps, movss or
         addss): the detour then takes f^(1/N) by one sqrtss per halving
         (N = 2, 4), and only for f > 0 (anything else is left as the game
         computed it). The flags must be dead after the site.
  blendr the same for the factor k of a per-tick approach, x += (target - x)
         x k, computed at run time: at N > 1 and 0 < k < 1 the detour makes it
         1 - (1 - k)^(1/N) (blend's value, by root's chain on 1 - k in a
         volatile register proven dead after the site). Flags dead after.
  srcblend  `mulss xmmD, src` whose source holds the factor k of a per-tick
         approach, x += (target - x) x k, in a register (or m32) that other
         code reads too: the detour copies k to a volatile register proven dead
         after the site, makes it blend's value there (at N > 1 and 0 < k < 1:
         -k + 1, the root chain, -r + 1, the same float steps as 1 - k and
         1 - r) and multiplies by the copy. The source keeps k; flags dead after.
  immstore  `mov m32, imm32` whose immediate bits are a finite float K: a
         detour loads K from its own embedded bytes, multiplies it by s in a
         volatile xmm register proven dead after the store, and writes K*s to
         the original destination. Integer flags and every live register stay
         as the original leaves them.
  zfirst, zlast   an instruction whose result is this tick's change to a
         rate (a velocity's acceleration, a growth step): the result is kept
         on the first (zfirst) or last (zlast) tick of each stock period and
         zeroed on the others, so the rate changes once per stock tick,
         exactly as stock's does.
  ufirst, ulast   the same for a per-tick factor on a rate (drag, decay):
         kept on the first or last tick, 1.0 on the others.
  countlast   a factor applied to a rate by `mulss/divss xmmD, m32`, or a change
         added to it by `addss/subss xmmD, m32`: skipped except on the last
         tick of each stock period, with F1's counters.
  argscale   `movaps xmmD, xmmS` copying a per-tick limit argument into a
         callee-saved register that the function only copies out of until its
         epilogue restores it: the copy is scaled by s.
  scaledadd  a call or import tail-jump to cVec::operator+= (dst.xyz +=
         src.xyz, w kept, as flower_kernel does it) that moves something by
         this tick's velocity: replaced by dst.xyz += s * src.xyz, w kept.
         A tail-jump replacement returns directly to its caller. At s = 1
         it is the same addition, bit for bit.
  floor1 at the join after a countdown's reload, while N > 1: the reloaded
         float at [base + disp] is raised to at least 1.0. Stock counts it
         down by 1 a tick and fires at <= 0, so any reload up to 1 is a
         period of one tick; counted down by s, a reload of 0 would fire every
         tick. Every path into the join must come from the reload block.
  gatefn a whole update function that runs only on stock ticks: exact stock
         cadence. Its callers must not use a return value.
  gate0  the same for a vtable slot whose callers read al: between stock
         ticks it returns eax = 0, what its own no-op path returns.
  count  an integer counter step skipped between stock ticks, exactly as F1
         (gen_integer_skips.emit_gate) with this group's mask.
         A register step names (load, store, path, None); an optional fifth
         element, -1 or +1, records the direction when the unit is a register
         initialized in the function. The same-field path proof still applies.
         With extra "factor", a `mulss xmm, m32` damping that runs before the
         movement is kept on the first stock-period tick and skipped on the
         others, preserving the velocity used throughout that period.
  dstarg `movss xmmN, m32`, one component of this tick's step vector, which
         goes straight into cVec(x, y, z, w): scaled right after the load.
  srcx   `addss/subss xmmD, src` whose source is this tick's step, with no
         register to spare: the detour runs `divss xmmD, [s]; op xmmD, src;
         mulss xmmD, [s]`. s = 1/N is a power of two, so both scalings are
         exact and the result is xmmD op s*src rounded once, the same bits as
         src's scaled copy would give; at N = 1 it is the original. Also
         `comiss/ucomiss xmmD, src`, a test of this tick's step against a
         limit in stock units: xmmD / s is compared with src (the flags of
         xmmD against s*src), and mulss, which leaves the flags, restores it.
  step   an instruction reading an enemy's speed (movss/movups/movaps or mulss
         from +1080) whose value is only this tick's step of one field, on
         every path (find_actor_clocks.Steps re-proves it), or only a move
         (find_actor_motion.Motion): scaled right after, as dst.
  mulstore  `mov dword [B + d], r32` storing a wait (tools/survey_flag_reads.py
         names it) whose r32 is, on the straight line from the read the
         manifest names, `movzx r32, byte [the fps byte]` then `shr r32, 1`
         (prove_mulstore): the stub stores r32 x N and keeps r32 (push r64;
         imul r32, dword [N]; the store; pop r64), so what the code does with
         the register afterwards (a setter returns it, and a state handler's
         return may be its dispatcher's status) sees the stock value. The
         flags are dead after the store.
  callscale, callblend   a call's rel32 retargeted at its own stub (no
         window): the stub counts the pass, multiplies the limit register by s
         (callblend: then, at N > 1 and 0 < k < 1, k = 1 - (1 - k)^(1/N) by
         the root chain on xmm4 and xmm5, volatile and no argument of 2DA570,
         merged into k's low lane) and
         jumps to the call's target, so the return address is the caller's.
         Flags are dead at a call.
  mulflag  `imul r32, r32` whose one factor is 1 << the 60 fps flag, built in
         the straight-line code before it (prove_mulflag): the product, a
         length in the port's 60 fps ticks, is multiplied by N right after
         (imul r32, [N]). The flags must be dead after it.
  callgate  a call of a function returning a yes/no answer in al, retargeted
         at a stub that runs F1's counted gate: between stock ticks it
         returns al = 0 ("no") at once (xor eax, eax; ret), otherwise it jumps
         on to the function. The caller's first read of rax must be `test al,
         al` or `movzx r32, al`, before any branch (prove_callgate). With
         extra (target, "void"): a call of an update whose rax that call's
         caller never reads (on every path until it is rewritten), so the
         update runs once a stock tick from that call only.
  count2 count, gated on the frame counter's bits from 1 up: it runs on ticks
         with ((fc >> 1) & (N-1)) == 0. For a step the port itself runs only
         on ticks of one parity (fc & 1): together, once every 2N ticks.
  notyet a countdown's test (`test al, al`; or `test al/m8, imm`, a counter's
         every-8th-tick bits; or `cmp` read by je/jne, a count-up's tick an
         event plays on) whose conditional branch fires it:
         between stock ticks the test is skipped and ZF, SF and OF are
         cleared, "above zero", so the branch takes the manifest's not-yet
         path. Its one flag consumer must be that branch.
  notyetneg a signed limit test with a negative not-yet path. Between stock
         ticks ZF and OF are cleared and SF is set: "below the limit". The
         next JL/JLE takes the declared path, or a JGE/JG falls through to it
         (1C8D80's `cmp eax, 10; jge close`), and both successors must
         overwrite these flags.
  notyetb an unsigned limit test (`cmp` read by JB/JBE/JAE/JA): between stock
         ticks the test is skipped with ZF = SF = OF = 0 and CF = 1, "below";
         JB/JBE take, JAE/JA fall through to, the declared path (the slot-8
         effect spawners' `cmp al, 2; jb`). Both successors must overwrite
         these flags.
  smode  `sub r8, [mode byte]` in a count gate: on stock ticks at N > 1 it
         subtracts the stock context's mode (the shadow byte, copied to
         [8g+2]) instead of the pinned real one; at N = 1 it is the original.
  imuln  `div r32` by the mode byte (its divisor loaded from it in the same
         run of code): the quotient, a duration in ticks, is multiplied by N
         right after (`imul eax, [N]`). The flags must be dead after it.

Every stub also counts its passes in a probe dword (inside pushfq/popfq), so
the log can say how often each site runs in the game.

Pool layout: group g's stock-tick mask (0/1/3, as F1) at [8g], the same mask
shifted left once (count2) at [8g+1], the stock context's mode (smode) at
[8g+2] and s at [8g+4], for up to 16 groups; 0.0 at [0x80] for the roots and
1.0 at [0x84]; each group's N as a dword at [0xC0 + 4g] (imuln); counters
{ticks, counted, last tick, passes} for the counted sites from [0x100] (2048);
literal slots from [0x8100] (512), one per constant, kind and group; probes from
[0x8900] (4096); code from 0xC900. At N = 1
(30 fps, F9, the phase key muted, a group off) every stub is the original
code.

    .venv/Scripts/python tools/gen_world_anims.py
"""
import collections
import csv
import math
import os
import re
import struct

from capstone import x86_const as X

import gen_tracer as tr
import gen_integer_skips as gis
import gen_menu_transitions as gmt

ROOT = tr.ROOT
DOCS = os.path.join(ROOT, "docs", "animation")
OUT_H = os.path.join(ROOT, "src", "world_anims.h")
OUT_CSV = os.path.join(DOCS, "world_anims.csv")
AUDITED_MAIN_SHA1 = "703d292ab2cb50cc9e237e44722dec51d956b79c"

GROUPS = ("sky", "swing", "human", "effect", "emitter", "turn", "scenery", "objects", "mode",
          "repeat", "actor", "menu", "steer", "flag", "skip", "player")
MAX_GROUPS = 16
GROUP_STRIDE, ZERO_OFFSET, INTN_OFFSET = 8, 0x80, 0xC0
COUNTER_OFFSET, SLOT = 0x100, 16
LITERAL_OFFSET, PROBE_OFFSET, CODE_OFFSET = 0x8100, 0x8900, 0xC900
MAX_COUNTERS = (LITERAL_OFFSET - COUNTER_OFFSET) // SLOT
MAX_LITERALS = (PROBE_OFFSET - LITERAL_OFFSET) // 4
MAX_PROBES = (CODE_OFFSET - PROBE_OFFSET) // 4
KIND = {"lin": 0, "sq": 1, "src": 2, "dst": 3, "pre": 4, "root": 5, "gatefn": 6,
        "count": 7, "gate0": 8, "dstarg": 9, "zfirst": 10, "zlast": 11, "ufirst": 12,
        "ulast": 13, "countlast": 14, "floor1": 15, "scaledadd": 16, "argscale": 17,
        "count2": 18, "notyet": 19, "smode": 20, "imuln": 21, "srcx": 22, "step": 23,
        "callscale": 24, "callblend": 25, "mulflag": 26, "callgate": 27, "mulstore": 28,
        "blend": 29, "blendr": 30, "srcblend": 31, "immstore": 32,
        "srcroot": 33, "notyetneg": 34, "notyetb": 35,
        "dstn": 36}
CALL_KINDS = ("callscale", "callblend", "callgate")
# kinds with F1's {ticks, counted, last, passes}
COUNTED = ("gatefn", "count", "gate0", "countlast", "count2", "notyet", "notyetneg", "notyetb",
           "smode", "callgate")
ONE_OFFSET = ZERO_OFFSET + 4   # float 1.0
MODE_BYTE = tr.MODE_BYTE
# pushfq; and dword [rsp], ~(OF|SF|ZF); popfq: "above zero" for a signed test
NOT_YET_FLAGS = b"\x9C\x81\x24\x24\x3F\xF7\xFF\xFF\x9D"
# Preserve unrelated flags; synthesize a negative, nonzero signed result.
NOT_YET_NEG_FLAGS = b"\x9C\x81\x24\x24\x3F\xF7\xFF\xFF\x81\x0C\x24\x80\x00\x00\x00\x9D"
# notyetb: ZF = SF = OF = 0 and CF = 1, "below" for an unsigned compare
NOT_YET_BELOW_FLAGS = b"\x9C\x81\x24\x24\x3F\xF7\xFF\xFF\x81\x0C\x24\x01\x00\x00\x00\x9D"
CVEC4 = "??0cVec@math@wk@@QEAA@MMMM@Z"     # wk::math::cVec::cVec(float, float, float, float)
CVEC_ADD = "??YcVec@math@wk@@QEAAAEAV012@AEBV012@@Z"          # cVec::operator+=(const cVec&)
CVEC_MULF = "??XcVec@math@wk@@QEAAAEAV012@M@Z"                # cVec::operator*=(float)
CVEC_SCALE = "?ScaleXYZ@cVec@math@wk@@SAXAEAV123@AEBV123@M@Z"  # ScaleXYZ(out, in, float)
CVEC_TIMES = "??DcVec@math@wk@@QEBA?AV012@M@Z"                  # cVec::operator*(float) const
assert len(GROUPS) <= MAX_GROUPS and MAX_GROUPS * GROUP_STRIDE <= ZERO_OFFSET
assert ONE_OFFSET + 4 <= INTN_OFFSET and INTN_OFFSET + 4 * MAX_GROUPS <= COUNTER_OFFSET

# (group, kind, rva, instruction as capstone prints it, extra, reason)
#   lin/sq: extra = (constant rva, value)
MANIFEST = [
    # --- objScroll's UV scroll, 35D5B0 (called by its update 35B840) -------
    ("sky", "dst", 0x35D6C9, "mulss xmm1, xmm7", None,
     "objScroll UV scroll (35D5B0), each material: U(+60) += data(+14) * 0.001 * "
     "(1 or 0.1) a tick, wrapped to +-1; xmm1 is that step, added to U next"),
    ("sky", "dst", 0x35D77C, "mulss xmm1, xmm7", None,
     "objScroll UV scroll: V(+64) += data(+15) * 0.001 * (1 or 0.1) a tick, wrapped"),
    ("sky", "dst", 0x35D862, "mulss xmm0, xmm7", None,
     "objScroll UV scroll, placement flag 0x80 (every material, no wrap): U += step"),
    ("sky", "dst", 0x35D886, "mulss xmm0, xmm7", None,
     "objScroll UV scroll, placement flag 0x80: V += step"),
    # --- the swinging bones, 1BA350 and 1BAA20 --------------------------------
    ("swing", "src", 0x1BA559, "subss xmm0, xmm1", None,
     "swing step (1BA350): v.y(+64) -= ts * gravity(+74) a tick; v is a "
     "displacement per tick (x += v; v = (x - x_old) * f), so gravity needs ts^2: "
     "the port's ts, and s here"),
    ("swing", "sq", 0x1BA574, "mulss xmm0, dword ptr [rip + 0x4b83b0]", (0x67292C, 0.2),
     "swing step, inside a wind field (168F50 type 6): v.xz += rotate(0, 0, "
     "rand * 0.2 + 0.5) a tick, an acceleration: K*s^2"),
    ("swing", "sq", 0x1BA58D, "addss xmm0, dword ptr [rip + 0x4b7873]", (0x671E08, 0.5),
     "the same wind push's constant term"),
    ("swing", "root", 0x1BA9D1, "movaps xmm2, xmm0", None,
     "swing step: v(+60) = (x - x_old) * (rand * 0.1 + damping(+78), 0.8) a tick, "
     "passed to cVec::Scale in xmm2: the factor per tick is f^s"),
    ("swing", "src", 0x1BABF1, "subss xmm0, xmm1", None,
     "swing step (1BAA20, the sibling): v.y -= ts * gravity, as 1BA559"),
    ("swing", "sq", 0x1BAC14, "mulss xmm0, dword ptr [rip + 0x4b7d10]", (0x67292C, 0.2),
     "1BAA20's wind push, as 1BA574"),
    ("swing", "sq", 0x1BAC2D, "addss xmm0, dword ptr [rip + 0x4b71d3]", (0x671E08, 0.5),
     "1BAA20's wind push, as 1BA58D"),
    ("swing", "root", 0x1BAF31, "movaps xmm2, xmm0", None,
     "1BAA20's damping, as 1BA9D1"),
    # --- cHuman ------------------------------------------------------------------
    ("human", "pre", 0x304464, "addss xmm0, dword ptr [rdi + 0x12f0]", None,
     "talk head-bob (3043C0, every tick from the human update 305840): weight(+12F0) "
     "+= 1 while the speaking flag (+11FC bit 31) is set, -0.2 otherwise, then "
     "clamped to [0, 1]; xmm0 is that step (both paths join here)"),
    ("human", "src", 0x3045E6, "addss xmm1, xmm9", None,
     "talk head-bob: frame(+12EC) += 1 a tick while the weight is up, wrapped at the "
     "keyframe track's length; the head's scale and rotation are sampled at it "
     "(4B9690 interpolates between keys)"),
    ("human", "count", 0x304A59, "inc ax",
     (0x304A48, 0x304A5C, (0x304A48, 0x304A4F, 0x304A54, 0x304A57, 0x304A59), None),
     "waypoint follower (3049D0): ticks since the last waypoint(+1272) += 1 a tick, "
     "up to 210; past 30 they raise the turn limit, so a villager stuck against "
     "something turns harder"),
    ("human", "gatefn", 0x30EB40, "push rbx", None,
     "mood particles (30EB40, from 305840): while a villager plays its mood idle "
     "(motion table +F0) or flag +11EF, a countdown(+1277) spawns its effect set 100 "
     "and reloads 4-7. Skipping only the decrement would still fire on the tick "
     "after, 13% too often: the whole function runs on stock ticks"),
    ("human", "gatefn", 0x304190, "push rbx", None,
     "a villager's shadow fade (304190): +1224 += 0x11 a tick up to 255, or -= 8 or "
     "0x22 down to 0; a byte, so the whole function runs on stock ticks"),
    ("human", "gatefn", 0x303F00, "push rbx", None,
     "a villager's fade (303F00): +1221 += or -= 0x11 a tick between 0 and 255; the "
     "whole function runs on stock ticks"),
    # --- turning toward something: 454 calls, all passing a stock per-tick limit
    ("turn", "argscale", 0x20E230, "movaps xmm6, xmm2", None,
     "turn toward a point (20E210, 439 calls): heading(+B4) += clamp(angle to the point, "
     "-limit, limit) a tick; the limit is copied to xmm6, used only as the clamp bound"),
    ("turn", "argscale", 0x20E2A6, "movaps xmm6, xmm2", None,
     "turn toward an angle (20E290, 15 calls): the same clamp, the limit in xmm6"),
    # --- scenery sway: a phase counter per object, +1 a tick ----------------------
    # 20A460 (called each tick from 207760 while flag 0x80 is set): phase =
    # (u16)+1112 % 360; rotation z(+B8) = sin(+1110 * phase deg) * +1111 * k,
    # scale(+C0..C8) = base(+10F0..F8) * (1 + sin(4 * phase deg) * +10FC).
    # The counter is seeded at random in 207DC0 and otherwise only counted.
    ("scenery", "count", 0x20786F, "inc word ptr [rbx + 0x1112]", None,
     "sway phase (cKihonObj's update 207760: every cKiType* and most vt* scenery, 122 "
     "classes): +1112 += 1 a tick; 20A460 makes the sway angle and scale pulse of it"),
    ("scenery", "count", 0x3404CD, "inc word ptr [rdi + 0x1112]", None,
     "cEnemyObj's update (340440): the same sway phase, its formula inline"),
    ("scenery", "count", 0x36D63C, "inc word ptr [rdi + 0x1112]", None,
     "vt2b's update (36D5C0): the same sway phase"),
    ("scenery", "count", 0x370B7C, "inc word ptr [rdi + 0x1112]", None,
     "vt16/vt21's update (370A90): the same sway phase"),
    ("scenery", "count", 0x206A7C, "dec dl",
     (0x206A4B, 0x206A7E, (0x206A4B, 0x206A52, 0x206A58, 0x206A60, 0x206A68, 0x206A70,
                           0x206A78, 0x206A7A, 0x206A7C), None),
     "cKihonObj's reaction cooldown (206A10): +11A8 -= 1 a tick while not 0; a reaction "
     "sets it to 65 ticks and none starts before it is 0"),
    ("scenery", "count", 0x340501, "dec al",
     (0x3404D4, 0x340503, (0x3404D4, 0x3404DB, 0x3404E4, 0x3404ED, 0x3404F6, 0x3404FD,
                           0x3404FF, 0x340501), None),
     "cEnemyObj's cooldown +1298: -= 1 a tick while not 0"),
    ("scenery", "count", 0x340514, "dec al",
     (0x340509, 0x340516, (0x340509, 0x340510, 0x340512, 0x340514), None),
     "cEnemyObj's cooldown +1299: -= 1 a tick while not 0"),
    # --- objects' own animation ------------------------------------------------
    ("objects", "lin", 0x39325C, "movss xmm7, dword ptr [rip + 0x2e69cc]", (0x679C30, 0.02),
     "wp20 (393210), model 620: materials 0-2's U(+60) += 0.02 a tick, wrapped at 1: the "
     "reflector's flowing texture"),
    ("objects", "lin", 0x3932F3, "movss xmm2, dword ptr [rip + 0x2deb09]", (0x671E04, 0.1),
     "wp20, model 620: the glow's colour(+50..58) -= 0.1 a tick down to 0.6, then up"),
    ("objects", "lin", 0x39333B, "movss xmm2, dword ptr [rip + 0x2deac1]", (0x671E04, 0.1),
     "wp20, model 620: the glow's colour += 0.1 a tick up to 2.0, then down"),
    ("objects", "src", 0x497C95, "addss xmm1, dword ptr [rcx + 0x11dc]", None,
     "item pickup (cItemObj, 497C70): alpha(+11E0, copied to +D2C) += rate(+11DC) a tick, "
     "clamped to [0, 1]; the rate is set to 0.1 after each step"),
    ("objects", "lin", 0x497D7F, "movss xmm1, dword ptr [rip + 0x1e02f5]", (0x67807C, -0.1),
     "item pickup (497D60): +11D4 -= 0.1 a tick in state 1/10, clamped to [0.7, 1]"),
    ("objects", "lin", 0x497D89, "movss xmm1, dword ptr [rip + 0x1da073]", (0x671E04, 0.1),
     "item pickup (497D60): +11D4 += 0.1 a tick otherwise, clamped to [0.7, 1]"),
    ("objects", "count", 0x3D1D34, "mov byte ptr [rdi + 0x1070], al", None,
     "the player's weapon (plwp and the wp* it draws, 3D1CB0, once a tick): its fade byte "
     "+1070 -= 10 a tick down to 0 while hidden, and its alpha +D2C = the owner's x "
     "+1070 / 255 right after: the byte's store is skipped between stock ticks, so it "
     "fades at stock's 10 a stock tick"),
    ("objects", "count", 0x3D1D49, "mov byte ptr [rdi + 0x1070], al", None,
     "the same fade byte += 10 a tick up to 255 while shown"),
    ("objects", "gatefn", 0x2DC3B0, "test cl, cl", None,
     "an object's alpha fade (2DC3B0, 68 calls from 61 object updates: scenery, animals, "
     "enemies): alpha byte(+D78) lerps toward a target set by distance or state, by a "
     "factor a tick with a minimum step, truncated to a byte. A lerp's factor cannot be "
     "taken to the 1/N power on a byte (it would stall short of the target): the whole "
     "function runs on stock ticks"),
    # --- the effect engine: espBase's shared step and slots 9-15 -----------------
    # Every effect class ends its slot 1 in the shared step 1928F0, and almost
    # all inherit slots 9-15. Velocity(+160) is a displacement per stock tick,
    # acceleration(+170) its change per stock tick: pos += vel*s, vel += acc*s.
    ("effect", "count", 0x1928F6, "inc word ptr [rcx + 0x260]", None,
     "particle age (the shared step 1928F0): age(+260) += 1 a tick; the particle "
     "dies once its lifetime(+262) <= age"),
    ("effect", "count", 0x1A214D, "mov dword ptr [rsi + 0x308], eax", None,
     "esp10's grow-in (1A20A0): while +308 < its length, +308 = +308 + 1 a tick and the "
     "chain grows to +308 / length of itself; the count's store is skipped between stock "
     "ticks (the register it was incremented in gives the same fraction as the last stock "
     "tick's until the next), so it grows as stock does"),
    ("effect", "count", 0x1A3130, "mov dword ptr [rdi + 0x308], eax", None,
     "esp13's grow-in (1A30C0): the same count"),
    ("effect", "count", 0x19292C, "inc byte ptr [rcx + 0x277]", None,
     "the fade-out window: +277 += 1 a tick; the particle dies at +276"),
    ("effect", "zlast", 0x192974, "movss xmm0, dword ptr [rbx + 0x170]", None,
     "velocity(+160) += acceleration(+170) a tick (1928F0), x, after the position "
     "used it in slot 14: on the last tick of each stock period"),
    ("effect", "zlast", 0x192987, "movss xmm1, dword ptr [rbx + 0x174]", None,
     "velocity += acceleration, y"),
    ("effect", "zlast", 0x1929A2, "movss xmm0, dword ptr [rbx + 0x178]", None,
     "velocity += acceleration, z"),
    ("effect", "lin", 0x1929EA, "mulss xmm0, dword ptr [rip + 0x4e4bfa]", (0x6775EC, 1 / 90),
     "spin(+27C) += data byte(+295) / 90 a tick, through the angle wrap"),
    ("effect", "gate0", 0x18FF60, "sub rsp, 0x28", 0x18FFAC,
     "keyframe index (slot 9, 18FF60): key(+264) += 1 a tick; once the OLD index "
     "reaches its count(+266) it loops, holds or kills. Skipping only the increment "
     "would end the last key 3 ticks early at /4: it runs on stock ticks only, and "
     "between them returns al = 0, what its own no-op path (18FFAC) returns"),
    ("effect", "count", 0x190AF9, "dec al",
     (0x190AEA, 0x190AFB, (0x190AEA, 0x190AF1, 0x190AF3, 0x190AF9), None),
     "spawn delay (slot 10, 190AD0): delay(+113) -= 1 a tick; at 0 the particle "
     "attaches to its parent and appears"),
    ("effect", "count", 0x18FBE0, "dec byte ptr [rcx + 0x26d]", None,
     "flipbook (slot 11, 18FBD0): hold(+26D) -= 1 a tick; at 0 the cell(+26E) "
     "advances and the hold reloads from +26C"),
    ("effect", "src", 0x190E0D, "addss xmm2, xmm3", None,
     "scale growth mode 0 (slot 12, 190DA0): scale x += rate(+180) a tick, "
     "clamped at +184; xmm3 (the rate) is also the direction test after"),
    ("effect", "src", 0x190E4E, "addss xmm2, xmm3", None,
     "scale growth mode 0: scale y += rate(+188), clamped at +18C"),
    ("effect", "countlast", 0x190EB9, "mulss xmm0, dword ptr [rbx + 0x190]", None,
     "scale growth mode 2: rate x(+188) *= decay(+190) a tick, after the scale "
     "used it: on the last tick of each stock period"),
    ("effect", "pre", 0x190EE1, "addss xmm6, dword ptr [rbx + 0x180]", None,
     "scale growth mode 2: scale x(+180) += the rate before its decay (xmm6)"),
    ("effect", "count", 0x190EFC, "add word ptr [rbx + 0x1a0], ax", None,
     "scale growth mode 2: wobble phase x(+1A0) += +19C a tick, a short angle "
     "(2048 a turn): an integer, so it steps on stock ticks"),
    ("effect", "countlast", 0x190F9C, "mulss xmm1, dword ptr [rbx + 0x194]", None,
     "scale growth mode 2: rate y(+18C) *= decay(+194) a tick, on the last tick"),
    ("effect", "pre", 0x190FA4, "addss xmm0, xmm7", None,
     "scale growth mode 2: scale y(+184) += the rate y copied before its decay "
     "(xmm0; xmm7 is the scale)"),
    ("effect", "count", 0x190FC1, "add word ptr [rbx + 0x1a2], ax", None,
     "scale growth mode 2: wobble phase y(+1A2) += +19E a tick"),
    ("effect", "dstarg", 0x190D20, "movss xmm3, dword ptr [rbx + 0x1bc]", 0x190D3E,
     "rotation (slot 13, 190D00): rot(+50) += angular velocity(+1B4..1BC) a tick, "
     "each wrapped: z, into cVec(x, y, z, w) and AddXYZ"),
    ("effect", "dstarg", 0x190D28, "movss xmm2, dword ptr [rbx + 0x1b8]", 0x190D3E,
     "rotation, y"),
    ("effect", "dstarg", 0x190D30, "movss xmm1, dword ptr [rbx + 0x1b4]", 0x190D3E,
     "rotation, x"),
    ("effect", "dstarg", 0x19111D, "movss xmm3, dword ptr [rcx + 0x168]", 0x191153,
     "position (slot 14, 191110): pos += velocity(+160) a tick: z, into cVec(x, y, "
     "z, 1) and operator+= on the position"),
    ("effect", "dstarg", 0x191128, "movss xmm2, dword ptr [rcx + 0x164]", 0x191153,
     "position += velocity, y"),
    ("effect", "dstarg", 0x191130, "movss xmm1, dword ptr [rcx + 0x160]", 0x191153,
     "position += velocity, x"),
    ("effect", "zfirst", 0x191282, "mulss xmm0, xmm1", None,
     "turbulence (data flag 0x200000): amplitude(+294) += data short(+2B6) * "
     "0.001 a tick, before its use this tick: on the first tick of each stock "
     "period"),
    ("effect", "ufirst", 0x1912AB, "addss xmm9, xmm6", None,
     "turbulence: amplitude *= 1 + data char(+2B5) * 0.001 a tick; xmm9 is that "
     "factor: on the first tick"),
    ("effect", "ufirst", 0x1912D0, "addss xmm2, xmm6", None,
     "turbulence: phase rate(+298) *= 1 + data char(+2B4) * 0.001 a tick, before "
     "the phases use it: on the first tick"),
    ("effect", "dst", 0x1912F2, "mulss xmm0, xmm2", None,
     "turbulence: phase x(+288) += data char(+2B0) * rate a tick"),
    ("effect", "dst", 0x191316, "mulss xmm8, xmm2", None,
     "turbulence: phase y(+28C) += data char(+2B1) * rate a tick"),
    ("effect", "dst", 0x19133B, "mulss xmm7, xmm2", None,
     "turbulence: phase z(+290) += data char(+2B2) * rate a tick"),
    ("effect", "ulast", 0x1910CA, "movss xmm1, dword ptr [rbx + 0x16c]", None,
     "drag (slot 15, 191090): velocity(+160) *= drag(+16C) a tick, passed to "
     "cVec::operator*= in xmm1: on the last tick"),
    # --- what the classes add in their own step (slot 1), for those seen running
    # in the 2026-09-18 trace. Each reaches the shared step as well. ---
    ("effect", "dst", 0x1A6DBB, "movss xmm0, dword ptr [rbx + 0x2d0]", None,
     "esp20 (EFF_TEX, 1A6C60), a model's surface: its material 0's U(+60) += rate(+2D0) a "
     "tick, wrapped; flowing water and portals are the likely users"),
    ("effect", "dst", 0x1A6DD3, "movss xmm1, dword ptr [rbx + 0x2d4]", None,
     "esp20: V(+64) += rate(+2D4) a tick"),
    ("effect", "dst", 0x1A6E01, "mulss xmm0, dword ptr [rbx + 0x2d8]", None,
     "esp20: U += sin(phase +2E8) * amplitude(+2D8) a tick"),
    ("effect", "src", 0x1A6E1B, "addss xmm0, dword ptr [rbx + 0x2e0]", None,
     "esp20: phase U(+2E8) += rate(+2E0) a tick, wrapped"),
    ("effect", "dst", 0x1A6E4C, "mulss xmm0, dword ptr [rbx + 0x2dc]", None,
     "esp20: V += cos(phase +2EC) * amplitude(+2DC) a tick"),
    ("effect", "src", 0x1A6E66, "addss xmm0, dword ptr [rbx + 0x2e4]", None,
     "esp20: phase V(+2EC) += rate(+2E4) a tick, wrapped"),
    ("effect", "dst", 0x1A6F03, "movss xmm0, dword ptr [rbx + 0x30c]", None,
     "esp20: spin(+308) += rate(+30C) a tick, wrapped"),
    ("effect", "dst", 0x19FB20, "movss xmm2, dword ptr [rcx + 0x2d0]", None,
     "esp08/esp40 (19FB20): texture offset U(+2C8) += rate(+2D0) a tick, wrapped to +-2"),
    ("effect", "dst", 0x19FB30, "movss xmm0, dword ptr [rcx + 0x2d4]", None,
     "esp08/esp40: texture offset V(+2CC) += rate(+2D4) a tick"),
    ("effect", "pre", 0x1A02C0, "addss xmm0, dword ptr [rbx + 0x2ec]", None,
     "the strips' step (1A02A0: espStrip, esp38, and esp09/10/13/31/32/41 through it): "
     "scroll(+2EC) += rate(+2F0) a tick, wrapped to [0, 1); xmm0 is the rate"),
    ("effect", "dst", 0x1A8CB5, "movaps xmm1, xmm0", None,
     "esp25 (1A8C80), a model playing a motion: progress(+2F0) += rate(+2D8) a tick, "
     "and the model's frame is set from it; xmm1 is the rate's copy"),
    ("effect", "countlast", 0x1A8CC8, "addss xmm0, dword ptr [rbx + 0x2dc]", None,
     "esp25: rate(+2D8) += acceleration(+2DC) a tick, after the progress used it: on "
     "the last tick"),
    ("effect", "pre", 0x1A2978, "addss xmm0, xmm2", None,
     "esp12 (1A28F0): progress(+2D4) += rate(+2D8) a tick (it picks a colour key); xmm0 "
     "is the rate's copy, xmm2 the progress"),
    ("effect", "countlast", 0x1A2970, "addss xmm1, dword ptr [rbx + 0x2dc]", None,
     "esp12: rate(+2D8) += acceleration(+2DC) a tick, after its use: on the last tick"),
    ("effect", "dst", 0x1A31E3, "movaps xmm6, xmm1", None,
     "esp13 (1A30C0), a strip: fade(+310) += rate(+314) a tick, the strip dies at 1"),
    ("effect", "countlast", 0x1A31EE, "addss xmm1, dword ptr [rdi + 0x318]", None,
     "esp13: rate(+314) += acceleration(+318) a tick, after its use: on the last tick"),
    ("effect", "dst", 0x1AA23D, "movss xmm0, dword ptr [rdi + 0x328]", None,
     "esp31 (1AA210), a strip: phase(+338) += rate(+328) a tick, wrapped"),
    ("effect", "zlast", 0x1A407F, "movss xmm0, dword ptr [rbp - 9]", None,
     "esp17, the coins (1A3CA0), once collected: velocity(+160) += the direction to "
     "Amaterasu x speed(+2D0) a tick, after the shared step used it: on the last tick; x "
     "(the speed's own ramp reads the pinned mode byte, 60 fps's half step: 2x at 120)"),
    ("effect", "zlast", 0x1A408C, "movss xmm1, dword ptr [rbp - 5]", None,
     "esp17: velocity += direction x speed, y"),
    ("effect", "zlast", 0x1A40A1, "movss xmm0, dword ptr [rbp - 1]", None,
     "esp17: velocity += direction x speed, z"),
    ("effect", "src", 0x1A44BB, "addss xmm6, xmm8", None,
     "esp18 (1A43E0): phase(+2E8) += rate(+2EC) a tick, wrapped; +2E4 = sin(phase) x "
     "amplitude(+2E0)"),
    # --- the emitters' clocks ---------------------------------------------------
    # Their spawn interval (1950D0) is already phase_steps.h's (1951A3).
    ("emitter", "src", 0x195D6B, "addss xmm0, xmm7", None,
     "emitter age(+1A0) += 1 a tick (the update 195A20 of espEmitter, 01, 03): "
     "its start delay(+1A6) and life(+1A8) are in ticks"),
    ("emitter", "lin", 0x195D59, "addss xmm0, dword ptr [rip + 0x4dfed3]", (0x675C34, 0.25),
     "emitter age += 0.25 a tick in the game's own slow motion (23B750)"),
    ("emitter", "src", 0x195DE8, "addss xmm0, xmm7", None,
     "emission age(+248) += 1 a tick: it spawns while (short)age < duration(+244)"),
    ("emitter", "lin", 0x195DD6, "addss xmm0, dword ptr [rip + 0x4dfe56]", (0x675C34, 0.25),
     "emission age += 0.25 a tick in slow motion"),
    ("emitter", "src", 0x195411, "addss xmm1, xmm6", None,
     "espEmitter02's update (1952F0): emission age(+248) += 1 a tick"),
    ("emitter", "src", 0x195673, "addss xmm0, xmm6", None,
     "espEmitter02: emitter age(+1A0) += 1 a tick"),
    ("emitter", "lin", 0x195661, "addss xmm0, dword ptr [rip + 0x4e05cb]", (0x675C34, 0.25),
     "espEmitter02: emitter age += 0.25 a tick in slow motion"),
    ("emitter", "countlast", 0x1954DB, "addss xmm1, dword ptr [rbx + 0x258]", None,
     "espEmitter02 (1952F0): spin rate(+254) += +258 a tick, after the angle used it: on "
     "the last tick"),
    ("emitter", "pre", 0x1954E3, "addss xmm0, dword ptr [rbx + 0x250]", None,
     "espEmitter02: spawn angle(+250, about the axis it picks) += rate a tick; xmm0 is the "
     "rate's copy from before its change"),
    ("emitter", "countlast", 0x1954EB, "mulss xmm1, dword ptr [rbx + 0x25c]", None,
     "espEmitter02: spin rate *= +25C a tick, on the last tick"),
    # --- the free emitters' own motion: vtable slots 6-9, called every tick by
    # the update (195A20) once the emitter has started, for data flag 0x80 ---
    ("emitter", "ufirst", 0x194800, "movss xmm0, dword ptr [rdi + 0x1c4]", None,
     "emitter spin (slot 6, 1947A0): angular velocity x(+148) *= data(+1C4) a tick "
     "once its age passes data(+1C0), before it turns the emitter: on the first tick"),
    ("emitter", "ufirst", 0x194818, "movss xmm1, dword ptr [rdi + 0x1c8]", None,
     "emitter spin: angular velocity y(+14C) *= data(+1C8)"),
    ("emitter", "ufirst", 0x194830, "movss xmm0, dword ptr [rdi + 0x1cc]", None,
     "emitter spin: angular velocity z(+150) *= data(+1CC)"),
    ("emitter", "dstarg", 0x194891, "movss xmm3, dword ptr [rbx + 0x150]", 0x1948AF,
     "emitter rotation(+50) += angular velocity a tick, each wrapped: z"),
    ("emitter", "dstarg", 0x194899, "movss xmm2, dword ptr [rbx + 0x14c]", 0x1948AF,
     "emitter rotation += angular velocity: y"),
    ("emitter", "dstarg", 0x1948A1, "movss xmm1, dword ptr [rbx + 0x148]", 0x1948AF,
     "emitter rotation += angular velocity: x"),
    ("emitter", "ufirst", 0x194642, "movss xmm1, dword ptr [rbx + 0x1c0]", None,
     "espEmitter02's spin (slot 6, 194610): angular velocity x(+148) *= data(+1C0), "
     "then += data(+1C4) * 0.001, wrapped, a tick, before it turns the emitter: on the "
     "first tick"),
    ("emitter", "ufirst", 0x19465A, "movss xmm6, dword ptr [rbx + 0x1c0]", None,
     "espEmitter02's spin: y(+14C) *= data(+1C0)"),
    ("emitter", "ufirst", 0x194672, "movss xmm9, dword ptr [rbx + 0x1c0]", None,
     "espEmitter02's spin: z(+150) *= data(+1C0)"),
    ("emitter", "zfirst", 0x194695, "mulss xmm0, dword ptr [rip + 0x4e2f47]", None,
     "espEmitter02's spin: x += data(+1C4) * 0.001"),
    ("emitter", "zfirst", 0x1946BB, "mulss xmm0, dword ptr [rip + 0x4e2f21]", None,
     "espEmitter02's spin: y += data(+1C8) * 0.001"),
    ("emitter", "zfirst", 0x1946DF, "mulss xmm0, dword ptr [rip + 0x4e2efd]", None,
     "espEmitter02's spin: z += data(+1CC) * 0.001"),
    ("emitter", "dstarg", 0x194704, "movaps xmm3, xmm0", 0x194716,
     "espEmitter02's rotation(+50) += angular velocity a tick: z, copied for cVec"),
    ("emitter", "dstarg", 0x194707, "movaps xmm1, xmm8", 0x194716,
     "espEmitter02's rotation += angular velocity: x"),
    ("emitter", "dstarg", 0x194713, "movaps xmm2, xmm6", 0x194716,
     "espEmitter02's rotation += angular velocity: y"),
    ("emitter", "dstarg", 0x194C8A, "movss xmm3, dword ptr [rax + 0x1ec]", 0x194CA2,
     "emitter offset (slot 7, 194BB0): offset(+16C) += data(+1E4) a tick while its age "
     "is in a data window; the offset is added to the emitter's position: z"),
    ("emitter", "dstarg", 0x194C92, "movss xmm2, dword ptr [rax + 0x1e8]", 0x194CA2,
     "emitter offset += data: y"),
    ("emitter", "dstarg", 0x194C9A, "movss xmm1, dword ptr [rax + 0x1e4]", 0x194CA2,
     "emitter offset += data: x"),
    ("emitter", "root", 0x194D05, "movss xmm0, dword ptr [rax + 0x1f4]", None,
     "emitter offset x *= data(+1F4) a tick once its age passes data(+1F0): the offset "
     "is shown as it is, so f^(1/N) a tick, smooth"),
    ("emitter", "root", 0x194D1D, "movss xmm1, dword ptr [rax + 0x1f8]", None,
     "emitter offset y *= data(+1F8)"),
    ("emitter", "root", 0x194D35, "movss xmm0, dword ptr [rax + 0x1fc]", None,
     "emitter offset z *= data(+1FC)"),
    ("emitter", "root", 0x194F16, "movss xmm1, dword ptr [rax + 0x224]", None,
     "emitter second offset x(+184) *= data(+224) a tick once its age passes data(+220), "
     "added to the position as it is"),
    ("emitter", "root", 0x194F2E, "movss xmm2, dword ptr [rax + 0x228]", None,
     "emitter second offset y(+188) *= data(+228)"),
    ("emitter", "root", 0x194F46, "movss xmm3, dword ptr [rax + 0x22c]", None,
     "emitter second offset z(+18C) *= data(+22C)"),
    ("emitter", "dstarg", 0x194FEE, "movss xmm3, dword ptr [rax + 0x21c]", 0x195006,
     "emitter second offset += data(+214) a tick in its age window [+200, +210): z"),
    ("emitter", "dstarg", 0x194FF6, "movss xmm2, dword ptr [rax + 0x218]", 0x195006,
     "emitter second offset += data: y"),
    ("emitter", "dstarg", 0x194FFE, "movss xmm1, dword ptr [rax + 0x214]", 0x195006,
     "emitter second offset += data: x"),
    ("emitter", "ufirst", 0x194AB8, "movss xmm2, dword ptr [rbx + 0x194]", ("scale", 0x194AD4),
     "free emitter (slot 8, 194A50): velocity(+13C) *= +194 a tick (skipped when it is "
     "0), before it moves the emitter: on the first tick"),
    ("emitter", "zfirst", 0x194AF5, "movss xmm2, dword ptr [rbx + 0x190]", ("scale", 0x194B07),
     "free emitter: velocity += its direction * +190 a tick, on the first tick"),
    ("emitter", "count", 0x194B2D, "subss xmm0, dword ptr [rbx + 0x198]", "float",
     "free emitter: velocity y -= +198 (gravity) a tick, on the first tick"),
    ("emitter", "scaledadd", 0x194B40, "call qword ptr [rip + 0x4dc2ba]", None,
     "free emitter: offset(+154) += velocity a tick by cVec::operator+=: s of it"),
    ("emitter", "ufirst", 0x194980, "movss xmm2, dword ptr [rbx + 0x194]", ("scale", 0x19499C),
     "free emitter (slot 8, 194920, espEmitter02): velocity *= +194, on the first tick"),
    ("emitter", "zfirst", 0x1949BD, "movss xmm2, dword ptr [rbx + 0x190]", ("scale", 0x1949CF),
     "free emitter (194920): velocity += direction * +190, on the first tick"),
    ("emitter", "count", 0x1949F5, "subss xmm0, dword ptr [rbx + 0x198]", "float",
     "free emitter (194920): velocity y -= +198, on the first tick"),
    ("emitter", "scaledadd", 0x194A08, "call qword ptr [rip + 0x4dc3f2]", None,
     "free emitter (194920): position(+60) += velocity a tick by cVec::operator+=: s of "
     "it"),
    ("emitter", "count", 0x1944DA, "sub ax, 2",
     (0x1944CA, 0x1944DE, (0x1944CA, 0x1944D1, 0x1944D4, 0x1944DA), None),
     "emitter detach (slot 9, 1944B0): +1AA -= 2 a tick while it has a parent(+118); "
     "at <= 0 it moves into the world frame and leaves it"),
    ("emitter", "count", 0x19432A, "sub ax, 2",
     (0x19431A, 0x19432E, (0x19431A, 0x194321, 0x194324, 0x19432A), None),
     "espEmitter02's detach (slot 9, 194300), as 1944DA"),
    ("emitter", "floor1", 0x19525E, "mov rax, qword ptr [rbx + 0x110]",
     ("rbx", 0x19C, 0x1951CC),
     "spawn interval (1950D0): the timer(+19C), counted down by phase_steps.h's "
     "scaled step (1951A3), reloads from data(+BD) plus an optional ramp, clamped "
     "at 0, plus 0.99 in slow motion. Stock fires every max(1, ceil(reload)) "
     "ticks, so a reload of 0 is one tick; counted down by s it fired every tick. "
     "The reload's three paths and the slow-motion add all join here"),
    # --- F6: the mode byte as a quantity (tools/survey_mode_reads.py) -----------
    ("mode", "dst", 0x476A12, "mulss xmm1, xmm3", None,
     "the event camera's path player (4763F0, on the event object at B661E0): "
     "playhead(+348) += mode * speed(+2D4) * 0.5 a tick, and the camera's position, "
     "target, roll and fov keys are sampled at it; xmm1 is that step, added next. The "
     "time-lapses lerp on this playhead: measured 2.0x FAST at 120"),
    ("mode", "dst", 0x476AB5, "mulss xmm1, xmm3", None,
     "the same player at the path's end, when it does not loop: playhead -= the same "
     "step (subtracted next)"),
    ("mode", "count", 0x4B668B, "add dword ptr [rcx + 0x7c], eax", None,
     "total play time ([B205C8]+7C, in flower_tick 4B63B0) += mode a tick, in 1/60 s; "
     "its one reader, the end-of-game Total Results screen, divides it by 60"),
    ("mode", "count", 0x407BB2, "sub dword ptr [rcx + 0x84], eax", "down",
     "the HUD timer counting down (cCockTimer, 407B00): +84 -= mode a tick, in 1/60 s "
     "(407C60 shows +84 / 3600 minutes, % 3600 / 60 seconds); below 0 it sets +89, "
     "which jns skips: eax is the mode byte, 1 or 2, so this is a countdown"),
    ("mode", "lin", 0x407D54, "mulss xmm0, dword ptr [rip + 0x27076c]", (0x6784C8, 0.15),
     "the HUD timer's pulse (407C60) under its warning time: phase(+78) += mode * 0.15 "
     "a tick, wrapped"),
    ("mode", "lin", 0x3FB499, "mulss xmm0, dword ptr [rip + 0x27d027]", (0x6784C8, 0.15),
     "cCockCtrlWnd's pulse (3FB410): phase(+98) += mode * 0.15 a tick, wrapped"),
    ("mode", "count", 0x1826D4, "mov dword ptr [rdi + 0x260], eax", None,
     "cPad::Actuater (1825A0): how long the rumble motors have run unchanged, +260 = +260 + "
     "mode a tick while one runs, reset when their state changes; at 1200 (20 s in 1/60 s) "
     "the pad stops being sent the rumble. On the other ticks the store is skipped"),
    ("mode", "count2", 0x1B2AC3, "inc byte ptr [r10 + 0x86]", None,
     "the 2D layout player's flipbook (1B2A50: every HUD and menu sprite sheet): hold(+86) "
     "+= 1 when mode != 1, or when (fc & 1) == the layout's phase(+2F, seeded fc & 1 by "
     "1B5380), and the cell advances past +69: 30 holds a second at 30 and at 60. At 120 "
     "the parity passes every other tick; with (fc >> 1) & (N-1) == 0 as well, once in "
     "four, whatever the phase"),
    ("mode", "imuln", 0x1C0A74, "div ecx", 0x1C0A6D,
     "memory-card screen (1C0160): +288 = 8 / mode, a wait in ticks"),
    ("mode", "imuln", 0x1C159E, "div ecx", 0x1C1597,
     "memory-card screen (1C10F0): +288 = 6 / mode, a wait in ticks"),
    ("mode", "imuln", 0x1C6415, "div ecx", 0x1C640C,
     "memory-card screen (1C6110): 1C7F90(this, 210 / mode), a duration in ticks"),
    ("mode", "imuln", 0x1C8051, "div ecx", 0x1C801F,
     "memory-card screen (1C7FE0): 210 / mode, the same duration"),
    ("mode", "count", 0x153F8B, "inc dword ptr [rbx + 0x58]", None,
     "an options slider held one way (153F30): +58 += 1 a tick, and the value(+94) moves "
     "by ((+58 / (60, or 30 by mode)) * 10 + 1) * 0.063 a tick, clamped to [1, 8]"),
    ("mode", "lin", 0x153FD4, "mulss xmm2, dword ptr [rip + 0x520f78]",
     (0x674F54, 0.06299212574958801), "that slider's step: its 0.063"),
    ("mode", "count", 0x15404B, "inc dword ptr [rbx + 0x5c]", None,
     "the same slider held the other way: +5C += 1 a tick"),
    ("mode", "lin", 0x154088, "mulss xmm0, dword ptr [rip + 0x520ec4]",
     (0x674F54, 0.06299212574958801), "its step's 0.063"),
    ("mode", "count", 0x1541BB, "inc dword ptr [rbx + 0x58]", None,
     "the second options slider (154160, value +8C, a finer step of 0.0236), held one "
     "way: +58 += 1 a tick"),
    ("mode", "lin", 0x154204, "mulss xmm2, dword ptr [rip + 0x520d44]",
     (0x674F50, 0.023622047156095505), "its step's 0.0236"),
    ("mode", "count", 0x15427B, "inc dword ptr [rbx + 0x5c]", None,
     "the second slider held the other way: +5C += 1 a tick"),
    ("mode", "lin", 0x1542B8, "mulss xmm0, dword ptr [rip + 0x520c90]",
     (0x674F50, 0.023622047156095505), "its step's 0.0236"),
    # --- the 60 fps flag as a quantity (tools/survey_flag_reads.py) -------------
    ("flag", "gatefn", 0x1825A0, "push rdi", None,
     "cPad::Actuater (1825A0, once a tick): each of the pad's 32 rumble slots counts its "
     "delay (+4) and then its length (+6) down by one a call, and the motors run while "
     "a length remains. Every length and delay is written `n << flag` (cPad::ActSet, 321 "
     "reads of the flag), in the port's 60 fps ticks: the function runs on the port's "
     "60 Hz ticks only. Its F6 count (1826D4, +260) steps on the same ticks"),
    ("flag", "mulflag", 0x3E2ACE, "imul ecx, eax", (0x3E2AA8, 0x3E2ABB),
     "the screen fade (3E2A90, a leaf; 68 callers): its length +C = (1 << flag) x n ticks, "
     "the elapsed count +E stepping up to it once a tick in 3E2B60, which lerps the "
     "colour by +E / +C: the length x N"),
    # --- the skip prompt's window: its per-tick callers -----------------------
    ("skip", "callgate", 0x3F2635, "call 0x13a7d0", (0x13A7D0, None),
     "the event skip (3F25F0, once a tick while an event can be skipped): 13A7D0 counts "
     "its window (+4) once a call and drops the prompt at 150, 5 s at 30 and 1.25 s at "
     "120; between stock ticks the call answers no"),
    ("skip", "callgate", 0x135B30, "call 0x13a7d0", (0x13A7D0, None),
     "the movie skip (135B00, once a tick while a movie plays): the same check and window"),
    ("skip", "callgate", 0x3F1B99, "call 0x13a7d0", (0x13A7D0, None),
     "3F1830's poll (a task loop yielding a tick at a time, left per tick by the task "
     "waits: 3F1C77): the same check and window, its answer kept in edi"),
    # --- the menus' held-direction repeat -------------------------------------
    ("repeat", "notyet", 0x13F675, "test al, al", 0x13F679,
     "hxNavigationController's repeat (13F410), first direction set: the counter "
     "([r13-79]) at <= 0 fires (reload 4, fire bits set), otherwise it loses mode and the "
     "bits are cleared"),
    ("repeat", "smode", 0x13F679, "sub al, byte ptr [rip + 0xa2b5c6]", None,
     "that counter -= mode, stored back next"),
    ("repeat", "notyet", 0x13F6F0, "test al, al", 0x13F6F4,
     "hxNavigationController's repeat, second set ([r13])"),
    ("repeat", "smode", 0x13F6F4, "sub al, byte ptr [rip + 0xa2b54b]", None,
     "that counter -= mode"),
    ("repeat", "notyet", 0x184BE9, "test al, al", 0x184BED,
     "the pad's repeat (1843A0), first set ([r15-79])"),
    ("repeat", "smode", 0x184BED, "sub al, byte ptr [rip + 0x9e6052]", None,
     "that counter -= mode"),
    ("repeat", "notyet", 0x184C1E, "test al, al", 0x184C22,
     "the pad's repeat, second set ([r15])"),
    ("repeat", "smode", 0x184C22, "sub al, byte ptr [rip + 0x9e601d]", None,
     "that counter -= mode"),
    # --- the sub-screens' list scroll (cSSScroll), called each tick through the
    # dispatchers 410B80 and 410F40 on the state +52; stock runs them at 60 Hz
    ("menu", "gatefn", 0x4111D0, "mov qword ptr [rsp + 8], rbx", None,
     "cSSScroll's scroll by one row, up (4111D0): every row(+24) -= spacing / 3 a tick "
     "while its count(+D0, from the global 7A90B0 = 3, which nothing writes) runs down; "
     "the rows are relinked at its end. Floats and a count together: the whole function "
     "runs on stock ticks"),
    ("menu", "gatefn", 0x4113A0, "mov qword ptr [rsp + 8], rbx", None,
     "cSSScroll's scroll by one row, down (4113A0): the same, rows += spacing / 3"),
    ("menu", "gatefn", 0x410540, "push rbx", None,
     "cSSScroll opening (410540): over 20 ticks(+D0 counted up) the list fades in on a "
     "squared curve and its header slides to place; rows 1-5 slide +50 a tick"),
    ("menu", "gatefn", 0x411570, "mov qword ptr [rsp + 0x10], rbx", None,
     "cSSScroll closing (411570): the same fade and slide out over 20 ticks, rows -50 a "
     "tick while above their target; it calls the blink 411960 (F1 counts its step on "
     "stock ticks, the same ones)"),
    # --- the imps' approach and jump kick: moves by constants, not by the speed.
    # 243630 is an action of state 2 of the imps em00..em04, em7a, em80, em81,
    # em83, em84 (the dispatch 242060, vtable +88); 2A1710 is the same action of
    # em56..em59 (from 29F500). Each tick of its runs toward a point near
    # Amaterasu (steps 1, 3, 5), pos.x/z += Normalize(point - pos).x/z * 2.5; step
    # 3 lasts +E3C = 120 ticks (a lea timer). Step 6 launches the kick once: vy
    # +E54 = 2, forward +E48 = 3. Then each tick vy += the port's time-scaled
    # rise (ts x 0.3 x speed), the imp moves forward by +E48 (2DA410: pos +=
    # M x (0, 0, d)), and +E48 *= 0.97, until it is about to land. Nothing here
    # reads the speed, so the motion finder never saw it; with the fall at its
    # stock pace the kick lasts its stock time and, unscaled, flew 2-3x as far.
    # The steps x s. The damping is decay_factors.h's already (0.97 ^ ts a
    # tick, 243B98 and 2A1C26), so +E48 decays at stock's rate in real time
    ("actor", "lin", 0x2437BD, "mulss xmm0, dword ptr [rip + 0x431c0f]", (0x6753D4, 2.5),
     "imp approach (243630 step 1): pos.x += dir.x * 2.5 a tick toward a point near "
     "Amaterasu"),
    ("actor", "lin", 0x2437E3, "mulss xmm0, dword ptr [rip + 0x431be9]", (0x6753D4, 2.5),
     "imp approach (243630 step 1): pos.z += dir.z * 2.5 a tick"),
    ("actor", "lin", 0x2438E6, "mulss xmm0, dword ptr [rip + 0x431ae6]", (0x6753D4, 2.5),
     "imp approach (243630 step 3, 120 ticks): pos.x += dir.x * 2.5 a tick"),
    ("actor", "lin", 0x24390C, "mulss xmm0, dword ptr [rip + 0x431ac0]", (0x6753D4, 2.5),
     "imp approach (243630 step 3): pos.z += dir.z * 2.5 a tick"),
    ("actor", "lin", 0x243A7C, "mulss xmm0, dword ptr [rip + 0x431950]", (0x6753D4, 2.5),
     "imp approach (243630 step 5, while its animation plays): pos.x += dir.x * 2.5"),
    ("actor", "lin", 0x243AA2, "mulss xmm0, dword ptr [rip + 0x43192a]", (0x6753D4, 2.5),
     "imp approach (243630 step 5): pos.z += dir.z * 2.5 a tick"),
    ("actor", "callscale", 0x243B85, "call 0x2da410", (0x2DA410, "xmm1"),
     "imp jump kick (243630 step 7): forward by +E48 a tick (2DA410, xmm1 = the step); "
     "+E48 *= 0.97 a tick after it is decay_factors.h's"),
    ("actor", "lin", 0x2A185B, "mulss xmm0, dword ptr [rip + 0x3d3b71]", (0x6753D4, 2.5),
     "em56..em59 approach (2A1710, as 243630 step 1): pos.x += dir.x * 2.5 a tick"),
    ("actor", "lin", 0x2A1881, "mulss xmm0, dword ptr [rip + 0x3d3b4b]", (0x6753D4, 2.5),
     "em56..em59 approach, step 1: pos.z"),
    ("actor", "lin", 0x2A1999, "mulss xmm0, dword ptr [rip + 0x3d3a33]", (0x6753D4, 2.5),
     "em56..em59 approach, step 3 (120 ticks): pos.x"),
    ("actor", "lin", 0x2A19BF, "mulss xmm0, dword ptr [rip + 0x3d3a0d]", (0x6753D4, 2.5),
     "em56..em59 approach, step 3: pos.z"),
    ("actor", "lin", 0x2A1B00, "mulss xmm0, dword ptr [rip + 0x3d38cc]", (0x6753D4, 2.5),
     "em56..em59 approach, step 5: pos.x"),
    ("actor", "lin", 0x2A1B26, "mulss xmm0, dword ptr [rip + 0x3d38a6]", (0x6753D4, 2.5),
     "em56..em59 approach, step 5: pos.z"),
    ("actor", "callscale", 0x2A1C19, "call 0x2da410", (0x2DA410, "xmm1"),
     "em56..em59 jump kick (2A1710 step 7): forward by +E48 a tick"),
    # --- the other enemy moves by a step in stock units, read one by one from the
    # census of position steps. The motion finder refused
    # the moves by +E48 because one imp action writes +E48 from the time scale
    # (24706F, a random step it adds to +EC0), and the ones by +E18 because the
    # imps' push vector +E10/+E18 is updated from itself elsewhere; per action,
    # each of these sets its step from constants (or the distance to its
    # target) and moves by it every tick for a stock-length time: an animation,
    # a lea or memory timer, a fall at its stock pace, or a clock these rows
    # scale. A ramp of the step (+E48 += k x speed) is scaled with it, so the
    # step takes its stock values at stock times.
    ("actor", "callscale", 0x24DD10, "call 0x2da410", (0x2DA410, "xmm1"),
     "em02 charge (24D9B0, vtable slot 47, while +E3C counts down): forward 4 a tick "
     "(+12B8 = 3)"),
    ("actor", "callscale", 0x24DD34, "call 0x2da410", (0x2DA410, "xmm1"),
     "em02 charge: forward 3 a tick (+12B8 = 2)"),
    ("actor", "callscale", 0x24DD49, "call 0x2da410", (0x2DA410, "xmm1"),
     "em02 charge: forward 2 a tick (+12B8 = 0 or 1)"),
    ("actor", "dst", 0x24907F, "movss xmm0, dword ptr [rsp + 0x40]", None,
     "imp leap (248DE0, from the imps' dispatch 2422E0): every tick of every step, "
     "pos += RotateY(+B4) x (0, 0, +E48) (Apply into the stack vector); +E48 = 1.2 or "
     "1.8, *= 0.8 a tick (decay_factors.h). Its x, added to pos.x"),
    ("actor", "dst", 0x249094, "movss xmm0, dword ptr [rsp + 0x44]", None,
     "imp leap: the rotated step's y (0 for a turn about y), added to pos.y"),
    ("actor", "dst", 0x2490AB, "movss xmm0, dword ptr [rsp + 0x48]", None,
     "imp leap: the rotated step's z, added to pos.z"),
    ("actor", "callscale", 0x249A57, "call 0x2da410", (0x2DA410, "xmm1"),
     "imp backstep (249960, from 2422E0): forward by speed x +E48 a tick (+E48 = -5) "
     "until its animation ends"),
    ("actor", "lin", 0x249A64, "mulss xmm0, dword ptr [rip + 0x433810]",
     (0x67D27C, 0.09999999403953552),
     "imp backstep: +E48 += speed x 0.1 a tick, the ramp of the step"),
    ("actor", "lin", 0x24B237, "mulss xmm0, dword ptr [rip + 0x433ce5]",
     (0x67EF24, 0.45000001788139343),
     "em01/em7a/em83 knockback (24B120, vtable slot 68): vy +E54 += speed x 0.45 a tick"),
    ("actor", "callscale", 0x24B24F, "call 0x2da410", (0x2DA410, "xmm1"),
     "em01/em7a/em83 knockback: forward by speed x +E48 (= -6) a tick"),
    ("actor", "lin", 0x24B25C, "mulss xmm0, dword ptr [rip + 0x433cbc]",
     (0x67EF20, 0.19999998807907104),
     "em01/em7a/em83 knockback: +E48 += speed x 0.2 a tick until -0.5"),
    ("actor", "callscale", 0x24C621, "call 0x2da410", (0x2DA410, "xmm1"),
     "em01/em83 attack (24C380, vtable slot 64): forward by speed x +E48 (= 5) a tick "
     "while its animation loops"),
    ("actor", "callscale", 0x254324, "call 0x2da410", (0x2DA410, "xmm1"),
     "em05/em09/em18/em7c..em7e knockback (254010, from 2526F0): forward by speed x "
     "+E48 (= -6) a tick until its animation ends"),
    ("actor", "lin", 0x254331, "mulss xmm0, dword ptr [rip + 0x41dad7]",
     (0x671E10, 0.699999988079071),
     "the same knockback: +E48 += speed x 0.7 a tick until 0"),
    ("actor", "srcx", 0x25697C, "subss xmm0, xmm1", None,
     "em05 family dash (2566F0, from 2529B0): clock +1290 (30) -= speed a tick; xmm1, "
     "the speed, goes on to the move"),
    ("actor", "callscale", 0x2569C3, "call 0x2da410", (0x2DA410, "xmm1"),
     "the same dash: forward by speed x +E18 (the distance / 30) a tick"),
    ("actor", "callscale", 0x256E37, "call 0x2da410", (0x2DA410, "xmm1"),
     "em05 family attack (256C00, from 2529B0): forward by speed x +E48 (= 3) a tick "
     "while its animation plays"),
    ("actor", "callscale", 0x257C41, "call 0x2da410", (0x2DA410, "xmm1"),
     "em05 family attack (2579F0, from 2529B0): forward by +E48 (= 3) x speed a tick"),
    ("actor", "lin", 0x257C56, "mulss xmm1, dword ptr [rip + 0x4272c2]",
     (0x67EF20, 0.19999998807907104),
     "the same attack: +E48 -= speed x 0.2 a tick"),
    ("actor", "callscale", 0x2571EB, "call 0x2da410", (0x2DA410, "xmm1"),
     "em05 family leap (257060, from 2529B0): vy = 8, then forward by speed x +E18 "
     "(= 5) a tick until it lands (the fall at its stock pace)"),
    ("actor", "callscale", 0x258364, "call 0x2da410", (0x2DA410, "xmm1"),
     "em05 family leap (258290, from 2529B0): vy = 8, forward by speed x +E18 (= 4) a "
     "tick until it lands"),
    ("actor", "callscale", 0x25A715, "call 0x2da410", (0x2DA410, "xmm1"),
     "hop (25A510): vy = 4, 7 or 9, then forward by +E18 (2.5 or 4) a tick until "
     "vy <= -4 and on down to the ground"),
    ("actor", "dst", 0x2766B7, "movss xmm0, dword ptr [rdi + 0xe10]", None,
     "em2b leap (276400, from 275020): +E10 = the way to its target / 20 a tick; pos.x "
     "+= +E10 every tick of the animation's frames 15..37"),
    ("actor", "dst", 0x2766CE, "movss xmm0, dword ptr [rdi + 0xe18]", None,
     "em2b leap: pos.z += +E18 a tick"),
    ("actor", "dst", 0x277CF6, "movss xmm0, dword ptr [rdi + 0xe10]", None,
     "em2b lunge (2779A0, from 275020): +E10 = the way to Amaterasu / 16 a tick; pos.x "
     "+= +E10 every tick while +E3E is 0"),
    ("actor", "dst", 0x277D0D, "movss xmm0, dword ptr [rdi + 0xe18]", None,
     "em2b lunge: pos.z += +E18 a tick"),
    ("actor", "callscale", 0x28D9FD, "call 0x2da410", (0x2DA410, "xmm1"),
     "em4d/em4e/em50 charge (28D810, from 289A90): forward by +E18 a tick; +E18 = 0.1, "
     "*= 1.2 a tick up to 7 (the growth is not scaled: it reaches 7 in 12 ticks)"),
    ("actor", "callscale", 0x2A143F, "call 0x2da410", (0x2DA410, "xmm1"),
     "em56/em57/em59 knockback (2A1260, vtable slot 46): forward by speed x +E48 (step "
     "3) or +E48 (step 4) a tick, +E48 = -6"),
    ("actor", "lin", 0x2A144C, "mulss xmm0, dword ptr [rip + 0x3d45f0]", (0x675A44, 1.5),
     "the same knockback: +E48 += speed x 1.5 a tick until 0"),
    ("actor", "callscale", 0x2A1669, "call 0x2da410", (0x2DA410, "xmm1"),
     "em56..em59 knockback (2A1570, from 29F500): forward by +E48 (= -6) a tick"),
    ("actor", "lin", 0x2A1676, "mulss xmm0, dword ptr [rip + 0x3d078a]", (0x671E08, 0.5),
     "the same knockback: +E48 += speed x 0.5 a tick until 0"),
    ("actor", "callscale", 0x2A3EFD, "call 0x2da410", (0x2DA410, "xmm1"),
     "em56/em57/em58 dive (2A3AF0, vtable slot 43): forward by (distance - 70) / 2 a "
     "tick while farther than 70"),
    ("actor", "lin", 0x2A3F02, "movss xmm3, dword ptr [rip + 0x3d1b6e]", (0x675A78, 5.0),
     "the same dive: pos += M x (0, -10, 5, 1) a tick (2DA3F0) until it lands; z"),
    ("actor", "lin", 0x2A3F0F, "movss xmm2, dword ptr [rip + 0x3d5c71]", (0x679B88, -10.0),
     "the same dive: y of (0, -10, 5, 1); x is xmm6 = 0 and w xmm7 = 1 (the prologue)"),
    ("actor", "dst", 0x2A3F81, "movss xmm0, dword ptr [rdi + 0xe10]", None,
     "the same dive: pos.x += 2 x +E10 (the unit way to Amaterasu) a tick"),
    ("actor", "dst", 0x2A3F9B, "movss xmm1, dword ptr [rdi + 0xe18]", None,
     "the same dive: pos.z += 2 x +E18 a tick"),
    ("actor", "lin", 0x2A4413, "movss xmm1, dword ptr [rip + 0x3d3c65]", (0x678080, -2.0),
     "em56/em57/em58 spacing (2A43F0, vtable slot 42): back 2 a tick nearer than 30"),
    ("actor", "lin", 0x2A4431, "movss xmm1, dword ptr [rip + 0x3cd9db]", (0x671E14, 2.0),
     "the same spacing: forward 2 a tick farther than 90 (a tail jump to 2DA410)"),
    ("actor", "callscale", 0x2A586D, "call 0x2da410", (0x2DA410, "xmm1"),
     "em56..em59 backstep (2A5730, from 29F770): forward by speed x +E48 (= -5) a tick "
     "until its animation ends"),
    ("actor", "lin", 0x2A587D, "mulss xmm0, dword ptr [rip + 0x3d79f7]",
     (0x67D27C, 0.09999999403953552),
     "the same backstep: +E48 += speed x 0.1 a tick"),
    ("actor", "callscale", 0x2A5EFF, "call 0x2da410", (0x2DA410, "xmm1"),
     "em56..em59 dive (2A5CA0, from 29F770): forward by (distance - 80) / 2.5 a tick "
     "while farther than 80"),
    ("actor", "lin", 0x2A5F04, "movss xmm3, dword ptr [rip + 0x3cfb6c]", (0x675A78, 5.0),
     "the same dive: pos += M x (0, -10, 5, 1) a tick until it lands; z"),
    ("actor", "lin", 0x2A5F11, "movss xmm2, dword ptr [rip + 0x3d3c6f]", (0x679B88, -10.0),
     "the same dive: y; x is xmm7 = 0 and w xmm8 = 1 (the prologue)"),
    ("actor", "lin", 0x2A5F83, "mulss xmm0, dword ptr [rip + 0x3d3cfd]", (0x679C88, 3.5),
     "the same dive: pos.x += +E10 (the unit way to Amaterasu) x 3.5 a tick"),
    ("actor", "lin", 0x2A5FA9, "mulss xmm0, dword ptr [rip + 0x3d3cd7]", (0x679C88, 3.5),
     "the same dive: pos.z += +E18 x 3.5 a tick"),
    ("actor", "callscale", 0x2A7274, "call 0x2da410", (0x2DA410, "xmm1"),
     "em58 knockback (2A7150, vtable slot 47): forward by +E48 (= -6) a tick"),
    ("actor", "lin", 0x2A7281, "mulss xmm0, dword ptr [rip + 0x3ce7bb]", (0x675A44, 1.5),
     "the same knockback: +E48 += speed x 1.5 a tick until 0"),
    ("actor", "callscale", 0x2A733A, "call 0x2da410", (0x2DA410, "xmm1"),
     "the same knockback's next step: forward by +E48 a tick"),
    ("actor", "lin", 0x2A7347, "mulss xmm0, dword ptr [rip + 0x3ce6f5]", (0x675A44, 1.5),
     "the same step: +E48 += speed x 1.5 a tick until 0"),
    ("actor", "callscale", 0x2A7E5F, "call 0x2da410", (0x2DA410, "xmm1"),
     "em59 approach (2A7C00, vtable slot 43): forward 3 a tick while farther than 60, "
     "until +E3C (30, a memory timer) runs out or it lands"),
    ("actor", "lin", 0x2A7FF3, "movss xmm1, dword ptr [rip + 0x3d0085]", (0x678080, -2.0),
     "em59 spacing (2A7FD0, vtable slot 42): back 2 a tick nearer than 30"),
    ("actor", "lin", 0x2A8011, "movss xmm1, dword ptr [rip + 0x3c9dfb]", (0x671E14, 2.0),
     "em59 spacing: forward 2 a tick farther than 90"),
    ("actor", "callscale", 0x2D4C2F, "call 0x2da410", (0x2DA410, "xmm1"),
     "em7a attack (2D4AA0, vtable slot 64): forward by speed x +E48 (= 3) a tick while "
     "its animation loops"),
    ("actor", "srcx", 0x2D5222, "subss xmm0, xmm1", None,
     "em7c dash (2D4F60, vtable slot 41): clock +1290 -= speed a tick; xmm1, the speed, "
     "goes on to the move"),
    ("actor", "callscale", 0x2D524A, "call 0x2da410", (0x2DA410, "xmm1"),
     "the same dash: forward by speed x 0.6 x 10 a tick"),
    ("actor", "lin", 0x239AF3, "mulss xmm7, dword ptr [rip + 0x43ed95]",
     (0x678890, 0.029999999329447746),
     "the enemies' death fade (239AA0, from ten classes' deaths): alpha +115C -= "
     "rate x 0.03 a tick (the imps' rate is 1.0, 33 ticks); at 0.01 the enemy is "
     "removed (2389F0)"),
    ("actor", "dst", 0x247AB6, "mulss xmm0, dword ptr [rbx + 0xe48]", None,
     "imp sidestep (247900, from the imps' dispatch 2422EB): in its animation's frames "
     "4..13, +EC0 (this tick's root-motion step: the motion advance rewrites it every "
     "tick, 4B9E22, and 2DA3D0 moves the imp by it) += speed x +E48, +E48 random, 1 to "
     "2 or 0 to 1.5 a tick. The imps' other steps of this kind (246E60, 2488B0, "
     "249A90) put the time scale in +E48; this one does not"),
    ("actor", "lin", 0x291A91, "subss xmm0, dword ptr [rip + 0x3e819b]",
     (0x679C34, 0.06981316953897476),
     "em51 orbit (291940, from its state-1 update 291850): every tick the angle +11D0 "
     "turns 4 degrees, and the position is set 60 from a centre at that angle, for "
     "+11B8 (150 to 300) of its clock; this way round"),
    ("actor", "lin", 0x291A9B, "addss xmm0, dword ptr [rip + 0x3e8191]",
     (0x679C34, 0.06981316953897476),
     "em51 orbit: the angle the other way round (+11DA bit 0 clear)"),
    ("actor", "callscale", 0x2BF31D, "call 0x2da410", (0x2DA410, "xmm1"),
     "em64 chase (2BF0F0, action 0 of its state-1 update 2BF0A0): forward by speed x "
     "+E18 a tick while +E3C (120, a memory timer) runs and it is farther than 25; "
     "+E18 from 3 up by speed x 0.5 a tick to 11 (the step finder's row 2BF322)"),
    ("actor", "dst", 0x28650F, "movss xmm2, dword ptr [rdi + 0x1080]", ("scale", 0x286526),
     "em3d jump (2860D0): pos += +E10 x speed a tick (cVec::operator*(float), then +=) "
     "until it lands; its init sets +E10 to a level direction x 5.5 or 7.5 and vy to 8 "
     "or 11"),
    ("actor", "dst", 0x286691, "movss xmm2, dword ptr [r14 + 0x1080]", ("scale", 0x2866A5),
     "em3d (2865B0): pos += M x (+E10 x speed) a tick (2DA3F0); +E10 = (0, 0, -2) and "
     "its z +E18 += speed a tick up to 10 (the actor clock row 2866CD): a step back "
     "that turns into a run"),
    ("actor", "lin", 0x2588EB, "movss xmm1, dword ptr [rip + 0x41c665]", (0x674F58, 3.0),
     "em05 family walk (258700, from its state-1 update 2529B0): while farther than 30 "
     "from the point at +1070, +E10 = the level way to it x 3 and pos += +E10, a tick"),
    # --- approaches by a fraction of the gap a tick, x += (target - x) x k,
    # toward a target the step does not move: k -> 1 - (1 - k)^s (blend)
    ("actor", "blend", 0x2561A1, "movss xmm1, dword ptr [rip + 0x4226e7]",
     (0x678890, 0.029999999329447746),
     "em05 family exit (255ED0 step 3, from 2529B0): every tick pos += (the point at "
     "+1070 - pos) x 0.03 (cVec *=, +=) while it fades"),
    ("actor", "blend", 0x256222, "movss xmm1, dword ptr [rip + 0x41bbda]",
     (0x671E04, 0.10000000149011612),
     "the same step: then pos.xz += (that point, 40 above its ground, - pos).xz x 0.1"),
    ("actor", "blend", 0x258B06, "movss xmm1, dword ptr [rip + 0x4192f6]",
     (0x671E04, 0.10000000149011612),
     "em05 family hover (258930, from 2529B0): pos += (the point at +1070, 43 above "
     "its ground, - pos) x 0.1 a tick until within 15"),
    ("actor", "blend", 0x291A4E, "movss xmm2, dword ptr [rip + 0x3e03ae]",
     (0x671E04, 0.10000000149011612),
     "em51 orbit centre (291940): +11C0 += (its target + (0, 15, 0) - +11C0) x 0.1 a "
     "tick (cVec::operator*(float), +=)"),
    ("actor", "blend", 0x2870B7, "movss xmm1, dword ptr [rip + 0x3f16bd]",
     (0x67877C, 0.02500000037252903),
     "em3d approach (286E80): while farther than 5 from its target, pos += (target - "
     "pos) x 0.025 a tick"),
    ("actor", "gatefn", 0x239010, "push rbx", None,
     "the enemies' hit shake and hit stop (239010, from 25 classes' updates while +10C0, "
     "set to 4, 8, 14 or 15 by a hit, is above 0; meanwhile they skip their fall and "
     "tracking): a part of the model moves +2 or -2 in y by +10C0's parity, and +10C0 "
     "-= 1. On stock ticks only: the shake at stock's pace, the stop its stock length"),
    # --- em52 (vtable 681CB8): a flyer that circles a point. Its state-1
    # update 2940C0 places its target +1260 on an orbit round +12A0 and turns
    # toward it (20E210, the turn family's already); each action moves it
    # forward by 50 x +1278 (its flight speed) x speed x +F54 a tick through
    # cVec::operator*(float) and 2DA3F0, +1278 easing toward 3 x +12B4 (+12B4
    # set every tick from the distance to +1260). Its .data factors 79FD48..
    # 79FD78 are only read (every reference a movss/mulss load)
    ("actor", "lin", 0x294119, "movss xmm0, dword ptr [rip + 0x50bc27]",
     (0x79FD48, -0.03999999910593033),
     "em52 orbit (2940C0, +12C4 = 0): its angle +12B0 += -0.04 x speed x +12B8 a tick"),
    ("actor", "lin", 0x294163, "movss xmm0, dword ptr [rip + 0x50bbed]",
     (0x79FD58, 0.03999999910593033),
     "em52 orbit: the radius's phase +12BC += 0.04 x speed a tick (radius +129C + "
     "25 sin +12BC)"),
    ("actor", "lin", 0x29429B, "movss xmm0, dword ptr [rip + 0x50baa5]",
     (0x79FD48, -0.03999999910593033),
     "em52 orbit round Amaterasu (2940C0, +12C4 = 1): +12B0 += -0.04 x 0.9 x speed a "
     "tick"),
    ("actor", "lin", 0x2942DA, "movss xmm0, dword ptr [rip + 0x50ba76]",
     (0x79FD58, 0.03999999910593033),
     "the same orbit: +12BC += 0.04 x 0.1 x speed a tick (xmm9's 0.1 is read again "
     "later, so the row is on the 0.04)"),
    ("actor", "dst", 0x294810, "mulss xmm0, dword ptr [rbx + 0x1080]", None,
     "em52 spin (2940C0, while +12D8 is set): +1274 += +1278 x speed a tick, the angle "
     "its child model's +B0 is set to"),
    ("actor", "lin", 0x2994D3, "movss xmm0, dword ptr [rip + 0x506885]",
     (0x79FD60, -0.05999999865889549),
     "em52 action 3 (2994C0): +12B0 += -0.06 x speed x +12B8 a tick"),
    ("actor", "lin", 0x2996DC, "movss xmm0, dword ptr [rip + 0x506664]",
     (0x79FD48, -0.03999999910593033),
     "the same action (+25F0 = 3): +12B0 += -0.04 x 4 x speed x +12B8 a tick"),
    ("actor", "lin", 0x299AD8, "movss xmm1, dword ptr [rip + 0x506268]",
     (0x79FD48, -0.03999999910593033),
     "em52 action 15 (299AC0): +12B0 -= -0.04 x speed x +12B8 x 0.5 a tick"),
    ("actor", "lin", 0x29A139, "mulss xmm1, dword ptr [rip + 0x3db937]", (0x675A78, 5.0),
     "em52 action 16 (29A030): the spin +1274 -= +1278 x 5 a tick (+1278 *= 0.93, the "
     "decay factors' 29A12E)"),
    ("actor", "lin", 0x2993BC, "movss xmm2, dword ptr [rip + 0x3e41dc]",
     (0x67D5A0, 0.0024999999441206455),
     "em52 action 4 (2990A0): +1278 *= 0.965 (the decay factors' 2993A4), then +- 0.0025 "
     "a tick toward 3 x +12B4"),
    ("actor", "lin", 0x29A4B4, "movss xmm2, dword ptr [rip + 0x3e30e4]",
     (0x67D5A0, 0.0024999999441206455),
     "em52 action 2 (29A380): the same ramp, +- 0.0025 a tick (the decay factors' "
     "29A49C)"),
    ("actor", "lin", 0x299624, "movss xmm3, dword ptr [rip + 0x3e6a9c]",
     (0x6800C8, 0.003000000026077032),
     "em52 action 3 (2994C0): +1278 *= 0.989 (the decay factors' 299609), then +- 0.003 "
     "a tick toward 3 x +12B4"),
    ("actor", "lin", 0x29969A, "movss xmm2, dword ptr [rip + 0x5066c2]",
     (0x79FD64, 0.009999999776482582),
     "the same action (+25F0 = 3): +- 0.01 a tick toward 3 x 4 x +12B4"),
    ("actor", "lin", 0x299C0E, "movss xmm3, dword ptr [rip + 0x3e64b2]",
     (0x6800C8, 0.003000000026077032),
     "em52 action 15 (299AC0): +1278 += 0.003 a tick, and 0.003 more while below 0.3"),
    ("actor", "srcx", 0x2995CB, "subss xmm0, xmm7", None,
     "em52 action 3 (2994C0): +12C0 -= 1 a tick; at 0 a sound (4E) and +12C0 = 12. "
     "xmm7's 1.0 is also a vector's w later, so the row is on the subtraction"),
    ("actor", "srcx", 0x29A45E, "subss xmm0, xmm7", None,
     "em52 action 2 (29A380): the same countdown, 30 ticks, sound 4A"),
    ("actor", "dst", 0x2983FB, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x29840D),
     "em52 action 6 (2981B0): pos += M x (0, 0, 50 x +1278 x 1.2) x speed x +F54 a tick "
     "(2DA3F0); +1278 set to 0.06 at frame 65, then x 0.97 a tick"),
    ("actor", "dst", 0x2986D9, "movss xmm2, dword ptr [rdi + 0x1080]", ("scale", 0x2986EB),
     "em52 action 5 (2984A0): the same move, +1278 set to 0.105 or 0.15 at frame 15"),
    ("actor", "dst", 0x299453, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x299465),
     "em52 action 4 (2990A0): forward by 50 x +1278 x speed x +F54 a tick (2DA3F0)"),
    ("actor", "dst", 0x299929, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x29993B),
     "em52 action 3 (2994C0): the same move"),
    ("actor", "dst", 0x299C79, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x299C8B),
     "em52 action 15 (299AC0): forward by 50 x +1278 x 0.06 x speed x +F54 a tick"),
    ("actor", "dst", 0x29A1A9, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x29A1BB),
     "em52 action 16 (29A030): forward by 50 x +1278 x speed x +F54 a tick"),
    ("actor", "dst", 0x29A59F, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x29A5B1),
     "em52 action 2 (29A380): the same move"),
    ("actor", "dst", 0x296B2F, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x296B3F),
     "em52 action 8 (296700): pos += M x (5 x min(frame x 0.1, 1), 0, 0) x speed x +F54 "
     "a tick, a slide sideways"),
    ("actor", "dst", 0x299E50, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x299E62),
     "em52 action 18 (299D40): the same slide, 5 one way"),
    ("actor", "dst", 0x299FC9, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x299FDB),
     "em52 action 17 (299EC0): the same slide, 5 the other way"),
    ("actor", "dst", 0x2974FC, "movss xmm2, dword ptr [rbx + 0x1080]", ("scale", 0x29750E),
     "em52 action 9 (297090): pos += M x (0, 0, 16 x (sin^2 + 0.1)) x speed x +F54 a tick"),
    ("actor", "lin", 0x296857, "addss xmm0, dword ptr [rip + 0x3e33a1]",
     (0x679C00, 0.03490658476948738),
     "em52 action 8 (296700): its heading +B4 += 2 degrees a tick in frames 35..59"),
    ("actor", "lin", 0x29686E, "subss xmm0, dword ptr [rip + 0x3e338a]",
     (0x679C00, 0.03490658476948738),
     "the same action: +B4 -= 2 degrees a tick in frames 60..109"),
    ("actor", "lin", 0x297968, "mulss xmm0, dword ptr [rip + 0x3dfc80]",
     (0x6775F0, 0.05000000074505806),
     "em52 action 12 (297720): +B4 += f x 0.05 x speed a tick, f from 0 to 1 over "
     "frames 10..80"),
    ("actor", "lin", 0x297C0A, "movss xmm1, dword ptr [rip + 0x508162]", (0x79FD74, 0.5),
     "the same action, once its pull has caught Amaterasu (+12DA): her position += "
     "the level way from em52 to her x f x 0.5 a tick (her own height below its)"),
    ("actor", "lin", 0x297C14, "movss xmm1, dword ptr [rip + 0x50815c]", (0x79FD78, 0.5),
     "the same push, her height at or above its"),
    ("actor", "blend", 0x2977A8, "movss xmm2, dword ptr [rip + 0x3da654]",
     (0x671E04, 0.10000000149011612),
     "em52 action 12 (297720): pos += (+12A0 - pos) x 0.1 x speed a tick (cVec "
     "operator*, +=), toward the point it circles"),
    ("actor", "blend", 0x297DE2, "movss xmm2, dword ptr [rip + 0x3da01a]",
     (0x671E04, 0.10000000149011612),
     "em52 action 13 (297D50): the same pull toward +12A0"),
    ("actor", "blend", 0x2980D9, "movss xmm2, dword ptr [rip + 0x3d9d23]",
     (0x671E04, 0.10000000149011612),
     "em52 action 14 (297FA0): pos += (Amaterasu's position - pos) x 0.1 a tick in "
     "frames 11..24 (a target that moves: close to k' = 1 - 0.9^s)"),
    # --- em2d (27E5E0, called from 27CA28 each tick): em2d (and in step 1
    # its partner, 9C4770/9C4778) close in on a point by 0.2 of the way a
    # tick, but move a flat 15 (step 1: 5 and 4) once 0.2 of the way would
    # pass 10. With 0.2 blended and the flat steps and the test's 10 times
    # s, the test switches at a gap of 10 s / k' (46 at 120, 47 at 60; stock
    # 50): a fraction of a stock tick's move either way
    ("actor", "blend", 0x27E785, "movss xmm2, dword ptr [rip + 0x3f419f]",
     (0x67292C, 0.20000000298023224),
     "em2d step 3: step = (+24A0 - pos) x 0.2 (cVec operator*(float)); pos += step"),
    ("actor", "srcx", 0x27E7A4, "comiss xmm0, dword ptr [rip + 0x3f472d]", None,
     "the same step's test: |step| > 10 in stock units"),
    ("actor", "lin", 0x27E7BB, "movss xmm2, dword ptr [rip + 0x3f9b69]", (0x67832C, 15.0),
     "the same step, far away: step = its direction x 15"),
    ("actor", "blend", 0x27E9A2, "movss xmm6, dword ptr [rip + 0x3f3f82]",
     (0x67292C, 0.20000000298023224),
     "em2d step 1: em2d toward +24A0 and its partner toward 9C4790, each by 0.2 of the "
     "way a tick (xmm6 for both)"),
    ("actor", "lin", 0x27E9C4, "movss xmm7, dword ptr [rip + 0x3f450c]", (0x672ED8, 10.0),
     "the same step's tests: |step| > 10 (xmm7 for both)"),
    ("actor", "lin", 0x27E9DF, "movss xmm2, dword ptr [rip + 0x3f7091]", (0x675A78, 5.0),
     "em2d, far away: step = its direction x 5"),
    ("actor", "lin", 0x27EA77, "movss xmm2, dword ptr [rip + 0x3faf35]", (0x6799B4, 4.0),
     "its partner, far away: step = its direction x 4"),
    # --- em8f (vtable 683798): its update 2D8BB0 runs the part step 2D79F0
    # for its four parts every tick, a state machine per part in +1420+i:
    # a spring to an anchor (1, 7, 13), knocked off and falling (3, 15),
    # hidden (5), flying back (9, 11). Treated as the particles are: the
    # velocity +1440+16i changes on stock ticks (zfirst, ufirst, countlast),
    # the part moves s x it every tick (scaledadd), the counters count on
    # stock ticks (count; notyet on the tests that read the old value), the
    # approaches blend
    ("actor", "blendr", 0x2D7A70, "addss xmm8, xmm6", None,
     "em8f part step: k = 0.1 + 0.05 x part, the factor of case 1's approach, pos += "
     "(anchor - pos) x k a tick after the spring's move (xmm8, read by that only)"),
    ("actor", "src", 0x2D7B31, "mulss xmm1, xmm6", None,
     "case 1: the part's alpha +5C += (1 - +5C) x 0.1 a tick (xmm6's 0.1 is also case "
     "3's gravity): 0.1 x s, the linear share of the fade in (0.9037 of the gap left a "
     "stock tick at 120, 0.9 stock)"),
    ("actor", "ufirst", 0x2D7B61, "movss xmm6, dword ptr [rip + 0x3abd7f]", None,
     "case 1: the velocity's damping, x 0.96 a tick on each lane (xmm6's three readers)"),
    ("actor", "zfirst", 0x2D7B74, "mulss xmm0, xmm1", None,
     "case 1: the spring, vx += (anchor - pos).x x 0.002 a tick"),
    ("actor", "zfirst", 0x2D7B92, "mulss xmm0, xmm1", None, "case 1: the spring, vy"),
    ("actor", "zfirst", 0x2D7BBA, "mulss xmm0, xmm1", None, "case 1: the spring, vz"),
    ("actor", "count", 0x2D7BDF, "mov word ptr [rsi + r14*2 + 0x1424], ax", None,
     "case 1: the wobble's phase +1424+2i += 1 a tick (its sine of 8 degrees a step, "
     "read before the store)"),
    ("actor", "zfirst", 0x2D7C2E, "mulss xmm0, dword ptr [rip + 0x3a22ba]", None,
     "case 1: the wobble, vy += sin(phase x 8 degrees) x 0.04 a tick"),
    ("actor", "scaledadd", 0x2D7C6C, "call qword ptr [rip + 0x39918e]", None,
     "case 1: the part's position += its velocity (cVec::operator+=)"),
    ("actor", "blend", 0x2D7D25, "mulss xmm1, dword ptr [rip + 0x3a0b63]",
     (0x678890, 0.029999999329447746),
     "case 3 (knocked off): the alpha fades, +5C += (0 - +5C) x 0.03 a tick"),
    ("actor", "scaledadd", 0x2D7D48, "call qword ptr [rip + 0x3990b2]", None,
     "case 3: position += velocity (set to (8, 1, 8) on entry)"),
    ("actor", "srcx", 0x2D7D5E, "subss xmm0, xmm6", None,
     "case 3: its fall, vy -= 0.1 a tick (xmm6's 0.1)"),
    ("actor", "countlast", 0x2D7D74, "mulss xmm0, dword ptr [rip + 0x3ab620]", None,
     "case 3: vx *= -0.7 a tick, a shake that dies away; after the move, so on the "
     "last tick of the stock tick"),
    ("actor", "countlast", 0x2D7D8A, "mulss xmm0, dword ptr [rip + 0x3ab60a]", None,
     "case 3: vz *= -0.7 a tick"),
    ("actor", "count", 0x2D7DA7, "mov word ptr [rsi + r14*2 + 0x142c], ax", None,
     "case 3: its timer +142C+2i -= 1 a tick (30); case 4 once the old value was 0"),
    ("actor", "notyet", 0x2D7DB0, "test cx, cx", 0x2D8592,
     "case 3's timer test, of the value before the store: between stock ticks, not yet"),
    ("actor", "count", 0x2D7DF1, "mov word ptr [rsi + r14*2 + 0x142c], ax", None,
     "case 5 (hidden): the timer -= 1 a tick (150), then back to the anchor"),
    ("actor", "notyet", 0x2D7DFA, "test cx, cx", 0x2D8592, "case 5's timer test"),
    ("actor", "ufirst", 0x2D7E86, "movss xmm6, dword ptr [rip + 0x3aba5a]", None,
     "case 7 (drawn back to the body, 40 above it): the damping, x 0.96 a tick"),
    ("actor", "zfirst", 0x2D7EA6, "mulss xmm0, xmm1", None,
     "case 7: the spring, vx += (target - pos).x x 0.002 a tick"),
    ("actor", "zfirst", 0x2D7EC4, "mulss xmm2, xmm1", None, "case 7: the spring, vy"),
    ("actor", "zfirst", 0x2D7EE6, "mulss xmm0, xmm1", None, "case 7: the spring, vz"),
    ("actor", "count", 0x2D7F0B, "mov word ptr [rsi + r14*2 + 0x1424], ax", None,
     "case 7: the wobble's phase += 1 a tick"),
    ("actor", "zfirst", 0x2D7F5A, "mulss xmm0, dword ptr [rip + 0x3a1f8e]", None,
     "case 7: the wobble, vy += sin x 0.04 a tick"),
    ("actor", "scaledadd", 0x2D7F98, "call qword ptr [rip + 0x398e62]", None,
     "case 7: position += velocity"),
    ("actor", "blend", 0x2D8054, "movss xmm2, dword ptr [rip + 0x39d9d4]",
     (0x675A30, 0.30000001192092896),
     "case 9: pos += (the body + its offset + 40 up - pos) x 0.3 a tick, each lane "
     "(xmm2 for the three)"),
    ("actor", "count", 0x2D80EB, "mov word ptr [rsi + r14*2 + 0x142c], ax", None,
     "case 9: its timer -= 1 a tick while not 0 (10). The branch after reads the "
     "subtraction's flags, so on the tick after the stock tick that stores 1 it moves "
     "on: up to 3/4 of a stock tick early"),
    ("actor", "blend", 0x2D81A8, "mulss xmm1, dword ptr [rip + 0x3a1ac4]",
     (0x679C74, 0.4000000059604645),
     "case 11 (back onto the body): pos.x += (target - pos).x x 0.4 a tick"),
    ("actor", "blend", 0x2D81CA, "mulss xmm1, dword ptr [rip + 0x3a1aa2]",
     (0x679C74, 0.4000000059604645), "case 11: the same for z"),
    ("actor", "srcx", 0x2D81E5, "subss xmm0, dword ptr [rip + 0x39a743]", None,
     "case 11: vy -= 0.9 a tick (from 3)"),
    ("actor", "pre", 0x2D8205, "addss xmm0, dword ptr [rax + 4]", None,
     "case 11: pos.y += vy a tick (xmm0 holds the new vy, stored before)"),
    ("actor", "ufirst", 0x2D831C, "movss xmm6, dword ptr [rip + 0x3ab5c4]", None,
     "case 13 (settling on the anchor): the damping, x 0.96 a tick"),
    ("actor", "zfirst", 0x2D832F, "mulss xmm0, xmm1", None,
     "case 13: the spring, vx += (anchor - pos).x x 0.001 a tick"),
    ("actor", "zfirst", 0x2D834D, "mulss xmm0, xmm1", None, "case 13: the spring, vy"),
    ("actor", "zfirst", 0x2D8375, "mulss xmm0, xmm1", None, "case 13: the spring, vz"),
    ("actor", "count", 0x2D839A, "mov word ptr [rsi + r14*2 + 0x1424], ax", None,
     "case 13: the wobble's phase += 1 a tick"),
    ("actor", "zfirst", 0x2D83E9, "mulss xmm0, dword ptr [rip + 0x3a183f]", None,
     "case 13: the wobble, vy += sin x 0.02 a tick"),
    ("actor", "scaledadd", 0x2D8427, "call qword ptr [rip + 0x3989d3]", None,
     "case 13: position += velocity"),
    ("actor", "count", 0x2D8439, "mov word ptr [rsi + r14*2 + 0x142c], ax", None,
     "case 13: its timer -= 1 a tick (30), then case 0"),
    ("actor", "notyet", 0x2D8442, "test cx, cx", 0x2D8592, "case 13's timer test"),
    ("actor", "blend", 0x2D84AB, "mulss xmm1, dword ptr [rip + 0x3a03dd]",
     (0x678890, 0.029999999329447746),
     "case 15 (knocked off, the part's last hit): the alpha fades by 0.03 a tick"),
    ("actor", "scaledadd", 0x2D84C4, "call qword ptr [rip + 0x398936]", None,
     "case 15: position += velocity (set to (12, 2, 12) on entry)"),
    ("actor", "srcx", 0x2D84DA, "subss xmm0, xmm6", None, "case 15: vy -= 0.1 a tick"),
    ("actor", "countlast", 0x2D84F0, "mulss xmm0, dword ptr [rip + 0x3ab3f8]", None,
     "case 15: vx *= -0.9 a tick, the shake"),
    ("actor", "countlast", 0x2D8506, "mulss xmm0, dword ptr [rip + 0x3ab3e2]", None,
     "case 15: vz *= -0.9 a tick"),
    ("actor", "count", 0x2D8523, "mov word ptr [rsi + r14*2 + 0x142c], ax", None,
     "case 15: its timer -= 1 a tick (30), then case 16"),
    ("actor", "notyet", 0x2D852C, "test cx, cx", 0x2D8541, "case 15's timer test"),
    ("actor", "count", 0x2D86FC, "mov word ptr [rsi + r14*2 + 0x1434], ax", None,
     "after a hit: +1434+2i (60) -= 1 a tick while not 0, and each of those ticks the "
     "velocity is set to 15 in a random direction. The re-roll stays a tick's: at 120 "
     "the part jitters four times as often by a quarter of the move each (smaller "
     "overall), for the stock time"),
    # --- The remaining enemy candidates (coverage.csv, 2026-09-26), read by
    # function, most sites first. em2d's update 27AD50 (vtable slot at 680D48)
    # and its part spinner 280CB0 (called from it every tick)
    ("actor", "count", 0x27AD9D, "mov dword ptr [rcx + 0x24e4], eax", None,
     "em2d update (27AD50): +24E4 -= 1 a tick while above 0 (reloaded with 70) while "
     "+24EC is set"),
    ("actor", "count", 0x27B05C, "mov dword ptr [rbx + 0x2520], eax", None,
     "em2d update: +2520 -= 1 a tick while above 0 (set to 60 or 30); at 0 it takes "
     "its partner as its target again"),
    ("actor", "pre", 0x27B6B0, "addss xmm0, dword ptr [rbx + 0x2480]", None,
     "em2d update: +2480 += speed a tick (xmm0 the speed's copy), a clock"),
    ("actor", "srcx", 0x27B705, "subss xmm0, xmm1", None,
     "em2d update (+E88 = 0x22D or 0x22E): +248C -= speed a tick (xmm1 the speed), the "
     "clock its attack waits on (<0) and its 40/60 caps"),
    ("actor", "count", 0x27BF38, "mov byte ptr [rbx + 0x24d3], al", None,
     "em2d update: +24D3 -= 1 a tick while above 0, the frame (19 - +24D3) of a "
     "sub-model sequence"),
    ("actor", "dst", 0x280D2E, "mulss xmm1, xmm8", None,
     "em2d part spin (280CB0, +E88 = 0x22D): +24F0 -= +F54 x 0.1745 a tick, wrapped "
     "(xmm8's 0.1745 is also +E88 = 0x22E's step, 280F53: a REX load, so the row is on "
     "the product)"),
    ("actor", "lin", 0x280D47, "mulss xmm1, dword ptr [rip + 0x400109]",
     (0x680E58, 0.0019392546964809299),
     "the same: +24F4 -= +F54 x 0.00194 a tick, wrapped; the angle of sub-model 0x23"),
    ("actor", "lin", 0x280D73, "mulss xmm6, dword ptr [rip + 0x4000f1]",
     (0x680E6C, 0.02327105775475502),
     "the same: +24F8 and +2504 -= +F54 x 0.0233 a tick (xmm6 read by those two only)"),
    ("actor", "lin", 0x280D8F, "mulss xmm1, dword ptr [rip + 0x4000c5]",
     (0x680E5C, 0.0029088822193443775),
     "the same: +24FC -= +F54 x 0.00291 a tick"),
    ("actor", "lin", 0x280DB3, "mulss xmm0, dword ptr [rip + 0x4000a5]",
     (0x680E60, 0.01163552887737751),
     "the same: +2500 += +F54 x 0.0116 a tick"),
    ("actor", "lin", 0x280DEC, "mulss xmm1, dword ptr [rip + 0x400080]",
     (0x680E74, 0.03490658849477768),
     "the same: +2508 -= +F54 x 0.0349 a tick"),
    ("actor", "lin", 0x280E10, "mulss xmm1, dword ptr [rip + 0x400064]",
     (0x680E7C, 0.04072435200214386),
     "the same: +250C -= +F54 x 0.0407 a tick"),
    ("actor", "lin", 0x280E29, "mulss xmm7, dword ptr [rip + 0x400053]",
     (0x680E84, 0.05235988274216652),
     "the same: +2510 -= +F54 x 0.0524 a tick"),
    ("actor", "srcx", 0x280F53, "subss xmm0, xmm8", None,
     "em2d part spin (+E88 = 0x22E): +24F0 -= 0.1745 a tick, wrapped"),
    ("actor", "lin", 0x280F94, "movss xmm6, dword ptr [rip + 0x3ffef4]",
     (0x680E90, 0.2327105849981308),
     "the same: +24F4 and +24F8 += +F54 x 0.2327 a tick (xmm6 read by those two only), "
     "each wrap advancing a digit counter (+24D8, +24D9)"),
    ("actor", "lin", 0x281037, "mulss xmm0, dword ptr [rip + 0x3ffe65]",
     (0x680EA4, 3.4906585216522217),
     "the same: +2504 += (1 / 5) x 3.49 x +F54 a tick; each wrap advances +24DA"),
    ("actor", "lin", 0x281228, "mulss xmm1, dword ptr [rip + 0x3ffc2c]",
     (0x680E5C, 0.0029088822193443775),
     "the same: +24FC -= +F54 x 0.00291 a tick"),
    ("actor", "lin", 0x281244, "mulss xmm0, dword ptr [rip + 0x3ffc14]",
     (0x680E60, 0.01163552887737751),
     "the same: +2500 += +F54 x 0.0116 a tick"),
    ("actor", "lin", 0x281264, "mulss xmm0, dword ptr [rip + 0x3ffc08]",
     (0x680E74, 0.03490658849477768),
     "the same: +2508 += +F54 x 0.0349 a tick"),
    ("actor", "lin", 0x281284, "mulss xmm1, dword ptr [rip + 0x3ffbf0]",
     (0x680E7C, 0.04072435200214386),
     "the same: +250C -= +F54 x 0.0407 a tick"),
    ("actor", "lin", 0x28129D, "mulss xmm6, dword ptr [rip + 0x3ffbdf]",
     (0x680E84, 0.05235988274216652),
     "the same: +2510 -= +F54 x 0.0524 a tick"),
    # --- em88 (vtable slot at 6BC990): its update 5DF660, and 5DE6E0 (called
    # from it every tick), which poses four joints (sub-models 0xC, 0xD, 0x19,
    # 0x1A) by per-tick approaches: x += (target - x) x k
    ("actor", "count", 0x5DE708, "mov dword ptr [rcx + 0x3900], eax", None,
     "em88 joints (5DE6E0): +3900 -= 1 a tick while above 0"),
    ("actor", "count", 0x5DE71A, "mov dword ptr [rcx + 0x3904], eax", None,
     "em88 joints: +3904 -= 1 a tick while above 0"),
    ("actor", "blend", 0x5DE833, "mulss xmm1, dword ptr [rip + 0x973f9]", (0x675C34, 0.25),
     "em88 joints, while its stun clock +3860 runs: 0xC's +B0 -= (+B0 + pi/4) x 0.25 a "
     "tick, toward -pi/4"),
    ("actor", "blend", 0x5DE874, "mulss xmm0, dword ptr [rip + 0x973b8]", (0x675C34, 0.25),
     "the same: 0xD's +B0 += (pi/6 - +B0) x 0.25 a tick"),
    ("actor", "blend", 0x5DE8BD, "mulss xmm1, dword ptr [rip + 0x99c03]",
     (0x6784C8, 0.15000000596046448),
     "the same: 0x19's +B4 -= (+B4 + pi/4) x 0.15 a tick"),
    ("actor", "blend", 0x5DE8F6, "mulss xmm7, dword ptr [rip + 0x99bca]",
     (0x6784C8, 0.15000000596046448),
     "the same: 0x1A's +B4 += (pi/4 - +B4) x 0.15 a tick"),
    ("actor", "blend", 0x5DE927, "movss xmm6, dword ptr [rip + 0x97101]",
     (0x675A30, 0.30000001192092896),
     "the same: the nodes of 0xC and 0xD, y and z += (0 - y) x 0.3 a tick (xmm6, read "
     "by those four only)"),
    ("actor", "blend", 0x5DEB04, "mulss xmm0, dword ptr [rip + 0x999bc]",
     (0x6784C8, 0.15000000596046448),
     "em88 joints, otherwise: 0xC's +B0 += (0 - +B0) x 0.15 x 1.2 (1.5 while B6B2AC "
     "bit 26 is set) a tick. The root is on 0.15, so the factor is (1 - 0.85^s) x 1.2 "
     "against 1 - 0.82^s: 0.8222 of the gap left a stock tick at 120 for 0.82"),
    ("actor", "blend", 0x5DEB4A, "mulss xmm0, dword ptr [rip + 0x99976]",
     (0x6784C8, 0.15000000596046448),
     "the same for 0xD's +B0"),
    ("actor", "blend", 0x5DEB90, "mulss xmm0, dword ptr [rip + 0x9709c]", (0x675C34, 0.25),
     "the same for 0x19's +B4, 0.25 x 1.2"),
    ("actor", "src", 0x5DEBDC, "mulss xmm8, xmm9", None,
     "the same for 0x1A's +B4: its 0.25 is a REX load (xmm8), so the factor 0.25 x 1.2 "
     "is scaled by s here (0.732 of the gap left a stock tick at 120 for 0.7)"),
    ("actor", "blend", 0x5DEC16, "movss xmm7, dword ptr [rip + 0x96e12]",
     (0x675A30, 0.30000001192092896),
     "the same branch: the nodes of 0xC and 0xD, y and z toward -10 and 9 by 0.3 x 1.2 "
     "a tick (xmm7, read by those four only)"),
    ("actor", "lin", 0x5DF758, "subss xmm0, dword ptr [rip + 0x92718]", (0x671E78, 30.0),
     "em88 update (5DF660), while B6B2A0 bit 23 and B6B2AC bit 26 are set and its "
     "health is below 0.9 of its maximum: the stun clock +3860 -= 30 a tick down to 43 "
     "(10)"),
    ("actor", "count", 0x5DF9CE, "inc dword ptr [rbx + 0x38e0]", None,
     "em88 update: +38E0 += 1 a tick while Amaterasu is higher than 100 (0 otherwise)"),
    ("actor", "srcx", 0x5DFBD7, "subss xmm0, xmm10", None,
     "em88 update: +38C0 -= 1 a tick while above 0"),
    ("actor", "count", 0x5DFC02, "mov dword ptr [rbx + 0x38c8], eax", None,
     "em88 update: +38C8 -= 1 a tick while above 0"),
    ("actor", "srcx", 0x5E0740, "addss xmm0, xmm9", None,
     "em88 update: three materials' U += 0.01 a tick, wrapped at 2"),
    ("actor", "srcx", 0x5E078B, "addss xmm0, xmm7", None,
     "em88 update: the first child's material U += 0.075 a tick, wrapped at 2"),
    ("actor", "srcx", 0x5E07B5, "addss xmm0, xmm7", None,
     "the same for the second child"),
    # --- cEnemyObj's pieces (340D00, from 340440 for each piece every tick):
    # state 4 launches a piece at its target on a 0.4-a-tick arc and goes to 5;
    # 5 and 3 fly it (pos += v, vy -= 0.4, in 3 vx and vz *= 0.99), spin it and
    # count down 90 ticks. Moves by s x v each tick, the velocity changes on the
    # last tick of each stock period (after that period's moves, stock's order)
    ("actor", "pre", 0x340EBC, "addss xmm0, dword ptr [rdi + 0x80]", None,
     "cEnemyObj piece, state 5 (340D00): x += vx a tick (xmm0 holds vx)"),
    ("actor", "pre", 0x340ECE, "addss xmm1, dword ptr [rdi + 0x88]", None,
     "the same: z += vz (xmm1 holds vz)"),
    ("actor", "pre", 0x340EF0, "addss xmm0, dword ptr [rdi + 0x84]", None,
     "the same: y += vy (xmm0 holds vy's copy)"),
    ("actor", "countlast", 0x340EF8, "subss xmm3, dword ptr [rip + 0x338d74]", None,
     "the same: vy -= 0.4 a tick, after the move"),
    ("actor", "lin", 0x340F9D, "movss xmm2, dword ptr [rip + 0x338cdb]",
     (0x679C80, 0.10471975803375244),
     "the same: its spin, RotateXr by 0.105 rad a tick"),
    ("actor", "lin", 0x340FB3, "movss xmm2, dword ptr [rip + 0x338c51]",
     (0x679C0C, 0.1745329201221466),
     "the same: RotateYr by 0.175 rad a tick"),
    ("actor", "count", 0x340FF2, "sub byte ptr [r12], 1", "down",
     "the same: its countdown byte -= 1 a tick (from 90); at 0 the piece stops (a sub "
     "of 1)"),
    ("actor", "pre", 0x34108D, "addss xmm0, dword ptr [rdi + 0x80]", None,
     "cEnemyObj piece, state 3: x += vx a tick (xmm0 holds vx's copy)"),
    ("actor", "countlast", 0x34109D, "mulss xmm3, dword ptr [rip + 0x336727]", None,
     "the same: vx *= 0.99 a tick, after the move"),
    ("actor", "pre", 0x3410B0, "addss xmm0, dword ptr [rdi + 0x84]", None,
     "the same: y += vy (xmm0 holds vy's copy)"),
    ("actor", "countlast", 0x3410B8, "subss xmm1, dword ptr [rip + 0x338bb4]", None,
     "the same: vy -= 0.4 a tick, after the move"),
    ("actor", "pre", 0x3410D3, "addss xmm0, dword ptr [rdi + 0x88]", None,
     "the same: z += vz (xmm0 holds vz's copy)"),
    ("actor", "countlast", 0x3410DB, "mulss xmm2, dword ptr [rip + 0x3366e9]", None,
     "the same: vz *= 0.99 a tick, after the move"),
    ("actor", "lin", 0x341248, "movss xmm2, dword ptr [rip + 0x338a30]",
     (0x679C80, 0.10471975803375244),
     "the same: its spin, RotateXr by 0.105 rad a tick"),
    ("actor", "lin", 0x34125E, "movss xmm2, dword ptr [rip + 0x3389a6]",
     (0x679C0C, 0.1745329201221466),
     "the same: RotateYr by 0.175 rad a tick"),
    ("actor", "count", 0x3413EC, "sub byte ptr [r12], 1", "down",
     "the same: its countdown byte -= 1 a tick (from 90), a sub of 1"),
    # --- em69's glow (2CD270, from its update 2CE8E0 every tick)
    ("actor", "lin", 0x2CD284, "movss xmm3, dword ptr [rip + 0x3ac9a4]",
     (0x679C30, 0.019999999552965164),
     "em69 glow (2CD270): +1280, +1284 and +1288 rise by 0.02 a tick toward the health "
     "share +1291 / +1290 (xmm3, read by those three only)"),
    ("actor", "lin", 0x2CD2DB, "movss xmm2, dword ptr [rip + 0x3ab3a9]",
     (0x67868C, 0.004999999888241291),
     "the same: they fall by 0.005 a tick (xmm2, read by those three only; reloaded at "
     "2CD435)"),
    ("actor", "lin", 0x2CD49B, "movss xmm7, dword ptr [rip + 0x3a858d]",
     (0x675A30, 0.30000001192092896),
     "the same, while B6B2C0 bit 23 is set: the glow +1264 += 0.3 a tick for each of "
     "its ten materials, up to 255 (xmm7, read by that only)"),
    ("actor", "srcx", 0x2CD577, "subss xmm0, xmm2", None,
     "the same, otherwise: the pulse +1264 -= |4 sin +1260| a tick down to 0 (+1260 is "
     "an actor step already)"),
    ("actor", "pre", 0x2CD5B8, "addss xmm2, dword ptr [rbx + 0x1264]", None,
     "the same: +1264 += |8 sin +1260| a tick up to 255 (xmm2 the step)"),
    # --- em60's recoil (2B6400, from 2A8D20): while +154C counts down, two
    # joints turn by +1550 and +1554 a tick, which decay x 0.9 after the turn,
    # and it slides away from Amaterasu by +155C, which decays x 0.77 before
    # the slide: the turns' decays on the last tick of each stock period, the
    # slide's on the first (count on its store)
    ("actor", "pre", 0x2B642D, "addss xmm0, dword ptr [rax + 0xb0]", None,
     "em60 recoil (2B6400): sub-model 5's +B0 += +1550 a tick"),
    ("actor", "pre", 0x2B6445, "addss xmm1, dword ptr [rax + 0xb4]", None,
     "the same: sub-model 5's +B4 += +1554 a tick"),
    ("actor", "pre", 0x2B646F, "addss xmm0, dword ptr [rax + 0xb0]", None,
     "the same: sub-model 0x1D's +B0 += +1550 a tick"),
    ("actor", "count", 0x2B6497, "dec dword ptr [rbx + 0x154c]", None,
     "the same: +154C -= 1 a tick; the recoil runs while it is not below 0"),
    ("actor", "countlast", 0x2B649D, "mulss xmm0, xmm2", None,
     "the same: +1550 *= 0.9 a tick, after the turns"),
    ("actor", "countlast", 0x2B64A1, "mulss xmm1, xmm2", None,
     "the same: +1558 *= 0.9 a tick"),
    ("actor", "countlast", 0x2B64B5, "mulss xmm0, xmm2", None,
     "the same: +1554 *= 0.9 a tick, after the turns"),
    ("actor", "count", 0x2B64D9, "movss dword ptr [rbx + 0x155c], xmm0", None,
     "the same: +155C *= 0.77 a tick (the store), before the slide: on the first tick "
     "of each stock period"),
    ("actor", "scaledadd", 0x2B653F, "call qword ptr [rip + 0x3ba8bb]", None,
     "the same: pos += (its position - Amaterasu's) normalized x +155C a tick"),
    # --- em03 / em80, 24EB80 (vtable slots at 67F330 and 697BB8)
    ("actor", "count", 0x24ECC5, "mov word ptr [rbx + 0xe3e], ax", None,
     "em03/em80 (24EB80) state 1: +E3E -= 1 a tick (from 40); while it runs its tint "
     "+1150, +1154, +1158 closes on (10, 0.5, 0.5), then on 1"),
    ("actor", "srcblend", 0x24ECCC, "mulss xmm1, xmm2", None,
     "the same: +1150 += (10 - +1150) x 0.5 a tick. xmm2's 0.5 is also a target, so "
     "the factor is blended here, in a copy"),
    ("actor", "srcblend", 0x24ECEB, "mulss xmm1, xmm2", None,
     "the same: +1154 += (0.5 - +1154) x 0.5"),
    ("actor", "srcblend", 0x24ED07, "mulss xmm1, xmm2", None,
     "the same: +1150 += (1 - +1150) x 0.5, once +E3E is 0"),
    ("actor", "srcblend", 0x24ED26, "mulss xmm1, xmm2", None,
     "the same: +1154 += (1 - +1154) x 0.5"),
    ("actor", "srcblend", 0x24ED48, "mulss xmm1, xmm2", None,
     "the same: +1158 += (0.5 or 1 - +1158) x 0.5"),
    ("actor", "srcx", 0x24EF3E, "addss xmm0, xmm7", None,
     "the same: the shock's radius +E10 += 1 a tick (from 8), the size of its hit test "
     "(2DC7B0)"),
    # --- em65's slot 25 (2BFCF0), called from its update every tick
    ("actor", "srcx", 0x2BFEC1, "subss xmm0, xmm6", None,
     "em65 (2BFCF0, +E88 = 0x211, while +1740 is set): +174C -= 1 a tick; below 0 a "
     "sound and +174C = 45"),
    # --- cMonsterGear (4A1A80, its update, calls these): gears that spin and
    # spring back
    ("actor", "count", 0x4A2063, "mov byte ptr [rbx + 0xe36], al", None,
     "cMonsterGear spin-down (4A1FE0): +E36 += 1 a tick up to 60; the spin's step is "
     "0.655 x k / (0.5 x +E36)"),
    ("actor", "pre", 0x4A2088, "addss xmm1, dword ptr [rbx + 0xb8]", None,
     "the same: +B8 += 0.655 x k / (0.5 x +E36) a tick (xmm1 the step; k = 1, or 0.015 "
     "in state 3)"),
    ("actor", "pre", 0x4A20D8, "addss xmm0, dword ptr [rbx + 0xb8]", None,
     "the same, while +E36 is 0: +B8 += 0.655 x k a tick"),
    ("actor", "lin", 0x4A213A, "subss xmm0, dword ptr [rip + 0x1cfac6]", (0x671C08, 1.0),
     "the same: +1070 -= 1 a tick (reloaded with 100 x a random share at 0)"),
    ("actor", "pre", 0x4A1F81, "addss xmm2, dword ptr [rbx + 0xb8]", None,
     "cMonsterGear spin (4A1EB0): +B8 += 0.6 x k a tick (xmm2 the step; k = 1, or 0.25 "
     "in state 3)"),
    ("actor", "lin", 0x4A1F60, "subss xmm0, dword ptr [rip + 0x1cfca0]", (0x671C08, 1.0),
     "the same: +1070 -= 1 a tick"),
    ("actor", "srcx", 0x4A2249, "subss xmm1, xmm6", None,
     "cMonsterGear turn (4A21A0): +B8 -= +-2.5 x (0.15 or 0.025) x 0.1 a tick (xmm6 "
     "the step)"),
    ("actor", "pre", 0x4A2E03, "addss xmm0, dword ptr [rcx]", None,
     "cMonsterGear spring (4A2D90, state 2): its scale +D20 += (1 - 0.4) / 5 a tick "
     "back to 1 (xmm0 the step)"),
    ("actor", "pre", 0x4A2E19, "addss xmm0, dword ptr [rdi + 0xd24]", None,
     "the same: +D24"),
    ("actor", "pre", 0x4A2E37, "addss xmm0, dword ptr [rdi + 0xd28]", None,
     "the same: +D28, whose reaching 1 ends the state"),
    ("actor", "count", 0x4A2F23, "mov byte ptr [rdi + 0xe35], al", None,
     "the same, state 3: +E35 -= 1 a tick (from 10), then state 0"),
    ("actor", "pre", 0x4A32BF, "addss xmm0, dword ptr [rcx]", None,
     "cMonsterGear spring (4A3250): its scale +D20 += (1 - 0.4) / 5 a tick back to 1"),
    ("actor", "pre", 0x4A32D5, "addss xmm0, dword ptr [rdi + 0xd24]", None,
     "the same: +D24"),
    ("actor", "pre", 0x4A32F3, "addss xmm0, dword ptr [rdi + 0xd28]", None,
     "the same: +D28"),
    ("actor", "count", 0x4A33E2, "mov byte ptr [rdi + 0xe35], al", None,
     "the same, state 3: +E35 -= 1 a tick (from 10)"),
    ("actor", "count", 0x4A2CA6, "dec dword ptr [rbx + 0x107c]", None,
     "cMonsterGear (4A2B00): +107C -= 1 a tick (its phases at 120, 70, 30 and 9 set "
     "its motion rate +F54)"),
    ("actor", "count", 0x4A2CBC, "dec dword ptr [rbx + 0x107c]", None,
     "the same: -= 1 more while 23B750 answers no"),
    # --- em60's update 2A8D20 (vtable slot at 682690): its countdowns
    ("actor", "count", 0x2A8FC2, "mov byte ptr [rbx + 0x15a3], al", None,
     "em60 update (2A8D20): +15A3 -= 1 a tick while above 0 (each tick it tries "
     "2B5B20's action)"),
    ("actor", "count", 0x2A90B0, "mov dword ptr [rbx + 0x1660], eax", None,
     "em60 update: +1660 -= 1 a tick while not below 0 (each tick it tries 2B5890's "
     "action)"),
    ("actor", "count", 0x2A90DC, "mov dword ptr [rbx + 0x1664], eax", None,
     "em60 update: +1664 -= 1 a tick while not below 0"),
    ("actor", "count", 0x2A9128, "mov dword ptr [rbx + 0x1668], eax", None,
     "em60 update: +1668 -= 1 a tick while not below 0"),
    ("actor", "count", 0x2A92BD, "inc dword ptr [rbx + 0x166c]", None,
     "em60 update: +166C += 1 a tick while Amaterasu is out of its reach (0 "
     "otherwise); past 90 it acts"),
    # --- em8f's slot 25 (2D8830): for 60 ticks after a hit it shakes, 1 a tick
    # in a random direction, and spins 0.506 rad a tick
    ("actor", "count", 0x2D8A3B, "mov word ptr [rdi + 0x1620], ax", None,
     "em8f (2D8830): +1620 -= 1 a tick (60 after a hit)"),
    ("actor", "pre", 0x2D8AC3, "addss xmm0, dword ptr [rax]", None,
     "the same, while +1620 runs: x += the random unit step's x a tick (scaled: at 120 "
     "four steps of a quarter, a smaller shake in stock time, as em8f's parts)"),
    ("actor", "pre", 0x2D8AD8, "addss xmm0, dword ptr [rax + 8]", None,
     "the same: z += its z"),
    ("actor", "lin", 0x2D8AEA, "addss xmm0, dword ptr [rip + 0x3aadf2]",
     (0x6838E4, 0.5061454772949219),
     "the same: its heading +B4 += 0.506 rad a tick"),
    # --- em8f, 2D9460 (from 2D9360)
    ("actor", "blend", 0x2D95AC, "mulss xmm0, dword ptr [rip + 0x39e03c]",
     (0x6775F0, 0.05000000074505806),
     "em8f (2D9460): +D2C += (0.6 - +D2C) x 0.05 a tick"),
    ("actor", "count", 0x2D95C8, "mov word ptr [rdi + 0x1230], ax", None,
     "the same: +1230 -= 1 a tick while above 0"),
    ("actor", "count", 0x2D9615, "mov word ptr [rdi + 0xe40], r8w", None,
     "the same, while B6B2A0 bit 14 is set: the bob's phase +E40 += 1 a tick, in "
     "degrees (the other branch's store, 2D96AB, is counted already)"),
    ("actor", "count", 0x2D9895, "mov word ptr [rdi + 0x1232], ax", None,
     "the same: +1232 -= 1 a tick while above 0"),
    ("actor", "count", 0x2D98B8, "mov word ptr [rdi + 0x1232], ax", None,
     "the same: -= 1 more while B6B2A0 bit 14 is set"),
    # --- em86 (vtable slot at 6BC570), 5CE810
    ("actor", "count", 0x5CE84B, "mov dword ptr [rcx + 0x1190], eax", None,
     "em86 (5CE810), while B6B2A0 bit 23 is set: +1190 += 1 a tick once started (not "
     "0)"),
    ("actor", "pre", 0x5CE86E, "addss xmm0, dword ptr [rdi + 0x5490]", None,
     "the same: +5490 += +5498 a tick up to +54A0, a material's level"),
    ("actor", "srcx", 0x5CE8FF, "addss xmm0, xmm7", None,
     "the same: two materials' U += 0.01 a tick, wrapped at 2"),
    ("actor", "pre", 0x5CEC96, "addss xmm0, dword ptr [rdi + 0x5490]", None,
     "em86, otherwise: +5490 += +5498 a tick up to +54A0"),
    ("actor", "srcx", 0x5CED1F, "addss xmm0, xmm7", None,
     "the same: two materials' U += 0.01 a tick, wrapped at 2"),
    # --- em65's slot 8 (2C0A60, vtable slot at 682FE8)
    ("actor", "count", 0x2C0C8C, "mov dword ptr [rdi + 0x1714], eax", None,
     "em65 (2C0A60): +1714 -= 1 a tick while above 0"),
    ("actor", "srcx", 0x2C1FEA, "addss xmm1, xmm6", None,
     "the same, while its child +1728 is above 200: the child's fall speed +1744 += "
     "0.8 a tick (xmm6 is also the fall helper's gravity at 2C1B03, so the row is on "
     "the add: dt = s, as the helper's own)"),
    ("actor", "srcx", 0x2C2002, "subss xmm0, xmm1", None,
     "the same: the child's y -= +1744 a tick, down to 200"),
    ("actor", "srcx", 0x2C2199, "subss xmm0, xmm2", None,
     "the same: +1734 -= speed a tick (xmm2 the speed, which is also the child's "
     "motion rate after: the row is on the subtraction)"),
    # --- em87 (5DAC90, from 5D5780): eight parts on a ring
    ("actor", "notyet", 0x5DAD37, "test cl, cl", 0x5DAD3B,
     "em87 ring (5DAC90): with B6B2BC bit 21 clear +5398 += 1 every tick, set only "
     "when its state clock +52DC crosses a multiple of 42. Between stock ticks the "
     "test reads \"set\", so the count runs once a stock tick (the crossing test between "
     "may add one when the clock crosses a multiple of 42)"),
    ("actor", "srcblend", 0x5DAF77, "mulss xmm1, xmm4", None,
     "em87 ring: a part's angle += (its slot's angle - angle) x 0.7 a tick (xmm4's 0.7 "
     "is also a health threshold at 5DAE05: the copy is blended)"),
    ("actor", "blend", 0x5DB1EC, "mulss xmm0, dword ptr [rip + 0x96c10]",
     (0x671E04, 0.10000000149011612),
     "em87 ring, turning: a part's spin speed += (target - speed) x 0.1 a tick"),
    ("actor", "dst", 0x5DB1FE, "mulss xmm0, xmm10", None,
     "the same: its angle += speed x (2, 0.3 or 0.05) a tick, wrapped (xmm0 the step, "
     "added next)"),
    # --- the shared object slot 36 (209000; cEnemyObj, the cKiType* and about
    # 100 more classes): state 1, rising away
    ("objects", "lin", 0x2091B3, "addss xmm0, dword ptr [rip + 0x4707f9]", (0x6799B4, 4.0),
     "objects' slot 36 (209000) state 1: y += 4 a tick (up to 500 above its start) for "
     "450 ticks (+E3C, an action timer already)"),
    ("objects", "lin", 0x2091C8, "addss xmm0, dword ptr [rip + 0x470af0]",
     (0x679CC0, 0.27925267815589905),
     "the same: its heading +B8 += 0.279 rad a tick"),
    # --- cEm's shared slots
    ("actor", "count", 0x2387EC, "mov dword ptr [rcx + 0x113c], eax", None,
     "cEm slot 38 (2387E0, a state's per-tick handler): +113C -= 1 a tick while above "
     "0"),
    ("actor", "blend", 0x239515, "mulss xmm2, dword ptr [rip + 0x43c513]",
     (0x675A30, 0.30000001192092896),
     "cEm slot 33 (239470): the near-camera fade +D2C += (max(0, 0.7 - (50 - z) x "
     "0.0233) - +D2C) x 0.3 a tick while its view depth z is below 50"),
    ("actor", "blend", 0x239543, "mulss xmm1, dword ptr [rip + 0x43c4e5]",
     (0x675A30, 0.30000001192092896),
     "the same: +D2C += (1 - +D2C) x 0.3 a tick beyond 50"),
    ("actor", "blend", 0x239571, "mulss xmm1, dword ptr [rip + 0x43c4b7]",
     (0x675A30, 0.30000001192092896),
     "the same while B6B2BC bit 31 or B6B2AC bit 29 is set"),
    ("actor", "count", 0x23A948, "sub al, 1", (0x23A93D, 0x23A94A, (0x23A93D, 0x23A944, 0x23A946, 0x23A948), None),
     "cEm slot (23A920): +1144 -= 1 a tick while above 0 (its zero test reads the "
     "sub's flags: skipped, \"not yet\")"),
    ("actor", "count", 0x23A97C, "dec ax", (0x23A96C, 0x23A97F, (0x23A96C, 0x23A973, 0x23A976, 0x23A97C), None),
     "the same: +1162 -= 1 a tick while not 0"),
    # --- em00..em03's slot (2422E0)
    ("actor", "lin", 0x242644, "addss xmm0, dword ptr [rip + 0x4375ec]",
     (0x679C38, 0.20943951606750488),
     "em00..em03 (2422E0, +E88 = 0x273): sub-model 0x1B's angle +14B8 += 0.209 rad a "
     "tick"),
    # --- em02 slot 49 (24E230): its hit probe
    ("actor", "lin", 0x24E407, "subss xmm0, dword ptr [rip + 0x429f1d]", (0x67832C, 15.0),
     "em02 (24E230): the hit probe's reach +E28 -= 15 a tick (the probe at pos + "
     "direction x +E28, tested with radius 20 every tick)"),
    # --- the slot-8 updates' effect spawners (em05 family 2512E0, em12 25B7A0,
    # em13/em14 25F300): while B6B2BC bit 21 is set, +1136 counts 0, 1, 2 and at
    # 2 an effect spawns and it restarts (100 while its checks fail)
    ("actor", "count", 0x25141C, "mov byte ptr [rdi + 0x1136], al", None,
     "em05 family update (2512E0): +1136 += 1 a tick; at 2 an effect (0x5D) and 0: one "
     "every 3 ticks"),
    ("actor", "count", 0x25B964, "mov byte ptr [rdi + 0x1136], al", None,
     "em12 update (25B7A0): the same spawner"),
    ("actor", "count", 0x25F464, "mov byte ptr [rbx + 0x1136], al", None,
     "em13/em14 update (25F300): the same spawner"),
    ("actor", "lin", 0x259CA5, "mulss xmm0, dword ptr [rip + 0x41d943]",
     (0x6775F0, 0.05000000074505806),
     "em09 slot 24 (259B00): its fade +115C -= speed x 0.05 a tick once its animation "
     "is past frame 80"),
    ("actor", "lin", 0x25E50C, "subss xmm1, dword ptr [rip + 0x41b4a0]", (0x6799B4, 4.0),
     "em12 (25E4C0): +1384 -= 4 a tick down to 0 while +10A4 is 200 or more"),
    ("actor", "count", 0x264656, "inc dword ptr [rdi + 0x1da0]", None,
     "em16 (264280, +E88 = 0x216): +1DA0 += 1 a tick; at 300 it acts"),
    ("actor", "count", 0x264E69, "inc dword ptr [rdi + 0x1cec]", None,
     "em16: +1CEC += 1 a tick while its health is above 0.65 of its maximum; past 90 "
     "it acts and restarts"),
    ("actor", "count", 0x2655F4, "mov dword ptr [rdi + 0x1d94], eax", None,
     "em16 update (slot 8): +1D94 -= 1 a tick while above 0"),
    # --- em16's head turn (26B920, from 26B160): a joint turns toward a point by
    # at most 10 and 3 degrees x a factor x speed a tick, the limits passed in
    # xmm2 and xmm3
    ("actor", "argscale", 0x26B945, "movaps xmm6, xmm3", None,
     "em16 joint turn (26B920): the limit 10 degrees x k x speed a tick (xmm3), copied "
     "to xmm6 for the heading's clamp"),
    ("actor", "argscale", 0x26B948, "movaps xmm7, xmm2", None,
     "the same: 3 degrees x k x speed a tick (xmm2), copied to xmm7 for the pitch's "
     "clamp"),
    ("actor", "count", 0x26F11B, "mov byte ptr [rbx + 0x1136], al", None,
     "em27/em29 update (26F030): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "lin", 0x272F12, "addss xmm0, dword ptr [rip + 0x3feefa]", (0x671E14, 2.0),
     "em27/em29 (272EC0, from 26F930 each tick): +1414 += 2 a tick while Amaterasu is "
     "within 200; at 150 + 22 x n it acts"),
    ("actor", "count", 0x273E64, "add word ptr [rbx + 0x13a2], -5", None,
     "em2b (273E10): +13A2 -= 5 a tick in state (1, 11)"),
    ("actor", "count", 0x273E84, "add word ptr [rbx + 0x13a2], -5", None,
     "the same in state (1, 8) before sub-state 6"),
    ("actor", "count", 0x273E8E, "add word ptr [rbx + 0x13a2], 8", None,
     "the same: += 8 a tick otherwise (floored at 0)"),
    ("actor", "count", 0x274172, "mov byte ptr [rdi + 0x1136], al", None,
     "em2b update (273FF0): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "lin", 0x274D11, "subss xmm0, dword ptr [rip + 0x3fdd27]",
     (0x672A40, 0.009999999776482582),
     "em2b slot 24 (274C30): its fade +115C -= 0.01 a tick (and a partner's with it)"),
    ("actor", "count", 0x275100, "dec ax", (0x2750F4, 0x275103, (0x2750F4, 0x2750FB, 0x2750FE, 0x275100), None),
     "em2b slot 16 (275020): +13A0 -= 1 a tick while above 0 (the dec: the register's "
     "value is tested after the store)"),
    # --- em2b's actions (274BB0 and 275020 dispatch them)
    ("actor", "count", 0x2755EF, "mov byte ptr [rdi + 0x1394], al", None,
     "em2b (275280): +1394 -= 1 a tick while above 0, then its next sub-state"),
    ("actor", "count", 0x275CE3, "mov word ptr [rbx + 0x138e], ax", None,
     "em2b (275A80): +138E -= 1 a tick while above 0, then state 0x802"),
    ("actor", "count", 0x276317, "dec ax", (0x27630B, 0x27631A, (0x27630B, 0x276312, 0x276315, 0x276317), None),
     "em2b (2762A0): +10C2 -= 1 a tick while not 0 (the dec: the register is read "
     "after the store)"),
    ("actor", "count", 0x276CF5, "dec ax", (0x276CE6, 0x276CF8, (0x276CE6, 0x276CED, 0x276CF0, 0x276CF3, 0x276CF5), None),
     "em2b (276CD0): the same countdown"),
    # --- em2c's slot 25 (278E30)
    ("actor", "count", 0x2790AE, "mov byte ptr [rdi + 0xe76], al", None,
     "em2c (278E30): +E76 -= 1 a tick while above 0 (the action timers' field, on a "
     "base the finder does not take)"),
    # --- em2d's actions (27C760, 27C850, 27C930 dispatch them)
    ("actor", "lin", 0x27D9FC, "subss xmm0, dword ptr [rip + 0x3fc26c]",
     (0x679C70, 0.07999999821186066),
     "em2d (27D840): its alpha +115C -= 0.08 a tick while Amaterasu is within 150"),
    ("actor", "lin", 0x27DA06, "addss xmm0, dword ptr [rip + 0x3fc262]",
     (0x679C70, 0.07999999821186066),
     "the same: += 0.08 a tick beyond"),
    ("actor", "pre", 0x27E2FB, "addss xmm0, dword ptr [rbx + 0x2434]", None,
     "em2d (27E000), while B6B2BC bit 21 is set: +2438 = +2434 + 2 x speed (xmm0 the "
     "speed's copy)"),
    ("actor", "srcx", 0x27E315, "addss xmm0, xmm1", None,
     "the same: the second speed"),
    ("actor", "pre", 0x27E319, "addss xmm1, xmm0", None,
     "the same: +2434 += 3 x speed a tick (xmm1 the speed)"),
    # --- em2d (281AE0) and its joint turn (2836F0)
    ("actor", "blend", 0x28293D, "mulss xmm1, dword ptr [rip + 0x3ef4bf]",
     (0x671E04, 0.10000000149011612),
     "em2d (281AE0): a child's +B0 += (2.2 - +B0) x 0.1 a tick"),
    ("actor", "blend", 0x2829E7, "mulss xmm1, dword ptr [rip + 0x3ef415]",
     (0x671E04, 0.10000000149011612),
     "the same toward 0.25"),
    ("actor", "argscale", 0x283715, "movaps xmm6, xmm3", None,
     "em2d joint turn (2836F0, as em16's 26B920): the limit in xmm3 (degrees x k a "
     "tick), copied to xmm6 for the heading's clamp"),
    ("actor", "argscale", 0x283718, "movaps xmm7, xmm2", None,
     "the same: the limit in xmm2, copied to xmm7 for the pitch's clamp"),
    ("actor", "count", 0x285956, "mov byte ptr [rbx + 0x1136], al", None,
     "em3d update (285870): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "count", 0x287738, "movss dword ptr [rbx + 0x115c], xmm1", None,
     "em3f (287690): its fade +115C -= speed x 0.05 a tick, computed in doubles (so no "
     "float literal): the store on stock ticks only. Its test below 0.1 reads the "
     "computed value, so it may end up to 3/4 of a stock tick early"),
    ("actor", "count", 0x288EB2, "mov byte ptr [rdi + 0x1136], al", None,
     "em4d/em4e/em50 update (288D90): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "count", 0x288EE4, "inc word ptr [rdi + 0x125c]", None,
     "the same: +125C += 1 a tick while Amaterasu is 20 below it (0 otherwise)"),
    ("actor", "count", 0x28A852, "mov word ptr [rbx + 0x125e], ax", None,
     "em4d family (28A670): +125E -= 1 a tick while not 0"),
    ("actor", "count", 0x28AA4A, "mov word ptr [rbx + 0x125e], ax", None,
     "em4d family (28A960): the same countdown"),
    ("actor", "count", 0x28B607, "mov word ptr [rbx + 0x125e], ax", None,
     "em4d/em50 (28B4F0): the same countdown"),
    ("actor", "count", 0x2914A6, "mov byte ptr [rbx + 0x1136], al", None,
     "em51 update (2913B0): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "lin", 0x291EAD, "mulss xmm0, dword ptr [rip + 0x3e7d7b]",
     (0x679C30, 0.019999999552965164),
     "em51 (291CB0): its fade +115C -= speed x 0.02 a tick"),
    ("actor", "srcx", 0x291ED4, "subss xmm0, xmm2", None,
     "the same: +11B8 -= speed a tick (xmm2 the speed); at 0 state 3"),
    ("actor", "count", 0x293339, "mov dword ptr [rdi + 0x12e8], eax", None,
     "em52 update (2930F0): +12E8 -= 1 a tick while not below 0 (+12E4 keeps its "
     "health meanwhile)"),
    ("actor", "count", 0x293770, "mov dword ptr [rdi + 0x12e0], eax", None,
     "the same: +12E0 -= 1 a tick while above 0"),
    ("actor", "count", 0x29A950, "mov byte ptr [rcx + 0x12db], al", None,
     "em52 (29A920, from its slot 25 every tick): +12DB -= 1 a tick while above 0"),
    # --- em52's parts (29B300, from its update 2930F0): each part is pulled
    # toward a point by (point - pos) x 0.0055, moves by its velocity x speed
    # unless held (+2), gains the pull x speed and is damped by its own factor
    # (+40) a tick. Integrated with dt = s: the move and the pull scaled, the
    # damping rooted (its y also x 0.975, the decay factors' 29B627)
    ("actor", "dst", 0x29B524, "movss xmm2, dword ptr [rsi + 0x1080]", ("scale", 0x29B534),
     "em52 part (29B300): pos += vel x speed a tick (cVec::operator*(float), +=)"),
    ("actor", "count", 0x29B54C, "dec ax",
     (0x29B515,0x29B54F,(0x29B515,0x29B519,0x29B51F,0x29B522,0x29B54C),None),
     "the same: the hold +2 -= 1 a tick instead of the move; while it is 41..44 the "
     "part tests for hits"),
    ("actor", "dst", 0x29B5F0, "movss xmm2, dword ptr [rsi + 0x1080]", ("scale", 0x29B600),
     "the same: vel += the pull x speed a tick"),
    ("actor", "root", 0x29B613, "movss xmm1, dword ptr [rdi + 0x40]", None,
     "the same: vel *= the part's damping +40 a tick (cVec::operator*=(float)): "
     "f^(1/N)"),
    ("actor", "srcx", 0x29D487, "subss xmm1, dword ptr [rcx + 0x1080]", None,
     "em56 slot 49 (29D3B0): y -= speed a tick while above the band 60 over its ground"),
    ("actor", "srcx", 0x29EB4E, "subss xmm1, dword ptr [rcx + 0x1080]", None,
     "em57..em59 slot 49 (29EB00): the same"),
    ("actor", "srcx", 0x29EB85, "addss xmm1, dword ptr [rcx + 0x1080]", None,
     "the same: y += speed a tick while below the band 80 over its ground"),
    ("actor", "count", 0x29EF4A, "mov byte ptr [rdi + 0x1136], al", None,
     "em56..em59 update (29EE50): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "blend", 0x2AD056, "movss xmm2, dword ptr [rip + 0x3cb832]",
     (0x678890, 0.029999999329447746),
     "em60 (2ACCF0): x and z += (the point - pos) x 0.03 a tick toward a point "
     "circling its target (cVec::operator*(float), +=)"),
    ("actor", "blend", 0x2AD095, "mulss xmm1, dword ptr [rip + 0x3c588f]",
     (0x67292C, 0.20000000298023224),
     "the same: y += (the point's y - y) x 0.2 a tick"),
    ("actor", "count", 0x2B4136, "mov byte ptr [rcx + 0x1560], al", None,
     "em60 (2B4120, from its slot 25 every tick): +1560 -= 1 a tick while above 0"),
    ("actor", "count", 0x2B4152, "mov dword ptr [rcx + 0x11b4], eax", None,
     "the same: +11B4 -= 1 a tick while not below 0"),
    ("actor", "argscale", 0x2B5275, "movaps xmm6, xmm3", None,
     "em60 joint turn (2B5250, as em16's 26B920): the limit in xmm3, copied to xmm6 "
     "for the heading's clamp"),
    ("actor", "argscale", 0x2B5278, "movaps xmm7, xmm2", None,
     "the same: the limit in xmm2, copied to xmm7 for the pitch's clamp"),
    ("actor", "srcx", 0x2BD9D7, "addss xmm0, xmm8", None,
     "em62 slot 25 (2BD880): each part's colour r (+50) += 0.05 a tick back to 1 once "
     "it is not hurt"),
    ("actor", "srcx", 0x2BD9F2, "addss xmm0, xmm8", None,
     "the same: g (+54)"),
    ("actor", "srcx", 0x2BDA0D, "addss xmm0, xmm8", None,
     "the same: b (+58)"),
    ("actor", "pre", 0x2C0682, "addss xmm0, dword ptr [rbx + 0x171c]", None,
     "em65 (2C05E0, from its slot 8 and 2C3160 every tick): +171C += 0.05 + 0.02 x a "
     "random share a tick; past 1 the frame +171B steps (of 4) and it wraps"),
    ("actor", "count", 0x2C789F, "inc dword ptr [rbx + 0x175c]", None,
     "em65 (2C7460): +175C += 1 a tick while its timer +16B8 is past 41"),
    ("actor", "count", 0x2C8A47, "mov byte ptr [rcx + 0x1724], al", None,
     "em65 (2C8A10, from its slot 25 every tick): +1724 -= 1 a tick while above 0"),
    ("actor", "srcx", 0x2C9190, "subss xmm1, xmm0", None,
     "the same: +1738 -= 1 a tick (9999 in state (2, 2), to end it at once)"),
    ("actor", "argscale", 0x2C9325, "movaps xmm6, xmm3", None,
     "em65 joint turn (2C9300, as em16's 26B920): the limit in xmm3, copied to xmm6"),
    ("actor", "argscale", 0x2C9328, "movaps xmm7, xmm2", None,
     "the same: the limit in xmm2, copied to xmm7"),
    ("actor", "srcx", 0x2CABF7, "subss xmm0, xmm1", None,
     "em68 slot 25 (2CA9C0): +123C -= speed a tick while above 0 (xmm1 the speed)"),
    ("actor", "srcx", 0x2CAC0B, "subss xmm0, xmm1", None,
     "the same: +1240 -= speed a tick; below 0 a sound and it acts"),
    ("actor", "lin", 0x2CBFE3, "subss xmm0, dword ptr [rip + 0x3a6a55]",
     (0x672A40, 0.009999999776482582),
     "em68 slot 24 (2CBF20): its fade +115C -= 0.01 a tick (a partner's with it)"),
    ("actor", "lin", 0x2CC778, "mulss xmm0, dword ptr [rip + 0x3a87d8]", (0x674F58, 3.0),
     "em68 (2CC370): y -= speed x 3 a tick while higher than +1074 - 100"),
    ("actor", "count", 0x2CE968, "mov byte ptr [rbx + 0x1136], al", None,
     "em69 update (2CE8E0): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "srcx", 0x2D4963, "subss xmm0, xmm2", None,
     "em6a slot 16 (2D48E0): +11A4 -= |4 sin +11A0| a tick until below 0"),
    ("actor", "count", 0x2D8C1C, "mov byte ptr [rbx + 0x1136], al", None,
     "em8f update (2D8BB0): the slot-8 effect spawner, one every 3 ticks"),
    ("actor", "count", 0x2D9A0A, "mov word ptr [rdi + 0xe40], r8w", None,
     "em8f (2D9940): its bob's phase +E40 += 1 a tick in degrees (as 2D9615's)"),
    ("scenery", "count", 0x340060, "movss dword ptr [rbx + 0x1128], xmm0", None,
     "cEnemyObj slot 19 (340030): its hit shake +1128 *= -0.4 a tick (a negative "
     "factor, no root): the store on stock ticks, stock's sequence"),
    ("scenery", "count", 0x340078, "movss dword ptr [rbx + 0x112c], xmm0", None,
     "the same: +112C *= -0.4 a tick"),
    ("scenery", "count", 0x340093, "mov byte ptr [rbx + 0x129a], al", None,
     "the same: +129A -= 1 a tick while above 0"),
    ("scenery", "count", 0x34034A, "movss dword ptr [rbx + 0x1128], xmm0", None,
     "cEnemyObj (3402F0, from its update 340440 every tick): +1128 *= -0.4 a tick, the "
     "store on stock ticks"),
    ("scenery", "count", 0x340362, "movss dword ptr [rbx + 0x112c], xmm0", None,
     "the same: +112C *= -0.4 a tick"),
    ("scenery", "lin", 0x343400, "movss xmm2, dword ptr [rip + 0x338298]", (0x67B6A0, 0.015625),
     "cEnemyObj slot 28 (343060): seven materials' V offsets -= or += 1/64 a tick "
     "after its motion advance (xmm2, read by those seven only)"),
    ("actor", "count", 0x4A1D85, "mov byte ptr [rbx + 0x1079], al", None,
     "cMonsterGear update (4A1A80): +1079 -= 1 a tick while above 0 (reloaded with 30 "
     "after a sound)"),
    ("actor", "count", 0x4A22B9, "mov byte ptr [rcx + 0x1078], al", None,
     "cMonsterGear (4A22A0): +1078 -= 1 a tick while above 0"),
    ("actor", "count", 0x4A2406, "mov byte ptr [rdi + 0x1078], al", None,
     "cMonsterGear (4A23C0): the same countdown while Amaterasu is within 500"),
    ("actor", "count", 0x4A3236, "mov byte ptr [rbx + 0xe35], al", None,
     "cMonsterGear spring (4A3120): +E35 -= 1 a tick while above 0"),
    ("actor", "srcx", 0x5C650F, "addss xmm0, xmm8", None,
     "em85 update (5C6450): two materials' U += xmm8 a tick, wrapped at 2"),
    ("actor", "pre", 0x5C6927, "addss xmm0, dword ptr [rdi + 0x3498]", None,
     "the same: +3498 += +34A0 a tick up to +34A8, a material's level"),
    ("actor", "srcx", 0x5C69BD, "addss xmm0, xmm8", None,
     "the same: two materials' U += xmm8 a tick, wrapped at 2"),
    ("actor", "argscale", 0x5CCDB5, "movaps xmm6, xmm3", None,
     "em85 joint turn (5CCD90, as em16's 26B920): the limit in xmm3, copied to xmm6"),
    ("actor", "argscale", 0x5CCDB8, "movaps xmm7, xmm2", None,
     "the same: the limit in xmm2, copied to xmm7"),
    ("actor", "count", 0x5CD6DE, "inc dword ptr [rcx + 0x3490]", None,
     "em85 (5CD690, from its update every tick): +3490 += 1 a tick while +348C is not "
     "above 0; past 3, +348C = 100"),
    ("actor", "count", 0x5CD7AE, "inc dword ptr [rcx + 0x3490]", None,
     "em85 (5CD760): the same"),
    ("actor", "srcblend", 0x5D17B0, "mulss xmm1, xmm8", None,
     "em86 (5D1080): x += (the target - x) x 0.1 a tick (xmm8's 0.1 is also passed to "
     "a call at 5D16D9: the copy is blended)"),
    ("actor", "srcblend", 0x5D17CE, "mulss xmm1, xmm8", None,
     "the same: z"),
    ("actor", "srcblend", 0x5D1FE5, "mulss xmm1, xmm9", None,
     "em86 (5D1810): x += (the target - x) x 0.1 a tick (xmm9, read elsewhere too)"),
    ("actor", "srcblend", 0x5D2007, "mulss xmm1, xmm9", None,
     "the same: z"),
    ("actor", "blend", 0x5D222A, "mulss xmm1, dword ptr [rip + 0xa53be]",
     (0x6775F0, 0.05000000074505806),
     "em86 (5D2050): y += (50 - y) x 0.05 a tick"),
    ("actor", "count", 0x5D2498, "mov dword ptr [rbx + 0x5424], eax", None,
     "the same: +5424 -= 1 a tick while not 0 (15); meanwhile +544C *= 0.5 a tick (the "
     "decay factors' 5D249E)"),
    ("actor", "blend", 0x5D25B0, "mulss xmm0, dword ptr [rip + 0xa0488]",
     (0x672A40, 0.009999999776482582),
     "em86 (5D24F0): x *= 0.99 a tick, toward 0 (x - x x 0.01)"),
    ("actor", "blend", 0x5D25CF, "mulss xmm0, dword ptr [rip + 0xa0469]",
     (0x672A40, 0.009999999776482582),
     "the same: z"),
    ("actor", "count", 0x5D2ACE, "inc dword ptr [rdi + 0x53fc]", None,
     "the same: +53FC += 1 a tick while Amaterasu is higher than 150; past 180 it acts"),
    ("actor", "count", 0x5D3867, "mov dword ptr [rbx + 0x53e4], eax", None,
     "em86 (5D3600): +53E4 -= 1 a tick while above 0 (then 90 after a sound)"),
    ("actor", "srcblend", 0x5D38F6, "mulss xmm0, xmm7", None,
     "the same: heading += wrap(its target angle - heading) x k a tick, k 0.035 (or "
     "0.015 plus a share) in xmm7"),
    ("actor", "pre", 0x5D57EA, "addss xmm0, dword ptr [rbx + 0x53a0]", None,
     "em87 update (5D5780): +53A0 += +53A8 a tick up to 1, a material's level"),
    ("actor", "srcx", 0x5D586F, "addss xmm0, xmm7", None,
     "the same: three materials' U += xmm7 a tick, wrapped"),
    ("actor", "pre", 0x5D5910, "addss xmm0, dword ptr [rbx + 0x53a0]", None,
     "the same, in the other branch: +53A0 += +53A8 a tick up to 1"),
    ("actor", "srcx", 0x5D598F, "addss xmm0, xmm7", None,
     "the same: three materials' U += xmm7 a tick, wrapped"),
    ("actor", "blend", 0x5DABD9, "mulss xmm0, dword ptr [rip + 0x97227]", (0x671E08, 0.5),
     "em87 (5DA9A0): heading += wrap(its target angle - heading) x 0.5 a tick"),
    ("actor", "blend", 0x5DB665, "mulss xmm1, dword ptr [rip + 0x96797]",
     (0x671E04, 0.10000000149011612),
     "em87 (5DB470): x += (the target - x) x 0.1 a tick"),
    ("actor", "blend", 0x5DB686, "mulss xmm1, dword ptr [rip + 0x96776]",
     (0x671E04, 0.10000000149011612),
     "the same: z"),
    ("actor", "argscale", 0x5DD935, "movaps xmm6, xmm3", None,
     "em87 joint turn (5DD910, as em16's 26B920): the limit in xmm3, copied to xmm6"),
    ("actor", "argscale", 0x5DD938, "movaps xmm7, xmm2", None,
     "the same: the limit in xmm2, copied to xmm7"),
    ("actor", "argscale", 0x5EA2A5, "movaps xmm6, xmm3", None,
     "em88 joint turn (5EA280): the limit in xmm3, copied to xmm6"),
    ("actor", "argscale", 0x5EA2A8, "movaps xmm7, xmm2", None,
     "the same: the limit in xmm2, copied to xmm7"),
    ("actor", "count", 0x5EB522, "inc dword ptr [rbx + 0x50c4]", None,
     "em89 (5EB440, from its updates every tick): +50C4 += 1 a tick while +5090 runs; "
     "past 900 a story flag"),
    ("actor", "count", 0x5EB5A4, "dec dword ptr [rbx + 0x5090]", None,
     "the same: +5090 -= 1 a tick (30)"),
    ("actor", "count", 0x5EB6D0, "dec eax",
     (0x5EB6C6,0x5EB6D2,(0x5EB6C6,0x5EB6CC,0x5EB6CE,0x5EB6D0),None),
     "the same: +5014 -= 1 a tick while above 0"),
    ("actor", "pre", 0x5EC810, "addss xmm0, dword ptr [rbx + 0x5098]", None,
     "em89 update (5EC0F0): +5098 += +50A0 a tick up to 1, a material's level"),
    ("actor", "pre", 0x5EC881, "addss xmm0, dword ptr [rbx + 0x5098]", None,
     "the same, for the next material"),
    ("actor", "srcx", 0x5EC924, "addss xmm0, xmm7", None,
     "the same: its materials' U += xmm7 a tick, wrapped"),
    ("actor", "blend", 0x5EE9A3, "mulss xmm1, dword ptr [rip + 0x8b285]",
     (0x679C30, 0.019999999552965164),
     "em89 (5EE760): y += (300 - y) x 0.02 a tick once its clock is past 20"),
    ("actor", "blend", 0x5EE9C7, "mulss xmm1, dword ptr [rip + 0x89ec1]",
     (0x678890, 0.029999999329447746),
     "the same: y += (100 - y) x 0.03 a tick before"),
    ("actor", "dst", 0x5EF90F, "mulss xmm0, dword ptr [rsi + 0x1080]", None,
     "em89 (5EF560): heading += +5074 degrees x speed a tick (its spin, +5074 between "
     "-1.5 and 1.5; xmm0 the step, added next)"),
    ("actor", "blend", 0x5F2062, "mulss xmm1, dword ptr [rip + 0x7fd9a]",
     (0x671E04, 0.10000000149011612),
     "em89 (5F1DF0): x += (the target - x) x 0.1 a tick"),
    ("actor", "blend", 0x5F2083, "mulss xmm1, dword ptr [rip + 0x7fd79]",
     (0x671E04, 0.10000000149011612),
     "the same: z"),
    ("actor", "count", 0x5F2873, "dec eax",
     (0x5F2866,0x5F2875,(0x5F2866,0x5F286C,0x5F286F,0x5F2871,0x5F2873),None),
     "em89 (5F2860): +507C -= 1 a tick while above 0"),
    ("actor", "root", 0x5F2D15, "addss xmm3, dword ptr [rip + 0x86c43]", None,
     "em89 (5F2A60): +5060 *= 0.98 + 0.02 x |x| a tick (xmm3 the factor): f^(1/N)"),
    ("actor", "srcblend", 0x5F2D72, "mulss xmm0, xmm7", None,
     "the same: heading += wrap(target - heading) x k a tick, k 0.055 or 0.025 in xmm7"),
    ("actor", "argscale", 0x5F4755, "movaps xmm6, xmm3", None,
     "em89 joint turn (5F4730): the limit in xmm3, copied to xmm6"),
    ("actor", "argscale", 0x5F4758, "movaps xmm7, xmm2", None,
     "the same: the limit in xmm2, copied to xmm7"),
    ("actor", "srcblend", 0x5F5647, "mulss xmm0, xmm7", None,
     "em89 (5F5600): heading += wrap(target - heading) x k a tick, k the argument in "
     "xmm2 (copied to xmm7)"),
    # --- pl00's update (3A9630, vt68B280 slot 8), Amaterasu ------------------
    ("player", "count", 0x3A98E1, "mov byte ptr [rsi + 0xd78], al", None,
     "pl00 update: Amaterasu's alpha +D78 near the camera, a byte set to (a + (t - a) "
     "x 0.3) x 255 a tick toward a target by distance: stored on stock ticks, stock's "
     "sequence"),
    ("player", "count", 0x3A9920, "mov byte ptr [rsi + 0xd78], al", None,
     "pl00 update: the alpha +D78 back to opaque, a + max(1/255, (1 - a) x 0.3) a "
     "tick: stored on stock ticks"),
    ("player", "count", 0x3A9941, "mov byte ptr [rcx + 0xd78], al", None,
     "pl00 update: the alpha +D78 -= 25 a tick while B664DC bit 0 fades her out: "
     "stored on stock ticks"),
    ("player", "count", 0x3A9B7A, "add byte ptr [rsi + 0x15c2], 0xff", None,
     "pl00 update: +15C2, the three ticks' grace after the B6B2A3 pause mode (3AD034 "
     "tests it): a tick each on stock ticks; skipped, the cmovs reads SF clear"),
    ("player", "count", 0x3A9C6F, "mov byte ptr [rsi + 0x1178], al", None,
     "pl00 update: countdown +1178, a tick each"),
    ("player", "count", 0x3A9D15, "inc byte ptr [rsi + 0x1176]", None,
     "pl00 update: +1176 counts the ticks a button is held, a tick each"),
    ("player", "count", 0x3A9D28, "mov byte ptr [rsi + 0x117d], al", None,
     "pl00 update: countdown +117D, a tick each"),
    ("player", "notyet", 0x3A9E07, "test al, 1", 0x3A9ECA,
     "pl00 update: the slide-off push, +10C0/+10C8 += 2 x (+FE0, +FE8) (and +1 when "
     "that is small) while she falls onto something (+1010 bit 7, near the ground, "
     "+E54 < 0), with its sound and 3A78E0: on stock ticks only, as the velocity's "
     "other changes"),
    ("player", "srcx", 0x3A9ED5, "addss xmm0, dword ptr [rsi + 0x10c0]", None,
     "pl00 update: the slide, x += +10C0 a tick: s of it (the velocity keeps stock's "
     "value, its push and damping on stock ticks)"),
    ("player", "pre", 0x3A9F09, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 update: the slide, z += +10C8 a tick (xmm0 holds +10C8): s of it"),
    ("player", "countlast", 0x3A9F37, "mulss xmm1, xmm7", None,
     "pl00 update: the slide's damping +10C0 x 0.9 a tick: on the last tick of each "
     "stock period, after that period's moves, as stock orders it"),
    ("player", "countlast", 0x3A9F3B, "mulss xmm2, xmm7", None,
     "pl00 update: the slide's damping +10C8 x 0.9 a tick, on the last tick of each "
     "stock period"),
    ("player", "countlast", 0x3A9F55, "mulss xmm1, xmm13", None,
     "pl00 update: the slide's ground friction +10C0 x 0.7 a tick (on the ground), on "
     "the last tick of each stock period"),
    ("player", "countlast", 0x3A9F5A, "mulss xmm2, xmm13", None,
     "pl00 update: the slide's ground friction +10C8 x 0.7 a tick, on the last tick of "
     "each stock period"),
    ("player", "count", 0x3A9FE1, "mov word ptr [rsi + 0x117a], ax", None,
     "pl00 update: countdown +117A (calls 3CC950 every 8 ticks), a tick each"),
    ("player", "notyet", 0x3A9FE8, "test al, 7", 0x3A9FF6,
     "pl00 update: +117A's every-8-ticks test reads the decremented register: between "
     "stock ticks, not yet"),
    ("player", "count", 0x3AA01D, "mov word ptr [rip + 0x7a3f94], ax", None,
     "pl00 update: item timer B4DFB8 (900 ticks, set by 3D0050 for item type 4 in "
     "413370, spawning effect 0x31 every 32 ticks), a tick each"),
    ("player", "notyet", 0x3AA03D, "test byte ptr [rip + 0x7a3f74], 0x1f", 0x3AA0AD,
     "pl00 update: B4DFB8's every-32-ticks effect test (the stored value): between "
     "stock ticks, not yet"),
    ("player", "count", 0x3AA0D1, "mov word ptr [rip + 0x7a3ee2], ax", None,
     "pl00 update: item timer B4DFBA (900 ticks from 3D0000, effect 0x33 every 32 "
     "ticks), a tick each"),
    ("player", "notyet", 0x3AA0D8, "test al, 0x1f", 0x3AA14D,
     "pl00 update: B4DFBA's every-32-ticks effect test: between stock ticks, not yet"),
    ("player", "count", 0x3AA167, "mov word ptr [rip + 0x7a3e4e], ax", None,
     "pl00 update: item timer B4DFBC (from 3D0010, effect 0x32 every 32 ticks), a tick "
     "each"),
    ("player", "notyet", 0x3AA174, "test al, 0x1f", 0x3AA1F3,
     "pl00 update: B4DFBC's every-32-ticks effect test: between stock ticks, not yet"),
    ("player", "count", 0x3AA208, "inc byte ptr [rsi + 0x117f]", None,
     "pl00 update: +117F counts up while 3CE4C0 holds, effect 0x28 every 8 ticks, a "
     "tick each"),
    ("player", "notyet", 0x3AA20E, "test byte ptr [rsi + 0x117f], 7", 0x3AA266,
     "pl00 update: +117F's every-8-ticks test (the stored byte): between stock ticks, "
     "not yet"),
    ("player", "count", 0x3AA275, "mov word ptr [rsi + 0x11e6], ax", None,
     "pl00 update: countdown +11E6, a tick each"),
    ("player", "count", 0x3AA437, "mov word ptr [rsi + 0x1186], ax", None,
     "pl00 update: countdown +1186, a tick each"),
    ("player", "count", 0x3AA44D, "mov word ptr [rsi + 0x11e4], ax", None,
     "pl00 update: countdown +11E4, a tick each"),
    ("player", "count", 0x3AA468, "sub ax, 1",
     (0x3AA45C,0x3AA46C,(0x3AA45C,0x3AA463,0x3AA466,0x3AA468),None),
     "pl00 update: countdown +1188 (+118C cleared at 0), a tick each; skipped, the jne "
     "reads \"not finished\""),
    ("player", "count", 0x3AA543, "mov byte ptr [rsi + 0x11ef], al", None,
     "pl00 update: countdown +11EF, a tick each"),
    ("player", "count", 0x3AA6B9, "dec dword ptr [rip + 0x61e065]", None,
     "pl00 update: the global countdown 9C8724 that holds her in its own path, a tick "
     "each"),
    ("player", "count", 0x3AA74D, "mov byte ptr [rsi + 0x117e], al", None,
     "pl00 update: +117E, a material crossfade (1 - v/255, v/255), -10 a tick: on "
     "stock ticks"),
    ("player", "count", 0x3AA814, "mov byte ptr [rsi + 0x117e], al", None,
     "pl00 update: +117E, +10 a tick: on stock ticks"),
    ("player", "count", 0x3AAD63, "add byte ptr [rsi + 0x1144], 0xff", None,
     "pl00 update: +1144, the lock-on retarget delay (B6AC44 x 2 ticks before +1110 "
     "takes +1108), a tick each; skipped, the jne reads \"not yet\""),
    ("player", "count", 0x3AB234, "movss dword ptr [rsi + 0xe48], xmm0", None,
     "pl00 update: her speed +E48 x 0.5 when the rise meets a ceiling (+E54 > 1): once "
     "per stock tick, as stock's tick-long contact"),
    ("player", "srcblend", 0x3AC5F6, "mulss xmm1, xmm10", None,
     "pl00 update: her pitch +B0 approaches the ground's slope by 0.3 a tick (xmm10 = "
     "0.3 is also 3ACAEB's alpha threshold)"),
    ("player", "srcblend", 0x3AC6CB, "mulss xmm1, xmm10", None,
     "pl00 update: her pitch +B0 returns to level by 0.3 a tick in the air"),
    # --- wp02's beads (382340, one of six per call from 3822D0): a rosary's shots
    ("player", "lin", 0x3827F7, "addss xmm0, dword ptr [rip + 0x2f747d]",
     (0x679C7C, 0.800000011920929),
     "wp02 bead, homing (state 3): its rate +1938 += 0.8 a tick up to 8 (turn in "
     "degrees x 2 and forward speed)"),
    ("player", "lin", 0x38284D, "mulss xmm0, dword ptr [rip + 0x2f00d3]",
     (0x672928, 0.01745329238474369),
     "wp02 bead, homing: the turn toward the target, rate x pi/180 x 2 a tick, passed "
     "to 2DE2A0: s of it"),
    ("player", "pre", 0x3828BF, "addss xmm0, dword ptr [r12]", None,
     "wp02 bead, homing: x += the forward step (rate, in the bead's frame) a tick: s "
     "of it; the velocity +16E0 keeps stock's value"),
    ("player", "pre", 0x3828CB, "addss xmm1, dword ptr [r15 + rdi + 0x1294]", None,
     "wp02 bead, homing: y += the forward step's y, s of it"),
    ("player", "pre", 0x3828E1, "addss xmm0, dword ptr [r15 + rdi + 0x1298]", None,
     "wp02 bead, homing: z += the forward step's z, s of it"),
    ("player", "count", 0x382A83, "sub byte ptr [rcx], 1", None,
     "wp02 bead, homing: its countdown (param 4), a tick each; skipped, the jne reads "
     "\"not yet\""),
    ("player", "pre", 0x382B74, "addss xmm0, dword ptr [r12]", None,
     "wp02 bead, bounced off (state 5): x += v.x a tick (xmm0 holds +16E0): s of it"),
    ("player", "srcx", 0x382B8A, "addss xmm0, dword ptr [rdi + rax*8 + 0x16e4]", None,
     "wp02 bead, bounced off: y += v.y a tick: s of it"),
    ("player", "pre", 0x382BA6, "addss xmm0, dword ptr [r15 + rdi + 0x1298]", None,
     "wp02 bead, bounced off: z += v.z a tick (xmm0 holds +16E8): s of it"),
    ("player", "countlast", 0x382BBF, "mulss xmm0, dword ptr [rip + 0x2f2e79]", None,
     "wp02 bead, bounced off: v.x x 0.93 a tick, on the last tick of each stock period "
     "after its moves"),
    ("player", "countlast", 0x382BD0, "subss xmm1, dword ptr [rip + 0x2ef234]", None,
     "wp02 bead, bounced off: v.y -= 0.6 (gravity) a tick, on the last tick of each "
     "stock period"),
    ("player", "countlast", 0x382BE6, "mulss xmm0, dword ptr [rip + 0x2f2e52]", None,
     "wp02 bead, bounced off: v.z x 0.93 a tick, on the last tick of each stock period"),
    ("player", "count", 0x382C1B, "mov byte ptr [rbx], al", None,
     "wp02 bead, bounced off: its countdown, a tick each"),
    ("player", "notyet", 0x382C1D, "test cl, cl", 0x382636,
     "wp02 bead, bounced off: the test of the countdown's old value (0 ends the "
     "state): between stock ticks, not yet"),
    ("player", "pre", 0x382CDF, "addss xmm0, dword ptr [r12]", None,
     "wp02 bead, dash (state 7): x += the step (20 forward in its frame) a tick: s of "
     "it"),
    ("player", "pre", 0x382CEB, "addss xmm1, dword ptr [r15 + rdi + 0x1294]", None,
     "wp02 bead, dash: y += the step's y, s of it"),
    ("player", "pre", 0x382D01, "addss xmm0, dword ptr [r15 + rdi + 0x1298]", None,
     "wp02 bead, dash: z += the step's z, s of it"),
    ("player", "count", 0x382D4F, "mov byte ptr [rbx], al", None,
     "wp02 bead, dash: its countdown (2), a tick each"),
    ("player", "notyet", 0x382D51, "test cl, cl", 0x382636,
     "wp02 bead, dash: the test of the countdown's old value: between stock ticks, not "
     "yet"),
    ("player", "blend", 0x382E13, "mulss xmm0, dword ptr [rip + 0x2efb11]",
     (0x67292C, 0.20000000298023224),
     "wp02 bead, lying (state 8): y approaches its rest height +11CA by 0.2 a tick"),
    ("player", "count", 0x382E2F, "mov byte ptr [rdx], al", None,
     "wp02 bead, lying: its countdown (60), a tick each"),
    ("player", "notyet", 0x382E31, "test cl, cl", 0x382E5E,
     "wp02 bead, lying: the test of the countdown's old value: between stock ticks, "
     "not yet"),
    ("player", "lin", 0x382FCD, "mulss xmm0, dword ptr [rip + 0x2ef953]",
     (0x672928, 0.01745329238474369),
     "wp02 bead, homing again: the turn, rate x pi/180 x 4 a tick: s of it"),
    ("player", "pre", 0x383043, "addss xmm0, dword ptr [r12]", None,
     "wp02 bead, homing again: x += the forward step a tick, s of it"),
    ("player", "pre", 0x38304F, "addss xmm1, dword ptr [r15 + rdi + 0x1294]", None,
     "wp02 bead, homing again: y += the forward step's y, s of it"),
    ("player", "pre", 0x383065, "addss xmm0, dword ptr [r15 + rdi + 0x1298]", None,
     "wp02 bead, homing again: z += the forward step's z, s of it"),
    ("player", "count", 0x38317E, "sub byte ptr [rcx], 1", None,
     "wp02 bead, homing again: its countdown, a tick each; skipped, the jne reads \"not "
     "yet\""),
    ("player", "pre", 0x383313, "addss xmm0, dword ptr [r12]", None,
     "wp02 bead, launched (state 13): x += v.x a tick (xmm0 holds +16E0): s of it"),
    ("player", "srcx", 0x383329, "addss xmm0, dword ptr [rdi + rax*8 + 0x16e4]", None,
     "wp02 bead, launched: y += v.y a tick: s of it"),
    ("player", "pre", 0x383345, "addss xmm0, dword ptr [r15 + rdi + 0x1298]", None,
     "wp02 bead, launched: z += v.z a tick (xmm0 holds +16E8): s of it"),
    ("player", "countlast", 0x383367, "mulss xmm1, xmm2", None,
     "wp02 bead, launched: v.y x 0.98 a tick, on the last tick of each stock period "
     "after its moves"),
    ("player", "countlast", 0x38336B, "mulss xmm0, xmm2", None,
     "wp02 bead, launched: v.x x 0.98 a tick, on the last tick of each stock period"),
    ("player", "countlast", 0x383381, "mulss xmm1, xmm2", None,
     "wp02 bead, launched: v.z x 0.98 a tick, on the last tick of each stock period"),
    ("player", "count", 0x383439, "sub byte ptr [rcx], r14b", "down",
     "wp02 bead, launched: its countdown (10), a tick each: sub by r14b, which is 1 "
     "(set at 382546 before the switch, not written on this path); skipped, the jne "
     "reads \"not yet\""),
    # --- wp3a's beads (397C70, from 397B70)
    ("player", "pre", 0x3981C1, "addss xmm1, dword ptr [rbx + rsi + 0x1294]", None,
     "wp3a bead, homing (state 3): y += the forward step (18 in its frame, toward a "
     "jittered target) a tick: s of it"),
    ("player", "pre", 0x3981CA, "addss xmm0, dword ptr [rdi]", None,
     "wp3a bead, homing: x += the step's x, s of it"),
    ("player", "pre", 0x3981E1, "addss xmm0, dword ptr [rbx + rsi + 0x1298]", None,
     "wp3a bead, homing: z += the step's z, s of it"),
    ("player", "count", 0x3982E0, "sub byte ptr [r12], 1", None,
     "wp3a bead, homing: its countdown (param 4), a tick each; skipped, the jne reads "
     "\"not yet\""),
    ("player", "pre", 0x398436, "addss xmm0, dword ptr [rdx]", None,
     "wp3a bead, bounced off (state 5): x += v.x a tick (xmm0 holds +16E0): s of it"),
    ("player", "srcx", 0x398447, "addss xmm0, dword ptr [rsi + rcx*8 + 0x16e4]", None,
     "wp3a bead, bounced off: y += v.y a tick: s of it"),
    ("player", "srcx", 0x398462, "addss xmm0, dword ptr [rsi + rcx*8 + 0x16e8]", None,
     "wp3a bead, bounced off: z += v.z a tick: s of it"),
    ("player", "countlast", 0x39847A, "mulss xmm0, dword ptr [rip + 0x2dd5be]", None,
     "wp3a bead, bounced off: v.x x 0.93 a tick, on the last tick of each stock period "
     "after its moves"),
    ("player", "countlast", 0x39848B, "subss xmm1, dword ptr [rip + 0x2d9979]", None,
     "wp3a bead, bounced off: v.y -= 0.6 (gravity), on the last tick of each stock "
     "period"),
    ("player", "countlast", 0x3984A2, "mulss xmm0, dword ptr [rip + 0x2dd596]", None,
     "wp3a bead, bounced off: v.z x 0.93, on the last tick of each stock period"),
    ("player", "count", 0x3984D6, "mov byte ptr [r12], al", None,
     "wp3a bead, bounced off: its countdown (5), a tick each"),
    ("player", "notyet", 0x3984DA, "test cl, cl", 0x39888D,
     "wp3a bead, bounced off: the test of the countdown's old value: between stock "
     "ticks, not yet"),
    ("player", "pre", 0x3986AC, "addss xmm0, dword ptr [rdi]", None,
     "wp3a bead, launched (state 13): x += v.x a tick (random +-5, +-5, 15 in the "
     "owner's frame, set once): s of it"),
    ("player", "pre", 0x3986C0, "addss xmm0, dword ptr [rbx + rsi + 0x1294]", None,
     "wp3a bead, launched: y += v.y a tick, s of it"),
    ("player", "pre", 0x3986DB, "addss xmm1, dword ptr [rbx + rsi + 0x1298]", None,
     "wp3a bead, launched: z += v.z a tick, s of it"),
    ("player", "count", 0x398792, "sub byte ptr [r12], 1", None,
     "wp3a bead, launched: its countdown (12), a tick each; skipped, the jne reads "
     "\"not yet\""),
    ("player", "count", 0x398833, "sub byte ptr [r12], 1", None,
     "wp3a bead (state 15): its countdown, a tick each; skipped, the jne reads \"not "
     "yet\""),
    # --- wp3a's second and third bead kinds (398920, 399590, from 397B70; the same code)
    ("player", "lin", 0x398D3D, "addss xmm0, dword ptr [rip + 0x2da197]", (0x672EDC, 20.0),
     "wp3a bead kind 2, flight (state 3): its speed +1938 += 20 a tick from 5 up to "
     "100"),
    ("player", "pre", 0x398DD2, "addss xmm1, dword ptr [rbx + rsi + 0x1294]", None,
     "wp3a bead kind 2, flight: y += the forward step (the speed, in its frame) a "
     "tick: s of it"),
    ("player", "pre", 0x398DDB, "addss xmm0, dword ptr [r12]", None,
     "wp3a bead kind 2, flight: x += the step's x, s of it"),
    ("player", "pre", 0x398DF6, "addss xmm0, dword ptr [rbx + rsi + 0x1298]", None,
     "wp3a bead kind 2, flight: z += the step's z, s of it"),
    ("player", "count", 0x398F48, "sub byte ptr [r15], 1", None,
     "wp3a bead kind 2, flight: its countdown (param 4), a tick each; skipped, the jne "
     "reads \"not yet\""),
    ("player", "pre", 0x39909A, "addss xmm0, dword ptr [rdx]", None,
     "wp3a bead kind 2, bounced off (state 5): x += v.x a tick (xmm0 holds +16E0): s "
     "of it"),
    ("player", "srcx", 0x3990AB, "addss xmm0, dword ptr [rsi + rcx*8 + 0x16e4]", None,
     "wp3a bead kind 2, bounced off: y += v.y a tick: s of it"),
    ("player", "srcx", 0x3990C6, "addss xmm0, dword ptr [rsi + rcx*8 + 0x16e8]", None,
     "wp3a bead kind 2, bounced off: z += v.z a tick: s of it"),
    ("player", "countlast", 0x3990DE, "mulss xmm0, dword ptr [rip + 0x2dc95a]", None,
     "wp3a bead kind 2, bounced off: v.x x 0.93, on the last tick of each stock period "
     "after its moves"),
    ("player", "countlast", 0x3990EF, "subss xmm1, dword ptr [rip + 0x2d8d15]", None,
     "wp3a bead kind 2, bounced off: v.y -= 0.6 (gravity), on the last tick of each "
     "stock period"),
    ("player", "countlast", 0x399106, "mulss xmm0, dword ptr [rip + 0x2dc932]", None,
     "wp3a bead kind 2, bounced off: v.z x 0.93, on the last tick of each stock period"),
    ("player", "count", 0x399139, "mov byte ptr [r15], al", None,
     "wp3a bead kind 2, bounced off: its countdown, a tick each"),
    ("player", "notyet", 0x39913C, "test cl, cl", 0x3994F5,
     "wp3a bead kind 2, bounced off: the test of the countdown's old value: between "
     "stock ticks, not yet"),
    ("player", "pre", 0x3992D4, "addss xmm0, dword ptr [r12]", None,
     "wp3a bead kind 2, launched (state 13): x += v.x a tick (xmm0 holds +16E0): s of "
     "it"),
    ("player", "pre", 0x3992EC, "addss xmm0, dword ptr [rbx + rsi + 0x1294]", None,
     "wp3a bead kind 2, launched: y += v.y a tick, s of it"),
    ("player", "pre", 0x399307, "addss xmm1, dword ptr [rbx + rsi + 0x1298]", None,
     "wp3a bead kind 2, launched: z += v.z a tick, s of it"),
    ("player", "count", 0x399410, "sub byte ptr [r15], 1", None,
     "wp3a bead kind 2, launched: its countdown, a tick each; skipped, the jne reads "
     "\"not yet\""),
    ("player", "count", 0x39949C, "sub byte ptr [r15], 1", None,
     "wp3a bead kind 2 (state 15): its countdown, a tick each; skipped, the jne reads "
     "\"not yet\""),
    ("player", "lin", 0x3999AD, "addss xmm0, dword ptr [rip + 0x2d9527]", (0x672EDC, 20.0),
     "wp3a bead kind 3, flight (state 3): its speed +1938 += 20 a tick from 5 up to "
     "100"),
    ("player", "pre", 0x399A42, "addss xmm1, dword ptr [rbx + rsi + 0x1294]", None,
     "wp3a bead kind 3, flight: y += the forward step a tick: s of it"),
    ("player", "pre", 0x399A4B, "addss xmm0, dword ptr [r12]", None,
     "wp3a bead kind 3, flight: x += the step's x, s of it"),
    ("player", "pre", 0x399A66, "addss xmm0, dword ptr [rbx + rsi + 0x1298]", None,
     "wp3a bead kind 3, flight: z += the step's z, s of it"),
    ("player", "count", 0x399B81, "add byte ptr [r15], 0xff", None,
     "wp3a bead kind 3, flight: its countdown (add 0xff), a tick each; skipped, the "
     "jne reads \"not yet\""),
    ("player", "pre", 0x399CD3, "addss xmm0, dword ptr [rdx]", None,
     "wp3a bead kind 3, bounced off (state 5): x += v.x a tick: s of it"),
    ("player", "srcx", 0x399CE4, "addss xmm0, dword ptr [rsi + rcx*8 + 0x16e4]", None,
     "wp3a bead kind 3, bounced off: y += v.y a tick: s of it"),
    ("player", "srcx", 0x399CFF, "addss xmm0, dword ptr [rsi + rcx*8 + 0x16e8]", None,
     "wp3a bead kind 3, bounced off: z += v.z a tick: s of it"),
    ("player", "countlast", 0x399D17, "mulss xmm0, dword ptr [rip + 0x2dbd21]", None,
     "wp3a bead kind 3, bounced off: v.x x 0.93, on the last tick of each stock period"),
    ("player", "countlast", 0x399D28, "subss xmm1, dword ptr [rip + 0x2d80dc]", None,
     "wp3a bead kind 3, bounced off: v.y -= 0.6, on the last tick of each stock period"),
    ("player", "countlast", 0x399D3F, "mulss xmm0, dword ptr [rip + 0x2dbcf9]", None,
     "wp3a bead kind 3, bounced off: v.z x 0.93, on the last tick of each stock period"),
    ("player", "count", 0x399D72, "mov byte ptr [r15], al", None,
     "wp3a bead kind 3, bounced off: its countdown, a tick each"),
    ("player", "notyet", 0x399D75, "test cl, cl", 0x39A0FF,
     "wp3a bead kind 3, bounced off: the test of the countdown's old value: between "
     "stock ticks, not yet"),
    ("player", "pre", 0x399F0D, "addss xmm0, dword ptr [r12]", None,
     "wp3a bead kind 3, launched (state 13): x += v.x a tick: s of it"),
    ("player", "pre", 0x399F25, "addss xmm0, dword ptr [rbx + rsi + 0x1294]", None,
     "wp3a bead kind 3, launched: y += v.y a tick, s of it"),
    ("player", "pre", 0x399F40, "addss xmm1, dword ptr [rbx + rsi + 0x1298]", None,
     "wp3a bead kind 3, launched: z += v.z a tick, s of it"),
    ("player", "count", 0x39A01A, "add byte ptr [r15], 0xff", None,
     "wp3a bead kind 3, launched: its countdown, a tick each; skipped, the jne reads "
     "\"not yet\""),
    ("player", "count", 0x39A0A6, "add byte ptr [r15], 0xff", None,
     "wp3a bead kind 3 (state 15): its countdown, a tick each; skipped, the jne reads "
     "\"not yet\""),
    # --- pl00's attack lunge (3B8540, called by the dispatcher 3AF020) ----------
    ("player", "lin", 0x3B884A, "mulss xmm0, dword ptr [rip + 0x2ba0da]",
     (0x67292C, 0.20000000298023224),
     "pl00 lunge (3B8540, sub-state 2): the speed +E48 = (+F48 - 0.5) x 0.2 as it "
     "starts, a displacement per tick: +E48 is the port's per-tick-at-this-rate speed "
     "(README), so s of it"),
    ("player", "lin", 0x3B91E3, "mulss xmm0, dword ptr [rip + 0x2b9741]",
     (0x67292C, 0.20000000298023224),
     "pl00 lunge (3B8540, sub-state 8): +E48 = (+F48 - 0.5) x 0.2 as it starts: s of "
     "it"),
    ("player", "lin", 0x3B96AF, "mulss xmm0, dword ptr [rip + 0x2b9275]",
     (0x67292C, 0.20000000298023224),
     "pl00 lunge (3B8540, sub-state 11): +E48 = (+F48 - 0.5) x 0.2 as it starts: s of "
     "it"),
    ("player", "countlast", 0x3B8FA3, "mulss xmm1, dword ptr [rip + 0x2bca8d]", None,
     "pl00 lunge (3B8540): +E48 x 0.75 a tick after it moves her (added to the root "
     "step +EC8): on the last tick of each stock period, so the s-sized moves sum to "
     "stock's per stock tick"),
    # --- pl00's state 3AFA90 (the fall to defeat; sub-state 2 counts +E3E up) ---
    ("player", "count", 0x3AFEAD, "mov word ptr [rsi + 0xe3e], ax", None,
     "pl00 state 3AFA90, sub-state 2: +E3E counts up a tick each (sounds at 0x6F and "
     "0x8E, +D40 bit 1 at 0xA3): on stock ticks"),
    ("player", "notyet", 0x3AFE23, "cmp word ptr [rsi + 0xe3e], 0x6f", 0x3AFE55,
     "pl00 state 3AFA90, sub-state 2: the sound at +E3E = 0x6F: between stock ticks, "
     "not yet (the count holds its value for the stock tick's other ticks)"),
    ("player", "notyet", 0x3AFE5A, "cmp word ptr [rsi + 0xe3e], ax", 0x3AFE8F,
     "pl00 state 3AFA90, sub-state 2: the sound at +E3E = 0x8E: between stock ticks, "
     "not yet"),
    # --- wp1c (38F400, from 38EEE0): a thrown piece that rolls -----------------
    ("player", "lin", 0x38F438, "movss xmm6, dword ptr [rip + 0x2e29c8]", (0x671E08, 0.5),
     "wp1c (38F400): xmm6 = 0.5, the slope push's factor (+FE0/+FE8): its velocity "
     "+E20/+E28 is per tick at this rate (built from the owner's +E48; x += v "
     "unscaled, the damping 0.94^s by decay_factors), so the push added at the throw "
     "is s of stock's"),
    ("player", "pre", 0x38F714, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "wp1c rolling (sub-state 1): v.x += 0.5 x +FE0 a tick on the ground (xmm0 holds "
     "it, 0.5 s by the lin): s of it again, a per-tick-at-this-rate velocity gains s^2 "
     "of stock's push a tick"),
    ("player", "pre", 0x38F71C, "addss xmm1, dword ptr [rdi + 0xe28]", None,
     "wp1c rolling: v.z += 0.5 x +FE8 a tick on the ground: s of it again (s^2 in all)"),
    # --- wp1d (391D60, from 38FDF0) --------------------------------------------
    ("player", "dst", 0x391DD3, "movaps xmm7, xmm0", ("slowmo",0x391DB2),
     "wp1d (391D60): xmm7 = the slow-motion factor (23AD90), the function's dt; its "
     "readers, all per-tick steps: the spin +B4 += 6 deg x dt, +1090 += dt, the bob y "
     "+= sin(+1110) x 0.7 (1.7) x dt, its phase +1110 += 0.24 dt, the countdown +1078 "
     "-= dt, the turn min(+1078, 10) deg x dt, the flight's velocity +E18 += dt and "
     "the move by +E10 x dt, the countdown +E28 -= dt"),
    # --- pl00's state 3C7880: charging while locked on to a target ---
    ("player", "lin", 0x3C7A20, "movss xmm3, dword ptr [rip + 0x2b21e0]",
     (0x679C08, 0.13962633907794952),
     "pl00 state 3C7880, sub-state 1: turn toward the locked target by at most 8 "
     "degrees a tick; scale the limit before 2DDF90"),
    ("player", "lin", 0x3C7E71, "movss xmm3, dword ptr [rip + 0x2b1d87]",
     (0x679C00, 0.03490658476948738),
     "pl00 state 3C7880, sub-state 3: turn toward the locked target by at most 2 "
     "degrees a tick; scale the limit before 2DDF90"),
    ("player", "notyet", 0x3C7B0D, "test byte ptr [rdi + 0x1152], 7", 0x3C7B7D,
     "pl00 charge: the effect spawned at every eighth +1152 tick must wait for a stock "
     "tick while the counter is held"),
    ("player", "notyet", 0x3C7B7D, "cmp word ptr [rdi + 0x1152], r13w", 0x3C7BBE,
     "pl00 charge: the sound at +1152 = 0 must not repeat between stock ticks"),
    ("player", "count", 0x3C7BBE, "inc word ptr [rdi + 0x1152]", None,
     "pl00 charge: +1152 counts the ticks spent charging; its threshold changes the "
     "charge tier, sound and effect sequence"),
    ("player", "notyet", 0x3C7BE5, "cmp eax, ecx", 0x3C7C39,
     "pl00 charge: the paired sounds near tick 30 or 15 must play once on the "
     "counter's stock tick"),
    ("player", "notyet", 0x3C7C59, "cmp eax, ecx", 0x3C7CAD,
     "pl00 charge: the paired sounds near tick 60 or 30 must play once on the "
     "counter's stock tick"),
    ("player", "notyet", 0x3C7CF2, "cmp al, sil", 0x3C80B6,
     "pl00 charge: the repeated sound every eight ticks after the full-charge "
     "threshold must wait for a stock tick"),
    # --- wp1a's launched piece (38D880, from 38DFF0) ---
    ("player", "count", 0x38D8D8, "sub byte ptr [rbx + rdi + 0x1124], 1", None,
     "wp1a piece: the 90-tick wait in state 4, set as state 3 ends, counts down once "
     "each stock tick"),
    ("player", "pre", 0x38D931, "addss xmm0, dword ptr [rax + 0x80]", None,
     "wp1a piece in flight: x += v.x each tick; scale the old velocity in xmm0 for "
     "this move while keeping +C0 in stock units"),
    ("player", "countlast", 0x38D939, "mulss xmm3, dword ptr [rip + 0x2e4fef]", None,
     "wp1a piece in flight: v.x x 0.9 after its move, on the last tick of each stock "
     "period"),
    ("player", "pre", 0x38D959, "addss xmm0, dword ptr [rax + 0x84]", None,
     "wp1a piece in flight: y += v.y each tick; scale the old velocity in xmm0 for "
     "this move while keeping +C4 in stock units"),
    ("player", "countlast", 0x38D961, "subss xmm1, xmm6", None,
     "wp1a piece in flight: v.y -= 1 after its move, on the last tick of each stock "
     "period"),
    ("player", "countlast", 0x38D978, "mulss xmm2, dword ptr [rip + 0x2e4fb0]", None,
     "wp1a piece in flight: v.z x 0.9 after its move, on the last tick of each stock "
     "period"),
    ("player", "pre", 0x38D980, "addss xmm0, dword ptr [rax + 0x88]", None,
     "wp1a piece in flight: z += v.z each tick; scale the old velocity in xmm0 for "
     "this move while keeping +C8 in stock units"),
    ("player", "lin", 0x38D998, "movss xmm2, dword ptr [rip + 0x2ec2f0]",
     (0x679C90, 0.05235987901687622),
     "wp1a piece in flight: rotate its matrix about X by three degrees each tick; "
     "scale the angle"),
    ("player", "lin", 0x38D9AE, "movss xmm2, dword ptr [rip + 0x2f4e0a]",
     (0x6827C0, 0.12217304855585098),
     "wp1a piece in flight: rotate its matrix about Y by seven degrees each tick; "
     "scale the angle"),
    ("player", "count", 0x38DA8C, "sub byte ptr [rbx + rdi + 0x1124], 1", None,
     "wp1a piece: the 60-tick flight wait at +1124 counts down once each stock tick, "
     "with the zero test reading not finished on skipped ticks"),
    # --- wp09 (387140) ---
    ("player", "dst", 0x38717B, "movaps xmm6, xmm0", ("slowmo",0x38716C),
     "wp09 (387140): xmm6 is 23AD90's slow-motion dt; its only readers after the copy "
     "are +E28 -= 0.1 x dt and the forward move by +E28 x dt; no animation-rate reader"),
    # --- wp0f (38A8F0) ---
    ("player", "dst", 0x38A935, "movaps xmm7, xmm0", ("slowmo",0x38A927),
     "wp0f (38A8F0): xmm7 is 23AD90's slow-motion dt; its only reader after the copy "
     "is the nearby-target sound cooldown +10FC -= dt; no animation-rate reader"),
    # --- wp0f (38ABD0) ---
    ("player", "dst", 0x38AC19, "movaps xmm7, xmm0", ("slowmo",0x38AC0B),
     "wp0f (38ABD0): xmm7 is 23AD90's slow-motion dt; every reader is a per-tick step: "
     "the +10F8 countdown on both state paths, the move by +E10 x dt, the clamped turn "
     "limit 0.10472 x dt, and the +10FC sound cooldown; no animation-rate reader"),
    # --- wp1d (38FE50) ---
    ("player", "dst", 0x38FE84, "movaps xmm6, xmm0", ("slowmo",0x38FE6F),
     "wp1d (38FE50): xmm6 is 23AD90's slow-motion dt; its only reader after the copy "
     "is the lifetime +E28 -= dt; no animation-rate reader"),
    ("player", "lin", 0x390021, "addss xmm0, dword ptr [rip + 0x2e9c23]",
     (0x679C4C, 0.5235987901687622),
     "wp1d (38FE50), flight: heading +B0 gains 0.523599 radians a tick, so s of the "
     "step"),
    ("player", "pre", 0x3900B3, "addss xmm0, dword ptr [rax]", None,
     "wp1d (38FE50), flight: position.x += velocity +E10 a tick; +E10 is built once at "
     "launch and keeps its stock value, so s of it"),
    ("player", "pre", 0x3900CA, "addss xmm0, dword ptr [rax + 4]", None,
     "wp1d (38FE50), flight: position.y += velocity +E14 a tick; s of the stock-valued "
     "velocity"),
    ("player", "pre", 0x3900E3, "addss xmm0, dword ptr [rax + 8]", None,
     "wp1d (38FE50), flight: position.z += velocity +E18 a tick; s of the stock-valued "
     "velocity"),
    # --- wp1d (390490) ---
    ("player", "dst", 0x3904C5, "movaps xmm7, xmm0", ("slowmo",0x3904BC),
     "wp1d (390490): xmm7 is 23AD90's slow-motion dt; every reader is a per-tick step: "
     "+1078 -= dt, the sin(+1110) x 0.7 x dt bob, +1110 += 0.24 x dt, the move by +E10 "
     "x dt, +E18 += dt, +E28 -= dt, and the clamped turn limit 0.20944 x dt; "
     "branch-local multiplies do not reach another state and there is no "
     "animation-rate reader"),
    ("player", "srcx", 0x3904F7, "addss xmm1, xmm8", None,
     "wp1d (390490), states 0-3: +D2C fades in by xmm8 = 0.05 a tick up to 1; apply s "
     "to the source step while leaving the shared xmm8 unchanged"),
    ("player", "srcx", 0x390AE2, "subss xmm1, xmm8", None,
     "wp1d (390490), state 5: +D2C fades out by xmm8 = 0.05 a tick down to 0.1; apply "
     "s to the source step"),
    # --- wp00 weapon pieces (37F790..3803A0) ---
    ("player", "dst", 0x37F7C2, "movaps xmm7, xmm0", ("slowmo",0x37F7AE),
     "wp00 (37F790): xmm7 = the slow-motion factor (23AD90), the function's dt; its "
     "only live readers multiply it by +E28 (= 10) and pass that result to 2DA410, the "
     "forward step each tick"),
    ("player", "dst", 0x37F9EB, "movaps xmm7, xmm0", ("slowmo",0x37F9E1),
     "wp00 (37F9C0): xmm7 = the slow-motion factor, the function's dt; its only live "
     "readers scale the +E10 direction vector before 2DA3F0 moves the piece and "
     "subtract dt from the lifetime +E28"),
    ("player", "dst", 0x37FFF0, "movaps xmm6, xmm0", ("slowmo",0x37FFE4),
     "wp00 (37FFC0): xmm6 = the slow-motion factor, the function's dt; its only live "
     "reader is +10FC -= dt, the 20-unit sound countdown"),
    ("player", "lin", 0x3800B1, "addss xmm0, dword ptr [rip + 0x2f4e9f]", (0x674F58, 3.0),
     "wp00 (37FFC0, sub-state 3): the hit radius +E18 grows by 3 a tick, from 3 to 53, "
     "before it is passed to 2DC7B0: s of the step"),
    ("player", "lin", 0x3800E5, "subss xmm1, dword ptr [rip + 0x2f598f]", (0x675A7C, 6.0),
     "wp00 (37FFC0, sub-state 4): the hit radius +E18 shrinks by 6 a tick to 23 before "
     "2DC7B0: s of the step"),
    ("player", "callscale", 0x38029C, "call 0x1802da410", (0x2DA410,"xmm1"),
     "wp00 (37FFC0, sub-state 1): forward by +E28 a tick (+E28 is signed +1101 x 5.5): "
     "s of it"),
    ("player", "dst", 0x3803DF, "movaps xmm6, xmm0", ("slowmo",0x3803CB),
     "wp00 (3803A0): xmm6 = the slow-motion factor, the function's dt; its only live "
     "reader is +10FC -= dt, the 20-unit sound countdown"),
    ("player", "scaledadd", 0x380575, "call qword ptr [rip + 0x2f0885]", None,
     "wp00 (3803A0, sub-state 1): position += the normalized way to Amaterasu x +E28 "
     "each tick; +E28 falls from 8 to 3.5 at the already-scaled 0.35 step, so add s of "
     "the vector while its value stays stock"),
    # --- wp06 (385C50) ---
    ("player", "dst", 0x385C88, "movaps xmm6, xmm0", ("slowmo",0x385C7C),
     "wp06 (385C50): xmm6 = the slow-motion factor, the function's dt; its only live "
     "readers add sin(+10F8) x dt to y and advance/wrap +10F8 by 0.3 x dt"),
    ("player", "pre", 0x385E23, "addss xmm0, dword ptr [rax]", None,
     "wp06 (385C50, sub-state 1): position.x += the persistent launch velocity +E10 a "
     "tick: s of it while the velocity keeps its stock value"),
    ("player", "pre", 0x385E3A, "addss xmm0, dword ptr [rax + 4]", None,
     "wp06 (385C50, sub-state 1): position.y += the persistent launch velocity +E14 a "
     "tick: s of it"),
    ("player", "pre", 0x385E53, "addss xmm0, dword ptr [rax + 8]", None,
     "wp06 (385C50, sub-state 1): position.z += the persistent launch velocity +E18 a "
     "tick: s of it"),
    ("player", "callscale", 0x385EF9, "call 0x1802da410", (0x2DA410,"xmm1"),
     "wp06 (385C50, sub-state 1): forward by 4 a tick within 60 of Amaterasu, "
     "otherwise 6: s of the per-tick step"),
    # --- pl04's three appendages (3A6120), one call per piece each tick ---
    ("player", "count", 0x3A62A9, "inc word ptr [r14]", None,
     "pl04 appendage: +414C[part] indexes its preset path, advancing one point per "
     "stock tick while the model sits on the current point"),
    ("player", "count", 0x3A65A7, "mov word ptr [rdi + rbx*2 + 0x414c], ax", None,
     "pl04 appendage: +414C[part] counts down the 90-tick hold in state 5 while the "
     "model follows its target's position"),
    ("player", "notyet", 0x3A65AF, "test cx, cx", 0x3A65BC,
     "pl04 appendage: state 5's zero test reads the countdown's old value; between "
     "stock ticks it must remain in state 5"),
    ("player", "blendr", 0x3A6661, "movss xmm7, dword ptr [rip + 0x2cf3c7]", None,
     "pl04 appendage, state 6/7: xmm7 = 0.3 for each coordinate's return to the preset "
     "anchor; all six uses are approach factors, including the second approach when "
     "closer than 10"),
    # --- pl00's linked attack state (3B9A70) ---
    ("player", "count", 0x3B9B95, "mov byte ptr [rdi + 0x11e9], al", None,
     "pl00 linked attack: +11E9 is the per-tick cooldown that suppresses another hit "
     "effect; decrement once on each stock tick"),
    ("player", "srcx", 0x3B9DFD, "subss xmm0, xmm6", None,
     "pl00 linked attack: when the partner's +F48 is in 10..14, her +F48 loses 1 each "
     "tick; scale this subtraction while xmm6 stays 1 for the threshold and later "
     "motion arguments"),
    ("player", "lin", 0x3B9E98, "subss xmm0, dword ptr [rip + 0x2b7f74]", (0x671E14, 2.0),
     "pl00 linked attack: the partner's +F48 loses 2 per tick while linked; scale the "
     "subtract literal"),
    ("player", "notyet", 0x3BB625, "test ax, ax", 0x3BB674,
     "pl00 linked attack, state 11: the +E3C zero-time effect check must wait for a "
     "stock tick while the countdown is held"),
    ("player", "count", 0x3BB677, "mov word ptr [rdi + 0xe3c], ax", None,
     "pl00 linked attack, state 11: +E3C counts down from 5 once each stock tick"),
    # pl00 ground offsets (3A75C0)
    ("player", "blend", 0x3A766F, "mulss xmm1, dword ptr [rip + 0x2d1219]",
     (0x678890, 0.029999999329447746),
     "pl00 ground offsets (3A75C0), (+1014 & 0x1F) == 8: +10A0 approaches the rotated "
     "+E48 target by 0.03 a tick"),
    ("player", "blend", 0x3A7695, "mulss xmm1, dword ptr [rip + 0x2d11f3]",
     (0x678890, 0.029999999329447746),
     "pl00 ground offsets (3A75C0), (+1014 & 0x1F) == 8: +10A8 approaches the rotated "
     "+E48 target by 0.03 a tick"),
    ("player", "blend", 0x3A76C4, "mulss xmm1, dword ptr [rip + 0x400c7c]",
     (0x7A8348, 0.30000001192092896),
     "pl00 ground offsets (3A75C0): +10A0 approaches the rotated +E48 target by 0.3 a "
     "tick; 7A8348 stays 0.3 at every mode"),
    ("player", "blend", 0x3A76EA, "mulss xmm1, dword ptr [rip + 0x400c56]",
     (0x7A8348, 0.30000001192092896),
     "pl00 ground offsets (3A75C0): +10A8 approaches the rotated +E48 target by 0.3 a "
     "tick; the same unscaled 7A8348 reader"),
    ("player", "blend", 0x3A7716, "mulss xmm1, dword ptr [rip + 0x400c2e]",
     (0x7A834C, 0.30000001192092896),
     "pl00 ground offsets (3A75C0): +10A4 approaches the rotated +E48 target by 0.3 a "
     "tick; 7A834C stays 0.3 at every mode"),
    ("player", "count", 0x3A7814, "movss dword ptr [rbx + 0x10a0], xmm0", None,
     "pl00 ground offsets (3A75C0), +E58 bits 14 and 16 path: +10A0 *= 0.1 a stock "
     "tick before the reduced move, so keep its store on the first tick of each stock "
     "period"),
    ("player", "count", 0x3A781C, "movss dword ptr [rbx + 0x10a8], xmm1", None,
     "pl00 ground offsets (3A75C0), +E58 bits 14 and 16 path: +10A8 *= 0.1 a stock "
     "tick before the reduced move, so keep its store on the first tick of each stock "
     "period"),
    # wp51, wp55, wp5a, wp5e
    ("player", "lin", 0x39E872, "movss xmm1, dword ptr [rip + 0x2db3ba]",
     (0x679C34, 0.06981316953897476),
     "wp51 (39E790): the caller passes a 4-degree steering limit to 39F770 every tick; "
     "the helper multiplies it by slow-motion dt, so pass s of the limit while leaving "
     "the helper stock for its one-shot caller"),
    ("player", "lin", 0x39EE6F, "movss xmm1, dword ptr [rip + 0x2dadbd]",
     (0x679C34, 0.06981316953897476),
     "wp51 (39EE30): the caller passes a 4-degree steering limit to 39F770 every tick; "
     "the helper multiplies it by slow-motion dt, so pass s of the limit while leaving "
     "the helper stock for its one-shot caller"),
    ("player", "dst", 0x39EAFC, "movaps xmm6, xmm0", ("slowmo",0x39EAE6),
     "wp51 (39EAC0): xmm6 = the slow-motion factor, the function's dt; its only live "
     "readers subtract dt from +10F0 in sub-states 3 and 1, after which xmm6 is "
     "overwritten"),
    ("player", "dst", 0x39EE66, "movaps xmm6, xmm0", ("slowmo",0x39EE5C),
     "wp51 (39EE30): xmm6 = the slow-motion factor, the function's dt; every live "
     "reader is a per-tick step: +10F0 -= dt, +E18 -= 0.75 x dt, movement by +E10 x "
     "dt, +E28 -= dt, and the later +10F0 -= dt"),
    ("player", "lin", 0x39F2F2, "movss xmm1, dword ptr [rip + 0x2d82f6]",
     (0x6775F0, 0.05000000074505806),
     "wp51 (39F2B0): the +C0/+C4/+C8 vector grows by 0.05 a tick through "
     "cVec::operator+= before each component is clamped to 1.5: s of the step"),
    ("player", "dst", 0x39F2E8, "movaps xmm8, xmm0", ("slowmo",0x39F2DE),
     "wp51 (39F2B0): xmm8 = the slow-motion factor, the function's dt; every live "
     "reader is a per-tick step: the two +10F0 countdowns, forward movement by 6 x dt, "
     "and +E18 += 0.3 x dt"),
    ("player", "pre", 0x3A0352, "addss xmm0, dword ptr [rax]", None,
     "wp55 (3A0160, sub-state 1): position.x += the persistent launch velocity +E10 "
     "each tick: s of the move while the velocity keeps its stock value"),
    ("player", "pre", 0x3A0373, "addss xmm0, dword ptr [rax + 4]", None,
     "wp55 (3A0160, sub-state 1): position.y += the persistent launch velocity +E14 "
     "each tick: s of the move"),
    ("player", "pre", 0x3A038C, "addss xmm0, dword ptr [rax + 8]", None,
     "wp55 (3A0160, sub-state 1): position.z += the persistent launch velocity +E18 "
     "each tick: s of the move"),
    ("player", "dst", 0x3A100B, "movaps xmm6, xmm0", ("slowmo",0x3A0FFF),
     "wp5a (3A0FE0): xmm6 = the slow-motion factor, the function's dt; its only live "
     "reader subtracts dt from the +10F0 sound countdown"),
    ("player", "lin", 0x3A10D0, "addss xmm0, dword ptr [rip + 0x2d3e80]", (0x674F58, 3.0),
     "wp5a (3A0FE0, sub-state 3): the hit radius +E18 grows by 3 a tick, from 3 to 53, "
     "before it is passed to 2DC7B0: s of the step"),
    ("player", "lin", 0x3A1104, "subss xmm1, dword ptr [rip + 0x2d4970]", (0x675A7C, 6.0),
     "wp5a (3A0FE0, sub-state 4): the hit radius +E18 shrinks by 6 a tick to 23 before "
     "it is passed to 2DC7B0: s of the step"),
    ("player", "callscale", 0x3A123A, "call 0x1802da410", (0x2DA410,"xmm1"),
     "wp5a (3A0FE0, sub-state 1): forward by +E28 each tick: s of the per-tick step"),
    ("player", "dst", 0x3A1A51, "movaps xmm6, xmm0", ("slowmo",0x3A1A45),
     "wp5e (3A1A30): xmm6 = the slow-motion factor, the function's dt; its only live "
     "reader subtracts 0.03 x dt from +D2C in sub-states 0 and 1"),
    # wp5e/wp5f follow-up
    ("player", "dst", 0x3A1B8E, "movaps xmm6, xmm0", ("slowmo",0x3A1B80),
     "wp5e (3A1B50): xmm6 = the slow-motion factor, the function's dt; its only live "
     "reader multiplies +E28 by dt for the per-tick forward move in sub-state 1"),
    ("player", "dst", 0x3A1E16, "movaps xmm7, xmm0", ("slowmo",0x3A1E0A),
     "wp5e (3A1DF0): xmm7 = the slow-motion factor, the function's dt; its only live "
     "reader subtracts dt from the lifetime +1108 in sub-state 1"),
    ("player", "dst", 0x3A1F11, "movaps xmm6, xmm0", ("slowmo",0x3A1F05),
     "wp5e (3A1EF0): xmm6 = the slow-motion factor, the function's dt; its only live "
     "reader subtracts 0.03 x dt from +D2C in sub-states 2 and 3"),
    ("player", "dst", 0x3A2551, "movaps xmm7, xmm0", ("slowmo",0x3A2545),
     "wp5f (3A2530): xmm7 = the slow-motion factor, the function's dt; its only live "
     "readers subtract dt from +1108, once conditionally and once on every update"),
    ("player", "callscale", 0x3A25BA, "call 0x1802da410", (0x2DA410,"xmm1"),
     "wp5f (3A2530): forward by +E48 each tick on the 23B750-true path: s of the "
     "per-tick move while +E48 keeps its stock value"),
    ("player", "callscale", 0x3A25D1, "call 0x1802da410", (0x2DA410,"xmm1"),
     "wp5f (3A2530): forward by +E48 each tick on the other path: s of the per-tick "
     "move while the already-covered +E48 acceleration stays stock-valued"),
    # pl00 target move (3D0440)
    ("player", "pre", 0x3D07A0, "addss xmm3, dword ptr [rax]", None,
     "pl00 (3D0440), active state: move x by s of the normalized target-direction "
     "step; leave +E10 stock-valued for the arrival distance check"),
    ("player", "pre", 0x3D07B7, "addss xmm0, dword ptr [rax + 4]", None,
     "pl00 (3D0440), active state: move y by s of the normalized target-direction "
     "step; leave +E14 stock-valued for the arrival distance check"),
    ("player", "pre", 0x3D07D0, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 (3D0440), active state: move z by s of the normalized target-direction "
     "step; leave +E18 stock-valued for the arrival distance check"),
    ("player", "notyet", 0x3D0895, "test ax, ax", 0x3D08A4,
     "pl00 (3D0440): zero-time exit must wait for a stock tick while +E3C is held"),
    ("player", "count", 0x3D08A7, "mov word ptr [rdi + 0xe3c], ax", None,
     "pl00 (3D0440): +E3C loses one per stock tick in active state"),
    # pl00 target companions (3D0EC0, 3D1140)
    ("player", "pre", 0x3D1016, "addss xmm0, dword ptr [rax]", None,
     "pl00 (3D0EC0): position.x gains s of +E10, rebuilt as 0.2 of the target "
     "direction each active tick"),
    ("player", "pre", 0x3D102D, "addss xmm0, dword ptr [rax + 4]", None,
     "pl00 (3D0EC0): position.y gains s of the active tick's +E14 target step"),
    ("player", "pre", 0x3D1046, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 (3D0EC0): position.z gains s of the active tick's +E18 target step"),
    ("player", "notyet", 0x3D1082, "test ax, ax", 0x3D111C,
     "pl00 (3D0EC0): the zero-time return and effect wait for a stock tick when the "
     "+E3C countdown is held"),
    ("player", "count", 0x3D111F, "mov word ptr [rdi + 0xe3c], ax", None,
     "pl00 (3D0EC0): commit the +E3C active-state decrement once per stock tick"),
    ("player", "srcx", 0x3D1281, "addss xmm0, dword ptr [rdi + 0xe10]", None,
     "pl00 (3D1140): position.x in xmm0 adds the +E10 target step from memory; scale "
     "the source step only, not the existing position"),
    ("player", "pre", 0x3D129C, "addss xmm0, dword ptr [rax + 4]", None,
     "pl00 (3D1140): position.y gains s of +E14, rebuilt as 0.2 of the target "
     "direction each active tick"),
    ("player", "pre", 0x3D12B5, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 (3D1140): position.z gains s of the active tick's +E18 target step"),
    ("player", "notyet", 0x3D12E1, "test ax, ax", 0x3D12FE,
     "pl00 (3D1140): the zero-time exit waits for a stock tick while +E3C is held"),
    ("player", "count", 0x3D1301, "mov word ptr [rdi + 0xe3c], ax", None,
     "pl00 (3D1140): commit the +E3C active-state decrement once per stock tick"),
    # wp1b (38E8D0)
    ("player", "srcx", 0x38EAD0, "addss xmm1, dword ptr [rdi + 0xfe0]", None,
     "wp1b (38E8D0), launch: grounded slope +FE0 contributes to the persistent "
     "per-tick-at-this-rate x velocity; add s of the stock launch push"),
    ("player", "srcx", 0x38EAD8, "addss xmm2, dword ptr [rdi + 0xfe8]", None,
     "wp1b (38E8D0), launch: grounded slope +FE8 contributes to the persistent "
     "per-tick-at-this-rate z velocity; add s of the stock launch push"),
    ("player", "dst", 0x38EB8E, "movss xmm0, dword ptr [rdi + 0xfe0]", None,
     "wp1b (38E8D0), flight: xmm0 loads grounded slope push +FE0; scale it once toward "
     "the s^2 change of a persistent per-tick-at-this-rate velocity"),
    ("player", "dst", 0x38EB96, "movss xmm1, dword ptr [rdi + 0xfe8]", None,
     "wp1b (38E8D0), flight: xmm1 loads grounded slope push +FE8; scale it once toward "
     "the s^2 velocity change"),
    ("player", "pre", 0x38EB9E, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "wp1b (38E8D0), flight: the already s-scaled slope push in xmm0 is scaled again "
     "before it is added to persistent x velocity +E20, giving s^2"),
    ("player", "pre", 0x38EBA6, "addss xmm1, dword ptr [rdi + 0xe28]", None,
     "wp1b (38E8D0), flight: the already s-scaled slope push in xmm1 is scaled again "
     "before it is added to persistent z velocity +E28, giving s^2"),
    # pl02 (3A2C70)
    ("player", "srcblend", 0x3A2FE5, "mulss xmm0, dword ptr [rbx + 0xe10]", None,
     "pl02 (3A2C70), state 5: position.x repeatedly approaches the sampled target with "
     "dynamic factor +E10; convert it to 1-(1-k)^s"),
    ("player", "srcblend", 0x3A3006, "mulss xmm1, dword ptr [rbx + 0xe10]", None,
     "pl02 (3A2C70), state 5: position.y uses the same dynamic +E10 approach factor"),
    ("player", "srcblend", 0x3A3029, "mulss xmm1, dword ptr [rbx + 0xe10]", None,
     "pl02 (3A2C70), state 5: position.z uses the same dynamic +E10 approach factor"),
    ("player", "srcblend", 0x3A3324, "mulss xmm0, dword ptr [rbx + 0xe10]", None,
     "pl02 (3A2C70), state 9: position.x approaches submodel 7 with dynamic factor "
     "+E10"),
    ("player", "srcblend", 0x3A3345, "mulss xmm1, dword ptr [rbx + 0xe10]", None,
     "pl02 (3A2C70), state 9: position.y uses the same dynamic approach factor"),
    ("player", "srcblend", 0x3A3368, "mulss xmm1, dword ptr [rbx + 0xe10]", None,
     "pl02 (3A2C70), state 9: position.z uses the same dynamic approach factor"),
    # wp11 (38C430)
    ("player", "count", 0x38C553, "mov word ptr [rdi + 0xe3c], ax", None,
     "wp11 (38C430): lower +E3C is the 30-tick interval that holds +E54 at zero; "
     "commit its decremented register value only on stock ticks"),
    ("player", "pre", 0x38C613, "addss xmm0, dword ptr [rax]", None,
     "wp11 (38C430), flight: position.x gains s of persistent stock-valued launch "
     "velocity +E10"),
    ("player", "pre", 0x38C634, "addss xmm0, dword ptr [rax + 4]", None,
     "wp11 (38C430), flight: position.y gains s of persistent stock-valued launch "
     "velocity +E14"),
    ("player", "pre", 0x38C64D, "addss xmm0, dword ptr [rax + 8]", None,
     "wp11 (38C430), flight: position.z gains s of persistent stock-valued launch "
     "velocity +E18"),
    # pl00 attack combo (3B7320)
    ("player", "callscale", 0x3B7EB5, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 attack combo (3B7320), state 7: turn toward the locked target by at most "
     "0.279253 radians a tick; scale this continuous call's limit"),
    ("player", "callscale", 0x3B81DA, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 attack combo (3B7320), state 9: turn toward the locked target by at most "
     "0.279253 radians a tick; scale this continuous call's limit"),
    ("player", "count", 0x3B849A, "movss dword ptr [rdi + 0xe48], xmm1", None,
     "pl00 attack combo (3B7320): while +D40 bit 3 is set, commit +E48 x 0.5 once per "
     "stock tick"),
    ("player", "count", 0x3B84E3, "movss dword ptr [rdi + 0xe48], xmm0", None,
     "pl00 attack combo (3B7320): while +E58 has collision bits 0x14000, commit +E48 x "
     "0.1 once per stock tick"),
    # pl02 (3A4480)
    ("player", "blend", 0x3A4676, "movss xmm2, dword ptr [rip + 0x2d2f72]",
     (0x6775F0, 0.05000000074505806),
     "pl02 (3A4480): +2110/+2114/+2118 approach +2120/+2124/+2128 by the shared 0.05 "
     "factor each tick; use 1-(1-0.05)^s"),
    ("player", "pre", 0x3A473D, "addss xmm0, dword ptr [rax]", None,
     "pl02 (3A4480): position.x gains s of the normalized horizontal direction times "
     "stock-valued speed +2108"),
    ("player", "pre", 0x3A475A, "addss xmm0, dword ptr [rax + 8]", None,
     "pl02 (3A4480): position.z gains s of the normalized horizontal direction times "
     "stock-valued speed +2108"),
    ("player", "countlast", 0x3A4779, "addss xmm1, xmm7", None,
     "pl02 (3A4480): +2108 gains 2 after the move, up to 60; change it on the last "
     "tick of each stock period so that period's moves use one stock speed"),
    ("player", "blend", 0x3A4937, "mulss xmm0, dword ptr [rip + 0x2cd4cd]",
     (0x671E0C, 0.6000000238418579),
     "pl02 (3A4480): when below the ground target, y approaches it by 0.6 a tick; use "
     "1-(1-0.6)^s"),
    ("player", "blend", 0x3A4941, "mulss xmm0, dword ptr [rip + 0x2cd4bb]",
     (0x671E04, 0.10000000149011612),
     "pl02 (3A4480): otherwise y approaches the ground target by 0.1 a tick; use "
     "1-(1-0.1)^s"),
    ("player", "scaledadd", 0x3A28F1, "jmp qword ptr [rip + 0x2ce508]", None,
     "wp5f (3A2700, sub-state 1): the tail jump to cVec::operator+= moves position by "
     "persistent launch velocity +E10/+E14/+E18 each tick; add s of the vector while "
     "the velocity keeps its stock value"),
    # pl02 steering (3A3550) and target follow (3A3CA0)
    ("player", "ulast", 0x3A373B, "movss xmm0, dword ptr [rip + 0x2d2619]", None,
     "pl02 (3A3550, first steering path): xmm0 = the 0.95 damping applied to all three "
     "persistent velocity lanes after their acceleration; keep 1 between stock ticks "
     "and apply 0.95 on the last tick"),
    ("player", "pre", 0x3A3771, "addss xmm1, dword ptr [rdx]", None,
     "pl02 (3A3550, first steering path): persistent velocity +E20 gains this tick's x "
     "acceleration: add s of the acceleration"),
    ("player", "pre", 0x3A377A, "addss xmm2, dword ptr [rbx + 0xe24]", None,
     "pl02 (3A3550, first steering path): persistent velocity +E24 gains this tick's y "
     "acceleration: add s of the acceleration"),
    ("player", "pre", 0x3A3787, "addss xmm3, dword ptr [rbx + 0xe28]", None,
     "pl02 (3A3550, first steering path): persistent velocity +E28 gains this tick's z "
     "acceleration: add s of the acceleration"),
    ("player", "scaledadd", 0x3A37AF, "call qword ptr [rip + 0x2cd64b]", None,
     "pl02 (3A3550, first steering path): position += persistent velocity "
     "+E20/+E24/+E28 each tick; add s of the vector while its value stays stock"),
    ("player", "ulast", 0x3A3921, "movss xmm0, dword ptr [rip + 0x2d2433]", None,
     "pl02 (3A3550, second steering path): xmm0 = the 0.95 damping applied to all "
     "three persistent velocity lanes after their acceleration; keep 1 between stock "
     "ticks and apply 0.95 on the last tick"),
    ("player", "pre", 0x3A3957, "addss xmm1, dword ptr [rdx]", None,
     "pl02 (3A3550, second steering path): persistent velocity +E20 gains this tick's "
     "x acceleration: add s of the acceleration"),
    ("player", "pre", 0x3A3960, "addss xmm2, dword ptr [rbx + 0xe24]", None,
     "pl02 (3A3550, second steering path): persistent velocity +E24 gains this tick's "
     "y acceleration: add s of the acceleration"),
    ("player", "pre", 0x3A396D, "addss xmm3, dword ptr [rbx + 0xe28]", None,
     "pl02 (3A3550, second steering path): persistent velocity +E28 gains this tick's "
     "z acceleration: add s of the acceleration"),
    ("player", "scaledadd", 0x3A3995, "call qword ptr [rip + 0x2cd465]", None,
     "pl02 (3A3550, second steering path): position += persistent velocity "
     "+E20/+E24/+E28 each tick; add s of the vector while its value stays stock"),
    ("player", "callscale", 0x3A4179, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl02 (3A3CA0, sub-states 2/3): turn +B4 toward the selected model every tick "
     "with the xmm3 limit: s of the per-tick turn limit"),
    ("player", "srcblend", 0x3A41B8, "mulss xmm0, dword ptr [rdi + 0xe10]", None,
     "pl02 (3A3CA0, sub-state 3): position.x approaches the selected model by dynamic "
     "factor +E10 each tick: use 1-(1-k)^s while +E10 itself stays stock"),
    ("player", "srcblend", 0x3A41E9, "mulss xmm1, dword ptr [rdi + 0xe10]", None,
     "pl02 (3A3CA0, sub-state 3): position.y approaches the selected model by dynamic "
     "factor +E10 each tick: use 1-(1-k)^s"),
    ("player", "srcblend", 0x3A421C, "mulss xmm1, dword ptr [rdi + 0xe10]", None,
     "pl02 (3A3CA0, sub-state 3): position.z approaches the selected model by dynamic "
     "factor +E10 each tick: use 1-(1-k)^s"),
    ("player", "callscale", 0x3A440A, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl02 (3A3CA0, sub-state 5): turn +B4 toward +2090's model position every tick "
     "with the xmm3 limit: s of the per-tick turn limit"),
    # pl03 path following (3A51F0)
    ("player", "notyet", 0x3A5525, "test byte ptr [rdi + 0xe3e], 7", 0x3A5553,
     "pl03 (3A51F0, sub-state 1): the effect at every eighth +E3E tick must wait for a "
     "stock tick while the already-covered counter is held"),
    ("player", "notyet", 0x3A5742, "test byte ptr [rdi + 0xe3e], 7", 0x3A5770,
     "pl03 (3A51F0, sub-state 3): the effect at every eighth +E3E tick must wait for a "
     "stock tick while the already-covered counter is held"),
    ("player", "callscale", 0x3A57A2, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl03 (3A51F0, sub-state 3): turn +B4 toward the selected model every tick with "
     "the xmm3 limit: s of the per-tick turn limit"),
    ("player", "srcblend", 0x3A57E1, "mulss xmm0, dword ptr [rdi + 0xe10]", None,
     "pl03 (3A51F0, sub-state 3): position.x approaches the selected model by dynamic "
     "factor +E10 each tick: use 1-(1-k)^s while +E10 itself stays stock"),
    ("player", "srcblend", 0x3A5812, "mulss xmm1, dword ptr [rdi + 0xe10]", None,
     "pl03 (3A51F0, sub-state 3): position.y approaches the selected model by dynamic "
     "factor +E10 each tick: use 1-(1-k)^s"),
    ("player", "srcblend", 0x3A5845, "mulss xmm1, dword ptr [rdi + 0xe10]", None,
     "pl03 (3A51F0, sub-state 3): position.z approaches the selected model by dynamic "
     "factor +E10 each tick: use 1-(1-k)^s"),
    ("player", "lin", 0x3A5937, "addss xmm1, dword ptr [rip + 0x2d42f1]",
     (0x679C30, 0.019999999552965164),
     "pl03 (3A51F0, sub-state 3): the dynamic approach factor +E10 grows by 0.02 a "
     "tick from 0.1 to 1: s of the step"),
    ("player", "callscale", 0x3A5AC6, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl03 (3A51F0, sub-state 5): turn +B4 toward +2100's model position every tick "
     "with the xmm3 limit: s of the per-tick turn limit"),
    # pl00 turn and charge (3C6080, 3C84B0)
    ("player", "lin", 0x3C615C, "movss xmm1, dword ptr [rip + 0x2b3aa4]",
     (0x679C08, 0.13962633907794952),
     "pl00 (3C6080, sub-states 2/3): 2DE0A0's first continuous angular limit is 8 "
     "degrees a tick: pass s of the caller-local limit"),
    ("player", "lin", 0x3C616C, "movss xmm0, dword ptr [rip + 0x2b3ac0]",
     (0x679C34, 0.06981316953897476),
     "pl00 (3C6080, sub-states 2/3): 2DE0A0's second continuous angular limit is 4 "
     "degrees a tick: pass s of the caller-local limit"),
    ("player", "lin", 0x3C64F4, "movss xmm1, dword ptr [rip + 0x2b370c]",
     (0x679C08, 0.13962633907794952),
     "pl00 (3C6080, sub-state 1): 2DE0A0's first continuous angular limit is 8 degrees "
     "a tick: pass s of the caller-local limit"),
    ("player", "lin", 0x3C6504, "movss xmm0, dword ptr [rip + 0x2b3728]",
     (0x679C34, 0.06981316953897476),
     "pl00 (3C6080, sub-state 1): 2DE0A0's second continuous angular limit is 4 "
     "degrees a tick: pass s of the caller-local limit"),
    ("player", "notyet", 0x3C668F, "cmp eax, 0xa", 0x3C66C7,
     "pl00 (3C6080, sub-state 0): the transition at +11F0 = 10 must wait for a stock "
     "tick while the counter is held"),
    ("player", "count", 0x3C66C9, "mov dword ptr [rdi + 0x11f0], eax", None,
     "pl00 (3C6080, sub-state 0): +11F0 advances once per stock tick from 0 to 10 "
     "before entering sub-state 1"),
    ("player", "notyet", 0x3C86CD, "test bl, 7", 0x3C8729,
     "pl00 (3C84B0): the effect on every eighth +1152 tick must wait for a stock tick "
     "while the charge counter is held"),
    ("player", "notyet", 0x3C8729, "cmp word ptr [r14 + 0x1152], r15w", 0x3C876B,
     "pl00 (3C84B0): the event at +1152 = 0 must not repeat between stock ticks"),
    ("player", "count", 0x3C876B, "inc word ptr [r14 + 0x1152]", None,
     "pl00 (3C84B0): +1152 counts charging time once per stock tick; its thresholds "
     "choose the charge tier, sounds and effects"),
    ("player", "notyet", 0x3C8788, "cmp eax, ecx", 0x3C87DC,
     "pl00 (3C84B0): the first threshold's paired events must play only on the "
     "counter's stock tick"),
    ("player", "notyet", 0x3C87F1, "cmp eax, ecx", 0x3C8845,
     "pl00 (3C84B0): the second threshold's paired events must play only on the "
     "counter's stock tick"),
    ("player", "notyet", 0x3C8879, "cmp al, 1", 0x3C8F60,
     "pl00 (3C84B0): the repeated event every eight ticks above the full-charge "
     "threshold must wait for a stock tick"),
    ("player", "callscale", 0x3C8FE1, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 (3C84B0): turn +B4 toward the current target every tick with the 32-degree "
     "xmm3 limit: s of the per-tick turn limit"),
    # wp09 launch/move (3875B0)
    ("player", "pre", 0x387802, "addss xmm0, dword ptr [rax]", None,
     "wp09 (3875B0), sub-state 1: position.x gains persistent launch velocity +E10 "
     "each tick; scale the copied velocity for this move while leaving the stored "
     "velocity stock-valued"),
    ("player", "pre", 0x387823, "addss xmm0, dword ptr [rax + 4]", None,
     "wp09 (3875B0), sub-state 1: position.y gains persistent launch velocity +E14 "
     "each tick; scale the copied velocity for this move"),
    ("player", "pre", 0x38783C, "addss xmm0, dword ptr [rax + 8]", None,
     "wp09 (3875B0), sub-state 1: position.z gains persistent launch velocity +E18 "
     "each tick; scale the copied velocity for this move"),
    # wp0d colour phase (388B50)
    ("player", "count", 0x388D63, "mov word ptr [rsi + 0xe3c], di", None,
     "wp0d (388B50): +E3C advances the cyclic colour waveform one count per stock "
     "tick; skip the incremented word store between stock ticks"),
    # wp30 two-joint angular spring (397050)
    ("player", "dst", 0x39710A, "mulss xmm1, dword ptr [rip + 0x2e04de]", None,
     "wp30 (397050), first joint spring: angular velocity +1C68 loses joint angle x "
     "0.05 each tick; scale the computed pull before it accumulates"),
    ("player", "srcx", 0x397140, "addss xmm0, dword ptr [rdi + 0x1c68]", None,
     "wp30 (397050), first joint spring: the joint angle gains angular velocity +1C68 "
     "each tick; add s of the stock-valued velocity"),
    ("player", "countlast", 0x397158, "mulss xmm1, dword ptr [rip + 0x2dacb0]", None,
     "wp30 (397050), first joint spring: +1C68 is damped x 0.7 after the move, on the "
     "last tick of each stock period"),
    ("player", "dst", 0x3971BA, "mulss xmm1, dword ptr [rip + 0x2e042e]", None,
     "wp30 (397050), second joint spring: angular velocity +1C6C loses joint angle x "
     "0.05 each tick; scale the computed pull before it accumulates"),
    ("player", "srcx", 0x3971ED, "addss xmm0, dword ptr [rdi + 0x1c6c]", None,
     "wp30 (397050), second joint spring: the joint angle gains angular velocity +1C6C "
     "each tick; add s of the stock-valued velocity"),
    ("player", "countlast", 0x397205, "mulss xmm1, dword ptr [rip + 0x2dac03]", None,
     "wp30 (397050), second joint spring: +1C6C is damped x 0.7 after the move, on the "
     "last tick of each stock period"),
    # pl00 state 2C conditional forward push (3C2430)
    ("player", "pre", 0x3C2A38, "addss xmm0, dword ptr [rax]", None,
     "pl00 state 2C (3C2430): the conditional rotated two-unit forward push is added "
     "to position.x every tick; scale the copied step"),
    ("player", "pre", 0x3C2A4C, "addss xmm0, dword ptr [rax + 4]", None,
     "pl00 state 2C (3C2430): the same rotated forward push, position.y component"),
    ("player", "pre", 0x3C2A62, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 state 2C (3C2430): the same rotated forward push, position.z component"),
    # pl00 turn/charge state (3BC710)
    ("player", "lin", 0x3BCA39, "movss xmm0, dword ptr [rip + 0x2c2e67]",
     (0x67F8A8, 0.15707963705062866),
     "pl00 (3BC710, sub-state 1): 2DE0A0's first continuous angular limit is 9 degrees "
     "a tick: pass s of the caller-local limit"),
    ("player", "lin", 0x3BCA47, "movss xmm1, dword ptr [rip + 0x2bd271]",
     (0x679CC0, 0.27925267815589905),
     "pl00 (3BC710, sub-state 1): 2DE0A0's second continuous angular limit is 16 "
     "degrees a tick: pass s of the caller-local limit"),
    ("player", "notyet", 0x3BCC0F, "test byte ptr [r14 + 0x1152], 7", 0x3BCC7B,
     "pl00 (3BC710): the sound/effect on every eighth +1152 charge tick must wait for "
     "a stock tick while the counter is held"),
    ("player", "notyet", 0x3BCC7B, "cmp word ptr [r14 + 0x1152], 0", 0x3BCCBD,
     "pl00 (3BC710): the event at +1152 = 0 must not repeat between stock ticks"),
    ("player", "count", 0x3BCCBD, "inc word ptr [r14 + 0x1152]", None,
     "pl00 (3BC710): +1152 counts charging time once per stock tick; its thresholds "
     "choose the charge tier, sounds and effects"),
    ("player", "notyet", 0x3BCE10, "cmp al, dil", 0x3BD7A0,
     "pl00 (3BC710): the repeated event every eight ticks above the full-charge "
     "threshold must wait for a stock tick"),
    # pl00 linked attack/state (3BEEE0)
    ("player", "count", 0x3BF3D7, "movss dword ptr [r14 + 0xe54], xmm0", None,
     "pl00 (3BEEE0): while the five-tick hit cooldown +11E9 is active, stock-valued "
     "vertical speed +E54 halves once per stock tick"),
    ("player", "notyet", 0x3BFB76, "test ax, ax", 0x3BFB99,
     "pl00 (3BEEE0, sub-state 7): +E3E's zero-time transition must wait for a stock "
     "tick while the countdown is held"),
    ("player", "count", 0x3BFB9C, "mov word ptr [r14 + 0xe3e], ax", None,
     "pl00 (3BEEE0, sub-state 7): +E3E's six-tick countdown loses one once per stock "
     "tick"),
    ("player", "callscale", 0x3BFC4E, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 (3BEEE0): the common tail turns +B4 toward the current target every tick "
     "with xmm3's 16-degree limit: pass s of the per-tick limit"),
    # pl00 common update (3A80F0)
    ("player", "blend", 0x3A81AB, "movss xmm2, dword ptr [rip + 0x2cf43d]",
     (0x6775F0, 0.05000000074505806),
     "pl00 (3A80F0, first path): +D20/+D24/+D28 approach 1 with the shared 0.05 factor "
     "each tick: use 1-(1-0.05)^s"),
    ("player", "blend", 0x3A8296, "movss xmm2, dword ptr [rip + 0x2cf352]",
     (0x6775F0, 0.05000000074505806),
     "pl00 (3A80F0, fallback path): +D20/+D24/+D28 approach 1 with the shared 0.05 "
     "factor each tick: use 1-(1-0.05)^s"),
    ("player", "count", 0x3A835F, "mov word ptr [rdi + 0x115a], ax", None,
     "pl00 (3A80F0): +115A's ordinary decrement commits once per stock tick"),
    ("player", "count", 0x3A8378, "add word ptr [rdi + 0x115a], -5", None,
     "pl00 (3A80F0): +115A's conditional extra -5 acceleration also commits only on "
     "stock ticks"),
    # pl00 state handlers (3CA320, 3C05C0)
    ("player", "count", 0x3CA9B9, "movss dword ptr [rsi + 0xe48], xmm0", None,
     "pl00 (3CA320, sub-state 5): persistent speed +E48 is multiplied by 0.1 once per "
     "stock tick before the current-rate move"),
    ("player", "callscale", 0x3C0BCF, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 (3C05C0): the common tail turns +B4 toward the current target every tick "
     "with xmm3's 16-degree limit: pass s of the per-tick limit"),
    ("player", "callscale", 0x3C72F9, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 state 48 (3C70C0, continuous path): 2DDF90's 8-degree angular limit is a "
     "per-tick turn step; scale xmm3 by s"),
    # pl01 movement (3B2CF0)
    ("player", "count", 0x3B3318, "mulss xmm0, dword ptr [rip + 0x2ccdbc]", "factor",
     "pl01 (3B2CF0, state 3 and mode 8): +E48 takes 0.94 damping before the move once "
     "on the first tick of each stock period; the other modes use their "
     "already-rewritten table"),
    ("player", "pre", 0x3B3B8B, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl01 (3B2CF0), conditional ground nudge: persistent +10B8 gains s of the "
     "0.1-scaled z acceleration"),
    ("player", "pre", 0x3B3B93, "addss xmm1, dword ptr [rdi + 0x10b0]", None,
     "pl01 (3B2CF0), conditional ground nudge: persistent +10B0 gains s of the "
     "0.1-scaled x acceleration"),
    ("player", "pre", 0x3B3BAB, "addss xmm1, dword ptr [rax]", None,
     "pl01 (3B2CF0), conditional ground nudge: position.x gains s of the persistent "
     "+10B0 velocity before the existing 0.9^s damping"),
    ("player", "pre", 0x3B3BC2, "addss xmm0, dword ptr [rax + 8]", None,
     "pl01 (3B2CF0), conditional ground nudge: position.z gains s of the persistent "
     "+10B8 velocity before the existing 0.9^s damping"),
    # wp03 launch/move (384010)
    ("player", "pre", 0x3841E7, "addss xmm0, dword ptr [rax]", None,
     "wp03 (384010, sub-state 1): position.x gains persistent launch velocity +E10 "
     "each tick; scale the copied velocity for this move while leaving the stored "
     "velocity stock-valued"),
    ("player", "pre", 0x384203, "addss xmm0, dword ptr [rax + 4]", None,
     "wp03 (384010, sub-state 1): position.y gains persistent launch velocity +E14 "
     "each tick; scale the copied velocity for this move"),
    ("player", "pre", 0x38421C, "addss xmm0, dword ptr [rax + 8]", None,
     "wp03 (384010, sub-state 1): position.z gains persistent launch velocity +E18 "
     "each tick; scale the copied velocity for this move"),
    # wp10 launch/move (38BA10)
    ("player", "pre", 0x38BC06, "addss xmm0, dword ptr [rax]", None,
     "wp10 (38BA10, sub-state 1): position.x gains persistent launch velocity +E10 "
     "each tick; scale the copied velocity for this move while leaving the stored "
     "velocity stock-valued"),
    ("player", "pre", 0x38BC22, "addss xmm0, dword ptr [rax + 4]", None,
     "wp10 (38BA10, sub-state 1): position.y gains persistent launch velocity +E14 "
     "each tick; scale the copied velocity for this move"),
    ("player", "pre", 0x38BC3B, "addss xmm0, dword ptr [rax + 8]", None,
     "wp10 (38BA10, sub-state 1): position.z gains persistent launch velocity +E18 "
     "each tick; scale the copied velocity for this move"),
    # wp12 launch/move (38CF10)
    ("player", "pre", 0x38D0E1, "addss xmm0, dword ptr [rax]", None,
     "wp12 (38CF10, sub-state 1): position.x gains persistent launch velocity +E10 "
     "each tick; scale the copied velocity for this move while leaving the stored "
     "velocity stock-valued"),
    ("player", "pre", 0x38D0F8, "addss xmm0, dword ptr [rax + 4]", None,
     "wp12 (38CF10, sub-state 1): position.y gains persistent launch velocity +E14 "
     "each tick; scale the copied velocity for this move"),
    ("player", "pre", 0x38D111, "addss xmm0, dword ptr [rax + 8]", None,
     "wp12 (38CF10, sub-state 1): position.z gains persistent launch velocity +E18 "
     "each tick; scale the copied velocity for this move"),
    # pl00 ground drift copies (3B1560, 3B18D0, 3B2620)
    ("player", "pre", 0x3B184B, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 sub-handler 3B1560: persistent ground-drift velocity +10B8 gains the "
     "computed 0.1 x ground-vector z push each tick; keep the velocity in stock units "
     "and add s of the push"),
    ("player", "pre", 0x3B1853, "addss xmm2, dword ptr [rdi + 0x10b0]", None,
     "pl00 sub-handler 3B1560: persistent ground-drift velocity +10B0 gains the "
     "computed 0.1 x ground-vector x push each tick; add s of the push"),
    ("player", "pre", 0x3B186B, "addss xmm2, dword ptr [rax]", None,
     "pl00 sub-handler 3B1560: position.x gains persistent stock-valued +10B0 each "
     "tick; scale the velocity copy for this move"),
    ("player", "pre", 0x3B1882, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 sub-handler 3B1560: position.z gains persistent stock-valued +10B8 each "
     "tick; scale the velocity copy for this move"),
    ("player", "lin", 0x3B210A, "movss xmm0, dword ptr [rip + 0x2c54de]",
     (0x6775F0, 0.05000000074505806),
     "pl00 state 0 (3B18D0): +E48 is a displacement per current-rate tick, so scale "
     "its stock 0.05 stopping threshold by s before the ordered compare"),
    ("player", "pre", 0x3B2282, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 0 (3B18D0): persistent ground-drift velocity +10B8 gains the computed "
     "0.1 x ground-vector z push each tick; add s of the push"),
    ("player", "pre", 0x3B228A, "addss xmm2, dword ptr [rdi + 0x10b0]", None,
     "pl00 state 0 (3B18D0): persistent ground-drift velocity +10B0 gains the computed "
     "0.1 x ground-vector x push each tick; add s of the push"),
    ("player", "pre", 0x3B22A2, "addss xmm2, dword ptr [rax]", None,
     "pl00 state 0 (3B18D0): position.x gains persistent stock-valued +10B0 each tick; "
     "scale the velocity copy for this move"),
    ("player", "srcx", 0x3B22B6, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 0 (3B18D0): position.z in xmm0 gains persistent stock-valued +10B8 "
     "from memory each tick; scale only the source velocity"),
    ("player", "pre", 0x3B2A6F, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 1 (3B2620): persistent ground-drift velocity +10B8 gains the computed "
     "0.1 x ground-vector z push each tick; add s of the push"),
    ("player", "pre", 0x3B2A77, "addss xmm2, dword ptr [rdi + 0x10b0]", None,
     "pl00 state 1 (3B2620): persistent ground-drift velocity +10B0 gains the computed "
     "0.1 x ground-vector x push each tick; add s of the push"),
    ("player", "pre", 0x3B2A8F, "addss xmm2, dword ptr [rax]", None,
     "pl00 state 1 (3B2620): position.x gains persistent stock-valued +10B0 each tick; "
     "scale the velocity copy for this move"),
    ("player", "srcx", 0x3B2AA3, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 1 (3B2620): position.z in xmm0 gains persistent stock-valued +10B8 "
     "from memory each tick; scale only the source velocity"),
    ("player", "pre", 0x3B0A5D, "addss xmm0, dword ptr [rax]", None,
     "pl00 sub-handler 3B06F0: position.x gains persistent stock-valued launch/recoil "
     "velocity +E10 each tick; scale the velocity copy for this move"),
    ("player", "srcx", 0x3B0A71, "addss xmm0, dword ptr [rdi + 0xe18]", None,
     "pl00 sub-handler 3B06F0: position.z in xmm0 gains persistent stock-valued "
     "launch/recoil velocity +E18 from memory each tick; scale only the source "
     "velocity"),
    ("player", "count", 0x3B3354, "mulss xmm0, dword ptr [rip + 0x2c6918]", "factor",
     "pl01 (3B2CF0): while held UI-state global B6B2AC bit 30 is set, +E48 takes the "
     "extra 0.4 damping once on the first tick of each stock period"),
    # Completed six-function batch.
    # pl00 all-slot auxiliary projectile/effect update (3CCC50)
    ("player", "pre", 0x3CCDAD, "addss xmm0, dword ptr [rbp]", None,
     "pl00 all-slot auxiliary update (3CCC50): position.x gains persistent "
     "stock-valued velocity.x each tick; scale the velocity copy for this move"),
    ("player", "pre", 0x3CCDC4, "addss xmm1, dword ptr [rbx + rax*8 + 0x1478]", None,
     "pl00 all-slot auxiliary update (3CCC50): position.z gains persistent "
     "stock-valued velocity.z each tick; scale the velocity copy for this move"),
    ("player", "pre", 0x3CCDD5, "addss xmm0, dword ptr [rbx + rax*8 + 0x1474]", None,
     "pl00 all-slot auxiliary update (3CCC50): position.y gains persistent "
     "stock-valued velocity.y each tick; scale the velocity copy for this move"),
    ("player", "countlast", 0x3CCDDE, "subss xmm2, xmm6", None,
     "pl00 all-slot auxiliary update (3CCC50): vertical velocity loses 0.6 once per "
     "stock period, after the period's scaled position move"),
    ("player", "count", 0x3CCE52, "mov byte ptr [rdi + rbx + 0x15b8], al", None,
     "pl00 all-slot auxiliary update (3CCC50): +15B8[slot] lifetime decrements once "
     "per stock tick"),
    ("player", "notyet", 0x3CCE59, "test cl, cl", 0x3CCE65,
     "pl00 all-slot auxiliary update (3CCC50): hold the lifetime's old-value zero test "
     "and state-3 transition between stock ticks"),
    # pl00 state handler (3BDCB0)
    ("player", "lin", 0x3BE1E7, "addss xmm0, dword ptr [rip + 0x2f0e0d]",
     (0x6AEFFC, 0.6800000071525574),
     "pl00 state handler 3BDCB0, sub-state 1: position.y gains 0.68 per tick; scale "
     "the spatial step by s"),
    ("player", "lin", 0x3BE1FC, "addss xmm1, dword ptr [rip + 0x2f0dec]",
     (0x6AEFF0, 0.3059999942779541),
     "pl00 state handler 3BDCB0, sub-state 1: vertical speed +E54 gains 0.306 per "
     "tick; scale the acceleration step by s"),
    # pl00 ground-motion state (3C3C70)
    ("player", "count", 0x3C3F3B, "add word ptr [rdi + 0xe3c], 8", None,
     "pl00 state 3C3C70: +E3C's eight-degree sine-wobble phase step advances once per "
     "stock tick"),
    ("player", "pre", 0x3C4122, "addss xmm2, dword ptr [rdi + 0x10b0]", None,
     "pl00 state 3C3C70: persistent ground-drift velocity +10B0 gains the computed 0.1 "
     "x ground-vector x push each tick; add s of the push"),
    ("player", "pre", 0x3C4140, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 3C3C70: persistent ground-drift velocity +10B8 gains the computed 0.1 "
     "x ground-vector z push each tick; add s of the push"),
    ("player", "pre", 0x3C4157, "addss xmm2, dword ptr [rax]", None,
     "pl00 state 3C3C70: position.x gains persistent stock-valued +10B0 each tick; "
     "scale the velocity copy for this move"),
    ("player", "srcx", 0x3C416B, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 3C3C70: position.z in xmm0 gains persistent stock-valued +10B8 from "
     "memory each tick; scale only the source velocity"),
    # pl00 state handler (3CC270)
    ("player", "count", 0x3CC466, "movss dword ptr [rbx + 0xe48], xmm0", None,
     "pl00 state 3CC270: persistent forward speed +E48 is multiplied by 0.4 once per "
     "stock tick"),
    # pl00 paired byte-timer state machine (3CD1A0)
    ("player", "count", 0x3CD1DF, "mov byte ptr [rbx + 0x115c], al", None,
     "pl00 timer helper 3CD1A0, +115D mode 2: +115C decrements once per stock tick"),
    ("player", "notyet", 0x3CD1E5, "test dl, dl", 0x3CD446,
     "pl00 timer helper 3CD1A0, +115D mode 2: hold the old-value zero test and its "
     "effect transition between stock ticks"),
    ("player", "count", 0x3CD2D9, "mov byte ptr [rbx + 0x115c], al", None,
     "pl00 timer helper 3CD1A0, +115D mode 1: +115C decrements once per stock tick"),
    ("player", "notyet", 0x3CD2DF, "test cl, cl", 0x3CD446,
     "pl00 timer helper 3CD1A0, +115D mode 1: hold the old-value zero test and its "
     "effect transition between stock ticks"),
    # pl00 common tick/effect sequencer (3CD460)
    ("player", "count", 0x3CD583, "inc word ptr [rbx + 0x114a]", None,
     "pl00 sequencer 3CD460: +114A's elapsed-tick count increments once per stock tick"),
    ("player", "notyet", 0x3CD593, "cmp word ptr [rbx + 0x114a], 1", 0x3CD5CF,
     "pl00 sequencer 3CD460: let the +114A == 1 first-tick effect fire only on a stock "
     "tick"),
    ("player", "count", 0x3CD5CF, "inc byte ptr [rbx + 0x1150]", None,
     "pl00 sequencer 3CD460: +1150's eight-tick phase counter increments once per "
     "stock tick"),
    ("player", "notyet", 0x3CD5DE, "cmp al, 1", 0x3CD696,
     "pl00 sequencer 3CD460: let the (+1150 & 7) == 1 periodic effect fire only on a "
     "stock tick"),
    ("player", "notyet", 0x3CD6AA, "cmp eax, ecx", 0x3CD6F8,
     "pl00 sequencer 3CD460: hold the +114A + 1 threshold effect between stock ticks"),
    ("player", "notyet", 0x3CD70C, "cmp eax, ecx", 0x3CD761,
     "pl00 sequencer 3CD460: hold the second +114A + 1 threshold effect and +1150 "
     "reset between stock ticks"),
    # Dormant sibling of 3CCC50 (3CCEA0).
    # No code/data-pointer/export call path exists in this build. These rows are safe today
    # because the helper is unreachable; a future caller must invoke it as a per-frame slot update.
    ("player", "pre", 0x3CCFB5, "addss xmm0, dword ptr [rbp]", None,
     "pl00 dormant single-slot auxiliary update (3CCEA0): position.x gains persistent "
     "stock-valued velocity.x each tick; scale the velocity copy for this move"),
    ("player", "pre", 0x3CCFC4, "addss xmm1, dword ptr [rsi + r14*8 + 0x1478]", None,
     "pl00 dormant single-slot auxiliary update (3CCEA0): position.z gains persistent "
     "stock-valued velocity.z each tick; scale the velocity copy for this move"),
    ("player", "pre", 0x3CCFD6, "addss xmm0, dword ptr [rsi + r14*8 + 0x1474]", None,
     "pl00 dormant single-slot auxiliary update (3CCEA0): position.y gains persistent "
     "stock-valued velocity.y each tick; scale the velocity copy for this move"),
    ("player", "countlast", 0x3CCFE0, "subss xmm2, dword ptr [rip + 0x2a4e24]", None,
     "pl00 dormant single-slot auxiliary update (3CCEA0): vertical velocity loses 0.6 "
     "once per stock period, after the period's scaled position move"),
    ("player", "count", 0x3CD076, "mov byte ptr [rdi + 0x15b8], al", None,
     "pl00 dormant single-slot auxiliary update (3CCEA0): +15B8[slot] lifetime "
     "decrements once per stock tick"),
    ("player", "notyet", 0x3CD07C, "test cl, cl", 0x3CD087,
     "pl00 dormant single-slot auxiliary update (3CCEA0): hold the old-value zero test "
     "and state-3 transition between stock ticks"),
    ("player", "dst", 0x39B98A, "movaps xmm6, xmm0", ("slowmo",0x39B976),
     "wp47 (39B950): cache the current-rate delta in callee-saved xmm6; its only live "
     "reader subtracts it from the +10EC sound/effect cooldown, and no animation-rate "
     "reader consumes this copy"),
    ("player", "lin", 0x39C3AD, "addss xmm0, dword ptr [rip + 0x2d8ba3]", (0x674F58, 3.0),
     "wp47 (39C0B0): scale the repeated +3 growth step of collision radius +E18; the "
     "53-unit clamp remains spatial"),
    ("player", "lin", 0x39C3E1, "subss xmm1, dword ptr [rip + 0x2d9693]", (0x675A7C, 6.0),
     "wp47 (39C0B0): scale the repeated -6 shrink step of collision radius +E18; the "
     "21-unit clamp remains spatial"),
    ("player", "lin", 0x39C78F, "addss xmm0, dword ptr [rip + 0x2d87c1]", (0x674F58, 3.0),
     "wp47 (39C540): scale the repeated +3 growth step of collision radius +E18; the "
     "53-unit clamp remains spatial"),
    ("player", "lin", 0x39C81F, "subss xmm1, dword ptr [rip + 0x2d9255]", (0x675A7C, 6.0),
     "wp47 (39C540): scale the repeated -6 shrink step of collision radius +E18; the "
     "21-unit clamp remains spatial"),
    ("player", "count", 0x39C8C5, "mov word ptr [rdi + 0xe3c], ax", None,
     "wp47 (39C540): +E3C is initialized to 10 then decremented once per stock tick "
     "before the terminal state transition"),
    ("player", "pre", 0x39D697, "addss xmm6, dword ptr [rax + 0xb0]", None,
     "wp49 (39D600): scale the random per-tick +B0 perturbation before accumulating it"),
    ("player", "pre", 0x39D6C9, "addss xmm6, dword ptr [rax + 0xb8]", None,
     "wp49 (39D600): scale the random per-tick +B8 perturbation before accumulating it"),
    ("player", "pre", 0x39D763, "addss xmm6, dword ptr [rax + 0xb0]", None,
     "wp49 (39D600): scale the alternate random per-tick +B0 perturbation before "
     "accumulating it"),
    # plwpsub/wp shared fade (3D27F0)
    ("player", "count", 0x3D2863, "mov byte ptr [rbx + 0x1070], al", None,
     "pl weapon sub-object update (3D27F0): +1070 fades down by 10 toward 0; commit "
     "the clamped byte only on stock ticks"),
    ("player", "count", 0x3D2878, "mov byte ptr [rbx + 0x1070], al", None,
     "pl weapon sub-object update (3D27F0): +1070 fades up by 10 toward 255; commit "
     "the clamped byte only on stock ticks"),
    # pl00 pose wobble and ground slide (3C43C0)
    ("player", "count", 0x3C465B, "add word ptr [rdi + 0xe3c], 8", None,
     "pl00 (3C43C0): +E3C is the phase of the submodel-y sine wobble and advances by 8 "
     "degrees once per stock tick"),
    ("player", "pre", 0x3C497F, "addss xmm2, dword ptr [rdi + 0x10b0]", None,
     "pl00 (3C43C0), grounded slide: persistent stock-valued +10B0 gains s of the "
     "0.1-scaled ground-vector x acceleration"),
    ("player", "pre", 0x3C499D, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 (3C43C0), grounded slide: persistent stock-valued +10B8 gains s of the "
     "0.1-scaled ground-vector z acceleration"),
    ("player", "pre", 0x3C49B4, "addss xmm2, dword ptr [rax]", None,
     "pl00 (3C43C0), grounded slide: position.x gains s of the resulting stock-valued "
     "+10B0 velocity before its existing 0.9^s damping"),
    ("player", "pre", 0x3C49CB, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 (3C43C0), grounded slide: position.z gains s of the resulting stock-valued "
     "+10B8 velocity before its existing 0.9^s damping"),
    # pl00 sibling grounded slide (3C4D90)
    ("player", "pre", 0x3C513C, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 (3C4D90), grounded slide: persistent stock-valued +10B8 gains s of the "
     "0.1-scaled ground-vector z acceleration"),
    ("player", "pre", 0x3C5144, "addss xmm2, dword ptr [rdi + 0x10b0]", None,
     "pl00 (3C4D90), grounded slide: persistent stock-valued +10B0 gains s of the "
     "0.1-scaled ground-vector x acceleration"),
    ("player", "pre", 0x3C515C, "addss xmm2, dword ptr [rax]", None,
     "pl00 (3C4D90), grounded slide: position.x gains s of the resulting stock-valued "
     "+10B0 velocity before its existing 0.9^s damping"),
    ("player", "srcx", 0x3C5170, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 (3C4D90), grounded slide: position.z gains s of source +10B8 while the "
     "destination register already holds position.z"),
    # held UI-state braking (3C5350, 3C57A0)
    ("player", "count", 0x3C567C, "mulss xmm0, dword ptr [rip + 0x2ac780]", "factor",
     "pl00 (3C5350): while held UI-state global B6B2AC bit 30 is set, keep the +E48 "
     "factor 0.1 only on the first tick of each stock period"),
    # 3C57A0 has three 2DDF90 turn calls: the state-0 call at 3C5C9D is one-shot and intentionally remains full-sized
    ("player", "callscale", 0x3C5A87, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 (3C57A0), sub-state 3: turn continuously toward the linked actor by at most "
     "0.139626 radians per tick; scale the call's limit"),
    ("player", "callscale", 0x3C5D14, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 (3C57A0), sub-state 1: turn continuously toward the linked actor by at most "
     "0.279253 radians per tick; scale the call's limit"),
    ("player", "count", 0x3C5E72, "mulss xmm0, dword ptr [rip + 0x2abf8a]", "factor",
     "pl00 (3C57A0): while held UI-state global B6B2AC bit 30 is set, keep the +E48 "
     "factor 0.1 only on the first tick of each stock period"),
    # pl00 attack-combo speed cap (3B7320), state 0: E48 is a displacement at this rate.
    # The three sites jointly implement min(E48 + 2*s, 3*s), equivalent to
    # min(E48/s + 2, 3)*s in stock-tick units. Their compound check lives in
    # verify_world_anims.py as well as the ordinary per-window check.
    ("player", "lin", 0x3B75C0, "addss xmm0, dword ptr [rip + 0x2ba84c]", (0x671E14, 2.0),
     "pl00 combo state 0: add s of the stock +2 acceleration to the already "
     "current-rate +E48 displacement"),
    ("player", "srcx", 0x3B75C8, "comiss xmm0, dword ptr [rip + 0x2bd989]", None,
     "pl00 combo state 0: compare the accelerated current-rate +E48 with s of the "
     "stock 3 cap; preserve the original branch flags"),
    ("player", "immstore", 0x3B75D9, "mov dword ptr [rdi + 0xe48], 0x40400000", None,
     "pl00 combo state 0: when the cap branch is taken, write the immediate stock 3 as "
     "a current-rate displacement 3*s"),
    ("player", "blend", 0x3BEC87, "mulss xmm1, dword ptr [rip + 0x2b3c9d]",
     (0x67292C, 0.20000000298023224),
     "pl00 state 3BEB40: persistent +E48 approaches the held +E18 speed by 0.2 of the "
     "gap on every update; use 1-(1-0.2)^s so the approach is per-second invariant"),
    ("player", "blend", 0x3C39FA, "mulss xmm1, dword ptr [rip + 0x2aef2a]",
     (0x67292C, 0.20000000298023224),
     "pl00 state 3C38C0: persistent +E48 approaches the held +E18 speed by 0.2 of the "
     "gap on every update; this sibling uses the same rate-converted gap factor"),
    # Pl00 shared +1156 normal-update clock. Each state owns one increment path;
    # the 0x1C2/0x1C3 limit readers compare the same stored clock after it advances.
    ("player", "count", 0x3C422F, "inc word ptr [rbx + 0x1156]", None,
     "pl00 state 3C41F0: advance +1156 once per stock tick when the action is active "
     "and the two input-block bits are clear"),
    ("player", "count", 0x3C4A78, "inc word ptr [rdi + 0x1156]", None,
     "pl00 state 3C4A30: the sibling normal-update +1156 advance has the same gated "
     "stock-tick cadence"),
    ("player", "count", 0x3C521F, "inc word ptr [rbx + 0x1156]", None,
     "pl00 state 3C51E0: advance +1156 once per stock tick before the 0x1C2 timeout "
     "comparison"),
    ("player", "count", 0x3C9E82, "inc word ptr [rdi + 0x1156]", None,
     "pl00 state 3C9E30: advance +1156 once per stock tick before the 0x1C2 timeout "
     "comparison"),
    ("player", "count", 0x3CD97D, "inc word ptr [rcx + 0x1156]", None,
     "pl00 shared helper 3CD950: advance +1156 once per stock tick while its pause and "
     "input-block gates are clear"),
    ("player", "count", 0x3CD9DD, "inc word ptr [rcx + 0x1158]", None,
     "pl00 shared helper 3CD9B0: advance +1158 once per stock tick while its pause and "
     "input-block gates are clear; +1158 is compared with +1156 and the 0x12C event "
     "threshold"),
    # wp1d slow-motion-paced state machines (390C00, 391290, 3915E0)
    ("player", "dst", 0x390C2F, "movaps xmm7, xmm0", ("slowmo",0x390C26),
     "wp1d (390C00): xmm7 is 23AD90's slow-motion dt; every live reader is a per-tick "
     "step: movement by +E10 x dt, +E18 growth, +E28 and +1078 countdowns, two clamped "
     "turns, the sin(+1110) y move and the +1110 phase step; no animation-rate reader"),
    ("player", "dst", 0x3912C3, "movaps xmm7, xmm0", ("slowmo",0x3912B9),
     "wp1d (391290): xmm7 is 23AD90's slow-motion dt; its only live readers move by "
     "+E10 x dt, grow +E18 by dt and count +E28 down by dt; no animation-rate reader"),
    ("player", "lin", 0x39151F, "addss xmm6, dword ptr [rip + 0x2ed75d]",
     (0x67EC84, 1.399999976158142),
     "wp1d (391290): collision radius +E24 grows by 1.4 each tick before it is passed "
     "to 2DC7B0; scale the repeated spatial-size ramp step"),
    ("player", "dst", 0x391643, "movaps xmm7, xmm0", ("slowmo",0x391621),
     "wp1d (3915E0): xmm7 is 23AD90's slow-motion dt; every live reader is a per-tick "
     "step: movement by +E10 x dt, +E18 growth, +E28 and +1078 countdowns, two clamped "
     "turns, +1090 growth, the sin(+1110) y move and the +1110 phase step; no "
     "animation-rate reader"),
    # wp47 and wp51 countdowns / phase
    ("player", "dst", 0x39B409, "movaps xmm7, xmm0", ("slowmo",0x39B3FB),
     "wp47 (39B3D0): xmm7 is 23AD90's slow-motion dt; its only live readers subtract "
     "dt from the +10F0 sound cooldown and +10EC state countdown; no animation-rate "
     "reader"),
    ("player", "dst", 0x39E7C5, "movaps xmm9, xmm0", ("slowmo",0x39E7B7),
     "wp51 (39E790): xmm9 is 23AD90's slow-motion dt; its only live reader subtracts "
     "dt from +10F0; no animation-rate reader"),
    ("player", "lin", 0x39E935, "subss xmm0, dword ptr [rip + 0x2db2f7]",
     (0x679C34, 0.06981316953897476),
     "wp51 (39E790): +1110 loses four degrees each tick on the reflected-orbit branch; "
     "scale the phase step"),
    ("player", "lin", 0x39E93F, "addss xmm0, dword ptr [rip + 0x2db2ed]",
     (0x679C34, 0.06981316953897476),
     "wp51 (39E790): +1110 gains four degrees each tick on the other orbit branch; "
     "scale the phase step"),
    # wp00 state handler (37F1E0)
    ("player", "lin", 0x37F494, "addss xmm0, dword ptr [rip + 0x2fa7b0]",
     (0x679C4C, 0.5235987901687622),
     "wp00 state 37F1E0: +B0's continuous 30-degree spin step advances every rising "
     "update; scale the angular step by s"),
    # wp1b grounded-flight helper (38E720)
    ("player", "dst", 0x38E792, "movss xmm0, dword ptr [rbx + 0xfe0]", None,
     "wp1b helper 38E720: load grounded slope +FE0 and scale it once toward the s^2 "
     "change of persistent per-current-rate velocity +E20"),
    ("player", "dst", 0x38E79A, "movss xmm1, dword ptr [rbx + 0xfe8]", None,
     "wp1b helper 38E720: load grounded slope +FE8 and scale it once toward the s^2 "
     "change of persistent per-current-rate velocity +E28"),
    ("player", "pre", 0x38E7A2, "addss xmm0, dword ptr [rbx + 0xe20]", None,
     "wp1b helper 38E720: scale the already s-scaled slope in xmm0 again before adding "
     "it to +E20, giving an s^2 velocity change"),
    ("player", "pre", 0x38E7AA, "addss xmm1, dword ptr [rbx + 0xe28]", None,
     "wp1b helper 38E720: scale the already s-scaled slope in xmm1 again before adding "
     "it to +E28, giving an s^2 velocity change"),
    # wp1c grounded-flight helper (38F240)
    ("player", "dst", 0x38F2BA, "mulss xmm0, dword ptr [rip + 0x2e2b46]", None,
     "wp1c helper 38F240: after applying the 0.5 slope factor, scale the resulting "
     "+FE0 push once toward the s^2 change of persistent current-rate velocity +E20"),
    ("player", "pre", 0x38F2C2, "addss xmm0, dword ptr [rbx + 0xe20]", None,
     "wp1c helper 38F240: after the 0.5 slope factor, scale xmm0 again before adding "
     "it to +E20, giving an s^2 velocity change"),
    ("player", "dst", 0x38F2DA, "mulss xmm0, dword ptr [rip + 0x2e2b26]", None,
     "wp1c helper 38F240: after applying the 0.5 slope factor, scale the resulting "
     "+FE8 push once toward the s^2 change of persistent current-rate velocity +E28"),
    ("player", "pre", 0x38F2E2, "addss xmm0, dword ptr [rbx + 0xe28]", None,
     "wp1c helper 38F240: after the 0.5 slope factor, scale xmm0 again before adding "
     "it to +E28, giving an s^2 velocity change"),
    # wp47 common state handler (39A840)
    ("player", "count", 0x39A89F, "dec byte ptr [rcx + 0x10f6]", None,
     "wp47 state 39A840: first of the normal two +10F6 countdown decrements commits "
     "once per stock tick"),
    ("player", "count", 0x39A8C5, "mov byte ptr [rbx + 0x10f6], al", None,
     "wp47 state 39A840: second +10F6 decrement commits on the same stock tick; the "
     "special global path can still force zero immediately"),
    # pl00 state handlers (3BC300, 3C1010)
    ("player", "notyet", 0x3BC4C4, "test cx, cx", 0x3BC4D0,
     "pl00 state 3BC300, state 3: hold +E3C's old-value zero transition between stock "
     "ticks"),
    ("player", "lin", 0x3C10FD, "movss xmm3, dword ptr [rip + 0x2b8b07]",
     (0x679C0C, 0.1745329201221466),
     "pl00 state 3C1010, state 1: scale the continuous 10-degree per-tick target-turn "
     "limit before 2DDF90"),
    ("player", "callscale", 0x3CA220, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 state 3CA160, sub-state 3: the 0.279253-radian target-heading limit runs on "
     "each update until animation completion, so scale the call's angular limit"),
    ("player", "callscale", 0x3CA2D3, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "pl00 state 3CA160, sub-state 1: the sibling 0.279253-radian target-heading limit "
     "runs on each update until animation completion"),
    # wp06 guided flight (385A60)
    ("player", "pre", 0x385B49, "addss xmm0, dword ptr [rax]", None,
     "wp06 (385A60): position.x gains s of the persistent stock-valued +E10 velocity"),
    ("player", "pre", 0x385B60, "addss xmm0, dword ptr [rax + 4]", None,
     "wp06 (385A60): position.y gains s of the persistent stock-valued +E14 velocity"),
    ("player", "pre", 0x385B79, "addss xmm0, dword ptr [rax + 8]", None,
     "wp06 (385A60): position.z gains s of the persistent stock-valued +E18 velocity"),
    # wp03 movement and spin (383AB0)
    ("player", "callscale", 0x383CF7, "call 0x1802ddf90", (0x2DDF90,"xmm3"),
     "wp03 (383AB0), state 1: turn continuously toward the owner by at most one degree "
     "per tick; scale the call limit"),
    ("player", "callscale", 0x383D1F, "call 0x1802da460", (0x2DA460,"xmm1"),
     "wp03 (383AB0), state 1: 2DA460 adds the stock-valued +E28 forward speed directly "
     "to position; scale its xmm1 argument"),
    ("player", "lin", 0x383D2C, "addss xmm0, dword ptr [rip + 0x2f5ee0]",
     (0x679C14, 0.2617993950843811),
     "wp03 (383AB0), state 1: +B0 spins by 15 degrees per tick; add s of the phase "
     "step"),
    ("player", "callscale", 0x383EA6, "call 0x1802da460", (0x2DA460,"xmm1"),
     "wp03 (383AB0), state 4: 2DA460 adds the random per-tick forward speed directly "
     "to position; scale its xmm1 argument"),
    ("player", "count", 0x383ED6, "movss dword ptr [rdi + 0xb0], xmm0", None,
     "wp03 (383AB0), state 4: commit +B0's changing +E3C-degree spin step once per "
     "stock tick, before +E3C decrements"),
    ("player", "count", 0x383EDE, "mov word ptr [rdi + 0xe3c], bx", None,
     "wp03 (383AB0), state 4: commit +E3C's decrement once per stock tick after the "
     "spin step"),
    ("player", "notyet", 0x383EE5, "test bx, bx", 0x383F2B,
     "wp03 (383AB0), state 4: while +E3C's store is held, keep its terminal effect and "
     "state transition on stock ticks"),
    # wp0d cyclic scale phase (388FD0)
    ("player", "count", 0x3891A2, "mov word ptr [rsi + 0xe3c], di", None,
     "wp0d (388FD0): +E3C advances the two cyclic sine-scale waveforms by one count "
     "per stock tick"),
    # wp04 post-motion wait (384BE0)
    ("player", "notyet", 0x384CFC, "test al, al", 0x384D04,
     "wp04 (384BE0), state 3: while +E37 is held at zero between stock ticks, defer "
     "the state transition to its next stock tick"),
    ("player", "count", 0x384D06, "mov byte ptr [rbx + 0xe37], al", None,
     "wp04 (384BE0), state 3: commit the optional three-tick post-motion +E37 "
     "countdown once per stock tick"),
    # pl03 shared scale approach (3A4DF0)
    ("player", "blend", 0x3A4E3C, "movss xmm2, dword ptr [rip + 0x2d27ac]",
     (0x6775F0, 0.05000000074505806),
     "pl03 (3A4DF0): +D20/+D24/+D28 approach 1 by the shared 0.05 factor each tick; "
     "use 1-(1-0.05)^s"),
    # pl03 every-eighth-tick sound (3A4DF0)
    ("player", "count", 0x3A4EE4, "mov byte ptr [rdi + 0x2250], al", None,
     "pl03 (3A4DF0): commit +2250's increment once per stock tick; cl keeps the old "
     "count for the following modulo-eight event test"),
    ("player", "notyet", 0x3A4EEA, "and cl, 7", 0x3A4F14,
     "pl03 (3A4DF0): on held ticks still apply `and cl, 7`, then force its jne down "
     "the no-sound path so sound 0x40B fires only on stock ticks"),
    # Shared wp/enemy visual update (33A560)
    ("player", "notyet", 0x33AA89, "test ax, ax", 0x33AAC9,
     "shared wp/enemy update 33A560, type 398: hold +E3E's old-value zero effect "
     "between stock ticks"),
    ("player", "count", 0x33AACC, "mov word ptr [r14 + 0xe3e], ax", None,
     "shared wp/enemy update 33A560, type 398: +E3E's repeating two-count effect timer "
     "decrements once per stock tick"),
    # wp09 slow-motion-paced state (387990)
    ("player", "dst", 0x3879B7, "movaps xmm6, xmm0", ("slowmo",0x3879A9),
     "wp09 state 387990: xmm6 is 23AD90's slow-motion dt; its only live readers count "
     "+1110 down and move forward by 6.5 times dt, both per-tick steps"),
    # Weapon fades and stock-valued vertical movement
    ("player", "srcx", 0x38CB20, "subss xmm1, xmm0", None,
     "wp12 helper 38CB10: +D2C loses s of the 0.1 fade step while xmm0 retains the "
     "stock 0.1 terminal threshold used by the following comparison"),
    ("player", "srcx", 0x38D5A6, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "wp1a common update 38D490: position.y in xmm0 gains s of stock-valued vertical "
     "speed +E54"),
    ("player", "pre", 0x38E540, "addss xmm0, dword ptr [rax + 4]", None,
     "wp1b common update 38E400: +E54 in xmm0 is stock-valued vertical speed; scale it "
     "before adding the existing position.y from memory"),
    # Companion hidden by decay_factors.h proximity in coverage.
    ("player", "srcx", 0x38F03F, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "wp1c common update 38EEE0: position.y in xmm0 gains s of stock-valued vertical "
     "speed +E54 before its 0.94^s damping"),
    # wp5a slow-motion-paced state (3A0D00)
    ("player", "dst", 0x3A0D44, "movaps xmm6, xmm0", ("slowmo",0x3A0D1E),
     "wp5a state 3A0D00: xmm6 is 23AD90's slow-motion dt; its only live readers count "
     "+10F0 down and drive the forward move, both per-tick steps"),
    # pl00 common visual sequencer (3A7950)
    ("player", "count", 0x3A79C1, "inc byte ptr [rdi + 0x1170]", None,
     "pl00 helper 3A7950: +1170 advances through its cyclic submodel-angle table once "
     "per stock tick"),
    # pl00 grounded drift state (3C9940)
    ("player", "pre", 0x3C9D81, "addss xmm2, dword ptr [rdi + 0x10b0]", None,
     "pl00 state 3C9940: persistent ground-drift velocity +10B0 gains s of the "
     "computed 0.1 times ground-vector x push"),
    ("player", "pre", 0x3C9D9F, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 3C9940: persistent ground-drift velocity +10B8 gains s of the "
     "computed 0.1 times ground-vector z push"),
    ("player", "pre", 0x3C9DB6, "addss xmm2, dword ptr [rax]", None,
     "pl00 state 3C9940: position.x gains s of the resulting stock-valued +10B0 "
     "velocity"),
    ("player", "srcx", 0x3C9DCA, "addss xmm0, dword ptr [rdi + 0x10b8]", None,
     "pl00 state 3C9940: position.z in xmm0 gains s of stock-valued +10B8 from memory"),
    # pl00 linked-actor countdown states
    ("player", "notyet", 0x3D03F0, "test ax, ax", 0x3D0420,
     "pl00 state 3D01F0: hold +E3C's old-value zero effect and completion path between "
     "stock ticks"),
    ("player", "count", 0x3D0426, "mov word ptr [rsi + 0xe3c], ax", None,
     "pl00 state 3D01F0: +E3C decrements once per stock tick"),
    ("player", "notyet", 0x3D1624, "test ax, ax", 0x3D163A,
     "pl00 state 3D14B0: hold +E3C's old-value zero cleanup between stock ticks"),
    ("player", "count", 0x3D163D, "mov word ptr [rbx + 0xe3c], ax", None,
     "pl00 state 3D14B0: +E3C decrements once per stock tick while the linked actor "
     "remains valid"),
    ("player", "notyet", 0x3D1778, "test ax, ax", 0x3D1786,
     "pl00 state 3D1670: hold +E3C's old-value zero state transition between stock "
     "ticks"),
    ("player", "count", 0x3D1789, "mov word ptr [rbx + 0xe3c], ax", None,
     "pl00 state 3D1670: +E3C decrements once per stock tick while the linked actor "
     "remains valid"),
    ("player", "notyet", 0x3D1895, "test ax, ax", 0x3D18A2,
     "pl00 state 3D1820: hold +E3C's old-value zero state transition between stock "
     "ticks"),
    ("player", "count", 0x3D18A5, "mov word ptr [rcx + 0xe3c], ax", None,
     "pl00 state 3D1820: +E3C decrements once per stock tick while the linked actor "
     "remains valid"),
    ("player", "lin", 0x3BDE41, "subss xmm1, dword ptr [rip + 0x2f119b]",
     (0x6AEFE4, 0.11900000274181366),
     "pl00 state 3BDCB0, sub-state 3: persistent vertical speed +E54 loses the stock "
     "0.119 step per update when it is above the global threshold; scale this "
     "decrement by s"),
    ("player", "lin", 0x3BDE4B, "addss xmm1, dword ptr [rip + 0x2f1199]",
     (0x6AEFEC, 0.2549999952316284),
     "pl00 state 3BDCB0, sub-state 3: persistent vertical speed +E54 gains the stock "
     "0.255 step per update on the other side of the threshold; scale this increment "
     "by s"),
    ("player", "count", 0x459DA1, "add word ptr [rax + 0xe3e], r8w", None,
     "pl00 3C1830 calls this selected-subactor updater on held input every update (372 "
     "of 372 traced ticks); the selected actor's +E3E animation count gains "
     "state-derived 2 or 6 once per stock tick"),
    ("player", "count", 0x459DBE, "add word ptr [rcx + 0xe3c], r8w", None,
     "pl00 selected-subactor updater 459D90: the same actor's +E3C animation phase "
     "gains 20 times the state-derived step once per stock tick, before its 0x384 cap"),
    # Pl00 linked-actor state 3D1330.
    ("player", "count", 0x3D13F4, "mov word ptr [rbx + 0xe3c], ax", None,
     "pl00 state 3D1330: while held input bitset B6B0D0 or its companion global is "
     "active and +E3C exceeds 5, commit the conditional two-count decrease on stock "
     "ticks"),
    ("player", "notyet", 0x3D145C, "test ax, ax", 0x3D148C,
     "pl00 state 3D1330: when +E3C is held at zero between stock ticks, defer its "
     "cleanup/transition until the next stock tick"),
    ("player", "count", 0x3D1492, "mov word ptr [rbx + 0xe3c], ax", None,
     "pl00 state 3D1330: commit the ordinary one-count +E3C decrease on stock ticks "
     "after the zero test"),
    # uta4's four-part state machine 55F120 (states in +1300+i), called for each
    # part by 55F0A0 and 55FFF0. It mirrors em8f's proven 2D79F0 update.
    ("objects", "blendr", 0x55F1A8, "addss xmm8, xmm6", None,
     "uta4 part: case 1's anchor-approach factor is 0.02 times part index, applied to "
     "all three position lanes each update"),
    ("objects", "lin", 0x55F260, "mulss xmm1, dword ptr [rip + 0x112b9c]",
     (0x671E04, 0.10000000149011612),
     "uta4 part case 0/1: +5C alpha linearly approaches one; scale this instruction's "
     "0.1 literal"),
    ("objects", "ufirst", 0x55F2B6, "movss xmm6, dword ptr [rip + 0x12462a]", None,
     "uta4 part case 1: the three velocity lanes' 0.96 damping runs once per stock "
     "tick before the next move"),
    ("objects", "zfirst", 0x55F2C9, "mulss xmm0, xmm1", None,
     "uta4 part case 1: spring vx gains 0.002 times anchor-to-part x on the first tick "
     "of each stock period"),
    ("objects", "zfirst", 0x55F2E7, "mulss xmm0, xmm1", None,
     "uta4 part case 1: the same spring vy"),
    ("objects", "zfirst", 0x55F30F, "mulss xmm0, xmm1", None,
     "uta4 part case 1: the same spring vz"),
    ("objects", "count", 0x55F334, "mov word ptr [rsi + r14*2 + 0x1304], ax", None,
     "uta4 part case 1: +1304 phase increments once per stock tick, before its "
     "eight-degree sine wobble"),
    ("objects", "zfirst", 0x55F383, "mulss xmm0, dword ptr [rip + 0x11ab65]", None,
     "uta4 part case 1: the sine wobble adds its y velocity impulse once per stock "
     "tick"),
    ("objects", "scaledadd", 0x55F3C1, "call qword ptr [rip + 0x111a39]", None,
     "uta4 part case 1: position += persistent part velocity by cVec::operator+=; move "
     "by s of the vector each tick"),
    ("objects", "scaledadd", 0x55F499, "call qword ptr [rip + 0x111961]", None,
     "uta4 part case 3, knocked loose: position += the current velocity each tick, "
     "scaled by s"),
    ("objects", "lin", 0x55F4AF, "subss xmm0, dword ptr [rip + 0x11294d]",
     (0x671E04, 0.10000000149011612),
     "uta4 part case 3: gravity subtracts s of the stock 0.1 literal from vy after the "
     "move"),
    ("objects", "countlast", 0x55F4C9, "mulss xmm0, dword ptr [rip + 0x123ecb]", None,
     "uta4 part case 3: vx multiplies by negative 0.7 only on the last tick of each "
     "stock period, after the move"),
    ("objects", "countlast", 0x55F4DF, "mulss xmm0, dword ptr [rip + 0x123eb5]", None,
     "uta4 part case 3: the same alternating decay for vz"),
    ("objects", "count", 0x55F4FC, "mov word ptr [rsi + r14*2 + 0x130c], ax", None,
     "uta4 part case 3: +130C countdown steps once per stock tick"),
    ("objects", "notyet", 0x55F505, "test cx, cx", 0x55FD04,
     "uta4 part case 3: the test reads the old countdown, so defer the zero transition "
     "between stock ticks"),
    ("objects", "count", 0x55F546, "mov word ptr [rsi + r14*2 + 0x130c], ax", None,
     "uta4 part case 5: the hidden-state +130C countdown steps once per stock tick"),
    ("objects", "notyet", 0x55F54F, "test cx, cx", 0x55FD04,
     "uta4 part case 5: defer the zero transition while the countdown is held"),
    ("objects", "ufirst", 0x55F5EB, "movss xmm6, dword ptr [rip + 0x1242f5]", None,
     "uta4 part case 7: the three velocity lanes' 0.96 damping runs once per stock "
     "tick"),
    ("objects", "zfirst", 0x55F60B, "mulss xmm0, xmm1", None,
     "uta4 part case 7: spring vx gains its target-position error times 0.002 once per "
     "stock tick"),
    ("objects", "zfirst", 0x55F629, "mulss xmm2, xmm1", None,
     "uta4 part case 7: the same spring vy"),
    ("objects", "zfirst", 0x55F64B, "mulss xmm0, xmm1", None,
     "uta4 part case 7: the same spring vz"),
    ("objects", "count", 0x55F670, "mov word ptr [rsi + r14*2 + 0x1304], ax", None,
     "uta4 part case 7: +1304 wobble phase increments once per stock tick"),
    ("objects", "zfirst", 0x55F6BF, "mulss xmm0, dword ptr [rip + 0x11a829]", None,
     "uta4 part case 7: the sine wobble's y velocity impulse runs once per stock tick"),
    ("objects", "scaledadd", 0x55F6FD, "call qword ptr [rip + 0x1116fd]", None,
     "uta4 part case 7: position += s of persistent velocity"),
    ("objects", "blend", 0x55F7B2, "movss xmm2, dword ptr [rip + 0x116276]",
     (0x675A30, 0.30000001192092896),
     "uta4 part case 9: the three coordinates approach the body and offset at 0.3 per "
     "stock tick"),
    ("objects", "count", 0x55F849, "mov word ptr [rsi + r14*2 + 0x130c], ax", None,
     "uta4 part case 9: +130C countdown from ten steps on stock ticks while nonzero"),
    ("objects", "blend", 0x55F906, "mulss xmm1, dword ptr [rip + 0x11a366]",
     (0x679C74, 0.4000000059604645),
     "uta4 part case 11: position x approaches body plus offset by 0.4 per stock tick"),
    ("objects", "blend", 0x55F928, "mulss xmm1, dword ptr [rip + 0x11a344]",
     (0x679C74, 0.4000000059604645),
     "uta4 part case 11: the same for position z"),
    ("objects", "lin", 0x55F943, "subss xmm0, dword ptr [rip + 0x112fe5]",
     (0x672930, 0.8999999761581421),
     "uta4 part case 11: gravity subtracts s of the 0.9 literal from vy before the y "
     "move"),
    ("objects", "pre", 0x55F963, "addss xmm0, dword ptr [rax + 4]", None,
     "uta4 part case 11: position y adds s of the just-updated stock-valued vy"),
    ("objects", "ufirst", 0x55FA8A, "movss xmm6, dword ptr [rip + 0x123e56]", None,
     "uta4 part case 13: the three velocity lanes' 0.96 damping runs once per stock "
     "tick"),
    ("objects", "zfirst", 0x55FA9D, "mulss xmm0, xmm1", None,
     "uta4 part case 13: spring vx gains 0.001 times anchor-position error once per "
     "stock tick"),
    ("objects", "zfirst", 0x55FABB, "mulss xmm0, xmm1", None,
     "uta4 part case 13: the same spring vy"),
    ("objects", "zfirst", 0x55FAE3, "mulss xmm0, xmm1", None,
     "uta4 part case 13: the same spring vz"),
    ("objects", "count", 0x55FB08, "mov word ptr [rsi + r14*2 + 0x1304], ax", None,
     "uta4 part case 13: +1304 wobble phase increments once per stock tick"),
    ("objects", "zfirst", 0x55FB57, "mulss xmm0, dword ptr [rip + 0x11a0d1]", None,
     "uta4 part case 13: the sine wobble's y velocity impulse runs once per stock tick"),
    ("objects", "scaledadd", 0x55FB95, "call qword ptr [rip + 0x111265]", None,
     "uta4 part case 13: position += s of persistent velocity"),
    ("objects", "count", 0x55FBA7, "mov word ptr [rsi + r14*2 + 0x130c], ax", None,
     "uta4 part case 13: +130C countdown steps once per stock tick"),
    ("objects", "notyet", 0x55FBB0, "test cx, cx", 0x55FD04,
     "uta4 part case 13: the test reads the old countdown; hold its zero transition "
     "between stock ticks"),
    ("objects", "blend", 0x55FC19, "mulss xmm1, dword ptr [rip + 0x1121e3]",
     (0x671E04, 0.10000000149011612),
     "uta4 part case 15: +5C alpha fades toward zero at 0.1 per stock tick"),
    ("objects", "scaledadd", 0x55FC32, "call qword ptr [rip + 0x1111c8]", None,
     "uta4 part case 15: position += s of its thrown velocity"),
    ("objects", "lin", 0x55FC48, "subss xmm0, dword ptr [rip + 0x1121b4]",
     (0x671E04, 0.10000000149011612),
     "uta4 part case 15: gravity subtracts s of the 0.1 literal from vy after the move"),
    ("objects", "countlast", 0x55FC62, "mulss xmm0, dword ptr [rip + 0x123732]", None,
     "uta4 part case 15: vx's negative-factor damping runs after the move on the last "
     "stock-period tick"),
    ("objects", "countlast", 0x55FC78, "mulss xmm0, dword ptr [rip + 0x12371c]", None,
     "uta4 part case 15: the same for vz"),
    ("objects", "count", 0x55FC95, "mov word ptr [rsi + r14*2 + 0x130c], ax", None,
     "uta4 part case 15: +130C countdown steps once per stock tick"),
    ("objects", "notyet", 0x55FC9E, "test cx, cx", 0x55FCB3,
     "uta4 part case 15: hold the old-countdown branch on intermediate ticks"),
    ("objects", "count", 0x55FE62, "mov word ptr [rsi + r14*2 + 0x1314], ax", None,
     "uta4 part: the 60-tick post-hit +1314 countdown steps once per stock tick while "
     "nonzero"),
    # utb6 update 56F760, state byte +E36. Even states initialize and fall
    # through to their odd, repeated update state. The 2DE0A0 call returns bounded
    # +B0/+B4 angular changes; its caller-local limits are passed in stack slots.
    ("objects", "lin", 0x56F8C0, "movss xmm1, dword ptr [rip + 0x10a33c]",
     (0x679C04, 0.0872664600610733),
     "utb6 case 1: scale the first angular limit passed to 2DE0A0, which bounds +B0's "
     "continuous turn each tick"),
    ("objects", "lin", 0x56F8CC, "movss xmm0, dword ptr [rip + 0x103054]",
     (0x672928, 0.01745329238474369),
     "utb6 case 1: scale the second angular limit passed to 2DE0A0, which bounds +B4's "
     "continuous turn"),
    ("objects", "srcblend", 0x56F9DE, "mulss xmm1, dword ptr [rdi + 0xe14]", None,
     "utb6 case 1: position x approaches the computed target by dynamic +E14 each tick"),
    ("objects", "srcblend", 0x56F9FF, "mulss xmm1, dword ptr [rdi + 0xe14]", None,
     "utb6 case 1: position y uses the same +E14 approach factor"),
    ("objects", "srcblend", 0x56FA22, "mulss xmm1, dword ptr [rdi + 0xe14]", None,
     "utb6 case 1: position z uses the same +E14 approach factor"),
    ("objects", "countlast", 0x56FA3C, "addss xmm0, dword ptr [rip + 0x10d924]", None,
     "utb6 case 1: hold +E14 constant through each stock period while its converted "
     "blend runs; add the full 0.07 only on the last tick, after the approach"),
    ("objects", "lin", 0x56FA95, "movss xmm1, dword ptr [rip + 0x10a16f]",
     (0x679C0C, 0.1745329201221466),
     "utb6 case 3: scale 2DE0A0's first angular limit for its repeated +B0 turn"),
    ("objects", "lin", 0x56FAA1, "movss xmm0, dword ptr [rip + 0x10a18b]",
     (0x679C34, 0.06981316953897476),
     "utb6 case 3: scale 2DE0A0's second angular limit for its repeated +B4 turn"),
    ("objects", "lin", 0x56FCB4, "movss xmm1, dword ptr [rip + 0x109fd4]",
     (0x679C90, 0.05235987901687622),
     "utb6 case 5: scale 2DE0A0's first angular limit for its repeated +B0 turn"),
    ("objects", "lin", 0x56FCC0, "movss xmm0, dword ptr [rip + 0x109f6c]",
     (0x679C34, 0.06981316953897476),
     "utb6 case 5: scale 2DE0A0's second angular limit for its repeated +B4 turn"),
    ("objects", "srcblend", 0x56FDFD, "mulss xmm1, dword ptr [rdi + 0xe14]", None,
     "utb6 case 5: position x approaches the computed target by dynamic +E14 each tick"),
    ("objects", "srcblend", 0x56FE1E, "mulss xmm1, dword ptr [rdi + 0xe14]", None,
     "utb6 case 5: position y uses the same +E14 approach factor"),
    ("objects", "srcblend", 0x56FE41, "mulss xmm1, dword ptr [rdi + 0xe14]", None,
     "utb6 case 5: position z uses the same +E14 approach factor"),
    ("objects", "countlast", 0x56FE5B, "addss xmm0, dword ptr [rip + 0x10a08d]", None,
     "utb6 case 5: hold +E14 through the stock period and add the full 0.04 on its "
     "last tick, after the converted approach"),
    ("objects", "lin", 0x56FE7E, "movss xmm0, dword ptr [rip + 0x109dae]",
     (0x679C34, 0.06981316953897476),
     "utb6 case 7: a shared literal bounds both +B0 and +B4 changes returned by 2DE0A0 "
     "every tick"),
    ("objects", "count", 0x56FF02, "mov word ptr [rdi + 0xe3c], ax", None,
     "utb6 case 7: commit +E3C's increment once per stock tick; the following "
     "comparison reads the advanced ax, so its transition can be up to three quarters "
     "of a stock tick early at 120"),
    ("objects", "lin", 0x56FF59, "movss xmm1, dword ptr [rip + 0x112863]",
     (0x6827C4, 0.5585053563117981),
     "utb6 case 9: scale 2DE0A0's first angular limit for its repeated +B0 turn"),
    ("objects", "lin", 0x56FF65, "movss xmm0, dword ptr [rip + 0x109d13]",
     (0x679C80, 0.10471975803375244),
     "utb6 case 9: scale 2DE0A0's second angular limit for its repeated +B4 turn"),
    ("objects", "callscale", 0x56FFE6, "call 0x1802da410", (0x2DA410,"xmm1"),
     "utb6 case 9: 2DA410 moves position by stock-valued +E48 each tick; scale the "
     "caller-local distance argument, while +E48's own rise and decay retain their "
     "cadence"),
    ("objects", "lin", 0x570078, "movss xmm1, dword ptr [rip + 0x109bb4]",
     (0x679C34, 0.06981316953897476),
     "utb6 case 11: scale 2DE0A0's first angular limit for its repeated +B0 turn"),
    ("objects", "lin", 0x570084, "movss xmm0, dword ptr [rip + 0x109bf4]",
     (0x679C80, 0.10471975803375244),
     "utb6 case 11: scale 2DE0A0's second angular limit for its repeated +B4 turn"),
    ("objects", "callscale", 0x570105, "call 0x1802da410", (0x2DA410,"xmm1"),
     "utb6 case 11: 2DA410 moves position by stock-valued +E48 each tick; scale only "
     "this call's distance"),
    # cBallObj update 33BB20: +E20/+E28 are horizontal velocity and +A8 points
    # to position. The position additions run each update, while +1128 damps the
    # velocities after their move. +E42 and +E40 are already stock-gated by
    # memory_timers.h; the shake impulses still need per-tick scaling.
    ("objects", "pre", 0x33BC15, "addss xmm1, dword ptr [rdi + 0xe28]", None,
     "cBallObj: scale the per-tick x acceleration from +1130 times +FE8 before adding "
     "it to persistent +E28"),
    ("objects", "pre", 0x33BC1D, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "cBallObj: scale the per-tick z acceleration from +1130 times +FE0 before adding "
     "it to persistent +E20"),
    ("objects", "pre", 0x33BDA8, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "cBallObj shake, phase 0-9: scale the sine impulse before adding it to persistent "
     "+E20"),
    ("objects", "pre", 0x33BDC8, "addss xmm0, dword ptr [rdi + 0xe28]", None,
     "cBallObj shake, phase 0-9: scale the cosine impulse before adding it to "
     "persistent +E28"),
    ("objects", "pre", 0x33BE52, "addss xmm1, dword ptr [rdi + 0xe20]", None,
     "cBallObj shake, phase 11-19, odd cycle: scale the cosine impulse before adding "
     "it to +E20"),
    ("objects", "src", 0x33BE5A, "subss xmm0, xmm8", None,
     "cBallObj shake, phase 11-19, odd cycle: scale the sine impulse in xmm8 before "
     "subtracting it from +E28"),
    ("objects", "pre", 0x33BE79, "addss xmm8, dword ptr [rdi + 0xe28]", None,
     "cBallObj shake, phase 11-19, even cycle: scale the sine impulse before adding it "
     "to +E28"),
    ("objects", "src", 0x33BE82, "subss xmm0, xmm1", None,
     "cBallObj shake, phase 11-19, even cycle: scale the cosine impulse in xmm1 before "
     "subtracting it from +E20"),
    ("objects", "pre", 0x33BECE, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "cBallObj shake, phase 21-29: scale the sine impulse before adding it to +E20"),
    ("objects", "pre", 0x33BEE6, "addss xmm0, dword ptr [rdi + 0xe28]", None,
     "cBallObj shake, phase 21-29: scale the cosine impulse before adding it to +E28"),
    # Both movement branches use the same stock-valued horizontal velocity.
    ("objects", "src", 0x33BFF7, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "cBallObj airborne branch: move x by one high-rate share of persistent +E20"),
    ("objects", "src", 0x33C00F, "addss xmm0, dword ptr [rdi + 0xe28]", None,
     "cBallObj airborne branch: move z by one high-rate share of persistent +E28"),
    ("objects", "src", 0x33C030, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "cBallObj grounded branch: move x by one high-rate share of persistent +E20"),
    ("objects", "src", 0x33C048, "addss xmm0, dword ptr [rdi + 0xe28]", None,
     "cBallObj grounded branch: move z by one high-rate share of persistent +E28"),
    # +116C counts frames while horizontal speed stays above the sound threshold.
    # The modulo test reads the old count: suppress its sound between stock ticks
    # as well as gating the increment, so a held multiple of ten cannot retrigger.
    ("objects", "notyet", 0x33C09D, "cmp r9d, eax", 0x33C0E3,
     "cBallObj moving sound: a held +116C multiple of ten must not play again between "
     "stock ticks"),
    ("objects", "count", 0x33C0E3, "inc word ptr [rdi + 0x116c]", None,
     "cBallObj moving sound: advance +116C once per stock tick after the modulo test"),
    # The shared +1128 factor is copied to xmm3 for x and kept in xmm1 for z.
    # Both velocity lanes damp after the move, on the last tick of a stock period.
    ("objects", "ulast", 0x33C0F4, "movss xmm1, dword ptr [rdi + 0x1128]", None,
     "cBallObj: hold dynamic +1128 drag until the last tick before damping both +E20 "
     "and +E28"),
    # utb7 update 570890, state byte +E36. 2DE0A0 returns a bounded turn for
    # +B0/+B4. Each state's two caller-local limits are in stock-tick units.
    ("objects", "lin", 0x570A9B, "movss xmm1, dword ptr [rip + 0x109169]",
     (0x679C0C, 0.1745329201221466),
     "utb7 state 1: scale the first 2DE0A0 angular limit for the repeated +B0 turn"),
    ("objects", "lin", 0x570AA7, "movss xmm0, dword ptr [rip + 0x109185]",
     (0x679C34, 0.06981316953897476),
     "utb7 state 1: scale the second angular limit for +B4"),
    ("objects", "lin", 0x570C88, "movss xmm1, dword ptr [rip + 0x108f7c]",
     (0x679C0C, 0.1745329201221466),
     "utb7 state 3: scale the first angular limit for +B0"),
    ("objects", "lin", 0x570C94, "movss xmm0, dword ptr [rip + 0x108f98]",
     (0x679C34, 0.06981316953897476),
     "utb7 state 3: scale the second angular limit for +B4"),
    ("objects", "lin", 0x570EE9, "movss xmm1, dword ptr [rip + 0x108d1b]",
     (0x679C0C, 0.1745329201221466),
     "utb7 state 5: scale the first angular limit for +B0"),
    ("objects", "lin", 0x570EF5, "movss xmm0, dword ptr [rip + 0x108d37]",
     (0x679C34, 0.06981316953897476),
     "utb7 state 5: scale the second angular limit for +B4"),
    ("objects", "lin", 0x57110A, "movss xmm1, dword ptr [rip + 0x1116b2]",
     (0x6827C4, 0.5585053563117981),
     "utb7 state 7: scale the first angular limit for +B0"),
    ("objects", "lin", 0x571116, "movss xmm0, dword ptr [rip + 0x108b62]",
     (0x679C80, 0.10471975803375244),
     "utb7 state 7: scale the second angular limit for +B4"),
    ("objects", "lin", 0x571229, "movss xmm1, dword ptr [rip + 0x1016f7]",
     (0x672928, 0.01745329238474369),
     "utb7 state 9: scale the first angular limit for +B0"),
    ("objects", "lin", 0x571235, "movss xmm0, dword ptr [rip + 0x1089f7]",
     (0x679C34, 0.06981316953897476),
     "utb7 state 9: scale the second angular limit for +B4"),
    # State 3 fades two material alphas from the shared 0.05 step in xmm7.
    ("objects", "src", 0x570E18, "addss xmm0, xmm7", None,
     "utb7 state 3: material 1 alpha rises by 0.05 per stock tick, clamped to one"),
    ("objects", "src", 0x570E52, "subss xmm0, xmm7", None,
     "utb7 state 3: material 0 alpha falls by 0.05 per stock tick, clamped to zero"),
    # State 5 rises by dynamic +E18, which ramps by 0.3 after the move.
    ("objects", "src", 0x570FEC, "addss xmm0, xmm1", None,
     "utb7 state 5: add one high-rate share of the stock-valued +E18 rise to the "
     "target height"),
    ("objects", "countlast", 0x570FF0, "addss xmm1, dword ptr [rip + 0x104a38]", None,
     "utb7 state 5: advance +E18 by the full 0.3 only after the last move in a stock "
     "period"),
    # em4d/em50 and cKiType023 each use one local step for sixteen material
    # channel fades across two six-state switch tables. The only reads of xmm6
    # between these loads and their restores are those addss/subss channel steps.
    ("actor", "lin", 0x287E35, "movss xmm6, dword ptr [rip + 0x3f98bb]",
     (0x6816F8, 0.07500000298023224),
     "em4d/em50 material channels 4 and 5: scale their shared fade step in xmm6 for "
     "all sixteen +50/+54/+58 updates"),
    ("objects", "lin", 0x36A665, "movss xmm6, dword ptr [rip + 0x31708b]",
     (0x6816F8, 0.07500000298023224),
     "cKiType023 material channels 4 and 5: scale their shared fade step in xmm6 for "
     "all sixteen +50/+54/+58 updates"),
    # et08 slot update 2E2FA0: six material V offsets take a fixed signed step,
    # then wrap back into [-1,1] if necessary. Only the initial step is a rate.
    ("objects", "lin", 0x2E2FBD, "movss xmm0, dword ptr [rip + 0x4bd173]",
     (0x7A0138, -0.029999999329447746),
     "et08 material 0 V: scale the -0.03 scroll step before the wrap checks"),
    ("objects", "lin", 0x2E300D, "movss xmm0, dword ptr [rip + 0x4bd127]",
     (0x7A013C, -0.029999999329447746),
     "et08 material 1 V: scale the -0.03 scroll step"),
    ("objects", "lin", 0x2E304D, "movss xmm0, dword ptr [rip + 0x4bd0eb]",
     (0x7A0140, -0.05999999865889549),
     "et08 material 3 V: scale the -0.06 scroll step"),
    ("objects", "lin", 0x2E308D, "movss xmm0, dword ptr [rip + 0x4bd0af]",
     (0x7A0144, -0.05999999865889549),
     "et08 material 5 V: scale the -0.06 scroll step"),
    ("objects", "lin", 0x2E30CD, "movss xmm0, dword ptr [rip + 0x4bd073]",
     (0x7A0148, -0.029999999329447746),
     "et08 material 7 V: scale the -0.03 scroll step"),
    ("objects", "lin", 0x2E310D, "movss xmm0, dword ptr [rip + 0x4bd037]",
     (0x7A014C, -0.029999999329447746),
     "et08 material 8 V: scale the -0.03 scroll step"),
    # ut1d slot update 532BC0: material 0/1/2 each has U and V scroll; material
    # 2 V has a literal zero step and only normalizes an out-of-range offset.
    ("objects", "lin", 0x532C5F, "movss xmm0, dword ptr [rip + 0x28cb05]",
     (0x7BF76C, 0.00800000037997961),
     "ut1d material 0 U: scale the 0.008 scroll step before wrapping"),
    ("objects", "lin", 0x532CA2, "movss xmm0, dword ptr [rip + 0x28cad2]",
     (0x7BF77C, 0.009999999776482582),
     "ut1d material 0 V: scale the 0.01 scroll step"),
    ("objects", "lin", 0x532CE2, "movss xmm0, dword ptr [rip + 0x28ca7e]",
     (0x7BF768, 0.00800000037997961),
     "ut1d material 1 U: scale the 0.008 scroll step"),
    ("objects", "lin", 0x532D18, "movss xmm0, dword ptr [rip + 0x28ca58]",
     (0x7BF778, -0.009999999776482582),
     "ut1d material 1 V: scale the -0.01 scroll step"),
    ("objects", "lin", 0x532DB7, "movss xmm0, dword ptr [rip + 0x28c9b1]",
     (0x7BF770, 0.009999999776482582),
     "ut1d material 2 U: scale the 0.01 scroll step"),
    # ut63 update 2209E0: the two repeated states use one shared fade step each.
    # In state 3, xmm6 steps all four material channels and the +D20/+D24/+D28
    # object colour channels; in state 1, xmm2 steps the four material channels.
    ("objects", "lin", 0x220A3F, "movss xmm6, dword ptr [rip + 0x4513bd]",
     (0x671E04, 0.10000000149011612),
     "ut63 states 3 and colour fade: scale the sole xmm6 step used by material "
     "+50/+54/+58/+5C and object +D20/+D24/+D28"),
    ("objects", "lin", 0x220AED, "movss xmm2, dword ptr [rip + 0x451e37]",
     (0x67292C, 0.20000000298023224),
     "ut63 state 1: scale the sole xmm2 step used by the four material channels before "
     "their clamp to one"),
    # utb7 update 570890: state 7's +E48 rise already has a phase_steps.h row,
    # so the persistent value stays in stock units while its 2DA410 move is
    # scaled at the call. State 9 has a separate literal vertical rise.
    ("objects", "callscale", 0x571197, "call 0x1802da410", (0x2DA410,"xmm1"),
     "utb7 state 7: scale only the caller-local distance passed to 2DA410, keeping "
     "+E48 stock-valued"),
    ("objects", "lin", 0x5712C2, "addss xmm0, dword ptr [rip + 0x10093e]", (0x671C08, 1.0),
     "utb7 state 9: position y rises by one stock unit each tick until the +D2C "
     "countdown ends"),
    # Shared enemy update 241180 calls 23F8D0, which passes the sole xmm6 step
    # to ten helper calls (two each of 23F9F0, 23FB70, 23FD00, 23FE90, 240020).
    # Each helper uses argument xmm3 only for the three colour-channel additions
    # or subtractions in its state 1 and state 3 paths, then clamps the result.
    ("actor", "lin", 0x23F8E4, "movss xmm6, dword ptr [rip + 0x438e90]",
     (0x67877C, 0.02500000037252903),
     "common em00.. enemy material fade: scale the caller's shared xmm6 step passed as "
     "xmm3 to all ten RGB helper calls"),
    # Each stock 0.05 load supplies the RMW material +60 scrolls below. The
    # conditional +/-1 stores normalize a wrapped offset after that scroll.
    ("objects", "lin", 0x33A875, "movss xmm7, dword ptr [rip + 0x33cd73]",
     (0x6775F0, 0.05000000074505806),
     "cBallObj et9a wp1e: scale the shared material 1-4 U scroll step"),
    ("objects", "lin", 0x4D11A6, "movss xmm7, dword ptr [rip + 0x1a6442]",
     (0x6775F0, 0.05000000074505806),
     "et69: scale the shared material 1-4 U scroll step"),
    ("objects", "lin", 0x598B56, "movss xmm7, dword ptr [rip + 0xdea92]",
     (0x6775F0, 0.05000000074505806),
     "598B10: scale the shared material 1-4 negative U scroll step and earlier colour "
     "step"),
    # The xmm8 RIP loads at 3933D2 and 397359 have a REX prefix and cannot be
    # retargeted by the eight-byte literal handler. Scale their consumers.
    ("objects", "src", 0x3933E8, "subss xmm0, xmm8", None,
     "wp20 material 1 U: scale the shared 0.05 before subtraction"),
    ("objects", "src", 0x393412, "subss xmm0, xmm8", None,
     "wp20 material 2 U: scale the shared 0.05 before subtraction"),
    ("objects", "src", 0x39343C, "subss xmm0, xmm8", None,
     "wp20 material 3 U: scale the shared 0.05 before subtraction"),
    ("objects", "src", 0x393466, "subss xmm0, xmm8", None,
     "wp20 material 4 U: scale the shared 0.05 before subtraction"),
    ("objects", "src", 0x3973F2, "addss xmm0, xmm8", None,
     "wp35 first material 0 U: scale the shared 0.05 before addition"),
    ("objects", "src", 0x39741C, "addss xmm0, xmm8", None,
     "wp35 first material 1 U: scale the shared 0.05 before addition"),
    ("objects", "src", 0x397558, "addss xmm0, xmm8", None,
     "wp35 second material 0 U: scale the shared 0.05 before addition"),
    ("objects", "src", 0x397582, "addss xmm0, xmm8", None,
     "wp35 second material 1 U: scale the shared 0.05 before addition"),
    # an03 1DC780: two persistent approach components. For stock factor 0.1,
    # use the compounded fraction 1-(1-0.1)^s at each high-rate update.
    ("actor", "blend", 0x1DC835, "mulss xmm3, dword ptr [rip + 0x4955c7]",
     (0x671E04, 0.10000000149011612),
     "an03 +E48: approach the distance-dependent target by 0.1 per stock tick"),
    ("actor", "blend", 0x1DC855, "mulss xmm2, dword ptr [rip + 0x4955a7]",
     (0x671E04, 0.10000000149011612),
     "an03 +E4C: approach the distance-dependent target by 0.1 per stock tick"),
    # hm3c 304950: the world X/Z position approaches the freshly computed target
    # by 0.05 of the remaining gap per stock tick.
    ("actor", "blend", 0x304989, "mulss xmm1, dword ptr [rip + 0x372c5f]",
     (0x6775F0, 0.05000000074505806),
     "hm3c X: compound the 0.05 approach factor"),
    ("actor", "blend", 0x3049AB, "mulss xmm1, dword ptr [rip + 0x372c3d]",
     (0x6775F0, 0.05000000074505806),
     "hm3c Z: compound the 0.05 approach factor"),
    # cBallObj 33ABC0 loads a sole 0.1 factor into xmm6 at entry. All nine uses
    # before its restore multiply persistent +E48/+E20/+E28 by that factor in
    # three movement branches. Root the factor once for elapsed-tick damping.
    ("objects", "root", 0x33ACE5, "movss xmm6, dword ptr [rip + 0x337117]", None,
     "cBallObj: compound the shared 0.1 momentum decay for all three vector components "
     "in all three branches"),
    # et67 stores three fixed rates in .data; all RIP references to those words
    # are these reads. Its U phases wrap by whole units after a scaled increment.
    ("objects", "lin", 0x2F1AC4, "movss xmm0, dword ptr [rip + 0x4ae7a8]",
     (0x7A0274, 0.00800000037997961),
     "et67 material 3 V: scale the 0.008 scroll step"),
    ("objects", "lin", 0x2F1B3E, "movss xmm0, dword ptr [rip + 0x4ae732]",
     (0x7A0278, 0.029999999329447746),
     "et67 submodel 5 angle: scale the 0.03 rotation step"),
    ("objects", "lin", 0x2F1B63, "movss xmm0, dword ptr [rip + 0x4ae709]",
     (0x7A0274, 0.00800000037997961),
     "et67 material 4 V: scale the 0.008 scroll step"),
    # wp2a and uta6 have one 0.1 channel step on each of two switch branches;
    # each branch updates all three RGB components before its state check.
    ("objects", "lin", 0x396D48, "movss xmm2, dword ptr [rip + 0x2db0b4]",
     (0x671E04, 0.10000000149011612),
     "wp2a material 1 RGB: scale the downward 0.1 step"),
    ("objects", "lin", 0x396D90, "movss xmm2, dword ptr [rip + 0x2db06c]",
     (0x671E04, 0.10000000149011612),
     "wp2a material 1 RGB: scale the upward 0.1 step"),
    ("objects", "lin", 0x562C77, "movss xmm2, dword ptr [rip + 0x10f185]",
     (0x671E04, 0.10000000149011612),
     "uta6 material 3 RGB: scale the downward 0.1 step"),
    ("objects", "lin", 0x562CCF, "movss xmm2, dword ptr [rip + 0x10f12d]",
     (0x671E04, 0.10000000149011612),
     "uta6 material 3 RGB: scale the upward 0.1 step"),
    # Three further three-channel material fades use one scalar step in each of
    # their downward and upward branches. The load feeds each RGB add/subtract.
    ("objects", "lin", 0x39A2D8, "movss xmm2, dword ptr [rip + 0x2d7b24]",
     (0x671E04, 0.10000000149011612),
     "wp3a material 1 RGB: scale the downward 0.1 step"),
    ("objects", "lin", 0x39A320, "movss xmm2, dword ptr [rip + 0x2d7adc]",
     (0x671E04, 0.10000000149011612),
     "wp3a material 1 RGB: scale the upward 0.1 step"),
    ("objects", "lin", 0x563E07, "movss xmm2, dword ptr [rip + 0x10eb1d]",
     (0x67292C, 0.20000000298023224),
     "uta7 material 2 RGB: scale the downward 0.2 step"),
    ("objects", "lin", 0x563E52, "movss xmm2, dword ptr [rip + 0x10ead2]",
     (0x67292C, 0.20000000298023224),
     "uta7 material 2 RGB: scale the upward 0.2 step"),
    ("objects", "lin", 0x3609A1, "movss xmm2, dword ptr [rip + 0x31145b]",
     (0x671E04, 0.10000000149011612),
     "es60 material 0 RGB: scale the downward 0.1 step"),
    ("objects", "lin", 0x3609E9, "movss xmm2, dword ptr [rip + 0x311413]",
     (0x671E04, 0.10000000149011612),
     "es60 material 0 RGB: scale the upward 0.1 step"),
    # cCockCompas vtable slot 3 updates its gameplay HUD compass color. Each of
    # four angle sectors changes one of the four RGBA bytes by +15 and the other
    # three by -15. Preserve the stock 30 Hz integer color sequence.
    ("objects", "count", 0x3FAE87, "add byte ptr [rdi + 0x71], 0xf", None,
     "compass sector 1: advance color byte +71 once per stock tick"),
    ("objects", "count", 0x3FAE8B, "add byte ptr [rdi + 0x72], 0xf1", None,
     "compass sector 1: advance color byte +72 once per stock tick"),
    ("objects", "count", 0x3FAE8F, "add byte ptr [rdi + 0x73], 0xf1", None,
     "compass sector 1: advance color byte +73 once per stock tick"),
    ("objects", "count", 0x3FAE93, "add byte ptr [rdi + 0x70], 0xf1", None,
     "compass sector 1: advance color byte +70 once per stock tick"),
    ("objects", "count", 0x3FAEA1, "add byte ptr [rdi + 0x72], 0xf", None,
     "compass sector 2: advance color byte +72 once per stock tick"),
    ("objects", "count", 0x3FAEA5, "add byte ptr [rdi + 0x73], 0xf1", None,
     "compass sector 2: advance color byte +73 once per stock tick"),
    ("objects", "count", 0x3FAEA9, "add byte ptr [rdi + 0x71], 0xf1", None,
     "compass sector 2: advance color byte +71 once per stock tick"),
    ("objects", "count", 0x3FAEAD, "add byte ptr [rdi + 0x70], 0xf1", None,
     "compass sector 2: advance color byte +70 once per stock tick"),
    ("objects", "count", 0x3FAEBC, "add byte ptr [rdi + 0x73], 0xf", None,
     "compass sector 3: advance color byte +73 once per stock tick"),
    ("objects", "count", 0x3FAEC0, "add byte ptr [rdi + 0x72], 0xf1", None,
     "compass sector 3: advance color byte +72 once per stock tick"),
    ("objects", "count", 0x3FAEC4, "add byte ptr [rdi + 0x71], 0xf1", None,
     "compass sector 3: advance color byte +71 once per stock tick"),
    ("objects", "count", 0x3FAEC8, "add byte ptr [rdi + 0x70], 0xf1", None,
     "compass sector 3: advance color byte +70 once per stock tick"),
    ("objects", "count", 0x3FAED7, "add byte ptr [rdi + 0x70], 0xf", None,
     "compass sector 4: advance color byte +70 once per stock tick"),
    ("objects", "count", 0x3FAEDB, "add byte ptr [rdi + 0x73], 0xf1", None,
     "compass sector 4: advance color byte +73 once per stock tick"),
    ("objects", "count", 0x3FAEDF, "add byte ptr [rdi + 0x72], 0xf1", None,
     "compass sector 4: advance color byte +72 once per stock tick"),
    ("objects", "count", 0x3FAEE3, "add byte ptr [rdi + 0x71], 0xf1", None,
     "compass sector 4: advance color byte +71 once per stock tick"),
    # ut6f loops over six materials using one table rate per channel.
    ("objects", "pre", 0x224B03, "addss xmm0, dword ptr [rax + 0x60]", None,
     "ut6f: scale each table-driven material U scroll step before adding it"),
    # em2c holds its 0.05 in xmm8 (a nine-byte RIP load); scale only its two
    # color additions, leaving the rest of that function's xmm8 uses alone.
    ("objects", "src", 0x279B67, "addss xmm0, xmm8", None,
     "em2c material channel +54: scale the 0.05 increment"),
    ("objects", "src", 0x279B89, "addss xmm0, xmm8", None,
     "em2c material channel +58: scale the 0.05 increment"),
    # Human and object material alpha fades, one fixed 0.05 rate per direction.
    ("objects", "lin", 0x31D5BB, "addss xmm0, dword ptr [rip + 0x35a02d]",
     (0x6775F0, 0.05000000074505806),
     "hm10 material 2 alpha: scale rising 0.05"),
    ("objects", "lin", 0x31D5F3, "subss xmm0, dword ptr [rip + 0x359ff5]",
     (0x6775F0, 0.05000000074505806),
     "hm10 material 2 alpha: scale falling 0.05"),
    ("objects", "lin", 0x31E8E7, "subss xmm0, dword ptr [rip + 0x358d01]",
     (0x6775F0, 0.05000000074505806),
     "hm19 material 1 alpha: scale falling 0.05"),
    ("objects", "lin", 0x31E8F9, "addss xmm0, dword ptr [rip + 0x358cef]",
     (0x6775F0, 0.05000000074505806),
     "hm19 material 2 alpha: scale rising 0.05"),
    ("objects", "lin", 0x331D5B, "addss xmm0, dword ptr [rip + 0x34588d]",
     (0x6775F0, 0.05000000074505806),
     "hm6e material 2 alpha: scale rising 0.05"),
    ("objects", "lin", 0x331D93, "subss xmm0, dword ptr [rip + 0x345855]",
     (0x6775F0, 0.05000000074505806),
     "hm6e material 2 alpha: scale falling 0.05"),
    ("objects", "lin", 0x331F3B, "addss xmm0, dword ptr [rip + 0x3456ad]",
     (0x6775F0, 0.05000000074505806),
     "hm6f material 2 alpha: scale rising 0.05"),
    ("objects", "lin", 0x331F73, "subss xmm0, dword ptr [rip + 0x345675]",
     (0x6775F0, 0.05000000074505806),
     "hm6f material 2 alpha: scale falling 0.05"),
    # The two enemy/object material U phases wrap by whole units after these rates.
    ("objects", "lin", 0x2E84EC, "movss xmm1, dword ptr [rip + 0x4b7cd8]",
     (0x7A01CC, -0.009999999776482582),
     "et24 material 0 U: scale the -0.01 scroll step"),
    ("objects", "lin", 0x515A7F, "movss xmm1, dword ptr [rip + 0x2a2cfd]",
     (0x7B8784, -0.009999999776482582),
     "es13 material 1 U: scale the -0.01 scroll step"),
    ("objects", "lin", 0x5A977F, "addss xmm0, dword ptr [rip + 0xd9011]",
     (0x682798, 0.0020000000949949026),
     "utf0 material 1 U state A: scale the 0.002 scroll step"),
    ("objects", "lin", 0x5A9789, "addss xmm0, dword ptr [rip + 0xc92af]",
     (0x672A40, 0.009999999776482582),
     "utf0 material 1 U state B: scale the 0.01 scroll step"),
    # cEnemyObj's damage/state callbacks approach their material 4 RGB channels.
    # Each local blend factor is used by all three channel gap multiplications.
    ("objects", "blend", 0x341CFF, "movss xmm4, dword ptr [rip + 0x333d29]",
     (0x675A30, 0.30000001192092896),
     "cEnemyObj 341BE0 state 4: compound the 0.3 material RGB approach"),
    ("objects", "blend", 0x341EA4, "movss xmm2, dword ptr [rip + 0x337dc8]",
     (0x679C74, 0.4000000059604645),
     "cEnemyObj 341BE0 state 0: compound the 0.4 material RGB approach"),
    ("objects", "blend", 0x342909, "movss xmm2, dword ptr [rip + 0x33311f]",
     (0x675A30, 0.30000001192092896),
     "cEnemyObj 3426A0 state 3: compound the 0.3 material RGB approach"),
    ("objects", "blend", 0x3429DF, "movss xmm2, dword ptr [rip + 0x333049]",
     (0x675A30, 0.30000001192092896),
     "cEnemyObj 3426A0 state 0: compound the 0.3 material RGB approach"),
    ("objects", "blend", 0x342CDE, "movss xmm2, dword ptr [rip + 0x332d4a]",
     (0x675A30, 0.30000001192092896),
     "cEnemyObj 342AC0: compound the 0.3 material RGB approach"),
    # Shared scalar rates in material scroll and alpha fade loops.
    ("objects", "lin", 0x2F3F56, "movss xmm6, dword ptr [rip + 0x384932]",
     (0x678890, 0.029999999329447746),
     "et6f: scale the 0.03 U step shared by its three materials"),
    ("objects", "lin", 0x5A5B9B, "movss xmm7, dword ptr [rip + 0xcc261]",
     (0x671E04, 0.10000000149011612),
     "utce: scale the 0.1 alpha step shared by four materials"),
    ("objects", "lin", 0x32CA91, "movss xmm6, dword ptr [rip + 0x34ab57]",
     (0x6775F0, 0.05000000074505806),
     "hm5d: scale the 0.05 alpha step in both branches"),
    ("objects", "lin", 0x32D132, "movss xmm6, dword ptr [rip + 0x34a4b6]",
     (0x6775F0, 0.05000000074505806),
     "hm5e: scale the 0.05 alpha step in both branches"),
    # A target alpha is approached by 0.2 on either of two paths.
    ("objects", "blend", 0x57BC2D, "mulss xmm1, dword ptr [rip + 0xf6cf7]",
     (0x67292C, 0.20000000298023224),
     "ut2c: compound the first material alpha approach"),
    ("objects", "blend", 0x57BC46, "mulss xmm6, dword ptr [rip + 0xf6cde]",
     (0x67292C, 0.20000000298023224),
     "ut2c: compound the second material alpha approach"),
    # Callers of the em6a/es18 U/V wrap helpers make their dynamic step from
    # a random scalar and this 0.03 literal, which is shared by U and V.
    ("objects", "lin", 0x2D4A56, "mulss xmm0, dword ptr [rip + 0x3a3e32]",
     (0x678890, 0.029999999329447746),
     "em6a: scale the random U/V scroll step before the helper call"),
    ("objects", "lin", 0x35E637, "mulss xmm6, dword ptr [rip + 0x31a251]",
     (0x678890, 0.029999999329447746),
     "es18: scale the random U/V scroll step before both helper calls"),
    # ut52 places its current material scroll step in +1078 each tick. Scale it
    # on both the plus and minus paths, leaving the material value itself intact.
    ("objects", "pre", 0x21DF5F, "addss xmm0, dword ptr [rax + 0x60]", None,
     "ut52 material 1 U: scale the +1078 step before addition"),
    ("objects", "src", 0x21DF91, "subss xmm0, dword ptr [rbx + 0x1078]", None,
     "ut52 material 0 U: scale the +1078 step before subtraction"),
    # cSubScrFilesEnemy applies a joystick-driven signed step to the file
    # carousel's slot phases. The derived /100 step drives the U/V phases.
    ("menu", "lin", 0x41C2EE, "mulss xmm6, dword ptr [rip + 0x2590da]", (0x6753D0, 0.03125),
     "cSubScrFilesEnemy: scale the signed file carousel step from input"),
    # anff loads one 0.04 change for all three alternating face/color lanes.
    ("actor", "lin", 0x205098, "movss xmm0, dword ptr [rip + 0x474e50]",
     (0x679EF0, 0.03999999910593033),
     "anff: scale the 0.04 rise/fall step shared by three channels"),
    # hm27's +1315 byte clock governs how long each flying target phase lasts.
    ("actor", "count", 0x322567, "add byte ptr [rdi + 0x1315], 0xff", None,
     "hm27 phase 1: step the +1315 countdown once per stock tick"),
    ("actor", "count", 0x32276A, "add byte ptr [rdi + 0x1315], 0xff", None,
     "hm27 phase 3: step the +1315 countdown once per stock tick"),
    # hm27's three stored byte velocities are divided by 100 and added to the
    # submodel position. Scale those displacement terms before the addition.
    ("actor", "pre", 0x322714, "addss xmm0, dword ptr [r15]", None,
     "hm27 submodel X: scale the byte-derived displacement"),
    ("actor", "pre", 0x322731, "addss xmm0, dword ptr [rsi + 0x84]", None,
     "hm27 submodel Y: scale the byte-derived displacement"),
    ("actor", "pre", 0x322754, "addss xmm0, dword ptr [rsi + 0x88]", None,
     "hm27 submodel Z: scale the byte-derived displacement"),
    # hmd1 is the sibling of hm27's flying-target state machine.
    ("actor", "count", 0x33793A, "add byte ptr [rdi + 0x1315], 0xff", None,
     "hmd1 phase 1: step the +1315 countdown once per stock tick"),
    ("actor", "count", 0x337B31, "add byte ptr [rdi + 0x1315], 0xff", None,
     "hmd1 phase 3: step the +1315 countdown once per stock tick"),
    ("actor", "pre", 0x337ADD, "addss xmm0, dword ptr [r15]", None,
     "hmd1 submodel X: scale the byte-derived displacement"),
    ("actor", "pre", 0x337AF9, "addss xmm0, dword ptr [rsi + 0x84]", None,
     "hmd1 submodel Y: scale the byte-derived displacement"),
    ("actor", "pre", 0x337B1B, "addss xmm0, dword ptr [rsi + 0x88]", None,
     "hmd1 submodel Z: scale the byte-derived displacement"),
    ("actor", "lin", 0x337B69, "addss xmm0, dword ptr [rip + 0x34210f]",
     (0x679C80, 0.10471975803375244),
     "hmd1 submodel 18: scale the 0.1047198 wrapped angle step"),
    # es17 chooses one of three +1078 opacity changes, and rotates +107C.
    ("actor", "lin", 0x35E2EC, "addss xmm0, dword ptr [rip + 0x34551c]",
     (0x6A3810, 4.396551609039307),
     "es17 state 2: scale the fixed 4.396552 opacity step"),
    ("actor", "lin", 0x35E311, "mulss xmm0, dword ptr [rip + 0x31b69b]", (0x6799B4, 4.0),
     "es17 state 1: scale the sinusoid-derived opacity fall"),
    ("actor", "lin", 0x35E359, "mulss xmm0, dword ptr [rip + 0x316bff]", (0x674F60, 8.0),
     "es17 state 0: scale the sinusoid-derived opacity rise"),
    ("actor", "lin", 0x35E39A, "addss xmm0, dword ptr [rip + 0x313a66]", (0x671E08, 0.5),
     "es17: scale the 0.5 wrapped angle step"),
    # esp04 samples a random displacement for each axis on its slot 14 tick.
    # The pre hooks scale each sample after its speed multiplication.
    ("actor", "pre", 0x19E26F, "addss xmm0, dword ptr [rsi + 0x2c4]", None,
     "esp04 X: scale the random displacement before adding it"),
    ("actor", "pre", 0x19E294, "addss xmm0, dword ptr [rsi + 0x2d4]", None,
     "esp04 yaw: scale the random rotation before wrapping"),
    ("actor", "pre", 0x19E2E0, "addss xmm0, dword ptr [rsi + 0x2d0]", None,
     "esp04 Z: scale the random displacement before adding it"),
    # The item sub-screen's two branches brighten RGB/alpha bytes by 16 on
    # each menu tick until the alpha reaches 128.
    ("menu", "count", 0x40E07E, "add byte ptr [rax + 0x38], 0x10", None,
     "cSubScrItem state 2 sprite 12 red: step once per stock menu tick"),
    ("menu", "count", 0x40E090, "add byte ptr [rax + 0x39], 0x10", None,
     "cSubScrItem state 2 sprite 12 green: step once per stock menu tick"),
    ("menu", "count", 0x40E0A2, "add byte ptr [rax + 0x3a], 0x10", None,
     "cSubScrItem state 2 sprite 12 blue: step once per stock menu tick"),
    ("menu", "count", 0x40E0C9, "add byte ptr [rax + 0x38], 0x10", None,
     "cSubScrItem state 1 sprite 11 red: step once per stock menu tick"),
    ("menu", "count", 0x40E0DB, "add byte ptr [rax + 0x39], 0x10", None,
     "cSubScrItem state 1 sprite 11 green: step once per stock menu tick"),
    ("menu", "count", 0x40E0ED, "add byte ptr [rax + 0x3a], 0x10", None,
     "cSubScrItem state 1 sprite 11 blue: step once per stock menu tick"),
    ("menu", "count", 0x40E0FB, "add byte ptr [rax + 0x3b], 0x10", None,
     "cSubScrItem state 1 sprite 11 alpha: step once per stock menu tick"),
    # These compiler-generated double additions take the float material U phase,
    # add a double constant, then narrow once before the unit-wrap comparison.
    ("objects", "src", 0x50E980, "addsd xmm0, qword ptr [rip + 0x1a7a18]", None,
     "cDigObj material 0 U: scale the 0.005 double step"),
    ("objects", "src", 0x5486EB, "addsd xmm0, qword ptr [rip + 0x16f9b5]", None,
     "et8d material 4 U: scale the 0.0025 double step"),
    # ut23's three state branches accumulate a moving submodel angle from a
    # per-tick +115C/+1160 rate and a +1168/+116C local angular phase.
    ("objects", "pre", 0x4F12EF, "addss xmm0, dword ptr [rbx + 0x116c]", None,
     "ut23 state 5: scale +1160 before advancing +116C"),
    ("objects", "pre", 0x4F1324, "addss xmm0, dword ptr [rax + 0xb8]", None,
     "ut23 state 5: scale +116C before rotating submodel 0"),
    ("objects", "pre", 0x4F1342, "addss xmm0, dword ptr [rbx + 0x1168]", None,
     "ut23 state 3: scale +115C before advancing +1168"),
    ("objects", "pre", 0x4F137A, "addss xmm0, dword ptr [rax + 0xb0]", None,
     "ut23 state 3: scale +1168 before rotating submodel 1"),
    ("objects", "lin", 0x4F13C4, "subss xmm0, dword ptr [rip + 0x181674]",
     (0x672A40, 0.009999999776482582),
     "ut23 state 1: scale the 0.01 decrease of +1168"),
    ("objects", "src", 0x4F13F8, "addss xmm0, dword ptr [rbx + 0x1168]", None,
     "ut23 state 1: scale +1168 before rotating submodel 1"),
    ("objects", "src", 0x4F1415, "subss xmm0, dword ptr [rbx + 0x1160]", None,
     "ut23 state 1: scale +1160 before decreasing +116C"),
    ("objects", "src", 0x4F1446, "addss xmm0, dword ptr [rbx + 0x116c]", None,
     "ut23 state 1: scale +116C before rotating submodel 0"),
    # et73 damps its three velocity lanes by 0.98 and applies gravity -0.8
    # before moving. The temporary height subtraction around 45FC40 cancels.
    ("objects", "lin", 0x2F61D1, "subss xmm0, dword ptr [rip + 0x383aa3]",
     (0x679C7C, 0.800000011920929),
     "et73: scale the 0.8 gravity step"),
    ("objects", "root", 0x2F61E8, "movss xmm1, dword ptr [rip + 0x383770]", None,
     "et73: root the shared 0.98 velocity retention factor"),
    ("objects", "pre", 0x2F6221, "addss xmm2, dword ptr [rax]", None,
     "et73 X: scale the updated velocity before moving"),
    ("objects", "src", 0x2F6235, "addss xmm0, dword ptr [rcx + 0xe54]", None,
     "et73 Y: scale the updated velocity before moving"),
    ("objects", "src", 0x2F624E, "addss xmm0, dword ptr [rcx + 0xe18]", None,
     "et73 Z: scale the updated velocity before moving"),
    # hm28's +E3C word is a 300-tick state wait. Its local AX value is decremented
    # and written back while nonzero; keep that write on stock ticks.
    ("actor", "count", 0x323A0E, "mov word ptr [rbx + 0xe3c], ax", None,
     "hm28: decrement the +E3C state wait once per stock tick"),
    # es11 adds a random 0.02 component and a mutable 0.05 base step to its
    # +1084 material phase before wrapping by one unit.
    ("actor", "lin", 0x2C074F, "mulss xmm0, dword ptr [rip + 0x3b94d9]",
     (0x679C30, 0.019999999552965164),
     "es11: scale the random 0.02 phase-step component"),
    ("actor", "srcx", 0x2C075F, "addss xmm0, dword ptr [rip + 0x4df85d]", None,
     "es11: scale the 0.05 base phase step"),
    # esf2's +1124 value waits eight actor ticks between paired effect calls.
    ("actor", "count", 0x5BB382, "mov byte ptr [rcx + 0x1124], al", None,
     "esf2: decrement the eight-tick effect cooldown at stock pace"),
    # cCockInkGauge's visual-state update is called from the gameplay HUD tick.
    # Its color-byte state machine and nine-tick counter, each store on stock
    # ticks. (A gatefn on 3FE5D0 also ran the layout update 1B54E0 it calls
    # once a stock tick, whose tracks mode_multipliers.h already makes x N:
    # 4x long.)
    ("objects", "count", 0x3FE9BC, "mov byte ptr [r14 + 0x8e], cl", None,
     "cCockInkGauge 3FE5D0, colour cycle state 0 (+90): +8E += 15 a tick up to 0x60"),
    ("objects", "count", 0x3FE9EC, "mov byte ptr [r14 + 0x8d], al", None,
     "cCockInkGauge colour cycle state 1: +8D -= 15 a tick down to 0"),
    ("objects", "count", 0x3FEA21, "mov byte ptr [r14 + 0x8f], cl", None,
     "cCockInkGauge colour cycle state 2: +8F += 15 a tick up to 0x60"),
    ("objects", "count", 0x3FEA4E, "mov byte ptr [r14 + 0x8e], al", None,
     "cCockInkGauge colour cycle state 3: +8E -= 15 a tick down to 0"),
    ("objects", "count", 0x3FEA7D, "mov byte ptr [r14 + 0x8d], cl", None,
     "cCockInkGauge colour cycle state 4: +8D += 15 a tick up to 0x60"),
    ("objects", "count", 0x3FEAA7, "mov byte ptr [r14 + 0x8f], al", None,
     "cCockInkGauge colour cycle state 5: +8F -= 15 a tick down to 0"),
    ("objects", "count", 0x3FE9D2, "mov byte ptr [r14 + 0x90], dl", None,
     "cCockInkGauge: state 0's end advances +90 on a stock tick (the byte's last step, "
     "to 0x60, may land up to N - 1 ticks early; the next state starts on time)"),
    ("objects", "count", 0x3FEA02, "mov byte ptr [r14 + 0x90], dl", None,
     "cCockInkGauge: state 1's end, the same"),
    ("objects", "count", 0x3FEA37, "mov byte ptr [r14 + 0x90], dl", None,
     "cCockInkGauge: state 2's end, the same"),
    ("objects", "count", 0x3FEA61, "mov byte ptr [r14 + 0x90], dl", None,
     "cCockInkGauge: state 3's end, the same"),
    ("objects", "count", 0x3FEA90, "mov byte ptr [r14 + 0x90], dl", None,
     "cCockInkGauge: state 4's end, the same"),
    ("objects", "count", 0x3FEAB0, "mov word ptr [r14 + 0x8f], 0", None,
     "cCockInkGauge: state 5's end clears +8F and the state +90 together, on a stock "
     "tick"),
    ("objects", "count", 0x3FEC77, "inc dword ptr [r14 + 0x80]", None,
     "cCockInkGauge: the sparkle clock +80, 0..9 and wrapped, a tick each"),
    ("objects", "notyet", 0x3FEC93, "test eax, eax", 0x3FEDEA,
     "cCockInkGauge: the sparkle at +80 = 0: between stock ticks, not yet (the clock "
     "holds 0 for the stock tick's other ticks)"),
    # hm0f's +14E0 is a 240-tick periodic clock, checked immediately after its
    # increment and reset at the boundary.
    ("actor", "count", 0x31D436, "inc word ptr [rcx + 0x14e0]", None,
     "hm0f: advance the 240-tick +14E0 clock on stock ticks"),
    # esfd has two forms of its state handler, each nudging +14F0 toward the
    # selected alpha target by 0.05 in either direction.
    ("actor", "lin", 0x362EF7, "addss xmm0, dword ptr [rip + 0x3146f1]",
     (0x6775F0, 0.05000000074505806),
     "esfd first handler: scale the +0.05 alpha approach"),
    ("actor", "lin", 0x362F09, "subss xmm0, dword ptr [rip + 0x3146df]",
     (0x6775F0, 0.05000000074505806),
     "esfd first handler: scale the -0.05 alpha approach"),
    ("actor", "lin", 0x363055, "addss xmm0, dword ptr [rip + 0x314593]",
     (0x6775F0, 0.05000000074505806),
     "esfd second handler: scale the +0.05 alpha approach"),
    ("actor", "lin", 0x363067, "subss xmm0, dword ptr [rip + 0x314581]",
     (0x6775F0, 0.05000000074505806),
     "esfd second handler: scale the -0.05 alpha approach"),
    # es13 mirrors es11's random plus mutable-base material phase scroll.
    ("actor", "lin", 0x5159FF, "mulss xmm0, dword ptr [rip + 0x164229]",
     (0x679C30, 0.019999999552965164),
     "es13: scale the random 0.02 phase-step component"),
    ("actor", "srcx", 0x515A0F, "addss xmm0, dword ptr [rip + 0x2a2d61]", None,
     "es13: scale the mutable 0.05 base phase step"),
    # es49 approaches two angles using the same 0.05 blend factor, then steps
    # its +10E8 lifetime countdown while nonzero.
    ("actor", "blendr", 0x4A9EE8, "movaps xmm2, xmm6", None,
     "es49 first FixTurnRate approach: compound the 0.05 factor"),
    ("actor", "blendr", 0x4A9EF8, "movaps xmm2, xmm6", None,
     "es49 second FixTurnRate approach: compound the 0.05 factor"),
    ("actor", "count", 0x4A9F31, "mov word ptr [rbx + 0x10e8], ax", None,
     "es49: decrement the +10E8 lifetime countdown at stock pace"),
    # esp14 slot 1 updates age and position each tick.
    ("actor", "count", 0x1A3502, "inc word ptr [rcx + 0x2d8]", None,
     "esp14: advance the +2D8 age on stock ticks"),
    ("actor", "pre", 0x1A356E, "addss xmm0, dword ptr [rbx + 0x164]", None,
     "esp14: scale the +174 displacement before adding to +164"),
    # esp27 slot 1 transforms two velocity components into three position steps.
    # Each product uses a transient stack matrix term; scaling the term scales
    # this product without changing the matrix used by the other products.
    ("actor", "dst", 0x1A912E, "mulss xmm2, dword ptr [rsp + 0x30]", None,
     "esp27 X: scale the +2D4 velocity product"),
    ("actor", "dst", 0x1A913F, "mulss xmm0, dword ptr [rsp + 0x34]", None,
     "esp27 X: scale the +2D8 velocity product"),
    ("actor", "dst", 0x1A9159, "mulss xmm0, dword ptr [rsp + 0x30]", None,
     "esp27 Y: scale the +2D8 velocity product"),
    ("actor", "dst", 0x1A915F, "mulss xmm4, dword ptr [rsp + 0x38]", None,
     "esp27 Z: scale the +2D8 velocity product"),
    ("actor", "dst", 0x1A9170, "mulss xmm2, dword ptr [rsp + 0x34]", None,
     "esp27 Y: scale the +2D4 velocity product"),
    ("actor", "dst", 0x1A9176, "mulss xmm5, dword ptr [rsp + 0x38]", None,
     "esp27 Z: scale the +2D4 velocity product"),
    # es7e vtable slot 8 advances the same +1074 stage counter in five branches.
    ("actor", "count", 0x5F5E73, "inc dword ptr [rbx + 0x1074]", None,
     "es7e: advance stage 3 counter on stock ticks"),
    ("actor", "count", 0x5F5F87, "inc dword ptr [rbx + 0x1074]", None,
     "es7e: advance stage 6 counter on stock ticks"),
    ("actor", "count", 0x5F6052, "inc dword ptr [rbx + 0x1074]", None,
     "es7e: advance stage 9 counter on stock ticks"),
    ("actor", "count", 0x5F6241, "inc dword ptr [rbx + 0x1074]", None,
     "es7e: advance stage 13 counter on stock ticks"),
    ("actor", "count", 0x5F6353, "inc dword ptr [rbx + 0x1074]", None,
     "es7e: advance stage 16 counter on stock ticks"),
    # esp17 slot 1 multiplies the three position axes by two damping factors.
    # +2C8 controls Y; +2CC controls X and Z through the subsequent xmm1 copy.
    ("actor", "root", 0x1A3DBC, "movss xmm0, dword ptr [rbx + 0x2c8]", None,
     "esp17: take the per-tick root of the Y damping factor"),
    ("actor", "root", 0x1A3DCC, "movss xmm1, dword ptr [rbx + 0x2cc]", None,
     "esp17: take the per-tick root of the X/Z damping factor"),
    ("actor", "count", 0x1A3E3F, "inc dword ptr [rbx + 0x2d8]", None,
     "esp17: advance the +2D8 age on stock ticks"),
    # ese0 called from 3613B0: two exclusive +E35 opacity ramp branches and
    # the shared +E36 trigger clock advance once per stock tick.
    ("actor", "count", 0x361AD4, "inc byte ptr [rbx + 0xe35]", None,
     "ese0: advance the +E35 opacity ramp on stock ticks"),
    ("actor", "count", 0x361B29, "inc byte ptr [rbx + 0xe35]", None,
     "ese0: advance the alternate +E35 opacity ramp on stock ticks"),
    ("actor", "count", 0x361B86, "inc byte ptr [rbx + 0xe36]", None,
     "ese0: advance the +E36 trigger clock on stock ticks"),
    # cCockGetItemInfo slot 3 integrates the item position and velocity. The
    # constant 1.5 is the acceleration used by every item in this loop.
    ("menu", "count", 0x3FD3F3, "sub dword ptr [rdi + 8], 1", None,
     "cCockGetItemInfo: decrement item timer on stock ticks"),
    ("menu", "lin", 0x3FD3DC, "movss xmm6, dword ptr [rip + 0x278660]", (0x675A44, 1.5),
     "cCockGetItemInfo: scale the per-tick 1.5 velocity increment"),
    ("menu", "pre", 0x3FD405, "addss xmm0, dword ptr [rdi]", None,
     "cCockGetItemInfo: scale updated velocity before position addition"),
    # hm18/hm32 render callbacks repeatedly blend the submodel pose with the
    # actor's +14F8/+1458 weight. Those weights already have scaled 0.2 updates;
    # the pose blend itself must run once per stock tick to avoid compounding.
    ("actor", "gatefn", 0x31E070, "mov qword ptr [rsp + 8], rbx", None,
     "hm18: blend its submodel pose once per stock tick"),
    ("actor", "gatefn", 0x3259C0, "mov qword ptr [rsp + 8], rbx", None,
     "hm32: blend its submodel pose once per stock tick"),
    # The shared effect manager ages live entries, and esp18's slot 1 advances
    # two wrapped phases using mutable steps. Its third phase is already patched.
    ("effect", "count", 0x19C3C5, "inc word ptr [rdx + 0x22]", None,
     "shared effect manager: advance +22 age on stock ticks"),
    ("effect", "src", 0x1A442A, "addss xmm6, xmm8", None,
     "esp18: scale the +2D8 phase step before wrapping +2D0"),
    ("effect", "src", 0x1A4470, "addss xmm6, xmm8", None,
     "esp18: scale the +2DC phase step before wrapping +2D4"),
    # es39's byte fade advances on stock ticks; the color is derived from it.
    ("actor", "count", 0x35FBF9, "mov byte ptr [rcx + 0x10e7], al", None,
     "es39: update its 15-step color fade on stock ticks"),
    # ese0's separate handlers advance +E35 per tick. One handler contains no
    # earlier patch and can be gated as a whole.
    ("actor", "count", 0x3616FB, "inc byte ptr [rbx + 0xe35]", None,
     "ese0: advance its first +E35 phase on stock ticks"),
    ("actor", "gatefn", 0x361780, "push rdi", None,
     "ese0: advance its second +E35 phase on stock ticks"),
    ("actor", "count", 0x361DA7, "inc byte ptr [rbx + 0xe35]", None,
     "ese0: advance its final +E35 phase on stock ticks"),
    # esfd approaches a state-selected alpha target by 0.05 in both directions.
    ("actor", "lin", 0x3636C6, "addss xmm0, dword ptr [rip + 0x313f22]",
     (0x6775F0, 0.05000000074505806),
     "esfd: scale the +0.05 alpha approach"),
    ("actor", "lin", 0x3636D8, "subss xmm0, dword ptr [rip + 0x313f10]",
     (0x6775F0, 0.05000000074505806),
     "esfd: scale the -0.05 alpha approach"),
    # hm19's two vertical state branches add a per-tick vertical displacement.
    ("actor", "pre", 0x31EE9F, "addss xmm0, dword ptr [rax + 4]", None,
     "hm19 state 2: scale +1314 times +EC4 before Y addition"),
    ("actor", "pre", 0x31EF01, "addss xmm6, dword ptr [rax + 4]", None,
     "hm19 state 1: scale the table-derived +EC4 Y step"),
    # hm27 and hmbd move a position toward a target over a remaining-tick count.
    # Their +E3C countdown is already paced; compound the runtime blend factors.
    ("actor", "blendr", 0x323380, "divss xmm6, xmm1", None,
     "hm27: compound the 1/(remaining+1) target blend"),
    ("actor", "blendr", 0x3356AF, "divss xmm6, xmm0", None,
     "hmbd: compound the 1/(remaining+1) target blend"),
    # hm48 moves by a computed XYZ displacement and turns by a 0.2 approach.
    ("actor", "pre", 0x32AC32, "addss xmm2, dword ptr [rax]", None,
     "hm48: scale the X displacement before position addition"),
    ("actor", "pre", 0x32AC46, "addss xmm0, dword ptr [rax + 4]", None,
     "hm48: scale the Y displacement before position addition"),
    ("actor", "pre", 0x32AC5C, "addss xmm0, dword ptr [rax + 8]", None,
     "hm48: scale the Z displacement before position addition"),
    ("actor", "blend", 0x32AD23, "movss xmm2, dword ptr [rip + 0x347c01]",
     (0x67292C, 0.20000000298023224),
     "hm48: compound the 0.2 turn approach"),
    # hmce approaches an X/Z target by 0.05 and a yaw target by 0.1.
    ("actor", "blend", 0x33718A, "mulss xmm1, dword ptr [rip + 0x34045e]",
     (0x6775F0, 0.05000000074505806),
     "hmce: compound the X 0.05 target blend"),
    ("actor", "blend", 0x3371AC, "mulss xmm1, dword ptr [rip + 0x34043c]",
     (0x6775F0, 0.05000000074505806),
     "hmce: compound the Z 0.05 target blend"),
    ("actor", "blend", 0x33717E, "movss xmm2, dword ptr [rip + 0x33ac7e]",
     (0x671E04, 0.10000000149011612),
     "hmce: compound the 0.1 FixTurnRate blend"),
    # hm68 repeatedly turns by 0.9599311 then wraps.
    ("actor", "lin", 0x32FE6A, "addss xmm0, dword ptr [rip + 0x3578be]",
     (0x687730, 0.9599310755729675),
     "hm68: scale the wrapped yaw step"),
    # Tick counters and animation phase clocks.
    ("actor", "count", 0x322B39, "inc byte ptr [rdi + 0x1316]", None,
     "hm27: alternate its submodel pose once per stock tick"),
    ("actor", "count", 0x32501E, "inc dword ptr [rbx + 0x1810]", None,
     "hm30: advance +1810 on stock ticks"),
    ("actor", "count", 0x3255A7, "inc dword ptr [rbx + 0x1770]", None,
     "hm31: advance +1770 on stock ticks"),
    ("actor", "count", 0x3263A6, "add byte ptr [rbx + 0x1311], 0xff", None,
     "hm36: decrement the +1311 countdown on stock ticks"),
    ("actor", "count", 0x326B3E, "inc dword ptr [rbx + 0x1810]", None,
     "hm3a: advance +1810 on stock ticks"),
    ("actor", "count", 0x327136, "inc dword ptr [rbx + 0x1814]", None,
     "hm3b: advance +1814 on stock ticks"),
    ("actor", "count", 0x327186, "inc byte ptr [rcx + 0x1818]", None,
     "hm3b: advance the 60-step +1818 wave on stock ticks"),
    ("actor", "count", 0x32B2DB, "dec byte ptr [rbx + 0x13b2]", None,
     "hm48: decrement the +13B2 wait on stock ticks"),
    ("actor", "count", 0x32BDF3, "inc word ptr [rdi + 0x16d0]", None,
     "hm52: advance the 240-step +16D0 phase on stock ticks"),
    ("actor", "count", 0x32D91A, "inc word ptr [rcx + 0x1310]", None,
     "hm62: advance the wrapped 240-step +1310 phase on stock ticks"),
    ("actor", "count", 0x337EE1, "inc byte ptr [rdi + 0x1316]", None,
     "hmd1: alternate its submodel pose once per stock tick"),
    # The cSSScroll helper is called from its per-frame state update. It only
    # advances the scroll state, velocity/position and pause timer.
    ("objects", "gatefn", 0x414080, "push rbx", None,
     "cSSScroll: pace the full scroll state update on stock UI ticks"),
    # cSubScrFude moves each queued brush sprite for ten ticks at a fixed 8.5
    # pixels per stock tick, decrementing its queue timer in the same branch.
    ("objects", "count", 0x4234D4, "dec byte ptr [rbx + 0x100]", None,
     "cSubScrFude: pace the first queued sprite countdown"),
    ("objects", "lin", 0x4234CC, "subss xmm0, dword ptr [rip + 0x25f320]", (0x6827F4, 8.5),
     "cSubScrFude: scale the first sprite's -8.5 vertical step"),
    ("objects", "count", 0x423554, "dec byte ptr [rbx + 0x100]", None,
     "cSubScrFude: pace the second queued sprite countdown"),
    ("objects", "lin", 0x42354C, "addss xmm0, dword ptr [rip + 0x25f2a0]", (0x6827F4, 8.5),
     "cSubScrFude: scale the second sprite's +8.5 vertical step"),
    # cCockLifeGauge's active pulse clock reaches 60 either one or two ticks at
    # a time, depending on the HUD branch.
    ("objects", "count", 0x3FF7C7, "inc byte ptr [rbx + 0x8d]", None,
     "cCockLifeGauge: pace the one-step life pulse clock"),
    ("objects", "count", 0x3FF869, "add byte ptr [rbx + 0x8d], 2", None,
     "cCockLifeGauge: pace the two-step life pulse clock"),
    # cSubScrStatus has four resource meter helpers, each called only from its
    # own per-frame branch. The helper adds the requested resource transfer and
    # returns a boolean before the caller subtracts the same amount from +284.
    # Gate each call as one unit so both sides of the transfer keep stock cadence.
    ("objects", "callgate", 0x434FCC, "call 0x180433250", (0x433250, None),
     "cSubScrStatus: pace resource meter 0 transfer helper"),
    ("objects", "callgate", 0x43516F, "call 0x1804331d0", (0x4331D0, None),
     "cSubScrStatus: pace resource meter 1 transfer helper"),
    ("objects", "callgate", 0x435311, "call 0x1804332e0", (0x4332E0, None),
     "cSubScrStatus: pace resource meter 2 transfer helper"),
    ("objects", "callgate", 0x4354B5, "call 0x180433360", (0x433360, None),
     "cSubScrStatus: pace resource meter 3 transfer helper"),
    # The four waiting sound flags can wrap after 256 increments. Their related
    # transfer progress clock +2A4 also counts per update tick.
    ("objects", "count", 0x434F19, "inc word ptr [rbx + 0x2a4]", None,
     "cSubScrStatus: pace the resource transfer progress counter"),
    ("objects", "count", 0x43500D, "mov byte ptr [rbx + 0x2b4], al", None,
     "cSubScrStatus: pace meter 0 wait flag"),
    ("objects", "count", 0x4351B0, "mov byte ptr [rbx + 0x2b5], al", None,
     "cSubScrStatus: pace meter 1 wait flag"),
    ("objects", "count", 0x435352, "mov byte ptr [rbx + 0x2b6], al", None,
     "cSubScrStatus: pace meter 2 wait flag"),
    ("objects", "count", 0x4354F6, "mov byte ptr [rbx + 0x2b7], al", None,
     "cSubScrStatus: pace meter 3 wait flag"),
    # hm52's sine-height hover phase counts 0..59 and wraps to zero. The wrap
    # follows its one-byte increment on the same path.
    ("actor", "count", 0x32C05D, "inc byte ptr [rbx + 0x16d2]", None,
     "hm52: advance its 60-step hover phase once per stock tick"),
    # cCockGameOver's three states count down a transition wait before dispatch.
    ("objects", "count", 0x3FCE4E, "sub word ptr [rbx + 0x7e], 1", None,
     "cCockGameOver: pace the first transition wait"),
    ("objects", "count", 0x3FCE9C, "sub word ptr [rbx + 0x7c], 1", None,
     "cCockGameOver: pace the second transition wait"),
    ("objects", "count", 0x3FCED3, "sub word ptr [rbx + 0x7c], 1", None,
     "cCockGameOver: pace the third transition wait"),
    # cSubScrFilesInfoWanted has an actual state-1 pause countdown. Its +64
    # selection changes are driven by controller action tests.
    ("objects", "count", 0x4207FD, "sub byte ptr [rbx + 0x7b], cl", "down",
     "cSubScrFilesInfoWanted: pace the state-1 pause countdown"),
    # cSubScrItem state 1 fades a sprite byte by +16 each tick until 0x80.
    ("objects", "count", 0x40DA2A, "add byte ptr [rax + 0x3b], 0x10", None,
     "cSubScrItem: pace the selected sprite's alpha fade"),
    # uta9's helper approaches all three +D20/+D24/+D28 components with the
    # same literal 0.08 factor. Compounding it gives the stock target approach.
    ("objects", "blend", 0x566175, "movss xmm2, dword ptr [rip + 0x113af3]",
     (0x679C70, 0.07999999821186066),
     "uta9: compound the shared 0.08 XYZ target blend"),
    # cGear's slot-3 update contains its full tick state machine: two waits and
    # its gear-angle advances. No previously patched sites are inside it.
    ("objects", "gatefn", 0x495950, "push rbx", None,
     "cGear: advance the full gear state machine on stock ticks"),
    # uta0, utaf and utb5 each use the same submodel-particle update: a short
    # byte countdown, position from velocity, velocity drag/gravity, collision
    # damping and state transition. Each is called once by its parent update and
    # has no previously patched site inside. Pace the complete state loop.
    ("objects", "gatefn", 0x55CA10, "mov rax, rsp", None,
     "uta0: pace its submodel particle state loop on stock ticks"),
    ("objects", "gatefn", 0x56C470, "mov rax, rsp", None,
     "utaf: pace its submodel particle state loop on stock ticks"),
    ("objects", "gatefn", 0x56EA30, "mov rax, rsp", None,
     "utb5: pace its submodel particle state loop on stock ticks"),
    # uta4 has three independent approach factors in its state-1 update. The
    # +1110 wait is loaded into AX, conditionally decremented, then stored.
    ("objects", "count", 0x561067, "dec ax",
     (0x56105B,0x56106A,(0x56105B,0x561062,0x561065,0x561067),None),
     "uta4: pace the +1110 state wait"),
    ("objects", "blend", 0x56107D, "mulss xmm6, dword ptr [rip + 0x11656b]",
     (0x6775F0, 0.05000000074505806),
     "uta4: compound the 0.05 scale approach"),
    ("objects", "blend", 0x5610B4, "movss xmm2, dword ptr [rip + 0x110d48]",
     (0x671E04, 0.10000000149011612),
     "uta4: compound the 0.1 XYZ target approach"),
    ("objects", "blend", 0x56112D, "movss xmm2, dword ptr [rip + 0x11190b]",
     (0x672A40, 0.009999999776482582),
     "uta4: compound the 0.01 XYZ target approach"),
    # ut65's whole helper advances one scripted submodel effect, with its pose
    # transitions and angle step in the same update; no existing patch is inside.
    ("objects", "gatefn", 0x2217F0, "mov qword ptr [rsp + 8], rbx", None,
     "ut65: pace the scripted submodel effect update on stock ticks"),
    # These ten animal action handlers share the same +1170 random wait. A LEA
    # decrements the loaded value; the following `test ecx` fires the reload/event
    # when the old count was zero. Keep both the store and its event test at the
    # stock cadence so a held zero does not fire again between stock ticks.
    ("actor", "count", 0x1D60E1, "mov dword ptr [rsi + 0x1170], eax", None,
     "an00: pace the +1170 wait"),
    ("actor", "notyet", 0x1D60E7, "test ecx, ecx", 0x1D6116,
     "an00: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1DD683, "mov dword ptr [rsi + 0x1170], eax", None,
     "an04/an0d/an0e: pace the +1170 wait"),
    ("actor", "notyet", 0x1DD689, "test ecx, ecx", 0x1DD6B8,
     "an04/an0d/an0e: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1E0F36, "mov dword ptr [rsi + 0x1170], eax", None,
     "an06/an08: pace the +1170 wait"),
    ("actor", "notyet", 0x1E0F3C, "test ecx, ecx", 0x1E0F6B,
     "an06/an08: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1E3B73, "mov dword ptr [rsi + 0x1170], eax", None,
     "an07: pace the +1170 wait"),
    ("actor", "notyet", 0x1E3B79, "test ecx, ecx", 0x1E3BA8,
     "an07: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1E7403, "mov dword ptr [rsi + 0x1170], eax", None,
     "an09: pace the +1170 wait"),
    ("actor", "notyet", 0x1E7409, "test ecx, ecx", 0x1E7438,
     "an09: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1EA349, "mov dword ptr [rsi + 0x1170], eax", None,
     "an0b: pace the +1170 wait"),
    ("actor", "notyet", 0x1EA34F, "test ecx, ecx", 0x1EA364,
     "an0b: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1ED649, "mov dword ptr [rdi + 0x1170], eax", None,
     "an0c: pace the +1170 wait"),
    ("actor", "notyet", 0x1ED64F, "test ecx, ecx", 0x1ED664,
     "an0c: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1F4D43, "mov dword ptr [rsi + 0x1170], eax", None,
     "an19: pace the +1170 wait"),
    ("actor", "notyet", 0x1F4D49, "test ecx, ecx", 0x1F4D78,
     "an19: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1FB14E, "mov dword ptr [rsi + 0x1170], eax", None,
     "an1e: pace the +1170 wait"),
    ("actor", "notyet", 0x1FB154, "test ecx, ecx", 0x1FB183,
     "an1e: suppress the +1170 reload event between stock ticks"),
    ("actor", "count", 0x1FEA54, "mov dword ptr [rsi + 0x1170], eax", None,
     "an02/an1b/an1f/an20: pace the +1170 wait"),
    ("actor", "notyet", 0x1FEA5A, "test ecx, ecx", 0x1FEA89,
     "an02/an1b/an1f/an20: suppress the +1170 reload event between stock ticks"),
    # et0f's two motion/action helpers each count down the same +1138 wait.
    ("objects", "count", 0x2E4FB9, "dec word ptr [rbx + 0x1138]", None,
     "et0f first helper: pace the +1138 wait"),
    ("objects", "count", 0x2E50F9, "dec word ptr [rbx + 0x1138]", None,
     "et0f second helper: pace the +1138 wait"),
    # et69's nearby-target effect reloads +E36 to 89 and then counts down AX.
    ("objects", "count", 0x4D1448, "dec al",
     (0x4D13E8,0x4D144A,(0x4D13E8,0x4D13EF,0x4D13F1,0x4D1448),None),
     "et69: pace the +E36 effect cooldown"),
    # ut6d has a 30-tick sound wait and a separate action countdown, both
    # loaded to AL and conditionally decremented before their stores.
    ("objects", "count", 0x224053, "dec al",
     (0x224019,0x224055,(0x224019,0x224020,0x224022,0x224053),None),
     "ut6d: pace the +E35 sound wait"),
    ("objects", "count", 0x22408A, "dec al",
     (0x224072,0x22408C,(0x224072,0x224079,0x22407B,0x22408A),None),
     "ut6d: pace the +E36 action countdown"),
    # The three +68 branches are too close to live jump targets for separate
    # five-byte windows. This vtable slot-3 callback does only those branches.
    ("objects", "gatefn", 0x3FC430, "mov eax, 0xc00", None,
     "cCockEventEdge: pace its whole +68 HUD edge callback on stock ticks"),
    ("objects", "count", 0x3FE52A, "dec dword ptr [rbx + 0x7c]", None,
     "cCockInkGauge: pace the +7C ink recovery cooldown"),
    # Files enemy list: both sprites slide by 32 each stock tick in either direction.
    ("objects", "lin", 0x41BBBC, "subss xmm0, dword ptr [rip + 0x256048]", (0x671C0C, 32.0),
     "cSubScrFilesEnemy: scale the first sprite's upward 32 step"),
    ("objects", "lin", 0x41BBCF, "subss xmm0, dword ptr [rip + 0x256035]", (0x671C0C, 32.0),
     "cSubScrFilesEnemy: scale the second sprite's upward 32 step"),
    ("objects", "lin", 0x41BE54, "addss xmm0, dword ptr [rip + 0x255db0]", (0x671C0C, 32.0),
     "cSubScrFilesEnemy: scale the first sprite's downward 32 step"),
    ("objects", "lin", 0x41BE67, "addss xmm0, dword ptr [rip + 0x255d9d]", (0x671C0C, 32.0),
     "cSubScrFilesEnemy: scale the second sprite's downward 32 step"),
    # The same factor in xmm1 advances all three D20/D24/D28 scale channels,
    # each clamped to one after its step.
    ("actor", "lin", 0x1D69ED, "movss xmm1, dword ptr [rip + 0x49c04b]",
     (0x672A40, 0.009999999776482582),
     "an00: scale the shared 0.01 three-channel growth step"),
    ("actor", "lin", 0x1D9DD8, "movss xmm1, dword ptr [rip + 0x49fe50]",
     (0x679C30, 0.019999999552965164),
     "an01: scale the shared 0.02 three-channel growth step"),
    ("actor", "lin", 0x1DE1A2, "movss xmm1, dword ptr [rip + 0x494896]",
     (0x672A40, 0.009999999776482582),
     "an04/an0d/an0e: scale the shared 0.01 three-channel growth step"),
    ("actor", "lin", 0x1E17E9, "movss xmm1, dword ptr [rip + 0x49709f]",
     (0x678890, 0.029999999329447746),
     "an06/an08: scale the shared 0.03 three-channel growth step"),
    ("actor", "lin", 0x1E4426, "movss xmm1, dword ptr [rip + 0x494462]",
     (0x678890, 0.029999999329447746),
     "an07: scale the shared 0.03 three-channel growth step"),
    ("actor", "lin", 0x1F17D7, "movss xmm1, dword ptr [rip + 0x4870b1]",
     (0x678890, 0.029999999329447746),
     "an05/an18: scale the shared 0.03 three-channel growth step"),
    ("actor", "lin", 0x1F8002, "movss xmm1, dword ptr [rip + 0x480886]",
     (0x678890, 0.029999999329447746),
     "an1a: scale the shared 0.03 three-channel growth step"),
    ("actor", "lin", 0x1FF1D4, "movss xmm1, dword ptr [rip + 0x47aaf4]",
     (0x679CD0, 0.014999999664723873),
     "an02/an1b/an1f/an20: scale the shared 0.015 three-channel growth step"),
    ("objects", "lin", 0x2EA7D7, "addss xmm1, dword ptr [rip + 0x38ce11]",
     (0x6775F0, 0.05000000074505806),
     "et2e: scale the first +1158 0.05 orbit step"),
    ("objects", "lin", 0x2EA870, "addss xmm1, dword ptr [rip + 0x38cd78]",
     (0x6775F0, 0.05000000074505806),
     "et2e: scale the second +1158 0.05 orbit step"),
    ("objects", "lin", 0x2EA8EF, "subss xmm0, dword ptr [rip + 0x38b33d]", (0x675C34, 0.25),
     "et2e: scale the descending Y 0.25 step"),
    ("objects", "count", 0x2EA94E, "inc al",
     (0x2EA943,0x2EA950,(0x2EA943,0x2EA94A,0x2EA94C,0x2EA94E),None),
     "et2e: pace the capped +E37 orbit stage counter"),
    ("objects", "lin", 0x2EAA41, "addss xmm1, dword ptr [rip + 0x38f227]",
     (0x679C70, 0.07999999821186066),
     "et2e: scale the +B4 0.08 rotation step"),
    ("objects", "gatefn", 0x1B2C60, "mov rax, rsp", None,
     "UI element compositor: pace the complete angle, RGBA and XY accumulation pass on "
     "stock ticks"),
    ("objects", "gatefn", 0x2DE450, "mov qword ptr [rsp + 8], rbx", None,
     "et67: pace the complete target-force, position integration and 0.9 drag step on "
     "stock ticks"),
    ("objects", "count", 0x3F877A, "inc word ptr [rdi + 0x194]", None,
     "cCockBattleResult: pace the +194 transition wait"),
    ("objects", "count", 0x3F896C, "sub word ptr [rdi + 0x198], 1", None,
     "cCockBattleResult: pace the +198 transition wait"),
    ("objects", "count", 0x3FD0E6, "inc word ptr [rcx + 0x7e]", None,
     "cCockGameOver: pace the +7E stage wait"),
    ("objects", "gatefn", 0x3FDB40, "push rbx", None,
     "cCockHappyPoint: pace the +168 display tally and +16C countdown together"),
    ("objects", "count", 0x4004F1, "mov byte ptr [rbx + 0x39c], al", None,
     "cCockLoading: pace the +39C loading animation counter"),
    ("objects", "count", 0x40059A, "inc dword ptr [rbx + 0x70]", None,
     "cCockLoading: pace the +70 loading animation counter"),
    ("objects", "lin", 0x232C8A, "movss xmm2, dword ptr [rip + 0x43fc9a]",
     (0x67292C, 0.20000000298023224),
     "utdc: scale the three-channel 0.2 shrink step"),
    ("objects", "lin", 0x232D55, "movss xmm2, dword ptr [rip + 0x43fbcf]",
     (0x67292C, 0.20000000298023224),
     "utdc: scale the three-channel 0.2 growth step"),
    ("objects", "gatefn", 0x22DB40, "mov rax, rsp", None,
     "utbc: pace the complete force, position and drag update on stock ticks"),
    ("objects", "lin", 0x405EE5, "movss xmm2, dword ptr [rip + 0x26bf1b]", (0x671E08, 0.5),
     "cCockSgStmcGauge: scale the shared 0.5 angle step for +68/+6C"),
    ("objects", "lin", 0x407175, "movss xmm2, dword ptr [rip + 0x26ac8b]", (0x671E08, 0.5),
     "cCockStomachGauge: scale the shared 0.5 angle step for +68/+6C"),
    ("actor", "lin", 0x1DBE6C, "movss xmm1, dword ptr [rip + 0x496ab4]",
     (0x672928, 0.01745329238474369),
     "an03: scale the shared one-degree B8 tilt step in either direction"),
    ("actor", "blend", 0x1DC6C0, "mulss xmm3, dword ptr [rip + 0x49573c]",
     (0x671E04, 0.10000000149011612),
     "an03: compound the E48 target blend of 0.1"),
    ("actor", "blend", 0x1DC6E0, "mulss xmm2, dword ptr [rip + 0x49571c]",
     (0x671E04, 0.10000000149011612),
     "an03: compound the E4C target blend of 0.1"),
    ("actor", "blend", 0x1ED7BF, "mulss xmm3, dword ptr [rip + 0x485165]",
     (0x67292C, 0.20000000298023224),
     "an0c slot 25: compound the E48 target blend of 0.2"),
    ("actor", "blend", 0x1ED7DF, "mulss xmm2, dword ptr [rip + 0x485145]",
     (0x67292C, 0.20000000298023224),
     "an0c slot 25: compound the E4C target blend of 0.2"),
    ("actor", "blend", 0x1EF04D, "mulss xmm3, dword ptr [rip + 0x4838d7]",
     (0x67292C, 0.20000000298023224),
     "an0c helper: compound the E48 target blend of 0.2"),
    ("actor", "blend", 0x1EF06D, "mulss xmm2, dword ptr [rip + 0x4838b7]",
     (0x67292C, 0.20000000298023224),
     "an0c helper: compound the E4C target blend of 0.2"),
    # cSubScrFilesInfo's two transitions, each store on stock ticks; both
    # tail-jump into their layout update 1B54E0, which runs every tick (a
    # gatefn on them ran it once a stock tick: tracks 4x long)
    ("objects", "count", 0x41E1E4, "movss dword ptr [rax + 0x24], xmm0", None,
     "cSubScrFilesInfo 41E170, state 1: sprite 6's y (+24) moves by its distance / 15 "
     "a tick"),
    ("objects", "count", 0x41E1F2, "mov dword ptr [rdi + 0x334], eax", None,
     "cSubScrFilesInfo 41E170: the transition's countdown +334 (15) -= 1 a tick"),
    ("objects", "notyet", 0x41E1F8, "test ecx, ecx", 0x41E26C,
     "cSubScrFilesInfo 41E170: its end at the old +334 = 0: between stock ticks, not "
     "yet (the countdown holds 0)"),
    ("objects", "count", 0x41EEFE, "movss dword ptr [rax + 0x24], xmm0", None,
     "cSubScrFilesInfo 41EE90, state 1: sprite 6's y (+24) moves back by its distance "
     "/ 15 a tick"),
    ("objects", "count", 0x41EF0C, "mov dword ptr [rdi + 0x334], eax", None,
     "cSubScrFilesInfo 41EE90: the countdown +334 -= 1 a tick"),
    ("objects", "notyet", 0x41EF12, "test ecx, ecx", 0x41EF8A,
     "cSubScrFilesInfo 41EE90: its end at the old +334 = 0: between stock ticks, not "
     "yet"),
    ("objects", "gatefn", 0x2EAB10, "push rdi", None,
     "et2e: pace its complete distance-follow displacement helper"),
    ("objects", "gatefn", 0x2EB340, "push rdi", None,
     "et2e: pace its complete nearby-target displacement helper"),
    ("objects", "gatefn", 0x406BC0, "mov eax, 0xc00", None,
     "cCockStamp update only changes its countdown +7C and exponential stamp scale "
     "+6C; pace the function together"),
    ("objects", "gatefn", 0x57E020, "mov qword ptr [rsp + 0x10], rbx", None,
     "ut33 eye and body wobble helper: pace E14 angular motion, E3E/E40 effect "
     "windows, and B0 angle together; parent still advances scaled motion"),
    ("objects", "count", 0x2F570B, "mov byte ptr [rbx + 0x1102], al", None,
     "et72: pace the +1102 90-tick action wait"),
    ("objects", "count", 0x2F6BB7, "mov word ptr [rbx + 0x1080], cx", None,
     "et74: pace the +1080 action counter"),
    ("objects", "count", 0x2F8806, "mov word ptr [rbx + 0x10bc], ax", None,
     "et92: pace the +10BC 120-tick wait"),
    ("objects", "count", 0x2F9072, "dec dword ptr [rbx + 0x1080]", None,
     "gt01: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2F966E, "dec dword ptr [rbx + 0x1080]", None,
     "gt03: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2F9D22, "dec dword ptr [rbx + 0x1080]", None,
     "gt11: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2FA2D2, "dec dword ptr [rbx + 0x1080]", None,
     "gt13: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2FAE4E, "dec dword ptr [rbx + 0x1080]", None,
     "gt19: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2FB43B, "dec dword ptr [rbx + 0x1080]", None,
     "gt1b: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2FBA48, "dec dword ptr [rbx + 0x1080]", None,
     "gt1d: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2FC019, "dec dword ptr [rbx + 0x1080]", None,
     "gt1f: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2FC62F, "dec dword ptr [rbx + 0x1080]", None,
     "gt97: pace the +1080 countdown in action 1"),
    ("objects", "count", 0x2FDACF, "mov word ptr [rdi + 0x1084], ax", None,
     "gtfe: pace the +1084 start wait"),
    ("objects", "count", 0x2FDE1C, "mov word ptr [rbx + 0x1084], ax", None,
     "gtfe: pace the +1084 end wait"),
    ("objects", "count", 0x2FF528, "dec dword ptr [rbx + 0x1074]", None,
     "gt_org1: pace the +1074 action countdown"),
    ("objects", "count", 0x2F13D5, "mov word ptr [rsi + 0xe3c], ax", None,
     "et67: pace the +E3C 16-tick action window"),
    ("objects", "count", 0x2F1A6F, "mov word ptr [rsi + 0xe42], ax", None,
     "et67: pace the +E42 action timer"),
    ("objects", "count", 0x2F2A19, "mov dword ptr [rdi + 0x1080], eax", None,
     "et6b: pace the first +1080 action countdown"),
    ("objects", "count", 0x2F2DC7, "mov dword ptr [rdi + 0x1080], eax", None,
     "et6b: pace the second +1080 action countdown"),
    ("objects", "count", 0x2F2E62, "mov dword ptr [rdi + 0x1080], eax", None,
     "et6b: pace the third +1080 action countdown"),
    ("objects", "count", 0x2F497B, "dec byte ptr [rbx + 0x10e7]", None,
     "et71: pace the +10E7 action countdown"),
    ("objects", "count", 0x2F9A9F, "mov word ptr [rbx + 0xe3c], ax", None,
     "gt10: pace the +E3C 30-tick action countdown"),
    ("objects", "count", 0x2FA93F, "dec dword ptr [rbx + 0x1080]", None,
     "gt17: pace the +1080 action countdown"),
    ("objects", "count", 0x14776D, "add bx, 5", "phase5",
     "cOptionCalibration: pace the +A2 angle phase increment of five degrees before "
     "the sine gauge is recalculated"),
    ("objects", "count", 0x147FFF, "inc dword ptr [rcx + 0x80]", None,
     "cOptionControllerSelect/cOptionPairing: pace the +80 elapsed-tick counter"),
    ("objects", "count", 0x1BF1F2, "dec dword ptr [rcx + 0x200]", None,
     "cMcLoad/cMcSave: pace the first +200 memory-card request countdown"),
    ("objects", "count", 0x1BF4B0, "dec dword ptr [rcx + 0x200]", None,
     "cMcLoad/cMcSave: pace the second +200 memory-card request countdown"),
    ("objects", "count", 0x3ECA47, "mov dword ptr [r14 + 0xf8], ecx", None,
     "UI event iterator: pace the +F8 conditional waiting counter"),
    ("objects", "count", 0x3F3B19, "mov dword ptr [rbx + 0x340], eax", None,
     "UI event manager: pace the +340 active wait when it is nonzero"),
    ("objects", "count", 0x3F98AE, "sub word ptr [rdi + 0x198], 1", None,
     "cCockBattleResult: pace the +198 transition countdown in the input branch"),
    ("objects", "count", 0x3FD1C4, "sub word ptr [rbx + 0x7c], 1", None,
     "cCockGameOver: pace the +7C repeating flash countdown"),
    ("objects", "count", 0x3FE1F0, "mov dword ptr [rbx], eax", None,
     "cCockHappyPoint: pace each +68 reward-display delay before its tally is credited"),
    ("objects", "count", 0x3FFC36, "dec ax", (0x3FFC2D,0x3FFC39,(0x3FFC2D,0x3FFC31,0x3FFC34,0x3FFC36),None),
     "cCockLifeGauge: pace the +78 life display wait's decrement while positive"),
    ("objects", "count", 0x4022B2, "sub ax, 1", "title",
     "cCockMapTitle: pace the +68 title countdown and its jns continuation together"),
    ("objects", "count", 0x405243, "sub cx, 1", "remain",
     "cCockRemain: pace the +68 countdown; the following cmove must see nonzero on "
     "skipped ticks"),
    ("objects", "lin", 0x40DCC3, "addss xmm0, dword ptr [rip + 0x26520d]", (0x672ED8, 10.0),
     "cSubScrItem: scale the list cursor sprite's ten-unit x step during its open "
     "selection state"),
    ("objects", "count", 0x41F62B, "sub dword ptr [rdi + 0xd4], 1", None,
     "cSubScrFilesInfoMess: pace the +D4 opening transition countdown"),
    ("objects", "count", 0x42036F, "sub dword ptr [rdi + 0xd4], 1", None,
     "cSubScrFilesInfoMess: pace the +D4 closing transition countdown"),
    ("objects", "count", 0x420D64, "dec byte ptr [rdi + 0x7a]", None,
     "cSubScrFilesInfoWanted: pace the +7A visibility countdown on the per-tick helper "
     "path"),
    ("objects", "lin", 0x425927, "subss xmm0, dword ptr [rip + 0x250179]", (0x675AA8, 40.0),
     "cSubScrItem: scale the 40-unit sprite x step during its active item-selection "
     "state"),
    ("actor", "count", 0x1DBFC8, "mov word ptr [rcx + 0x1184], ax", None,
     "an03: pace the +1184 900-tick behavior countdown"),
    ("actor", "count", 0x1DC5E8, "mov word ptr [rcx + 0xe3c], ax", None,
     "an03: pace the randomized +E3C behavior countdown"),
    ("actor", "dst", 0x1E7CD6, "movss xmm1, dword ptr [rip + 0x490bb2]", None,
     "an09: scale the shared 0.03 rise step in xmm1 for D20/D24/D28 together"),
    ("actor", "dst", 0x1EAE28, "movss xmm1, dword ptr [rip + 0x48da60]", None,
     "an0b: scale the shared 0.03 rise step in xmm1 for D20/D24/D28 together"),
    ("actor", "count", 0x1EB097, "mov word ptr [rbx + 0xe3c], ax", None,
     "an0b: pace the +E3C action countdown"),
    ("actor", "count", 0x1EFE85, "mov byte ptr [rbx + 0x1230], al", None,
     "an05/an18: pace the +1230 contact cooldown"),
    ("actor", "lin", 0x1F2683, "addss xmm0, dword ptr [rip + 0x48757d]",
     (0x679C08, 0.13962633907794952),
     "an05/an18: scale the positive B4 turn-search step"),
    ("actor", "lin", 0x1F268D, "subss xmm0, dword ptr [rip + 0x487573]",
     (0x679C08, 0.13962633907794952),
     "an05/an18: scale the negative B4 turn-search step"),
    ("actor", "dst", 0x1F5628, "movss xmm1, dword ptr [rip + 0x483260]", None,
     "an19: scale the shared 0.03 rise step in xmm1 for D20/D24/D28 together"),
    ("actor", "dst", 0x1FB885, "movss xmm1, dword ptr [rip + 0x47d003]", None,
     "an1e: scale the shared 0.03 rise step in xmm1 for D20/D24/D28 together"),
    ("actor", "count", 0x202407, "sub word ptr [rdi + 0x119c], 1", None,
     "anc7: pace the +119C countdown in the event handler"),
    ("actor", "count", 0x203242, "mov dword ptr [rcx + 0x1170], eax", None,
     "an0c: pace the +1170 behavior countdown"),
    ("actor", "count", 0x205C75, "mov byte ptr [rdi + 0x1175], al", None,
     "anff: pace the +1175 submodel motion countdown"),
    ("actor", "count", 0x484CD8, "mov byte ptr [rcx + 0x1200], al", None,
     "cDogLikeHm: pace the +1200 effect cooldown"),
    ("actor", "count", 0x484DAE, "inc dword ptr [rbx + 0x120c]", None,
     "cDogLikeHm: pace the +120C active-behavior counter"),
    ("actor", "count", 0x48620D, "mov byte ptr [rbx + 0xe36], al", None,
     "cDogLikeHm: pace the +E36 action-step counter while below ten"),
    ("actor", "blend", 0x2049EB, "mulss xmm1, dword ptr [rip + 0x47103d]",
     (0x675A30, 0.30000001192092896),
     "an05/an18: compound the 0.3 B0 heading blend toward its target"),
    ("actor", "blend", 0x204A1E, "mulss xmm1, dword ptr [rip + 0x47100a]",
     (0x675A30, 0.30000001192092896),
     "an05/an18: compound the 0.3 B0 heading blend toward zero"),
    ("actor", "count", 0x4855A2, "add byte ptr [rdi + 0xe36], 0xff", None,
     "cDogLikeHm: pace the +E36 action countdown branch"),
    ("actor", "src", 0x488848, "subss xmm0, xmm7", None,
     "cDogMakimono: scale the one-unit +1070 descent step at its subtraction"),
    ("actor", "count", 0x48D476, "sub byte ptr [rdi + 0x10f8], cl", "down",
     "cFish: pace the +10F8 countdown by one in action stage one"),
    ("objects", "countlast", 0x40D977, "mulss xmm0, xmm6", None,
     "cSubScrItem: keep sprite 13 alpha between stock ticks, apply the current alpha "
     "factor only once per stock period"),
    ("objects", "countlast", 0x40D9CA, "mulss xmm0, xmm6", None,
     "cSubScrItem: keep sprite 14 alpha between stock ticks, apply the current alpha "
     "factor only once per stock period"),
    ("objects", "count", 0x40D76E, "mov byte ptr [rbx + 0x51], al", None,
     "cPictureBook: pace the +51 close-state sequence through its slot-12 update"),
    ("objects", "count", 0x424D9B, "add al, 8",
     (0x424D85,0x424D9D,(0x424D85,0x424D89,0x424D8B,0x424D9B),None),
     "cSubScrItem: pace the +3B alpha increase by eight during the image fade"),
    ("objects", "count", 0x424DF3, "sub al, 8",
     (0x424DB6,0x424DF5,(0x424DB6,0x424DBA,0x424DBC,0x424DF3),None),
     "cSubScrItem: pace the +3B alpha decrease by eight during the image fade"),
    ("objects", "count", 0x5A4AC8, "mov byte ptr [rbx + 0x10e2], al", None,
     "utce: pace the +10E2 contact cooldown"),
    ("objects", "count", 0x5A4D45, "mov byte ptr [rdi + 0x10e1], al", None,
     "utce: pace the +10E1 contact cooldown"),
    ("objects", "count", 0x5A4DDD, "mov byte ptr [rdi + 0xe36], bl", None,
     "utce: pace the +E36 ten-stage spin counter"),
    ("objects", "pre", 0x5A4DF6, "addss xmm0, dword ptr [rdi + 0xb8]", None,
     "utce: scale the current spin step before adding the old B8 heading in stage two"),
    ("objects", "pre", 0x5A4E3C, "addss xmm0, dword ptr [rdi + 0xb8]", None,
     "utce: scale the current spin step before adding the old B8 heading in stage one"),
    ("objects", "count", 0x5A4F39, "mov byte ptr [rdi + 0x10e3], al", None,
     "utce: pace the +10E3 contact cooldown"),
    ("objects", "count", 0x5AAAB6, "dec byte ptr [rcx + 0x10d8]", None,
     "utf8: pace the +10D8 countdown before the one-time direction reversal"),
    ("objects", "src", 0x5A4149, "subss xmm0, xmm6", None,
     "utc7: scale the submodel angular step in the first branch"),
    ("objects", "src", 0x5A41AF, "addss xmm0, xmm6", None,
     "utc7: scale the submodel angular step in the second branch"),
    ("objects", "src", 0x5A425C, "addss xmm0, xmm6", None,
     "utc7: scale the submodel angular step in the third branch"),
    ("objects", "count", 0x5A33A1, "mov byte ptr [rbx + 0xe35], al", None,
     "utc6: pace the +E35 short wait"),
    ("objects", "lin", 0x5A342F, "addss xmm1, dword ptr [rip + 0x117ee9]",
     (0x6BB320, 0.0949999988079071),
     "utc6: scale the positive +1084 angle step"),
    ("objects", "lin", 0x5A3439, "subss xmm1, dword ptr [rip + 0x117edf]",
     (0x6BB320, 0.0949999988079071),
     "utc6: scale the negative +1084 angle step"),
    ("objects", "pre", 0x5A3B89, "addss xmm0, dword ptr [r14 + 0x1088]", None,
     "utc6: scale the angular step before adding the old +1088 heading"),
    ("objects", "src", 0x5A3BBE, "subss xmm0, xmm6", None,
     "utc6: scale the angular step at the +1088 subtraction"),
    ("actor", "count", 0x484799, "mov byte ptr [rdi + 0x120a], al", None,
     "cDogLikeHm: pace the +120A contact effect window to its saturation at 29"),
    ("actor", "count", 0x4847D7, "mov byte ptr [rdi + 0x120b], al", None,
     "cDogLikeHm: pace the +120B effect cooldown after its three-tick reset"),
    ("actor", "dst", 0x1EDFAA, "movss xmm1, dword ptr [rip + 0x48a8de]", None,
     "an0c: scale the shared 0.03 rise for D20, D24, and D28"),
    ("actor", "pre", 0x202B25, "addss xmm0, dword ptr [rax + 4]", None,
     "anff: scale +E54 vertical velocity before adding the old actor Y"),
    ("actor", "pre", 0x484BD6, "addss xmm0, dword ptr [rax + 4]", None,
     "cDogLikeHm: scale +E54 vertical velocity before adding the old actor Y"),
    ("actor", "pre", 0x1D5529, "addss xmm0, dword ptr [rax + 4]", None,
     "an00: scale +1248 vertical velocity before adding the old submodel Y"),
    ("objects", "count", 0x5A4B8A, "mov byte ptr [rcx + 0x10e2], al", None,
     "utca: pace the +10E2 effect cooldown"),
    ("objects", "count", 0x5A503B, "mov byte ptr [rbx + 0x10e0], al", None,
     "utce: pace the +10E0 wait before returning scale to one"),
    ("objects", "count", 0x5A5AAB, "mov byte ptr [rdi + 0x1071], al", None,
     "utce: pace the +1071 effect cooldown"),
    ("objects", "count", 0x5A5C5A, "mov byte ptr [rbx + 0x1072], al", None,
     "utce: pace the +1072 wait before returning scale to one"),
    ("objects", "lin", 0x5A5FA0, "subss xmm0, dword ptr [rip + 0x115708]",
     (0x6BB6B0, 0.18000000715255737),
     "utce: scale the negative 0.18 submodel angular step"),
    ("objects", "count", 0x5A5FC5, "add byte ptr [rbx + 0xe35], 0xff", None,
     "utce: pace the E35 return-stage countdown"),
    ("objects", "lin", 0x5A6000, "addss xmm0, dword ptr [rip + 0x1156a8]",
     (0x6BB6B0, 0.18000000715255737),
     "utce: scale the positive 0.18 submodel angular step"),
    ("objects", "count", 0x5A6025, "inc byte ptr [rbx + 0xe35]", None,
     "utce: pace the E35 outward-stage count"),
    ("objects", "src", 0x5A60BB, "subss xmm0, xmm1", None,
     "utce: scale the +1074-derived submodel angular step at the subtraction"),
    ("objects", "pre", 0x5A60F9, "addss xmm0, dword ptr [rax + 0xb8]", None,
     "utce: scale the +1074-derived submodel angular step before adding the old B8 "
     "angle"),
    ("objects", "count", 0x5A6180, "add byte ptr [rdi + 0xe35], 0xff", None,
     "utce: pace the E35 action-stage countdown"),
    ("objects", "count", 0x5A6FCD, "mov byte ptr [rbx + 0xe36], al", None,
     "utd0: pace the E36 action-stage countdown"),
    ("objects", "pre", 0x5A7A23, "addss xmm1, dword ptr [rdx + 0xd2c]", None,
     "utd8: scale the state-selected positive or negative D2C rise step before adding "
     "the old value"),
    ("objects", "count", 0x5A9445, "dec dword ptr [rdi + 0x1118]", None,
     "utf0: pace the +1118 duration counter"),
    ("objects", "count", 0x5A9481, "mov byte ptr [rdi + 0x1116], al", None,
     "utf0: pace the +1116 two-tick effect cooldown"),
    ("objects", "lin", 0x5A9851, "addss xmm0, dword ptr [rip + 0x105b5b]", (0x6AF3B4, 0.625),
     "utf0: scale the 0.625 submodel B4 angular step"),
    ("objects", "count", 0x5A98CC, "mov byte ptr [rdi + 0x1117], al", None,
     "utf0: pace the +1117 effect cooldown"),
    ("objects", "count", 0x5AA238, "add byte ptr [rbx + 0x10e4], 0xff", None,
     "utf1: pace the +10E4 stage countdown"),
    ("objects", "count", 0x5AA992, "mov byte ptr [rbx + 0xe36], al", None,
     "utf8: pace the E36 action countdown"),
    ("objects", "count", 0x5ABABF, "mov byte ptr [rcx + 0xe36], al", None,
     "utfa: pace the E36 action countdown"),
    ("actor", "root", 0x204685, "movss xmm2, dword ptr [rip + 0x4755c7]", None,
     "an7f/anff/cAnimal: compound the 1.25 growth factor shared by C0, C4, C8"),
    ("actor", "root", 0x2046A4, "movss xmm2, dword ptr [rip + 0x47138c]", None,
     "an7f/anff/cAnimal: compound the 0.75 shrink factor shared by C0, C4, C8"),
    ("actor", "pre", 0x48694C, "addss xmm0, dword ptr [rbx]", None,
     "cDogLikeHm: scale the east-west velocity before adding actor X"),
    ("actor", "pre", 0x486970, "addss xmm0, dword ptr [rbx + 8]", None,
     "cDogLikeHm: scale the north-south velocity before adding actor Z"),
    ("actor", "count", 0x486A70, "mov byte ptr [rdi + 0xe36], al", None,
     "cDogLikeHm: pace the E36 steering-stage count before ten"),
    ("actor", "pre", 0x486B39, "addss xmm0, dword ptr [rbx]", None,
     "cDogLikeHm: scale the turn-derived displacement before adding actor X"),
    ("actor", "pre", 0x486D6F, "addss xmm0, dword ptr [rbx]", None,
     "cDogLikeHm: scale the turn-derived displacement before adding actor X"),
    ("actor", "pre", 0x486D87, "addss xmm0, dword ptr [rbx + 8]", None,
     "cDogLikeHm: scale the turn-derived displacement before adding actor Z"),
    ("objects", "lin", 0x5A2BBA, "addss xmm0, dword ptr [rip + 0xd94b6]",
     (0x67C078, 0.02617993950843811),
     "utbf: scale the 0.02617994 B4 angular step"),
    ("objects", "count", 0x5A2DBD, "mov byte ptr [rcx + 0xe36], al", None,
     "utbf: pace the E36 action countdown"),
    ("objects", "src", 0x5A67EF, "subss xmm0, xmm7", None,
     "utcf: scale the first +1074 fade decrement"),
    ("objects", "src", 0x5A6825, "subss xmm0, xmm7", None,
     "utcf: scale the second +1074 fade decrement"),
    ("objects", "lin", 0x5A7400, "subss xmm1, dword ptr [rip + 0xca800]", (0x671C08, 1.0),
     "utd8: scale the one-unit +1158 float countdown step"),
    ("objects", "count", 0x5A7FBF, "mov byte ptr [rcx + 0xe36], al", None,
     "utd8: pace the E36 stage count before five"),
    ("objects", "src", 0x5A883F, "addss xmm0, dword ptr [rbx + 0xf54]", None,
     "utf0: scale the +F54-derived addition to +110C"),
    ("objects", "pre", 0x5A89D8, "addss xmm0, dword ptr [rbx + 0x110c]", None,
     "utf0: scale the +F54-derived addition to +110C"),
    ("objects", "lin", 0x5A8BFF, "addss xmm1, dword ptr [rip + 0xcce3d]", (0x675A44, 1.5),
     "utf0: scale the 1.5 rise of the actor Y under its ceiling"),
    ("objects", "pre", 0x5A8D88, "addss xmm0, dword ptr [rbx + 0x110c]", None,
     "utf0: scale the +F54-derived addition to +110C"),
    ("actor", "gatefn", 0x201430, "push rbx", None,
     "anc7: pace the angle-only B4 smoothing helper called from its already paced "
     "actor update"),
    ("actor", "pre", 0x201EDD, "addss xmm1, dword ptr [rbx + 0x110c]", None,
     "anc7: scale the branch-two acceleration before adding the prior +110C velocity"),
    ("actor", "src", 0x201EF5, "subss xmm0, xmm1", None,
     "anc7: scale the current +110C velocity at the +1108 displacement subtraction"),
    ("actor", "pre", 0x201F17, "addss xmm0, dword ptr [rbx + 0x110c]", None,
     "anc7: scale the branch-one acceleration before adding the prior +110C velocity"),
    ("actor", "pre", 0x201F27, "addss xmm0, dword ptr [rbx + 0x1108]", None,
     "anc7: scale the current +110C velocity before adding prior +1108 displacement"),
    ("actor", "count", 0x20217A, "mov byte ptr [rbx + 0x1101], al", None,
     "anc7: pace the +1101 effect interval count"),
    ("actor", "count", 0x202233, "mov byte ptr [rbx + 0x1105], al", None,
     "anc7: pace the +1105 action cooldown"),
    ("actor", "srcblend", 0x1EF230, "mulss xmm3, xmm1", None,
     "an0c: compound the dynamic E48 approach factor after constructing its target"),
    ("actor", "srcblend", 0x1EF24C, "mulss xmm2, xmm1", None,
     "an0c: compound the dynamic E4C approach factor after constructing its target"),
    ("actor", "count", 0x2029BE, "mov byte ptr [rbx + 0x1187], al", None,
     "anff shared helper: pace the +1187 effect cooldown used by both callers"),
    ("actor", "pre", 0x48D999, "addss xmm0, dword ptr [rax + 4]", None,
     "cFish: scale the configured vertical step before adding old actor Y"),
    ("objects", "count", 0x5A7F12, "inc byte ptr [rbx + 0xe36]", None,
     "utd8: pace the E36 action count that follows motion selection"),
    ("objects", "count", 0x5A9BDA, "mov byte ptr [rcx + 0x10e6], al", None,
     "utf1: pace the +10E6 short wait"),
    ("objects", "gatefn", 0x5A9F90, "mov r11, rsp", None,
     "utf1: pace the +10E5 countdown together with its material and effect transitions"),
    ("objects", "lin", 0x5AB32B, "subss xmm1, dword ptr [rip + 0xc6ae1]", (0x671E14, 2.0),
     "utf9: scale the two-unit +10A8 fall toward its lower bound"),
    ("objects", "gatefn", 0x5ABF60, "push rbp", None,
     "utfa: pace the E36 action sequence and its effects together"),
    ("objects", "gatefn", 0x5AC5D0, "mov qword ptr [rsp + 0x10], rbx", None,
     "utfa: pace the E36 countdown and its 15/10-count event effects together"),
    ("objects", "gatefn", 0x5ACB30, "push rbx", None,
     "utfa: pace +1074 countdown, B4/submodel steering, and the 40-count effect "
     "together"),
    ("actor", "dst", 0x201FF9, "cvtdq2ps xmm3, xmm3", None,
     "anc7: scale the shared upward step before it feeds +1198, actor Z, and five "
     "linked world offsets"),
    ("actor", "dst", 0x2020C6, "mulss xmm2, xmm0", None,
     "anc7: scale the shared downward step before it feeds +1198, actor Z, and five "
     "linked world offsets"),
    ("actor", "src", 0x204E5F, "subsd xmm0, qword ptr [rip + 0x475091]", None,
     "anff: scale the double-precision decrement of +11B4 before conversion back to "
     "float"),
    ("actor", "src", 0x204EA1, "addsd xmm0, qword ptr [rip + 0x47504f]", None,
     "anff: scale the double-precision increment of +11B4 before conversion back to "
     "float"),
    ("actor", "srcroot", 0x204F55, "mulss xmm0, dword ptr [rip + 0x474d17]", None,
     "anff: compound the 0.4 EC8 damping factor per stock period"),
    ("actor", "notyet", 0x486B4B, "cmp byte ptr [rdi + 0xe36], bl", 0x486BA8,
     "cDogLikeHm: suppress the two E36-zero effects on held ticks before the paced "
     "count"),
    ("actor", "count", 0x486BA8, "inc byte ptr [rdi + 0xe36]", None,
     "cDogLikeHm: pace the E36 steering-stage count and its zero-triggered effects"),
    ("objects", "count", 0x2E5160, "dec word ptr [rbx + 0x1138]", None,
     "et0f: pace the +1138 action countdown in the fourth stage"),
    ("objects", "count", 0x2E596A, "dec word ptr [rbx + 0x1138]", None,
     "et0f: pace the +1138 action countdown after motion selection"),
    ("objects", "count", 0x2EE53B, "mov byte ptr [rbx + 0x1070], al", None,
     "et47: pace the +1070 30/60-tick behavior wait"),
    ("objects", "count", 0x2F098D, "mov byte ptr [rbx + 0xe76], cl", None,
     "et65: pace the +E76 bit-controlled cooldown"),
    ("objects", "count", 0x2F701C, "mov word ptr [rbx + 0xe3c], r8w", "up",
     "et7f: pace the +E3C ten-count effect interval"),
    ("objects", "notyet", 0x2F702E, "cmp ecx, eax", 0x2F70C5,
     "et7f: suppress the effect on held ticks when the old +E3C count is a multiple of "
     "ten"),
    ("objects", "count", 0x2F7551, "mov byte ptr [rbx + 0x1091], cl", None,
     "et8a: pace the +1091 four-count effect interval"),
    ("objects", "notyet", 0x2F7557, "and al, 3", 0x2F76CF,
     "et8a: suppress the four-count effect on held ticks"),
    ("objects", "blend", 0x2F76FE, "movss xmm6, dword ptr [rip + 0x380dc2]",
     (0x6784C8, 0.15000000596046448),
     "et8a: compound the shared 0.15 position blend for actor X, Y, and Z"),
    ("objects", "lin", 0x2F7789, "addss xmm0, dword ptr [rip + 0x3824ff]",
     (0x679C90, 0.05235987901687622),
     "et8a: scale the submodel E4 rotation step"),
    ("objects", "count", 0x2F787F, "mov word ptr [rdi + 0xe3c], bx", None,
     "et8a: pace the +E3C oscillator count"),
    ("objects", "count", 0x2FE5A6, "mov byte ptr [rdi + 0x1082], al", None,
     "gtfe: pace the +1082 stage count"),
    ("objects", "notyet", 0x2FE5AC, "test cl, cl", 0x2FE61E,
     "gtfe: suppress the stage-zero effect on held ticks"),
    ("objects", "lin", 0x2EAFE5, "addss xmm1, dword ptr [rip + 0x38d4db]",
     (0x6784C8, 0.15000000596046448),
     "et2e: scale the +1158 phase increment before the conditional wrap correction"),
    ("objects", "pre", 0x2ED375, "addss xmm0, dword ptr [rbx + 0x1140]", None,
     "et43: scale the angle-derived +1140 movement step in the timed stage"),
    ("objects", "pre", 0x2ED395, "addss xmm0, dword ptr [rbx + 0x1148]", None,
     "et43: scale the angle-derived +1148 movement step in the timed stage"),
    ("objects", "root", 0x2F1BDF, "movss xmm2, dword ptr [rip + 0x4ae695]", None,
     "et67: compound the shared 1.7 submodel X/Y/Z expansion factor"),
    ("objects", "lin", 0x33CE0C, "movss xmm1, dword ptr [rip + 0x33b268]",
     (0x67807C, -0.10000000149011612),
     "cCarryObj: scale the -0.1 +11D4 progress step"),
    ("objects", "lin", 0x33CE16, "movss xmm1, dword ptr [rip + 0x334fe6]",
     (0x671E04, 0.10000000149011612),
     "cCarryObj: scale the 0.1 +11D4 progress step"),
    ("objects", "count", 0x33CE97, "dec al",
     (0x33CE8C,0x33CE99,(0x33CE8C,0x33CE93,0x33CE95,0x33CE97),None),
     "cCarryObj: pace the +11C4 cooldown decrement"),
    ("objects", "count", 0x33CFA1, "mov byte ptr [rbx + 0x12b1], al", "down",
     "cCarryObj: pace the +12B1 wait's register-computed decrement at its store"),
    ("objects", "notyet", 0x33CFA7, "test cl, cl", 0x33CFD8,
     "cCarryObj: suppress the +12B1 zero-trigger effect on held ticks"),
    ("objects", "count", 0x33CFE3, "dec al",
     (0x33CFD8,0x33CFE5,(0x33CFD8,0x33CFDF,0x33CFE1,0x33CFE3),None),
     "cCarryObj: pace the +11C5 cooldown decrement"),
    ("objects", "pre", 0x33D1A1, "addss xmm1, dword ptr [rcx + 0x11d0]", None,
     "cCarryObj: scale the +11CC step before advancing +11D0"),
    ("objects", "dst", 0x33D6A7, "divss xmm1, xmm0", None,
     "cCarryObj: scale the +11C8 decrement derived from its remaining count"),
    ("objects", "count", 0x33D6D9, "dec ax",
     (0x33D6CD,0x33D6DC,(0x33D6CD,0x33D6D4,0x33D6D7,0x33D6D9),None),
     "cCarryObj: pace the +11C6 remaining count"),
    ("objects", "lin", 0x2E1AF6, "movss xmm0, dword ptr [rip + 0x390306]",
     (0x671E04, 0.10000000149011612),
     "et04: scale the positive +D2C state blend step"),
    ("objects", "lin", 0x2E1B00, "movss xmm0, dword ptr [rip + 0x396574]",
     (0x67807C, -0.10000000149011612),
     "et04: scale the negative +D2C state blend step"),
    ("objects", "lin", 0x2E9015, "movss xmm2, dword ptr [rip + 0x388de7]",
     (0x671E04, 0.10000000149011612),
     "et2b: scale the shared actor C0/C4/C8 channel rise"),
    ("objects", "blend", 0x223983, "movss xmm2, dword ptr [rip + 0x44e479]",
     (0x671E04, 0.10000000149011612),
     "ut69 update state one: compound the shared 0.1 approach toward one for "
     "D20/D24/D28"),
    ("objects", "blend", 0x223AD0, "movss xmm2, dword ptr [rip + 0x44e32c]",
     (0x671E04, 0.10000000149011612),
     "ut69 update state two: compound the shared 0.1 approach toward one for "
     "D20/D24/D28"),
    ("objects", "lin", 0x367C5A, "movss xmm2, dword ptr [rip + 0x30acca]",
     (0x67292C, 0.20000000298023224),
     "cKiType012/vt0c callback: scale the shared 0.2 rise of the D20/D24/D28 channels "
     "in state two"),
    ("objects", "lin", 0x35C82F, "movss xmm2, dword ptr [rip + 0x31adb9]",
     (0x6775F0, 0.05000000074505806),
     "objScroll 35C790 state five: scale the shared 0.05 rise of D20/D24/D28"),
    ("objects", "blend", 0x22933D, "mulss xmm1, dword ptr [rip + 0x4495e7]",
     (0x67292C, 0.20000000298023224),
     "ut96 update: compound the 0.2 X approach toward the computed point"),
    ("objects", "blend", 0x22935F, "mulss xmm1, dword ptr [rip + 0x4495c5]",
     (0x67292C, 0.20000000298023224),
     "ut96 update: compound the 0.2 Z approach toward the computed point"),
    ("objects", "lin", 0x55260E, "addss xmm2, dword ptr [rip + 0x124fda]",
     (0x6775F0, 0.05000000074505806),
     "ut47 first update: scale the +1084 angular phase advance"),
    ("objects", "lin", 0x5530E4, "addss xmm2, dword ptr [rip + 0x124504]",
     (0x6775F0, 0.05000000074505806),
     "ut47 second update: scale the +1084 angular phase advance"),
    ("objects", "lin", 0x35C5C6, "movss xmm3, dword ptr [rip + 0x315836]",
     (0x671E04, 0.10000000149011612),
     "objScroll 35C520 state fade: scale the shared 0.1 rise of C0/C8 and D20/D24/D28"),
    ("objects", "srcblend", 0x55F47A, "mulss xmm1, xmm6", None,
     "uta4 part case three: compound the 0.03 alpha approach factor at its multiply "
     "while preserving xmm6 for the other states"),
    ("objects", "lin", 0x55A53C, "movss xmm6, dword ptr [rip + 0x1176c4]", (0x671C08, 1.0),
     "55A430 coordinator: scale the shared one-unit E14 rise and fall for objects AA "
     "A0 and A1"),
    ("objects", "lin", 0x55A744, "movss xmm6, dword ptr [rip + 0x1176b8]",
     (0x671E04, 0.10000000149011612),
     "55A430 coordinator: scale the shared 0.1 D20/D24/D28 descent for linked objects "
     "in state zero"),
    ("objects", "lin", 0x55A838, "movss xmm6, dword ptr [rip + 0x1175c4]",
     (0x671E04, 0.10000000149011612),
     "55A430 coordinator: scale the shared 0.1 D20/D24/D28 ascent for linked objects "
     "in state one"),
    ("menu", "gatefn", 0x50FFC0, "mov qword ptr [rsp + 0x18], rbx", None,
     "50FA50 UI update: run the layout color and alpha fade helper once per stock menu "
     "tick so its byte steps and truncation retain stock order"),
    # 5C4B00 is the scene-update callback installed by 5C5040 via 48C8E0.
    # Each listed scalar is a movement amount used in one callback tick. The
    # event branches at 5C4F5C are left to execute at their normal cadence.
    ("actor", "lin", 0x5C4B2D, "movss xmm6, dword ptr [rip + 0xb4e7f]", (0x6799B4, 4.0),
     "e80/e82/e83 horizontal and vertical scalar movement, held in xmm6 until 5C4D26"),
    ("actor", "lin", 0x5C4B58, "subss xmm0, dword ptr [rip + 0xb0f28]", (0x675A88, 14.0),
     "e80 vertical step of 14"),
    ("actor", "lin", 0x5C4B85, "addss xmm0, dword ptr [rip + 0xb03cf]", (0x674F5C, 7.0),
     "e81 horizontal step of 7"),
    ("actor", "lin", 0x5C4B94, "addss xmm1, dword ptr [rip + 0xad278]", (0x671E14, 2.0),
     "e81 secondary step of 2"),
    ("actor", "lin", 0x5C4BB1, "subss xmm0, dword ptr [rip + 0xb03a7]", (0x674F60, 8.0),
     "e81 vertical step of 8"),
    ("actor", "lin", 0x5C4BC7, "movss xmm7, dword ptr [rip + 0xad039]", (0x671C08, 1.0),
     "e82/e83/e85/e89 vertical step of 1, held in xmm7 until 5C4D9A"),
    ("actor", "lin", 0x5C4C2B, "movss xmm1, dword ptr [rip + 0xad1e1]", (0x671E14, 2.0),
     "e84/e88 scalar movement of 2"),
    ("actor", "lin", 0x5C4C81, "subss xmm0, dword ptr [rip + 0xb02d7]", (0x674F60, 8.0),
     "e85 vertical step of 8"),
    ("actor", "lin", 0x5C4CAE, "movss xmm1, dword ptr [rip + 0xad15e]", (0x671E14, 2.0),
     "e86/e87 scalar movement of 2"),
    ("actor", "lin", 0x5C4CCF, "subss xmm0, dword ptr [rip + 0xb0289]", (0x674F60, 8.0),
     "e86/e87 vertical step of 8"),
    ("actor", "lin", 0x5C4CEC, "movss xmm1, dword ptr [rip + 0xad114]", (0x671E08, 0.5),
     "e89 scalar movement of 0.5"),
    ("actor", "lin", 0x5C4D26, "movss xmm6, dword ptr [rip + 0xb022a]", (0x674F58, 3.0),
     "e8a scalar movement of 3, held in xmm6"),
    ("actor", "lin", 0x5C4D63, "movss xmm1, dword ptr [rip + 0xb0cc5]",
     (0x675A30, 0.30000001192092896),
     "e8b scalar movement of 0.3"),
    ("actor", "lin", 0x5C4D84, "subss xmm0, dword ptr [rip + 0xb0cb8]", (0x675A44, 1.5),
     "e8b vertical step of 1.5"),
    ("actor", "lin", 0x5C4D9A, "movss xmm7, dword ptr [rip + 0xb0632]", (0x6753D4, 2.5),
     "e8c/e8e scalar movement of 2.5, held in xmm7"),
    ("actor", "lin", 0x5C4DC5, "subss xmm0, dword ptr [rip + 0xadb6b]", (0x672938, 11.0),
     "e8c vertical step of 11"),
    ("actor", "lin", 0x5C4DE2, "movss xmm1, dword ptr [rip + 0xb0c8e]", (0x675A78, 5.0),
     "e8d scalar movement of 5"),
    ("actor", "lin", 0x5C4E03, "subss xmm0, dword ptr [rip + 0xb3219]", (0x678024, 9.0),
     "e8d vertical step of 9"),
    ("actor", "lin", 0x5C4E19, "movss xmm6, dword ptr [rip + 0xb0c5b]", (0x675A7C, 6.0),
     "e8e/e8f scalar movement of 6, held in xmm6"),
    ("actor", "lin", 0x5C4E7E, "subss xmm0, dword ptr [rip + 0xb0bfe]", (0x675A84, 12.0),
     "e8f vertical step of 12"),
    ("actor", "lin", 0x5C4EA0, "movss xmm1, dword ptr [rip + 0xada84]",
     (0x67292C, 0.20000000298023224),
     "e90 scalar movement of 0.2"),
    ("actor", "lin", 0x5C4EC1, "subss xmm0, dword ptr [rip + 0xacf43]",
     (0x671E0C, 0.6000000238418579),
     "e90 vertical step of 0.6"),
    ("actor", "lin", 0x5C4EDE, "movss xmm1, dword ptr [rip + 0xb0ba2]", (0x675A88, 14.0),
     "e91 scalar movement of 14"),
    ("actor", "lin", 0x5C4EFF, "subss xmm0, dword ptr [rip + 0xadfd1]", (0x672ED8, 10.0),
     "e91 vertical step of 10"),
    ("actor", "lin", 0x5C4F1B, "addss xmm0, dword ptr [rip + 0xb0039]", (0x674F5C, 7.0),
     "e81 horizontal step of 7 in the alternative scene mode"),
    ("actor", "lin", 0x5C4F2B, "addss xmm1, dword ptr [rip + 0xacee1]", (0x671E14, 2.0),
     "e81 secondary step of 2 in the alternative scene mode"),
    ("actor", "lin", 0x5C4F4F, "subss xmm0, dword ptr [rip + 0xb0009]", (0x674F60, 8.0),
     "e81 vertical step of 8 in the alternative scene mode"),
    # utd7 231510 updates three scale components toward 1.6 in state one and
    # separately follows indexed position targets with three coordinates.
    ("objects", "blend", 0x2315C5, "movss xmm2, dword ptr [rip + 0x44135f]",
     (0x67292C, 0.20000000298023224),
     "state-one D20/D24/D28 approaches use this same 0.2 factor only as the per-tick "
     "blend"),
    ("objects", "blend", 0x23164C, "movss xmm2, dword ptr [rip + 0x4443dc]",
     (0x675A30, 0.30000001192092896),
     "current position xyz approaches use this same 0.3 factor only as the per-tick "
     "blend"),
    # utd2 230760 derives every submodel angle increment and the +1070 sine
    # phase from fVar6, selected solely from +E35: 1, 5, or 0 per update.
    ("objects", "lin", 0x2307CA, "movss xmm7, dword ptr [rip + 0x441436]", (0x671C08, 1.0),
     "normal-state per-tick phase speed 1 held in xmm7 for all five submodel angles "
     "and +1070"),
    ("objects", "lin", 0x2307D6, "movss xmm7, dword ptr [rip + 0x44529a]", (0x675A78, 5.0),
     "state-one per-tick phase speed 5 held in xmm7 for the same paths"),
    ("objects", "lin", 0x52E4C1, "subss xmm0, dword ptr [rip + 0x14393b]",
     (0x671E04, 0.10000000149011612),
     "52E450 callback for variants 7/8 and motion EE8: scale the submodel zero Y "
     "decrement 0.1"),
    ("objects", "lin", 0x52E4E8, "subss xmm0, dword ptr [rip + 0x149100]",
     (0x6775F0, 0.05000000074505806),
     "same callback: scale the submodel one Y decrement 0.05"),
    ("objects", "lin", 0x52E520, "subss xmm0, dword ptr [rip + 0x1438dc]",
     (0x671E04, 0.10000000149011612),
     "variants 10 to 12 and motion EEB: scale the root Y decrement 0.1"),
    ("objects", "lin", 0x52E572, "subss xmm0, dword ptr [rip + 0x14b6f6]",
     (0x679C70, 0.07999999821186066),
     "variants 13 to 15 and motion EEC: scale the submodel zero Y decrement 0.08"),
    ("objects", "lin", 0x52E599, "subss xmm0, dword ptr [rip + 0x14edc7]",
     (0x67D368, 0.07000000029802322),
     "same callback: scale the submodel one Y decrement 0.07"),
    ("objects", "lin", 0x52E5D9, "movss xmm1, dword ptr [rip + 0x14b68f]",
     (0x679C70, 0.07999999821186066),
     "variants 17 to 19 and motion EED: scale the shared 0.08 source for submodels "
     "three and six"),
    ("objects", "pre", 0x2EAD28, "addss xmm2, dword ptr [rcx + 0xb4]", None,
     "et2e 2EAD00: scale xmm2 after max of 0.02 and 2.1 minus the caller target, "
     "immediately before adding it to persistent B4 phase"),
    ("objects", "pre", 0x62E117, "addss xmm0, dword ptr [rdi + 0x1174]", None,
     "et2f 62E0B0: scale the selected +1 or -0.2 change to +1174 before adding it, "
     "preserving the zero-to-one clamp"),
    ("objects", "src", 0x62E284, "addss xmm1, xmm9", None,
     "et2f 62E0B0: scale xmm9 only in the +1170 interpolation phase add, preserving "
     "its separate uses as reference value and endpoint threshold"),
    ("objects", "lin", 0x20A044, "movss xmm1, dword ptr [rip + 0x470108]",
     (0x67A154, 0.05999999865889549),
     "cKiType000 to cKiType003 shared update: scale the 0.06 D2C decrease, which can "
     "be applied twice when E79 low nibble is F"),
    ("objects", "lin", 0x2146CA, "addss xmm1, dword ptr [rip + 0x45d742]", (0x671E14, 2.0),
     "ut05 214690: scale the +2 change to the 10A8 state value before its zero "
     "threshold"),
    ("objects", "lin", 0x214753, "subss xmm1, dword ptr [rip + 0x45d6b9]", (0x671E14, 2.0),
     "ut05 214690: scale the -2 change to the 10A8 state value before its -12 "
     "threshold"),
    ("objects", "lin", 0x22BEAB, "movss xmm1, dword ptr [rip + 0x44dde5]",
     (0x679C98, -0.05000000074505806),
     "utbb 22BE90: scale the -0.05 D2C fade when 115A is set"),
    ("objects", "lin", 0x22BECB, "movss xmm1, dword ptr [rip + 0x44b71d]",
     (0x6775F0, 0.05000000074505806),
     "utbb 22BE90: scale the +0.05 D2C fade when E35 selects phases one to three"),
    ("objects", "lin", 0x2E109C, "addss xmm0, dword ptr [rip + 0x3a1720]",
     (0x6827C4, 0.5585053563117981),
     "cTubomi et40/44/45 2E0FE0: scale the 0.5585054 angular step before the "
     "submodel-three E4 wrap"),
    ("objects", "lin", 0x22619F, "subss xmm0, dword ptr [rip + 0x453a89]",
     (0x679C30, 0.019999999552965164),
     "ut86 225F90 state eight: scale the 0.02 D2C fade before its zero transition"),
    ("objects", "lin", 0x228190, "movss xmm1, dword ptr [rip + 0x44f458]",
     (0x6775F0, 0.05000000074505806),
     "ut92 228170: scale the 0.05 per-subrecord 5C decrease shared across the loop, "
     "preserving the zero clamp"),
    ("objects", "pre", 0x2E8484, "addss xmm0, dword ptr [rbx + 0x1084]", None,
     "et24 2E83E0: scale xmm0 after random value times 0.02 plus 0.05, before adding "
     "that whole per-tick phase step to persistent 1084"),
    ("objects", "lin", 0x2ED800, "addss xmm0, dword ptr [rip + 0x394fbc]",
     (0x6827C4, 0.5585053563117981),
     "et44 2ED7E0: scale the submodel-three E4 angular step 0.5585054 before wrapping"),
    ("objects", "lin", 0x2ED8D0, "addss xmm0, dword ptr [rip + 0x394eec]",
     (0x6827C4, 0.5585053563117981),
     "et45 2ED8B0: scale the sibling submodel-three E4 angular step 0.5585054 before "
     "wrapping"),
    ("objects", "lin", 0x23046F, "movss xmm7, dword ptr [rip + 0x44d211]",
     (0x67D688, 0.012217304669320583),
     "utd1 230400: scale the 0.0122173 return-to-zero step shared by four B4 angles "
     "after each is clamped to plus or minus 0.3"),
    # These sub-screen handlers use the menu's stock 60 Hz cadence.
    ("menu", "count", 0x6013CB, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the +1B wait after 5FFF10 until 80 ticks or the user's advance "
     "input"),
    ("menu", "count", 0x601440, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the next +1B wait until 80 ticks or advance input"),
    ("menu", "count", 0x6014E4, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the third +1B wait until 80 ticks or advance input"),
    ("menu", "count", 0x601588, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the fourth +1B wait until 80 ticks or advance input"),
    ("menu", "count", 0x6015F1, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the +1B twenty-tick delay in state twelve"),
    ("menu", "count", 0x601644, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the +1B fifty-tick wait or advance input"),
    ("menu", "count", 0x6016DA, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the next +1B fifty-tick wait or advance input"),
    ("menu", "count", 0x60173B, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the +1B twenty-tick delay before the next message"),
    ("menu", "count", 0x60178C, "inc byte ptr [rbx + 0x1b]", None,
     "601270: pace the final +1B eighty-tick wait or advance input"),
    ("menu", "lin", 0x606B1B, "addss xmm0, dword ptr [rip + 0xb690d]",
     (0x6BD430, 19.66666603088379),
     "606A80 state three: scale the 19.66667 Y slide step during the three-tick page "
     "transition"),
    ("menu", "count", 0x606B28, "inc byte ptr [rdi + 4]", None,
     "same transition: pace the +4 count until three updates and the reset to state "
     "one"),
    ("menu", "lin", 0x606B99, "subss xmm0, dword ptr [rip + 0xb688f]",
     (0x6BD430, 19.66666603088379),
     "606A80 state two: scale the opposing 19.66667 Y slide step"),
    ("menu", "count", 0x606BA6, "inc byte ptr [rdi + 4]", None,
     "same transition: pace the +4 count until three updates and the reset to state "
     "one"),
    # Gate the stored timer where its old register is the comparison operand.
    # None is the existing audited memory-store count form; register computations
    # and old-value comparisons remain intact on held ticks.
    ("menu", "count", 0x6074B0, "mov byte ptr [rbx + 7], al", None,
     "607360 page transition: +7 advances for sixteen stock ticks; 6074B3 compares the "
     "old DL to fifteen and EAX is overwritten before any subsequent use"),
    ("menu", "count", 0x601E89, "mov dword ptr [rdi + 0x60], ecx", None,
     "601D50 grow-in: +60 advances the sine phase up to ninety; the phase is read "
     "before increment and ECX is replaced with 128 immediately after the store"),
    ("menu", "lin", 0x601E7E, "mulss xmm2, dword ptr [rip + 0x77e16]",
     (0x679C9C, 1.2999999523162842),
     "601D50 grow-in: scale the shared sine-dependent 1.3 decrement used for both +2C "
     "and +30 layout scales"),
    ("menu", "count", 0x601EAD, "add byte ptr [rdi + 0x5c], 0x15", None,
     "601D50 grow-in: alpha +5C advances by twenty-one up to 128; the following "
     "compare reloads and clamps the held field"),
    ("menu", "count", 0x601F34, "mov word ptr [rdi + 0x18], ax", None,
     "601D50 controller wait: pace +18's 452-update timeout; the threshold comparison "
     "uses the unchanged old CX"),
    ("menu", "count", 0x50C41D, "mov byte ptr [rdi + 1], cl", None,
     "50C350 state three: pace +1's sixteen-update slide; layout X is recomputed from "
     "the old timer and the completion test compares old DL"),
    ("menu", "count", 0x50C4C8, "mov byte ptr [rdi + 1], al", None,
     "50C350 state two: pace the matching slide timer; completion compares the old CL "
     "and the calculated EAX is discarded"),
    ("menu", "count", 0x50FA6F, "sub al, 1",
     (0x50FA67,0x50FA71,(0x50FA67,0x50FA6B,0x50FA6D,0x50FA6F),None),
     "50FA50 prompt delay: decrement +38 on stock ticks, synthesizing not-finished "
     "flags for the 50FA74 branch so 50FD40 runs once on completion"),
    ("objects", "count", 0x2315E2, "mov word ptr [rbx + 0xe3c], ax", None,
     "utd7 231510: pace the +E3C sixty-tick shrink timeout; the old CX is retained for "
     "the later completion test and the computed EAX is discarded"),
    ("menu", "count", 0x1D34F5, "inc dword ptr [rbx + 0x1c]", None,
     "1D34A0 texture command state three: +1C waits thirty stock updates before "
     "returning completion"),
    ("menu", "count", 0x1D35DC, "dec r8d", (0x1D35D8,0x1D35DF,(0x1D35D8,0x1D35DC),None),
     "1D34A0 texture crossfade: decrement the +1C timer in R8D before the alpha "
     "divisions; held ticks keep both the field and derived opacity at the old count"),
    ("menu", "count", 0x13BE27, "dec ecx",
     (0x13BE20,0x13BE29,(0x13BE20,0x13BE23,0x13BE25,0x13BE27),None),
     "13BE10 input slot delay: pace each of the three positive +14 countdowns before "
     "the state checks"),
    ("effect", "count", 0x19144F, "inc byte ptr [rcx + 0x277]", None,
     "191440 particle fade lifetime: +277 advances until the +276 threshold, then "
     "calls virtual slot seven to end the particle"),
    ("objects", "gatefn", 0x20AE00, "mov rax, rsp", None,
     "shared detached submodel debris: preserve the whole stock recurrence for "
     "position plus velocity, 0.98 horizontal drag, 0.4 gravity, rotation, collision "
     "bounce, sixty-tick flight and ninety-tick rest; its three void callers ignore "
     "RAX and its body contains no other paced patch"),
    ("objects", "blend", 0x35CDCC, "mulss xmm1, dword ptr [rip + 0x31a81c]",
     (0x6775F0, 0.05000000074505806),
     "objScroll 35CC30 state three: D2C approaches one by five percent per stock tick, "
     "then snaps at 0.98"),
    ("objects", "blend", 0x35CE40, "movss xmm2, dword ptr [rip + 0x31a7a8]",
     (0x6775F0, 0.05000000074505806),
     "objScroll 35CC30 state five: the three D20/D24/D28 scale components share the "
     "five-percent approach factor"),
    ("objects", "pre", 0x2290CE, "addss xmm1, dword ptr [rdi + 0x1190]", None,
     "ut96 229060: scale the complete step returned by 229520 before adding it to "
     "persistent +1190; this helper sums nearby positive volume contributions and "
     "negative hazard contributions"),
    ("objects", "lin", 0x2290ED, "mulss xmm0, dword ptr [rip + 0x453ea7]",
     (0x67CF9C, -0.0010000000474974513),
     "ut96 229060: scale the separate C0-dependent negative 0.001 step when flag +1010 "
     "bit fourteen is set, before the final clamp to 0.5 through 3"),
    ("menu", "count", 0x1C8CBC, "sub al, 1",
     (0x1C8CB5,0x1C8CBE,(0x1C8CB5,0x1C8CB8,0x1C8CBA,0x1C8CBC),None),
     "1C8C90 message manager: pace the four positive delayed-release counters and "
     "synthesize not-finished flags before 3EB870 releases the resource"),
    ("menu", "count", 0x1D0311, "mov word ptr [rdi + 0x46], ax", None,
     "1D0240 message state dispatcher: hold the +46 input delay store between stock "
     "ticks; AX is discarded after it, with consumers reading the stored field on the "
     "next invocation"),
    ("menu", "count", 0x1D039A, "inc byte ptr [rbx + 0xee]", None,
     "1D0350 message advance wait: pace the +EE visual wait phase while processing "
     "advance input on every update"),
    ("menu", "count", 0x1D2B42, "mov word ptr [rcx + 0x52], ax", None,
     "1D2B10 message bytecode wait: gate the positive +52 delay decrement store while "
     "the function continues returning one until the stored field reaches zero"),
    ("objects", "blend", 0x561819, "mulss xmm0, dword ptr [rip + 0x115dcf]",
     (0x6775F0, 0.05000000074505806),
     "uta4 5616C0 active hover: +D2C alpha approaches .6 by five percent per stock "
     "update"),
    ("objects", "count", 0x561835, "mov word ptr [rdi + 0x1110], ax", None,
     "uta4 5616C0: gate the positive +1110 cooldown decrement store; computed AX is "
     "discarded and the transition reads the stored field"),
    ("objects", "count", 0x561862, "mov word ptr [rdi + 0xe40], r8w", None,
     "uta4 5616C0: hold the +E40 oscillator phase store between stock ticks; quotient "
     "and sine inputs use the old phase and the incremented R8W is discarded"),
    ("objects", "count", 0x561A35, "mov word ptr [rdi + 0x1112], ax", None,
     "uta4 5616C0: hold the positive +1112 cooldown decrement store; subsequent logic "
     "reloads the field"),
    ("objects", "count", 0x561A58, "mov word ptr [rdi + 0x1112], ax", None,
     "uta4 5616C0: the extra flag-dependent +1112 decrement is a second stock-tick "
     "step; computed AX is discarded before the distance test"),
    ("objects", "count", 0x561C45, "mov word ptr [rdi + 0xe40], r8w", None,
     "uta4 561A90 state one: hold the +E40 phase store while the sine-position "
     "calculation continues using the old phase"),
    ("objects", "blend", 0x561C2F, "mulss xmm1, dword ptr [rip + 0x1159b9]",
     (0x6775F0, 0.05000000074505806),
     "uta4 561A90 state one: +D2C approaches .6 by five percent per stock update"),
    ("objects", "count", 0x561D93, "mov word ptr [rdi + 0xe40], r8w", None,
     "uta4 561A90 state three: hold the +E40 phase store while the sine-position "
     "calculation continues using the old phase"),
    ("objects", "blend", 0x561D7D, "mulss xmm1, dword ptr [rip + 0x11586b]",
     (0x6775F0, 0.05000000074505806),
     "uta4 561A90 state three: +D2C approaches .6 by five percent per stock update"),
    ("objects", "count", 0x561EE1, "mov word ptr [rdi + 0xe40], r8w", None,
     "uta4 561A90 state five: hold the +E40 phase store while the sine-position "
     "calculation continues using the old phase"),
    ("objects", "blend", 0x561ECB, "mulss xmm1, dword ptr [rip + 0x11571d]",
     (0x6775F0, 0.05000000074505806),
     "uta4 561A90 state five: +D2C approaches .6 by five percent per stock update"),
    ("menu", "count", 0x1C8F57, "sub al, 1",
     (0x1C8F50,0x1C8F59,(0x1C8F50,0x1C8F53,0x1C8F55,0x1C8F57),None),
     "1C8F30 message manager: pace four delayed-release counters, synthesizing "
     "not-finished flags before freeing the resource on zero"),
    ("menu", "count", 0x1D391F, "inc dword ptr [rcx + 0x1c]", None,
     "1D3910 message-command pause: +1C counts forty-five updates then +57 becomes FF; "
     "pace the counter while completion reads its stored value"),
    ("menu", "count", 0x43C6FF, "dec byte ptr [rcx + 0x8c]", None,
     "43C6F0 menu dispatcher: pace the +8C notification delay while leaving input "
     "handling on every update"),
    ("menu", "notyet", 0x43C70F, "cmp al, 1", 0x43C752,
     "43C6F0: suppress the +8C-equals-one notification between stock ticks so holding "
     "the delay cannot repeat its sound"),
    ("menu", "count", 0x43FA9A, "dec byte ptr [rcx + 0x8c]", None,
     "43FA90 menu dispatcher: pace the +8C notification delay while leaving input "
     "handling on every update"),
    ("menu", "notyet", 0x43FAAA, "cmp cl, 1", 0x43FAFB,
     "43FA90: suppress the +8C-equals-one notification between stock ticks so holding "
     "the delay cannot repeat its sound"),
    ("menu", "count", 0x3D8ED7, "dec al",
     (0x3D8ECA,0x3D8ED9,(0x3D8ECA,0x3D8ECE,0x3D8ED3,0x3D8ED5,0x3D8ED7),None),
     "3D8EB0 camera controller: pace the positive four-tick +7 hold delay and keep all "
     "flag and input processing on every update"),
    ("actor", "count", 0x1DC143, "mov word ptr [rcx + 0x1184], ax", None,
     "1DC130: pace +1184's positive countdown; its zero event immediately reloads nine "
     "hundred stock ticks"),
    ("actor", "count", 0x1EC992, "mov dword ptr [rcx + 0x1170], eax", None,
     "1EC980: hold the +1170 random-target delay store; the event tests the old EDX "
     "and reloads the field after drawing a new target"),
    ("actor", "notyet", 0x1EC998, "test edx, edx", 0x1ECA9B,
     "1EC980: allow the random-target event only on stock ticks, including the "
     "old-counter-equals-zero call after the last decrement"),
    ("actor", "count", 0x2030D1, "mov dword ptr [rcx + 0x1170], eax", None,
     "2030B0: hold the +1170 random-target delay store while preserving its old EDX "
     "event test"),
    ("actor", "notyet", 0x2030D7, "test edx, edx", 0x20314C,
     "2030B0: gate the old-counter-zero event with its countdown so target selection "
     "and RNG draws have exact stock cadence"),
    ("actor", "count", 0x203190, "mov dword ptr [rbx + 0x1170], edx", None,
     "203160: hold the +1170 random-target delay store while preserving its old R9D "
     "event test"),
    ("actor", "notyet", 0x203196, "test r9d, r9d", 0x203217,
     "203160: gate the old-counter-zero event with its countdown so target selection "
     "and RNG draws have exact stock cadence"),
    ("actor", "count", 0x203896, "inc word ptr [rcx + 0x1228]", None,
     "203890: pace the +1228 three-update particle-spawn period; the event reloads "
     "zero immediately so a held phase cannot repeat it"),
    ("actor", "count", 0x203C7A, "inc byte ptr [rcx + 0x11b3]", None,
     "203C70: pace the +11B3 three-update particle-spawn period; the event reloads "
     "zero immediately so a held phase cannot repeat it"),
    ("objects", "count", 0x3DD22A, "mov byte ptr [rbx + 1], al", None,
     "objScroll 3DD070 outer band: gate this persistent byte-green interpolation store "
     "to preserve quantized stock progression; computed AL is discarded before the "
     "independent red component"),
    ("objects", "count", 0x3DD24C, "mov byte ptr [rbx], al", None,
     "objScroll 3DD070 outer band: gate this persistent byte-red interpolation store; "
     "computed AL is discarded before the independent blue component"),
    ("objects", "count", 0x3DD26A, "mov byte ptr [rbx + 2], al", None,
     "objScroll 3DD070 outer band: gate this persistent byte-blue interpolation store; "
     "computed AL is discarded before the radial band test"),
    ("objects", "count", 0x3DD2A8, "mov byte ptr [rbx + 1], al", None,
     "objScroll 3DD070 inner band: gate this persistent byte-green fade store to "
     "preserve quantized stock progression; computed AL is discarded before the "
     "independent red component"),
    ("objects", "count", 0x3DD2C9, "mov byte ptr [rbx], al", None,
     "objScroll 3DD070 inner band: gate this persistent byte-red fade store; computed "
     "AL is discarded before the independent blue component"),
    ("objects", "count", 0x3DD2E7, "mov byte ptr [rbx + 2], al", None,
     "objScroll 3DD070 inner band: gate this persistent byte-blue fade store; computed "
     "AL is discarded before the radial band test"),
    ("objects", "count", 0x3DDD77, "mov byte ptr [rbx + 1], al", None,
     "3DDBC0 outer band: gate the persistent byte-green interpolation store; computed "
     "AL is discarded before the independent red component"),
    ("objects", "count", 0x3DDD99, "mov byte ptr [rbx], al", None,
     "3DDBC0 outer band: gate the persistent byte-red interpolation store; computed AL "
     "is discarded before the independent blue component"),
    ("objects", "count", 0x3DDDB7, "mov byte ptr [rbx + 2], al", None,
     "3DDBC0 outer band: gate the persistent byte-blue interpolation store; computed "
     "AL is discarded before the radial band test"),
    ("objects", "count", 0x3DDDF5, "mov byte ptr [rbx + 1], al", None,
     "3DDBC0 inner band: gate the persistent byte-green fade store; computed AL is "
     "discarded before the independent red component"),
    ("objects", "count", 0x3DDE16, "mov byte ptr [rbx], al", None,
     "3DDBC0 inner band: gate the persistent byte-red fade store; computed AL is "
     "discarded before the independent blue component"),
    ("objects", "count", 0x3DDE34, "mov byte ptr [rbx + 2], al", None,
     "3DDBC0 inner band: gate the persistent byte-blue fade store; computed AL is "
     "discarded before the radial band test"),
    ("menu", "count", 0x426386, "inc byte ptr [r10 + 0x1ae]", None,
     "426310 asynchronous menu fade: +1AE advances a six-update alpha phase, derived "
     "from the stored phase and fixed endpoints, then marks +1AD inactive on "
     "completion"),
    ("menu", "gatefn", 0x48BEB0, "push rbx", None,
     "48BEB0: stock-cadence void startup helper keeps its eight-update wait and "
     "load-completion event together; the only caller ignores RAX and the body "
     "has no other paced steps"),
    ("actor", "count", 0x4893C8, "dec ax",
     (0x4893C0,0x4893CB,(0x4893C0,0x4893C3,0x4893C6,0x4893C8),None),
     "4893C0 transition dispatcher: pace the positive startup hold counter while "
     "preserving event and input processing on every update"),
    ("actor", "count", 0x48FFD4, "inc byte ptr [rcx + 0x155]", None,
     "48FFD0: pace the nine-update particle period; completion immediately resets +155 "
     "to zero, preventing repeated spawn events on held ticks"),
    ("actor", "count", 0x5F6729, "inc dword ptr [rbx + 0x107c]", None,
     "et9f 5F6690: pace the thirty-one-update inactive-player delay before spawning "
     "its once-latched +1078 effect; copying the player's model remains on every "
     "update"),
    ("actor", "count", 0x5FC892, "mov byte ptr [rbx + 0x1088], al", None,
     "ut9c 5FC850: hold the positive +1088 cooldown decrement store; computed AL is "
     "discarded and subsequent logic reads the stored field"),
    ("actor", "count", 0x651767, "mov byte ptr [rcx + 0x11aa], al", None,
     "ut35 651750: hold the +11AA countdown store for the +11AC high-bit delay; "
     "completion tests the old DL"),
    ("actor", "notyet", 0x65176D, "test dl, dl", 0x65179E,
     "ut35 651750: clear the +11AC high bit only on a stock tick, including the "
     "old-count-negative invocation after the last decrement"),
    ("actor", "count", 0x6521BD, "dec byte ptr [rdi + 0x11b0]", None,
     "ut35 652160: pace the +11B0 scripted motion-change delay while keeping "
     "attachment matrix copies and input processing on every update"),
    ("actor", "notyet", 0x6521C3, "cmp byte ptr [rdi + 0x11b0], 0x48", 0x6521F0,
     "ut35 652160: fire the seventy-two-remaining motion-change event only on stock "
     "ticks so a held delay cannot restart the motion repeatedly"),
    ("actor", "notyet", 0x6521F0, "cmp byte ptr [rdi + 0x11b0], 0x39", 0x65221D,
     "ut35 652160: fire the fifty-seven-remaining motion-change event only on stock "
     "ticks so a held delay cannot restart the motion repeatedly"),
    ("actor", "count", 0x443E44, "mov word ptr [rbx + 0x37c], ax", None,
     "443DF0 sound-volume dispatcher: hold the positive +37C start delay while the "
     "waiting branch continues returning before sound start"),
    ("actor", "count", 0x444301, "mov dword ptr [rbx + 0x398], eax", None,
     "4442A0 sound-volume dispatcher: hold the positive +398 sixty-update stop delay; "
     "computed EAX is discarded and the stored delay is tested on the next invocation"),
    ("actor", "count", 0x444559, "mov dword ptr [rbx + 0x398], eax", None,
     "444450 sound-volume dispatcher: pace the shared +398 reload/decrement store; "
     "completion consumes the previous field before this store and computed EAX is "
     "discarded by 4516E0"),
    ("actor", "count", 0x444714, "mov dword ptr [rbx + 0x398], eax", None,
     "444650 sound-volume dispatcher: hold the positive +398 sixty-update stop delay; "
     "computed EAX is discarded and the stored delay is tested on the next invocation"),
    ("menu", "srcx", 0x448A74, "subss xmm0, dword ptr [rdx + 0xb04]", None,
     "4487E0 audio mixer: scale the negative +B04 approach step for +AAC before its "
     "target clamp, preserving the stored stock-unit rate"),
    ("menu", "srcx", 0x448A81, "addss xmm0, dword ptr [rdx + 0xb04]", None,
     "4487E0 audio mixer: scale the positive +B04 approach step for +AAC before its "
     "target clamp"),
    ("menu", "srcx", 0x448ABA, "subss xmm0, dword ptr [rdx + 0xb08]", None,
     "4487E0 audio mixer: scale the negative +B08 approach step for +AB0 before its "
     "target clamp"),
    ("menu", "srcx", 0x448AC7, "addss xmm0, dword ptr [rdx + 0xb08]", None,
     "4487E0 audio mixer: scale the positive +B08 approach step for +AB0 before its "
     "target clamp"),
    ("menu", "srcx", 0x448B00, "subss xmm0, dword ptr [rdx + 0xb0c]", None,
     "4487E0 audio mixer: scale the negative +B0C approach step for +AB4 before its "
     "target clamp"),
    ("menu", "srcx", 0x448B0D, "addss xmm0, dword ptr [rdx + 0xb0c]", None,
     "4487E0 audio mixer: scale the positive +B0C approach step for +AB4 before its "
     "target clamp"),
    ("menu", "srcx", 0x448B46, "subss xmm0, dword ptr [rdx + 0xb10]", None,
     "4487E0 audio mixer: scale the negative +B10 approach step for +AB8 before its "
     "target clamp"),
    ("menu", "srcx", 0x448B53, "addss xmm0, dword ptr [rdx + 0xb10]", None,
     "4487E0 audio mixer: scale the positive +B10 approach step for +AB8 before its "
     "target clamp"),
    ("menu", "srcx", 0x448B8C, "subss xmm0, dword ptr [rdx + 0xb14]", None,
     "4487E0 audio mixer: scale the negative +B14 approach step for +ABC before its "
     "target clamp"),
    ("menu", "srcx", 0x448B99, "addss xmm0, dword ptr [rdx + 0xb14]", None,
     "4487E0 audio mixer: scale the positive +B14 approach step for +ABC before its "
     "target clamp"),
    ("menu", "srcx", 0x448BD2, "subss xmm0, dword ptr [rdx + 0xb18]", None,
     "4487E0 audio mixer: scale the negative +B18 approach step for +AC0 before its "
     "target clamp"),
    ("menu", "srcx", 0x448BDF, "addss xmm0, dword ptr [rdx + 0xb18]", None,
     "4487E0 audio mixer: scale the positive +B18 approach step for +AC0 before its "
     "target clamp"),
    ("menu", "srcx", 0x448C18, "subss xmm0, dword ptr [rdx + 0xb1c]", None,
     "4487E0 audio mixer: scale the negative +B1C approach step for +AC4 before its "
     "target clamp"),
    ("menu", "srcx", 0x448C25, "addss xmm0, dword ptr [rdx + 0xb1c]", None,
     "4487E0 audio mixer: scale the positive +B1C approach step for +AC4 before its "
     "target clamp"),
    ("menu", "srcx", 0x448C5E, "subss xmm0, dword ptr [rdx + 0xb20]", None,
     "4487E0 audio mixer: scale the negative +B20 approach step for +AC8 before its "
     "target clamp"),
    ("menu", "srcx", 0x448C6B, "addss xmm0, dword ptr [rdx + 0xb20]", None,
     "4487E0 audio mixer: scale the positive +B20 approach step for +AC8 before its "
     "target clamp"),
    ("menu", "srcx", 0x448CA9, "subss xmm0, dword ptr [rdx + 0x58]", None,
     "4487E0 audio mixer: scale the negative +58 approach step in the three-lane +ACC "
     "loop before its target clamp"),
    ("menu", "srcx", 0x448CB3, "addss xmm0, dword ptr [rdx + 0x58]", None,
     "4487E0 audio mixer: scale the positive +58 approach step in the three-lane +ACC "
     "loop before its target clamp"),
    ("menu", "gatefn", 0x451A30, "push rbx", None,
     "451A30 audio-channel update: keep the coupled remaining-update divisor, "
     "remaining count, pan approaches, start delay and lifecycle callbacks at exact "
     "stock cadence; both callers discard RAX and its body has no paced sites"),
    ("menu", "pre", 0x160E75, "addss xmm0, dword ptr [r15 + 0x30]", None,
     "160D80 gallery: scale the complete signed analog zoom step after input shaping "
     "and division, before adding old +30 and clamping to one through 2.5"),
    ("menu", "lin", 0x1610CF, "mulss xmm6, dword ptr [rip + 0x5142f9]", (0x6753D0, 0.03125),
     "160D80 gallery: scale the shared signed horizontal scroll rate once before zoom "
     "compensation and its seven layout accumulations"),
    ("menu", "lin", 0x1610D7, "mulss xmm7, dword ptr [rip + 0x5142f1]", (0x6753D0, 0.03125),
     "160D80 gallery: scale the independent image-pan rate before adding old +20"),
    ("menu", "pre", 0x1616EF, "addss xmm8, dword ptr [r15 + 0x24]", None,
     "160D80 gallery: scale the complete vertical analog/button pan step before adding "
     "old +24 and applying the zoom-dependent bounds"),
    ("menu", "count", 0x456A42, "dec word ptr [rbx + 0x32]", None,
     "4569F0 scripted scene wait state one: pace the +32 timeout while the external "
     "readiness condition is still checked on every update"),
    ("menu", "count", 0x456A8A, "dec word ptr [rbx + 0x32]", None,
     "4569F0 scripted scene wait state two: pace the +32 timeout while the external "
     "readiness condition is still checked on every update"),
    ("menu", "count", 0x456BB3, "sub word ptr [rbx + 0x32], 1", None,
     "4569F0 scripted scene wait state five: pace the +32 transition countdown and "
     "synthesize not-finished flags before its zero event changes the state"),
    ("menu", "count", 0x456C4A, "sub word ptr [rbx + 0x32], 1", None,
     "4569F0 scripted scene wait state six: pace the +32 transition countdown and "
     "synthesize not-finished flags before its zero event changes the state"),
    ("menu", "count", 0x456C9B, "sub word ptr [rbx + 0x30], 1", None,
     "4569F0 scripted scene wait state eight: pace the +30 transition countdown and "
     "synthesize not-finished sign flags before changing the state"),
    ("objects", "count", 0x22A754, "mov word ptr [rdi + 0x1152], ax", None,
     "ut9e 22A6C0: hold the positive +1152 cooldown decrement store; AX is discarded "
     "before loading the independent +1150 cooldown"),
    ("objects", "count", 0x22A76A, "mov word ptr [rdi + 0x1150], ax", None,
     "ut9e 22A6C0: hold the positive +1150 cooldown decrement store; AX is discarded "
     "before the state dispatcher"),
    ("objects", "count", 0x22FF34, "mov word ptr [rbx + 0x1200], ax", None,
     "utd1 22FE00: hold the positive +1200 turn cooldown decrement store; AX is "
     "discarded before the movement helper"),
    ("objects", "count", 0x234690, "sub ax, 1",
     (0x234680,0x234694,(0x234680,0x234687,0x23468A,0x234690),None),
     "utf2 234640: pace the positive +1120 countdown and synthesize not-finished flags "
     "so its zero event and scenario flag occur exactly once"),
    ("objects", "count", 0x23472A, "sub ax, 1",
     (0x23471A,0x23472E,(0x23471A,0x234721,0x234724,0x23472A),None),
     "utf2 234640: pace the positive +1122 countdown and synthesize not-finished flags "
     "before its zero event resets scale and scenario flag"),
    ("objects", "count", 0x235859, "mov byte ptr [rbx + 0xe76], cl", None,
     "utf6 235820: hold the positive +E76 collision cooldown decrement store; CL is "
     "not read after this store"),
    ("objects", "count", 0x23590B, "mov byte ptr [rbx + 0x111a], r8b", None,
     "utf6 235820: hold the +111A seven-update particle period store; quotient and "
     "completion use the old phase"),
    ("objects", "notyet", 0x235918, "cmp ecx, eax", 0x235969,
     "utf6 235820: fire the old-phase modulo-seven particle event only on a stock "
     "tick, preventing repeats while the phase is held"),
    ("objects", "gatefn", 0x632E90, "mov qword ptr [rsp + 0x18], rbx", None,
     "et30 632E90: stock-cadence void selection controller keeps parent +11EB wait, "
     "child 62FB60 cooldowns, random target selection and reservation resets together; "
     "its helpers perform selection rather than movement and caller 630480 ignores RAX"),
    ("objects", "lin", 0x22F43B, "mulss xmm1, dword ptr [rip + 0x44e15d]",
     (0x67D5A0, 0.0024999999441206455),
     "utcb 22F3F0: scale the negative submodel-one angular rate before subtracting its "
     "previous angle and wrapping"),
    ("objects", "lin", 0x22F479, "mulss xmm7, dword ptr [rip + 0x44940f]",
     (0x678890, 0.029999999329447746),
     "utcb 22F3F0: scale the negative submodel-two angular rate before subtracting its "
     "previous angle and wrapping"),
    ("objects", "lin", 0x22F497, "mulss xmm0, dword ptr [rip + 0x44e101]",
     (0x67D5A0, 0.0024999999441206455),
     "utcb 22F3F0: scale the positive submodel-one angular rate before adding its "
     "previous angle and wrapping"),
    ("objects", "lin", 0x22F4D1, "mulss xmm7, dword ptr [rip + 0x4493b7]",
     (0x678890, 0.029999999329447746),
     "utcb 22F3F0: scale the positive submodel-two angular rate before adding its "
     "previous angle and wrapping"),
    ("objects", "blend", 0x220213, "mulss xmm1, dword ptr [rip + 0x452711]",
     (0x67292C, 0.20000000298023224),
     "ut60 220180: alpha eases twenty percent toward the visibility target 0.3 or one"),
    ("objects", "blend", 0x220533, "mulss xmm1, dword ptr [rip + 0x4523f1]",
     (0x67292C, 0.20000000298023224),
     "ut61 2204A0: alpha eases twenty percent toward the visibility target 0.3 or one"),
    ("objects", "blend", 0x222B49, "movss xmm2, dword ptr [rip + 0x44f2b3]",
     (0x671E04, 0.10000000149011612),
     "ut66 222B30: shared ten-percent coefficient returns all three scale axes toward "
     "one after a hit"),
    ("objects", "blend", 0x2251C4, "mulss xmm1, dword ptr [rip + 0x44d760]",
     (0x67292C, 0.20000000298023224),
     "ut83 225140: alpha eases twenty percent toward 0.5 or one according to player "
     "height"),
    ("objects", "blend", 0x21B732, "mulss xmm1, dword ptr [rip + 0x45a2f6]",
     (0x675A30, 0.30000001192092896),
     "ut37 21B6B0: alpha eases thirty percent toward 0.2 or one according to "
     "visibility"),
    ("objects", "blend", 0x21B923, "mulss xmm6, dword ptr [rip + 0x457001]",
     (0x67292C, 0.20000000298023224),
     "ut37 21B760: submodel vertical offset eases twenty percent toward the player's "
     "relative height before fixed bounds"),
    ("objects", "blend", 0x229B5E, "mulss xmm1, dword ptr [rip + 0x44da8a]",
     (0x6775F0, 0.05000000074505806),
     "ut9a 229A20: alpha eases five percent toward the fixed no-ground target 0.1"),
    ("objects", "blend", 0x229B87, "mulss xmm1, dword ptr [rip + 0x448d9d]",
     (0x67292C, 0.20000000298023224),
     "ut9a 229A20: alpha eases twenty percent toward one when ground was found"),
    ("objects", "srcblend", 0x229BB8, "mulss xmm0, dword ptr [rip + 0x44824c]",
     ("block", 0x229BAF, 0x229BC6),
     "ut9a 229A20: vertical position eases sixty percent toward the higher ground "
     "target before the player-ground clamp"),
    ("objects", "srcblend", 0x229BC2, "mulss xmm0, xmm2", ("block", 0x229BAF, 0x229BC6),
     "ut9a 229A20: use a rooted copy of the ten-percent coefficient for downward "
     "vertical easing; preserve XMM2 because it also provided an alpha target earlier"),
    ("objects", "blend", 0x231C73, "movss xmm2, dword ptr [rip + 0x440189]",
     (0x671E04, 0.10000000149011612),
     "utd9 231A80: shared ten-percent coefficient returns all three scale axes toward "
     "one during the motion-completion state"),
    ("objects", "blend", 0x209C1C, "mulss xmm6, dword ptr [rip + 0x46be0c]",
     (0x675A30, 0.30000001192092896),
     "cKiType 209B70: alpha eases thirty percent toward one during its activation "
     "transition"),
    ("objects", "srcblend", 0x225C1E, "mulss xmm1, xmm0", None,
     "ut86 225B70: alpha eases twenty percent toward 0.2; root a copy of XMM0's "
     "coefficient to preserve the endpoint held in the same register"),
    ("objects", "blend", 0x225C37, "mulss xmm1, dword ptr [rip + 0x44cced]",
     (0x67292C, 0.20000000298023224),
     "ut86 225B70: alpha eases twenty percent toward one in the complementary "
     "visibility branch"),
    ("objects", "count", 0x225DF6, "mov byte ptr [rdi + 0x10f8], r8b", None,
     "ut86 225B70: pace the stored +10F8 seven-update particle phase; the completion "
     "quotient consumes the old phase"),
    ("objects", "notyet", 0x225E03, "cmp ecx, eax", 0x225E9F,
     "ut86 225B70: fire the old-phase modulo-seven particle event only on a stock "
     "tick, preventing repeats while the phase is held"),
    ("objects", "blend", 0x227464, "mulss xmm1, dword ptr [rip + 0x44b4c0]",
     (0x67292C, 0.20000000298023224),
     "ut8b 227340: alpha eases twenty percent toward one after both visibility tests "
     "succeed"),
    ("objects", "srcblend", 0x227489, "mulss xmm1, xmm0", None,
     "ut8b 227340: alpha eases twenty percent toward 0.2 after a visibility test "
     "fails; preserve the endpoint while rooting a copy of the coefficient"),
    ("objects", "count", 0x23792B, "mov byte ptr [rdi + 0xe76], cl", None,
     "utf7 2378F0: hold the positive collision cooldown store; the computed CL is "
     "discarded before the next state and alpha update"),
    ("objects", "blend", 0x2379BE, "mulss xmm1, dword ptr [rip + 0x43af66]",
     (0x67292C, 0.20000000298023224),
     "utf7 2378F0: alpha eases twenty percent toward 0.3 or one according to player "
     "height"),
    ("objects", "blend", 0x562378, "mulss xmm1, dword ptr [rip + 0x115270]",
     (0x6775F0, 0.05000000074505806),
     "uta5 562350: vertical position eases five percent toward ground height minus "
     "thirty before the original no-ground fallback"),
    ("objects", "blend", 0x562A28, "mulss xmm1, dword ptr [rip + 0x10fefc]",
     (0x67292C, 0.20000000298023224),
     "uta6 5628B0: alpha eases twenty percent toward the visibility endpoint selected "
     "by the two ray tests"),
    ("objects", "blend", 0x563BDC, "mulss xmm1, dword ptr [rip + 0x10ed48]",
     (0x67292C, 0.20000000298023224),
     "uta7 563A00: the paired ut9e object's alpha eases twenty percent toward 0.3 or "
     "one according to player height"),
    ("objects", "blend", 0x5707A2, "mulss xmm0, dword ptr [rip + 0x10165a]",
     (0x671E04, 0.10000000149011612),
     "utb7 570640: vertical position eases ten percent toward its already-paced sine "
     "phase and fixed ground offset"),
    ("objects", "blend", 0x57A85E, "mulss xmm1, dword ptr [rip + 0xfb1ca]",
     (0x675A30, 0.30000001192092896),
     "ut2b 57A800: alpha eases thirty percent toward zero or one selected by the "
     "camera-height test"),
    ("objects", "blend", 0x57DF2C, "mulss xmm1, dword ptr [rip + 0xf49f8]",
     (0x67292C, 0.20000000298023224),
     "ut33 57DDF0: alpha eases twenty percent toward the visibility endpoint selected "
     "by the two ray tests"),
    ("objects", "blend", 0x57F11D, "mulss xmm1, dword ptr [rip + 0xf3807]",
     (0x67292C, 0.20000000298023224),
     "ut48 57F030: alpha eases twenty percent toward the visibility endpoint selected "
     "by the two ray tests"),
    ("objects", "blend", 0x35D346, "movss xmm2, dword ptr [rip + 0x31a2a2]",
     (0x6775F0, 0.05000000074505806),
     "objScroll 35D0E0: shared five-percent coefficient returns all three scale axes "
     "toward one in state five"),
    ("objects", "blend", 0x35BD8F, "mulss xmm2, dword ptr [rip + 0x319c99]",
     (0x675A30, 0.30000001192092896),
     "objScroll 35B840: alpha eases thirty percent toward the distance-derived "
     "visibility target clamped above zero"),
    ("objects", "blend", 0x35BDB9, "mulss xmm1, dword ptr [rip + 0x319c6f]",
     (0x675A30, 0.30000001192092896),
     "objScroll 35B840: alpha eases thirty percent toward one in the complementary "
     "distance branch"),
    ("objects", "blend", 0x221120, "mulss xmm1, dword ptr [rip + 0x451804]",
     (0x67292C, 0.20000000298023224),
     "ut65 221070: alpha eases twenty percent toward 0.3 or one according to player "
     "height"),
    ("objects", "blend", 0x230EA5, "mulss xmm1, dword ptr [rip + 0x441a7f]",
     (0x67292C, 0.20000000298023224),
     "utd7 230E20: alpha eases twenty percent toward the ground-dependent +1624 "
     "endpoint, retaining the height test's endpoint scaling"),
    ("objects", "pre", 0x231437, "addss xmm0, dword ptr [rbx + 0xb4]", None,
     "utd7 231200: scale the complete clamped signed yaw step returned by 2DE0A0 "
     "before adding the old yaw and wrapping"),
    ("objects", "srcblend", 0x23146D, "mulss xmm0, dword ptr [rbx + 0x162c]", None,
     "utd7 231200: root a copy of the +162C easing factor for X, leaving its "
     "already-paced ramp in stock units"),
    ("objects", "srcblend", 0x231492, "mulss xmm1, dword ptr [rbx + 0x162c]", None,
     "utd7 231200: root a copy of the +162C easing factor for Y, leaving the ramp and "
     "other axes unchanged"),
    ("objects", "srcblend", 0x2314B9, "mulss xmm1, dword ptr [rbx + 0x162c]", None,
     "utd7 231200: root a copy of the +162C easing factor for Z, leaving the ramp in "
     "stock units"),
    ("objects", "blend", 0x5600CF, "mulss xmm0, dword ptr [rip + 0x111d2d]",
     (0x671E04, 0.10000000149011612),
     "uta4 55FFF0: ground height eases ten percent toward the higher of its ray result "
     "and the other object's height"),
    ("objects", "count", 0x5601BD, "inc byte ptr [rbx + 0x1114]", None,
     "uta4 55FFF0: pace the three-frame material flipbook index; every update still "
     "copies the held index into the four materials and the index wraps at three"),
    ("objects", "blend", 0x5608E9, "mulss xmm1, dword ptr [rip + 0x116cff]",
     (0x6775F0, 0.05000000074505806),
     "uta4 5607A0: alpha eases five percent toward 0.6 in state one"),
    ("objects", "count", 0x560905, "mov word ptr [rdi + 0x1110], ax", None,
     "uta4 5607A0: hold the positive +1110 cooldown decrement store; computed AX is "
     "discarded before the phase calculation"),
    ("objects", "blend", 0x560A95, "mulss xmm6, dword ptr [rip + 0x111fa3]",
     (0x672A40, 0.009999999776482582),
     "uta4 5607A0: X eases one percent toward the fixed placement X while outside the "
     "twenty-unit dead zone"),
    ("objects", "blend", 0x560AB9, "mulss xmm1, dword ptr [rip + 0x111f7f]",
     (0x672A40, 0.009999999776482582),
     "uta4 5607A0: Z eases one percent toward the fixed placement Z while outside the "
     "twenty-unit dead zone"),
    ("objects", "count", 0x560B4F, "mov word ptr [rdi + 0x1112], ax", None,
     "uta4 5607A0: hold the regular positive +1112 decrement store; AX is discarded "
     "before the external flag read"),
    ("objects", "count", 0x560B72, "mov word ptr [rdi + 0x1112], ax", None,
     "uta4 5607A0: hold the flag-dependent extra +1112 decrement store; later "
     "conditions reload the stored field"),
    ("objects", "blend", 0x56F4FB, "mulss xmm0, dword ptr [rip + 0x102901]",
     (0x671E04, 0.10000000149011612),
     "utb6 56F330: Y eases ten percent toward its already-paced sine phase plus the "
     "fixed ground offset"),
    ("objects", "pre", 0x56F5C3, "addss xmm0, dword ptr [rdi + 0xb0]", None,
     "utb6 56F330: scale the complete clamped signed pitch step before adding the old "
     "pitch and wrapping"),
    ("objects", "pre", 0x56F5E1, "addss xmm0, dword ptr [rdi + 0xb4]", None,
     "utb6 56F330: scale the complete clamped signed yaw step before adding the old "
     "yaw and wrapping"),
    ("objects", "srcblend", 0x56F697, "mulss xmm1, xmm6", None,
     "utb6 56F330: alpha eases twenty percent toward 0.4; copy XMM6's coefficient "
     "because it also supplies the stock motion-start rate"),
    ("objects", "srcblend", 0x56F6AE, "mulss xmm8, xmm6", None,
     "utb6 56F330: alpha eases twenty percent toward zero in the far-distance branch, "
     "retaining the shared stock-unit coefficient"),
    # Division easing: preserve stock DIVSS at N=1 and the source denominator.
    ("objects", "srcblend", 0x4BCA48, "divss xmm1, dword ptr [rip + 0x1b6488]", None,
     "sg00 4BC9F0: horizontal input angle approaches its target by one tenth per stock "
     "tick before rebuilding the model matrix"),
    ("objects", "srcblend", 0x4BCA68, "divss xmm2, dword ptr [rip + 0x1b6468]", None,
     "sg00 4BC9F0: vertical input angle approaches its target by one tenth per stock "
     "tick; fixed matrix offsets remain geometric"),
    ("objects", "srcblend", 0x4BCF1A, "divss xmm1, dword ptr [rip + 0x1b5fb6]", None,
     "sg00 4BCEB0: horizontal input angle eases by one tenth toward the half-input "
     "target"),
    ("objects", "srcblend", 0x4BCF3A, "divss xmm2, dword ptr [rip + 0x1b5f96]", None,
     "sg00 4BCEB0: vertical input angle eases by one tenth toward the 0.36-input "
     "target"),
    ("objects", "srcblend", 0x62F828, "divss xmm0, xmm2", None,
     "et2f 62F700: X approaches the selected target by one over the remaining stock "
     "ticks; use a rooted copy of the divisor, shared by XYZ"),
    ("objects", "srcblend", 0x62F845, "divss xmm1, xmm2", None,
     "et2f 62F700: Y uses the same remaining-ticks easing divisor as X"),
    ("objects", "srcblend", 0x62F864, "divss xmm1, xmm2", None,
     "et2f 62F700: Z uses the same remaining-ticks easing divisor as X"),
    ("objects", "count", 0x62F872, "sub word ptr [rbx + 0x1158], 1", "down",
     "et2f 62F700: remaining target-approach ticks at +1158 decrement after XYZ, with "
     "JNE completion and one E34 transition on expiry"),
    ("objects", "srcblend", 0x63236B, "divss xmm1, xmm0", None,
     "et30 632230: X approaches the selected target by one over remaining stock ticks "
     "at +11A4"),
    ("objects", "srcblend", 0x632396, "divss xmm2, xmm0", None,
     "et30 632230: Y uses the same remaining-ticks easing divisor as X"),
    ("objects", "srcblend", 0x6323C3, "divss xmm2, xmm0", None,
     "et30 632230: Z uses the same remaining-ticks easing divisor as X"),
    ("objects", "count", 0x6323D1, "sub word ptr [rdi + 0x11a4], 1", "down",
     "et30 632230: remaining target-approach ticks decrement after XYZ and change E34 "
     "out of this phase on expiry"),
    # Quantized vertex-color easing must execute the byte store at stock cadence.
    ("objects", "count", 0x3DD9D6, "mov byte ptr [rbx + 1], al", None,
     "objScroll 3DD830: byte green approaches 255 with a distance-derived coefficient; "
     "discard the computed AL before the next channel load"),
    ("objects", "count", 0x3DD9F7, "mov byte ptr [rbx], al", None,
     "objScroll 3DD830: byte red approaches zero with the same distance-derived "
     "coefficient; computed AL is discarded by the next channel load"),
    ("objects", "count", 0x3DDA15, "mov byte ptr [rbx + 2], al", None,
     "objScroll 3DD830: byte blue approaches zero with the same distance-derived "
     "coefficient; computed AL is not consumed after this store"),
    ("objects", "count", 0x3DDA50, "mov byte ptr [rbx + 3], al", None,
     "objScroll 3DD830: byte alpha approaches zero in the inner distance band; "
     "computed AL is discarded before the loop advances"),
    ("objects", "count", 0x3DD6F1, "mov byte ptr [rdi], al", None,
     "objScroll 3DD580: byte alpha fades with a distance-derived coefficient; hold the "
     "quantized store between stock ticks"),
    # ut89's angular velocity changes before each angle integration.
    ("objects", "count", 0x652964, "addss xmm0, xmm6", "float",
     "ut89 652910: increase each angular velocity toward its target only on stock "
     "ticks, before the following clamp and angle integration"),
    ("objects", "count", 0x652976, "subss xmm0, xmm6", "float",
     "ut89 652910: decrease each angular velocity toward its target only on stock "
     "ticks, before the following clamp and angle integration"),
    ("objects", "pre", 0x65298D, "addss xmm0, dword ptr [rax + 0xb8]", None,
     "ut89 652910: scale the complete angular velocity immediately before adding the "
     "old angle; clamp targets retain their units"),
    ("objects", "srcx", 0x553603, "addss xmm0, xmm6", None,
     "ut91 5534A0: animation decision phase +1080 advances one per stock tick in modes "
     "1 and 3, independently of the already-paced model motion"),
    ("objects", "count", 0x55361C, "mov byte ptr [rbx + 0x1070], al", None,
     "ut91 5534A0: positive byte cooldown +1070 counts down; AL is discarded before "
     "return"),
    # The coupled sound phase uses signed-positive completion tests.
    ("objects", "lin", 0x548225, "addss xmm0, dword ptr [rip + 0x167017]",
     (0x6AF244, 1.3333333730697632),
     "ut9d 5481E0: sound phase amplitude rises 1.333333 per stock tick toward the "
     "fixed 60 limit"),
    ("objects", "count", 0x548253, "dec dword ptr [rdi + 0x1070]", None,
     "ut9d 5481E0: sound phase countdown at +1070 controls a single stop/reload event"),
    ("objects", "notyet", 0x548259, "cmp dword ptr [rdi + 0x1070], 0", 0x5482C0,
     "ut9d 5481E0: a held countdown tick takes JG past the sound-stop and "
     "random-reload event, preserving stock cadence"),
    ("objects", "lin", 0x548362, "subss xmm0, dword ptr [rip + 0x166eda]",
     (0x6AF244, 1.3333333730697632),
     "ut9d 5481E0: sound phase amplitude falls 1.333333 per stock tick toward zero"),
    ("objects", "count", 0x54838B, "dec dword ptr [rdi + 0x1070]", None,
     "ut9d 5481E0: sound phase countdown controls one transition out of the falling "
     "phase"),
    ("objects", "notyet", 0x548391, "cmp dword ptr [rdi + 0x1070], 0", 0x5482C5,
     "ut9d 5481E0: a held countdown tick takes JG past the phase transition"),
    ("objects", "pre", 0x509EE5, "addss xmm0, dword ptr [rax + 4]", None,
     "ut1b 509EB0: add the complete Y velocity +1098 to old height at stock speed "
     "before clamping to the fixed starting-height-plus-90 target"),
    ("objects", "src", 0x50EF63, "subsd xmm0, qword ptr [rip + 0x169565]", None,
     "et7d 50EF30: scale the double-precision alpha decrement before conversion back "
     "to float; completion exits the fade phase once"),
    ("objects", "count", 0x50EFB1, "inc dword ptr [rbx + 0x1070]", None,
     "et7d 50EF30: wait 60 stock ticks after model-motion completion before entering "
     "the alpha fade phase"),
    ("objects", "lin", 0x583D07, "addss xmm0, dword ptr [rip + 0xf5f65]",
     (0x679C74, 0.4000000059604645),
     "utcc 583C90: height rises 0.4 per stock tick toward starting height plus 220"),
    ("objects", "lin", 0x583DAC, "subss xmm0, dword ptr [rip + 0xee060]", (0x671E14, 2.0),
     "utcc 583C90: height falls two units per stock tick toward starting height"),
    ("objects", "lin", 0x57CB2F, "addss xmm0, dword ptr [rip + 0xf5df5]",
     (0x67292C, 0.20000000298023224),
     "ut2c 57CA00: height rises 0.2 per stock tick toward the fixed +E14 target before "
     "phase 3 changes to 4"),
    ("objects", "srcx", 0x552E57, "subss xmm1, xmm6", None,
     "ut47 552CF0: scale the complete vertical move at the position subtraction, "
     "retaining the unscaled vertical component used to derive horizontal movement"),
    ("objects", "srcx", 0x552F45, "subss xmm1, xmm0", None,
     "ut47 552CF0: scale the complete sine-directed horizontal X move before "
     "subtracting it from the old position"),
    ("objects", "srcx", 0x552F7B, "subss xmm1, xmm0", None,
     "ut47 552CF0: scale the complete cosine-directed horizontal Z move before "
     "subtracting it from the old position"),
    ("objects", "src", 0x552FB8, "addss xmm0, dword ptr [rip + 0x2740b0]", None,
     "ut47 552CF0: scale the live +1088 rate increase read from the mutable speed "
     "table, consistent with the already-scaled rate decrease in the earlier branch"),
    ("objects", "srcx", 0x55298F, "subss xmm1, xmm7", None,
     "ut47 552950: scale the negative height step while preserving XMM7 as the "
     "completion threshold source"),
    ("objects", "srcx", 0x55299D, "addss xmm1, xmm7", None,
     "ut47 552950: scale the positive height step while preserving XMM7 as the "
     "completion threshold source"),
    ("objects", "pre", 0x5529F1, "comiss xmm7, xmm6", None,
     "ut47 552950: scale the complete per-tick height limit immediately before "
     "comparing it against absolute remaining height distance, so the snap uses the "
     "scaled step"),
    ("objects", "count", 0x217FE4, "inc dword ptr [rbx + 0x107c]", None,
     "ut1e 217F20: phase-three wait counts 15 stock ticks before one motion setup and "
     "state transition"),
    ("objects", "count", 0x2180D6, "inc dword ptr [rbx + 0x107c]", None,
     "ut1e 217F20: phase-one wait counts 30 stock ticks before the phase-two sound and "
     "transition"),
    ("objects", "count", 0x21806F, "inc ecx", (0x218069,0x218071,(0x218069,0x21806F),None),
     "ut1e 217F20: phase-two +107C period increments before the modulo-30 event test; "
     "preserve the loaded register on held ticks"),
    ("objects", "notyet", 0x218084, "cmp ecx, eax", 0x21816D,
     "ut1e 217F20: held modulo-30 ticks skip the recurring sound event even when the "
     "counter is divisible by 30"),
    ("objects", "count", 0x21ABD0, "mov byte ptr [rdi + 0x10e1], al", None,
     "ut36 21AA80: positive byte cooldown +10E1 delays reactivation; computed AL is "
     "discarded before the sound mask test"),
    ("objects", "count", 0x21AC12, "inc byte ptr [rdi + 0x10e0]", None,
     "ut36 21AA80: phase-one recurring sound period +10E0 advances after its old-value "
     "test"),
    ("objects", "notyet", 0x21ABD6, "test byte ptr [rdi + 0x10e0], 0x1f", 0x21AC12,
     "ut36 21AA80: held phase-one sound period skips the modulo-32 trigger"),
    ("objects", "count", 0x21AD62, "inc byte ptr [rdi + 0x10e0]", None,
     "ut36 21AA80: phase-three recurring sound period advances after the old-value "
     "test"),
    ("objects", "notyet", 0x21AD25, "test byte ptr [rdi + 0x10e0], 0x1f", 0x21AD62,
     "ut36 21AA80: held phase-three sound period skips the modulo-32 trigger"),
    ("objects", "count", 0x21AA6C, "inc byte ptr [rbx + 0x10e0]", None,
     "ut36 21A970: recurring sound period +10E0 advances after its old-value test"),
    ("objects", "notyet", 0x21AA30, "test byte ptr [rbx + 0x10e0], 0x1f", 0x21AA6C,
     "ut36 21A970: held sound period skips the modulo-32 trigger"),
    ("objects", "count", 0x21A5F3, "inc byte ptr [rdi + 0x10e0]", None,
     "ut36 219F90: phase-three sound-trigger branch advances the shared +10E0 period"),
    ("objects", "notyet", 0x21A59F, "test byte ptr [rdi + 0x10e0], 0x1f", 0x21A85A,
     "ut36 219F90: held +10E0 ticks skip the phase-three recurring sound trigger "
     "across two flag-neutral register reloads"),
    ("objects", "count", 0x21A85A, "inc byte ptr [rdi + 0x10e0]", None,
     "ut36 219F90: other branches advance the shared recurring sound period"),
    ("objects", "notyet", 0x21A81E, "test byte ptr [rdi + 0x10e0], 0x1f", 0x21A85A,
     "ut36 219F90: held +10E0 ticks skip the recurring sound trigger in the common "
     "phase-one branch"),
    ("objects", "count", 0x2202E7, "mov byte ptr [rbx + 0x10f8], cl", None,
     "ut60 220270: recurring sound period +10F8 advances after copying its old byte to "
     "AL"),
    ("objects", "notyet", 0x2202ED, "and al, 0x1f", 0x220317,
     "ut60 220270: keep the masked old AL but skip its modulo-32 sound event on held "
     "ticks"),
    ("objects", "count", 0x220815, "mov byte ptr [rbx + 0x10f8], cl", None,
     "ut61 2205B0: recurring sound period +10F8 advances after copying the old byte to "
     "AL"),
    ("objects", "notyet", 0x22081B, "and al, 0x1f", 0x220845,
     "ut61 2205B0: held sound-period ticks skip the old-value modulo-32 sound event"),
    ("objects", "count", 0x226F12, "mov word ptr [rdi + 0xe42], dx", None,
     "ut88 226E40: +E42 counts stock ticks until the placement-dependent initial delay "
     "has elapsed"),
    ("objects", "notyet", 0x226EFC, "cmp edx, ecx", 0x226F07,
     "ut88 226E40: a held delay tick skips the equality transition based on the old "
     "+E42 value"),
    ("objects", "count", 0x22708D, "mov byte ptr [rdi + 0x10f8], al", None,
     "ut88 226E40: +10F8 sound period increments with computed AL discarded before its "
     "old CL test"),
    ("objects", "notyet", 0x227093, "test cl, cl", 0x22713F,
     "ut88 226E40: held sound-period ticks skip the old-zero sound event, including "
     "wraparound"),
    ("objects", "count", 0x22116A, "inc dword ptr [rdi + 0x1138]", None,
     "ut65 221070: +1138 is the common elapsed phase read modulo 120 or 140 by child "
     "helpers; each child sound also sets a latch to prevent replay while the phase is "
     "held"),
    ("objects", "count", 0x22C0C0, "subss xmm0, dword ptr [rip + 0x4511a0]", "float",
     "utbb 22C000: change Y velocity by the stock gravity step on the first tick of "
     "each stock period, before integrating it"),
    ("objects", "pre", 0x22C0D7, "addss xmm0, dword ptr [rax + 4]", None,
     "utbb 22C000: integrate the complete Y velocity at stock speed after writing the "
     "velocity back, preserving the unscaled velocity field"),
    ("objects", "count", 0x22C41E, "mov byte ptr [rbx + 0xe36], al", None,
     "utbb 22C3D0: bounded 0-to-5 reactivation debounce counts stock ticks before "
     "enabling the object"),
    ("objects", "count", 0x22C902, "mov byte ptr [rbx + 0x1106], al", None,
     "utbc 22C880: positive +1106 cooldown decrements with AL discarded before return"),
    ("objects", "count", 0x22CF32, "mov byte ptr [rbx + 0x1100], al", None,
     "utbc 22CED0: positive +1100 debounce decrements and returns before the "
     "action-selection path"),
    ("objects", "count", 0x22F646, "sub dword ptr [rcx + 0x1090], 1", "down",
     "utcb 22F640: five-tick wait before restoring placement and opening the selected "
     "dialogue; expiry leaves this phase"),
    ("objects", "count", 0x232798, "mov byte ptr [rbx + 0x1100], r8b", None,
     "utdb 232680: recurring phase-five sound period +1100 advances after computing "
     "the old-byte quotient; R8 is not read after its store"),
    ("objects", "notyet", 0x2327A4, "cmp ecx, eax", 0x2326C5,
     "utdb 232680: held modulo-six ticks skip the old-counter sound event"),
    ("objects", "count", 0x238436, "mov word ptr [rbx + 0xe3c], ax", None,
     "utfb 238380: positive three-tick spawn cooldown decrements and returns before "
     "the spawn/reload path"),
    ("objects", "count", 0x33D38C, "mov byte ptr [rbx + 0x12b0], al", None,
     "cCarryObj 33D360: positive seven-tick attached-effect cooldown decrements with "
     "AL discarded before the effect-state test"),
    ("objects", "count", 0x3672DC, "sub ax, 1", (0x3672D0,0x3672E0,(0x3672D0,0x3672D7,0x3672DA,0x3672DC),None),
     "cKiType011: positive +11B0 countdown controls one cleanup at zero, preserving "
     "not-finished flags on held ticks"),
    ("objects", "count", 0x3678E9, "sub ax, 1", (0x3678DD,0x3678ED,(0x3678DD,0x3678E4,0x3678E7,0x3678E9),None),
     "cKiType012: positive +11B0 countdown controls one cleanup at zero, preserving "
     "not-finished flags on held ticks"),
    ("objects", "count", 0x4985A6, "mov byte ptr [rbx + 0x11b6], al", None,
     "cItemObj 4984E0: positive +11B6 pickup cooldown decrements with AL discarded "
     "before the enable test reloads the field"),
    ("objects", "count", 0x4985F0, "sub al, 1", (0x4985E5,0x4985F2,(0x4985E5,0x4985EC,0x4985EE,0x4985F0),None),
     "cItemObj 4984E0: +11B7 attached-effect cooldown decrements once per stock tick; "
     "its JNE cleanup uses not-finished flags on held ticks"),
    ("objects", "count", 0x49861D, "mov byte ptr [rbx + 0x11b8], al", None,
     "cItemObj 4984E0: positive +11B8 cooldown decrements with AL discarded before the "
     "next cooldown load"),
    ("objects", "count", 0x498630, "mov byte ptr [rbx + 0x11b5], al", None,
     "cItemObj 4984E0: positive +11B5 cooldown decrements with AL discarded before "
     "return"),
    ("objects", "count", 0x61FBC2, "inc dword ptr [rbx + 0x1148]", None,
     "et26 61FB30: +1148 counts elapsed phase-four model ticks while motion advances "
     "independently"),
    ("objects", "count", 0x61FC53, "inc dword ptr [rbx + 0x1148]", None,
     "et26 61FB30: +1148 counts a 600-stock-tick attached-state timeout before one "
     "motion/state transition"),
    ("objects", "count", 0x6519B5, "mov word ptr [rbx + 0xe3e], ax", None,
     "ut35 6518E0: positive +E3E motion-phase duration decrements with AX discarded "
     "before the next speed calculation"),
    ("objects", "count", 0x651C15, "mov word ptr [rbx + 0xe3e], ax", None,
     "ut35 651B40: positive +E3E motion-phase duration decrements with AX discarded "
     "before the next speed calculation"),
    ("objects", "count", 0x552CCA, "inc byte ptr [rbx + 0x1078]", None,
     "ut47 552B70: +1078 counts 13 consecutive stock ticks of negligible movement "
     "before the stuck phase; threshold changes E35 out of this branch"),
    ("objects", "count", 0x560CA2, "mov word ptr [rbx + 0xe3e], cx", None,
     "uta4 560BD0: +E3E recurring 120-tick effect period advances after deriving the "
     "old signed quotient; CX is discarded before the old-value event comparison"),
    ("objects", "notyet", 0x560CB1, "cmp r8d, eax", 0x560D24,
     "uta4 560BD0: held modulo-120 ticks skip the effect trigger based on the old "
     "period value"),
    ("objects", "count", 0x4D1156, "mov byte ptr [rbx + 0x10e0], al", None,
     "et69 4D1000: +10E0 advances the 100-tick recurring sound delay with AL discarded "
     "before return"),
    ("objects", "count", 0x4FEC7D, "dec byte ptr [rbx + 0xe35]", None,
     "ut16 4FEC40: positive +E35 counts the stock duration of temporary extra "
     "model-motion advances; all three motion calls already use the common motion "
     "pacing"),
    ("objects", "count", 0x4FF19B, "sub al, 1",
     (0x4FF190,0x4FF19D,(0x4FF190,0x4FF197,0x4FF199,0x4FF19B),None),
     "ut17 4FF080: positive five-tick motion-start delay counts down with JNE "
     "completion suppressed on held ticks"),
    ("objects", "count", 0x50E8E0, "sub dword ptr [rcx + 0x1134], 1", "down",
     "cDigObj 50E810: scripted effect waits 75 or 210 stock ticks before changing E34 "
     "out of the wait phase"),
    ("objects", "count", 0x50E954, "mov dword ptr [rcx + 0x1134], eax", None,
     "cDigObj 50E900: positive eight-tick effect cooldown decrements and returns "
     "before the next spawn/reload"),
    ("objects", "count", 0x517319, "inc byte ptr [rbx + 0xe36]", None,
     "ut28 517200: +E36 is a 16-tick quantized alpha phase; alpha is recomputed from "
     "the held phase and phase sixteen immediately exits this state"),
    ("objects", "count", 0x523FC3, "sub word ptr [rbx + 0xe3c], cx", "down",
     "ut58 523FA0: phase-four +E3C counts down from 30; CX equals one on this dispatch "
     "branch and JNS suppresses completion between stock ticks"),
    ("objects", "count", 0x55233B, "mov word ptr [rbx + 0x1070], ax", None,
     "ut43 5522E0: +1070 is a 360-tick recurring sound cooldown; store the decremented "
     "or freshly reloaded value only on stock ticks"),
    ("objects", "notyet", 0x552306, "test ax, ax", 0x552338,
     "ut43 recurring 360-tick sound: test the old cooldown only on stock ticks, "
     "including the zero that starts the next period; the paired store holds its value "
     "between them."),
    ("objects", "notyet", 0x2383EE, "test ax, ax", 0x238433,
     "utfb recurring spawn: old-zero event and the positive three-tick decrement share "
     "the stock cadence, preserving the original four-tick spawn interval."),
    ("objects", "notyet", 0x50E91C, "test eax, eax", 0x50E952,
     "cDigObj recurring effect: sample old-zero at stock cadence along with the "
     "countdown, preserving its original nine-tick interval."),
    ("objects", "notyet", 0x33D386, "test al, al", 0x33D38A,
     "cCarryObj attached effect: defer old-zero expiry between stock ticks, paired "
     "with the seven-tick decrement, so the flag reset and respawn keep their original "
     "cadence."),
    ("objects", "pre", 0x22AABC, "addss xmm0, dword ptr [rdi + 0xb4]", None,
     "ut9e return movement: scale the complete clamped yaw delta before adding the "
     "current yaw and wrapping it."),
    ("objects", "pre", 0x23108F, "addss xmm0, dword ptr [rbx + 0xb4]", None,
     "utd7 tracking: scale the complete 2DE0A0 yaw delta before adding the old yaw and "
     "wrapping it."),
    ("objects", "pre", 0x22761E, "addss xmm0, dword ptr [rcx + 0xb4]", None,
     "ut8e spin: scale the selected sign and 0.03/0.01 angular step at the common join "
     "before adding the old yaw."),
    ("objects", "pre", 0x22D9ED, "addss xmm0, xmm2", None,
     "utbc radius growth: scale the complete distance/(radius*10*2pi) increment before "
     "adding the current radius and applying the 2.5 clamp."),
    ("objects", "lin", 0x58FF34, "addss xmm0, dword ptr [rip + 0xe501c]", (0x674F58, 3.0),
     "ute2 state 3: rise three units per stock tick until the state-4 fixed placement "
     "takes over."),
    ("objects", "count", 0x22B1F0, "inc dword ptr [rbx + 0x107c]", None,
     "utb8 phase-zero readiness: require three stock ticks of ready result before "
     "starting the phase-one event."),
    ("objects", "count", 0x55B725, "mov word ptr [rbx + 0xe3e], ax", None,
     "ut8a fast model speed: decrement the positive +E3E forty-tick duration once per "
     "stock tick."),
    ("objects", "count", 0x56351B, "mov word ptr [rdi + 0x1180], ax", None,
     "uta6 thrown submodel: pace the +1180 twenty-five-tick duration."),
    ("objects", "scaledadd", 0x56350B, "call qword ptr [rip + 0x10d8ef]", None,
     "uta6 thrown submodel: scale the rotated +1170 velocity when integrating XYZ; the "
     "launch vector retains its stock magnitude."),
    ("objects", "notyet", 0x563522, "test cx, cx", 0x56352E,
     "uta6 thrown submodel: gate the old-zero completion test alongside its +1180 "
     "timer."),
    ("objects", "count", 0x5674DB, "inc dword ptr [rbx + 0x1104]", None,
     "utaa area duration: advance +1104 once per stock tick while the player is inside "
     "the region; the outside assignment remains an immediate reset to 90."),
    ("objects", "count", 0x56A08B, "inc dword ptr [rbx + 0x1104]", None,
     "utab area duration: advance +1104 once per stock tick while the player is inside "
     "the region; the outside assignment remains an immediate reset to 90."),
    ("objects", "gatefn", 0x55D010, "mov qword ptr [rsp + 0x18], rbx", None,
     "uta1 spring update: the void caller 55CECA ignores the result; the entire "
     "previously unpatched spring, damping, integration, countdowns and completion "
     "events run at stock cadence."),
    ("objects", "lin", 0x630BEF, "movss xmm0, dword ptr [rip + 0x4a235]",
     (0x67AE2C, -0.20000000298023224),
     "et30 supplemental motion: scale only the steady negative 0.2 blend-weight fade; "
     "the event-bit impulse of 1 remains immediate and the event bit is cleared after "
     "use."),
    ("objects", "srcx", 0x630D64, "addss xmm1, xmm9", None,
     "et30 supplemental motion: advance the independent +125C motion frame by one "
     "stock-frame fraction while preserving the shared XMM9 one used by the duration "
     "limit."),
    ("objects", "srcroot", 0x2118DB, "mulss xmm0, dword ptr [rip + 0x468bad]", None,
     "cObjSimpleEmRoll sustained scale growth: use the per-tick root of 1.33 when "
     "B6AC5C is active; preserve the shared source constant."),
    ("objects", "srcroot", 0x2E4FE8, "mulss xmm1, dword ptr [rip + 0x38ce14]", None,
     "et0f dismissal: compose the 0.1 alpha decay across fractional stock ticks until "
     "the state-one reset."),
    ("objects", "pre", 0x4F2A23, "addss xmm0, dword ptr [rcx + 4]", None,
     "ut25 platform passenger: scale the complete +1150 platform velocity before "
     "adding it to player Y, matching platform integration."),
    ("objects", "pre", 0x4F1EAF, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 rising platform state 7: scale acceleration +115C before adding it to "
     "stock-unit velocity +1150; retain the velocity clamps."),
    ("objects", "pre", 0x4F21B2, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 rising platform state 11: scale acceleration +115C before adding it to "
     "stock-unit velocity +1150; retain the velocity clamps."),
    ("objects", "pre", 0x4F242F, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 descending platform state 15: scale acceleration +115C before adding it to "
     "stock-unit velocity +1150; retain the velocity clamps."),
    ("objects", "pre", 0x4F2552, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 descending platform state 17: scale acceleration +115C before adding it to "
     "stock-unit velocity +1150; retain the velocity clamps."),
    ("objects", "src", 0x4F1EFE, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 state 7: integrate platform Y with a fraction of the stock-unit +1150 "
     "velocity."),
    ("objects", "src", 0x4F2204, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 state 11: integrate platform Y with a fraction of the stock-unit +1150 "
     "velocity."),
    ("objects", "src", 0x4F2481, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 state 15: integrate platform Y with a fraction of the stock-unit +1150 "
     "velocity."),
    ("objects", "src", 0x4F25A4, "addss xmm0, dword ptr [rdi + 0x1150]", None,
     "ut25 state 17: integrate platform Y with a fraction of the stock-unit +1150 "
     "velocity."),
    ("objects", "count", 0x21335B, "addss xmm0, xmm6", "float",
     "ut01 animation restart delay: advance the +1090 stock-frame counter once per "
     "stock tick; +1094 clears on the completion event and action starts reset the "
     "counter."),
    ("objects", "lin", 0x57F597, "addss xmm0, dword ptr [rip + 0xf2669]", (0x671C08, 1.0),
     "ut48 raised platform: rise one unit per stock tick, clamped to +E14 plus 100."),
    ("objects", "lin", 0x57F5D4, "subss xmm0, dword ptr [rip + 0xf262c]", (0x671C08, 1.0),
     "ut48 lowered platform: descend one unit per stock tick, clamped to +E14."),
    ("objects", "lin", 0x21CBDF, "addss xmm1, dword ptr [rip + 0x458e5d]", (0x675A44, 1.5),
     "ut49 platform restoration: rise 1.5 units per stock tick until the +E14 height "
     "clamp."),
    ("objects", "count", 0x160348, "dec byte ptr [rbx + 0x44]", None,
     "selection dialog exit phase 3: consume the positive byte +44 animation-close "
     "delay at stock cadence before returning to the owner state."),
    ("objects", "count", 0x160384, "dec byte ptr [rbx + 0x44]", None,
     "selection dialog exit phase 2: consume the positive byte +44 animation-close "
     "delay at stock cadence before selecting the next action."),
    ("objects", "count", 0x1D0500, "inc dword ptr [rbx + 0x1c]", None,
     "text box exit interpolation: advance the six-step +1C clock at stock cadence; "
     "scale fields derive directly from that clock."),
    ("objects", "count", 0x1D2817, "inc dword ptr [rbx + 0x1c]", None,
     "dialogue response phase 1: pace the fifteen-tick +1C delay before advancing +57."),
    ("objects", "count", 0x1D2840, "inc dword ptr [rbx + 0x1c]", None,
     "dialogue response phase 3: pace the forty-five-tick +1C delay before advancing "
     "+57."),
    ("objects", "count", 0x1D28D2, "inc dword ptr [rbx + 0x1c]", None,
     "dialogue response phase 5: pace the final fifteen-tick +1C delay before "
     "reporting completion."),
    ("objects", "count", 0x1D0EFB, "add dword ptr [rbx + 0x7c], edi", None,
     "dialogue text reveal: add the integer reveal-speed amount to +7C once per stock "
     "tick, including the input-selected tenfold acceleration."),
    ("objects", "count", 0x1D1B9C, "inc dword ptr [rbx + 0x1c]", None,
     "text box entrance interpolation: advance its six-step +1C clock once per stock "
     "tick; scale fields derive directly from that clock."),
    ("objects", "count", 0x13F1C1, "mov dword ptr [rdi + 0x18], eax", None,
     "controller reassignment: consume the thirty-tick +18 delay after the active "
     "input mode closes."),
    ("objects", "count", 0x14ADDE, "mov dword ptr [rbx + 0x18], eax", None,
     "asynchronous UI operation: advance bounded +18 progress at stock cadence until "
     "+1C; the displayed progress ratio follows this count."),
    ("objects", "count", 0x15FDA5, "inc dword ptr [rdi + 0x15c]", None,
     "audio playlist: pace the 1320-tick inter-track wait after playback completes; "
     "immediate failure initializes the threshold and remains immediate."),
    ("objects", "count", 0x186469, "mov dword ptr [rsi + 0x248], eax", None,
     "cPad movement chord: require five stock ticks of the held action before changing "
     "its combined-action bits; releasing the action resets +248."),
    ("objects", "count", 0x1866EB, "mov dword ptr [rbx + 0x264], eax", None,
     "cPad update input blackout: consume positive +264 at stock cadence; hardware "
     "updates and actuator calls continue normally."),
    ("objects", "count", 0x186F64, "mov dword ptr [rbx + 0x10], ecx", None,
     "controller recovery: consume the positive sixty-tick +10 delay before reporting "
     "a connection/reassignment outcome."),
    ("objects", "gatefn", 0x4990A0, "push rbx", None,
     "cItemObj floating state: run the coupled height-selected acceleration, velocity "
     "clamp/damping, position integration, and collision transition together at stock "
     "cadence."),
    ("objects", "gatefn", 0x498D00, "push rbx", None,
     "cItemObj falling state: keep the coupled XYZ integration, gravity, contact "
     "checks, impact restitution, and state transitions together at stock cadence."),
    ("objects", "pre", 0x2172B1, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "ut12 falling phase: add the original +E54 vertical velocity divided by N to "
     "position; the ground-contact clamp and phase transition remain immediate."),
    ("objects", "lin", 0x217360, "subss xmm0, dword ptr [rip + 0x45aaa0]", (0x671E08, 0.5),
     "ut12 falling phase: subtract 0.5/N from the original vertical velocity per tick."),
    ("objects", "count", 0x2310F0, "inc byte ptr [rbx + 0x1620]", None,
     "utd7 trailing position history: advance its sixty-entry sampling cursor once per "
     "stock tick; held ticks refresh the current slot."),
    ("objects", "lin", 0x231157, "movss xmm2, dword ptr [rip + 0x446491]",
     (0x6775F0, 0.05000000074505806),
     "utd7 exit growth: shared 0.05 scale increment is divided by N before all three "
     "scale channels and the 1.6 clamp."),
    ("objects", "dst", 0x2025CF, "mulss xmm0, dword ptr [rdi + 0x1108]", None,
     "Shared path follower: scale the complete +112C times +1108 progress increment "
     "before adding +1194 and applying its path-segment wrap."),
    ("objects", "blend", 0x202649, "mulss xmm0, dword ptr [rip + 0x4705cb]", (0x672C1C, 0.125),
     "Shared path follower: use the Nth-root surviving-gap coefficient for the 0.125 "
     "heading approach."),
    ("objects", "blend", 0x203F64, "mulss xmm2, dword ptr [rip + 0x471ac4]",
     (0x675A30, 0.30000001192092896),
     "Shared depth fade: approach the freshly projected depth target with a "
     "time-corrected 0.3 blend."),
    ("objects", "blend", 0x203F92, "mulss xmm1, dword ptr [rip + 0x471a96]",
     (0x675A30, 0.30000001192092896),
     "Shared depth fade: approach opaque alpha with a time-corrected 0.3 blend in the "
     "far-depth branch."),
    ("objects", "blend", 0x203FC0, "mulss xmm1, dword ptr [rip + 0x471a68]",
     (0x675A30, 0.30000001192092896),
     "Shared depth fade: approach opaque alpha with a time-corrected 0.3 blend in the "
     "alternate scene branch."),
    ("objects", "lin", 0x2040FE, "mulss xmm0, dword ptr [rip + 0x46e82a]",
     (0x672930, 0.8999999761581421),
     "Shared animal/player-relative movement: scale the complete normalized X "
     "direction times its 0.9 per-tick step."),
    ("objects", "lin", 0x204123, "mulss xmm0, dword ptr [rip + 0x46e805]",
     (0x672930, 0.8999999761581421),
     "Shared animal/player-relative movement: scale the complete normalized Z "
     "direction times its 0.9 per-tick step."),
    ("objects", "lin", 0x209354, "movss xmm2, dword ptr [rip + 0x4695d0]",
     (0x67292C, 0.20000000298023224),
     "Shared cKiType appearance: divide the shared 0.2 scale increment by N before all "
     "three scale channels and their one-unit clamp."),
    ("objects", "lin", 0x244DF2, "movss xmm1, dword ptr [rip + 0x433a96]",
     (0x678890, 0.029999999329447746),
     "244C80 shrinks all three persistent submodel scale channels by the same 0.03 "
     "increment per stock tick before their 0.2 clamps."),
    ("objects", "lin", 0x2450F4, "movss xmm2, dword ptr [rip + 0x433794]",
     (0x678890, 0.029999999329447746),
     "244C80 restores all three persistent submodel scale channels by the same 0.03 "
     "increment per stock tick before their one-unit clamps."),
    # 623540 has two callers: 6262D0's loop runs every tick (its wait 62671D is
    # not a task_waits.h loop: the loop reads the mode byte), 626A00's passes once
    # a stock tick (task_waits.h 626CD1). A gatefn on 623540 would gate the
    # second again on the frame counter's phase, so only the first call is gated.
    ("objects", "callgate", 0x626404, "call 0x623540", (0x623540, "void"),
     "Shared minigame six-object update, from 6262D0's per-tick loop: advance "
     "movement, target ownership timeout, random respawn and loop placement together "
     "on stock ticks (626A00's loop already calls it once a stock tick)."),
    ("objects", "srcx", 0x6263C0, "subss xmm0, dword ptr [r9 + 0x144]", None,
     "Minigame backdrop scrolling: divide the speed operand by N before subtracting it "
     "from track Z; preserve the full loop length used for wrapping."),
    ("objects", "count", 0x62668C, "sub al, 1",
     (0x626681,0x62668E,(0x626681,0x626688,0x62668A,0x62668C),None),
     "Minigame close delay: count the positive 30-tick byte once per stock tick and "
     "preserve not-complete flags when held."),
    ("flag", "gatefn", 0x1882A0, "test byte ptr [rcx + 0x20], 1", None,
     "Rumble waveform wrapper: sample the analog waveform, accumulate small-motor PWM, "
     "emit pulse requests and advance/wrap its phase together at the same N60 cadence "
     "as cPad Actuater."),
    ("objects", "srcblend", 0x315F07, "divss xmm1, xmm0", None,
     "315E60 stage-zero submodel X scale approaches zero using the reciprocal of the "
     "already stock-paced E3C+1 countdown; use the Nth-root surviving-gap blend."),
    ("objects", "srcblend", 0x315F30, "divss xmm1, xmm0", None,
     "315E60 stage-zero submodel Y scale approaches two using the reciprocal of the "
     "already stock-paced E3C+1 countdown; use the Nth-root surviving-gap blend."),
    ("objects", "srcblend", 0x315F5A, "divss xmm6, xmm0", None,
     "315E60 stage-zero submodel Z scale approaches zero using the reciprocal of the "
     "already stock-paced E3C+1 countdown; use the Nth-root surviving-gap blend."),
    ("objects", "gatefn", 0x55D940, "mov rax, rsp", None,
     "uta2 first pendulum: preserve the complete coupled external load, angular force, "
     "vertical spring, stock damping, passenger transport, collision release and phase "
     "sound at stock cadence. Inner decay 55DE71 is delegated to this cadence gate."),
    ("objects", "gatefn", 0x55E070, "mov rax, rsp", None,
     "uta2 second pendulum: preserve the complete coupled external load, angular "
     "force, stock damping, passenger transport, collision release and phase sound at "
     "stock cadence. Inner decay 55E39E is delegated to this cadence gate."),
    ("objects", "gatefn", 0x55E520, "mov rax, rsp", None,
     "uta2 striking pendulum: preserve the coupled angular force, stock damping, "
     "passenger transport, hit/reload cooldown and target impulse at stock cadence. "
     "Inner decay 55E859 is delegated to this cadence gate."),
    ("objects", "gatefn", 0x4A76A0, "mov rax, rsp", None,
     "Shared deforming-model spring: evaluate positional error, bounded displacement, "
     "spring acceleration, velocity drag/friction and the resulting transform together "
     "on stock ticks; reset-event handlers in 4A74D0 remain immediate."),
    ("objects", "lin", 0x364F82, "addss xmm0, dword ptr [rip + 0x30ce7e]", (0x671E08, 0.5),
     "cKiType019 death rise: scale the constant half-unit ascent per stock tick; "
     "motion advance remains independently time-correct."),
    ("objects", "pre", 0x365008, "addss xmm0, dword ptr [rcx + 4]", None,
     "cKiType019 death rise: the first operand is the complete (E3C-30)*0.3 ascent "
     "step; scale it before adding old Y."),
    ("objects", "count", 0x364FB1, "movss dword ptr [rax + 4], xmm0", None,
     "cKiType019 death jitter: commit the positive random displacement only on stock "
     "ticks, preserving its amplitude and sample cadence."),
    ("objects", "count", 0x364FDC, "movss dword ptr [rax + 4], xmm1", None,
     "cKiType019 death jitter: commit the negative random displacement only on stock "
     "ticks; later height tests reload Y from memory."),
    ("objects", "lin", 0x36CDE2, "addss xmm0, dword ptr [rip + 0x30501e]", (0x671E08, 0.5),
     "cKiType041 death rise: scale the half-unit ascent separately from the already "
     "corrected motion clock."),
    ("objects", "pre", 0x36CE68, "addss xmm0, dword ptr [rcx + 4]", None,
     "cKiType041 death rise: scale the complete elapsed-count ascent step before "
     "adding old Y."),
    ("objects", "count", 0x36CE11, "movss dword ptr [rax + 4], xmm0", None,
     "cKiType041 death jitter: commit the positive random displacement only on stock "
     "ticks; the following join reloads Y."),
    ("objects", "count", 0x36CE3C, "movss dword ptr [rax + 4], xmm1", None,
     "cKiType041 death jitter: commit the negative random displacement only on stock "
     "ticks; its arithmetic result is not reused."),
    ("objects", "count", 0x2E1A48, "movss dword ptr [rax + 0xb0], xmm0", None,
     "et04 linked model settling: commit the -0.5 X rotation recurrence on stock "
     "ticks; retain sign reversal and amplitude together."),
    ("objects", "count", 0x2E1A5C, "movss dword ptr [rax + 0xb4], xmm1", None,
     "et04 linked model settling: commit the matching -0.5 Y rotation recurrence on "
     "the same stock ticks."),
    ("objects", "count", 0x2E1A64, "movss dword ptr [rax + 0xb8], xmm0", None,
     "et04 linked model settling: commit the matching -0.5 Z rotation recurrence on "
     "the same stock ticks."),
    ("objects", "src", 0x2F2C82, "addsd xmm0, xmm1", None,
     "cObj appearance: scale the double-precision D20 alpha increment from the shared "
     "XMM1 step, preserving the source and narrowing once."),
    ("objects", "src", 0x2F2C9D, "addsd xmm0, xmm1", None,
     "cObj appearance: scale the double-precision D24 alpha increment, preserving the "
     "shared XMM1 step for the other channels."),
    ("objects", "src", 0x2F2CB8, "addsd xmm0, xmm1", None,
     "cObj appearance: scale the double-precision D28 alpha increment before its "
     "original float conversion and unit clamp."),
    ("objects", "srcx", 0x33B052, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "cBallObj ballistic motion: scale persistent E54 vertical velocity when adding it "
     "to world Y; the port gravity update stays separate."),
    ("objects", "count", 0x33B085, "movss dword ptr [rbx + 0x1140], xmm0", None,
     "cBallObj spin-rate settling: commit the complete (1140-0.2)*double damping "
     "recurrence only on stock ticks, preserving its coupled stock update."),
    ("objects", "pre", 0x56414C, "addss xmm0, dword ptr [rdi + 0xe14]", None,
     "uta7 platform: scale the complete positive passenger-load torque before adding "
     "it to angular velocity E14."),
    ("objects", "pre", 0x564175, "addss xmm1, dword ptr [rdi + 0xe14]", None,
     "uta7 platform: scale the complete negative passenger-load torque before adding "
     "it to angular velocity E14."),
    ("objects", "srcx", 0x5641C6, "addss xmm0, xmm1", None,
     "uta7 platform: scale the sustained secondary passenger torque when accumulating "
     "E14."),
    ("objects", "srcx", 0x56420B, "subss xmm0, xmm1", None,
     "uta7 platform: scale the sustained opposing passenger torque when accumulating "
     "E14."),
    ("objects", "lin", 0x564271, "mulss xmm1, dword ptr [rip + 0x154c6b]",
     (0x6B8EE4, 4.999999873689376e-06),
     "uta7 platform: scale the height-error spring acceleration before subtracting it "
     "from E14."),
    ("objects", "count", 0x5642FE, "mov word ptr [rdi + 0xe3e], cx", None,
     "uta7 platform: commit the E3E force-duration countdown only on stock ticks; its "
     "decremented register and flags are not used after the store."),
    ("objects", "lin", 0x5642F6, "subss xmm0, dword ptr [rip + 0x154afe]",
     (0x6B8DFC, 0.00017453292093705386),
     "uta7 platform: scale the sustained E3E acceleration while its countdown advances "
     "at stock cadence."),
    ("objects", "count", 0x564358, "mov word ptr [rdi + 0xe40], ax", None,
     "uta7 platform: commit the E40 force-duration countdown only on stock ticks; "
     "later code does not consume the decremented register."),
    ("objects", "lin", 0x564350, "subss xmm0, dword ptr [rip + 0x154aac]",
     (0x6B8E04, 0.001745329238474369),
     "uta7 platform: scale the sustained E40 acceleration while retaining its force "
     "magnitude and duration in stock units."),
    ("objects", "lin", 0x5643B2, "subss xmm1, dword ptr [rip + 0x154a42]",
     (0x6B8DFC, 0.00017453292093705386),
     "uta7 platform: scale the passenger acceleration in the alternate mode branch "
     "alongside its already corrected baseline acceleration."),
    ("objects", "lin", 0x5643FF, "mulss xmm0, dword ptr [rip + 0x154ad9]",
     (0x6B8EE0, 9.999999974752427e-07),
     "uta7 platform: scale the coupled submodel spring force before the existing "
     "rate-correct 0.996 damping."),
    ("objects", "srcx", 0x56445E, "addss xmm0, dword ptr [rdi + 0xe14]", None,
     "uta7 platform: integrate angular velocity E14 into submodel B8 with the current "
     "step duration before wrapping and clamping the angle."),
    ("objects", "pre", 0x56309A, "addss xmm0, dword ptr [rdi + 0xe14]", None,
     "uta5 platform: scale the complete positive passenger-load torque before adding "
     "it to angular velocity E14."),
    ("objects", "pre", 0x5630C3, "addss xmm1, dword ptr [rdi + 0xe14]", None,
     "uta5 platform: scale the complete opposing passenger-load torque before adding "
     "it to angular velocity E14."),
    ("objects", "count", 0x563182, "mov word ptr [rdi + 0xe3e], cx", None,
     "uta5 platform: commit the E3E force-duration countdown only on stock ticks; its "
     "temporary decremented value is unused afterwards."),
    ("objects", "lin", 0x56317A, "addss xmm0, dword ptr [rip + 0x155c7a]",
     (0x6B8DFC, 0.00017453292093705386),
     "uta5 platform: scale the sustained E3E acceleration while retaining stock force "
     "duration."),
    ("objects", "count", 0x5631E0, "mov word ptr [rdi + 0xe40], ax", None,
     "uta5 platform: commit the E40 force-duration countdown only on stock ticks "
     "alongside the existing corrected force increment."),
    ("objects", "srcx", 0x563252, "addss xmm0, dword ptr [rdi + 0xe14]", None,
     "uta5 platform: integrate angular velocity E14 into submodel B0 with the current "
     "step duration before wrapping and boundary response."),
    ("objects", "callscale", 0x482C8C, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: scale the angular limit; its XMM2 coefficient comes from "
     "the already time-correct mode table 7A82D0 minus one."),
    ("objects", "callscale", 0x482CB5, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: scale the angular limit while retaining the mode-table "
     "coefficient already corrected by mode_constants."),
    ("objects", "callblend", 0x482D3F, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the constant 0.08 approach coefficient and the "
     "constant angular limit together."),
    ("objects", "callblend", 0x482D8B, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the repeated positive-error approach's constant "
     "coefficient and limit."),
    ("objects", "callblend", 0x482DCE, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the constant-coefficient ground-height branch and "
     "angular limit."),
    ("objects", "callblend", 0x482E28, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the constant-coefficient pitch branch and angular "
     "limit."),
    ("objects", "root", 0x482E83, "movss xmm3, dword ptr [rip + 0x1f6ad5]", None,
     "Camera pitch velocity: take the stock-period root of the shared 0.98 damping "
     "factor used by all three magnitude thresholds."),
    ("objects", "callblend", 0x482F1D, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the first magnitude-threshold approach and its "
     "angular limit."),
    ("objects", "callblend", 0x482F4C, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the additional positive-error approach and its "
     "angular limit."),
    ("objects", "callblend", 0x482F84, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the second magnitude-threshold approach and its "
     "angular limit."),
    ("objects", "callblend", 0x482FB3, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the additional second-threshold approach and its "
     "angular limit."),
    ("objects", "callscale", 0x482FF1, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera pitch approach: correct the angular cap only; the coefficient is the "
     "already time-correct 7A82D0 mode-table value minus one."),
    ("objects", "callscale", 0x48306C, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera state-2 pitch approach: correct the angular cap only, retaining the "
     "already corrected mode-table coefficient."),
    ("objects", "callscale", 0x4830DF, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera state-5 pitch approach: correct the angular cap only, retaining the "
     "already corrected mode-table coefficient."),
    ("objects", "callscale", 0x483137, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera state-7/11 pitch approach: correct the angular cap only, retaining the "
     "already corrected 7A82D8 mode-table coefficient."),
    ("objects", "callscale", 0x483189, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera scripted pitch approach: correct the angular cap only, retaining the "
     "already corrected mode-table coefficient."),
    ("objects", "gatefn", 0x475E60, "push rbx", None,
     "Camera transition program: advance the 32-sample cursor, accumulated weight, "
     "seven pose approaches and dependent derived camera pose together at stock "
     "cadence."),
    ("objects", "lin", 0x36763A, "movss xmm2, dword ptr [rip + 0x30b2ea]",
     (0x67292C, 0.20000000298023224),
     "cKiType fading appearance: scale the shared 0.2 alpha increment used by "
     "D20/D24/D28 before the three unit clamps."),
    ("objects", "lin", 0x566398, "addss xmm0, dword ptr [rip + 0x10ba74]", (0x671E14, 2.0),
     "uta9 moving platform: scale its constant upward Y step before the 65-unit height "
     "clamp."),
    ("objects", "lin", 0x5663C3, "subss xmm0, dword ptr [rip + 0x10f6ad]", (0x675A78, 5.0),
     "uta9 moving platform: scale its downward Y step before clamping to the saved "
     "lower height."),
    ("objects", "lin", 0x566409, "movss xmm3, dword ptr [rip + 0x10b9f7]", (0x671E08, 0.5),
     "uta9 moving platform: scale the shared half-unit X/Z tracking step; retain the "
     "20-unit spatial dead zone and endpoint clamps."),
    ("objects", "lin", 0x566725, "subss xmm0, dword ptr [rip + 0x10b6e7]", (0x671E14, 2.0),
     "uta9 sinking platform: scale its constant two-unit downward Y step while motion "
     "advance remains independently time-correct."),
    ("objects", "count", 0x566801, "mov word ptr [rdi + 0xe40], r9w", None,
     "uta9 platform sound clock: commit E40 only on stock ticks; all subsequent "
     "arithmetic uses the previous value saved in R8D."),
    ("objects", "notyet", 0x566814, "cmp r8d, eax", 0x56683F,
     "uta9 periodic platform sound: force the modulo comparison's not-due branch "
     "between stock ticks so a held E40 cannot replay the same sound."),
    ("objects", "blend", 0x46CF46, "movss xmm7, dword ptr [rip + 0x2059de]",
     (0x67292C, 0.20000000298023224),
     "Camera follower: correct the shared 0.2 easing coefficient for both target XYZ "
     "and camera XYZ approaches."),
    ("objects", "blend", 0x46D174, "movss xmm2, dword ptr [rip + 0x2057b0]",
     (0x67292C, 0.20000000298023224),
     "Camera alternate follower: correct the shared 0.2 easing coefficient for target "
     "XYZ, keeping derived orientation spatial."),
    ("objects", "blend", 0x46D378, "movss xmm6, dword ptr [rip + 0x2055ac]",
     (0x67292C, 0.20000000298023224),
     "Camera return follower: correct the shared 0.2 target XYZ and camera XY easing "
     "coefficient."),
    ("objects", "blend", 0x46D507, "mulss xmm3, dword ptr [rip + 0x208521]",
     (0x675A30, 0.30000001192092896),
     "Camera return follower: correct the separate 0.3 camera-Z easing coefficient."),
    ("objects", "gatefn", 0x4A8B50, "mov qword ptr [rsp + 8], rbx", None,
     "Coupled model tether: evaluate spring acceleration, velocity friction, "
     "sign-crossing stop, position integration, bounds and settlement together at "
     "stock cadence."),
    ("objects", "gatefn", 0x330B90, "mov rax, rsp", None,
     "Custom motion program: advance its independent 1344 clock, sampled root delta, "
     "vertical calibration and dependent path interpolation together at stock cadence."),
    ("objects", "gatefn", 0x5ADF40, "sub rsp, 0x38", None,
     "Paired sliding panels: preserve the complete coupled opening/closing movement, "
     "endpoint clamps and saved-flag completion events at stock cadence."),
    ("objects", "gatefn", 0x5FD490, "sub rsp, 0x38", None,
     "Paired sliding panels: preserve both panels' opposing motion, endpoint clamps "
     "and saved-flag completion events at stock cadence."),
    ("objects", "gatefn", 0x221190, "mov qword ptr [rsp + 8], rbx", None,
     "Linked sweeping beam: preserve growth, angle sweep, six-tick sound clock, "
     "collision segment and fade state together at stock cadence."),
    ("objects", "blend", 0x567A83, "mulss xmm1, dword ptr [rip + 0x10a379]",
     (0x671E04, 0.10000000149011612),
     "utaa linked alpha: correct the 0.1 appearance easing coefficient after the "
     "motion-frame threshold."),
    ("objects", "lin", 0x567DB0, "subss xmm0, dword ptr [rip + 0x10ab74]",
     (0x67292C, 0.20000000298023224),
     "utaa linked alpha: scale the 0.2 fade step before its zero clamp."),
    ("objects", "blend", 0x5682CB, "mulss xmm1, dword ptr [rip + 0x109b31]",
     (0x671E04, 0.10000000149011612),
     "utaa alternate linked appearance: correct the 0.1 approach coefficient while "
     "preserving motion-frame thresholds."),
    ("objects", "blend", 0x568EF9, "mulss xmm1, dword ptr [rip + 0x108f03]",
     (0x671E04, 0.10000000149011612),
     "utaa alternate linked appearance: correct the 0.1 approach coefficient after "
     "frame fifty."),
    ("objects", "blend", 0x56AFF4, "mulss xmm1, dword ptr [rip + 0x106e08]",
     (0x671E04, 0.10000000149011612),
     "utab linked alpha: correct the 0.1 approach coefficient after frame fifty."),
    ("objects", "blend", 0x56B6A1, "mulss xmm1, dword ptr [rip + 0x10675b]",
     (0x671E04, 0.10000000149011612),
     "utab linked alpha: correct the 0.1 approach coefficient after frame fifty in the "
     "alternate update."),
    ("objects", "blend", 0x56889C, "mulss xmm1, dword ptr [rip + 0x1113d0]",
     (0x679C74, 0.4000000059604645),
     "utaa linked appearance: correct the 0.4 approach coefficient after frame twenty."),
    ("objects", "blend", 0x56A949, "mulss xmm1, dword ptr [rip + 0x10f323]",
     (0x679C74, 0.4000000059604645),
     "utab linked appearance: correct the 0.4 approach coefficient after frame twenty."),
    ("objects", "pre", 0x57BE5E, "addss xmm0, dword ptr [rax]", None,
     "ut2c tracking: scale the complete normalized X motion step before position "
     "accumulation and local-space clamping."),
    ("objects", "pre", 0x57BE7B, "addss xmm0, dword ptr [rax + 8]", None,
     "ut2c tracking: scale the complete normalized Z motion step before position "
     "accumulation."),
    ("objects", "pre", 0x57C045, "addss xmm0, dword ptr [rax]", None,
     "ut2c alternate tracking: scale the complete normalized X step, retaining speed "
     "magnitude and the spatial stop threshold."),
    ("objects", "pre", 0x57C05E, "addss xmm0, dword ptr [rax + 8]", None,
     "ut2c alternate tracking: scale the complete normalized Z step before local-space "
     "bounds."),
    ("objects", "pre", 0x57C664, "addss xmm0, dword ptr [rax]", None,
     "ut2c tracking: scale the normalized X movement step in the third branch."),
    ("objects", "pre", 0x57C67D, "addss xmm0, dword ptr [rax + 8]", None,
     "ut2c tracking: scale the normalized Z movement step in the third branch."),
    ("actor", "srcblend", 0x572255, "mulss xmm1, xmm7", None,
     "Scripted cutscene alignment loop: correct its variable X approach coefficient on "
     "each actual wait(1) pass; the initial single alignment update stays in stock "
     "units."),
    ("actor", "srcblend", 0x572275, "mulss xmm0, xmm7", None,
     "Scripted cutscene alignment loop: correct its variable Z approach coefficient; "
     "the loop turn already uses the globally corrected 2DA510 helper."),
    ("actor", "count", 0x4B320B, "add word ptr [rax + 0x1c], cx", "down",
     "Area-gated event delay: count the positive +1C duration down only on stock "
     "ticks; a held tick must retain the not-complete JNE branch."),
    ("actor", "count", 0x4B323E, "mov byte ptr [rax + 0x111], cl", None,
     "Event cooldown +111: commit the decremented byte only on stock ticks; the "
     "function returns immediately after the store."),
    ("actor", "count", 0x4B33C0, "mov byte ptr [rbx + 0xf1], al", None,
     "Periodic positional sound: commit its thirty-tick cooldown only on stock ticks; "
     "the zero test before it schedules the next sound."),
    ("actor", "count", 0x4C1194, "inc dword ptr [rcx + 8]", None,
     "Script prompt timeout: advance its +8 frame clock only on stock ticks, retaining "
     "the 300-frame timeout."),
    ("actor", "count", 0x4C15AE, "inc dword ptr [rax + 8]", None,
     "Script prompt timeout: advance the first branch's +8 duration clock only on "
     "stock ticks before the 240/600-frame limits."),
    ("actor", "count", 0x4C1695, "inc dword ptr [rax + 8]", None,
     "Script prompt timeout: advance the alternate branch's +8 duration clock only on "
     "stock ticks."),
    ("actor", "count", 0x4C1A58, "sub eax, 1",
     (0x4C1A51,0x4C1A5B,(0x4C1A51,0x4C1A54,0x4C1A56,0x4C1A58),None),
     "Script prompt countdown: gate the register decrement, store back to the same +8 "
     "field, and preserve the not-complete JNE outcome on a held tick."),
    ("objects", "count", 0x229F07, "mov word ptr [rsi + 0xe3c], di", None,
     "ut9a: pace the E3C sine-wave sample clock; its temporary DI is discarded "
     "immediately and the later branch uses the preserved 1090 comparison."),
    ("objects", "lin", 0x22A05D, "addss xmm0, dword ptr [rip + 0x44b9df]", (0x675A44, 1.5),
     "ut9a: scale the 1.5 growth of the bounded player-relative radial offset; the "
     "resulting X/Z positions are rebuilt from the player's position each update."),
    ("objects", "count", 0x22A289, "mov word ptr [rsi + 0xe3c], di", None,
     "ut9a alternate: pace its E3C sine-wave sample clock."),
    ("objects", "lin", 0x22A2C0, "addss xmm0, dword ptr [rip + 0x44f938]",
     (0x679C00, 0.03490658476948738),
     "ut9a alternate: scale the continuous two-degree yaw step before wrapping."),
    ("objects", "lin", 0x21D835, "addss xmm0, dword ptr [rip + 0x4543cb]", (0x671C08, 1.0),
     "ut52: scale the one-unit upward movement before its ceiling clamp."),
    ("objects", "count", 0x21D9E7, "sub dword ptr [rbx + 0x1098], 1", None,
     "ut52: pace the recurring sound delay and preserve the JNS continuation on held "
     "ticks."),
    ("objects", "count", 0x21DA75, "sub dword ptr [rbx + 0x1094], 1", None,
     "ut52: pace the post-impact wait, preserving JNS on held ticks."),
    ("objects", "count", 0x21DC02, "sub dword ptr [rbx + 0x1094], 1", None,
     "ut52: pace the descending-phase timeout and retain its JNS continuation."),
    ("objects", "count", 0x21DCC8, "sub dword ptr [rbx + 0x1098], 1", None,
     "ut52: pace the alternate recurring sound delay with JNS continuation."),
    ("objects", "lin", 0x56E68A, "addss xmm0, dword ptr [rip + 0x103776]", (0x671E08, 0.5),
     "utb5: scale the half-unit rise while every linked input state is complete."),
    ("objects", "count", 0x56E72F, "mov word ptr [rbx + 0xe3c], ax", None,
     "utb5: hold the 300-tick delay store; the pre-decrement zero test drives the "
     "phase change."),
    ("objects", "lin", 0x56E74C, "addss xmm0, dword ptr [rip + 0x1036b4]", (0x671E08, 0.5),
     "utb5: scale the half-unit reset rise before the saved-height clamp; motion "
     "advancement stays time corrected."),
    ("objects", "count", 0x4FFBEA, "sub al, bpl",
     (0x4FFBDF,0x4FFBED,(0x4FFBDF,0x4FFBE6,0x4FFBE8,0x4FFBEA),None,-1),
     "cBamboo: BPL is the callee-saved positive unit set in the prologue; pace the "
     "five-tick register decrement and synthesize not-complete JNE flags on held "
     "ticks."),
    ("objects", "count", 0x56C05A, "mov word ptr [rdi + 0xe3c], dx", None,
     "utaf: pace the E3C fifteenth-tick sound clock."),
    ("objects", "notyet", 0x56C067, "cmp dx, 0xf", 0x56C08A,
     "utaf: suppress the fifteenth-tick sound equality on held clock ticks."),
    ("objects", "count", 0x57DC05, "mov word ptr [rbx + 0xe3e], ax", None,
     "ut32: hold the forty-tick fast-motion duration store; the old-zero test selects "
     "the normal speed."),
    ("objects", "count", 0x583C38, "mov byte ptr [rbx + 0x1078], r8b", None,
     "utcc: pace the seven-tick effect interval's byte clock."),
    ("objects", "notyet", 0x583C45, "cmp ecx, eax", 0x583C83,
     "utcc: suppress the modulo-seven event on held clock ticks."),
    ("objects", "count", 0x62FB76, "mov byte ptr [rcx + 0x1103], al", None,
     "et30: pace the one-to-eight-tick randomized effect cooldown; AL is then "
     "overwritten with the false return."),
    ("objects", "count", 0x4980BE, "inc byte ptr [rdi + 0x11b4]", None,
     "cItemObj: pace the byte UV phase; material UV is freshly calculated from view "
     "direction plus this clock."),
    ("objects", "count", 0x497F29, "movss dword ptr [rbx + 0x11d8], xmm2", None,
     "cItemObj: commit the countdown-coupled alpha decrement only at stock cadence, "
     "using the original remaining-duration formula."),
    ("objects", "count", 0x497F4E, "mov dword ptr [rbx + 0x11c0], eax", None,
     "cItemObj: hold the remaining alpha duration store to match its dependent alpha "
     "decrement."),
    ("objects", "blend", 0x56598A, "mulss xmm1, dword ptr [rip + 0x10c472]",
     (0x671E04, 0.10000000149011612),
     "uta8: correct the 0.1 X-position approach coefficient."),
    ("objects", "blend", 0x5659AE, "mulss xmm1, dword ptr [rip + 0x10c44e]",
     (0x671E04, 0.10000000149011612),
     "uta8: correct the 0.1 Z-position approach coefficient."),
    ("objects", "count", 0x56D377, "movss dword ptr [rbx + 0x1070], xmm1", None,
     "utb2: commit the selected downward force only on stock ticks as part of its "
     "coupled spring update."),
    ("objects", "count", 0x56D3A4, "movss dword ptr [rbx + 0x1070], xmm2", None,
     "utb2: commit the spring force and 0.96 damping together at stock cadence."),
    ("objects", "count", 0x56D3B1, "movss dword ptr [rax + 4], xmm2", None,
     "utb2: commit the dependent Y integration at the same stock cadence as its "
     "velocity."),
    ("objects", "zfirst", 0x22EC9B, "movss xmm0, dword ptr [rbx + 0x10e8]", None,
     "utbe: zero the acceleration step between stock ticks before velocity "
     "accumulation and its terminal-speed clamp."),
    ("objects", "srcx", 0x22ECD7, "addss xmm0, dword ptr [rbx + 0x10e4]", None,
     "utbe: integrate the resulting velocity as a per-frame Y movement step."),
    ("objects", "dst", 0x2E38E4, "movss xmm0, dword ptr [rcx + rsi + 0x7a0078]", None,
     "et08: scale the selected table acceleration after loading it and before adding "
     "to the 1144 rise rate."),
    ("objects", "pre", 0x2E3934, "addss xmm0, dword ptr [rcx + 4]", None,
     "et08: scale the complete rise-rate movement step before accumulating the "
     "submodel height."),
    ("objects", "count", 0x2EC719, "movss dword ptr [rbx + 0xe54], xmm0", None,
     "et41: commit the selected 0.2/0.8 vertical acceleration only at stock cadence; "
     "the motion consumer already scales velocity integration."),
    ("objects", "count", 0x2ECCC9, "movss dword ptr [rbx + 0xe54], xmm0", None,
     "et42: commit the corresponding selected vertical acceleration only at stock "
     "cadence."),
    ("objects", "src", 0x49FDCA, "addss xmm0, xmm6", None,
     "cKakejiku: scale the animation-switch elapsed frame clock's unit increment; XMM6 "
     "remains the stock constant used elsewhere."),
    ("objects", "count", 0x4E4106, "dec dword ptr [rbx]", None,
     "ut0a: pace each of the four ninety-tick linked interaction delays while "
     "retaining the per-update target census."),
    ("objects", "zfirst", 0x4F08A0, "movss xmm0, dword ptr [rbx + 0x10e0]", None,
     "ut21: zero the angular acceleration between stock ticks before the speed cap."),
    ("objects", "src", 0x4F08D5, "addss xmm0, dword ptr [rbx + 0x10e4]", None,
     "ut21: integrate the resulting angular velocity as a time-scaled yaw step."),
    ("objects", "count", 0x4F08F4, "mov word ptr [rbx + 0xe3c], cx", None,
     "ut21: pace the E3C forty-five-tick positional sound clock."),
    ("objects", "notyet", 0x4F0928, "cmp ecx, eax", 0x4F0879,
     "ut21: suppress the periodic sound equality between stock clock ticks."),
    ("objects", "src", 0x2360B2, "subss xmm0, xmm1", None,
     "utf6: scale the complete turn step of one revolution per E3E stock duration "
     "before wrapping."),
    ("objects", "count", 0x236121, "sub ax, r14w",
     (0x236115,0x236125,(0x236115,0x23611C,0x23611F,0x236121),None,-1),
     "utf6: R14W is the positive unit initialized in the prologue; pace the E3C "
     "register countdown and preserve its JNE continuation."),
    ("objects", "notyet", 0x236193, "cmp ecx, eax", 0x2361C0,
     "utf6: prevent the thirty-tick sound equality from recurring while the already "
     "gated E40 clock is held."),
    ("objects", "notyet", 0x23623C, "cmp word ptr [rbx + 0xe3c], 0x5a", 0x23627B,
     "utf6: emit the ninety-tick sound only on a stock timer tick."),
    ("objects", "notyet", 0x23627B, "cmp word ptr [rbx + 0xe3c], 0x3c", 0x2362BC,
     "utf6: emit the sixty-tick sound only on a stock timer tick."),
    ("objects", "notyet", 0x2362BC, "cmp word ptr [rbx + 0xe3c], 0x1e", 0x236814,
     "utf6: emit the thirty-tick sound only on a stock timer tick."),
    ("flag", "count", 0x4BDA0A, "add dword ptr [rbp + 8], esi", None,
     "Movie continuous rumble PWM: pace the phase increment in the port's 60-Hz "
     "context. Its initial phase is zero, intensity is a byte or its interpolation, "
     "and every crossing subtracts 255, so a held phase remains below 255 and cannot "
     "repeat a pulse. Discrete movie keyframe events remain driven by the external "
     "playhead."),
    ("actor", "count", 0x238BDC, "sub eax, 1",
     (0x238BD2,0x238BDF,(0x238BD2,0x238BD8,0x238BDA,0x238BDC),None),
     "Shared actor death delay: gate the register decrement and preserve JNE on held "
     "ticks before its completion callback."),
    ("actor", "count", 0x23AED5, "dec word ptr [rbp + 0x232]", None,
     "Battle manager: pace the +232 wait; completion clears both the wait and its +234 "
     "active state before calling the next stage."),
    ("actor", "count", 0x23D789, "inc dword ptr [rbx + 0x40]", None,
     "Battle manager: pace the active battle elapsed-time counter while retaining its "
     "pause and inactive guards."),
    ("actor", "count", 0x303B7C, "mov byte ptr [rbx + 0x1276], al", None,
     "Shared actor fade: pace the byte duration from which D20 XYZ alpha is freshly "
     "calculated each update."),
    ("actor", "count", 0x30417B, "mov byte ptr [rdi + 0x1191], al", None,
     "Shared actor visibility fade: commit the clamped two-unit alpha step at stock "
     "cadence before byte quantization can lose a fractional step."),
    ("actor", "count", 0x304181, "mov byte ptr [rdi + 0x1190], al", None,
     "Shared actor visibility fade: commit the duplicate material alpha byte at the "
     "same cadence as its +1191 source."),
    ("actor", "count", 0x305ABA, "mov byte ptr [rbx + 0x1222], cl", None,
     "Shared actor child fade: commit the clamped eight-unit alpha step at stock "
     "cadence; later visibility checks reload the stored byte."),
    ("actor", "count", 0x309104, "mov word ptr [rdi + 0xe3e], r8w", None,
     "Shared actor positional sound: pace the three-tick E3E interval clock."),
    ("actor", "notyet", 0x30910C, "cmp ecx, eax", 0x309147,
     "Suppress the corresponding modulo-three sound equality while the E3E clock is "
     "held."),
    ("actor", "count", 0x309257, "mov word ptr [rdi + 0xe3e], r8w", None,
     "Alternate positional sound: pace its three-tick E3E interval clock."),
    ("actor", "notyet", 0x30925F, "cmp ecx, eax", 0x30929A,
     "Suppress the alternate modulo-three sound equality while the E3E clock is held."),
    ("actor", "count", 0x3112CB, "inc byte ptr [rbx + 0x131e]", None,
     "Linked-motion actor: pace the sixteen-update launch delay; motion advancement "
     "remains independently time corrected."),
    ("actor", "count", 0x311A67, "mov byte ptr [rbx + 0xe37], cl", None,
     "Linked-motion actor: E37 values two through forty-two are a forty-update wait, "
     "so hold this state-counter store between stock ticks."),
    ("actor", "count", 0x311C01, "inc byte ptr [rbx + 0x131e]", None,
     "Linked-motion actor: pace the forty-five-tick recurring sound interval; firing "
     "resets the clock to zero immediately."),
    ("actor", "count", 0x3121C1, "inc byte ptr [rbx + 0x131e]", None,
     "Alternate linked-motion actor: pace its forty-five-tick recurring sound interval "
     "with the same immediate clock reset."),
    ("actor", "gatefn", 0x311FA0, "push rbx", None,
     "Linked-motion actor: the closed view-distance-gated periodic-effect sampler has "
     "one direct caller, 311EC3, which discards its result. Run its counter, "
     "old-counter threshold and reset together at stock cadence."),
    ("actor", "lin", 0x316ACB, "subss xmm0, dword ptr [rip + 0x35b135]", (0x671C08, 1.0),
     "Shared actor: scale the continuous one-unit sinking movement under its active "
     "flags."),
    ("actor", "count", 0x316FEF, "mov byte ptr [rbx + 0xa], al", None,
     "Appearance effect record: pace the selected byte hold delay; the old-zero branch "
     "resets its state and computed AL is discarded."),
    ("actor", "blend", 0x3048F3, "mulss xmm1, dword ptr [rip + 0x372cf5]",
     (0x6775F0, 0.05000000074505806),
     "Shared actor tracking: correct the 0.05 X approach toward the fresh linked-model "
     "target."),
    ("actor", "blend", 0x304915, "mulss xmm1, dword ptr [rip + 0x372cd3]",
     (0x6775F0, 0.05000000074505806),
     "Shared actor tracking: correct the corresponding 0.05 Z approach."),
    ("actor", "blend", 0x30D468, "mulss xmm1, dword ptr [rip + 0x36a180]",
     (0x6775F0, 0.05000000074505806),
     "Shared actor return state: correct its repeated 0.05 X-position approach toward "
     "the stored target."),
    ("actor", "blend", 0x30D48C, "mulss xmm1, dword ptr [rip + 0x36a15c]",
     (0x6775F0, 0.05000000074505806),
     "Shared actor return state: correct its repeated 0.05 Z-position approach."),
    ("actor", "gatefn", 0x3D3400, "mov qword ptr [rsp + 8], rbx", None,
     "Eight-slot ballistic effect controller: advance each slot's position, "
     "acceleration, completion test and age together at stock cadence. Its sole direct "
     "caller is the frame dispatcher and uses only state mutations."),
    ("menu", "pre", 0x40CEAC, "addss xmm1, dword ptr [rax + 0x20]", None,
     "UI page transition: scale the completed spacing-over-duration step before adding "
     "it to the first row's X position."),
    ("menu", "pre", 0x40CED3, "addss xmm7, dword ptr [rax + 0x20]", None,
     "UI page transition: scale the corresponding second-row X step after division; "
     "the shared spacing constant keeps its original value."),
    ("menu", "count", 0x4385A2, "mov word ptr [rbx + 4], ax", None,
     "Confirmation menu: pace the fifteen-tick exit delay; selection commands remain "
     "on their input-event paths."),
    ("objects", "srcroot", 0x2E4171, "mulss xmm1, dword ptr [rip + 0x38dc8b]", None,
     "et0d dismissal: compose the 0.1 alpha decay across fractional stock ticks before "
     "its 0.2 terminal clamp."),
    ("objects", "src", 0x23705C, "subss xmm0, xmm1", None,
     "utf6 alternate attempt: scale the complete submodel turn step before wrapping, "
     "preserving its duration denominator."),
    ("objects", "count", 0x237087, "sub ax, r14w",
     (0x23707B,0x23708B,(0x23707B,0x237082,0x237085,0x237087),None,-1),
     "utf6 alternate attempt: R14W is the positive unit; pace the E3C register "
     "countdown and preserve the not-complete JNE outcome."),
    ("objects", "srcroot", 0x33E1CF, "mulss xmm6, dword ptr [rip + 0x33475d]", None,
     "Carry object floor approach: compose the old-Y weight 0.92 while the fresh floor "
     "query continues each update."),
    ("objects", "blend", 0x33E1DC, "mulss xmm0, dword ptr [rip + 0x33ba8c]",
     (0x679C70, 0.07999999821186066),
     "Carry object floor approach: use the complementary compounded 0.08 weight on the "
     "fresh floor-clamped Y target."),
    ("objects", "srcroot", 0x49970F, "mulss xmm6, dword ptr [rip + 0x1d921d]", None,
     "Item object floor approach: compose the old-Y weight 0.92 while retaining its "
     "fresh collision and floor query."),
    ("objects", "blend", 0x49971C, "mulss xmm0, dword ptr [rip + 0x1e054c]",
     (0x679C70, 0.07999999821186066),
     "Item object floor approach: use the complementary compounded 0.08 weight on the "
     "fresh floor-clamped Y target."),
    ("objects", "srcroot", 0x365985, "mulss xmm0, dword ptr [rip + 0x30c483]", None,
     "vte2 deformation: compose the 0.7 release-amplitude decay; every matrix is "
     "rebuilt from the object's base orientation before applying that amplitude."),
    ("objects", "count", 0x368B83, "mulss xmm0, dword ptr [rip + 0x30cf9d]", "factor",
     "cKiType014: alternate the collision-driven tilt target's sign once per stock "
     "period before the already corrected turn approach."),
    ("objects", "count", 0x369454, "mulss xmm0, dword ptr [rip + 0x30c6cc]", "factor",
     "Alternate scenery collision response: alternate the tilt target's sign once per "
     "stock period before the corrected turn approach."),
    ("objects", "count", 0x369E40, "mulss xmm0, dword ptr [rip + 0x30bce0]", "factor",
     "Third scenery collision response: alternate the tilt target's sign once per "
     "stock period before the corrected turn approach."),
    ("objects", "src", 0x4A745B, "subss xmm0, xmm1", None,
     "cScrGear: scale the complete angular-velocity product before subtracting it from "
     "roll and wrapping."),
    ("objects", "count", 0x517102, "mov byte ptr [rbx + 0xd78], al", None,
     "cObjPillar: commit the clamped integer alpha approach at stock cadence, "
     "preserving its original quantized 0.2 step and later stored-byte tests."),
    ("objects", "count", 0x22FF88, "mov byte ptr [rbx + 0x1208], al", None,
     "utd1: pace the recurring three-tick effect counter."),
    ("objects", "notyetneg", 0x22FF8E, "cmp cl, 1", 0x22FFBF,
     "utd1: the effect compares old CL with one; take its JLE hold path between stock "
     "ticks to prevent repeated spawns."),
    ("objects", "count", 0x509D64, "movss dword ptr [rax], xmm0", None,
     "ut1b shake: hold the sampled X position between stock ticks."),
    ("objects", "count", 0x509D84, "movss dword ptr [rax + 4], xmm0", None,
     "ut1b shake: hold the sampled Y position between stock ticks."),
    ("objects", "count", 0x509DA5, "movss dword ptr [rax + 8], xmm0", None,
     "ut1b shake: hold the sampled Z position between stock ticks."),
    ("objects", "count", 0x509DAA, "sub dword ptr [rbx + 0x109c], 1", None,
     "ut1b shake: pace its ten-tick duration together with the three position commits "
     "and preserve the unfinished JNE branch."),
    ("menu", "gatefn", 0x15F000, "mov qword ptr [rsp + 8], rbx", None,
     "Held-input slider: run acceleration counters, quantized volume increments, clamp "
     "resets and repeat sound together at stock cadence; all three callers discard the "
     "result."),
    ("menu", "src", 0x40CC05, "subss xmm1, xmm2", None,
     "Page transition: scale the complete spacing/duration X step on the first page."),
    ("menu", "src", 0x40CC30, "subss xmm1, xmm7", None,
     "Page transition: scale the complete spacing/duration X step on the second page."),
    ("actor", "count", 0x455AB6, "inc dword ptr [rbx - 0x10]", None,
     "Sound mixer: pace each active slot's age while middleware status and maintenance "
     "continue each update."),
    ("actor", "count", 0x455B13, "mov word ptr [rbx - 2], dx", None,
     "Sound mixer: commit the clamped integer fade at stock cadence while the "
     "middleware volume application remains live."),
    ("actor", "gatefn", 0x444DE0, "push rbx", None,
     "Sound instance controller: run the pre-start delay, play age and state "
     "transitions together at stock cadence; callers discard the result and mixer "
     "maintenance stays in 455A60."),
    ("objects", "gatefn", 0x22DAD0, "mov qword ptr [rsp + 8], rbx", None,
     "utbc airborne physics: run forces, contact correction, gravity, original 0.99 "
     "drag and position integration together at stock cadence; its caller discards the "
     "result."),
    ("objects", "pre", 0x33BD04, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "Ball object: scale the completed wind X impulse before accumulating persistent "
     "E20 velocity."),
    ("objects", "pre", 0x33BD0C, "addss xmm1, dword ptr [rdi + 0xe28]", None,
     "Ball object: scale the completed wind Z impulse before accumulating persistent "
     "E28 velocity."),
    ("objects", "src", 0x33BF86, "subss xmm2, xmm0", None,
     "Ball object airborne physics: scale the complete random acceleration plus 0.2 "
     "gravity before subtracting it from vertical velocity."),
    ("objects", "pre", 0x33BFA7, "addss xmm1, xmm2", None,
     "Ball object airborne physics: scale the floor spring acceleration before adding "
     "it to vertical velocity."),
    ("objects", "src", 0x33BFC7, "addss xmm0, dword ptr [rdi + 0x1174]", None,
     "Ball object airborne physics: integrate vertical velocity by the elapsed share "
     "of a stock tick; its 0.98 drag is already compounded by decay_factors."),
    ("objects", "src", 0x468224, "addss xmm0, xmm1", None,
     "Camera zoom: integrate the retained zoom velocity by the elapsed share of a "
     "stock tick."),
    ("objects", "srcroot", 0x468230, "mulss xmm1, xmm6", None,
     "Camera zoom: compound its persistent velocity's 0.9 decay."),
    ("objects", "srcroot", 0x468259, "mulss xmm1, dword ptr [rip + 0x209bab]", None,
     "Camera distance: compound the repeated 0.6 damping below the lower range."),
    ("objects", "src", 0x468269, "addss xmm2, xmm1", None,
     "Camera distance: integrate retained distance velocity without changing that "
     "velocity's later damping input."),
    ("objects", "srcroot", 0x468284, "mulss xmm1, xmm6", None,
     "Camera distance: compound its persistent velocity's 0.9 decay."),
    ("objects", "srcroot", 0x4682F3, "mulss xmm0, dword ptr [rip + 0x217de1]", None,
     "Camera distance: compound the 0.94 release damping while neither held zoom "
     "command is active."),
    ("objects", "pre", 0x46832D, "addss xmm0, dword ptr [rbx + 0x1b0]", None,
     "Camera pitch: scale the fresh velocity step before adding persistent pitch; "
     "input acceleration already consumes B6AC38."),
    ("objects", "pre", 0x468345, "addss xmm0, dword ptr [rbx + 0x1b4]", None,
     "Camera yaw: scale the fresh velocity step before adding persistent yaw; input "
     "acceleration already consumes B6AC38."),
    ("objects", "srcroot", 0x468365, "mulss xmm2, dword ptr [rip + 0x20fcb3]", None,
     "Camera pitch: compound 0.85 velocity damping."),
    ("objects", "srcroot", 0x46836D, "mulss xmm0, dword ptr [rip + 0x20fcab]", None,
     "Camera yaw: compound 0.85 velocity damping."),
    ("objects", "srcroot", 0x46838E, "mulss xmm2, xmm6", None,
     "Camera pitch: compound the extra 0.9 damping in the negative-state branch."),
    ("objects", "srcroot", 0x468392, "mulss xmm0, xmm6", None,
     "Camera yaw: compound the extra 0.9 damping in the negative-state branch."),
    ("objects", "srcroot", 0x4683B7, "mulss xmm2, xmm1", None,
     "Camera pitch lower clamp: compound 0.4 attenuation while velocity keeps pushing "
     "against the bound."),
    ("objects", "srcroot", 0x4683E9, "mulss xmm2, xmm1", None,
     "Camera pitch upper clamp: compound the same repeated 0.4 attenuation."),
    ("objects", "srcroot", 0x4684E9, "mulss xmm0, xmm1", None,
     "Alternate camera pitch lower clamp: compound its repeated 0.4 velocity "
     "attenuation."),
    ("objects", "srcroot", 0x468518, "mulss xmm0, xmm1", None,
     "Alternate camera pitch upper clamp: compound its repeated 0.4 velocity "
     "attenuation."),
    ("objects", "pre", 0x468698, "addss xmm0, dword ptr [rbx + 0x1c0]", None,
     "Alternate camera pitch: scale the completed input velocity before accumulating "
     "pitch."),
    ("objects", "pre", 0x4686B0, "addss xmm1, dword ptr [rbx + 0x1c4]", None,
     "Alternate camera yaw: scale the completed input velocity before accumulating "
     "yaw."),
    ("objects", "srcroot", 0x4686C8, "mulss xmm1, dword ptr [rip + 0x20a260]", None,
     "Alternate camera yaw: compound persistent velocity's 0.9 decay."),
    ("objects", "srcroot", 0x4686D8, "mulss xmm0, dword ptr [rip + 0x20a250]", None,
     "Alternate camera pitch: compound persistent velocity's 0.9 decay."),
    ("objects", "src", 0x468E40, "addss xmm0, xmm1", None,
     "Close camera zoom: integrate retained zoom velocity by elapsed time."),
    ("objects", "srcroot", 0x468E4C, "mulss xmm1, xmm3", None,
     "Close camera zoom: compound persistent velocity's 0.9 decay."),
    ("objects", "srcroot", 0x468E75, "mulss xmm1, dword ptr [rip + 0x208f8f]", None,
     "Close camera distance: compound its repeated 0.6 lower-range damping."),
    ("objects", "src", 0x468E85, "addss xmm2, xmm1", None,
     "Close camera distance: integrate velocity without changing its later damping "
     "input."),
    ("objects", "srcroot", 0x468EA0, "mulss xmm1, xmm3", None,
     "Close camera distance: compound persistent velocity's 0.9 decay."),
    ("objects", "srcroot", 0x468F0F, "mulss xmm0, dword ptr [rip + 0x2171c5]", None,
     "Close camera distance: compound 0.94 release damping."),
    ("objects", "pre", 0x468F27, "addss xmm0, dword ptr [rbx + 0x1b0]", None,
     "Close camera pitch: scale the completed input velocity before accumulating "
     "pitch."),
    ("objects", "pre", 0x468F3F, "addss xmm1, dword ptr [rbx + 0x1b4]", None,
     "Close camera yaw: scale the completed input velocity before accumulating yaw."),
    ("objects", "srcroot", 0x468F57, "mulss xmm0, dword ptr [rip + 0x20f0c1]", None,
     "Close camera yaw: compound its 0.85 velocity decay."),
    ("objects", "srcroot", 0x468F67, "mulss xmm3, dword ptr [rip + 0x20f0b1]", None,
     "Close camera pitch: compound its 0.85 velocity decay."),
    ("objects", "srcroot", 0x468F98, "mulss xmm3, xmm1", None,
     "Close camera lower clamp: compound repeated 0.4 velocity attenuation."),
    ("objects", "srcroot", 0x468FC7, "mulss xmm3, xmm1", None,
     "Close camera upper clamp: compound repeated 0.4 velocity attenuation."),
    ("objects", "pre", 0x4690CB, "addss xmm0, dword ptr [rcx + 0x258]", None,
     "Radius camera: scale retained X input velocity before accumulating radius X."),
    ("objects", "pre", 0x4690E3, "addss xmm1, dword ptr [rcx + 0x25c]", None,
     "Radius camera: scale retained Y input velocity before accumulating radius Y."),
    ("objects", "srcroot", 0x469190, "mulss xmm1, xmm3", None,
     "Radius camera lower X bound: compound repeated 0.5 attenuation of the input "
     "velocity."),
    ("objects", "srcroot", 0x4691C4, "mulss xmm0, xmm3", None,
     "Radius camera upper X bound: compound repeated 0.5 attenuation of the input "
     "velocity."),
    ("objects", "srcroot", 0x4691F1, "mulss xmm0, xmm3", None,
     "Radius camera lower Y bound: compound repeated 0.5 attenuation of the input "
     "velocity."),
    ("objects", "srcroot", 0x46921A, "mulss xmm0, xmm3", None,
     "Radius camera upper Y bound: compound repeated 0.5 attenuation of the input "
     "velocity."),
    ("objects", "srcroot", 0x46928A, "mulss xmm0, xmm3", None,
     "Second radius camera: compound the X input velocity's 0.9 idle damping."),
    ("objects", "srcroot", 0x46929E, "mulss xmm0, xmm3", None,
     "Second radius camera: compound radius X's 0.9 idle damping before integration."),
    ("objects", "srcroot", 0x4692EB, "mulss xmm0, xmm3", None,
     "Second radius camera: compound the Y input velocity's 0.9 idle damping."),
    ("objects", "srcroot", 0x4692FF, "mulss xmm0, xmm3", None,
     "Second radius camera: compound radius Y's 0.9 idle damping before integration."),
    ("objects", "pre", 0x469313, "addss xmm0, dword ptr [rcx + 0x258]", None,
     "Second radius camera: scale retained X input velocity before accumulating radius "
     "X."),
    ("objects", "pre", 0x46932B, "addss xmm1, dword ptr [rcx + 0x25c]", None,
     "Second radius camera: scale retained Y input velocity before accumulating radius "
     "Y."),
    ("objects", "srcroot", 0x469343, "mulss xmm1, dword ptr [rip + 0x21a59d]", None,
     "Second radius camera: compound Y input velocity's 0.96 decay after integration."),
    ("objects", "srcroot", 0x469353, "mulss xmm0, dword ptr [rip + 0x21a58d]", None,
     "Second radius camera: compound X input velocity's 0.96 decay after integration."),
    ("objects", "srcroot", 0x4693E0, "mulss xmm1, xmm3", None,
     "Second radius camera lower X bound: compound repeated 0.5 velocity attenuation."),
    ("objects", "srcroot", 0x469414, "mulss xmm0, xmm3", None,
     "Second radius camera upper X bound: compound repeated 0.5 velocity attenuation."),
    ("objects", "srcroot", 0x469444, "mulss xmm0, xmm3", None,
     "Second radius camera lower Y bound: compound repeated 0.5 velocity attenuation."),
    ("objects", "srcroot", 0x469475, "mulss xmm0, xmm3", None,
     "Second radius camera upper Y bound: compound repeated 0.5 velocity attenuation."),
    ("actor", "gatefn", 0x48DE00, "sub rsp, 0x48", None,
     "Input repeat controller: pace the repeated cost, three-tick repeat counter, "
     "sound and synthetic pad action together; callers discard the result."),
    ("actor", "gatefn", 0x4AF910, "push rbx", None,
     "Integer ramp: pace the startup wait, remaining duration and "
     "distance/remaining-duration request together under the original pause "
     "conditions."),
    ("objects", "src", 0x2F1776, "subss xmm0, dword ptr [rsi + 0x1110]", None,
     "et67: scale the positive speed's 1110 decrement before storing 1114."),
    ("objects", "blendr", 0x2F1824, "movaps xmm2, xmm7", None,
     "et67: compound the fresh steering target's weight 1-0.9 before its vector "
     "product; XMM7 remains available unchanged."),
    ("objects", "root", 0x2F182D, "movss xmm2, dword ptr [rip + 0x4aea4f]", None,
     "et67: compound the retained velocity's complementary 0.9 weight before its "
     "vector product."),
    ("objects", "scaledadd", 0x2F1878, "call qword ptr [rip + 0x37f582]", None,
     "et67: integrate persistent 1100 velocity by the elapsed share of a stock tick."),
    ("objects", "scaledadd", 0x2F159D, "call qword ptr [rip + 0x37f85d]", None,
     "et67: scale each active link's fresh force vector before accumulating persistent "
     "1100 velocity."),
    ("objects", "root", 0x46854B, "movss xmm4, dword ptr [rip + 0x217b89]", None,
     "Alternate camera: compound its shared 0.94 idle damping factor before either "
     "persistent velocity consumes it."),
    ("objects", "root", 0x468FFF, "movss xmm5, dword ptr [rip + 0x209929]", None,
     "Radius camera: compound the shared 0.9 idle input-velocity damping factor before "
     "both branches consume it."),
    ("objects", "root", 0x469007, "movss xmm4, dword ptr [rip + 0x21a8d9]", None,
     "Radius camera: compound the shared 0.96 radius and input-velocity decay factor "
     "before all its uses."),
    ("actor", "gatefn", 0x5541D0, "push rdi", None,
     "Periodic encounter controller: pace its elapsed stage clock, exact threshold "
     "events, three recurring spawn delays and resets together at stock cadence; its "
     "sole caller discards the result."),
    ("actor", "count", 0x4AF8C0, "dec eax",
     (0x4AF8B9,0x4AF8C2,(0x4AF8B9,0x4AF8BC,0x4AF8BE,0x4AF8C0),None),
     "Integer ramp: pace its positive startup delay before the full-amplitude request."),
    ("actor", "count", 0x491699, "inc word ptr [r8 + 0xe6]", None,
     "Dialogue controller: pace its 450-tick wait before starting the next request; "
     "the completion path switches phase to two."),
    ("objects", "gatefn", 0x476030, "mov qword ptr [rsp + 8], rbx", None,
     "Camera shake: pace both coupled amplitude decays, phase advances, wraps, and "
     "integer durations together; all callers discard the result."),
    ("objects", "count", 0x477686, "mov byte ptr [rdi + 0x182], al", None,
     "Two-player camera: pace its byte transition ramp while continuing to sample and "
     "project fresh player geometry."),
    ("objects", "blendr", 0x4776BF, "minss xmm4, xmm0", None,
     "Two-player camera: compound the capped approach weight before forming its "
     "complement and blending all six eye/view coordinates."),
    ("objects", "count", 0x477CC1, "mov byte ptr [rsi + 0x182], al", None,
     "Alternate two-player camera: pace its byte transition ramp while continuing to "
     "sample fresh player geometry."),
    ("objects", "blendr", 0x477CE9, "minss xmm2, xmm0", None,
     "Alternate two-player camera: compound the capped approach weight shared by the "
     "six eye/view coordinates and field of view."),
    # The celestial brush's per-tick update 16C7E0 (the brush object 8909C0), 2026-09-30
    ("player", "count", 0x16CA1D, "mov dword ptr [rcx], eax", None,
     "Brush techniques: hold each active technique's remaining ticks +128[id] (10, 30 "
     "or 120, copied from +124 when one is recognized) between stock ticks."),
    ("player", "notyet", 0x16CA1F, "test eax, eax", 0x16CA43,
     "Brush techniques: between stock ticks the held count's decremented copy in EAX "
     "must not end the technique; take the still-active path."),
    ("player", "count", 0x16CA8E, "sub eax, 1",
     (0x16CA84,0x16CA91,(0x16CA84,0x16CA8A,0x16CA8C,0x16CA8E),None),
     "Brush: pace the 300-tick window +D34 (174DB0) after which the repeat count +D30 "
     "resets."),
    ("player", "count", 0x16CF76, "dec eax",
     (0x16CF6F,0x16CF78,(0x16CF6F,0x16CF72,0x16CF74,0x16CF76),None),
     "Brush state 4: pace the wait +68 (60 ticks from 171940/174DB0) before the "
     "recognized technique is applied."),
    ("player", "count", 0x16D132, "dec eax",
     (0x16D12B,0x16D134,(0x16D12B,0x16D12E,0x16D130,0x16D132),None),
     "Brush state 5: pace the 60-tick wait +6C that evaluation mode 6 (174740) arms, "
     "before state 6 closes the brush."),
    ("player", "count", 0x16D28A, "dec eax",
     (0x16D27C,0x16D28C,(0x16D27C,0x16D282,0x16D284,0x16D28A),None),
     "Brush idle: pace the 20-tick cooldown +E28 after the brush closes, before it can "
     "open again."),
    ("player", "count", 0x16D752, "sub eax, 1",
     (0x16D748,0x16D755,(0x16D748,0x16D74E,0x16D750,0x16D752),None),
     "Brush drawing: pace the delay +21B4 that 1709B0 arms (with +21B0 = 1) before it "
     "signals +21B8 = 1."),
    ("player", "count", 0x16F097, "inc dword ptr [rsi + 0x21dc]", None,
     "Brush: hold the counter +21DC whose multiples of 30 play sound 0x74, so the "
     "sound repeats once a stock second."),
    ("player", "notyet", 0x16F06A, "cmp ecx, eax", 0x16F097,
     "Brush: the modulo-30 test reads the old +21DC; between stock ticks take the "
     "no-sound path so a held count plays 0x74 once."),
    ("player", "count", 0x170396, "dec dword ptr [rsi + 0x1c]", None,
     "Brush timed effect: pace the duration +1C (100 to 370 ticks from 174DB0, by the "
     "effect mode +18) before it stops."),
    ("player", "blend", 0x16F75F, "movss xmm5, dword ptr [rip + 0x62a099]", (0x799800, 0.25),
     "Brush strokes: each entry's +0C approaches +10 by 0.25 of the gap a tick (at "
     "least 0.5, clamped): the approach's factor."),
    ("player", "lin", 0x16F767, "movss xmm6, dword ptr [rip + 0x62a095]", (0x799804, 0.5),
     "Brush strokes: the approach's minimum step 0.5 a tick."),
    ("player", "lin", 0x16F76F, "movss xmm4, dword ptr [rip + 0x5057e1]", (0x674F58, 3.0),
     "Brush strokes: each entry's global +84565C grows by 3 a tick up to +845660."),
    # Camera modes (dispatched by 476B00, 4760E0 and 475C70), 2026-09-30. Their 2DA570
    # approaches are the survey's "camera: read as a whole elsewhere" rows: a constant
    # factor gets callblend, a factor from a mode table mode_constants.h already
    # corrects gets callscale (the limit only), as 482C8C/482D3F.
    # 478450
    ("objects", "count", 0x47881B, "dec ax",
     (0x47880F,0x47881E,(0x47880F,0x478816,0x478819,0x47881B),None),
     "Camera mode 478450: pace the 90-tick hold +292 set when the view is blocked."),
    ("objects", "callblend", 0x478A73, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 478450: turn yaw +1B4 behind the target: constant 0.3 approach and "
     "its 0.0349 limit."),
    ("objects", "count", 0x478A8A, "dec word ptr [rdi + 0x410]", None,
     "Camera mode 478450: pace the 90-tick turn-behind window +410."),
    ("objects", "callblend", 0x478B19, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 478450: yaw toward the requested +39C: constant 0.1 approach and its "
     "limit."),
    ("objects", "count", 0x478B1E, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 478450: pace the yaw request's duration +398."),
    ("objects", "callblend", 0x478B53, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 478450: pitch +1B0 toward +3A4: constant 0.2 approach and its limit."),
    ("objects", "count", 0x478B58, "dec word ptr [rdi + 0x3a0]", None,
     "Camera mode 478450: pace the pitch request's duration +3A0 (30 ticks on entry)."),
    ("objects", "callblend", 0x478B8A, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 478450 (mode 9): pitch toward -0.314: constant 0.2 approach and its "
     "0.0105 limit."),
    # 47C9D0
    ("objects", "count", 0x47CFA7, "dec ax",
     (0x47CF7E,0x47CFAA,(0x47CF7E,0x47CF85,0x47CF89,0x47CF8C,0x47CF8E,0x47CF96,0x47CF9E,0x47CFA2,0x47CFA5,0x47CFA7),None),
     "Camera mode 47C9D0: pace the idle delay +3B8 (counted while the stick is still) "
     "before 468420 recenters."),
    ("objects", "callscale", 0x47D0A4, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47C9D0: yaw toward +39C; the factor is the 7A82D8 mode-table value "
     "minus one, which mode_constants corrects: scale the limit only."),
    ("objects", "count", 0x47D0A9, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 47C9D0: pace the yaw request's duration +398."),
    ("objects", "callblend", 0x47D0E9, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47C9D0: yaw behind the target: constant 0.05 approach and its 0.0698 "
     "limit."),
    ("objects", "count", 0x47D0EE, "dec word ptr [rdi + 0x484]", None,
     "Camera mode 47C9D0: pace the turn-behind window +484."),
    # 47DAB0, a copy of 47C9D0
    ("objects", "count", 0x47E0E6, "dec ax",
     (0x47E0BD,0x47E0E9,(0x47E0BD,0x47E0C4,0x47E0C8,0x47E0CB,0x47E0CD,0x47E0D5,0x47E0DD,0x47E0E1,0x47E0E4,0x47E0E6),None),
     "Camera mode 47DAB0: pace the idle delay +3B8 before 468420 recenters."),
    ("objects", "callscale", 0x47E201, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47DAB0: yaw toward +39C; the mode-table factor is already corrected: "
     "scale the limit only."),
    ("objects", "count", 0x47E206, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 47DAB0: pace the yaw request's duration +398."),
    ("objects", "callblend", 0x47E246, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47DAB0: yaw behind the target: constant 0.05 approach and its limit."),
    ("objects", "count", 0x47E24B, "dec word ptr [rdi + 0x484]", None,
     "Camera mode 47DAB0: pace the turn-behind window +484."),
    # 47A3A0
    ("objects", "blend", 0x47A43B, "mulss xmm1, dword ptr [rip + 0x1fe085]",
     (0x6784C8, 0.15000000596046448),
     "Camera mode 47A3A0: field of view +1D0 approaches 65 by 0.15 a tick."),
    ("objects", "blend", 0x47A677, "mulss xmm1, dword ptr [rip + 0x1f7785]",
     (0x671E04, 0.10000000149011612),
     "Camera mode 47A3A0: distance +200 approaches the global 7A7C0C by 0.1 a tick."),
    ("objects", "callscale", 0x47AA70, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47A3A0: approach with the 7A8330 mode-table factor (corrected by "
     "mode_constants): scale the 0.0087 limit only."),
    ("objects", "callscale", 0x47AAC9, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47A3A0: the chained second approach with the 7A8330 factor: scale "
     "its limit only."),
    ("objects", "callscale", 0x47AB22, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47A3A0: the third 7A8330-factor approach: scale its limit only."),
    ("objects", "callblend", 0x47AC05, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47A3A0: turn yaw behind the target: constant 0.3 approach and its "
     "0.0349 limit."),
    ("objects", "count", 0x47AC1B, "dec word ptr [rdi + 0x410]", None,
     "Camera mode 47A3A0: pace the turn-behind window +410."),
    ("objects", "callscale", 0x47ACBA, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47A3A0: yaw toward +39C with the corrected 7A82D8 factor: scale the "
     "limit only."),
    ("objects", "count", 0x47ACBF, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 47A3A0: pace the yaw request's duration +398."),
    ("objects", "count", 0x47B5B5, "dec ax",
     (0x47B585,0x47B5B8,(0x47B585,0x47B58C,0x47B595,0x47B59E,0x47B5A7,0x47B5B0,0x47B5B3,0x47B5B5),None),
     "Camera mode 47A3A0: pace the recenter delay +3B8."),
    # 477F90
    ("objects", "callblend", 0x4780FC, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 477F90: +1C4 toward xmm8: constant 0.2 approach and its 0.279 limit."),
    ("objects", "callblend", 0x47811C, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 477F90: +1C0 toward xmm8: constant 0.2 approach and its limit."),
    ("objects", "count", 0x478121, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 477F90: pace the request's duration +398."),
    # 470AE0
    ("objects", "callblend", 0x470F25, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 470AE0: yaw toward +39C: constant 0.1 approach and its 0.1396 limit."),
    ("objects", "count", 0x470F2A, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 470AE0: pace the yaw request's duration +398."),
    ("objects", "callblend", 0x470F5F, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 470AE0: pitch toward +3A4: constant 0.2 approach and its limit."),
    ("objects", "count", 0x470F64, "dec word ptr [rdi + 0x3a0]", None,
     "Camera mode 470AE0: pace the pitch request's duration +3A0."),
    # 46B080
    ("objects", "count", 0x46B61A, "dec ax",
     (0x46B5F1,0x46B61D,(0x46B5F1,0x46B5F8,0x46B5FC,0x46B5FF,0x46B601,0x46B609,0x46B611,0x46B615,0x46B618,0x46B61A),None),
     "Camera mode 46B080: pace the idle delay +3B8 before the pitch returns to +3B0."),
    ("objects", "callblend", 0x46B725, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 46B080: yaw +1B4 toward the target's bearing: constant 0.9 approach "
     "and its 0.349 limit."),
    ("objects", "callblend", 0x46B74E, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 46B080: pitch +1B0 toward +3A4: constant 0.2 approach and its 0.0349 "
     "limit."),
    ("objects", "callscale", 0x46B7A3, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 46B080: yaw toward +39C with the corrected 7A82D8 factor: scale the "
     "limit only."),
    ("objects", "count", 0x46B7A8, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 46B080: pace the yaw request's duration +398."),
    ("objects", "callblend", 0x46B7EB, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 46B080: yaw behind the target: constant 0.05 approach and its limit."),
    ("objects", "count", 0x46B7F0, "dec word ptr [rdi + 0x484]", None,
     "Camera mode 46B080: pace the turn-behind window +484."),
    # Camera modes, second part (2026-09-30)
    # 4797A0
    ("objects", "blend", 0x47983D, "mulss xmm1, dword ptr [rip + 0x1f90e7]",
     (0x67292C, 0.20000000298023224),
     "Camera mode 4797A0: field of view +1D0 approaches its speed-dependent target by "
     "0.2 a tick."),
    ("objects", "blend", 0x479A1B, "mulss xmm1, dword ptr [rip + 0x1f83e1]",
     (0x671E04, 0.10000000149011612),
     "Camera mode 4797A0: distance +200 approaches the global 7A7C0C by 0.1 a tick."),
    ("objects", "dst", 0x479C99, "movss xmm0, dword ptr [rip + 0x54ea77]", None,
     "Camera mode 4797A0: yaw +1B4 gains the stick-driven yaw velocity 9C8718 each "
     "tick (its damping and input are the 468xxx rows): scale the step."),
    ("objects", "dst", 0x479D2A, "movss xmm0, dword ptr [rip + 0x54e9e2]", None,
     "Camera mode 4797A0: pitch +1B0 gains the stick-driven pitch velocity 9C8714 each "
     "tick: scale the step."),
    # 46A090
    ("objects", "count", 0x46A417, "dec al",
     (0x46A40C,0x46A419,(0x46A40C,0x46A413,0x46A415,0x46A417),None),
     "Camera mode 46A090: pace the 15-tick byte +413 armed when a tracked point comes "
     "close, during which it follows that point."),
    # 2026-09-30: map 312's script, the vt79E318 sub-state updates, the 23C420 sequencer
    ("actor", "gatefn", 0x5FB060, "mov rax, rsp", None,
     "Map 312's script update (the +18 field of its 7AD9B0 record, called only by "
     "3F3A10's `call rcx`, which ignores rax): its 300-tick sequence +6D8/+6DC, the "
     "actor's rise (+6D4 -= 1.2, +6D0 += +6D4, y += +6D0), counters and sounds "
     "together at stock cadence."),
    ("objects", "count", 0x21F4CA, "sub dword ptr [rbx + 0x13f0], 1", None,
     "vt79E318 sub-state 1: pace the 10-tick wait +13F0."),
    ("objects", "count", 0x21F5B9, "sub dword ptr [rbx + 0x13f0], 1", None,
     "vt79E318 sub-state 3: pace the 20-tick (then 5 to 36) wait +13F0."),
    ("objects", "lin", 0x21F65B, "subss xmm0, dword ptr [rip + 0x457f8d]",
     (0x6775F0, 0.05000000074505806),
     "vt79E318 sub-state 3: +D2C loses 0.05 a tick while the wait runs."),
    ("objects", "count", 0x21F66D, "sub dword ptr [rbx + 0x13f0], 1", None,
     "vt79E318 sub-state 4: pace the wait +13F0."),
    ("objects", "count", 0x21F85A, "sub dword ptr [rbx + 0x13f0], 1", None,
     "vt79E318 slot 5 copy, sub-state 1: pace the 10-tick wait +13F0."),
    ("objects", "count", 0x21F905, "sub dword ptr [rbx + 0x13f0], 1", None,
     "vt79E318 slot 5 copy, sub-state 3: pace the wait +13F0."),
    ("objects", "lin", 0x21F96B, "subss xmm0, dword ptr [rip + 0x457c7d]",
     (0x6775F0, 0.05000000074505806),
     "vt79E318 slot 5 copy, sub-state 3: +D2C loses 0.05 a tick."),
    ("objects", "count", 0x21F97D, "sub dword ptr [rbx + 0x13f0], 1", None,
     "vt79E318 slot 5 copy, sub-state 4: pace the wait +13F0."),
    # 2026-10-01: the remaining unattributed candidates, first batch
    # 4902F0 (called by 4900B0): a two-entry widget whose states 2 and 3 slide the page over 16 ticks
    ("menu", "count", 0x490394, "mov byte ptr [rdi + 1], cl", None,
     "4902F0 state 2: hold the slide's tick count +1 (0 to 15) between stock ticks; "
     "the page offset is recomputed from it each tick."),
    ("menu", "notyet", 0x490397, "cmp dl, 0xf", 0x49061F,
     "4902F0 state 2: the end test reads the old count (dl); between stock ticks take "
     "the not-yet path, so the slide ends on its stock tick."),
    ("menu", "count", 0x49041C, "mov byte ptr [rdi + 1], al", None,
     "4902F0 state 3: hold the opposite slide's tick count +1 between stock ticks."),
    ("menu", "notyet", 0x49041F, "cmp cl, 0xf", 0x49061F,
     "4902F0 state 3: the same end test on the old count."),
    # 600190 (called by 600040): a menu whose unselected entries shrink back
    ("menu", "root", 0x600647, "movss xmm6, dword ptr [rip + 0x79311]", None,
     "600190: the unselected entries' scales +2C/+30 shrink by 0.98 a tick down to "
     "their base (the max with it): take the factor's N-th root."),
    # 5CBAD0 (called by nine state handlers 5C8160..5CB850): the swimmer's approach and its speed
    ("actor", "count", 0x5CBDF2, "mov byte ptr [rdi + 0x3417], al", None,
     "5CBAD0: hold the 40-tick countdown +3417 (rearmed while the player is beyond 400 "
     "or +D40 bit 3 is set) between stock ticks; each tick it is nonzero, 5CDBA0 turns "
     "the heading toward +1340."),
    ("actor", "blend", 0x5CBDDE, "movss xmm2, dword ptr [rip + 0xac6e2]",
     (0x6784C8, 0.15000000596046448),
     "5CBAD0: 5CDBA0's heading approach toward +1340 by 0.15 a tick."),
    ("actor", "root", 0x5CBE8E, "addss xmm1, dword ptr [rip + 0xadaca]", None,
     "5CBAD0: the speed +343C damps by 0.98 + 0.02 sin^2 of its clock phase (a factor "
     "in [0.98, 1]) a tick: take the factor's N-th root."),
    ("actor", "root", 0x5CBF2E, "addss xmm1, dword ptr [rip + 0xada2a]", None,
     "5CBAD0 (+340C set): the same damping."),
    ("actor", "srcblend", 0x5CBFA9, "mulss xmm0, xmm7", None,
     "5CBAD0: the heading +B4 approaches the bearing to +1340 by xmm7 (0.035 or 0.055, "
     "times 0.7 to 1.5 by the player's distance) a tick."),
    ("actor", "dst", 0x5CBFB6, "movss xmm2, dword ptr [rdi + 0x1080]", ("scale", 0x5CBFD0),
     "5CBAD0: the forward move (0, 0, 50 x +343C), times the speed +1080 and +F54, "
     "goes to 2DA3F0: scale the speed as read."),
    # 2026-10-01: the weapons' falls. 20EA30 (y += dt x vy, vy -= g x dt, dt read nowhere
    # else) takes dt in xmm2; these slot-8 updates pass their slow-motion factor (23AD90's
    # 0.25 or 1, kept in xmm6/xmm7 or passed from xmm0) unscaled. The enemies' calls pass
    # +1080, whose loads are step rows already; no weapon here has a slowmo row.
    ("player", "callscale", 0x37ED84, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 37EC90 (vt6AD470[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x383814, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 383750 (vt6AD5D0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x3845DA, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 3844F0 (vt6AD6D0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x385698, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 3855D0 (vt6AD868[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x386409, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 386320 (vt6AD980[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x386BFE, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 386AE0 (vt6ADA30[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x3881BA, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 3880C0 (vt6ADAE0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x3897F7, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 389730 (vt6ADC20[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x389E65, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 389D50 (vt6ADCE0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x38B3AF, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 38B280 (vt6ADDE0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x38BF45, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 38BE70 (vt6ADEE8[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x38C91B, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 38C810 (vt6ADFF0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39A5B3, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39A520 (vt6AE5C0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39AAFB, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39AA10 (vt6AE6C0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39CB75, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39CA60 (vt6AE770[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39D3F9, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39D2E0 (vt6AE820[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39D42B, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39D2E0 (vt6AE820[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39DA47, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39D990 (vt6AE8D0[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39E2C6, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39E1E0 (vt6AE980[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x39FBDB, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 39FAB0 (vt6AEA38[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x3A0A25, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 3A0940 (vt6AEB38[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x3A1641, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 3A1540 (vt6AEBE8[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    ("player", "callscale", 0x3A2372, "call 0x18020ea30", (0x20EA30, "xmm2"),
     "Weapon update 3A2290 (vt6AEC98[8]): its gravity fall's dt, the slow-motion "
     "factor, is a per-tick share: scale it at the call."),
    # 2026-10-01, second batch
    # 47FF90, a camera mode (dispatched by 475C70): the request approaches of the other modes
    ("objects", "callblend", 0x4803FC, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47FF90: yaw +1B4 toward the request +39C plus pi: constant 0.1 "
     "approach and its 0.1396 limit."),
    ("objects", "count", 0x480401, "dec word ptr [rdi + 0x398]", None,
     "Camera mode 47FF90: pace the yaw request's duration +398."),
    ("objects", "callblend", 0x480436, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Camera mode 47FF90: pitch toward +3A4: constant 0.2 approach and its 0.279 "
     "limit."),
    ("objects", "count", 0x48043B, "dec word ptr [rdi + 0x3a0]", None,
     "Camera mode 47FF90: pace the pitch request's duration +3A0."),
    # 472E80 (camera mode 8 path of 4760E0): the drop while the player falls, 2 x +290 below the view
    ("objects", "count", 0x472F4F, "add word ptr [rbx + 0x290], 2", None,
     "Camera 472E80: +290 grows by 2 a tick while the player falls (vy below -2, off "
     "the ground): pace it; the drop is recomputed from it each tick."),
    ("objects", "count", 0x472F83, "mov word ptr [rbx + 0x290], cx", None,
     "Camera 472E80: the undo of that +2 when the drop passes -20 (sub cx, 2; store): "
     "skip it with the add between stock ticks."),
    ("objects", "count", 0x472F90, "dec word ptr [rbx + 0x290]", None,
     "Camera 472E80: +290 shrinks by 1 a tick back to 0 once the player lands: pace "
     "it."),
    # the moving platforms (vt7AA108's states; ids 0x819, 0x82E, 0x842)
    ("objects", "pre", 0x489E36, "addss xmm0, dword ptr [rax + 4]", None,
     "Platform state 489DD0: y += the speed +1080 a tick (rising): scale the step "
     "first."),
    ("objects", "src", 0x489E4E, "subss xmm0, dword ptr [rbx + 0x1080]", None,
     "Platform state 489DD0: y -= the speed +1080 a tick (sinking): scale the step."),
    ("objects", "lin", 0x48A017, "subss xmm0, dword ptr [rip + 0x1f325d]",
     (0x67D27C, 0.09999999403953552),
     "Platform 0x82E (489FE0, phase 4): its speed loses 0.1 a tick."),
    ("objects", "lin", 0x48A080, "addss xmm0, dword ptr [rip + 0x224f50]",
     (0x6AEFD8, 0.020000001415610313),
     "Platform 0x82E (489FE0, phase 1): its speed gains 0.02 a tick."),
    ("objects", "count", 0x48A05B, "mov dword ptr [rdx + 0x10a0], eax", None,
     "Platform 0x82E (489FE0, phase 3): pace the 5-tick pause +10A0 with the speed at "
     "0."),
    ("objects", "notyet", 0x48A061, "test ecx, ecx", 0x48A0A5,
     "Platform 0x82E: the pause's end test reads the old count (ecx); between stock "
     "ticks take the not-yet path."),
    ("objects", "count", 0x489D93, "sub dword ptr [rbx + 0x10a0], 1", None,
     "Platform state 489C60: pace the 5-tick shake +10A0 (its random +-0.6 jitter is "
     "resampled each tick at stock amplitude) before the next state."),
    ("objects", "count", 0x489F8F, "sub dword ptr [rbx + 0x10a0], 1", None,
     "Platform state 489F20: pace the 5-tick shake +10A0 before it stops."),
    ("objects", "gatefn", 0x48DED0, "mov qword ptr [rsp + 0x18], rsi", None,
     "Treasure fanfare 48DED0 (from 48DA60 and 48ECA0): its count-up +8F (sound 0x1BC "
     "at 23), the per-tick fade of 18EB20's +1D0 and the wait for its message to close "
     "run together at stock cadence."),
    # 2A2B40 (an enemy's circling, from 29F770, sub-state 1)
    ("actor", "lin", 0x2A2C14, "subss xmm0, dword ptr [rip + 0x3d6d98]", (0x6799B4, 4.0),
     "2A2B40: the circling radius +13B4 shrinks by 4 a tick (beyond 200 from the "
     "player)."),
    ("actor", "lin", 0x2A2C26, "subss xmm0, dword ptr [rip + 0x3d2e4e]", (0x675A7C, 6.0),
     "2A2B40: the radius +13B4 shrinks by 6 a tick (flag +13C9)."),
    ("actor", "lin", 0x2A2C43, "addss xmm0, dword ptr [rip + 0x3cf1c9]", (0x671E14, 2.0),
     "2A2B40: the radius +13B4 grows by 2 a tick up to 110 + 22 x +1146."),
    ("actor", "lin", 0x2A2C8F, "subss xmm0, dword ptr [rip + 0x3de1e9]",
     (0x680E80, 0.04363323003053665),
     "2A2B40: the circling angle +13B0 turns by -0.0436 a tick."),
    ("actor", "lin", 0x2A2C99, "addss xmm0, dword ptr [rip + 0x3de1df]",
     (0x680E80, 0.04363323003053665),
     "2A2B40: the circling angle +13B0 turns by 0.0436 a tick."),
    # the item shop's panels (globals 7A9C50, 7A9D30, 7A9E10, updated by 4BA500): their drop-in bounce
    ("menu", "gatefn", 0x43C010, "cmp byte ptr [rcx + 0x94], 1", None,
     "Shop panel 43BF40's drop-in (state 1): v += 6, y += 2v, a bounce at 0 by -0.47 "
     "until |v| < 3, together at stock cadence (its tail-jump target; the panel's "
     "pad-reading states stay per tick)."),
    ("menu", "gatefn", 0x43F6B0, "cmp byte ptr [rcx + 0x94], 1", None,
     "Shop panel 43F610's drop-in, the same bounce at stock cadence."),
    ("menu", "gatefn", 0x442790, "cmp byte ptr [rcx + 0x94], 1", None,
     "Shop panel 4426F0's drop-in, the same bounce at stock cadence."),
    ("menu", "countlast", 0x43E1D1, "mulss xmm1, dword ptr [rip + 0x23a13f]", None,
     "Shop panel 43BF40's exit (state 2, sub-state 1): its speed +B8 grows x1.7 a tick: "
     "only on the last tick of each stock period."),
    ("menu", "srcx", 0x43E1E1, "subss xmm0, xmm1", None,
     "Shop panel 43BF40's exit: y -= the speed +B8 a tick, up to -512: scale the step."),
    # 2026-10-01, third batch
    # 601170: the menu background shared by the screens 600040, 5FF5E0, 5FFF50, 601B70, 601CA0, 5FF790, 601D50
    ("menu", "lin", 0x6011AD, "addss xmm0, dword ptr [rip + 0x7ef13]",
     (0x6800C8, 0.003000000026077032),
     "Menu background 601170: its alpha +8 gains 0.003 a tick up to the layout's "
     "maximum."),
    ("menu", "lin", 0x6011ED, "subss xmm1, dword ptr [rip + 0x71a27]", (0x672C1C, 0.125),
     "Menu background 601170: its offset +C loses 0.125 a tick down to -190."),
    ("menu", "lin", 0x601223, "addss xmm0, dword ptr [rip + 0xbc169]",
     (0x6BD394, 0.000699999975040555),
     "Menu background 601170: its angle +10 gains 0.0007 a tick (wrapped)."),
    # 52EE10 (from 531F50), a map script's tick routine on the script manager 7A8CB0
    ("objects", "count", 0x52EE71, "inc dword ptr [rax + 8]", None,
     "Map script 52EE10: pace its tick count 7A8CB0+8 (event 0x1E0023 after 300) while "
     "the save flag +71C bit 1 holds."),
    ("objects", "count", 0x52F042, "sub eax, 1",
     (0x52F03B,0x52F045,(0x52F03B,0x52F03E,0x52F040,0x52F042),None),
     "Map script 52EE10: pace the countdown 7A8CB0+C to its event 0x1E0030."),
    # 13B250 (from 13B130, the event camera 48C280): a keyframed rumble
    ("objects", "count", 0x13B3A7, "add dword ptr [rbp + 0x20], esi", None,
     "Event camera rumble 13B250: pace its pulse accumulator +20 (+= the key's "
     "intensity each tick, a pulse on the other motor at each 255) to once a stock "
     "tick."),
    # 20E130 (obj, d): x, z += R(+B0) x (0, 0, d), a forward step
    ("objects", "callscale", 0x22FF46, "call 0x18020e130", (0x20E130, "xmm1"),
     "22FE00 (from 22FDB0): its walk by the speed +11F4 a tick through 20E130."),
    ("objects", "callscale", 0x307C57, "call 0x18020e130", (0x20E130, "xmm1"),
     "307B90 (from 307B10): steps back 2 (or 1.5) a tick through 20E130."),
    ("objects", "callscale", 0x307EE4, "call 0x18020e130", (0x20E130, "xmm1"),
     "307B90: the same back step, its other state."),
    ("objects", "callscale", 0x308408, "call 0x18020e130", (0x20E130, "xmm1"),
     "308340 (from 307B10): steps back 2 (or 1.5) a tick through 20E130."),
    ("objects", "callscale", 0x30854A, "call 0x18020e130", (0x20E130, "xmm1"),
     "308340: steps by xmm6 (-0.3 once +E3C passes 10) a tick through 20E130."),
    ("objects", "callscale", 0x3086FA, "call 0x18020e130", (0x20E130, "xmm1"),
     "308340: steps back 2 (or 1.5) a tick, its other state."),
    # 21EBD0 and 21EF90: copies of vt79E318's sub-state updates 21F340/21F6D0 that no vtable, call or pointer names (their .rdata words are their own IP-to-state map entries); rows in them are harmless
    ("objects", "blend", 0x21ED91, "mulss xmm1, dword ptr [rip + 0x456c97]",
     (0x675A30, 0.30000001192092896),
     "21EBD0: +D2C fades toward 0 by 0.3 a tick."),
    ("objects", "count", 0x21EDCC, "mov dword ptr [rbx + 0x13f0], eax", None,
     "21EBD0: pace the wait +13F0 (+D2C re-flashes to 1 at 7 and 4)."),
    ("objects", "blend", 0x21F151, "mulss xmm1, dword ptr [rip + 0x4568d7]",
     (0x675A30, 0.30000001192092896),
     "21EF90: +D2C fades toward 0 by 0.3 a tick."),
    ("objects", "count", 0x21F18C, "mov dword ptr [rbx + 0x13f0], eax", None,
     "21EF90: pace the wait +13F0."),
    # 2026-10-01, fourth batch
    # 4AC680 (from 4AEB70): the environment's light and fog update
    ("objects", "count", 0x4AD0F3, "mov byte ptr [rsi + 0xfb0], al", None,
     "Environment 4AC680: pace the transition count +FB0 (while it runs, the light "
     "colours B699B0.. snap toward the new ones, 0.1 of the gap left a tick)."),
    ("objects", "srcx", 0x4AD324, "subss xmm1, xmm7", None,
     "Environment 4AC680: the fade +FE0 loses 1/+FE4 a tick down to 0: scale the step."),
    # the camera
    ("objects", "count", 0x476FCC, "inc word ptr [rbx + 0x41c]", None,
     "Camera dispatcher 476B00: pace the count +41C of ticks the camera button is held "
     "(past 10, a long press)."),
    # 54EDC0, a cutscene task: its two walk loops before the walk-out (waits 54F698,
    # 54FA0A) run one pass a stock tick by task_waits.h. Each pass doubles each of
    # five walkers' step +EC8 (this tick's: their motion advance rewrites it every
    # tick as speed x K, 363A20) and applies it once more through cMatrix::Apply
    # (2DA3D0). x N: a stock tick's push a pass, as stock's
    ("objects", "dstn", 0x54F665, "addss xmm0, xmm0", 0x54F698,
     "Cutscene task 54EDC0: the first walk loop (up to 270 passes, one a stock tick) "
     "pushes five walkers by twice their step; at 120 the step is a quarter of stock's, "
     "so x N."),
    ("objects", "dstn", 0x54F9D7, "addss xmm0, xmm0", 0x54FA0A,
     "Cutscene task 54EDC0: the second walk loop (120 passes, one a stock tick), as "
     "54F665."),
    # 54EDC0, a cutscene task: its walk-out loop at 54F880 waits by wait(1) at 54F92D, which task_waits.h leaves per tick (DATA_LEFT: the loop reaches the root motion's patched code)
    ("objects", "count", 0x54F932, "sub r14, 1", "reg",
     "Cutscene task 54EDC0: pace the walk-out loop's 15 passes (r14), so the five "
     "actors walk (root motion x 2, at the current rate's share) and the objects fade "
     "for 15 stock ticks."),
    ("objects", "src", 0x54F8FE, "subss xmm0, xmm8", None,
     "Cutscene task 54EDC0: in the same loop, the objects' +D2C fades by 0.1 a pass: "
     "scale the step."),
    # the map scripts' per-tick updates (their records' +18 in 7AD9B0)
    ("objects", "count", 0x574148, "sub eax, 1",
     (0x574141,0x57414B,(0x574141,0x574144,0x574146,0x574148),None),
     "Map 207's script (573FE0, from 579220): pace the countdown 7A8CB0+8 to its event "
     "0x260035."),
    ("objects", "count", 0x58BCF8, "sub eax, 1",
     (0x58BCF1,0x58BCFB,(0x58BCF1,0x58BCF4,0x58BCF6,0x58BCF8),None),
     "Map 20D's script (58BB90, from 58D800): pace the countdown 7A8CB0+8 to its event "
     "0x2C0008."),
    ("objects", "src", 0x634F92, "subsd xmm0, qword ptr [rip + 0x88d9e]", None,
     "Map F08's script (634E90, from 634D30): B75140's +50 fades by 0.03 a tick, in "
     "doubles: scale the step."),
    ("objects", "src", 0x634FDE, "addsd xmm0, qword ptr [rip + 0x4c532]", None,
     "Map F08's script: B75140's +50 grows by 0.05 a tick, in doubles: scale the step."),
    # 2026-10-01, fifth batch
    ("objects", "countlast", 0x36E425, "mulss xmm0, dword ptr [rip + 0x3039e3]", None,
     "36E060 (scenery tilting under the brush's wind technique): once the wind stops, "
     "its tilt +1114 decays x0.7 a tick: only on the last tick of each stock period."),
    ("objects", "count", 0x1D2478, "inc dword ptr [rcx + 0x1c]", None,
     "1D2130 (from 1D2060): pace the 45-tick count +1C while state +57 is 1."),
    ("objects", "callscale", 0x32EFAC, "call 0x18020e030", (0x20E030, "xmm2"),
     "32EF40, sub-state 1 (20 ticks): turns toward B66380 by at most 10 degrees a tick "
     "through 20E030."),
    ("objects", "gatefn", 0x281470, "push rbx", None,
     "The twin enemy's orbit 281470 (from its state handlers 27C240..280610): the "
     "shared orbit angle 9C4780 (+0.01 or +0.005 a tick), the circle offsets from the "
     "distance, and the approach of the position to its circle point by param_2^2 a "
     "tick, together at stock cadence."),
    ("actor", "lin", 0x205505, "mulss xmm0, dword ptr [rip + 0x474767]",
     (0x679C74, 0.4000000059604645),
     "Animal 205310's knockback slide on the ground: x += +E10 x 0.4 a tick (+E10 "
     "damps x0.97, a decay_factors row)."),
    ("actor", "lin", 0x205524, "mulss xmm0, dword ptr [rip + 0x474748]",
     (0x679C74, 0.4000000059604645),
     "Animal 205310's slide on the ground: z += +E18 x 0.4 a tick."),
    ("actor", "src", 0x205537, "addss xmm0, dword ptr [rbx + 0xe10]", None,
     "Animal 205310's slide in the air: x += +E10 a tick."),
    ("actor", "src", 0x20554F, "addss xmm0, dword ptr [rbx + 0xe18]", None,
     "Animal 205310's slide in the air: z += +E18 a tick."),
    ("actor", "callscale", 0x1ED84D, "call 0x18020e030", (0x20E030, "xmm2"),
     "Animal 1ED4C0: within 10 of its target it turns by at most 3 degrees a tick "
     "through 20E030 (the 20E210 path beside it is the turn group's)."),
    ("actor", "callscale", 0x1EF0DA, "call 0x18020e030", (0x20E030, "xmm2"),
     "Animal 1EEF50: the same turn through 20E030."),
    ("actor", "callscale", 0x1EF2B8, "call 0x18020e030", (0x20E030, "xmm2"),
     "Animal 1EF120: the same turn through 20E030."),
    ("actor", "count", 0x2432A5, "mov word ptr [rsi + 0xe3c], ax", None,
     "Imp state 243180 (from 242060): pace the countdown +E3C."),
    ("player", "count", 0x165F87, "dec ax",
     (0x165F6C,0x165F8A,(0x165F6C,0x165F70,0x165F73,0x165F87),None),
     "Brush 165BD0 (from the brush update 16C7E0): pace the countdown +60 (reloaded by "
     "1695D0 when it runs out)."),
    ("objects", "count", 0x313A80, "dec ax",
     (0x313A72,0x313A83,(0x313A72,0x313A76,0x313A79,0x313A7B,0x313A80),None),
     "3135B0's state 1 (313A60, from the main tick through 3134A0): pace the delay +40 "
     "before its check."),
    ("objects", "count", 0x467D23, "mov byte ptr [rbx], al", None,
     "467CA0 (from the main tick): pace its countdown byte while +1 is set."),
    ("objects", "notyet", 0x467D25, "test cl, cl", 0x467D6B,
     "467CA0: the end test reads the old count (cl); between stock ticks take the "
     "not-yet path."),
    ("objects", "srcblend", 0x469BE8, "mulss xmm1, xmm2", None,
     "Camera mode 4697B0: z approaches its target by +260 a tick (an approach that "
     "speeds up: +260 grows 0.01 a tick to 0.3)."),
    ("objects", "lin", 0x469BEC, "addss xmm2, dword ptr [rip + 0x208e4c]",
     (0x672A40, 0.009999999776482582),
     "Camera mode 4697B0: the approach factor +260 grows by 0.01 a tick."),
    ("objects", "srcblend", 0x46BF18, "mulss xmm1, xmm3", None,
     "Camera mode 46BCD0: z approaches its target by +260 a tick."),
    ("objects", "lin", 0x46BF1C, "addss xmm3, dword ptr [rip + 0x206b1c]",
     (0x672A40, 0.009999999776482582),
     "Camera mode 46BCD0: +260 grows by 0.01 a tick up to 0.3."),
    ("objects", "srcblend", 0x46C792, "mulss xmm1, xmm2", None,
     "Camera mode 46C370: z approaches its target by +260 a tick."),
    ("objects", "lin", 0x46C796, "addss xmm2, dword ptr [rip + 0x2062a2]",
     (0x672A40, 0.009999999776482582),
     "Camera mode 46C370: +260 grows by 0.01 a tick."),
    ("objects", "count", 0x4761B1, "inc byte ptr [rbx + 0x47c]", None,
     "Camera 4760E0 (from 476B00): pace the count +47C of ticks the camera button is "
     "held (past 10, a long press)."),
    ("actor", "count", 0x2A1073, "mov word ptr [rbx + 0x13ba], ax", None,
     "2A0F40 sub-state 3: pace the 150-tick countdown +13BA."),
    ("human", "count", 0x3179BA, "dec ax",
     (0x3179AC,0x3179BD,(0x3179AC,0x3179B0,0x3179B3,0x3179B5,0x3179BA),None),
     "Villager 317870 (from 317020, cHuman's update 305840): pace the countdown +14."),
    ("player", "callblend", 0x39F848, "call 0x1802da570", (0x2DA570, "xmm3"),
     "Weapon aim 39F770 (from 39E790, 39EAC0, 39EE30): the pitch +B0 approaches the "
     "angle to the player by 0.15 a tick within a limit of the slow-motion factor x "
     "the caller's rate."),
    ("player", "callscale", 0x39F86F, "call 0x1802ddf90", (0x2DDF90, "xmm3"),
     "Weapon aim 39F770: the heading turns toward the player within the same limit."),
    # 2026-10-01, sixth batch
    # the screen transition B65E80, driven by 48A920's task loop (its wait 48ABDE stays per tick: the loop sets the mode byte)
    ("menu", "count", 0x48AA86, "addss xmm2, xmm7", "float",
     "Screen transition 48A920 (mode 3): pace the 6-tick count B65E9C (its ease B65EA0 "
     "is recomputed from it each pass)."),
    ("menu", "count", 0x48AD2C, "addss xmm3, dword ptr [rip + 0x1e6ed4]", "float",
     "Screen transition 48AD20 (mode 2, from 48A830): pace the 6-tick count +1C (the "
     "slide +28 is recomputed from it)."),
    ("objects", "srcblend", 0x48DD9A, "divss xmm1, dword ptr [rip + 0x1e71b6]", None,
     "48DCE0 (from 48EC20): +EC approaches its target by a third of the gap a tick."),
    ("objects", "count", 0x48F331, "dec word ptr [rcx + 0xe4]", None,
     "48F300 (from 48E9C0): pace the countdown +E4 while the player is farther than "
     "400."),
    ("objects", "count", 0x48FF69, "sub byte ptr [rdi + 0x159], 1", None,
     "48FE70 (from 48ECA0): pace the 50-tick delay +159."),
    ("objects", "count", 0x49125A, "mov word ptr [rbx + 0xe6], ax", None,
     "491200 (from 48E9C0): pace the countdown +E6."),
    ("objects", "notyet", 0x491261, "test cx, cx", 0x491266,
     "491200: the end test reads the old count (cx); between stock ticks take the "
     "not-yet path."),
    ("objects", "count", 0x495F36, "mov dword ptr [rbx + 0x94], eax", None,
     "495E40: pace the 8-tick spawn period +94 (an effect each time it runs out)."),
    ("objects", "notyet", 0x495F3C, "test ecx, ecx", 0x495FAB,
     "495E40: the period test reads the old count (ecx); between stock ticks take the "
     "not-yet path."),
    ("objects", "src", 0x4D2644, "subsd xmm0, qword ptr [rip + 0x1e24cc]", None,
     "Map 103's script (4D2600, from 4D2280 and 4DBF90): an object's +D2C fades by "
     "0.01 a tick, in doubles."),
    ("human", "lin", 0x4ABC08, "addss xmm0, dword ptr [rip + 0x1ce004]",
     (0x679C14, 0.2617993950843811),
     "Villager 4ABA90 (from 30C780): +E14 turns by 15 degrees a tick while its motion "
     "time is under 30."),
    # 2026-10-01, seventh batch: the last of the unattributed candidates
    # the map scripts' per-tick updates (the +18 field of their 7AD9B0 records) and what they call
    ("objects", "count", 0x5015C7, "inc dword ptr [rax + 0x9c]", None,
     "Map 109's script (501560, from 501660 and 5099D0): pace the 20-tick delay "
     "B6D788+9C before a free slot of five is filled."),
    ("objects", "count", 0x5428AE, "sub dword ptr [rax + 0x254], 1", None,
     "Map 201's script (5427E0, from 547980): pace the 10-tick countdown B71D60+254."),
    ("objects", "count", 0x54447A, "mov dword ptr [rdx + 0x258], eax", None,
     "Map 201's script (5443F0, from 547980): pace the 90-tick countdown B71D60+258 (the "
     "js after it cannot fire: the jne before the subtraction keeps 0 away)."),
    ("objects", "count", 0x579B02, "inc dword ptr [rax + 4]", None,
     "Map 207's script (579220): pace its tick count B72F58+4 (an event at 600)."),
    ("objects", "count", 0x58F5D5, "inc dword ptr [rax + 8]", None,
     "Map 20F's script (58F4F0, from 58FC20): pace the tick count 7A8CB0+8 (a flicker "
     "every 2 ticks, events at 30 and 60)."),
    ("objects", "count", 0x590FF5, "dec cl",
     (0x590FE5,0x590FF7,(0x590FE5,0x590FE9,0x590FEB,0x590FED,0x590FF5),None),
     "Map 301's script (590F10, from 5944E0): pace the countdown byte B73000+20."),
    ("objects", "count", 0x596BA2, "mov byte ptr [rdx + 0x22], al", None,
     "Map 302's script (596AF0, from 598670): pace the 50-tick sound period B73010+22."),
    ("objects", "count", 0x5971F6, "mov byte ptr [rcx + 0x21], al", None,
     "Map 302's script (597100, from 598670): pace the 90-tick sound period B73010+21."),
    ("objects", "count", 0x597AF0, "mov byte ptr [rcx + 0x20], al", None,
     "Map 302's script (597A30, from 598670): pace the 30-tick sound period B73010+20."),
    ("objects", "src", 0x59AC5B, "addss xmm0, xmm7", None,
     "Map 303's script (59ABA0, from 5A2620): an object's +D2C fades in by xmm7 a "
     "tick."),
    ("objects", "lin", 0x5BCA47, "movss xmm0, dword ptr [rip + 0xc32fd]",
     (0x67FD4C, -0.06981316953897476),
     "A map script (5BC850, from the update 5C1760): the angle +10 turns toward its "
     "target by at most 0.0698 a tick: the lower limit (threshold and step)."),
    ("objects", "lin", 0x5BCA54, "movss xmm0, dword ptr [rip + 0xbd1d8]",
     (0x679C34, 0.06981316953897476),
     "5BC850: the upper limit 0.0698."),
    ("objects", "lin", 0x5C24A9, "movss xmm0, dword ptr [rip + 0xbd89b]",
     (0x67FD4C, -0.06981316953897476),
     "A map script (5C22D0, from the update 5C4300): the same turn's lower limit."),
    ("objects", "lin", 0x5C24B6, "movss xmm0, dword ptr [rip + 0xb7776]",
     (0x679C34, 0.06981316953897476),
     "5C22D0: the upper limit."),
    ("objects", "lin", 0x622D84, "movss xmm7, dword ptr [rip + 0x54864]",
     (0x6775F0, 0.05000000074505806),
     "A map script (622D00, from the update 622C40): the objects' +D2C fades in by "
     "0.05 a tick."),
    # other per-tick countdowns
    ("objects", "count", 0x50B0B6, "sub dword ptr [rbx + 0x3b54], 1", None,
     "50AF10 (from 50D3C0): pace the countdown +3B54."),
    ("objects", "count", 0x50B3EE, "sub dword ptr [rbx + 0x3b54], 1", None,
     "50B230 (from 50D3C0): pace the 120-tick countdown +3B54."),
    ("objects", "count", 0x539CDA, "sub dword ptr [rbx + 0x1078], 1", None,
     "539C70 (state 2 of the state table 7C18A0): pace the countdown +1078."),
    ("objects", "src", 0x5F81F0, "addsd xmm0, xmm6", None,
     "5F8190, a task whose wait(1) loop (5F820B) stays per tick (task_waits.h left it "
     "a poll): an object's +D2C fades in by xmm6 a pass, in doubles."),
    ("menu", "count", 0x6000B6, "mov word ptr [rdi + 0x18], ax", None,
     "Menu 600040 (from 600FF0): pace the 450-tick idle count +18."),
    ("menu", "notyetneg", 0x6000BA, "cmp cx, r8w", 0x600108,
     "Menu 600040: the limit test reads the old count (cx); between stock ticks take "
     "the not-yet path (jle)."),
    ("menu", "count", 0x601C46, "inc byte ptr [rcx + 0x1b]", None,
     "Menu 601B70 (from 600FF0): pace the 8-tick count +1B."),
    ("menu", "count", 0x60216A, "sub ecx, 0x10", "reg",
     "Menu 601D50 (from 600FF0): pace the alpha byte +3B's fade by 0x10 a tick (the "
     "subtraction in ecx; between stock ticks the old value is stored back)."),
    # 2026-10-01: a tail jump retargeted like a call (callscale now takes E9 as well as E8)
    ("objects", "callscale", 0x5BB5C7, "jmp 0x18020e130", (0x20E130, "xmm1"),
     "5BB550 (state 3 of 5BB270's object, from the update 5BB0F0, vt6BC160[8]): after "
     "its motion advance and a snap turn toward +E10 it walks 1.0 a tick forward by a "
     "tail jump into 20E130: scale the step at the jump."),
    # 2026-10-02: the four functions whose gate went on 10-01 and cDogLikeHm's
    # gate, each now paced by rows on its own fields.
    # 1C8D80 (the HUD's number slide): the +48 step 0..10 shares its store 1C8DC5
    # between the inc (state 1, reaching it by a jmp) and the dec (state 0); the
    # register-counter proof now takes a jmp to the store and the sibling row's entry.
    ("menu", "count", 0x1C8DA6, "inc eax",
     (0x1C8D9E,0x1C8DC5,(0x1C8D9E,0x1C8DA1,0x1C8DA4,0x1C8DA6),None),
     "HUD number slide 1C8D80, state 1 (sliding out): +48 += 1 a tick up to 10; the "
     "layout's position is (+3C, +38) blended by (+48 / 10)^k each tick, and the "
     "layout update 1B54E0 it calls still runs every tick"),
    ("menu", "count", 0x1C8DC3, "dec eax",
     (0x1C8DBC,0x1C8DC5,(0x1C8DBC,0x1C8DBF,0x1C8DC1,0x1C8DC3),None),
     "HUD number slide 1C8D80, state 0 (sliding in): +48 -= 1 a tick down to 0"),
    ("menu", "notyetneg", 0x1C8DA1, "cmp eax, 0xa", 0x1C8DA6,
     "HUD number slide 1C8D80, state 1: `cmp +48, 10; jge` hides the number on the "
     "tick after +48 reaches 10; between stock ticks it reads \"below 10\" (jge falls "
     "through to the skipped inc), so the last position shows a whole stock tick as in "
     "stock"),
    # 4763F0 (a camera mode's update): 4A0900's call of it comes right after
    # 481A10 set the transition length +290 = +292 = r13d, which is 0 from 4A0942
    # on, so that pass never reaches the count; the count runs from the per-tick
    # camera update (4BA500 -> 475C70 -> 4763F0 or 46D5A0's three helpers).
    ("objects", "count", 0x476805, "dec ax",
     (0x4767E9,0x476808,(0x4767E9,0x4767F0,0x4767F3,0x4767F9,0x476800,0x476803,0x476805),None),
     "Camera 4763F0: the mode transition's count +290 -= 1 a tick from +292 to 0"),
    ("objects", "blendr", 0x47683D, "minss xmm3, xmm1", None,
     "Camera 4763F0: the transition's factor k = min(1, 0.04 + 0.96 (len - count) / "
     "len) blends the stored view (+1A0, +190, +1D0 field of view, +380) toward this "
     "tick's computed one, x = (1 - k) x + k target, every tick: with the count paced, "
     "k is 1 - (1 - k)^(1/N) between stock ticks; xmm7 = 1.0 (476607, callee-saved), "
     "so 1 - k follows at 476841"),
    # 33DE40 (cCarryObj, et99: a carried object floating on water): v(+E54) +=
    # +-0.03 toward the rest height, x 0.8 past +-0.4, height (+A8)->y += v.
    ("objects", "zfirst", 0x33DEF4, "movss xmm1, dword ptr [rip + 0x349a64]", None,
     "cCarryObj 33DE40 float bob: the velocity's change -0.03 (above the rest height) "
     "is this tick's change to +E54: kept on the first tick of each stock period, 0 on "
     "the others"),
    ("objects", "zfirst", 0x33DEFE, "movss xmm1, dword ptr [rip + 0x349a52]", None,
     "cCarryObj 33DE40 float bob: the change +0.03 (below the rest height), as 33DEF4"),
    ("objects", "count", 0x33DF2C, "mulss xmm1, dword ptr [rip + 0x33bd48]", "factor",
     "cCarryObj 33DE40 float bob: the velocity's damping x 0.8 past +-0.4 runs before "
     "the move: kept on the first tick of each stock period, skipped on the others "
     "(the velocity is unchanged there, so the bound test repeats it otherwise)"),
    ("objects", "src", 0x33DF41, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "cCarryObj 33DE40 float bob: height += v a tick; v changes once a stock period, "
     "so the height passes through stock's values at every stock tick"),
    # 375FF0 (vtca state 1): +E36 counts down the state, +1070 counts up and
    # plays a sound at some of its values; at +E36 = 0 the next pass restarts
    # the motion and goes to state 0. The caller 375AA0 discards rax.
    ("objects", "notyet", 0x375FFA, "cmp byte ptr [rcx + 0xe36], 0", 0x3760BA,
     "vtca 375FF0: `cmp +E36, 0; jne`: between stock ticks the state's end (motion "
     "restart, state 0) waits, so it comes on a stock tick as in stock"),
    ("objects", "callgate", 0x376136, "call 0x18044e470", (0x44E470,"void"),
     "vtca 375FF0: the sound 44E470 at the +1070 values it plays on: with +1070 held "
     "between stock ticks, the call runs on stock ticks only, once per value"),
    ("objects", "count", 0x37613B, "dec byte ptr [rdi + 0xe36]", None,
     "vtca 375FF0: the state's countdown +E36 -= 1 a tick"),
    ("objects", "count", 0x376141, "inc byte ptr [rdi + 0x1070]", None,
     "vtca 375FF0: the phase +1070 += 1 a tick (its sounds at fixed values)"),
    # 4873A0 (cDogLikeHm): its gatefn also ran the root motion (2DA3D0 applies the
    # motion advance's +EC0, already a tick's share) and, in sub-states 0..3,
    # 4B9B70's motion advance once a stock tick (4x slow); its quantities instead:
    ("actor", "pre", 0x4875AB, "addss xmm0, dword ptr [rbx + 0xb4]", None,
     "cDogLikeHm 4873A0, +1230 = 0: heading +B4 += the spin +1204 a tick (xmm0 holds "
     "the spin, copied at 4875A8)"),
    ("actor", "countlast", 0x4875B8, "divss xmm6, dword ptr [rip + 0x1ee484]", None,
     "cDogLikeHm 4873A0: the spin +1204 /= 1.5 a tick after it turns the heading: on "
     "the last tick of each stock period only, so the heading gains the stock spin "
     "over each period"),
    ("actor", "lin", 0x4874B6, "movss xmm6, dword ptr [rip + 0x1ea946]",
     (0x671E04, 0.10000000149011612),
     "cDogLikeHm 4873A0, +1230 = 1: heading +B4 steps 0.1 a tick toward +1234 "
     "(wrapped) and snaps to it within 0.1; xmm6 is both the step and the snap's bound"),
    ("actor", "count", 0x4875FB, "mov byte ptr [rbx + 0xe36], al", None,
     "cDogLikeHm 4873A0: +E36 += 1 a tick, two sounds at 18 and 36, back to 0 at 37: "
     "the store is skipped between stock ticks (the wrap test reads the stored byte)"),
    ("actor", "callgate", 0x48762A, "call 0x18044e3c0", (0x44E3C0,"void"),
     "cDogLikeHm 4873A0: the sound at +E36 = 18 or 36: al holds the unstored count "
     "between stock ticks, so the call runs on stock ticks only"),
    # 2026-10-02: rows from reading the near sites.
    # The animals' launch and knockback slides: each update adds the velocity
    # +E10/+E18 (set once at the action's start: a direction x a speed) to the
    # position every tick, then decays it by 0.97 or 0.95, which decay_factors.h
    # roots. The adds were left at a stock tick's displacement, so at 120 a slide
    # went about four times as far. As 205310's (a875edd1): the add scaled by s.
    ("actor", "src", 0x1D5937, "addss xmm0, dword ptr [rsi + 0xe10]", None,
     "an00 1D57B0 launch slide: position.x += +E10 a tick (the velocity's decay is "
     "decay_factors.h's, 1D596C)"),
    ("actor", "pre", 0x1D5952, "addss xmm0, dword ptr [rax + 8]", None,
     "an00 1D57B0 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at "
     "1D5943)"),
    ("actor", "pre", 0x1D8C54, "addss xmm0, dword ptr [rax]", None,
     "an01 1D8B20 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at "
     "1D8C4C)"),
    ("actor", "src", 0x1D8C68, "addss xmm0, dword ptr [rdi + 0xe18]", None,
     "an01 1D8B20 launch slide: position.z += +E18 a tick"),
    ("actor", "src", 0x1DD1CE, "addss xmm0, dword ptr [rdi + 0xe10]", None,
     "an04 1DD060 slide (while +F48 <= 20): position.x += +E10 a tick"),
    ("actor", "pre", 0x1DD1E9, "addss xmm0, dword ptr [rax + 8]", None,
     "an04 1DD060 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1DD1DA)"),
    ("actor", "pre", 0x1E0884, "addss xmm0, dword ptr [rax]", None,
     "an06/an08 1E0750 launch slide: position.x += +E10 a tick (xmm0 holds +E10, "
     "loaded at 1E087C)"),
    ("actor", "src", 0x1E0898, "addss xmm0, dword ptr [rdi + 0xe18]", None,
     "an06/an08 1E0750 launch slide: position.z += +E18 a tick"),
    ("actor", "src", 0x1E36A5, "addss xmm0, dword ptr [rdi + 0xe10]", None,
     "an07 1E3550 slide (while +F48 <= 20): position.x += +E10 a tick"),
    ("actor", "pre", 0x1E36C0, "addss xmm0, dword ptr [rax + 8]", None,
     "an07 1E3550 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1E36B1)"),
    ("actor", "pre", 0x1E6E88, "addss xmm0, dword ptr [rax]", None,
     "an09 1E6D20 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at "
     "1E6E79)"),
    ("actor", "pre", 0x1E6E9F, "addss xmm0, dword ptr [rax + 8]", None,
     "an09 1E6D20 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at "
     "1E6E90)"),
    ("actor", "src", 0x1E9C87, "addss xmm0, dword ptr [rsi + 0xe10]", None,
     "an0b 1E9B00 launch slide: position.x += +E10 a tick"),
    ("actor", "pre", 0x1E9CA2, "addss xmm0, dword ptr [rax + 8]", None,
     "an0b 1E9B00 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at "
     "1E9C93)"),
    ("actor", "src", 0x1ED0EE, "addss xmm0, dword ptr [rsi + 0xe10]", None,
     "an0c 1ECF50 launch slide: position.x += +E10 a tick"),
    ("actor", "pre", 0x1ED109, "addss xmm0, dword ptr [rax + 8]", None,
     "an0c 1ECF50 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at "
     "1ED0FA)"),
    ("actor", "src", 0x1EF942, "addss xmm0, dword ptr [rsi + 0xe10]", None,
     "an0d/an0e 1EF700 launch slide: position.x += +E10 a tick"),
    ("actor", "pre", 0x1EF962, "addss xmm0, dword ptr [rax + 8]", None,
     "an0d/an0e 1EF700 launch slide: position.z += +E18 a tick (xmm0 holds +E18, "
     "loaded at 1EF953)"),
    ("actor", "src", 0x1F09E7, "addss xmm0, dword ptr [rsi + 0xe10]", None,
     "an05/an18 1F07A0 launch slide: position.x += +E10 a tick"),
    ("actor", "pre", 0x1F0A07, "addss xmm0, dword ptr [rax + 8]", None,
     "an05/an18 1F07A0 launch slide: position.z += +E18 a tick (xmm0 holds +E18, "
     "loaded at 1F09F8)"),
    ("actor", "pre", 0x1F4770, "addss xmm0, dword ptr [rax]", None,
     "an19 1F4610 launch slide: position.x += +E10 a tick (xmm0 holds +E10, loaded at "
     "1F4761)"),
    ("actor", "pre", 0x1F4787, "addss xmm0, dword ptr [rax + 8]", None,
     "an19 1F4610 launch slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at "
     "1F4778)"),
    ("actor", "src", 0x1F73EA, "addss xmm0, dword ptr [rdi + 0xe10]", None,
     "an1a 1F7290 slide (while +F48 <= 20): position.x += +E10 a tick"),
    ("actor", "src", 0x1F7402, "addss xmm0, dword ptr [rdi + 0xe18]", None,
     "an1a 1F7290 slide: position.z += +E18 a tick"),
    ("actor", "src", 0x1FA4A5, "addss xmm0, dword ptr [rdi + 0xe10]", None,
     "an1b 1FA390 slide: position.x += +E10 a tick (its decay 0.95, decay_factors.h)"),
    ("actor", "pre", 0x1FA4C0, "addss xmm0, dword ptr [rax + 8]", None,
     "an1b 1FA390 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1FA4B1)"),
    ("actor", "src", 0x1FDE05, "addss xmm0, dword ptr [rdi + 0xe10]", None,
     "an1f 1FDCF0 slide: position.x += +E10 a tick (its decay 0.95, decay_factors.h)"),
    ("actor", "pre", 0x1FDE20, "addss xmm0, dword ptr [rax + 8]", None,
     "an1f 1FDCF0 slide: position.z += +E18 a tick (xmm0 holds +E18, loaded at 1FDE11)"),
    ("actor", "pre", 0x1FE3F4, "addss xmm0, dword ptr [rax]", None,
     "an02/an20 1FE2C0 launch slide: position.x += +E10 a tick (xmm0 holds +E10, "
     "loaded at 1FE3EC)"),
    ("actor", "src", 0x1FE408, "addss xmm0, dword ptr [rdi + 0xe18]", None,
     "an02/an20 1FE2C0 launch slide: position.z += +E18 a tick"),
    # 202DC0 (the knockback 202C40 sets up, for an09, an19 and 1FAB80's): a
    # forward step by the speed +E48 (decaying 0.97) and the slide +E10/+E18.
    ("actor", "callscale", 0x202DEB, "call 0x1802da410", (0x2DA410, "xmm1"),
     "knockback 202DC0: the forward step 2DA410 by the speed +E48 a tick (xmm1); "
     "+E48's 0.97 decay is decay_factors.h's (202DF8)"),
    ("actor", "src", 0x202E13, "addss xmm0, dword ptr [rbx + 0xe10]", None,
     "knockback 202DC0: position.x += +E10 a tick"),
    ("actor", "pre", 0x202E2E, "addss xmm0, dword ptr [rax + 8]", None,
     "knockback 202DC0: position.z += +E18 a tick (xmm0 holds +E18, loaded at 202E1F)"),
    # 206000 (cAnimal, 26 classes): as 205310's slide: on the ground (+D40 bit 3)
    # v x 0.4 a tick, in the air v; the paths join at 2062AB with xmm0 = z's step.
    ("actor", "lin", 0x206279, "mulss xmm0, dword ptr [rip + 0x4739f3]",
     (0x679C74, 0.4000000059604645),
     "cAnimal 206000 slide on the ground: x += +E10 x 0.4 a tick"),
    ("actor", "lin", 0x206291, "mulss xmm0, dword ptr [rip + 0x4739db]",
     (0x679C74, 0.4000000059604645),
     "cAnimal 206000 slide on the ground: z += +E18 x 0.4 a tick"),
    ("actor", "pre", 0x20629B, "addss xmm0, dword ptr [rax]", None,
     "cAnimal 206000 slide in the air: x += +E10 a tick (xmm0 holds +E10, loaded at "
     "20626F; entered only from 206277's je)"),
    ("actor", "dst", 0x2062A3, "movss xmm0, dword ptr [rbx + 0xe18]", None,
     "cAnimal 206000 slide in the air: +E18, z's step, scaled right after its load; "
     "the ground path joins after it at 2062AB with its own 0.4 x s"),
    ("actor", "src", 0x48573D, "addss xmm0, dword ptr [rdi + 0xe10]", None,
     "cDogLikeHm 485390: position.x += +E10 a tick while it turns toward its point "
     "(the velocity's 0.97 decay is decay_factors.h's)"),
    ("actor", "pre", 0x485758, "addss xmm0, dword ptr [rax + 8]", None,
     "cDogLikeHm 485390: position.z += +E18 a tick (xmm0 holds +E18, loaded at 485749)"),
    # an01 1D9100 case 5: walking toward a point, +1170 counts down a random 0..31
    # ticks; at 0 it reloads and +E3C (the reloads) steps, past 4 state 6.
    ("actor", "count", 0x1D932E, "mov dword ptr [rsi + 0x1170], eax", None,
     "an01 1D9100 case 5: the countdown +1170 -= 1 a tick while far from its point: "
     "the store is skipped between stock ticks"),
    ("actor", "notyet", 0x1D9334, "test ecx, ecx", 0x1D940E,
     "an01 1D9100 case 5: `test ecx, ecx; jne` on the countdown's old value: between "
     "stock ticks it reads \"not yet\", so the reload and the +E3C step come on a stock "
     "tick"),
    # cBallObj 33C290 state 2 (cBallObj, et9a, ut96: a ball rolled away): the
    # position += +E20/+E28 a tick, which decays 0.985 (decay_factors.h), and the
    # model turns by |v| x 2 pi / K a tick about the rolling axis.
    ("objects", "pre", 0x33C336, "addss xmm0, dword ptr [rax]", None,
     "cBallObj 33C290 roll: position.x += +E20 a tick (xmm0 holds +E20, loaded at "
     "33C31D)"),
    ("objects", "pre", 0x33C34D, "addss xmm0, dword ptr [rax + 8]", None,
     "cBallObj 33C290 roll: position.z += +E28 a tick (xmm0 holds +E28, loaded at "
     "33C33E)"),
    ("objects", "lin", 0x33C3B8, "mulss xmm0, dword ptr [rip + 0x335ac0]",
     (0x671E80, 6.2831854820251465),
     "cBallObj 33C290 roll: the model's turn this tick, |v| x 2 pi / K (4BD280's "
     "angle), multiplied into its matrix"),
    # objScroll's falls (35C790, 35CC30, 35D0E0, from 35C490): y += vy a tick, then
    # vy = (vy - 0.4) x 0.97 or 0.98: the gravity is phase_steps.h's, the drag
    # decay_factors.h's, so vy stays in a stock tick's units and the add needs s.
    ("objects", "pre", 0x35C8CF, "addss xmm0, dword ptr [rax + 4]", None,
     "objScroll 35C790 fall: position.y += +E10 a tick (xmm0 holds +E10, loaded at "
     "35C8C0)"),
    ("objects", "src", 0x35D001, "addss xmm0, dword ptr [rdi + 0xe24]", None,
     "objScroll 35CC30 fall: position.y += +E24 a tick"),
    ("objects", "src", 0x35D21A, "addss xmm0, dword ptr [rdi + 0xe20]", None,
     "objScroll 35D0E0 fall: position.y += +E20 a tick"),
    ("objects", "src", 0x35D456, "addss xmm0, dword ptr [rdi + 0xe24]", None,
     "objScroll 35D0E0 fall: position.y += +E24 a tick"),
    # wp20 model 0x624 (393210, the reflector's second model) and utbd 22E430:
    # two dangling parts on springs: spin -= joint x 0.05 (xmm8), joint += spin,
    # spin x 0.9 (decay_factors.h). The pull changes the spin once a stock period
    # (zfirst), the joint moves by s of it every tick.
    ("objects", "zfirst", 0x3934FC, "mulss xmm1, xmm8", None,
     "wp20 0x624 part 1: the spring's pull on the spin +1C68, joint x 0.05: kept on "
     "the first tick of each stock period, 0 on the others"),
    ("objects", "pre", 0x39352F, "addss xmm0, dword ptr [rax + 0xe4]", None,
     "wp20 0x624 part 1: joint += spin +1C68 a tick (xmm0 holds +1C68, loaded at "
     "39351F)"),
    ("objects", "zfirst", 0x3935A8, "mulss xmm1, xmm8", None,
     "wp20 0x624 part 2: the pull on the spin +1C6C, as 3934FC"),
    ("objects", "pre", 0x3935D9, "addss xmm0, dword ptr [rax + 0xe4]", None,
     "wp20 0x624 part 2: joint += spin +1C6C a tick (xmm0 holds +1C6C, loaded at "
     "3935CB)"),
    ("objects", "zfirst", 0x22E704, "mulss xmm1, xmm8", None,
     "utbd 22E430 part 1: the spring's pull on the spin +1104, joint x 0.05: kept on "
     "the first tick of each stock period"),
    ("objects", "src", 0x22E737, "addss xmm0, dword ptr [rsi + 0x1104]", None,
     "utbd 22E430 part 1: joint += spin +1104 a tick"),
    ("objects", "zfirst", 0x22E7B0, "mulss xmm1, xmm8", None,
     "utbd 22E430 part 2: the pull on the spin +1108, as 22E704"),
    ("objects", "src", 0x22E7DE, "addss xmm0, dword ptr [rsi + 0x1108]", None,
     "utbd 22E430 part 2: joint += spin +1108 a tick"),
    ("objects", "src", 0x22E5B8, "addss xmm1, xmm8", None,
     "utbd 22E430 state 3: the scale +C0 += 0.05 a tick up to 0.7"),
    ("objects", "src", 0x22E5BD, "addss xmm0, xmm8", None,
     "utbd 22E430 state 3: the scale +C8 += 0.05 a tick up to 0.7"),
    ("objects", "count", 0x22E60F, "mov byte ptr [rdi + 0xe36], al", None,
     "utbd 22E430 state 5: the countdown +E36 -= 1 a tick: the store is skipped "
     "between stock ticks"),
    ("objects", "notyet", 0x22E615, "test cl, cl", 0x22E673,
     "utbd 22E430 state 5: `test cl, cl; jne` on the countdown's old value: between "
     "stock ticks \"not yet\", so state 6 starts on a stock tick"),
    ("objects", "pre", 0x38F741, "addss xmm0, dword ptr [rax]", None,
     "wp1c 38F400: position.x += +E20 a tick (xmm0 holds +E20, loaded at 38F734); "
     "+E20's acceleration is a world row (38F714) and its 0.94 decay decay_factors.h's"),
    ("objects", "pre", 0x38F75B, "addss xmm0, dword ptr [rax + 8]", None,
     "wp1c 38F400: position.z += +E28 a tick (xmm0 holds +E28, loaded at 38F74C)"),
    # pl00 states 0 and 1 (3B18D0, 3B2620): position += +10A0/+10A8 a tick, then
    # x 0.98 (decay_factors.h): a push on Amaterasu that slides her.
    ("player", "pre", 0x3B209E, "addss xmm0, dword ptr [rax]", None,
     "pl00 state 0 3B18D0: position.x += +10A0 a tick (xmm0 holds +10A0, loaded at "
     "3B2096); its 0.98 decay is decay_factors.h's"),
    ("player", "pre", 0x3B20B5, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 state 0 3B18D0: position.z += +10A8 a tick (xmm0 holds +10A8, loaded at "
     "3B20A6)"),
    ("player", "pre", 0x3B297F, "addss xmm0, dword ptr [rax]", None,
     "pl00 state 1 3B2620: position.x += +10A0 a tick (xmm0 holds +10A0, loaded at "
     "3B2977)"),
    ("player", "src", 0x3B2993, "addss xmm0, dword ptr [rdi + 0x10a8]", None,
     "pl00 state 1 3B2620: position.z += +10A8 a tick"),
    # an0b 1EC2C0: +1170 counts down a random 0..31 ticks; at 0 a new wander
    # point +1160 (random within 220 of its anchor) and a reload.
    ("actor", "count", 0x1EC414, "mov dword ptr [rdi + 0x1170], eax", None,
     "an0b 1EC2C0: the wander countdown +1170 -= 1 a tick: the store is skipped "
     "between stock ticks"),
    ("actor", "notyet", 0x1EC41A, "test ecx, ecx", 0x1EC48D,
     "an0b 1EC2C0: `test ecx, ecx; jne` on the countdown's old value: between stock "
     "ticks \"not yet\", so the new point is picked on a stock tick"),
    ("objects", "pre", 0x20981F, "addss xmm0, dword ptr [rax + 4]", None,
     "cKiType 2097C0 state 2 (a thrown or knocked object's fall): position.y += +E54 a "
     "tick (xmm0 holds +E54, just stored); its gravity 0.6 is phase_steps.h's (209808)"),
    ("objects", "count", 0x214059, "sub eax, 1",
     (0x21402E,0x21405C,(0x21402E,0x214034,0x214036,0x214059),None),
     "ut04 213FB0 state 2: the countdown +111C -= 1 a tick (from 10): a skipped tick "
     "reads \"not finished\", as stock between its ticks"),
    ("actor", "count", 0x20C798, "mov byte ptr [rbx + 0xd79], al", None,
     "slot 1 of 780 actor classes (20C620): the fade-in byte +D79 += 25 a tick up to "
     "255: the store is skipped between stock ticks"),
    # 21E850 / 21EBD0 / 21EF90 (five or six object classes): state 3's wait +13F0
    # -= ecx, which is 1 there (`cmp ecx, 1; jne` before), and state 1's -= 1;
    # jns: at -1 the state moves on. 21EDCC/21F18C pace the other waits.
    ("objects", "count", 0x21E98A, "sub dword ptr [rbx + 0x13f0], ecx", "down",
     "21E850 state 3: the wait +13F0 -= 1 a tick (ecx is 1: `cmp ecx, 1; jne` just "
     "before); a skipped tick reads \"not finished\" for the jns"),
    ("objects", "count", 0x21EA1E, "sub dword ptr [rbx + 0x13f0], 1", None,
     "21E850 state 1: the wait +13F0 -= 1 a tick"),
    ("objects", "count", 0x21ED02, "sub dword ptr [rbx + 0x13f0], edx", "down",
     "21EBD0 state 3: the wait +13F0 -= 1 a tick (edx is 1: `cmp edx, 1; jne` just "
     "before)"),
    ("objects", "count", 0x21F0C2, "sub dword ptr [rbx + 0x13f0], ecx", "down",
     "21EF90 state 3: the wait +13F0 -= 1 a tick (ecx is 1: `cmp ecx, 1; jne` just "
     "before)"),
    ("objects", "src", 0x22F83E, "addss xmm0, dword ptr [rcx + 0x1094]", None,
     "utcb 22F820: position.y += +1094 a tick, the speed growing by 0.5 a tick to 9.5 "
     "(phase_steps.h, 22F86A)"),
    ("objects", "src", 0x22F848, "subss xmm0, dword ptr [rcx + 0x1094]", None,
     "utcb 22F820: position.y -= +1094 a tick (the other direction)"),
    ("actor", "count", 0x241296, "mov byte ptr [rdi + 0x1136], al", None,
     "em00..em03 update (241180): the slot-8 effect spawner +1136 += 1 a tick, at 2 an "
     "effect and 0 (as em05's 25141C)"),
    ("actor", "count", 0x2412E8, "inc word ptr [rdi + 0x12b6]", None,
     "em00..em03 update (241180): +12B6 counts the ticks it spends more than 20 below "
     "its target's height"),
    ("actor", "pre", 0x256255, "addss xmm0, dword ptr [rax + 8]", None,
     "255ED0: position.z += +E18 a tick (xmm0 holds +E18, loaded at 256246); x "
     "approaches its point through the blend literal 256222"),
    ("objects", "count", 0x2313BE, "mov byte ptr [rbx + 0x1630], al", None,
     "utd7 231200: the cooldown +1630 -= 1 a tick while not 0 (at 0 the check 2DC7B0 "
     "runs and may reload it): the store is skipped between stock ticks"),
    ("actor", "lin", 0x25E535, "addss xmm0, dword ptr [rip + 0x4138d7]", (0x671E14, 2.0),
     "em12 25E4C0: the orbit radius +1384 += 2 a tick up to 150 + 22 x +1146"),
    ("actor", "lin", 0x272F5A, "subss xmm1, dword ptr [rip + 0x406a52]", (0x6799B4, 4.0),
     "em27/em29 272EC0: the orbit radius +1414 -= 4 a tick down to 0 (its growth by 2 "
     "is the world literal 272F12)"),
    ("actor", "count", 0x27881C, "mov word ptr [rsi + 0xe3e], ax", None,
     "em2b 278590: +E3E -= 1 a tick while above 0 (at 0 an effect and a reload to 1: "
     "one every other tick): the store is skipped between stock ticks"),
    ("actor", "notyet", 0x2787CB, "test ax, ax", 0x278811,
     "em2b 278590: `test ax, ax; jg` on +E3E: between stock ticks \"above 0\", so the "
     "effect and its reload come on stock ticks"),
    ("actor", "pre", 0x286B86, "addss xmm0, dword ptr [r14 + 0x11c0]", None,
     "em3d 2865B0: the clock +11C0 += speed (+1080) a tick (xmm0 holds the speed, "
     "copied at 286B83)"),
    ("actor", "pre", 0x286BB2, "addss xmm0, dword ptr [rbx + 4]", None,
     "em3d 2865B0: position.y += sin(+1258) x 0.7 x speed a tick (xmm0 holds that "
     "step); the phase +1258's step is the world step row 286BBC"),
    ("actor", "lin", 0x28D254, "addss xmm1, dword ptr [rip + 0x3e4bb8]", (0x671E14, 2.0),
     "em4d/em4e/em50 28D1A0: position.y += 2 a tick while below +E50 + 55 (the rise "
     "before its bob)"),
    ("actor", "lin", 0x28D72D, "addss xmm1, dword ptr [rip + 0x3e46df]", (0x671E14, 2.0),
     "em4d/em4e 28D320: the same rise, y += 2 a tick"),
    ("actor", "lin", 0x2911FA, "addss xmm1, dword ptr [rip + 0x3e0c12]", (0x671E14, 2.0),
     "em50 290EC0: the same rise, y += 2 a tick"),
    ("actor", "src", 0x29D454, "subss xmm1, xmm0", None,
     "em56 29D3B0: position.y -= 2 x speed (+1080) a tick while above its floor (xmm0 "
     "holds 2 x speed)"),
    ("actor", "src", 0x29D4C2, "addss xmm1, dword ptr [rcx + 0x1080]", None,
     "em56 29D3B0: position.y += speed (+1080) a tick while below its ceiling"),
    ("actor", "count", 0x2A4E49, "dec ax",
     (0x2A4E2E,0x2A4E4C,(0x2A4E2E,0x2A4E35,0x2A4E38,0x2A4E49),None),
     "29F770's state 2A4BA0: the wait +E3C -= 1 a tick while not 0 (at 0 the state "
     "ends): skipped between stock ticks"),
    ("actor", "notyet", 0x2A4E35, "test ax, ax", 0x2A4E49,
     "29F770's state 2A4BA0: `test ax, ax; jne` on +E3C: between stock ticks \"not 0\", "
     "so the state ends on a stock tick"),
    ("actor", "pre", 0x2D49A4, "addss xmm2, dword ptr [rbx + 0x11a4]", None,
     "em6a 2D48E0: the glow +11A4 += |sin(+11A0) x 8| a tick up to 255 (xmm2 holds "
     "that step)"),
    # em8f's body (its parts were ffe6c5c8's): the death 2D90E0 (cases 1, 3), the
    # hover 2D9460/2D9940 and the return 2D9C00.
    ("actor", "scaledadd", 0x2D9192, "call qword ptr [rip + 0x397c68]", None,
     "em8f 2D90E0 case 3 (dying): position += the velocity +E10..+E18 a tick "
     "(cVec::operator+=)"),
    ("actor", "scaledadd", 0x2D92E2, "call qword ptr [rip + 0x397b18]", None,
     "em8f 2D90E0 case 1: position += the velocity a tick"),
    ("actor", "countlast", 0x2D91B0, "mulss xmm1, dword ptr [rip + 0x3a0fac]", None,
     "em8f 2D90E0 case 3: the horizontal velocity +E10 x -0.4 a tick (a shake that "
     "dies out): on the last tick of each stock period only, so it flips once a stock "
     "tick"),
    ("actor", "countlast", 0x2D91C8, "mulss xmm0, dword ptr [rip + 0x3a0f94]", None,
     "em8f 2D90E0 case 3: +E18 x -0.4, as 2D91B0"),
    ("actor", "countlast", 0x2D9300, "mulss xmm1, dword ptr [rip + 0x3a0e5c]", None,
     "em8f 2D90E0 case 1: +E10 x -0.4, as 2D91B0"),
    ("actor", "countlast", 0x2D9318, "mulss xmm0, dword ptr [rip + 0x3a0e44]", None,
     "em8f 2D90E0 case 1: +E18 x -0.4, as 2D91B0"),
    ("actor", "lin", 0x2D917B, "subss xmm0, dword ptr [rip + 0x3a0b4d]",
     (0x679CD0, 0.014999999664723873),
     "em8f 2D90E0 case 3: the alpha +D2C -= 0.015 a tick until it is gone"),
    ("actor", "srcblend", 0x2D9666, "mulss xmm0, dword ptr [rdi + 0x1238]", None,
     "em8f 2D9460: y approaches its hover height (sin x 12 + floor + 30) by +1238 a "
     "tick, a factor that grows by 0.05 a tick (phase_steps.h)"),
    ("actor", "blend", 0x2D96FC, "mulss xmm0, dword ptr [rip + 0x39deec]",
     (0x6775F0, 0.05000000074505806),
     "em8f 2D9460: y approaches sin x 6 + floor + 20 by 0.05 a tick"),
    ("actor", "blend", 0x2D9A6D, "mulss xmm0, dword ptr [rip + 0x39db7b]",
     (0x6775F0, 0.05000000074505806),
     "em8f 2D9940: y approaches sin x 3 + floor + 20 by 0.05 a tick"),
    ("actor", "srcblend", 0x2D9AC6, "mulss xmm0, dword ptr [rdi + 0xe20]", None,
     "em8f 2D9940: x approaches its target's x by +E20 a tick (+E20 grows by 0.02 a "
     "tick, phase_steps.h)"),
    ("actor", "srcblend", 0x2D9AEF, "mulss xmm1, dword ptr [rdi + 0xe20]", None,
     "em8f 2D9940: y approaches its target's y + 28 by +E20 a tick"),
    ("actor", "srcblend", 0x2D9B19, "mulss xmm0, dword ptr [rdi + 0xe20]", None,
     "em8f 2D9940: z approaches its target's z by +E20 a tick"),
    ("actor", "blend", 0x2D9B73, "mulss xmm1, dword ptr [rip + 0x398db1]",
     (0x67292C, 0.20000000298023224),
     "em8f 2D9940: the alpha +D2C approaches 0.3 by 0.2 a tick"),
    ("actor", "blend", 0x2D9B89, "mulss xmm1, dword ptr [rip + 0x398273]",
     (0x671E04, 0.10000000149011612),
     "em8f 2D9940: the alpha +D2C approaches 0.6 by 0.1 a tick"),
    ("actor", "blend", 0x2D9CBD, "mulss xmm6, dword ptr [rip + 0x398c67]",
     (0x67292C, 0.20000000298023224),
     "em8f 2D9C00 state 2: the alpha +D2C approaches 1 by 0.2 a tick"),
    ("actor", "blend", 0x2D9CDE, "mulss xmm1, dword ptr [rip + 0x39811e]",
     (0x671E04, 0.10000000149011612),
     "em8f 2D9C00 state 2: y approaches the floor +E50 by 0.1 a tick"),
    ("objects", "lin", 0x2E2703, "movss xmm1, dword ptr [rip + 0x4bd955]",
     (0x7A0060, -0.0025833332911133766),
     "et07 2E25B0: material 1's U += -0.002583 a tick (a .data constant, 7A0060), "
     "wrapped into -1..1"),
    ("objects", "count", 0x2E2D60, "mov word ptr [rbx + 0xe3c], cx", None,
     "et07 2E2BE0 case 1: the fade-in count +E3C -= 1 a tick from 15 (alpha = (15 - "
     "it) / 15): the store is skipped between stock ticks"),
    ("objects", "src", 0x2E39FF, "subss xmm0, dword ptr [rcx + rsi + 0x7a0084]", None,
     "et08 2E36F0 case 4: submodel 1 sinks by the .data table's step a tick (7A0084 + "
     "0x1C x +1C7) until it is at 0"),
    ("objects", "count", 0x2E555B, "sub dword ptr [rdi + 0x112c], 1", None,
     "et0f 2E5330: +112C -= 1 a tick from 150 while it closes in; below 0 its speed "
     "rises to 9"),
    ("objects", "count", 0x2E6D13, "dec dword ptr [rbx + 0x1080]", None,
     "et12 2E6C80: the wait +1080 -= 1 a tick from 60"),
    ("objects", "notyet", 0x2E6D19, "cmp dword ptr [rbx + 0x1080], 0", 0x2E6D28,
     "et12 2E6C80: `cmp +1080, 0; jg`: between stock ticks \"above 0\", so the state's "
     "step comes on a stock tick"),
    ("objects", "lin", 0x2E84C2, "movss xmm0, dword ptr [rip + 0x4b7cfa]",
     (0x7A01C4, 0.0005000000237487257),
     "et24 2E83E0: the phase +1088 += 0.0005 a tick (a .data constant, 7A01C4), "
     "wrapped"),
    ("objects", "lin", 0x2EA9B1, "subss xmm0, dword ptr [rip + 0x38744f]", (0x671E08, 0.5),
     "et2e 2EA790: position.y -= 0.5 a tick as it sinks"),
    ("objects", "src", 0x2F2E38, "subsd xmm0, qword ptr [rip + 0x385690]", None,
     "et6b 2F2970 case 8: the alpha +D2C -= a double constant (6784D0) a tick down to "
     "0 while +1080 counts 30"),
    ("objects", "srcblend", 0x307619, "divss xmm6, xmm0", None,
     "307110's 307340: x moves (target - x) / (+E3C + 1) a tick, +E3C paced by "
     "action_timers.h: the divisor's blend, so x passes stock's values at its stock "
     "ticks and lands when +E3C is 0"),
    ("objects", "srcblend", 0x307642, "divss xmm2, xmm0", None,
     "307110's 307340: z the same (xmm0 holds +E3C + 1)"),
    ("human", "count", 0x314DB2, "mov word ptr [rbx + 0x1328], ax", None,
     "cHumanSpa/hm0a/hm0b/hm5d 314B60: the countdown +1328 -= 1 a tick while not 0: "
     "the store is skipped between stock ticks"),
    ("human", "count", 0x314DC6, "mov byte ptr [rbx + 0x1327], al", None,
     "314B60: the countdown +1327 -= 1 a tick while not 0"),
    ("human", "count", 0x314DD9, "mov byte ptr [rbx + 0x132c], al", None,
     "314B60: the countdown +132C -= 1 a tick while not 0"),
    ("objects", "blend", 0x31606F, "mulss xmm1, dword ptr [rip + 0x35bd8d]",
     (0x671E04, 0.10000000149011612),
     "314B60's 315E60: x approaches its submodel's x by 0.1 a tick"),
    ("objects", "src", 0x3160C1, "addss xmm0, dword ptr [rbx + 0xe14]", None,
     "314B60's 315E60: y += +E14 a tick, a rise speed growing by 0.5 a tick to 1.5 "
     "(phase_steps.h, 316099)"),
    ("human", "count", 0x327724, "inc dword ptr [rbx + 0x1450]", None,
     "hm3c 327400: the material flipbook's tick +1450 += 1 a tick (frames at +1450 / 5 "
     "and / 3, mod 31)"),
    ("objects", "pre", 0x33ACCF, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "cBallObj 33ABC0: the vertical velocity +E54 += +112C a tick while 4643B0 holds "
     "(xmm0 holds +112C, loaded at 33ACC7); +E54 is in a stock tick's units (srcx "
     "33B052 scales its add to y)"),
    ("objects", "blend", 0x3421C9, "movss xmm4, dword ptr [rip + 0x33385f]",
     (0x675A30, 0.30000001192092896),
     "cEnemyObj 341F10: material 4's colour (+50/+54/+58) approaches its target by 0.3 "
     "a tick (xmm4 is only that factor)"),
    ("objects", "blend", 0x342537, "movss xmm4, dword ptr [rip + 0x3334f1]",
     (0x675A30, 0.30000001192092896),
     "cEnemyObj 3423D0: material 4's colour approaches its target by 0.3 a tick (xmm4 "
     "is only that factor)"),
    ("objects", "pre", 0x36884E, "addss xmm0, dword ptr [rax + 4]", None,
     "cKiType014/vt4a..4c 368790: position.y += +E54 a tick (xmm0 holds +E54, just "
     "stored); its gravity 0.6 is phase_steps.h's"),
    ("objects", "pre", 0x3690F6, "addss xmm0, dword ptr [rax + 4]", None,
     "cKiType017 369090: position.y += +E54 a tick, as 36884E"),
    ("objects", "pre", 0x369AD6, "addss xmm0, dword ptr [rax + 4]", None,
     "cKiType018/vt53 369A70: position.y += +E54 a tick, as 36884E"),
    ("objects", "pre", 0x36AACC, "addss xmm1, dword ptr [rax + 4]", None,
     "cKiType023/vt4f 36AA30: position.y += +E54 a tick (xmm1 holds +E54, just "
     "stored); its gravity 0.2 is phase_steps.h's"),
    ("objects", "scaledadd", 0x371F0E, "call qword ptr [rip + 0x2feeec]", None,
     "vt29 371DE0: position += a turned (0, +E2C, K) a tick (cVec::operator+=)"),
    ("objects", "lin", 0x371F1C, "subss xmm0, dword ptr [rip + 0x307ce8]",
     (0x679C0C, 0.1745329201221466),
     "vt29 371DE0: its roll +B8 -= 10 degrees a tick"),
    ("player", "lin", 0x38C2E2, "addss xmm0, dword ptr [rip + 0x2f221a]",
     (0x67E504, 0.3490658402442932),
     "wp11 38C160 state 1: its spin +1078 += 20 degrees a tick"),
    ("player", "src", 0x38DBBA, "addss xmm0, dword ptr [rbx + 0xe20]", None,
     "wp1a 38DB30: position.x += +E20 a tick (its 0.95 decay is decay_factors.h's, "
     "38DBE7)"),
    ("player", "src", 0x38DBD2, "addss xmm0, dword ptr [rbx + 0xe28]", None,
     "wp1a 38DB30: position.z += +E28 a tick"),
    ("player", "pre", 0x38DD7E, "addss xmm0, dword ptr [rax]", None,
     "wp1a 38DCB0: position.x += +E20 a tick (xmm0 holds +E20, loaded at 38DD67)"),
    ("player", "pre", 0x38DD95, "addss xmm0, dword ptr [rax + 8]", None,
     "wp1a 38DCB0: position.z += +E28 a tick (xmm0 holds +E28, loaded at 38DD86)"),
    ("player", "lin", 0x390309, "addss xmm0, dword ptr [rip + 0x2e993b]",
     (0x679C4C, 0.5235987901687622),
     "wp1d 390110: its spin +B0 += 30 degrees a tick"),
    ("player", "lin", 0x392A55, "movss xmm1, dword ptr [rip + 0x41513f]",
     (0x7A7B9C, -0.0025833332911133766),
     "wp1e 392990: material 1's U += -0.002583 a tick (a .data constant, 7A7B9C), "
     "wrapped into -1..1"),
    ("player", "count", 0x392E3F, "mov word ptr [rbx + 0xe3c], cx", None,
     "wp1e 392D00 case 1: the fade-in count +E3C -= 1 a tick from 15: the store is "
     "skipped between stock ticks"),
    ("objects", "count", 0x3930CE, "mov byte ptr [rdi], al", None,
     "392FE0 case 5 (a part's grow-in helper): its counter (param 4) -= 1 a tick from "
     "5: the store is skipped between stock ticks"),
    ("objects", "notyet", 0x3930D0, "test cl, cl", 0x39312D,
     "392FE0 case 5: `test cl, cl; jne` on the counter's old value: between stock "
     "ticks \"not yet\", so case 6 starts on a stock tick"),
    ("objects", "count", 0x396F8E, "mov byte ptr [rdi], al", None,
     "396EA0 case 5 (the same helper's copy): the counter -= 1 a tick from 5"),
    ("objects", "notyet", 0x396F90, "test cl, cl", 0x396FED,
     "396EA0 case 5: as 3930D0"),
    ("player", "count", 0x39B092, "sub word ptr [rdi + 0x10f8], 1", None,
     "wp47 39AEB0: the repeat timer +10F8 -= 1 a tick, reloaded when it goes below 0"),
    ("player", "count", 0x39B2B0, "sub word ptr [rdi + 0x10f8], 1", None,
     "wp47 39B170: the repeat timer +10F8 -= 1 a tick, as 39B092"),
    ("player", "lin", 0x39DE46, "addss xmm0, dword ptr [rip + 0x2dbdfe]",
     (0x679C4C, 0.5235987901687622),
     "wp4c 39DDB0 state 1: its spin +B0 += 30 degrees a tick (+ a random 0..20, "
     "39DE4E)"),
    ("player", "lin", 0x39DE4E, "mulss xmm1, dword ptr [rip + 0x2e06ae]",
     (0x67E504, 0.3490658402442932),
     "wp4c 39DDB0 state 1: the spin's random part, x 20 degrees a tick"),
    ("player", "callscale", 0x39DE7A, "call 0x1802da460", (0x2DA460, "xmm1"),
     "wp4c 39DDB0 state 1: the forward step 2DA460 by 5 a tick (xmm1)"),
    # pl00's water states (3B, 3C swimming, 3D) move by the speed +E48 through
    # 2DA460 (3C40DE, 3C493B, 3C50E3) and have no rows: +E48 is a per-tick speed
    # in every pl00 state, and they hand it to and from the ground, the jumps
    # and the stroke 54. The swimming fix is on its accelerations instead
    # (kSwimAccelSites in the patch source, ts^2 like kAirAccelSites). Rows
    # here that scaled the moves (a build before the release) cut her speed to a
    # quarter on entering the water at 120.
    ("player", "dst", 0x3A0440, "movaps xmm6, xmm0", ("slowmo",0x3A0434),
     "wp55 3A0410: xmm6 keeps the slow-motion factor (23AD90) as its dt: its readers "
     "are the countdown +1108 -= dt (3A05F2) and the forward step dt x speed (3A062E, "
     "2DA410), each a tick's step"),
    # pl00 integrates its vertical velocity +E54 as y += timeScale x +E54 (and
    # gravity -= timeScale x 0.7), so +E54 is in a stock tick's units: what adds to
    # it every tick, or moves y by itself, wants s.
    ("player", "pre", 0x3A789A, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "pl00 3A75C0: +E54 += +10A4 a tick while +10A4 > 0, the push's vertical part "
     "(xmm0 holds +10A4, loaded at 3A788D)"),
    ("player", "pre", 0x3A78B3, "addss xmm0, dword ptr [rax + 4]", None,
     "pl00 3A75C0: y += +10A4 a tick while +10A4 <= 0 (xmm0 holds +10A4)"),
    ("player", "root", 0x3AAEE9, "movss xmm12, dword ptr [rip + 0x2c7a3a]", None,
     "pl00 3A9630: xmm12 = 0.2, only the factor +E54 x 0.2 a tick while she rides "
     "something whose height changed (3AB70B)"),
    ("player", "pre", 0x3B5648, "addss xmm0, dword ptr [rax]", None,
     "pl00 3B3FF0: position.x += the push +10A0 a tick (xmm0 holds +10A0, loaded at "
     "3B5640); its 0.98 decay is decay_factors.h's"),
    ("player", "pre", 0x3B565F, "addss xmm0, dword ptr [rax + 8]", None,
     "pl00 3B3FF0: position.z += +10A8 a tick (xmm0 holds +10A8, loaded at 3B5657)"),
    ("player", "lin", 0x3BC9DB, "addss xmm1, dword ptr [rip + 0x2f2615]",
     (0x6AEFF8, 0.5249999761581421),
     "pl00 3BC710 case 1: +E54 += 0.525 a tick"),
    ("player", "pre", 0x3BB844, "addss xmm0, dword ptr [rdi + 0xec8]", None,
     "pl00 3B9A70: the root motion's z step +EC8 += +E48 a tick, a forward drive "
     "decaying 0.9 (decay_factors.h); xmm0 holds +E48 (loaded at 3BB839)"),
    ("player", "pre", 0x3C5DE3, "addss xmm0, dword ptr [rax]", None,
     "pl00 3C57A0: position.x += the push +10A0 a tick (xmm0 holds +10A0, loaded at "
     "3C5DDB); its 0.98 decay is decay_factors.h's"),
    ("player", "src", 0x3C5DF7, "addss xmm0, dword ptr [rbx + 0x10a8]", None,
     "pl00 3C57A0: position.z += the push +10A8 a tick"),
    ("player", "pre", 0x3C6984, "addss xmm0, dword ptr [rax + 4]", None,
     "pl00 3C68C0: y += +E54 = +E42 + 1 a tick (+E42 counts up on stock ticks, "
     "memory_timers.h); xmm0 holds that step"),
    ("player", "lin", 0x3C9BB6, "mulss xmm0, dword ptr [rip + 0x2e5442]",
     (0x6AF000, 0.7999999523162842),
     "pl00 3C9940: a submodel's y += sin(+E3C degrees) x 0.8 a tick (a bob)"),
    ("player", "count", 0x3C9BC8, "add word ptr [rdi + 0xe3c], 8", None,
     "pl00 3C9940: the bob's phase +E3C += 8 degrees a tick: skipped between stock "
     "ticks"),
    ("player", "callscale", 0x3CA555, "call 0x1802ddf90", (0x2DDF90, "xmm3"),
     "pl00 3CA320 case 1: each tick she turns toward the lock-on target by at most 16 "
     "degrees (2DDF90's limit, xmm3)"),
    ("player", "callscale", 0x3CA6F4, "call 0x1802ddf90", (0x2DDF90, "xmm3"),
     "pl00 3CA320 case 3: each tick she turns toward the target by at most 8 degrees"),
    ("player", "countlast", 0x3CA75A, "mulss xmm0, dword ptr [rip + 0x2a76aa]", None,
     "pl00 3CA320 case 3: +E48 x 0.6 a tick while +E58 bit 1 holds (after the "
     "mode-table pair): on the last tick of each stock period only"),
    ("menu", "count", 0x3FCF50, "sub word ptr [rcx + 0x7c], 1", None,
     "cCockGameOver 3FCF50: the countdown +7C -= 1 a tick from 60; below 0 the "
     "screen's step +61 and a reload"),
    ("menu", "count", 0x45917F, "sub dword ptr [rbx + 0x68], eax", "down",
     "459120 state 3 (a layout's wait): +68 -= 1 a tick (eax is 1: `cmp eax, 1; jne` "
     "just before); a skipped tick reads \"not finished\" for the jns"),
    ("menu", "pre", 0x4591C7, "addss xmm0, dword ptr [rdi + 0x2c]", None,
     "459120 state 1: a layout element's +2C += +48C a tick, a speed growing by 0.05 a "
     "tick (phase_steps.h); xmm0 holds +48C, just stored"),
    ("objects", "srcblend", 0x49948D, "divss xmm1, xmm0", None,
     "cItemObj 499410: x moves (target - x) / +E3C a tick, +E3C counted down by "
     "memory_timers.h: the divisor's blend"),
    ("objects", "srcblend", 0x4994B8, "divss xmm2, xmm0", None,
     "cItemObj 499410: z the same"),
    ("objects", "srcblend", 0x499638, "divss xmm1, xmm0", None,
     "cItemObj 4995A0: x moves (+E10 - x) / +E3C a tick, as 49948D"),
    ("objects", "srcblend", 0x499666, "divss xmm2, xmm0", None,
     "cItemObj 4995A0: z the same"),
    ("objects", "src", 0x499878, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "cItemObj 4997D0: y += +E54 (0.8, set just before) a tick"),
    ("objects", "lin", 0x4C20E7, "movss xmm6, dword ptr [rip + 0x1b5501]",
     (0x6775F0, 0.05000000074505806),
     "4C1F50: +D2C += 0.05 a tick up to 1 (xmm6 is only that step)"),
    ("objects", "src", 0x4F0EA6, "subss xmm1, xmm0", None,
     "ut23 4F0CD0: its spin +1164 -= 0.00058 a tick while its count is under 120, "
     "floored at 0.00058 (the floor compare keeps xmm0)"),
    ("objects", "src", 0x4F1081, "subss xmm1, xmm0", None,
     "ut23 4F0CD0: the same in its other state"),
    ("objects", "count", 0x4F1A76, "mov word ptr [rdi + 0xe42], ax", None,
     "ut25 4F1910: the wait +E42 -= 1 a tick while above its target and above 0: the "
     "store is skipped between stock ticks"),
    ("objects", "src", 0x509E02, "addss xmm0, dword ptr [rbx + 0x1098]", None,
     "ut1b 509D10: position.y += +1098 a tick, its rise speed falling by 0.5 a tick "
     "(phase_steps.h, 509E17)"),
    ("objects", "count", 0x50E6FA, "inc dword ptr [rbx + 0x1134]", None,
     "cDigObj 50E600: +1134 += 1 a tick up to 10 (then the fade by 0.06 a tick, "
     "phase_steps.h)"),
    ("objects", "lin", 0x515A55, "movss xmm0, dword ptr [rip + 0x2a2d1f]",
     (0x7B877C, 0.0005000000237487257),
     "es13 515970: the phase +10E0 += 0.0005 a tick (a .data constant, 7B877C), "
     "wrapped"),
    ("objects", "lin", 0x5525F5, "mulss xmm0, dword ptr [rip + 0x123433]",
     (0x675A30, 0.30000001192092896),
     "ut47 5525B0: y -= sin(+1084) x 0.3 a tick (a bob; +1084's step is the world "
     "literal 55260E)"),
    ("objects", "lin", 0x5530CB, "mulss xmm0, dword ptr [rip + 0x12295d]",
     (0x675A30, 0.30000001192092896),
     "ut47 553000: the same bob, y -= sin(+1084) x 0.3 a tick"),
    ("objects", "src", 0x55D731, "addss xmm0, dword ptr [rbx + 0xe54]", None,
     "uta2 55D630: position.y += +E54 a tick, its gravity 0.2 phase_steps.h's (55D746)"),
    ("objects", "blend", 0x560996, "mulss xmm0, dword ptr [rip + 0x116c52]",
     (0x6775F0, 0.05000000074505806),
     "uta4 5607A0: y approaches its hover height by 0.05 a tick"),
    ("objects", "srcblend", 0x560E5A, "mulss xmm0, dword ptr [rbx + 0xe20]", None,
     "uta4 560BD0: x approaches its target by +E20 a tick (+E20 grows by 0.02 a tick, "
     "phase_steps.h)"),
    ("objects", "srcblend", 0x560E8A, "mulss xmm0, dword ptr [rbx + 0xe20]", None,
     "uta4 560BD0: y approaches its target's y + 20 by +E20 a tick"),
    ("objects", "srcblend", 0x560EB4, "mulss xmm0, dword ptr [rbx + 0xe20]", None,
     "uta4 560BD0: z approaches its target's z by +E20 a tick"),
    ("objects", "blend", 0x560F0F, "mulss xmm1, dword ptr [rip + 0x111a15]",
     (0x67292C, 0.20000000298023224),
     "uta4 560BD0: the alpha +D2C approaches 0.6 by 0.2 a tick"),
    ("objects", "blend", 0x560F29, "mulss xmm6, dword ptr [rip + 0x110ed3]",
     (0x671E04, 0.10000000149011612),
     "uta4 560BD0: the alpha +D2C approaches its other target by 0.1 a tick"),
    ("objects", "blend", 0x5613E4, "mulss xmm1, dword ptr [rip + 0x110a18]",
     (0x671E04, 0.10000000149011612),
     "uta4 561360 case 3: the alpha +D2C approaches its target by 0.1 a tick"),
    ("objects", "scaledadd", 0x5613F8, "call qword ptr [rip + 0x10fa02]", None,
     "uta4 561360 case 3: position += the velocity +E10..+E18 a tick "
     "(cVec::operator+=)"),
    ("objects", "scaledadd", 0x561629, "call qword ptr [rip + 0x10f7d1]", None,
     "uta4 561360's other case: position += the velocity a tick"),
    ("objects", "countlast", 0x561416, "mulss xmm1, dword ptr [rip + 0x118d4a]", None,
     "uta4 561360: the horizontal velocity +E10 x -0.6 a tick (a shake that dies out): "
     "on the last tick of each stock period only"),
    ("objects", "countlast", 0x56142E, "mulss xmm0, dword ptr [rip + 0x118d32]", None,
     "uta4 561360: +E18 x -0.6, as 561416"),
    ("objects", "countlast", 0x561647, "mulss xmm1, dword ptr [rip + 0x118b19]", None,
     "uta4 561360's other case: +E10 x -0.6, as 561416"),
    ("objects", "countlast", 0x56165F, "mulss xmm0, dword ptr [rip + 0x118b01]", None,
     "uta4 561360's other case: +E18 x -0.6, as 561416"),
    ("objects", "srcblend", 0x5618BE, "mulss xmm0, dword ptr [rdi + 0x1118]", None,
     "uta4 5616C0: y approaches its hover height by +1118 a tick (a factor it grows)"),
    ("objects", "blend", 0x561CB0, "mulss xmm0, dword ptr [rip + 0x117f78]",
     (0x679C30, 0.019999999552965164),
     "uta4 561A90: y approaches its hover height by 0.02 a tick"),
    ("objects", "blend", 0x561DFE, "mulss xmm0, dword ptr [rip + 0x117e2a]",
     (0x679C30, 0.019999999552965164),
     "uta4 561A90: the same in its next case"),
    ("objects", "blend", 0x561F4C, "mulss xmm0, dword ptr [rip + 0x117cdc]",
     (0x679C30, 0.019999999552965164),
     "uta4 561A90: the same in its third case"),
    ("objects", "lin", 0x5631A1, "addss xmm0, dword ptr [rip + 0x11ffcf]",
     (0x683178, 0.005235987715423107),
     "uta6 562D30: its spin speed +E14 += 0.0052 a tick more while +10C0 has bit 0 or "
     "14"),
    ("objects", "lin", 0x564322, "subss xmm0, dword ptr [rip + 0x11ee4e]",
     (0x683178, 0.005235987715423107),
     "uta7 563EB0: its spin speed +E14 -= 0.0052 a tick while +10C0 has bit 0 or 14"),
    ("objects", "callscale", 0x564FFE, "call 0x1802ddf90", (0x2DDF90, "xmm3"),
     "uta8 564E60: each tick it turns toward its point by at most n x 8 degrees "
     "(2DDF90's limit, xmm3)"),
    ("objects", "count", 0x5654DD, "mov word ptr [rbx + 0xe3c], ax", None,
     "uta8 565410: +E3C += 1 a tick, its colour flashing on +E3C's parity: the store "
     "is skipped between stock ticks"),
    ("objects", "src", 0x56892C, "subss xmm0, dword ptr [rdi + 0xe10]", None,
     "utaa 568590: position.x -= +E10 a tick, a speed growing by 0.2 a tick "
     "(phase_steps.h)"),
    ("objects", "src", 0x56A9D9, "subss xmm0, dword ptr [rdi + 0xe10]", None,
     "utab 56A640: position.x -= +E10 a tick, as 56892C"),
    ("objects", "lin", 0x56D485, "subss xmm0, dword ptr [rip + 0x10c7e3]",
     (0x679C70, 0.07999999821186066),
     "utb2 56D250 state 5: position.y -= 0.08 a tick while its wait +E3C runs "
     "(lea_timers.h)"),
    ("objects", "lin", 0x56D4D0, "addss xmm0, dword ptr [rip + 0x10492c]",
     (0x671E04, 0.10000000149011612),
     "utb2 56D250 state 7: position.y += 0.1 a tick while its wait runs"),
    ("objects", "count", 0x57040A, "mov word ptr [rbx + 0x10da], ax", None,
     "570340 state 3: the wait +10DA -= 1 a tick from 90: the store is skipped between "
     "stock ticks"),
    ("objects", "notyet", 0x570411, "test cx, cx", 0x5704AC,
     "570340 state 3: `test cx, cx; jne` on the wait's old value: between stock ticks "
     "\"not yet\", so state 4 starts on a stock tick"),
    ("objects", "count", 0x570499, "mov word ptr [rbx + 0x10da], ax", None,
     "570340 state 7: the wait +10DA -= 1 a tick from 90"),
    ("objects", "notyet", 0x5704A0, "test cx, cx", 0x5704AC,
     "570340 state 7: as 570411, so state 1 starts on a stock tick"),
    ("objects", "blend", 0x57CBDA, "mulss xmm1, dword ptr [rip + 0xfd092]",
     (0x679C74, 0.4000000059604645),
     "ut2c 57CA00 case 6: material 0's +5C approaches 0.01 by 0.4 a tick"),
    ("objects", "count", 0x598C2C, "mov byte ptr [rbx + 0xe36], al", None,
     "598B10 state 5 (a part's grow-in, as utbd's): the countdown +E36 -= 1 a tick: "
     "the store is skipped between stock ticks"),
    ("objects", "notyet", 0x598C32, "test cl, cl", 0x598C9B,
     "598B10 state 5: `test cl, cl; jne` on the old value: between stock ticks \"not "
     "yet\", so state 6 starts on a stock tick"),
    ("objects", "lin", 0x5996C2, "addss xmm0, dword ptr [rip + 0xd873a]",
     (0x671E04, 0.10000000149011612),
     "et99 599590: material 1's +5C += 0.1 a tick (material 2's step is "
     "phase_steps.h's)"),
    ("objects", "lin", 0x5AB281, "addss xmm1, dword ptr [rip + 0xc6b8b]", (0x671E14, 2.0),
     "utf9 5AB220 state 2: +10A8 += 2 a tick up to 2 (then state 0)"),
    ("objects", "pre", 0x5C6BF9, "addss xmm0, dword ptr [rdi + 0x3440]", None,
     "em85 5C6450: its phase +3440 += speed x +343C a tick (xmm0 holds that step)"),
    ("objects", "lin", 0x5C6C97, "addss xmm0, dword ptr [rip + 0xb2fd5]",
     (0x679C74, 0.4000000059604645),
     "em85 5C6450: y += 0.4 a tick while it rises"),
    ("objects", "lin", 0x5C6CB9, "addss xmm0, dword ptr [rip + 0xc0e73]",
     (0x687B34, 2.4000000953674316),
     "em85 5C6450: y += 2.4 a tick more while +D40 bit 3 is set"),
    ("objects", "count", 0x5C6DC0, "mov dword ptr [rdi + 0x348c], eax", None,
     "em85 5C6450: the countdown +348C -= 1 a tick while above 0"),
    ("objects", "lin", 0x5CBC60, "movss xmm2, dword ptr [rip + 0xf0808]",
     (0x6BC470, 0.006500000134110451),
     "5CBAD0 (em85's, 9 callers): +343C steps toward 3 x +3438 by 0.0065 a tick (one "
     "path)"),
    ("objects", "lin", 0x5CBD0D, "movss xmm2, dword ptr [rip + 0xb60eb]",
     (0x681E00, 0.005499999970197678),
     "5CBAD0: the same by 0.0055 a tick (the other path)"),
    ("objects", "blend", 0x5D22A1, "mulss xmm6, dword ptr [rip + 0xa0683]",
     (0x67292C, 0.20000000298023224),
     "em86 5D2050: y approaches its height by 0.2 a tick"),
    ("objects", "lin", 0x5D373F, "movss xmm2, dword ptr [rip + 0xe8d29]",
     (0x6BC470, 0.006500000134110451),
     "em86 5D3600: +544C steps toward its target by 0.0065 a tick (one path)"),
    ("objects", "lin", 0x5D37EC, "movss xmm2, dword ptr [rip + 0xa9dac]",
     (0x67D5A0, 0.0024999999441206455),
     "em86 5D3600: the same by 0.0025 a tick (the other path)"),
    ("objects", "lin", 0x5DAB40, "movss xmm2, dword ptr [rip + 0xe1928]",
     (0x6BC470, 0.006500000134110451),
     "em87 5DA9A0: +535C steps toward its target by 0.0065 a tick"),
    ("actor", "pre", 0x5E06B8, "addss xmm0, dword ptr [rbx + 0x390c]", None,
     "em88 5DF660: +390C += +3914 a tick up to +391C (xmm0 holds +3914, loaded at "
     "5E06B0)"),
    ("actor", "count", 0x5EB465, "inc dword ptr [rbx + 0x50c0]", None,
     "em89 5EB440: +50C0 += 1 a tick while 169EC0 answers 1"),
    ("actor", "count", 0x5EB477, "dec eax",
     (0x5EB46D,0x5EB479,(0x5EB46D,0x5EB473,0x5EB475,0x5EB477),None),
     "em89 5EB440: +50C0 -= 1 a tick otherwise, down to 0"),
    ("actor", "count", 0x5EC1C0, "dec ecx",
     (0x5EC1B6,0x5EC1C2,(0x5EC1B6,0x5EC1BC,0x5EC1BE,0x5EC1C0),None),
     "em89 5EC0F0: the countdown +5080 -= 1 a tick while above 0"),
    ("actor", "count", 0x5EC209, "inc dword ptr [rbx + 0x5050]", None,
     "em89 5EC0F0: +5050 counts the ticks its target spends above 100"),
    ("actor", "src", 0x5EF876, "subss xmm0, xmm1", None,
     "em89 5EF560: +5074 -= speed x 0.025 x xmm6 a tick (xmm1 holds that step; the "
     "speed's load is not a world row here)"),
    ("actor", "pre", 0x5EF890, "addss xmm0, dword ptr [rsi + 0x5074]", None,
     "em89 5EF560: +5074 += speed x 0.025 x xmm6 a tick on the other path (xmm0 holds "
     "that step)"),
    ("actor", "lin", 0x5F2AAD, "movss xmm2, dword ptr [rip + 0xc99bb]",
     (0x6BC470, 0.006500000134110451),
     "em89 5F2A60: +5060 steps toward its target by 0.0065 a tick (one of four paths)"),
    ("actor", "lin", 0x5F2AD1, "movss xmm2, dword ptr [rip + 0xc9997]",
     (0x6BC470, 0.006500000134110451),
     "em89 5F2A60: the same, second path"),
    ("actor", "lin", 0x5F2AF5, "movss xmm2, dword ptr [rip + 0xc9973]",
     (0x6BC470, 0.006500000134110451),
     "em89 5F2A60: the same, third path"),
    ("actor", "lin", 0x5F2B19, "movss xmm2, dword ptr [rip + 0xc994f]",
     (0x6BC470, 0.006500000134110451),
     "em89 5F2A60: the same, fourth path"),
    ("objects", "count", 0x651F22, "mov byte ptr [rbx + 0x11a9], al", None,
     "ut35 651DC0: the countdown +11A9 -= 1 a tick (below 0 an effect and a reload): "
     "the store is skipped between stock ticks"),
    ("objects", "notyet", 0x651F28, "test cl, cl", 0x651F58,
     "ut35 651DC0: `test cl, cl; jns` on the old value: between stock ticks \"not yet\", "
     "so the effect comes on a stock tick"),
    ("effect", "lin", 0x3633B0, "addss xmm0, dword ptr [rip + 0x30ea50]", (0x671E08, 0.5),
     "esfd 363210 case 3: +E54 += 0.5 a tick while +E3C is under its table's limit "
     "(then +E54 x 0.98, decay_factors.h; state 3 ends when +E54 < 0, 362D10)"),
    ("effect", "count", 0x3633B8, "mov word ptr [rbx + 0xe3c], r8w", None,
     "esfd 363210 case 3: +E3C += 1 a tick up to the table's limit: the store is "
     "skipped between stock ticks"),
    # pl00 3B2CF0, her ground movement, has no rows: the run fix (FixRunSpeed,
    # kJogParams in dinput8_proxy.cpp) rewrites its constants in .data, which no
    # patched-range check sees. Rows on its acceleration (3B2FBC) and on the
    # sprint charge +1174 (3B31C4, 3B31E5, 3B3588) compensated a second time: the
    # charge, counted on stock ticks against frames the run fix already x N,
    # took 8x stock's time at 120 and she never left the jog (4685584d, 10-02).
    # survey_double_pacing's "data" check refuses a row next to such a read.
    ("menu", "count", 0x407B92, "mov dword ptr [rcx + 0x84], eax", None,
     "cCockTimer 407B00: the count-up timer +84 += 1 a tick up to 0x57E04: the store "
     "is skipped between stock ticks (the stock context's rate; its count-down twin "
     "407BB2 is the mode group's)"),
    # The slot-8 effect spawners (+1136: at 2 an effect and 0, else += 1) count
    # their store on stock ticks; their `cmp al, 2; jb` read the held value on the
    # ticks between and spawned on the first tick at 2: one every 2 stock ticks
    # instead of 3. Between stock ticks the compare now reads "below" (notyetb).
    ("actor", "notyetb", 0x2513EA, "cmp al, 2", 0x25141A,
     "em05 family 2512E0: the spawner's `cmp al, 2; jb`: between stock ticks \"below "
     "2\", so the effect comes on a stock tick, one every 3"),
    ("actor", "notyetb", 0x25B932, "cmp al, 2", 0x25B962,
     "em12 25B7A0: the spawner's test, as 2513EA"),
    ("actor", "notyetb", 0x25F423, "cmp al, 2", 0x25F462,
     "em13/em14 25F300: the spawner's test, as 2513EA"),
    ("actor", "notyetb", 0x26F0E9, "cmp al, 2", 0x26F119,
     "em27/em29 26F030: the spawner's test, as 2513EA"),
    ("actor", "notyetb", 0x274140, "cmp al, 2", 0x274170,
     "em2b 273FF0: the spawner's test, as 2513EA"),
    ("actor", "notyetb", 0x285947, "cmp al, 2", 0x285954,
     "em3d 285870: the spawner's test, as 2513EA"),
    ("actor", "notyetb", 0x288E7E, "cmp al, 2", 0x288EB0,
     "em4d/em4e/em50 288D90: the spawner's test, as 2513EA"),
    ("actor", "notyetb", 0x291497, "cmp al, 2", 0x2914A4,
     "em51 2913B0: the spawner's test, as 2513EA"),
    ("actor", "notyetb", 0x29EF16, "cmp al, 2", 0x29EF48,
     "29EF4A's spawner: its test, as 2513EA"),
    ("actor", "notyetb", 0x2CE934, "cmp al, 2", 0x2CE966,
     "2CE968's spawner: its test, as 2513EA"),
    ("actor", "notyetb", 0x2D8C0D, "cmp al, 2", 0x2D8C1A,
     "em8f 2D8C1C's spawner: its test, as 2513EA"),
    ("actor", "notyetb", 0x241264, "cmp al, 2", 0x241294,
     "em00..em03 241180: the spawner's test, as 2513EA"),
]

# Code nothing can reach, whose tail jumps a gatefn proof may pass over: each
# range is proven dead on every run (dead_code_problem): no branch, call,
# code pointer, rip lea, switch table, data word or unwind entry names an
# address in it from outside it, and it cannot be fallen into.
DEAD_CODE = {
    0x55D910: (0x55D910, 0x55D935,
               "unused leaf copy of uta2's inline slot-8 dispatch at 55D660: "
               "no execution reference and preceded by initializer RET/padding"),
    0x410B80: (0x410B80, 0x410BB6,
               "a copy of the dispatcher 410F40 inlines (switch on +52 to cSSScroll's "
               "scroll, open, close and cursor states, by tail jumps); nothing refers to it"),
}

# These retained copies have unwind descriptions but no execution entry.
# Validate their exclusion independently of the cadence-patch proof: unwind
# metadata describes an existing frame and cannot invoke an unused helper.
DORMANT_DEBRIS = (
    (0x395850, 0x396BE0),
    (0x188520, 0x1885B0),
    (0x18A170, 0x18A1E0),
    (0x1BB900, 0x1BBA70),
    (0x2013D0, 0x201430),
    (0x202690, 0x2026E0),
    (0x204BE0, 0x204C90),
    (0x207BA0, 0x207DC0),
    (0x20E5D0, 0x20E6E0),
    (0x212100, 0x212140),
    (0x21D470, 0x21D4D0),
    (0x23ABA0, 0x23AC00),
    (0x23E630, 0x23E6E0),
    (0x2EC860, 0x2EC920),
    (0x2ECE10, 0x2ECE80),
    (0x301A70, 0x301BC0),
    (0x317810, 0x317870),
    (0x33D700, 0x33D780),
    (0x33DBA0, 0x33DBE0),
    (0x35DAF0, 0x35DB40),
    (0x36EE50, 0x36EEF0),
    (0x370D50, 0x370E40),
    (0x3CF340, 0x3CF440),
    (0x3F1280, 0x3F12C0),
    (0x3FCBF0, 0x3FCC10),
    (0x40BFB0, 0x40BFF0),
    (0x40FE90, 0x40FEF0),
    (0x468750, 0x468AA0),
    (0x469490, 0x4697B0),
    (0x46D680, 0x46DA70),
    (0x46DA70, 0x46DCF0),
    (0x46DCF0, 0x46E890),
    (0x470550, 0x470AE0),
    (0x471660, 0x471C00),
    (0x471C00, 0x472140),
    (0x472330, 0x472CC0),
    (0x478EF0, 0x4797A0),
    (0x47BAE0, 0x47C9D0),
    (0x47EC10, 0x47F5F0),
    (0x498E30, 0x498E70),
    (0x4A1DA0, 0x4A1EB0),
    (0x4AC140, 0x4AC1A0),
    (0x4FECB0, 0x4FECF0),
    (0x510220, 0x510290),
    (0x55C030, 0x55C1F0),
    (0x56BC90, 0x56BE50),
    (0x56E110, 0x56E2D0),
    (0x5A2C60, 0x5A2CA0),
    (0x5A3690, 0x5A36F0),
    (0x5AA9C0, 0x5AAA10),
    (0x5D4C50, 0x5D4CC0),
    (0x5DE130, 0x5DE1A0),
    # the eighteen-slot copies of the six-slot state loop (382340, the live
    # one; 395850's six-slot copy above): 393F50 and 3809D0 run 393FB0 and
    # 380A30 over slots 17..0, and their helpers after them. Only their own
    # switch tables (dormant_internal_tables) and the data words below name
    # addresses in them.
    (0x393F50, 0x395850),
    (0x3809D0, 0x3822D0),
    # helpers whose only callers are dormant: 3AECC0 (called from 3AE320 and
    # 3AE880, which nothing enters) and three called from 478EF0-4797A0 above
    (0x3AE320, 0x3AE480),
    (0x3AE880, 0x3AEAD0),
    (0x3AECC0, 0x3AED60),
    (0x4752F0, 0x4753C0),
    (0x481810, 0x4818E0),
    (0x4829A0, 0x482B40),
)

# Unaligned data words that read as an address in a dormant range only because
# they straddle two fields of other data. Each is pinned to the 16 bytes around
# it (from word - 8), and must be the only data word naming its address
# (dormant_data_coincidences).
DORMANT_DATA_COINCIDENCES = (
    (0x7A2041, 0x394002, "e43480010000008802403900000000f0",
     "the id 0x39400288's upper bytes and a zero in a table of {id, pointer} pairs "
     "(ids ..287, ..288, ..289 beside pointers 18034E4D0, 18034E5F0)"),
    (0x677D9D, 0x39434D, "0000004546465f484d43390000000000",
     "'MC9' and the terminator of the ASCII name EFF_HMC9 at 677D98, one of a run "
     "of 16-byte name slots (EFF_HMC8, EFF_HMC9, EFF_HMCA)"),
    (0x6DBA0E, 0x381308, "08073c00080b3a000813380008233600",
     "halves of two dword records {u16 value, u8 8, u8 code} of a decode table "
     "(3C, 3A, 38, 36 descending)"),
    (0x79BAC2, 0x38200D, "0b00030048003b000d20380048003f00",
     "the halfwords 200D and 0038 of a u16 table (0048 003B 200D 0038 0048 003F)"),
)


def dormant_switch_destinations(dec, starts, sources, actual_refs):
    """A bounded switch is internal control flow, not an external code pointer.
    The six-slot wrapper and its retained state loop have no execution entry.
    Its 14 case RVAs live in .text after an unconditional jump and a padding
    NOP. Prove the load's exact bound/base/dispatch and all destinations before
    removing ONLY these internal switch edges from the dormant-entry audit.
    Actual data pointers and LEAs remain in that audit independently.
    """
    expected = ((0x395AB9, "cmp", "eax, 0xd"),
                (0x395ABC, "ja", "0x395e14"),
                (0x395AC2, "lea", "rdx, [rip - 0x395ac9]"),
                (0x395ACF, "mov", "ecx, dword ptr [rdx + rax*4 + 0x396b9c]"),
                (0x395AD6, "add", "rcx, rdx"),
                (0x395AD9, "jmp", "rcx"),
                (0x396B96, "jmp", "0x395f79"),
                (0x396B9B, "nop", ""))
    for at, mnemonic, operands in expected:
        i = dec.run(at, at)[0]
        if (i.mnemonic, i.op_str) != (mnemonic, operands):
            raise RuntimeError("dormant 395850 switch changed at %X" % at)
    lo, hi = 0x396B9C, 0x396B9C + 14 * 4
    if any(lo <= a < hi for a in actual_refs) or any(
            lo <= target < hi and any(not 0x395850 <= src < 0x396BE0
                                     for src, _size, _mn in incoming)
            for target, incoming in sources.items()):
        raise RuntimeError("dormant 395850 switch table gained an execution entry")
    destinations = {struct.unpack_from("<I", dec.img, at)[0] for at in range(lo, hi, 4)}
    if any(not 0x395ADB <= target < lo or not starts[target] for target in destinations):
        raise RuntimeError("dormant 395850 switch gained an external/invalid destination")
    return destinations


def dormant_internal_tables(dec, starts, tables, text_lo, text_hi):
    """The destinations of switch tables that are a dormant range's own control
    flow. A table counts when it lies in a DORMANT_DEBRIS range and its RVA
    occurs nowhere in the image (as a dword, or as a qword address) but as the
    displacement of loads inside that range; then its entries (as
    tr.global_pass reads them) that lie in the range are internal. A
    destination some other table names stays a reference."""
    img = dec.img
    inner, outer = set(), set()
    for tbl in sorted(tables):
        dests = []
        for i in range(4096):
            t = struct.unpack_from("<I", img, tbl + i * 4)[0]
            if not text_lo <= t < text_hi:
                break
            dests.append(t)
        rng = next(((a, b) for a, b in DORMANT_DEBRIS if a <= tbl < b), None)
        own = rng is not None and not img.count(struct.pack("<Q", tr.BASE + tbl))
        if own:
            a, b = rng
            pat = struct.pack("<I", tbl)
            at = img.find(pat)
            while own and at != -1:
                p = next((p for p in range(at - 1, max(a, at - 15) - 1, -1) if starts[p]), None)
                i = dec.run(p, p)[0] if p is not None else None
                own = a <= at < b and i is not None and p + i.size >= at + 4 and any(
                    op.type == X.X86_OP_MEM and op.mem.disp == tbl for op in i.operands)
                at = img.find(pat, at + 1)
        for t in dests:
            (inner if own and rng[0] <= t < rng[1] else outer).add(t)
    return inner - outer


def dormant_data_coincidences(img, secs):
    """The addresses DORMANT_DATA_COINCIDENCES reads: each listed word still
    holds its pinned bytes, and no other dword (at any alignment) or qword
    address in .rdata or .data names the same address."""
    listed = collections.defaultdict(set)
    for off, value, pinned, _why in DORMANT_DATA_COINCIDENCES:
        if bytes(img[off - 8:off + 8]).hex() != pinned or \
                struct.unpack_from("<I", img, off)[0] != value:
            raise RuntimeError("dormant data coincidence at %X changed" % off)
        listed[value].add(off)
    for value, offs in listed.items():
        for name in (".rdata", ".data"):
            a, b = secs[name]
            for pat in (struct.pack("<I", value), struct.pack("<Q", tr.BASE + value)):
                at = img.find(pat, a, b)
                while at != -1:
                    if len(pat) == 8 or at not in offs:
                        raise RuntimeError("%X is also named by the data word at %X" % (value, at))
                    at = img.find(pat, at + 1, b)
    return set(listed)


def dead_code_problem(dec, starts, sources, indirect, lo, hi, dead=()):
    """None if [lo, hi) cannot be reached from outside itself and the ranges
    `dead` (each proven the same way, so their union has no entry)"""
    for t in range(lo, hi):
        if t in indirect:
            return "%X is named by a code pointer, switch table, lea or unwind entry" % t
        for src, _s, mn in sources.get(t, []):
            if not lo <= src < hi and not any(a <= src < b for a, b in dead):
                return "%X is entered by the %s at %X" % (t, mn, src)
    phys = gmt.physical_predecessor(dec, starts, lo)
    if phys is not None and phys.mnemonic not in tr.UNCOND and phys.mnemonic != "int3":
        return "%X is entered by falling through %X" % (lo, phys.address)
    return None


def exported_void(rva):
    """True if main.dll's only data reference to rva is its export table entry,
    under a decorated name that returns void (`?Name@Class@@QEAAX...` or
    `?Name@@YAX...`): whatever calls it through the export cannot read rax."""
    import re
    import pefile
    from gamedir import GAME
    pe = pefile.PE(os.path.join(GAME, "main.dll"))
    ex = pe.DIRECTORY_ENTRY_EXPORT
    names = [e.name.decode() for e in ex.symbols if e.address == rva and e.name]
    if not names or not all(re.search(r"@@(?:[A-Z]EAAX|YAX)", n) for n in names):
        return False
    eat = (ex.struct.AddressOfFunctions, ex.struct.AddressOfFunctions + 4 * ex.struct.NumberOfFunctions)
    img = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        if s.Name.rstrip(b"\0") not in (b".rdata", b".data"):
            continue
        a, b = s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize
        for off in range(a, b - 4):
            if struct.unpack_from("<I", img, off)[0] == rva and not eat[0] <= off < eat[1]:
                return False
            if off + 8 <= b and struct.unpack_from("<Q", img, off)[0] == base + rva:
                return False
    return True


def gatefn_entry(dec, starts, sources, rva):
    """gmt.function_entry, a tail jump's target allowed as well as a call's"""
    # These UI slot-3 callbacks have no direct call sites. Their outputs are
    # state mutations; the dispatchers do not use a return value. Nor have the
    # map scripts' updates (gatefn_callers proves their one `call rcx`).
    if rva not in (0x3FC430, 0x406BC0) and rva not in MAP_SCRIPT_UPDATES and \
            not any(mn in ("call", "jmp") for _a, _s, mn in sources.get(rva, [])):
        return "not a direct call or tail jump target"
    phys = gmt.physical_predecessor(dec, starts, rva)
    if phys is not None and phys.mnemonic not in tr.UNCOND | tr.PADDING:
        return "falls through from %X %s" % (phys.address, phys.mnemonic)
    return None


def unwind_function_roots(img, secs):
    """Resolve split UNW_FLAG_CHAININFO ranges to their owning entry.

    A chained range resumes its parent's frame; it is not a new function
    whose callers could consume a different return value.
    """
    roots = {}
    lo, hi = secs[".pdata"]
    for off in range(lo, hi - 11, 12):
        begin, end, unwind = struct.unpack_from("<III", img, off)
        if not begin and not end:
            break
        root, seen = begin, set()
        while (img[unwind] >> 3) & 4:
            if unwind in seen:
                raise RuntimeError("cyclic unwind chain at %X" % begin)
            seen.add(unwind)
            codes = img[unwind + 2]
            parent = unwind + 4 + 2 * (codes + (codes & 1))
            root, _end, unwind = struct.unpack_from("<III", img, parent)
        roots[begin] = root
    return roots


def closed_window_problem(run, sources, indirect, begins, protected):
    """A manifest's complete forward branch region with no interior entry.

    Every interior branch target must come solely from this region. Each
    instruction still passes the normal relocation checks on its own; only
    the internal forward branches and code following an alternate-path jmp
    are handled here. Calls, backward branches and indirect entries refuse.
    """
    lo, hi = run[0].address, run[-1].address + run[-1].size
    entries = {i.address for i in run}
    if hi - lo < 5 or any(x.address + x.size != y.address for x, y in zip(run, run[1:])):
        return "block is not a contiguous detour window"
    for ins in run:
        if ins.address != lo:
            if ins.address in indirect or ins.address in begins:
                return "indirect or unwind entry inside the block"
            if any(not lo <= a < hi for a, _s, _mn in sources.get(ins.address, [])):
                return "external branch enters the block"
        why = tr.window_problem([ins], set(), protected)
        if why:
            return why
        if ins.mnemonic in tr.UNCOND and ins.mnemonic != "jmp":
            return "return or indirect transfer inside the block"
        if tr.is_rel_branch(ins):
            target = ins.operands[0].imm
            if lo <= target < hi and (target not in entries or target <= ins.address):
                return "internal branch is not forward to an instruction"
        elif ins.mnemonic == "jmp":
            return "indirect jump inside the block"
    return None


def discard_proven_switch_data(dec, sources, targets, indirect):
    """Remove branch decodings inside the bounded 3677E0 switch's RVA table.

    CMP eax,20 bounds its 21 table loads. Every destination precedes the
    table, which follows RET; no code entry names any byte of the table.
    Its little-endian RVAs otherwise decode as fictitious JS instructions.
    Keep destinations that also have an actual branch or address reference.
    """
    expected = ((0x367815, "cmp", "eax, 0x14"),
                (0x367818, "ja", "0x367876"),
                (0x367823, "mov", "ecx, dword ptr [r8 + rax*4 + 0x367878]"),
                (0x36782B, "add", "rcx, r8"),
                (0x36782E, "jmp", "rcx"),
                (0x367876, "ret", ""))
    for at, mn, op in expected:
        i = dec.run(at, at)[0]
        if (i.mnemonic, i.op_str) != (mn, op):
            raise RuntimeError("3677E0 bounded switch changed at %X" % at)
    lo, hi = 0x367878, 0x367878 + 21 * 4
    for at in range(lo, hi, 4):
        value = struct.unpack_from("<I", dec.img, at)[0]
        if not 0x367830 <= value <= 0x367876:
            raise RuntimeError("3677E0 switch destination outside its cases")
    if any(lo <= at < hi for at in indirect) or any(
            lo <= at < hi and any(not lo <= a < hi for a, _s, _m in refs)
            for at, refs in sources.items()):
        raise RuntimeError("3677E0 switch data gained a code entry")
    dropped = set()
    clean = {}
    for at, refs in sources.items():
        keep = [r for r in refs if not lo <= r[0] < hi]
        if len(keep) != len(refs):
            dropped.add(at)
        if keep:
            clean[at] = keep
    return clean, targets - (dropped - set(clean) - indirect)


# The map scripts: 7AD9B0 holds 0x30-byte records {u16 map, s16 index, ..., +08
# init, +10, +18 update, +20, +28}, ended by map FFFF. 3F4590 stores the current
# map's record at [manager + 128], and 3F3A10 (once a tick, from 4BA500) calls
# its +18 update by `call rcx` at 3F3B83, reading nothing of rax after. The
# records' other readers (3F3070's callers) read the map, the index or +20.
MAP_SCRIPT_TABLE = (0x7AD9B0, 0x7AEA00)
MAP_SCRIPT_DISPATCH = 0x3F3B83
MAP_SCRIPT_UPDATES = {0x5FB060: 0x312}


def map_script_update_problem(dec, sources, fn):
    """None if fn is only a map script's update, called only at 3F3B83"""
    expected = ((0x3F3B73, "mov", "rax, qword ptr [rbx + 0x128]"),
                (0x3F3B7A, "mov", "rcx, qword ptr [rax + 0x18]"),
                (0x3F3B7E, "test", "rcx, rcx"),
                (0x3F3B81, "je", "0x3f3b85"),
                (0x3F3B83, "call", "rcx"),
                (0x3F3B85, "lea", "rcx, [rbx + 0x20]"),
                (0x3F3B89, "call", "0x456530"))
    for at, mn, op in expected:
        i = dec.run(at, at)[0]
        if (i.mnemonic, i.op_str) != (mn, op):
            return "map-script dispatch changed at %X" % at
    if sources.get(fn):
        return "map script %X gained a direct caller" % fn
    img, lo, hi = dec.img, MAP_SCRIPT_TABLE[0], MAP_SCRIPT_TABLE[1]
    if struct.unpack_from("<H", img, hi)[0] != 0xFFFF:
        return "map-script table no longer ends at %X" % hi
    slots = []
    pat = struct.pack("<Q", tr.BASE + fn)
    at = img.find(pat)
    while at != -1:
        slots.append(at)
        at = img.find(pat, at + 1)
    want = [r + 0x18 for r in range(lo, hi, 0x30)
            if struct.unpack_from("<H", img, r)[0] == MAP_SCRIPT_UPDATES[fn]]
    if slots != want or len(want) != 1:
        return "%X is named at %s, not only by map %X's update field" % (
            fn, ", ".join("%X" % s for s in slots), MAP_SCRIPT_UPDATES[fn])
    if struct.pack("<I", fn) in bytes(img[lo:hi]):
        return "map-script table names %X as a dword too" % fn
    return None


def gatefn_callers(dec, starts, sources, indirect, fn, begins=None,
                   address_taken=None, unwind_roots=None, seen=None):
    """gmt.rax_unused_after_calls, passing over tail jumps from DEAD_CODE. A
    tail jump from a function F (cPad::Update's to cPad::Actuater) hands rax
    to F's callers: every call of F must leave it unread in turn, and F must
    have no tail jump or address taken of its own."""
    import bisect
    if fn == 0x3FC430:
        if fn not in indirect or sources.get(fn):
            return None, "cCockEventEdge vtable slot changed or gained a direct caller"
        return [0x6AFE80], None
    if fn == 0x406BC0:
        if fn not in indirect or sources.get(fn):
            return None, "cCockStamp vtable slot changed or gained a direct caller"
        return [0x6AFCD0], None
    if fn in MAP_SCRIPT_UPDATES:
        why = map_script_update_problem(dec, sources, fn)
        return (None, why) if why else ([MAP_SCRIPT_DISPATCH], None)
    # These slot-8 update wrappers tail-jump to their particle state loops.
    # Each returns without setting a result on its other exit path, so the
    # slot has no meaningful RAX result for its indirect callers.
    # The slot-18 callbacks below update model deformation (and two linked
    # head controllers), then tail
    # call the shared deformation wrapper. Their dispatchers use mutations,
    # not a return value. Keep following ordinary wrappers recursively.
    void_update_tails = {0x55BE90, 0x56BAF0, 0x56DF20,
                         0x31DE10, 0x333BA0, 0x333DD0, 0x336A20, 0x3399F0,
                         0x3A5E50}  # wp44 slot-8 Update, same void deformation tail
    seen = set() if seen is None else set(seen)
    if fn in seen:
        return None, "cyclic tail-call chain at %X" % fn
    seen.add(fn)
    live = {t: [x for x in v if not any(lo <= x[0] < hi for lo, hi, _w in DEAD_CODE.values())]
            for t, v in sources.items() if t == fn}
    for lo, hi, _why in DEAD_CODE.values():
        if any(lo <= x[0] < hi for x in sources.get(fn, [])):
            why = dead_code_problem(dec, starts, sources, indirect, lo, hi)
            if why:
                return None, "dead code %X-%X: %s" % (lo, hi, why)
    tails = [x for x in live.get(fn, []) if x[2] == "jmp"]
    if tails and begins:
        live[fn] = [x for x in live[fn] if x[2] != "jmp"]
        via = set()
        for a, _s, _mn in tails:
            f = begins[bisect.bisect_right(begins, a) - 1]
            f = (unwind_roots or {}).get(f, f)
            if f in void_update_tails:
                via.add(f)
                continue
            if f in (indirect if address_taken is None else address_taken) and \
                    f not in void_update_tails and not exported_void(f):
                return None, "%X (tail-jumping to it at %X) has its address taken" % (f, a)
            got, why = gatefn_callers(dec, starts, sources, indirect, f,
                                     begins, address_taken, unwind_roots, seen)
            if why:
                return None, "via %X's tail jump at %X: %s" % (f, a, why)
            via.add(f)
        if not live[fn]:
            return sorted(via), None
    return gmt.rax_unused_after_calls(dec, live, fn)


# What the in-game log counts per tick for each group (role 0; role 1 is the
# human group's second figure): scrolling materials, swinging bones, talking
# heads and mood spawners, live particles, live emitters, turning actors,
# swaying scenery, items, event camera paths (and HUD timers), repeat checks.
HEADLINE = {0x35D6C9: 0, 0x35D77C: 0, 0x35D862: 0, 0x35D886: 0,
            0x20E230: 0, 0x20E2A6: 0,
            0x1BA9D1: 0, 0x1BAF31: 0,
            0x3045E6: 0, 0x30EB40: 1,
            0x1928F6: 0,
            0x195D6B: 0, 0x195673: 0,
            0x20786F: 0, 0x3404CD: 0, 0x36D63C: 0, 0x370B7C: 0,
            0x497C95: 0,
            0x476A12: 0, 0x407BB2: 1,
            0x4111D0: 0, 0x4113A0: 0, 0x410540: 0, 0x411570: 0,
            0x13F675: 0, 0x13F6F0: 0, 0x184BE9: 0, 0x184C1E: 0,
            0x1825A0: 0, 0x3E2ACE: 1}

VOLATILE_TEMPS = gmt.VOLATILE_TEMPS
FLAGS6 = frozenset(gis.FLAGS)


def group_mask(g):
    return GROUP_STRIDE * GROUPS.index(g)


def group_scale(g):
    return GROUP_STRIDE * GROUPS.index(g) + 4


def group_mask2(g):
    """the mask shifted left once: count2's gate on the counter's bits 1 and up"""
    return GROUP_STRIDE * GROUPS.index(g) + 1


def group_smode(g):
    """the stock context's mode byte, for smode"""
    return GROUP_STRIDE * GROUPS.index(g) + 2


def group_intn(g):
    """the group's N as a dword, for imuln"""
    return INTN_OFFSET + 4 * GROUPS.index(g)


def rex_for(reg_idx, rm_idx=0):
    rex = 0x40 | (0x04 if reg_idx >= 8 else 0) | (0x01 if rm_idx >= 8 else 0)
    return bytes([rex]) if rex != 0x40 else b""


def emit_mulss_scale(pool, reg, group):
    r = gmt.xmm_index(reg)
    pool.pool_rel32(b"\xF3" + rex_for(r) + bytes([0x0F, 0x59, ((r & 7) << 3) | 5]),
                    group_scale(group))


def emit_divss_scale(pool, reg, group):
    """divss xmmD, [s]: x N, exact (s = 1/N is a power of two)"""
    r = gmt.xmm_index(reg)
    pool.pool_rel32(b"\xF3" + rex_for(r) + bytes([0x0F, 0x5E, ((r & 7) << 3) | 5]),
                    group_scale(group))


def emit_probe(pool, probe):
    """pushfq; inc dword [probe]; popfq: a pass count that leaves flags alone."""
    pool.emit(b"\x9C")
    pool.pool_rel32(b"\xFF\x05", PROBE_OFFSET + 4 * probe)
    pool.emit(b"\x9D")


def emit_src(pool, ins, temp, group):
    ops = ins.operands
    dst = ins.reg_name(ops[0].reg)
    if ins.mnemonic in ("addsd", "subsd"):
        # The compiler promotes some float phases to double. Convert the
        # per-group float scale exactly to double,
        # multiply the original qword literal, and leave the phase untouched.
        t = gmt.xmm_index(temp)
        pool.pool_rel32(b"\xF3" + rex_for(t) +
                          bytes([0x0F, 0x10, ((t & 7) << 3) | 5]), group_scale(group))
        pool.emit(gmt.enc_rr(0x5A, temp, temp, prefix=b"\xF3"))  # cvtss2sd
        if ops[1].type == X.X86_OP_REG:
            pool.emit(gmt.enc_rr(0x59, temp, ins.reg_name(ops[1].reg), prefix=b"\xF2"))
        else:
            const_rva = ins.address + ins.size + ops[1].mem.disp
            pool.game_rel32(b"\xF2" + rex_for(t) +
                            bytes([0x0F, 0x59, ((t & 7) << 3) | 5]), const_rva)  # mulsd
        pool.emit(gmt.enc_rr(0x58 if ins.mnemonic == "addsd" else 0x5C,
                             dst, temp, prefix=b"\xF2"))
        return
    if ops[1].type == X.X86_OP_MEM:
        if ops[1].mem.base == X.X86_REG_RIP:
            t = gmt.xmm_index(temp)
            const_rva = ins.address + ins.size + ops[1].mem.disp
            pool.game_rel32(b"\xF3" + rex_for(t) +
                            bytes([0x0F, 0x10, ((t & 7) << 3) | 5]), const_rva)
        else:
            load, why = gmt.reencode_load(ins, temp)
            if why:
                raise RuntimeError("%X: %s" % (ins.address, why))
            pool.emit(load)
    else:
        pool.emit(gmt.enc_rr(0x28, temp, ins.reg_name(ops[1].reg), prefix=b""))   # movaps
    emit_mulss_scale(pool, temp, group)
    pool.emit(gmt.enc_rr(gmt.OPCODE[ins.mnemonic], dst, temp))


def emit_srcx(pool, ins, group):
    """divss xmmD, [s]; the instruction; mulss xmmD, [s]"""
    d = gmt.xmm_index(ins.reg_name(ins.operands[0].reg))
    pool.pool_rel32(b"\xF3" + rex_for(d) + bytes([0x0F, 0x5E, ((d & 7) << 3) | 5]),
                    group_scale(group))
    tr.emit_relocated(pool, ins, None)
    emit_mulss_scale(pool, ins.reg_name(ins.operands[0].reg), group)


def emit_root(pool, ins, group):
    """After the instruction: its xmmD = xmmD ** (1/N) for N = 1, 2, 4, when xmmD > 0."""
    tr.emit_relocated(pool, ins, None)
    emit_root_chain(pool, gmt.xmm_index(ins.reg_name(ins.operands[0].reg)), group)


def emit_blendr(pool, ins, temp, group):
    """After the instruction, at N > 1 and 0 < xmmD < 1: T = 1 - xmmD, T =
    T^(1/N) by the root chain, xmmD's low lane = 1 - T (its other lanes kept):
    blend_ref's float steps. Clobbers T and the flags."""
    tr.emit_relocated(pool, ins, None)
    d = gmt.xmm_index(ins.reg_name(ins.operands[0].reg))
    t = gmt.xmm_index(temp)

    def jcc8(opcode):
        pool.emit(bytes([opcode, 0]))
        return len(pool.code)

    exits = []
    pool.pool_rel32(b"\xF6\x05", group_mask(group), trailing=b"\xFF")      # test [mask], 0xFF
    exits.append(jcc8(0x74))                                                 # jz done: N = 1
    pool.pool_rel32(rex_for(d) + bytes([0x0F, 0x2F, ((d & 7) << 3) | 5]), ZERO_OFFSET)
    exits.append(jcc8(0x76))                                   # comiss xmmD, [0.0]; jbe done
    pool.pool_rel32(rex_for(d) + bytes([0x0F, 0x2F, ((d & 7) << 3) | 5]), ONE_OFFSET)
    exits.append(jcc8(0x73))                                   # comiss xmmD, [1.0]; jae done
    pool.pool_rel32(b"\xF3" + rex_for(t) + bytes([0x0F, 0x10, ((t & 7) << 3) | 5]),
                    ONE_OFFSET)                                              # movss xmmT, [1.0]
    pool.emit(gmt.enc_rr(0x5C, temp, "xmm%d" % d))                           # subss xmmT, xmmD
    emit_root_chain(pool, t, group)
    pool.emit(gmt.enc_rr(0x5C, "xmm%d" % d, "xmm%d" % d))                    # subss xmmD, xmmD
    pool.pool_rel32(b"\xF3" + rex_for(d) + bytes([0x0F, 0x58, ((d & 7) << 3) | 5]),
                    ONE_OFFSET)                                              # addss xmmD, [1.0]
    pool.emit(gmt.enc_rr(0x5C, "xmm%d" % d, temp))                           # subss xmmD, xmmT
    for at in exits:
        pool.code[at - 1] = len(pool.code) - at


def emit_srcblend(pool, ins, temp, group):
    """T = the source's k; at N > 1 and 0 < k < 1, T = -T + 1 (1 - k, rounded
    alike), the root chain, T = -T + 1 again: blend_ref's float steps; then
    `mulss xmmD, T`. The -1.0 sits in the stub's own bytes. Clobbers T and the
    flags; the source is only read."""
    ops = ins.operands
    dst = ins.reg_name(ops[0].reg)
    t = gmt.xmm_index(temp)

    def jcc8(opcode):
        # The division path includes two reciprocals, so use rel32 guards.
        pool.emit(bytes([0x0F, 0x80 | (opcode & 15)]) + b"\0" * 4)
        return len(pool.code)

    pool.emit(b"\xEB\x04")                                      # jmp over the constant
    neg = pool.here()
    pool.emit(struct.pack("<f", -1.0))
    if ops[1].type == X.X86_OP_MEM:
        if ops[1].mem.base == X.X86_REG_RIP:
            const_rva = ins.address + ins.size + ops[1].mem.disp
            pool.game_rel32(b"\xF3" + rex_for(t) +
                            bytes([0x0F, 0x10, ((t & 7) << 3) | 5]), const_rva)
        else:
            load, why = gmt.reencode_load(ins, temp)
            if why:
                raise RuntimeError("%X: %s" % (ins.address, why))
            pool.emit(load)                                      # movss xmmT, m32
    elif ins.reg_name(ops[1].reg) != temp:
        pool.emit(gmt.enc_rr(0x28, temp, ins.reg_name(ops[1].reg), prefix=b""))  # movaps
    exits = []
    pool.pool_rel32(b"\xF6\x05", group_mask(group), trailing=b"\xFF")      # test [mask], 0xFF
    exits.append(jcc8(0x74))                                                 # jz done: N = 1
    divide = ins.mnemonic == "divss"

    def reciprocal():
        # Reserve stack space: Windows has no red zone. The original source
        # is loaded before changing rsp, so rsp-relative operands also work.
        pool.emit(b"\x48\x83\xEC\x10")
        pool.emit(b"\xF3" + rex_for(t) + bytes([0x0F, 0x11, ((t & 7) << 3) | 4, 0x24]))
        pool.pool_rel32(b"\xF3" + rex_for(t) + bytes([0x0F, 0x10, ((t & 7) << 3) | 5]), ONE_OFFSET)
        pool.emit(b"\xF3" + rex_for(t) + bytes([0x0F, 0x5E, ((t & 7) << 3) | 4, 0x24]))
        pool.emit(b"\x48\x83\xC4\x10")

    if divide:
        pool.pool_rel32(rex_for(t) + bytes([0x0F, 0x2F, ((t & 7) << 3) | 5]), ONE_OFFSET)
        exits.append(jcc8(0x76))                               # d <= 1 or NaN: unchanged
        reciprocal()                                          # k = 1/d
    else:
        pool.pool_rel32(rex_for(t) + bytes([0x0F, 0x2F, ((t & 7) << 3) | 5]), ZERO_OFFSET)
        exits.append(jcc8(0x76))                               # k <= 0 or NaN: unchanged
        pool.pool_rel32(rex_for(t) + bytes([0x0F, 0x2F, ((t & 7) << 3) | 5]), ONE_OFFSET)
        exits.append(jcc8(0x73))                               # k >= 1: unchanged

    def one_minus():
        pool.pool_rel32(b"\xF3" + rex_for(t) + bytes([0x0F, 0x59, ((t & 7) << 3) | 5]), neg)
        pool.pool_rel32(b"\xF3" + rex_for(t) + bytes([0x0F, 0x58, ((t & 7) << 3) | 5]),
                        ONE_OFFSET)                              # mulss T, [-1]; addss T, [1]
    one_minus()
    emit_root_chain(pool, t, group)
    one_minus()
    if divide:
        reciprocal()                                          # d' = 1/rooted k
    for at in exits:
        struct.pack_into("<i", pool.code, at - 4, len(pool.code) - at)
    pool.emit(gmt.enc_rr(0x5E if divide else 0x59, dst, temp))


def emit_srcroot(pool, ins, temp, group):
    """Multiply by a private copy of a per-tick factor raised to 1/N."""
    ops = ins.operands
    dst = ins.reg_name(ops[0].reg)
    if ops[1].type == X.X86_OP_MEM:
        if ops[1].mem.base == X.X86_REG_RIP:
            t = gmt.xmm_index(temp)
            const_rva = ins.address + ins.size + ops[1].mem.disp
            pool.game_rel32(b"\xF3" + rex_for(t) +
                            bytes([0x0F, 0x10, ((t & 7) << 3) | 5]), const_rva)
        else:
            load, why = gmt.reencode_load(ins, temp)
            if why:
                raise RuntimeError("%X: %s" % (ins.address, why))
            pool.emit(load)
    else:
        pool.emit(gmt.enc_rr(0x28, temp, ins.reg_name(ops[1].reg), prefix=b""))
    emit_root_chain(pool, gmt.xmm_index(temp), group)
    pool.emit(gmt.enc_rr(0x59, dst, temp))


def emit_phase_keep(pool, ins, group, last, unit):
    """After the instruction: on the first (or last) tick of each stock period
    keep its xmmD; on the others make it 0 (or 1.0 with unit). Flags and rax
    are saved around the test."""
    tr.emit_relocated(pool, ins, None)
    d = gmt.xmm_index(ins.reg_name(ins.operands[0].reg))
    pool.emit(b"\x9C\x50")                                  # pushfq; push rax
    pool.game_rel32(b"\x8B\x05", tr.FRAME_COUNTER)          # mov eax, [fc]
    if last:
        pool.emit(b"\xFF\xC0")                              # inc eax
    pool.pool_rel32(b"\x84\x05", group_mask(group))         # test [mask], al
    pool.emit(b"\x58\x74\x00")                              # pop rax; jz keep
    at = len(pool.code)
    if unit:                                                # movss xmmD, [1.0]
        pool.pool_rel32(b"\xF3" + rex_for(d) + bytes([0x0F, 0x10, ((d & 7) << 3) | 5]),
                        ONE_OFFSET)
    else:                                                   # xorps xmmD, xmmD
        pool.emit(rex_for(d, d) + bytes([0x0F, 0x57, 0xC0 | ((d & 7) << 3) | (d & 7)]))
    pool.code[at - 1] = len(pool.code) - at
    pool.emit(b"\x9D")                                      # popfq


def emit_count_gate(pool, step, skip_bytes, flags, counter, group, last=False, mask=None,
                    emit_step=None, flag_bytes=None):
    """gen_integer_skips.emit_gate, reading this group's mask and counters.
    With last, the step runs on the last tick of each stock period: the tick
    is identified by fc + 1 throughout. mask names another mask byte (count2),
    emit_step writes the step itself (smode), and flag_bytes replaces the
    countdown's flag synthesis on a skipped tick (notyet)."""
    slot = COUNTER_OFFSET + SLOT * counter
    mask = group_mask(group) if mask is None else mask

    def jcc8(opcode):
        pool.emit(bytes([opcode, 0]))
        return len(pool.code)

    def land(at):
        pool.code[at - 1] = len(pool.code) - at

    pool.emit(b"\x9C\x50")                                  # pushfq; push rax
    pool.pool_rel32(b"\xFF\x05", slot + gis.PASSES)
    pool.game_rel32(b"\x8B\x05", tr.FRAME_COUNTER)          # mov eax, [fc]
    if last:
        pool.emit(b"\xFF\xC0")                              # inc eax
    pool.pool_rel32(b"\x3B\x05", slot + gis.LAST_TICK)
    same = jcc8(0x74)
    pool.pool_rel32(b"\x89\x05", slot + gis.LAST_TICK)
    pool.pool_rel32(b"\xFF\x05", slot + gis.TICKS)
    pool.pool_rel32(b"\x84\x05", mask)
    skipped = jcc8(0x75)
    pool.pool_rel32(b"\xFF\x05", slot + gis.COUNTED)
    land(same)
    land(skipped)
    pool.pool_rel32(b"\x84\x05", mask)                      # gate: test [mask], al
    pool.emit(b"\x58\x0F\x85")                              # pop rax; jnz skip
    branch = len(pool.code)
    pool.emit(b"\0" * 4)
    pool.emit(b"\x9D")
    if emit_step:
        emit_step(pool)
    else:
        tr.emit_relocated(pool, step, None)
    pool.emit(b"\xE9")
    join = len(pool.code)
    pool.emit(b"\0" * 4)
    struct.pack_into("<i", pool.code, branch, len(pool.code) - branch - 4)
    pool.emit(b"\x9D" + skip_bytes)
    if flag_bytes:
        pool.emit(flag_bytes)
    elif flags:
        pool.emit(b"\x9C\x81\x24\x24\x3F\xFF\xFF\xFF\x9D")
    struct.pack_into("<i", pool.code, join, len(pool.code) - join - 4)


def emit_smode_step(pool, ins, group):
    """`sub r8, [mode]` at N > 1 subtracts the stock context's mode instead:
    cmp byte [mask], 0; je orig; sub r8, [smode]; jmp done; orig: the
    original, relocated; done. The cmp's flags are dead: sub writes all six."""
    pool.pool_rel32(b"\x80\x3D", group_mask(group), trailing=b"\x00")   # cmp byte [mask], 0
    pool.emit(b"\x74\x00")                                              # je orig
    je = len(pool.code)
    code = bytes(ins.bytes)
    prefix = code[:ins.disp_offset]                     # [rex] 2A modrm(rip)
    pool.pool_rel32(prefix, group_smode(group))         # sub r8, byte [rip + smode]
    pool.emit(b"\xEB\x00")                                              # jmp done
    jmp = len(pool.code)
    pool.code[je - 1] = len(pool.code) - je
    tr.emit_relocated(pool, ins, None)
    pool.code[jmp - 1] = len(pool.code) - jmp


def emit_imuln(pool, ins, group):
    """the relocated div, then imul eax, dword [N]"""
    tr.emit_relocated(pool, ins, None)
    pool.pool_rel32(b"\x0F\xAF\x05", group_intn(group))


R32 = {"eax": 0, "ecx": 1, "edx": 2, "ebx": 3, "esp": 4, "ebp": 5, "esi": 6, "edi": 7}
R32.update({"r%dd" % k: k for k in range(8, 16)})


def emit_mulflag(pool, ins, group):
    """the relocated imul, then imul r32, dword [N] on its destination"""
    tr.emit_relocated(pool, ins, None)
    r = R32[ins.reg_name(ins.operands[0].reg)]
    rex = b"\x44" if r >= 8 else b""
    pool.pool_rel32(rex + bytes([0x0F, 0xAF, ((r & 7) << 3) | 5]), group_intn(group))


FPS_BYTE = 0xB6AC44


def emit_mulstore(pool, ins, group):
    """push r64; imul r32, dword [N]; the store; pop r64: the wait stored
    times N, the register kept (the store has no rip operand: its bytes as
    they are)"""
    r = R32[ins.reg_name(ins.operands[1].reg)]
    rex = b"\x41" if r >= 8 else b""
    pool.emit(rex + bytes([0x50 + (r & 7)]))                            # push r64
    pool.pool_rel32((b"\x44" if r >= 8 else b"") +
                    bytes([0x0F, 0xAF, ((r & 7) << 3) | 5]), group_intn(group))
    pool.emit(bytes(ins.bytes))                                         # the store
    pool.emit(rex + bytes([0x58 + (r & 7)]))                            # pop r64


def prove_mulstore(dec, targets, ins, read_at):
    """None if `ins` is `mov dword [B + d], r32` (B not rsp, rip or r, no
    index) and the straight line from read_at to it is `movzx r32, byte [the
    fps byte]`, `shr r32, 1` and instructions that neither write r32 nor
    leave the line, with no way into it after read_at"""
    ops = ins.operands
    if ins.mnemonic != "mov" or len(ops) != 2 or ops[0].type != X.X86_OP_MEM or \
            ops[0].size != 4 or ops[1].type != X.X86_OP_REG or ops[1].size != 4:
        return "mulstore needs mov dword [B + d], r32"
    m = ops[0].mem
    r = gis.canon(ins, ops[1].reg)
    if m.base in (0, X.X86_REG_RIP, X.X86_REG_RSP) or m.index or \
            gis.canon(ins, m.base) == r:
        return "mulstore needs a plain [B + d] with B not rsp, rip or the stored register"
    seq = [i for i in dec.run(read_at, ins.address) if i.address <= ins.address]
    if not seq or seq[0].address != read_at or seq[-1].address != ins.address:
        return "cannot decode %X..%X" % (read_at, ins.address)
    first = seq[0]
    fo = first.operands
    if first.mnemonic != "movzx" or fo[0].type != X.X86_OP_REG or \
            gis.canon(first, fo[0].reg) != r or fo[1].type != X.X86_OP_MEM or \
            fo[1].size != 1 or fo[1].mem.base != X.X86_REG_RIP or \
            first.address + first.size + fo[1].mem.disp != FPS_BYTE:
        return "%X is not movzx of the stored register from the fps byte" % read_at
    halved = False
    for i in seq[1:-1]:
        if i.address in targets:
            return "a branch target at %X inside the stretch" % i.address
        if i.mnemonic.startswith(("j", "call", "ret", "loop")):
            return "control transfer at %X inside the stretch" % i.address
        _rd, w = i.regs_access()
        if r not in {gis.canon(i, x) for x in w}:
            continue
        if i.mnemonic == "shr" and not halved and i.operands[0].type == X.X86_OP_REG and \
                i.operands[1].type == X.X86_OP_IMM and i.operands[1].imm == 1:
            halved = True
            continue
        return "%X %s %s writes the stored register" % (i.address, i.mnemonic, i.op_str)
    if ins.address in targets:
        return "a branch target at the store %X" % ins.address
    if not halved:
        return "no shr r32, 1 between %X and the store" % read_at
    return None


def prove_mulflag(dec, targets, ins, extra):
    """None if `ins` is `imul r32, r32` one of whose operands holds 1 << the 60
    fps flag, built in straight-line code nothing branches into: `mov r32, 1`
    at one_at, `mov ecx, dword [flag]` at read_at (then at most `and ecx,
    0x1f`), `shl r16, cl` of that register, and a `movzx r32, r16` of it into
    the operand; no other write of those registers on the way."""
    one_at, read_at = extra
    ops = ins.operands
    if ins.mnemonic != "imul" or len(ops) != 2 or ops[0].type != X.X86_OP_REG or \
            ops[1].type != X.X86_OP_REG or ops[0].size != 4:
        return "mulflag needs imul r32, r32"
    seq = [i for i in dec.run(one_at, ins.address) if i.address <= ins.address]
    if not seq or seq[0].address != one_at or seq[-1].address != ins.address:
        return "cannot decode %X..%X" % (one_at, ins.address)
    for i in seq[1:]:
        if i.address in targets:
            return "a branch target at %X inside the stretch" % i.address
        if i.mnemonic.startswith(("j", "call", "ret", "loop")):
            return "control transfer at %X inside the stretch" % i.address
    first = seq[0]
    if first.mnemonic != "mov" or first.operands[1].type != X.X86_OP_IMM or \
            first.operands[1].imm != 1:
        return "%X is not mov r32, 1" % one_at
    one = gis.canon(first, first.operands[0].reg)
    state = {one: "one"}
    for i in seq[1:-1]:
        text = "%s %s" % (i.mnemonic, i.op_str)
        _r, w = i.regs_access()
        wrote = {gis.canon(i, r) for r in w} - {gis.canon(i, X.X86_REG_EFLAGS)}
        if i.address == read_at:
            mem = next((op.mem for op in i.operands if op.type == X.X86_OP_MEM), None)
            if text.split(",")[0] != "mov ecx" or mem is None or mem.base != X.X86_REG_RIP or \
                    i.address + i.size + mem.disp != 0xB6AC40:
                return "%X is not mov ecx, dword [the 60 fps flag]" % read_at
            state[gis.canon(i, X.X86_REG_ECX)] = "flag"
            continue
        if i.mnemonic == "and" and text == "and ecx, 0x1f" and \
                state.get(gis.canon(i, X.X86_REG_ECX)) == "flag":
            continue
        if i.mnemonic == "shl" and text.endswith(", cl") and \
                state.get(gis.canon(i, X.X86_REG_ECX)) == "flag" and \
                state.get(gis.canon(i, i.operands[0].reg)) == "one":
            state[gis.canon(i, i.operands[0].reg)] = "shifted"
            continue
        if i.mnemonic == "movzx" and i.operands[1].type == X.X86_OP_REG and \
                state.get(gis.canon(i, i.operands[1].reg)) == "shifted":
            for k in list(state):
                if k == gis.canon(i, i.operands[0].reg):
                    del state[k]
            state[gis.canon(i, i.operands[0].reg)] = "factor"
            continue
        for r in wrote:
            if r in state:
                del state[r]
    factors = {gis.canon(ins, op.reg) for op in ops}
    if not any(state.get(f) == "factor" for f in factors):
        return "no operand of %X holds 1 << the flag" % ins.address
    return None


def emit_root_chain(pool, d, group):
    """xmmD = xmmD ** (1/N): one sqrtss per set bit of the mask (1, then 2),
    only when xmmD > 0. Clobbers the flags."""

    def jcc8(opcode):
        pool.emit(bytes([opcode, 0]))
        return len(pool.code)

    exits = []
    # comiss xmmD, [zero]: CF or ZF (and PF, NaN) when xmmD <= 0
    pool.pool_rel32(rex_for(d) + bytes([0x0F, 0x2F, ((d & 7) << 3) | 5]), ZERO_OFFSET)
    exits.append(jcc8(0x76))                                         # jbe done
    sqrt = gmt.enc_rr(0x51, "xmm%d" % d, "xmm%d" % d)
    for bit in (1, 2):
        pool.pool_rel32(b"\xF6\x05", group_mask(group), trailing=bytes([bit]))  # test [mask], bit
        exits.append(jcc8(0x74))                                     # jz done
        pool.emit(sqrt)
    for at in exits:
        pool.code[at - 1] = len(pool.code) - at


def prove_callgate(dec, after):
    """None if, from the instruction after the call, rax is first read as the
    answer's low byte (`test al, al`, or `movzx r32, al`) with no branch,
    call or return before it."""
    at = after
    for _ in range(12):
        i = dec.run(at, at)[0]
        rd, wr = gmt.reads_writes(i)
        text = "%s %s" % (i.mnemonic, i.op_str)
        if rd & {"rax", "eax", "ax", "al", "ah"}:
            if text == "test al, al" or (i.mnemonic == "movzx" and text.endswith(", al")):
                return None
            return "the answer is read at %X by %s" % (at, text)
        if wr & {"rax", "eax", "ax", "al", "ah"}:
            return "rax rewritten at %X before the answer is read" % at
        if i.mnemonic.startswith("j") or i.mnemonic in ("call", "ret"):
            return "control flow at %X before the answer is read" % at
        at += i.size
    return "the answer is not read within 12 instructions"


def emit_blend(pool, group):
    """At N > 1 and 0 < xmm2 < 1: xmm2 = 1 - (1 - xmm2)^(1/N), by the root chain
    on xmm4, the result merged into xmm2's low lane from xmm5 (both volatile
    and no argument of the clamped approach; xmm2's other lanes are kept).
    Otherwise xmm2 is left as it is. Clobbers the flags (dead at a call)."""

    def jcc8(opcode):
        pool.emit(bytes([opcode, 0]))
        return len(pool.code)

    exits = []
    pool.pool_rel32(b"\xF6\x05", group_mask(group), trailing=b"\xFF")    # test [mask], 0xFF
    exits.append(jcc8(0x74))                                              # jz done: N = 1
    pool.pool_rel32(b"\x0F\x2F\x15", ZERO_OFFSET)                          # comiss xmm2, [0.0]
    exits.append(jcc8(0x76))                                              # jbe done: k <= 0, NaN
    pool.pool_rel32(b"\x0F\x2F\x15", ONE_OFFSET)                           # comiss xmm2, [1.0]
    exits.append(jcc8(0x73))                                              # jae done: k >= 1
    pool.pool_rel32(b"\xF3\x0F\x10\x25", ONE_OFFSET)                      # movss xmm4, [1.0]
    pool.emit(b"\xF3\x0F\x5C\xE2")                                        # subss xmm4, xmm2
    emit_root_chain(pool, 4, group)
    pool.pool_rel32(b"\xF3\x0F\x10\x2D", ONE_OFFSET)                      # movss xmm5, [1.0]
    pool.emit(b"\xF3\x0F\x5C\xEC")                                        # subss xmm5, xmm4
    pool.emit(b"\xF3\x0F\x10\xD5")                                        # movss xmm2, xmm5
    for at in exits:
        pool.code[at - 1] = len(pool.code) - at


def emit_fn_gate(pool, counter, group, ret0=False):
    """gen_menu_transitions.emit_fn_gate, reading this group's mask. With
    ret0, a tick between stock ticks returns eax = 0 (gate0)."""
    slot = COUNTER_OFFSET + SLOT * counter
    mask = group_mask(group)

    def jcc8(opcode):
        pool.emit(bytes([opcode, 0]))
        return len(pool.code)

    def land(at):
        pool.code[at - 1] = len(pool.code) - at

    pool.emit(b"\x50")                                           # push rax
    pool.pool_rel32(b"\xFF\x05", slot + gis.PASSES)
    pool.game_rel32(b"\x8B\x05", tr.FRAME_COUNTER)               # mov eax, [fc]
    pool.pool_rel32(b"\x3B\x05", slot + gis.LAST_TICK)
    same = jcc8(0x74)
    pool.pool_rel32(b"\x89\x05", slot + gis.LAST_TICK)
    pool.pool_rel32(b"\xFF\x05", slot + gis.TICKS)
    pool.pool_rel32(b"\x84\x05", mask)
    skipped = jcc8(0x75)
    pool.pool_rel32(b"\xFF\x05", slot + gis.COUNTED)
    land(same)
    land(skipped)
    pool.pool_rel32(b"\x84\x05", mask)                           # test [mask], al
    pool.emit(b"\x58")                                           # pop rax
    run = jcc8(0x74)                                             # jz body
    if ret0:
        pool.emit(b"\x33\xC0")                                   # xor eax, eax
    pool.emit(b"\xC3")                                           # ret: not a stock tick
    land(run)


def iat_names():
    """{IAT slot rva: import name} of main.dll."""
    import pefile
    from gamedir import GAME
    pe = pefile.PE(os.path.join(GAME, "main.dll"), fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    out = {}
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in entry.imports:
            if imp.name:
                out[imp.address - base] = imp.name.decode()
    return out


def prove_dstarg(dec, ins, call_at, iat):
    """`movss xmmN, m32`, a component of this tick's step vector: straight line
    to the cVec(float x4) constructor call at call_at, xmmN neither read nor
    written on the way."""
    ops = ins.operands
    if ins.mnemonic not in ("movss", "movaps") or ops[0].type != X.X86_OP_REG or \
            not ins.reg_name(ops[0].reg).startswith("xmm") or \
            (ins.mnemonic == "movss" and ops[1].type != X.X86_OP_MEM):
        return "dstarg needs movss xmm, m32 or movaps xmm, xmm"
    reg = ins.reg_name(ops[0].reg)
    at = ins.address + ins.size
    for _ in range(16):
        i = dec.run(at, at)[0]
        if at == call_at:
            m = i.operands[0].mem if i.operands and i.operands[0].type == X.X86_OP_MEM else None
            if i.mnemonic != "call" or m is None or m.base != X.X86_REG_RIP:
                return "%X is not an import call" % at
            name = iat.get(at + i.size + m.disp)
            if name != CVEC4:
                return "%X calls %s, not %s" % (at, name, CVEC4)
            return None
        rd, wr = gmt.reads_writes(i)
        if reg in rd or reg in wr:
            return "%s touched at %X %s %s" % (reg, at, i.mnemonic, i.op_str)
        if i.mnemonic.startswith("j") or i.mnemonic in ("call", "ret"):
            return "control flow at %X before the constructor" % at
        at += i.size
    return "no constructor call within 16 instructions"


def import_call(i, iat):
    """The import a `call qword ptr [rip + X]` calls, or None."""
    m = i.operands[0].mem if i.operands and i.operands[0].type == X.X86_OP_MEM else None
    if i.mnemonic != "call" or m is None or m.base != X.X86_REG_RIP:
        return None
    return iat.get(i.address + i.size + m.disp)


def import_tail(i, iat):
    """The import a `jmp qword ptr [rip + X]` tail-jumps to, or None."""
    m = i.operands[0].mem if i.operands and i.operands[0].type == X.X86_OP_MEM else None
    if i.mnemonic != "jmp" or m is None or m.base != X.X86_REG_RIP:
        return None
    return iat.get(i.address + i.size + m.disp)


def factor_consumer(dec, ins, reg, iat):
    """For ufirst/ulast: the register's next reader multiplies by it (mulss
    with it as either operand) or passes it to cVec::operator*=(float) in
    xmm1, on straight-line code. A movaps copy may feed another multiply;
    both the copy and the original must reach their multiplies."""
    at = ins.address + ins.size
    for _ in range(32):
        i = dec.run(at, at)[0]
        rd, wr = gmt.reads_writes(i)
        if i.mnemonic == "call":
            return None if reg == "xmm1" and import_call(i, iat) == CVEC_MULF else \
                "call at %X is not operator*=(float) taking %s" % (at, reg)
        if reg in rd:
            if i.mnemonic == "movaps" and len(i.operands) == 2 and \
                    i.operands[0].type == X.X86_OP_REG and \
                    i.operands[1].type == X.X86_OP_REG and \
                    i.reg_name(i.operands[1].reg) == reg:
                copy = i.reg_name(i.operands[0].reg)
                why = factor_consumer(dec, i, copy, iat)
                if why:
                    return "copy in %s: %s" % (copy, why)
                at += i.size
                continue
            return None if i.mnemonic == "mulss" else \
                "first reader of %s at %X is %s %s" % (reg, at, i.mnemonic, i.op_str)
        if reg in wr:
            return "%s rewritten at %X before its use" % (reg, at)
        if i.mnemonic.startswith("j") or i.mnemonic == "ret":
            return "control flow at %X before the factor is used" % at
        at += i.size
    return "no use of %s within 32 instructions" % reg


def prove_scale_arg(dec, ins, call_at, iat, allowed=(CVEC_SCALE,)):
    """xmm2 loaded by `ins` is only the float argument of ScaleXYZ at call_at:
    on the way it is at most tested against 0 (ucomiss), branches only jump
    forward to at most just past the call, and nothing else touches it. So a
    factor made 1.0, or a magnitude made 0, has the effect of no step. For a
    `dst` row the call may also be cVec::operator*(float) const, which takes
    its factor in xmm2 as well (rcx this, rdx the result)."""
    reg = ins.reg_name(ins.operands[0].reg)
    if reg != "xmm2":
        return "ScaleXYZ takes its scale in xmm2, not %s" % reg
    at = ins.address + ins.size
    for _ in range(16):
        i = dec.run(at, at)[0]
        if at == call_at:
            name = import_call(i, iat)
            return None if name in allowed else "%X calls %s, not ScaleXYZ" % (at, name)
        rd, wr = gmt.reads_writes(i)
        if i.mnemonic in ("ucomiss", "comiss") and reg in rd and reg not in wr:
            pass
        elif reg in rd or reg in wr:
            return "%s touched at %X %s %s" % (reg, at, i.mnemonic, i.op_str)
        if i.mnemonic.startswith("j"):
            if not tr.is_rel_branch(i) or i.mnemonic == "jmp":
                return "branch at %X" % at
            t = i.operands[0].imm
            if not at < t <= call_at + 6:
                return "branch at %X leaves the block" % at
        elif i.mnemonic in ("call", "ret"):
            return "control flow at %X before ScaleXYZ" % at
        at += i.size
    return "no ScaleXYZ within 16 instructions"


SLOWMO_GETTER = 0x23AD90   # the game's slow-motion factor: 0.25 while [9C1F50]+0x234 is 1


def prove_slowmo_copy(dec, ins, call_at):
    """`movaps xmmD, xmm0` into a callee-saved xmmD, on straight-line code
    after `call 23AD90` at call_at with nothing writing xmm0 between."""
    ops = ins.operands
    if ins.mnemonic != "movaps" or ops[1].type != X.X86_OP_REG or \
            ins.reg_name(ops[1].reg) != "xmm0" or ops[0].type != X.X86_OP_REG:
        return "slowmo needs movaps xmmD, xmm0"
    if gmt.xmm_index(ins.reg_name(ops[0].reg)) < 6:
        return "%s is volatile: a call would lose it" % ins.reg_name(ops[0].reg)
    c = dec.run(call_at, call_at)
    if not c or c[0].mnemonic != "call" or c[0].operands[0].type != X.X86_OP_IMM or \
            c[0].operands[0].imm != SLOWMO_GETTER:
        return "%X is not a call of %X" % (call_at, SLOWMO_GETTER)
    at = call_at + c[0].size
    for _ in range(16):
        if at == ins.address:
            return None
        i = dec.run(at, at)[0]
        rd, wr = gmt.reads_writes(i)
        if "xmm0" in wr:
            return "xmm0 written at %X before the copy" % at
        if i.mnemonic.startswith("j") or i.mnemonic in ("call", "ret"):
            return "control flow at %X before the copy" % at
        at += i.size
    return "the copy is not within 16 instructions of the call"


def prove_argscale(dec, ins):
    """`movaps xmmD, xmmA` (xmmA an argument register, xmm0..xmm3) into a
    callee-saved xmmD, and from there to the
    function's ret nothing reads xmmD but `movaps xmmX, xmmD` copies and
    nothing writes it but the epilogue's restore from the stack. Branches on
    the way must stay inside that stretch."""
    ops = ins.operands
    if ins.mnemonic != "movaps" or ops[1].type != X.X86_OP_REG or \
            ins.reg_name(ops[1].reg) not in ("xmm0", "xmm1", "xmm2", "xmm3"):
        return "argscale needs movaps xmmD, xmm0..xmm3"
    reg = ins.reg_name(ops[0].reg)
    if gmt.xmm_index(reg) < 6:
        return "%s is volatile: a call would lose it" % reg
    at, end = ins.address + ins.size, None
    body = []
    for _ in range(64):
        i = dec.run(at, at)[0]
        body.append(i)
        if i.mnemonic == "ret":
            end = i.address
            break
        at += i.size
    if end is None:
        return "no ret within 64 instructions"
    restored = False
    for i in body:
        rd, wr = gmt.reads_writes(i)
        if i.mnemonic.startswith("j") and (not tr.is_rel_branch(i) or
                                            not ins.address < i.operands[0].imm <= end):
            return "branch at %X leaves the function's tail" % i.address
        if reg in wr:
            if i.mnemonic == "movaps" and i.operands[1].type == X.X86_OP_MEM and \
                    i.operands[1].mem.base == X.X86_REG_RSP:
                restored = True
                continue
            return "%s written at %X" % (reg, i.address)
        if reg in rd and not (i.mnemonic == "movaps" and i.operands[1].type == X.X86_OP_REG
                              and i.reg_name(i.operands[1].reg) == reg):
            return "%s read at %X by %s %s" % (reg, i.address, i.mnemonic, i.op_str)
    return None if restored else "%s is not restored before the ret" % reg


def prove_join(dec, starts, sources, indirect, rva, block_lo):
    """Every way into `rva` comes from [block_lo, rva): direct branches and the
    fall-through, and it is no indirect destination."""
    if rva in indirect:
        return "%X is an indirect destination" % rva
    for src, _s, mn in sources.get(rva, []):
        if not block_lo <= src < rva:
            return "%X is entered by the %s at %X, outside the reload" % (rva, mn, src)
    phys = gmt.physical_predecessor(dec, starts, rva)
    if phys is None or not block_lo <= phys.address < rva:
        return "%X does not follow the reload block" % rva
    return None


def emit_floor1(pool, ins, group, base, disp, temp):
    """While the mask is set: [base + disp] = max([base + disp], 1.0). The
    flags are proven dead; temp is proven dead."""
    t = gmt.xmm_index(temp)
    b = {"rbx": 3, "rsi": 6, "rdi": 7, "rbp": 5}[base]
    assert t < 8 and base != "rbp"

    def mem(op):
        return b"\xF3\x0F" + bytes([op, 0x80 | (t << 3) | b]) + struct.pack("<i", disp)
    pool.pool_rel32(b"\xF6\x05", group_mask(group), trailing=b"\xFF")   # test [mask], 0xFF
    pool.emit(b"\x74\x00")                                                  # jz skip
    at = len(pool.code)
    pool.emit(mem(0x10))                                                    # movss xmmT, [b + d]
    pool.pool_rel32(b"\xF3\x0F\x5F" + bytes([(t << 3) | 5]), ONE_OFFSET)    # maxss xmmT, [1.0]
    pool.emit(mem(0x11))                                                    # movss [b + d], xmmT
    pool.code[at - 1] = len(pool.code) - at
    tr.emit_relocated(pool, ins, None)


def emit_scaledadd(pool, group, tail=False):
    """In place of `call` or import tail-jump to cVec::operator+= (rcx += rdx, xyz; w kept; rax =
    rcx): each of x, y, z: movss xmm0, [rdx+k]; mulss xmm0, [s]; addss xmm0,
    [rcx+k]; movss [rcx+k], xmm0. xmm0 is volatile across the call it
    replaces, and flags are dead at a call."""
    for k in (0, 4, 8):
        disp = b"" if k == 0 else bytes([k])
        mod = 0x00 if k == 0 else 0x40
        pool.emit(b"\xF3\x0F\x10" + bytes([mod | 0x02]) + disp)          # movss xmm0, [rdx+k]
        pool.pool_rel32(b"\xF3\x0F\x59\x05", group_scale(group))       # mulss xmm0, [s]
        pool.emit(b"\xF3\x0F\x58" + bytes([mod | 0x01]) + disp)          # addss xmm0, [rcx+k]
        pool.emit(b"\xF3\x0F\x11" + bytes([mod | 0x01]) + disp)          # movss [rcx+k], xmm0
    pool.emit(b"\x48\x8B\xC1")                                           # mov rax, rcx
    if tail:
        pool.emit(b"\xC3")                                                # ret to original caller


def emit_immstore(pool, ins, temp, group):
    """Replace an unprefixed `mov m32, imm32` whose immediate is float K
    with `m32 = K*s`. K lives in the stub so this kind needs no mutable
    literal slot. The proof has established that temp is dead, that the
    destination is not RIP-relative, and that the original encoding is the
    unprefixed C7 /0 form; the copied ModRM/SIB/displacement therefore names
    the same address from the stub."""
    raw = bytes(ins.bytes)
    t = gmt.xmm_index(temp)
    pool.emit(b"\xEB\x04")                                      # jump over embedded K
    k = pool.here()
    pool.emit(raw[ins.imm_offset:ins.imm_offset + 4])
    pool.pool_rel32(b"\xF3" + rex_for(t) +
                    bytes([0x0F, 0x10, ((t & 7) << 3) | 5]), k)  # movss xmmT, [K]
    emit_mulss_scale(pool, temp, group)
    modrm = raw[ins.modrm_offset]
    store = (b"\xF3" + rex_for(t) + bytes([0x0F, 0x11,
             (modrm & 0xC7) | ((t & 7) << 3)]) +
             raw[ins.modrm_offset + 1:ins.imm_offset])
    pool.emit(store)                                              # movss original m32, xmmT


def prove_gate0(dec, starts, begins, rva, noop):
    """An entry whose own no-op path returns al = 0: `xor al, al` or `xor eax,
    eax`, then the prologue's stack adjustment undone, then ret."""
    if rva not in begins:
        return "not a function start in .pdata"
    phys = gmt.physical_predecessor(dec, starts, rva)
    if phys is not None and phys.mnemonic not in tr.UNCOND | tr.PADDING:
        return "falls through from %X %s" % (phys.address, phys.mnemonic)
    first = dec.run(rva, rva)[0]
    if first.mnemonic != "sub" or first.op_str.split(", ")[0] != "rsp":
        return "entry does not open with sub rsp"
    seq = dec.run(noop, noop + 12)
    if len(seq) < 3 or "%s %s" % (seq[0].mnemonic, seq[0].op_str) not in ("xor al, al",
                                                                          "xor eax, eax"):
        return "no-op path at %X does not clear al" % noop
    if seq[1].mnemonic != "add" or seq[1].op_str != first.op_str or seq[2].mnemonic != "ret":
        return "no-op path at %X does not undo %s and return" % (noop, first.op_str)
    return None


def flags_dead_after(dec, at, bound=160):
    """None if no arithmetic flag is read from `at` on before every path has
    rewritten all six, reached a call or returned."""
    work, seen = [(at, FLAGS6)], set()
    while work:
        a, live = work.pop()
        if not live or (a, live) in seen:
            continue
        if len(seen) > bound:
            return "flag liveness exceeds the bound"
        seen.add((a, live))
        seq = dec.run(a, a)
        if not seq or seq[0].address != a:
            return "cannot decode %X for flag liveness" % a
        i = seq[0]
        if i.mnemonic in ("call", "ret", "retf"):
            continue
        if i.mnemonic in ("int3", "ud2"):
            return "flag path reaches padding at %X" % a
        ef = gis.arithmetic_eflags(i)
        if any(ef & gis.READ_FLAG[f] for f in live):
            return "flags read at %X %s %s" % (a, i.mnemonic, i.op_str)
        remaining = frozenset(f for f in live if not ef & gis.WRITE_FLAG[f])
        if i.mnemonic.startswith("j"):
            if not tr.is_rel_branch(i):
                return "indirect branch at %X" % a
            work.append((i.operands[0].imm, remaining))
            if i.mnemonic != "jmp":
                work.append((a + i.size, remaining))
        else:
            work.append((a + i.size, remaining))
    return None


# which way a conditional branch goes with ZF = SF = OF = 0 (CF and PF unread)
NOT_YET_TAKEN = {"jle": False, "jg": True, "jl": False, "jge": True, "je": False,
                 "jne": True, "js": False, "jns": True, "jo": False, "jno": True}


def prove_notyet(dec, ins, notyet_at, negative=False, below=False):
    """None if `ins` is `test r, r` (or `test r, imm` / `test m, imm`: a
    counter's low bits, an every-8th-tick test; `and r, imm`, whose register
    result must be preserved on skipped ticks; or `cmp`, a counter's
    equality or signed limit used by an event) whose
    flags have exactly one reader, the next conditional branch (allowing
    flag-neutral register moves/loads between the test and branch),
    that branch reads only ZF, SF and OF, and with those clear it goes to
    notyet_at."""
    ops = ins.operands
    same_reg = len(ops) == 2 and ops[0].type == X.X86_OP_REG and \
        ops[1].type == X.X86_OP_REG and ops[0].reg == ops[1].reg
    bits = len(ops) == 2 and ops[0].type in (X.X86_OP_REG, X.X86_OP_MEM) and \
        ops[1].type == X.X86_OP_IMM
    and_reg = ins.mnemonic == "and" and len(ops) == 2 and \
        ops[0].type == X.X86_OP_REG and ops[1].type == X.X86_OP_IMM
    if not (ins.mnemonic == "test" and (same_reg or bits)) and \
            ins.mnemonic != "cmp" and not and_reg:
        return "notyet needs test r, r, test r/m, imm, and r, imm or cmp"
    at = ins.address + ins.size
    for _ in range(3):
        seq = dec.run(at, at)
        if not seq or seq[0].address != at:
            return "cannot decode the branch after the test"
        br = seq[0]
        ops = br.operands
        if br.mnemonic != "mov" or len(ops) != 2 or \
                ops[0].type != X.X86_OP_REG or br.reg_name(ops[0].reg) == "rsp" or \
                ops[1].type not in (X.X86_OP_IMM, X.X86_OP_REG, X.X86_OP_MEM):
            break
        at += br.size
    if below:
        if ins.mnemonic != "cmp" or br.mnemonic not in ("jb", "jbe", "jae", "ja") or \
                not tr.is_rel_branch(br):
            return "notyetb needs cmp read by JB, JBE, JAE or JA, not %s %s" % (
                ins.mnemonic, br.mnemonic)
        # CF = 1, ZF = 0: JB/JBE jump, JAE/JA fall through
        goes = br.operands[0].imm if br.mnemonic in ("jb", "jbe") else at + br.size
        if goes != notyet_at:
            return "with CF = 1 and ZF = 0, %X %s goes to %X, not %X" % (
                at, br.mnemonic, goes, notyet_at)
        for nxt in (br.operands[0].imm, at + br.size):
            why = flags_dead_after(dec, nxt)
            if why:
                return "after the branch: " + why
        return None
    if br.mnemonic not in NOT_YET_TAKEN or not tr.is_rel_branch(br):
        return "the test's next flag reader is %s, not a signed or zero branch" % br.mnemonic
    if negative and br.mnemonic not in ("jl", "jle", "jge", "jg"):
        return "a negative not-yet path needs JL, JLE, JGE or JG, not %s" % br.mnemonic
    if not negative and ins.mnemonic == "cmp" and br.mnemonic not in ("je", "jne", "jg", "jle"):
        return "a cmp's not-yet supports zero or signed-positive branches, not %s" % br.mnemonic
    # SF = 1, OF = ZF = 0: JL/JLE jump, JGE/JG fall through
    taken = br.mnemonic in ("jl", "jle") if negative else NOT_YET_TAKEN[br.mnemonic]
    goes = br.operands[0].imm if taken else at + br.size
    if goes != notyet_at:
        return "with ZF = OF = 0 and SF = %d, %X %s goes to %X, not %X" % (
            int(negative), at, br.mnemonic, goes, notyet_at)
    # nothing after the branch may read the test's flags, on either path
    for nxt in (br.operands[0].imm, at + br.size):
        why = flags_dead_after(dec, nxt)
        if why:
            return "after the branch: " + why
    return None


def unwind_record_bytes(img, secs):
    """.rdata offsets inside an UNWIND_INFO record's header and unwind codes,
    and a chained record's RUNTIME_FUNCTION: unwind data, whose dwords can
    look like code addresses (the codes at 747074 read 001C6413)."""
    a, b = secs[".pdata"]
    out = set()
    for off in range(a, b - 11, 12):
        begin, end, unwind = struct.unpack_from("<III", img, off)
        if begin == 0 and end == 0:
            break
        codes = img[unwind + 2]
        size = 4 + 2 * (codes + (codes & 1))
        if (img[unwind] >> 3) & 4:
            size += 12
        out.update(range(unwind, unwind + size))
    return out


def code_refs_outside_unwind(img, secs, lo, hi, starts):
    """tr.data_references, without the dwords that lie in unwind records."""
    skip = unwind_record_bytes(img, secs)
    found = set()
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range((a + 3) & ~3, b - 3, 4):
            v = struct.unpack_from("<I", img, off)[0]
            if lo <= v < hi and starts[v] and off not in skip:
                found.add(v)
        for off in range((a + 7) & ~7, b - 7, 8):
            v = struct.unpack_from("<Q", img, off)[0] - tr.BASE
            if lo <= v < hi and starts[v]:
                found.add(v)
    return found


def unaligned_code_refs(img, secs, lo, hi, starts):
    """Actual data pointers, including packed/unaligned data and export RVAs.
    Pure unwind headers/codes describe frames; handler and scope addresses
    after those codes remain included in this scan.
    """
    skip = unwind_record_bytes(img, secs)
    found = set()
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a, b - 3):
            v = struct.unpack_from("<I", img, off)[0]
            if lo <= v < hi and starts[v] and off not in skip:
                found.add(v)
            if off + 8 <= b:
                v = struct.unpack_from("<Q", img, off)[0] - tr.BASE
                if lo <= v < hi and starts[v]:
                    found.add(v)
    return found


TASK_WAIT = 0x4567C0   # main+4567C0(task, n), the scripted tasks' wait


def task_wait_loops():
    """the waits src/task_waits.h takes over as loops (entry 1): one pass a
    stock tick"""
    text = open(os.path.join(ROOT, "src", "task_waits.h"), encoding="utf-8").read()
    body = re.search(r"kTaskWaitSites\[\]\s*=\s*\{(.*?)\n\};", text, re.S).group(1)
    return {int(a, 16) for a, _r, _t, _o, e in re.findall(
        r"\{0x([0-9A-F]+), (-?\d+), (\d+), 0x([0-9A-F]{2}), (\d)\}", body) if e == "1"}


def reaches(dec, start, goal, bound=2000):
    """`goal` is reached from `start` along the function's own edges (calls
    return, ret ends a path), breadth first"""
    work, seen = collections.deque([start]), set()
    while work:
        at = work.popleft()
        if at == goal:
            return True
        if at in seen or len(seen) > bound:
            continue
        seen.add(at)
        seq = dec.run(at, at)
        if not seq or seq[0].address != at:
            continue
        i = seq[0]
        if i.mnemonic in ("ret", "int3", "ud2"):
            continue
        if i.mnemonic.startswith("j"):
            if not tr.is_rel_branch(i):
                continue
            work.append(i.operands[0].imm)
            if i.mnemonic == "jmp":
                continue
        work.append(at + i.size)
    return False


def prove_paced_store(dec, ins, wait_at):
    """dstn: the result is only stored, and the site is on a cycle through a
    wait that task_waits.h takes over as a loop"""
    if not isinstance(wait_at, int):
        return "dstn needs the address of its loop's wait call"
    seq = dec.run(wait_at, wait_at)
    if not seq or seq[0].address != wait_at or seq[0].mnemonic != "call" or \
            seq[0].operands[0].type != X.X86_OP_IMM or seq[0].operands[0].imm != TASK_WAIT:
        return "%X is not a call of the task wait %X" % (wait_at, TASK_WAIT)
    if wait_at not in task_wait_loops():
        return "task_waits.h does not take the wait at %X over as a loop" % wait_at
    if not reaches(dec, ins.address, wait_at) or not reaches(dec, wait_at, ins.address):
        return "%X and the wait at %X are not on one cycle" % (ins.address, wait_at)
    reg = ins.reg_name(ins.operands[0].reg)
    at = ins.address + ins.size
    nxt = dec.run(at, at)
    if not nxt or nxt[0].address != at:
        return "cannot decode %X" % at
    st = nxt[0]
    ops = st.operands
    if st.mnemonic != "movss" or ops[0].type != X.X86_OP_MEM or ops[1].type != X.X86_OP_REG or \
            st.reg_name(ops[1].reg) != reg:
        return "the next instruction %s %s is not a store of %s" % (st.mnemonic, st.op_str, reg)
    return gmt.xmm_dead_after(dec, st, reg)


def step_source_consumer(dec, ins, reg):
    """For `dst` whose step is subtracted or added as a source: the first
    reader of reg is `addss/subss xmmA, reg` with xmmA another register, and
    reg is dead after it."""
    at = ins.address + ins.size
    for _ in range(12):
        seq = dec.run(at, at)
        i = seq[0]
        rd, wr = gmt.reads_writes(i)
        if reg in rd:
            ops = i.operands
            if i.mnemonic in ("addss", "subss") and ops[1].type == X.X86_OP_REG and \
                    i.reg_name(ops[1].reg) == reg and i.reg_name(ops[0].reg) != reg:
                return gmt.xmm_dead_after(dec, i, reg)
            return "first reader of %s at %X is %s %s" % (reg, at, i.mnemonic, i.op_str)
        if reg in wr:
            return "%s rewritten at %X before any accumulation" % (reg, at)
        if i.mnemonic.startswith("j") or i.mnemonic in ("call", "ret"):
            return "control flow at %X before the accumulation" % at
        at += i.size
    return "no accumulation of %s within 12 instructions" % reg


def triple_rise_consumer(dec, ins, reg):
    """Animal callbacks use one 0.03 step for D20/D24/D28.

    The shared source is kept across the three guarded additions, so the
    ordinary single-consumer proof is deliberately too narrow. Check each
    addition and every intervening instruction before scaling the load.
    """
    uses = {
        0x1E7CD6: (0x1E7CDE, 0x1E7D01, 0x1E7D24),
        0x1EAE28: (0x1EAE30, 0x1EAE53, 0x1EAE76),
        0x1EDFAA: (0x1EDFB2, 0x1EDFD5, 0x1EDFF8),
        0x1F5628: (0x1F5630, 0x1F5653, 0x1F5676),
        0x1FB885: (0x1FB88D, 0x1FB8B0, 0x1FB8D3),
    }.get(ins.address)
    if not uses or reg != "xmm1" or ins.mnemonic != "movss" or \
            ins.op_str.split(", ", 1)[0] != "xmm1":
        return "not a shared animal rise step"
    seq = [i for i in dec.run(ins.address + ins.size, uses[-1])
           if i.address <= uses[-1]]
    for i in seq:
        rd, wr = gmt.reads_writes(i)
        if i.address in uses:
            if i.mnemonic != "addss" or i.op_str != "xmm0, xmm1":
                return "rise use at %X changed" % i.address
        elif reg in rd or reg in wr:
            return "other rise-step use at %X" % i.address
    if tuple(i.address for i in seq if i.address in uses) != uses:
        return "missing rise-step use"
    return gmt.xmm_dead_after(dec, seq[-1], reg)


def shared_animal_displacement(dec, ins, reg):
    """The anc7 platform step feeds its height and five linked world offsets."""
    paths = {
        0x201FF9: ("xmm3", (0x201FFC, 0x20202E, 0x202043, 0x202057,
                             0x20206B, 0x20207F, 0x202093)),
        0x2020C6: ("xmm2", (0x2020D2, 0x202103, 0x202114, 0x202128,
                             0x20213C, 0x202150, 0x202164)),
    }
    path = paths.get(ins.address)
    if not path or path[0] != reg:
        return "not an anc7 shared displacement"
    uses = path[1]
    seq = [i for i in dec.run(ins.address + ins.size, uses[-1])
           if i.address <= uses[-1]]
    found = []
    for i in seq:
        rd, wr = gmt.reads_writes(i)
        if i.address in uses:
            if reg not in rd or reg in wr or i.mnemonic not in ("movaps", "addss", "subss"):
                return "displacement use at %X changed" % i.address
            found.append(i.address)
        elif reg in rd or reg in wr:
            return "other displacement use at %X" % i.address
    if tuple(found) != uses:
        return "missing displacement use"
    return gmt.xmm_dead_after(dec, seq[-1], reg)


def prove_imuln(dec, targets, ins, load_at):
    """None if `ins` is `div r32` whose divisor was loaded from the mode byte
    by `movzx r32, byte [mode]` at load_at, in straight-line code that nothing
    branches into and that writes the divisor nowhere else."""
    if ins.mnemonic != "div" or ins.operands[0].type != X.X86_OP_REG or \
            ins.operands[0].size != 4:
        return "imuln needs div r32"
    divisor = ins.operands[0].reg
    seq = dec.run(load_at, ins.address)
    if not seq or seq[0].address != load_at:
        return "cannot decode from %X" % load_at
    ld = seq[0]
    mem = next((op.mem for op in ld.operands if op.type == X.X86_OP_MEM), None)
    if ld.mnemonic != "movzx" or ld.operands[0].reg != divisor or mem is None or \
            mem.base != X.X86_REG_RIP or ld.address + ld.size + mem.disp != MODE_BYTE:
        return "%X is not movzx %s, byte [mode]" % (load_at, ins.reg_name(divisor))
    for i in seq[1:]:
        if i.address == ins.address:
            return None
        if i.address in targets:
            return "a branch target at %X between the load and the div" % i.address
        if i.mnemonic.startswith(("j", "call", "ret", "loop")):
            return "control transfer at %X between the load and the div" % i.address
        _r, written = i.regs_access()
        if gis.canon(ins, divisor) in {gis.canon(i, r) for r in written}:
            return "%X %s writes the divisor" % (i.address, i.mnemonic)
    return "the div is not reached from %X" % load_at


def main():
    img, secs, begins, sha = tr.load_image()
    if sha != AUDITED_MAIN_SHA1:
        raise RuntimeError("main.dll %s is not the audited build %s" % (sha, AUDITED_MAIN_SHA1))
    # the hand-read sites, and the enemies' clocks tools/find_actor_clocks.py proves
    import find_actor_clocks
    clock_rows = find_actor_clocks.sites(img, secs)
    manifest = MANIFEST + clock_rows
    # the enemies' other speed-paced steps, and the turn steps (the actor
    # group's hand-read rows, the imps' kick, pace nothing by the speed)
    clock_rvas = [m[2] for m in clock_rows]
    step_finder = find_actor_clocks.Steps(img, secs, clock_rvas)
    steps = find_actor_clocks.step_sites(img, secs, clock_rvas, step_finder)
    step_rvas = {m[2] for m in steps}
    manifest += steps
    # the enemies' motion: the moves by their speed, and the changes of the
    # velocities they move by (tools/find_actor_motion.py proves each)
    import find_actor_motion
    motion, mrows, _mrefused = find_actor_motion.census(img, secs, step_finder, clock_rows)
    motion_rvas = {r[0] for r in mrows}
    manifest += [("actor", kind, rva, text, None, reason) for rva, kind, text, reason in mrows]
    # the fps byte's half-second waits (tools/survey_flag_reads.py proves each)
    import survey_flag_reads
    flag_rows, flag_problems = survey_flag_reads.audit()
    manifest += survey_flag_reads.mulstore_rows(flag_rows, img)
    import survey_turn_steps
    trows, problems = survey_turn_steps.audit()
    if problems:
        for p in problems:
            print("TURN STEP PROBLEM " + p)
        raise RuntimeError("tools/survey_turn_steps.py finds %d problems; nothing written"
                           % len(problems))
    for rva, target, reg, blend, _raw in survey_turn_steps.selected(trows):
        row = next(r for r in trows if r["site"] == "%X" % rva)
        manifest.append(("steer", "callblend" if blend else "callscale", rva,
                         "call 0x%x" % target, (target, reg),
                         "turn step of %X in %X: %s x s%s; %s" % (
                             target, int(row["function"], 16), reg,
                             ", k -> 1 - (1 - k)^(1/N)" if blend else "", row["evidence"])))
    if any(m[0] == "turn" for m in manifest):
        # scaling the turn limit is right only if no caller compensated it already
        import survey_turn_limits
        _rows, problems = survey_turn_limits.audit()
        if problems:
            for p in problems:
                print("TURN LIMIT PROBLEM " + p)
            raise RuntimeError("tools/survey_turn_limits.py finds %d problems; nothing written"
                               % len(problems))
    if any(m[0] in ("mode", "repeat") for m in manifest):
        # F6: every read of the mode byte in one class, and the manifest's
        # mode/repeat sites exactly the ones the survey's F6 entries name
        import survey_mode_reads
        _rows, problems = survey_mode_reads.audit()
        problems += survey_mode_reads.manifest_problems(manifest)
        if problems:
            for p in problems:
                print("MODE READ PROBLEM " + p)
            raise RuntimeError("tools/survey_mode_reads.py finds %d problems; nothing written"
                               % len(problems))
    if any(m[0] == "flag" for m in manifest):
        # every read of the 60 fps flag and the fps byte in one class, and the
        # manifest's flag sites exactly the ones the survey names
        problems = flag_problems + survey_flag_reads.manifest_problems(manifest, flag_rows)
        if problems:
            for p in problems:
                print("FLAG READ PROBLEM " + p)
            raise RuntimeError("tools/survey_flag_reads.py finds %d problems; nothing written"
                               % len(problems))
    begins = sorted(begins)
    lo, hi = secs[".text"]
    starts, targets, switch, _tables = tr.global_pass(img, lo, hi)
    sources, leas = gmt.direct_sources(img, lo, hi)
    indirect = switch | gmt.code_pointers(img, secs, lo, hi, starts) | leas | \
        gmt.unwind_entries(img, secs)
    dec = tr.Decoder(img, starts)
    sources, targets = discard_proven_switch_data(dec, sources, targets, indirect)
    # imuln's straight-line proof: every way into code, without the data words
    # that only look like code addresses because they are unwind codes
    strict_targets = set(targets) | switch | leas | gmt.unwind_entries(img, secs) | \
        code_refs_outside_unwind(img, secs, lo, hi, starts)
    # An unwind entry proves reachability, but does not take the address for
    # an indirect call. Keep those separate when following void tail calls.
    gate_address_taken = switch | leas | code_refs_outside_unwind(img, secs, lo, hi, starts)
    dormant_actual_refs = leas | code_refs_outside_unwind(img, secs, lo, hi, starts) | \
        (unaligned_code_refs(img, secs, lo, hi, starts) - dormant_data_coincidences(img, secs))
    dormant_internal_switch = dormant_switch_destinations(dec, starts, sources,
                                                        dormant_actual_refs) | \
        dormant_internal_tables(dec, starts, _tables, lo, hi)
    dormant_refs = dormant_actual_refs | (switch - dormant_internal_switch)
    for dormant_lo, dormant_hi in DORMANT_DEBRIS:
        why = dead_code_problem(dec, starts, sources, dormant_refs,
                                dormant_lo, dormant_hi, DORMANT_DEBRIS)
        if why:
            raise RuntimeError("dormant debris %X-%X became reachable: %s" %
                               (dormant_lo, dormant_hi, why))
        print("dormant debris %X-%X: no execution entry" % (dormant_lo, dormant_hi))
    unwind_roots = unwind_function_roots(img, secs)
    targets |= indirect | set(begins) | tr.data_references(img, secs, lo, hi, starts)
    # Leaf functions need no pdata record. A direct call entry after a
    # return/padding is an independent entry, not the preceding unwind
    # function (which may have an unrelated vtable pointer). Imports and
    # external call targets are not entries in this image.
    gate_begins = set(begins)
    # 333DD0 is a leaf slot-18 model-deformation callback with no .pdata
    # record: do not assign its tail jump to the preceding initializer.
    leaf = [i for i in dec.run(0x333DD0, 0x333DD7) if i.address <= 0x333DD7]
    if [(i.address, i.mnemonic, i.op_str) for i in leaf] != [
            (0x333DD0, "add", "rcx, 0x1310"),
            (0x333DD7, "jmp", "0x4a74d0")]:
        raise RuntimeError("model-deformation leaf callback changed")
    if struct.unpack_from("<Q", img, 0x69A688)[0] != tr.BASE + 0x333DD0:
        raise RuntimeError("model-deformation slot-18 callback changed")
    gate_begins.add(0x333DD0)
    for entry, refs in sources.items():
        if not lo <= entry < hi or not starts[entry] or \
                not any(mn == "call" for _a, _s, mn in refs):
            continue
        phys = gmt.physical_predecessor(dec, starts, entry)
        if phys is not None and phys.mnemonic in tr.UNCOND | tr.PADDING:
            gate_begins.add(entry)
    gate_begins = sorted(gate_begins)
    iat = iat_names()
    begin_set = set(begins)
    protected = [r for r in gis.patched_ranges() if "world_anims" not in r[2]]
    import check_patch_sites as cps
    for a, raw, label in cps.turn_callers():
        protected.append((a, a + len(raw), label))
    for a, raw, label in cps.day_clock():
        protected.append((a, a + len(raw), label))
    own_literals = [(rva, rva + 8, "world_anims literal")
                    for _g, kind, rva, *_ in manifest if kind in ("lin", "sq", "blend")]

    own_calls = [(rva, rva + 5, "world_anims call")
                 for _g, kind, rva, *_ in manifest if kind in CALL_KINDS]
    fenced = protected + own_literals + own_calls
    # register counters that share one store (1C8D80's inc reaches the dec's
    # store by a jmp): each row's path proof lets the others' entries into the
    # store, and every one of them must pass its own proof
    store_entries = collections.defaultdict(list)
    for _g, kind, rva, _t, extra, _r in manifest:
        if kind in ("count", "count2") and isinstance(extra, tuple) and \
                len(extra) in (4, 5) and isinstance(extra[2], tuple):
            entry = gmt.counter_store_entry(dec, dec.run(rva, rva)[0], extra[1])
            if entry is not None:
                store_entries[extra[1]].append((rva, entry.address))
    rows, literals, detours, calls = [], [], [], []
    for group, kind, rva, text, extra, reason in manifest:
        row = dict(site="%X" % rva, group=group, kind=kind, instruction=text, reason=reason,
                   function="", status="refused", proof="", window="", stub="", temp="",
                   probe="")
        rows.append(row)
        if kind in CALL_KINDS:
            # a call's rel32 retargeted at its own stub: the call must be
            # `E8 rel32` to the target, and no other family may touch it
            target, reg = extra
            fn = gmt.containing_function(begins, rva)
            row["function"] = "%X" % fn if fn is not None else ""
            raw = bytes(img[rva:rva + 5])
            if raw[0] not in (0xE8, 0xE9) or                     rva + 5 + struct.unpack_from("<i", raw, 1)[0] != target:
                row["proof"] = "not `call %X`" % target
                continue
            if raw[0] == 0xE9 and kind == "callgate":
                # a tail jump hands the gate's `ret` the caller's caller
                row["proof"] = "a callgate needs a call, not a tail jump"
                continue
            if not starts[rva]:
                row["proof"] = "not an instruction start"
                continue
            if any(x in tr.RELOCATED for x in range(rva, rva + 5)):
                row["proof"] = "holds a base relocation"
                continue
            clash = [w for a, b, w in protected + own_literals if a < rva + 5 and rva < b]
            if clash:
                row["proof"] = "overlaps " + clash[0]
                continue
            if kind == "callgate":
                # "void": a call whose rax nothing reads, which the gate's
                # rax = 0 cannot change
                why = gmt.rax_unused_after_calls(dec, {target: [(rva, 5, "call")]}, target)[1]                     if reg == "void" else prove_callgate(dec, rva + 5)
                if why:
                    row["proof"] = why
                    continue
            elif reg not in ("xmm1", "xmm2", "xmm3"):
                row["proof"] = "scales %s, not a float argument register" % reg
                continue
            # a tail jump (E9) is retargeted the same way: the stub ends in a
            # jump to the target, and the stack holds what the jmp left there
            calls.append(dict(site=rva, kind=kind, group=group, target=target, reg=reg,
                              row=row, probe=None, counter=None, op=raw[0]))
            row.update(status="selected", proof="%s %X; rel32 retargeted (5 bytes, no window)"
                       % ("call" if raw[0] == 0xE8 else "tail jmp", target))
            continue
        fn = rva if kind in ("gatefn", "gate0") else gmt.containing_function(begins, rva)
        row["function"] = "%X" % fn if fn is not None else ""
        insns, idx = dec.around(rva, fn, rva) if fn is not None else (None, None)
        if insns is None:
            row["proof"] = "not a decoded instruction"
            continue
        ins = insns[idx]
        got = "%s %s" % (ins.mnemonic, ins.op_str)
        if got != text:
            row["proof"] = "instruction is %s" % got
            continue
        for a, b, what in protected:
            if a < rva + ins.size and rva < b:
                row["proof"] = "already patched by " + what
                break
        if row["proof"]:
            continue
        if kind in ("lin", "sq", "blend"):
            const_rva, want = extra
            mem = next((op.mem for op in ins.operands if op.type == X.X86_OP_MEM), None)
            if ins.size != 8 or mem is None or mem.base != X.X86_REG_RIP or ins.disp_offset != 4:
                row["proof"] = "not the 8-byte rip form"
                continue
            if ins.address + ins.size + mem.disp != const_rva:
                row["proof"] = "reads %X, not %X" % (ins.address + ins.size + mem.disp, const_rva)
                continue
            value = struct.unpack_from("<f", img, const_rva)[0]
            if struct.pack("<f", value) != struct.pack("<f", want):
                row["proof"] = "constant is %r, not %r" % (value, want)
                continue
            if kind == "blend" and not 0 < value < 1:
                row["proof"] = "a blend's factor must be in (0, 1), not %r" % value
                continue
            literals.append(dict(rva=rva, const=const_rva, kind=KIND[kind], group=group,
                                 orig=bytes(ins.bytes), row=row))
            row.update(status="selected", proof="%s = %g at %X" % (
                {"lin": "K*s", "sq": "K*s^2", "blend": "1-(1-K)^s"}[kind], value, const_rva))
            continue
        info = dict(site=rva, kind=kind, group=group, ins=ins, row=row, temp=None,
                    counter=None, probe=None, skip=b"", flags=0)
        if kind == "src":
            double = ins.mnemonic in ("addsd", "subsd")
            if ins.mnemonic not in gmt.OPCODE and not double:
                row["proof"] = "src needs addss, subss, mulss, addsd or subsd"
                continue
            if double:
                op = ins.operands[1]
                if op.type == X.X86_OP_REG:
                    if not ins.reg_name(op.reg).startswith("xmm") or op.reg == ins.operands[0].reg:
                        row["proof"] = "double src needs a distinct XMM source"
                        continue
                else:
                    if ins.size != 8 or op.type != X.X86_OP_MEM or \
                            op.mem.base != X.X86_REG_RIP or ins.disp_offset != 4:
                        row["proof"] = "double src needs an XMM source or the 8-byte RIP qword form"
                        continue
                    const_rva = ins.address + ins.size + op.mem.disp
                    value = struct.unpack_from("<d", img, const_rva)[0]
                    if not math.isfinite(value) or value == 0:
                        row["proof"] = "double source must be a finite nonzero double"
                        continue
            last = None
            for temp in VOLATILE_TEMPS:
                if double and any(o.type == X.X86_OP_REG and ins.reg_name(o.reg) == temp
                                  for o in ins.operands):
                    continue
                last = gmt.xmm_dead_after(dec, ins, temp)
                if last is None:
                    info["temp"] = temp
                    break
            if info["temp"] is None:
                row["proof"] = last
                continue
            if ins.operands[1].type == X.X86_OP_MEM and not double and \
                    ins.operands[1].mem.base != X.X86_REG_RIP:
                _b, why = gmt.reencode_load(ins, info["temp"])
                if why:
                    row["proof"] = why
                    continue
            row["temp"] = info["temp"]
            row["proof"] = ("%s dead after the site on every path; double literal %g at %X" %
                            (info["temp"], value, const_rva) if double and op.type == X.X86_OP_MEM else
                            "%s dead after the site on every path" % info["temp"])
        elif kind in ("srcblend", "srcroot"):
            ops = ins.operands
            allowed = ("mulss", "divss") if kind == "srcblend" else ("mulss",)
            if ins.mnemonic not in allowed or ops[0].type != X.X86_OP_REG or \
                    not ins.reg_name(ops[0].reg).startswith("xmm"):
                row["proof"] = "%s needs %s xmm, src" % (kind, "/".join(allowed))
                continue
            last = None
            for temp in VOLATILE_TEMPS:
                if temp == ins.reg_name(ops[0].reg):
                    continue
                last = gmt.xmm_dead_after(dec, ins, temp)
                if last is None:
                    info["temp"] = temp
                    break
            if info["temp"] is None:
                row["proof"] = last or "no dead temporary"
                continue
            if ops[1].type == X.X86_OP_MEM and ops[1].mem.base != X.X86_REG_RIP:
                _b, why = gmt.reencode_load(ins, info["temp"])
                if why:
                    row["proof"] = why
                    continue
            why = flags_dead_after(dec, rva + ins.size)
            if why:
                row["proof"] = why
                continue
            row["temp"] = info["temp"]
            row["proof"] = "%s dead after the site on every path; flags dead after" % \
                info["temp"]
        elif kind == "srcx":
            ops = ins.operands
            if ins.mnemonic not in ("addss", "subss", "comiss", "ucomiss") or \
                    ops[0].type != X.X86_OP_REG or not ins.reg_name(ops[0].reg).startswith("xmm"):
                row["proof"] = "srcx needs addss/subss/comiss/ucomiss xmm, x"
                continue
            if ops[1].type == X.X86_OP_REG and ops[1].reg == ops[0].reg:
                row["proof"] = "srcx needs a source other than the destination"
                continue
            row["proof"] = ("xmmD / s, op, * s: exact for s = 1/N a power of two; no flags "
                            "touched, no register borrowed")
        elif rva in motion_rvas:
            # the motion finder proves what the value is (a move's speed, a
            # velocity's change or factor, placed by stock's order); the checks
            # here are the stub's own: a factor passed straight to its multiply,
            # a countlast's flags
            got_kind, why = motion.prove(rva)
            if not why and got_kind != kind:
                why = "the motion finder says %s" % got_kind
            reg = ins.reg_name(ins.operands[0].reg) if ins.operands and \
                ins.operands[0].type == X.X86_OP_REG else ""
            if not why and not reg.startswith("xmm"):
                why = "%s needs an xmm destination" % kind
            if not why and kind in ("ufirst", "ulast"):
                why = factor_consumer(dec, ins, reg, iat)
            if not why and kind == "countlast":
                if ins.mnemonic != "mulss":
                    why = "countlast needs mulss xmm, m32"
                else:
                    flags, fwhy = gis.flag_policy(dec, ins, 0)
                    why = fwhy if flags is None else None
            if why:
                row["proof"] = why
                continue
            row["proof"] = "tools/find_actor_motion.py: on every path only %s" % (
                "a move by the speed" if kind == "step" else "a velocity's change" if
                kind[0] == "z" else "a velocity's factor" if kind[0] == "u" else
                "a velocity lane's factor")
        elif kind in ("zfirst", "ufirst") and isinstance(extra, tuple) and extra[0] == "scale":
            why = prove_scale_arg(dec, ins, extra[1], iat)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "only ScaleXYZ's scale at %X (and a zero test)" % extra[1]
        elif kind == "step" or (kind == "srcx" and rva in step_rvas):
            got_kind, _d, _st, why = step_finder.prove(rva)
            if why or got_kind != kind:
                row["proof"] = why or "the step finder says %s" % got_kind
                continue
            row["proof"] = ("the speed read here is, on every path, only one field's step "
                            "(find_actor_clocks.Steps)")
            if kind == "srcx":
                row["proof"] += "; xmmD / s, op, * s"
        elif kind == "dst" and isinstance(extra, tuple) and extra[0] == "slowmo":
            # the game's slow-motion factor (23AD90: 0.25 or 1.0) kept in a
            # callee-saved register as a function's dt; the manifest has read
            # every reader of the register in the function (each a step)
            why = prove_slowmo_copy(dec, ins, extra[1])
            if why:
                row["proof"] = why
                continue
            row["proof"] = "a callee-saved copy of 23AD90's return (the call at %X), the " \
                "function's per-tick dt" % extra[1]
        elif kind == "dst" and isinstance(extra, tuple) and extra[0] == "scale":
            # the step is the float factor of a vector product that moves
            # something (the manifest says what); scaled right after its load
            why = prove_scale_arg(dec, ins, extra[1], iat, (CVEC_SCALE, CVEC_TIMES))
            if why:
                row["proof"] = why
                continue
            row["proof"] = "only the factor of the vector product at %X (and a zero " \
                "test)" % extra[1]
        elif kind == "dstn":
            why = prove_paced_store(dec, ins, extra)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "only stored, in the loop of the wait at %X that task_waits.h " \
                "runs once a stock tick" % extra
        elif kind in ("dst", "zfirst", "zlast"):
            reg = ins.reg_name(ins.operands[0].reg)
            why = gmt.scalar_step_consumer(dec, ins, reg)
            # a change subtracted from (or added to) another register: zeroed,
            # it leaves that register as it was (utbd's and wp20's spring pull)
            if why and kind in ("dst", "zfirst", "zlast") and                     not step_source_consumer(dec, ins, reg):
                why = None
                row["proof"] = "the step's next reader adds or subtracts it into another " \
                    "register, and %s is dead after" % reg
            if why and kind == "dst" and not triple_rise_consumer(dec, ins, reg):
                why = None
                row["proof"] = "one scaled step feeds three guarded D20/D24/D28 additions"
            if why and kind == "dst" and not shared_animal_displacement(dec, ins, reg):
                why = None
                row["proof"] = "one scaled step feeds actor height and linked world offsets"
            if why:
                row["proof"] = why
                continue
            row["proof"] = row["proof"] or "the step's next reader is its accumulation"
        elif kind in ("ufirst", "ulast"):
            why = factor_consumer(dec, ins, ins.reg_name(ins.operands[0].reg), iat)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "the factor's next reader multiplies by it"
        elif kind == "argscale":
            why = prove_argscale(dec, ins)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "the limit's copy in %s is only copied out, then restored" % \
                ins.reg_name(ins.operands[0].reg)
        elif kind == "scaledadd":
            tail = ins.mnemonic == "jmp"
            if (import_tail(ins, iat) if tail else import_call(ins, iat)) != CVEC_ADD:
                row["proof"] = "not a call or import tail-jump to cVec::operator+="
                continue
            info["tail"] = tail
            row["proof"] = ("tail-jumps to" if tail else "calls") + " cVec::operator+="
        elif kind == "immstore":
            ops, raw = ins.operands, bytes(ins.bytes)
            if ins.mnemonic != "mov" or len(ops) != 2 or \
                    ops[0].type != X.X86_OP_MEM or ops[0].size != 4 or \
                    ops[1].type != X.X86_OP_IMM or ins.imm_size != 4 or \
                    ins.imm_offset + 4 != ins.size:
                row["proof"] = "immstore needs mov m32, imm32"
                continue
            if ins.modrm_offset != 1 or raw[0] != 0xC7 or raw[1] & 0x38:
                row["proof"] = "immstore needs the unprefixed C7 /0 encoding"
                continue
            if ops[0].mem.base in (0, X.X86_REG_RIP) or ops[0].mem.index:
                row["proof"] = "immstore needs one non-RIP base register and no index"
                continue
            value = struct.unpack_from("<f", raw, ins.imm_offset)[0]
            if not math.isfinite(value):
                row["proof"] = "immstore's float immediate is not finite"
                continue
            last = None
            for temp in VOLATILE_TEMPS:
                last = gmt.xmm_dead_after(dec, ins, temp)
                if last is None:
                    info["temp"] = temp
                    break
            if info["temp"] is None:
                row["proof"] = last or "no dead temporary"
                continue
            row["temp"] = info["temp"]
            row["proof"] = ("immediate bits are finite float %g; %s dead after the store "
                            "on every path" % (value, info["temp"]))
        elif kind == "pre":
            ops = ins.operands
            if ins.mnemonic not in ("addss", "comiss", "ucomiss") or \
                    ops[0].type != X.X86_OP_REG or \
                    not ins.reg_name(ops[0].reg).startswith("xmm"):
                row["proof"] = "pre needs addss/comiss/ucomiss xmm, x"
                continue
            row["proof"] = ("addss is commutative: the step in %s is scaled first" if
                            ins.mnemonic == "addss" else
                            "the per-tick comparison limit in %s is scaled first") % \
                ins.reg_name(ops[0].reg)
        elif kind in ("root", "blendr"):
            ops = ins.operands
            factor_ops = ("movaps", "movss", "addss", "divss") + (("minss",) if kind == "blendr" else ())
            if ins.mnemonic not in factor_ops or ops[0].type != X.X86_OP_REG                     or not ins.reg_name(ops[0].reg).startswith("xmm"):
                row["proof"] = "%s needs %s into an xmm register" % (kind, "/".join(factor_ops))
                continue
            if kind == "blendr":
                # 1 - k and its root in a volatile register nothing reads after
                last = None
                for temp in VOLATILE_TEMPS:
                    if temp == ins.reg_name(ops[0].reg):
                        continue
                    last = gmt.xmm_dead_after(dec, ins, temp)
                    if last is None:
                        info["temp"] = temp
                        break
                if info["temp"] is None:
                    row["proof"] = last or "no dead temporary"
                    continue
                row["temp"] = info["temp"]
        elif kind == "dstarg":
            why = prove_dstarg(dec, ins, extra, iat)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "untouched until cVec(x, y, z, w) at %X" % extra
        elif kind == "floor1":
            base, disp, block_lo = extra
            why = prove_join(dec, starts, sources, indirect, rva, block_lo)
            if not why:
                why = flags_dead_after(dec, rva)
            if not why:
                for temp in VOLATILE_TEMPS:
                    if gmt.xmm_dead_after(dec, ins, temp) is None:
                        info["temp"] = temp
                        break
                else:
                    why = "no dead temporary"
            if why:
                row["proof"] = why
                continue
            row["temp"] = info["temp"]
            row["proof"] = "a join of the reload block (%X on); flags and %s dead" % (
                block_lo, info["temp"])
        elif kind == "countlast":
            if ins.operands[0].type != X.X86_OP_REG or not (
                    ins.mnemonic in ("mulss", "divss") or
                    (ins.mnemonic in ("addss", "subss") and ins.operands[1].type in
                     (X.X86_OP_MEM, X.X86_OP_REG))):
                row["proof"] = ("countlast needs mulss/divss xmm, x (skipped: x 1) or "
                                "addss/subss xmm, x (skipped: + 0)")
                continue
            flags, why = gis.flag_policy(dec, ins, 0)
            if flags is None:
                row["proof"] = why
                continue
            row["proof"] = "%s: skipped, the rate is kept; %s" % (
                "a factor" if ins.mnemonic in ("mulss", "divss") else "a change", why)
        elif kind == "count" and extra == "factor":
            if ins.mnemonic != "mulss" or ins.operands[0].type != X.X86_OP_REG or \
                    ins.operands[1].type != X.X86_OP_MEM:
                row["proof"] = "a factor step needs mulss xmm, m32"
                continue
            flags, why = gis.flag_policy(dec, ins, 0)
            if flags is None:
                row["proof"] = why
                continue
            row["proof"] = "a pre-move factor: kept on the first stock-period tick; " + why
        elif kind == "count" and extra == "float":
            if ins.mnemonic not in ("addss", "subss") or \
                    ins.operands[0].type != X.X86_OP_REG or \
                    not ins.reg_name(ins.operands[0].reg).startswith("xmm") or \
                    ins.operands[1].type not in (X.X86_OP_MEM, X.X86_OP_REG):
                row["proof"] = "a float step needs addss/subss xmm, src"
                continue
            flags, why = gis.flag_policy(dec, ins, 0)
            if flags is None:
                row["proof"] = why
                continue
            row["proof"] = "a float step: skipped, it adds nothing; " + why
        elif kind in ("notyet", "notyetneg", "notyetb"):
            why = prove_notyet(dec, ins, extra, negative=kind == "notyetneg",
                               below=kind == "notyetb")
            if why:
                row["proof"] = why
                continue
            if ins.mnemonic == "and":
                # The instruction also writes its register. Keep that value
                # on a held tick, changing only the following branch's flags.
                info["skip"] = bytes(ins.bytes)
            row["proof"] = ("its flags' one branch goes to %X with ZF=OF=0, SF=%d" % (
                extra, int(kind == "notyetneg"))) if kind != "notyetb" else \
                "its flags' one branch goes to %X with ZF=0, CF=1" % extra
        elif kind == "smode":
            mem = next((op.mem for op in ins.operands if op.type == X.X86_OP_MEM), None)
            if ins.mnemonic != "sub" or ins.operands[0].type != X.X86_OP_REG or \
                    ins.operands[0].size != 1 or mem is None or mem.base != X.X86_REG_RIP or \
                    ins.address + ins.size + mem.disp != MODE_BYTE:
                row["proof"] = "smode needs sub r8, byte [the mode byte]"
                continue
            flags, why = gis.flag_policy(dec, ins, 0)
            if flags != 0:
                row["proof"] = why or "its flags are read"
                continue
            row["proof"] = "subtracts the mode byte; " + why
        elif kind == "mulstore":
            why = prove_mulstore(dec, strict_targets, ins, extra)
            if not why:
                why = flags_dead_after(dec, rva + ins.size)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "stores the fps byte read at %X, halved: the value times N, the " \
                "register kept; flags dead after" % extra
        elif kind == "mulflag":
            why = prove_mulflag(dec, strict_targets, ins, extra)
            if not why:
                why = flags_dead_after(dec, rva + ins.size)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "a factor 1 << flag built from %X and the flag read at %X; flags " \
                "dead after" % extra
        elif kind == "imuln":
            why = prove_imuln(dec, strict_targets, ins, extra)
            if not why:
                why = flags_dead_after(dec, rva + ins.size)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "divides by the mode byte loaded at %X; flags dead after" % extra
        elif kind in ("count", "count2"):
            step = ins
            if extra == "up":
                # The quotient calculation sits between this field's load,
                # its +1 in r8w, and the store. Gate the store while retaining
                # the old count for the effect's comparison.
                path = [i for i in dec.run(0x2F7000, 0x2F701C)
                        if i.address <= 0x2F701C]
                if rva != 0x2F701C or not path or \
                        path[0].op_str != "r8d, word ptr [rbx + 0xe3c]" or \
                        not any(i.address == 0x2F7013 and i.mnemonic == "inc" and
                                i.op_str == "r8w" for i in path) or \
                        path[-1].op_str != "word ptr [rbx + 0xe3c], r8w":
                    row["proof"] = "+E3C quotient/count path changed"
                    continue
            if extra == "phase5":
                # cOptionCalibration keeps BX across the imported sine call
                # (Windows x64 callee-saved). The call receives only XMM0,
                # and the +A2 field is not passed to it. A mov eax, 360 sits
                # between the add and store, hence the normal immediate
                # register-store proof cannot cover this one path.
                path = [i for i in dec.run(0x147747, 0x147776)
                        if i.address <= 0x147776]
                expect = (0x147747, 0x14774E, 0x147751, 0x147755,
                          0x147758, 0x147760, 0x147765, 0x14776D,
                          0x147771, 0x147776)
                if rva != 0x14776D or tuple(i.address for i in path) != expect or \
                        path[0].mnemonic != "movzx" or \
                        path[0].op_str != "ebx, word ptr [rdi + 0xa2]" or \
                        path[5].mnemonic != "call" or \
                        path[5].operands[0].imm != 0x65D74E or \
                        path[7].mnemonic != "add" or path[7].op_str != "bx, 5" or \
                        path[8].mnemonic != "mov" or path[8].op_str != "eax, 0x168" or \
                        path[9].mnemonic != "mov" or \
                        path[9].op_str != "word ptr [rdi + 0xa2], bx":
                    row["proof"] = "calibration phase path changed"
                    continue
            elif extra in ("title", "remain"):
                paths = {
                    "title": (0x4022B2, 0x4022AE, 0x4022BA,
                              (0x4022AE, 0x4022B2, 0x4022B6, 0x4022BA),
                              "eax, word ptr [rbx + 0x68]",
                              "word ptr [rbx + 0x68], ax"),
                    "remain": (0x405243, 0x405236, 0x40524C,
                               (0x405236, 0x40523A, 0x40523D, 0x40523F,
                                0x405243, 0x405247, 0x40524C),
                               "ecx, word ptr [rbx + 0x68]",
                               "word ptr [rbx + 0x68], cx"),
                }
                at, load_at, store_at, addresses, load_text, store_text = paths[extra]
                path = [i for i in dec.run(load_at, store_at)
                        if i.address <= store_at]
                if rva != at or tuple(i.address for i in path) != addresses or \
                        path[0].mnemonic != "movzx" or path[0].op_str != load_text or \
                        path[-1].mnemonic != "mov" or path[-1].op_str != store_text or \
                        any(i.address in strict_targets for i in path[1:]):
                    row["proof"] = "%s counter path changed" % extra
                    continue
            elif extra in (None, "down", "up") or \
                    isinstance(extra, tuple) and extra[0] == "block":
                if step.operands[0].type != X.X86_OP_MEM:
                    row["proof"] = "memory counter expected"
                    continue
            elif extra == "reg":
                # a loop's pass count kept in a register (`sub r14, 1; jne`
                # around a wait(1)): skipped between stock ticks, the loop
                # runs one pass a tick and ends after its stock count of
                # stock ticks
                if step.operands[0].type != X.X86_OP_REG or \
                        step.mnemonic not in ("inc", "dec", "add", "sub"):
                    row["proof"] = "a register counter needs inc/dec/add/sub r"
                    continue
            else:
                # A fifth item supplies an audited direction when a register
                # subtrahend carries the positive unit (as memory steps use
                # "down"). The first four items still prove the complete
                # load/step/store path and register identity.
                counter_path = extra[:4] if isinstance(extra, tuple) and len(extra) == 5 else extra
                if isinstance(extra, tuple) and len(extra) == 5 and extra[4] not in (-1, 1):
                    row["proof"] = "explicit register-counter direction must be -1 or 1"
                    continue
                joins = {e for r, e in store_entries.get(counter_path[1], ()) if r != rva}
                why = gmt.prove_register_counter(dec, starts, sources, indirect, step, counter_path,
                                                 joins)
                if why:
                    row["proof"] = why
                    continue
            # "down": the manifest says why the subtrahend is positive
            delta = (extra[4] if isinstance(extra, tuple) and len(extra) == 5 else
                     -1 if extra == "down" else 1 if extra == "up" else
                     {"inc": 1, "dec": -1}.get(step.mnemonic, 0))
            ops = step.operands
            if not delta and step.mnemonic in ("add", "sub") and len(ops) == 2 and \
                    ops[1].type == X.X86_OP_IMM:
                # `sub r, 1` and `add r, -1` count down as dec does (a skipped
                # tick reads "not finished"); `add r, 1` counts up
                bits = 8 * ops[0].size
                v = ops[1].imm & ((1 << bits) - 1)
                v = v - (1 << bits) if v >> (bits - 1) else v
                v = -v if step.mnemonic == "sub" else v
                delta = v if v in (1, -1) else 0
                if extra == "reg" and v:
                    # a register loop counter or fade stepping by more than
                    # one: its direction is what a skipped tick's "not
                    # finished" flags stand for
                    delta = 1 if v > 0 else -1
            flags, why = gis.flag_policy(dec, step, delta, cmov=True)
            if flags is None:
                row["proof"] = why
                continue
            info["flags"] = flags
            row["proof"] = why + ("; calibration +A2 phase path" if extra == "phase5" else
                                  "; %s counter path" % extra if extra in ("title", "remain") else
                                  "; complete counter block" if isinstance(extra, tuple) and extra[0] == "block" else
                                  "" if extra in (None, "down", "up") else
                                  "; a register loop counter" if extra == "reg" else
                                  "; load %X and store %X one field" % extra[:2])
        elif kind == "gate0":
            why = prove_gate0(dec, starts, begin_set, rva, extra)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "entry (a vtable slot); its no-op path %X returns al = 0" % extra
        elif kind == "gatefn":
            why = gatefn_entry(dec, starts, sources, rva)
            if why:
                row["proof"] = why
                continue
            callers, why = gatefn_callers(dec, starts, sources, indirect, rva, gate_begins,
                                          gate_address_taken, unwind_roots)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "entry; callers %s ignore rax" % ", ".join("%X" % c for c in callers)
        if kind in ("srcblend", "count") and isinstance(extra, tuple) and extra[0] == "block":
            _tag, block_lo, block_hi = extra
            a = next((j for j, i in enumerate(insns) if i.address == block_lo), None)
            b = next((j for j, i in enumerate(insns) if i.address + i.size == block_hi), None)
            why = "block bounds are not instructions"
            if a is not None and b is not None and a <= idx <= b:
                why = closed_window_problem(insns[a:b + 1], sources, gate_address_taken,
                                            begin_set, fenced)
                if not why:
                    info["block"] = (block_lo, block_hi)
                    row["proof"] += "; complete forward branch block, no interior entry"
        elif kind in ("gatefn", "gate0"):
            a, b = idx, idx
            while insns[b].address + insns[b].size - insns[a].address < 5:
                b += 1
            why = tr.window_problem(insns[a:b + 1], targets - {rva}, fenced)
        elif kind == "scaledadd":
            # the call is replaced, not relocated: its window is itself
            a = b = idx
            why = None
            for pa, pb, what in fenced:
                if pa < rva + ins.size and rva < pb:
                    why = "overlaps " + what
            if any(x in tr.RELOCATED for x in range(rva, rva + ins.size)):
                why = "holds a base relocation"
        elif kind in ("pre", "floor1"):
            # the site is a join: it must open the window
            a, b = idx, idx
            while insns[b].address + insns[b].size - insns[a].address < 5:
                b += 1
            why = tr.window_problem(insns[a:b + 1], targets - {rva}, fenced)
        else:
            # imuln's windows (new in F6) leave out the words inside unwind
            # records that only look like code addresses; the older kinds keep
            # the windows they were verified with in the game
            a, b, why = tr.find_window(
                insns, idx, strict_targets | set(begins) if kind in ("imuln", "mulflag",
                                                                      "mulstore", "immstore")
                else targets,
                fenced)
        if why:
            row["proof"] += "; window: " + why
            continue
        run = insns[a:b + 1]
        if kind in ("root", "blendr"):
            # the chain clobbers the flags right after the copy: nothing from
            # there on (the rest of the window included) may read them
            why = flags_dead_after(dec, rva + ins.size)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "flags dead after the copy (%X on)" % (rva + ins.size)
            if kind == "blendr":
                row["proof"] += "; %s dead after it" % info["temp"]
        info.update(run=run, lo=run[0].address, hi=run[-1].address + run[-1].size)
        detours.append(info)
        row["status"] = "selected"

    windows = []
    for d in sorted(detours, key=lambda d: (d["lo"], d["hi"])):
        if windows and d["lo"] < windows[-1]["hi"]:
            w = windows[-1]
            merged = {i.address: i for i in w["run"] + d["run"]}
            run = [merged[x] for x in sorted(merged)]
            block = w.get("block") or d.get("block")
            if block:
                why = closed_window_problem(run, sources, gate_address_taken, begin_set, fenced)
                if block != (run[0].address, run[-1].address + run[-1].size):
                    why = "overlap changes the declared branch block"
            else:
                why = tr.window_problem(run, targets, fenced)
            if why or any(x.address + x.size != y.address for x, y in zip(run, run[1:])):
                raise RuntimeError("cannot merge windows at %X: %s" % (d["lo"], why))
            w.update(hi=max(w["hi"], d["hi"]), run=run, block=block)
            w["sites"].append(d)
        else:
            windows.append(dict(lo=d["lo"], hi=d["hi"], run=d["run"], sites=[d], block=d.get("block")))
    counters = [d for w in windows for d in w["sites"] if d["kind"] in COUNTED] + \
        [d for d in calls if d["kind"] in COUNTED]
    sites_all = [d for w in windows for d in w["sites"]] + calls
    # literals of one constant, kind and group hold the same value at every N
    # (the runtime and the verifier fill each from its constant): one slot
    slot_of = {}
    for l in literals:
        slot_of.setdefault((l["const"], l["kind"], l["group"]),
                           LITERAL_OFFSET + 4 * len(slot_of))
    if len(counters) > MAX_COUNTERS or len(slot_of) > MAX_LITERALS or \
            len(sites_all) > MAX_PROBES:
        raise RuntimeError("pool layout overflow")
    for n, d in enumerate(counters):
        d["counter"] = n
    for n, d in enumerate(sorted(sites_all, key=lambda d: d["site"])):
        d["probe"] = n

    pool = tr.Pool(CODE_OFFSET)
    orig = bytearray()
    win_rows, site_rows = [], []
    for wi, w in enumerate(windows):
        stub = pool.here()
        orig_off = len(orig)
        orig += b"".join(bytes(i.bytes) for i in w["run"])
        by_at = {d["site"]: d for d in w["sites"]}
        dead = False
        block_labels, block_branches = {}, []
        for i in w["run"]:
            if dead:
                continue
            block_labels[i.address] = pool.here()
            d = by_at.get(i.address)
            if w.get("block") and tr.is_rel_branch(i) and w["lo"] <= i.operands[0].imm < w["hi"]:
                if d is not None:
                    raise RuntimeError("a block's branch cannot itself be a patch site")
                opcode = bytes(i.bytes)
                prefix = b"\xE9" if i.mnemonic == "jmp" else \
                    b"\x0F" + bytes([0x80 | (opcode[0] & 15)]) if len(opcode) == 2 else opcode[:2]
                pool.emit(prefix)
                field = len(pool.code)
                pool.emit(b"\0" * 4)
                block_branches.append((field, i.operands[0].imm))
            elif d is None:
                tr.emit_relocated(pool, i, None)
            elif d["kind"] in ("gatefn", "gate0"):
                emit_fn_gate(pool, d["counter"], d["group"], ret0=d["kind"] == "gate0")
                emit_probe(pool, d["probe"])
                tr.emit_relocated(pool, i, None)
            elif d["kind"] in ("count", "countlast", "count2", "notyet", "notyetneg", "notyetb",
                               "smode"):
                emit_probe(pool, d["probe"])
                g = d["group"]
                emit_count_gate(pool, i, d["skip"], d["flags"], d["counter"], g,
                                last=d["kind"] == "countlast",
                                mask=group_mask2(g) if d["kind"] == "count2" else None,
                                emit_step=(lambda p, i=i, g=g: emit_smode_step(p, i, g))
                                if d["kind"] == "smode" else None,
                                flag_bytes=NOT_YET_FLAGS if d["kind"] == "notyet" else
                                NOT_YET_NEG_FLAGS if d["kind"] == "notyetneg" else
                                NOT_YET_BELOW_FLAGS if d["kind"] == "notyetb" else None)
            elif d["kind"] == "imuln":
                emit_probe(pool, d["probe"])
                emit_imuln(pool, i, d["group"])
            elif d["kind"] == "mulflag":
                emit_probe(pool, d["probe"])
                emit_mulflag(pool, i, d["group"])
            elif d["kind"] == "mulstore":
                emit_probe(pool, d["probe"])
                emit_mulstore(pool, i, d["group"])
            else:
                emit_probe(pool, d["probe"])
                if d["kind"] == "src":
                    emit_src(pool, i, d["temp"], d["group"])
                elif d["kind"] == "srcx":
                    emit_srcx(pool, i, d["group"])
                elif d["kind"] in ("dst", "step"):
                    tr.emit_relocated(pool, i, None)
                    emit_mulss_scale(pool, i.reg_name(i.operands[0].reg), d["group"])
                elif d["kind"] == "dstn":
                    tr.emit_relocated(pool, i, None)
                    emit_divss_scale(pool, i.reg_name(i.operands[0].reg), d["group"])
                elif d["kind"] == "pre":
                    emit_mulss_scale(pool, i.reg_name(i.operands[0].reg), d["group"])
                    tr.emit_relocated(pool, i, None)
                elif d["kind"] == "root":
                    emit_root(pool, i, d["group"])
                elif d["kind"] == "blendr":
                    emit_blendr(pool, i, d["temp"], d["group"])
                elif d["kind"] == "srcblend":
                    emit_srcblend(pool, i, d["temp"], d["group"])
                elif d["kind"] == "srcroot":
                    emit_srcroot(pool, i, d["temp"], d["group"])
                elif d["kind"] == "scaledadd":
                    emit_scaledadd(pool, d["group"], d.get("tail", False))
                elif d["kind"] == "immstore":
                    emit_immstore(pool, i, d["temp"], d["group"])
                elif d["kind"] == "floor1":
                    base, disp, _lo = next(m[4] for m in manifest if m[2] == d["site"])
                    emit_floor1(pool, i, d["group"], base, disp, d["temp"])
                elif d["kind"] in ("zfirst", "zlast", "ufirst", "ulast"):
                    emit_phase_keep(pool, i, d["group"], last=d["kind"].endswith("last"),
                                    unit=d["kind"][0] == "u")
                elif d["kind"] in ("dstarg", "argscale"):
                    tr.emit_relocated(pool, i, None)
                    emit_mulss_scale(pool, i.reg_name(i.operands[0].reg), d["group"])
            if i.mnemonic in tr.UNCOND and not w.get("block"):
                dead = True
        for field, target in block_branches:
            struct.pack_into("<i", pool.code, field,
                             block_labels[target] - (pool.code_off + field + 4))
        if not dead:
            pool.game_rel32(b"\xE9", w["hi"])
        win_rows.append((w["lo"], stub, orig_off, w["hi"] - w["lo"]))
        for d in w["sites"]:
            d["row"].update(window="%X" % w["lo"], stub="%X" % stub, probe="%d" % d["probe"])
            temp = gmt.xmm_index(d["temp"]) if d["temp"] else 0xFF
            site_rows.append((d["site"], KIND[d["kind"]], GROUPS.index(d["group"]), wi, temp,
                              0xFFFF if d["counter"] is None else d["counter"], d["probe"],
                              HEADLINE.get(d["site"], 0 if d["group"] == "actor" else 2)))
        while pool.here() % 16:
            pool.emit(b"\xCC")
    # the call stubs: each counts its pass, scales the limit and jumps on
    call_rows = []
    for ci, d in enumerate(sorted(calls, key=lambda d: d["site"])):
        stub = pool.here()
        if d["kind"] == "callgate":
            emit_fn_gate(pool, d["counter"], d["group"], ret0=True)
            emit_probe(pool, d["probe"])
        else:
            emit_probe(pool, d["probe"])
            emit_mulss_scale(pool, d["reg"], d["group"])
            if d["kind"] == "callblend":
                emit_blend(pool, d["group"])
        pool.game_rel32(b"\xE9", d["target"])
        call_rows.append((d["site"], stub, d["target"]))
        d["row"].update(window="call %d" % ci, stub="%X" % stub, probe="%d" % d["probe"])
        site_rows.append((d["site"], KIND[d["kind"]], GROUPS.index(d["group"]), ci, 0xFF,
                          0xFFFF if d["counter"] is None else d["counter"], d["probe"], 0))
        while pool.here() % 16:
            pool.emit(b"\xCC")
    lit_rows = []
    for l in literals:
        slot = slot_of[(l["const"], l["kind"], l["group"])]
        lit_rows.append((l["rva"], l["const"], slot, l["kind"], GROUPS.index(l["group"])))
        l["row"]["window"] = "slot %X" % slot

    refused = [r for r in rows if r["status"] != "selected"]
    if refused:
        for r in refused:
            print("REFUSED %s %s: %s" % (r["site"], r["kind"], r["proof"]))
        raise RuntimeError("%d manifest site(s) failed their proof; nothing written" % len(refused))

    lines = ["// Generated by tools/gen_world_anims.py -- do not edit.",
             "// World animations, first set: every site, its proof and its reason are in",
             "// docs/animation/world_anims.csv.",
             "#pragma once", "#include <cstdint>", "",
             '#define WORLD_ANIMS_MAIN_SHA1 "%s"' % sha,
             "static const uint32_t kWorldFrameCounterRva = 0x%X;" % tr.FRAME_COUNTER,
             "static const uint32_t kWorldGroupStride = %d;  // group g: uint8 mask at [g*8], "
             "mask << 1 at [g*8+1], stock mode at [g*8+2], float s = 1/N at [g*8+4]" %
             GROUP_STRIDE,
             "static const uint32_t kWorldZeroOffset = 0x%X;  // float 0.0, then 1.0" %
             ZERO_OFFSET,
             "static const uint32_t kWorldIntNOffset = 0x%X;  // uint32 N per group" %
             INTN_OFFSET,
             "static const uint32_t kWorldCounterOffset = 0x%X;  // {ticks, counted, last tick, "
             "passes}" % COUNTER_OFFSET,
             "static const uint32_t kWorldCounterStride = %d;" % SLOT,
             "static const uint32_t kWorldProbeOffset = 0x%X;  // uint32 passes per site" %
             PROBE_OFFSET,
             "static const uint32_t kWorldCodeOffset = 0x%X;" % CODE_OFFSET,
             "static const uint32_t kWorldPoolSize = 0x%X;" % pool.here(),
             "static const int kWorldGroups = %d;" % len(GROUPS),
             "static const char* const kWorldGroupName[] = {%s};" %
             ", ".join('"%s"' % g for g in GROUPS),
             "// site kinds: 0 lin K*s, 1 sq K*s^2, 2 scaled source, 3 scaled result,",
             "// 4 scaled destination first, 5 root f^(1/N), 6 function run on stock ticks only,",
             "// 7 counter skipped between stock ticks, 8 function run on stock ticks only that",
             "// returns 0 between them, 9 scaled constructor argument, 10/11 a rate's change",
             "// kept on the first/last tick of each stock period and zeroed on the others,",
             "// 12/13 a rate's factor kept there and 1.0 on the others, 14 a factor applied",
             "// on the last tick only, 15 a reloaded countdown raised to 1.0 while N > 1,",
             "// 16 cVec::operator+= replaced by dst.xyz += s * src.xyz, 17 a copied per-tick",
             "// limit scaled, 18 a counter gated on the frame counter's bits 1 and up, 19 a",
             "// countdown's test read as not yet between stock ticks, 20 a counter losing",
             "// the stock context's mode on stock ticks, 21 a duration n / mode times N,",
             "// 22 a scaled source applied as (xmmD / s op src) * s, with no register borrowed,",
             "// 23 an enemy's speed scaled as read (a step's only factor of time), 24 a call",
             "// retargeted at a stub that scales its limit register, 25 the same, and the",
             "// clamped approach's per-tick blend k made 1 - (1 - k)^(1/N); for 24 and 25",
             "// `window` indexes kWorldCalls, 26 a length (1 << flag) x n times N, 27 a",
             "// call answering no (al = 0) between stock ticks (kWorldCalls too), 28 a",
             "// stored integer wait times N, 29 a literal blend, 30/31 computed blend",
             "// forms, 32 an immediate float store changed from K to K*s",
             ""]
    for name, data in (("kWorldCode", pool.code), ("kWorldOrig", orig)):
        lines.append("static const uint8_t %s[] = {" % name)
        for j in range(0, len(data), 24):
            lines.append("    " + ",".join("0x%02X" % x for x in data[j:j + 24]) + ",")
        lines += ["};", ""]
    lines += ["struct WorldLiteralOrig { uint8_t b[8]; };",
              "static const WorldLiteralOrig kWorldLiteralOrig[] = {"]
    lines += ["    {{" + ",".join("0x%02X" % x for x in l["orig"]) + "}},  // %X" % l["rva"]
              for l in literals]
    lines += ["};", ""]
    tables = [
        ("WorldFixup", "uint32_t field, next, target;", "kWorldFixups", pool.fixups),
        ("WorldWindow", "uint32_t rva, stub, orig; uint16_t len;", "kWorldWindows", win_rows),
        ("WorldSite", "uint32_t site; uint8_t kind, group; uint16_t window; uint8_t temp; "
         "uint16_t counter, probe; uint8_t role;",
         "kWorldSites", sorted(site_rows)),
        ("WorldLiteral", "uint32_t rva, constRva, slot; uint8_t kind, group;", "kWorldLiterals",
         lit_rows),
        ("WorldCall", "uint32_t rva, stub, target;", "kWorldCalls", call_rows),
    ]
    for typ, fields, name, trows in tables:
        lines += ["struct %s { %s };" % (typ, fields), "static const %s %s[] = {" % (typ, name)]
        lines += ["    {" + ", ".join("0x%X" % v for v in r) + "}," for r in trows]
        lines += ["};", ""]
    # each call's opcode as shipped, in kWorldCalls' order: E8 a call, E9 a tail jump
    ops = [d["op"] for d in sorted(calls, key=lambda d: d["site"])]
    lines += ["static const uint8_t kWorldCallOps[] = {"]
    lines += ["    " + ", ".join("0x%X" % o for o in ops[k:k + 16]) + ","
              for k in range(0, len(ops), 16)]
    lines += ["};", ""]
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print("world anims: %d sites (%s), %d windows, %d literals, %d calls, %d fixups, %d pool "
          "bytes" % (len(rows), dict(collections.Counter(r["kind"] for r in rows)), len(windows),
                     len(literals), len(call_rows), len(pool.fixups), pool.here()))
    for r in rows:
        print("  %-5s %s %-6s %-9s %s" % (r["group"], r["site"], r["kind"], r["window"], r["proof"]))


if __name__ == "__main__":
    main()
