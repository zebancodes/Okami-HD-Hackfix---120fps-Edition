#!/usr/bin/env python3
"""Generate the task waits' stock length.

A scripted task yields with main+4567C0(task, n); cTaskManager::step counts
the task's countdown (+12, a word) down by one a tick and wakes it at 0. So a
pause of n ticks lasts n / fps seconds: a quarter of stock's at 120, and a
loop that yields with wait(1) runs four passes per stock tick.

tools/survey_task_waits.py sorts every call of the wait and describes the loop
around each one on a cycle (tools/task_wait_loops.py). This converts:

  pause   a constant length above one, on no cycle: a straight-line pause
          between two lines or two camera cuts;
  data    a length read from data or made from a loop's pass count, each read
          by hand (DATA_REVIEWED): in stock ticks, like the constants;
  loop    a wait on a cycle whose innermost loop steps state from one pass to
          the next (task_wait_loops: a read-modify-write, a carried float, a
          pass counter; or a call of a reviewed stepping callee), with
          nothing in the loop or below it that reads the pad, reads a rate
          global or is already patched, except below a callee read by hand
          (CALLEES_REVIEWED). Its wait(1) becomes wait(N): one pass a stock
          tick, stock's steps at stock's cadence. A constant pause in such a
          loop, or in a poll, is converted as a pause unless the loop reads a
          rate global or reaches patched code (the pad does not matter to a
          pause: stock checks the pad no more often).

Each such call's rel32 is retargeted at one of two entries of a shared stub
that multiplies the length by N, the ticks per stock tick of the stock context
(as the phase steps' N), caps it at the word's 0xFFFF and jumps on to the
wait; the return address stays the caller's. At N = 1 the stub hands the
length on untouched. The pause entry counts the pauses and their stock ticks,
the loop entry the passes, for the log.

The skip latch. The event camera sequencer (4A0900, in CALLEES_REVIEWED)
checks the skip button through main+13A7D0, which arms on the button's press
edge: a word the pad sets for one tick (main+B6B0D0..DF). A loop converted to
one pass a stock tick would see a press only if it fell on its tick. So the
task manager's call in flower_tick (4B6652, after the pad update at 4B6639 and
before any task runs) is retargeted at a stub that keeps the press words of
the last four ticks, and main+13A7D0's two reads of them (a lea for the
LargeBitElement it builds, a mov of the upper word) become windows that OR in
those of the previous N - 1 ticks. A reader once a stock tick then sees every
press once; at N = 1 the OR is zero and the reads are the originals. When the
skip check disarms (its armed byte main+7E6010 falls), the presses before
that tick are forgotten, so the press that skipped cannot arm it again.

Not converted, and why (task_waits.csv has every call):
  a poll's wait(1)  looks right at any rate; converted, it would miss a state
          that lasts less than a stock tick;
  wait(1) on no cycle  a one-tick yield;
  a loop with pad, rate or patched evidence outside the reviewed callees: a
          loop that must see every tick's input, or whose work below is
          already in real time.

    .venv/Scripts/python tools/gen_task_waits.py
    -> src/task_waits.h
"""
import collections
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_tracer as tr  # noqa: E402
import gen_integer_skips as gis  # noqa: E402
import survey_task_waits as stw  # noqa: E402
import task_wait_loops as twl  # noqa: E402

ROOT = tr.ROOT
OUT_H = os.path.join(ROOT, "src", "task_waits.h")
AUDITED_MAIN_SHA1 = "703d292ab2cb50cc9e237e44722dec51d956b79c"
WAIT = stw.WAIT
TASK_MANAGER = 0x456530
TICK_CALL = 0x4B6652          # flower_tick: call cTaskManager's per-tick run
PRESS_LO, PRESS_HI = 0xB6B0D0, 0xB6B0D8
SKIP_STATE = 0x7E6010         # main+13A7D0's state: [0] armed
SKIP_READS = {0x13A841: "lea r8, [rip + press]", 0x13A853: "mov rax, qword ptr [rip + press + 8]"}

# Callees read by hand. A loop's pad, rate and patched evidence found only
# below one of these is waived; "steps" marks a callee whose call is itself
# per-pass work (the loop then steps even with no evidence of its own).
CALLEES_REVIEWED = {
    0x4A0900: ("steps", "the event camera sequencer, called once a pass with a cut list: it counts "
               "the cut's frames (+8) and at the list's frames starts sounds (19C850), effects "
               "(2E0020, 2DFE60) and the next camera path, so at 120 all of them came 4x early "
               "against the path (F6 plays paths at stock speed). Its rate and patched evidence "
               "is the path player's first step when a cut starts a path (4763F0, F6's own "
               "site); its pad read is the skip check 13A7D0, which the skip latch keeps whole "
               "at one pass a stock tick; the stick reads below 481A10 set the path up once"),
    0x43B0E0: ("steps", "a four-mode sequencer over main+B4DFD8 (save/load, loading screen): "
               "case 1 counts main+B4DFD9 down from 7 a call before it moves on; its other "
               "states poll"),
    0x487E30: ("", "starts one of an actor's motions by index (4B9B70, which reads the mode "
               "multipliers to set the motion up); the motion then plays on the actor's own "
               "update. Called once a pass, it only chooses the next motion"),
    0x3E2A90: ("", "sets up a HUD message; the 60 fps flag it reads doubles the message's own "
               "duration, a count the HUD keeps; the loop's waits are the script's rhythm"),
    0x44A160: ("", "starts a BGM track (main+B4DFF0); the patched instruction 17 calls below "
               "(the phase step at 1D601) is in the sound library's stream setup, which runs "
               "once a start. The loops that call it do so once, when a state is reached"),
    0x439D60: ("", "starts a scene fade: stamps the frame counter into +0x2C (frame_clocks.csv: "
               "a stamp, stored and never subtracted) and sets flags; called once, as the "
               "loop ends"),
}

# Lengths that are not constants to the survey, each read in the code
# (tools/ghidra_lines.py). value: the length if the code fixes it on its path.
DATA_REVIEWED = {
    0x492A28: (None, "4927F0's event step: wait(entry[+0x10]), a u16 of the event's cut table, "
               "in ticks as the constants beside it"),
    0x4A9493: (None, "4A9470: wait([+0x20]), the event entry's delay before it starts a camera "
               "path (481A10)"),
    0x4CA383: (60, "lea edx, [rdi + 0x3B] under cmp edi, 1 / jne: wait(60)"),
    0x4E5FBA: (10, "lea edx, [rbx + 10] after the countdown loop that leaves rbx 0: wait(10)"),
    0x4EC6CD: (10, "lea edx, [r + 10] with r zero on the path: wait(10)"),
    0x4F7DA0: (5, "lea edx, [r + 5] with r zero on the path: wait(5)"),
    0x5110B3: (None, "wait(byte [[B71B50] + 0x41]): the mini-game's own delay in ticks"),
    0x5136A3: (None, "wait(byte [[B71B50] + 0x41]), as 5110B3"),
    0x54F1A3: (45, "lea edx, [r + 0x2D] with r zero on the path: wait(45)"),
    0x5B60F3: (None, "wait(len - 30), len a u16 of the event's table (+0xD0 entry, +4): the part "
               "of a timed stretch before its last 30 ticks, which a loop then runs"),
    0x5B6358: (None, "wait(len - 30), as 5B60F3"),
    0x5B65CA: (None, "wait(len - 30), as 5B60F3"),
    0x5B68C4: (None, "wait(len - 30), as 5B60F3"),
    0x615D0C: (60, "lea edx, [r + 0x3C] with r zero on the path: wait(60)"),
    0x62A60C: (90, "lea edx, [r + 0x5A] with r zero on the path: wait(90)"),
    0x4D6E61: (None, "wait(10 - k), k the passes of the poll before it (4D6D40, a loop this "
               "converts): the rest of a 10-tick minimum"),
    0x5021B4: (None, "wait(60 - k), k the passes of the poll before it (50217F, converted): the "
               "rest of a 60-tick minimum"),
    0x54BE87: (None, "wait(10 - k), k the passes of the poll before it (54BD10, converted)"),
}
# data rows left alone: a one-tick yield the survey could not fold
DATA_LEFT = {
    0x51C26A: "lea edx, [r + 1] with r zero on the path: a straight-line wait(1)",
    0x54F92D: "lea edx, [r + 1] with r zero: a wait(1) in a poll (54F880's loop steps, but "
              "through 2DA3D0 and 481570 it reaches patched code)",
}

# Loops the rule selects that stay per tick, and why.
LOOPS_EXCLUDED = {}

# world_anims.h rows written for a loop this paces (kind dstn, x N): their
# windows are not evidence against the loop, they need it paced.
PACED_ROWS = {
    0x54F665: "54EDC0's first walk loop (wait 54F698): a walker's step x N",
    0x54F9D7: "54EDC0's second walk loop (wait 54FA0A): a walker's step x N",
}


def paced_windows():
    """[(start, end)] of the world windows that hold a PACED_ROWS site"""
    import verify_world_anims as vwa
    hdr = vwa.parse_header()
    return [(rva, rva + n) for rva, _stub, _orig, n in hdr["windows"]
            if any(rva <= p < rva + n for p in PACED_ROWS)]


_PACED = None


def paced_evidence(e):
    global _PACED
    if _PACED is None:
        _PACED = paced_windows()
    p = e.split()
    if len(p) < 3 or p[0] != "direct" or "world_anims.h" not in e:
        return False
    a = int(p[1], 16)
    return any(lo <= a < hi for lo, hi in _PACED)

# pool: [0] N, [4] pauses scaled, [8] calls at N = 1, [0xC] stock ticks the
# scaled pauses asked for, [0x10] loop passes at one a stock tick, [0x14] the
# skip check's armed byte at the last tick, [0x20] the press words of the
# previous N - 1 ticks ORed, [0x30] the last four ticks' press words (ring,
# newest first), [0x70] the lea window's copy of the press words; code from 0x80
N_OFFSET, SCALED_OFFSET, PLAIN_OFFSET, TICKS_OFFSET = 0, 4, 8, 0xC
LOOPS_OFFSET, ARMED_OFFSET, HIST_OFFSET, RING_OFFSET, SCRATCH_OFFSET = 0x10, 0x14, 0x20, 0x30, 0x70
CODE_OFFSET = 0x80
ENTRY_PAUSE, ENTRY_LOOP = 0, 1


def unwaived(evidence):
    if not evidence:
        return set()
    items = [e for e in evidence.split(" | ") if not paced_evidence(e)]
    return {s for s in twl.sources(items) if s not in CALLEES_REVIEWED}


def decide(r):
    """(entry, why) for a call this converts, or (None, why)"""
    at = int(r["site"], 16)
    if r["cls"] == "timed" and not r["loop"]:
        return ENTRY_PAUSE, "pause"
    if r["cls"] == "data":
        if at in DATA_REVIEWED:
            if r["loop"] and (unwaived(r["rate"]) or unwaived(r["patched"])):
                return None, "data pause in a loop with rate or patched evidence"
            return ENTRY_PAUSE, "data"
        return None, "data: " + DATA_LEFT.get(at, "NOT REVIEWED")
    if not r["loop"]:
        return None, "one-tick yield"
    if at in LOOPS_EXCLUDED:
        return None, "excluded: " + LOOPS_EXCLUDED[at]
    rate, pat, pad = unwaived(r["rate"]), unwaived(r["patched"]), unwaived(r["pad"])
    if r["cls"] == "timed":
        if rate or pat:
            return None, "pause in a loop with rate or patched evidence"
        return ENTRY_PAUSE, "pause in a loop"
    calls = {int(c, 16) for c in r["calls"].split()} if r["calls"] else set()
    steps = bool(r["steps"]) or any(CALLEES_REVIEWED.get(c, ("",))[0] == "steps" for c in calls)
    if not steps:
        return None, "poll"
    if pad or rate or pat:
        return None, "steps, with %s evidence" % "/".join(
            k for k, v in (("pad", pad), ("rate", rate), ("patched", pat)) if v)
    return ENTRY_LOOP, "loop"


def select(rows):
    return [(r, e, why) for r in rows for e, why in [decide(r)] if e is not None]


def emit_stubs(pool):
    """the wait's two entries, the tick stub, the skip check's two windows:
    {name: pool offset}"""
    at = {}
    # -- pause entry: edx = N == 1 ? edx : min(edx * N, 0xFFFF); counted -----
    at["pause"] = pool.here()
    pool.pool_rel32(b"\x83\x3D", N_OFFSET, trailing=b"\x01")    # cmp dword [N], 1
    pool.emit(b"\x75\x00")                                       # jne scale
    jne = len(pool.code)
    pool.pool_rel32(b"\xF0\xFF\x05", PLAIN_OFFSET)               # lock inc dword [plain]
    pool.game_rel32(b"\xE9", WAIT)                               # jmp wait
    pool.code[jne - 1] = len(pool.code) - jne
    pool.pool_rel32(b"\xF0\xFF\x05", SCALED_OFFSET)              # scale: lock inc [scaled]
    pool.pool_rel32(b"\xF0\x01\x15", TICKS_OFFSET)               # lock add [ticks], edx
    common = pool.here()
    pool.pool_rel32(b"\x8B\x05", N_OFFSET)                       # common: mov eax, [N]
    pool.emit(b"\x0F\xAF\xC2")                                   # imul eax, edx
    pool.emit(b"\x3D\xFF\xFF\x00\x00")                           # cmp eax, 0xFFFF
    pool.emit(b"\x76\x05")                                       # jbe ok
    pool.emit(b"\xB8\xFF\xFF\x00\x00")                           # mov eax, 0xFFFF
    pool.emit(b"\x8B\xD0")                                       # ok: mov edx, eax
    pool.game_rel32(b"\xE9", WAIT)                               # jmp wait
    # -- loop entry: the same, counted as a pass ---------------------------
    at["loop"] = pool.here()
    pool.pool_rel32(b"\x83\x3D", N_OFFSET, trailing=b"\x01")    # cmp dword [N], 1
    pool.emit(b"\x75\x00")                                       # jne lscale
    jne = len(pool.code)
    pool.pool_rel32(b"\xF0\xFF\x05", PLAIN_OFFSET)               # lock inc dword [plain]
    pool.game_rel32(b"\xE9", WAIT)                               # jmp wait
    pool.code[jne - 1] = len(pool.code) - jne
    pool.pool_rel32(b"\xF0\xFF\x05", LOOPS_OFFSET)               # lscale: lock inc [loops]
    pool.emit(b"\xE9")                                           # jmp common
    pool.emit(struct.pack("<i", common - (pool.here() + 4)))
    # -- tick stub: in place of flower_tick's call of the task manager -------
    # keeps rcx (the manager), rdx, r8, r9 and every callee-saved register;
    # uses rax, r10, r11 and the flags, which the call clobbers anyway
    at["tick"] = pool.here()
    for dst, src in ((0x30, 0x20), (0x38, 0x28), (0x20, 0x10), (0x28, 0x18),
                     (0x10, 0x00), (0x18, 0x08)):
        pool.pool_rel32(b"\x48\x8B\x05", RING_OFFSET + src)      # mov rax, [ring + src]
        pool.pool_rel32(b"\x48\x89\x05", RING_OFFSET + dst)      # mov [ring + dst], rax
    pool.game_rel32(b"\x48\x8B\x05", PRESS_LO)                   # mov rax, [press]
    pool.pool_rel32(b"\x48\x89\x05", RING_OFFSET)                # mov [ring], rax
    pool.game_rel32(b"\x48\x8B\x05", PRESS_HI)                   # mov rax, [press + 8]
    pool.pool_rel32(b"\x48\x89\x05", RING_OFFSET + 8)            # mov [ring + 8], rax
    pool.game_rel32(b"\x0F\xB6\x05", SKIP_STATE)                 # movzx eax, byte [armed]
    pool.pool_rel32(b"\x44\x8B\x15", ARMED_OFFSET)               # mov r10d, [was armed]
    pool.pool_rel32(b"\x89\x05", ARMED_OFFSET)                   # mov [was armed], eax
    pool.emit(b"\x45\x85\xD2")                                   # test r10d, r10d
    pool.emit(b"\x74\x00")                                       # jz keep
    jz = len(pool.code)
    pool.emit(b"\x85\xC0")                                       # test eax, eax
    pool.emit(b"\x75\x00")                                       # jnz keep
    jnz = len(pool.code)
    pool.emit(b"\x33\xC0")                                       # xor eax, eax
    for off in range(0x10, 0x40, 8):
        pool.pool_rel32(b"\x48\x89\x05", RING_OFFSET + off)      # mov [ring + off], rax
    pool.code[jz - 1] = len(pool.code) - jz
    pool.code[jnz - 1] = len(pool.code) - jnz
    pool.emit(b"\x33\xC0")                                       # keep: xor eax, eax
    pool.emit(b"\x45\x33\xD2")                                   # xor r10d, r10d
    pool.pool_rel32(b"\x44\x8B\x1D", N_OFFSET)                   # mov r11d, [N]
    jbs = []
    for k in (1, 2, 3):
        pool.emit(b"\x41\x83\xFB" + bytes([k + 1]))              # cmp r11d, k + 1
        pool.emit(b"\x72\x00")                                   # jb done
        jbs.append(len(pool.code))
        pool.pool_rel32(b"\x48\x0B\x05", RING_OFFSET + 0x10 * k)       # or rax, [ring k]
        pool.pool_rel32(b"\x4C\x0B\x15", RING_OFFSET + 0x10 * k + 8)   # or r10, [ring k + 8]
    for j in jbs:
        pool.code[j - 1] = len(pool.code) - j
    pool.pool_rel32(b"\x48\x89\x05", HIST_OFFSET)                # done: mov [hist], rax
    pool.pool_rel32(b"\x4C\x89\x15", HIST_OFFSET + 8)            # mov [hist + 8], r10
    pool.game_rel32(b"\xE9", TASK_MANAGER)                       # jmp the task manager
    # -- window at 13A841: r8 = a copy of the press words ORed with the history
    at["lea"] = pool.here()
    pool.game_rel32(b"\x4C\x8B\x05", PRESS_LO)                   # mov r8, [press]
    pool.pool_rel32(b"\x4C\x0B\x05", HIST_OFFSET)                # or r8, [hist]
    pool.pool_rel32(b"\x4C\x89\x05", SCRATCH_OFFSET)             # mov [copy], r8
    pool.game_rel32(b"\x4C\x8B\x05", PRESS_HI)                   # mov r8, [press + 8]
    pool.pool_rel32(b"\x4C\x0B\x05", HIST_OFFSET + 8)            # or r8, [hist + 8]
    pool.pool_rel32(b"\x4C\x89\x05", SCRATCH_OFFSET + 8)         # mov [copy + 8], r8
    pool.pool_rel32(b"\x4C\x8D\x05", SCRATCH_OFFSET)             # lea r8, [copy]
    pool.game_rel32(b"\xE9", 0x13A848)                           # jmp back
    # -- window at 13A853: rax = the upper press word ORed with its history
    at["mov"] = pool.here()
    pool.game_rel32(b"\x48\x8B\x05", PRESS_HI)                   # mov rax, [press + 8]
    pool.pool_rel32(b"\x48\x0B\x05", HIST_OFFSET + 8)            # or rax, [hist + 8]
    pool.game_rel32(b"\xE9", 0x13A85A)                           # jmp back
    return at


def check_windows(img, secs, problems):
    """the skip check's two reads: the bytes the stub assumes, no branch into
    their tails, no relocation in them"""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    lo, hi = secs[".text"]
    _starts, targets, switch, _tables = tr.global_pass(img, lo, hi)
    out = []
    for rva, want in sorted(SKIP_READS.items()):
        i = next(md.disasm(bytes(img[rva:rva + 16]), rva))
        g = tr.RIPLEA.search(i.op_str)
        t = None
        if g:
            d = int(g.group(2), 0)
            t = rva + i.size + (d if g.group(1) == "+" else -d)
        want_t = PRESS_LO if i.mnemonic == "lea" else PRESS_HI
        if i.size != 7 or t != want_t or (i.mnemonic, i.op_str.split(",")[0]) not in (
                ("lea", "r8"), ("mov", "rax")):
            problems.append("%X: %s %s is not %s" % (rva, i.mnemonic, i.op_str, want))
        inner = set(range(rva + 1, rva + 7))
        if inner & (targets | switch):
            problems.append("%X: a branch lands inside the window" % rva)
        if any(x in tr.RELOCATED for x in range(rva, rva + 7)):
            problems.append("%X: holds a base relocation" % rva)
        out.append((rva, bytes(img[rva:rva + 7])))
    b = bytes(img[TICK_CALL:TICK_CALL + 5])
    if b[0] != 0xE8 or TICK_CALL + 5 + struct.unpack_from("<i", b, 1)[0] != TASK_MANAGER:
        problems.append("%X is not flower_tick's call of the task manager" % TICK_CALL)
    return out, b


def main():
    img, secs, _begins, sha = tr.load_image()
    if sha != AUDITED_MAIN_SHA1:
        raise RuntimeError("main.dll %s is not the audited build %s" % (sha, AUDITED_MAIN_SHA1))
    rows, problems = stw.audit()
    if problems:
        for p in problems:
            print("TASK WAIT PROBLEM " + p)
        raise RuntimeError("tools/survey_task_waits.py finds %d problems" % len(problems))
    unread = [r["site"] for r in rows if r["cls"] == "data" and
              int(r["site"], 16) not in DATA_REVIEWED and int(r["site"], 16) not in DATA_LEFT]
    stale = [a for a in list(DATA_REVIEWED) + list(DATA_LEFT)
             if not any(int(r["site"], 16) == a and r["cls"] == "data" for r in rows)]
    stale += [a for a in LOOPS_EXCLUDED if not any(int(r["site"], 16) == a for r in rows)]
    protected = gis.patched_ranges()
    import check_patch_sites as cps
    for fam in (cps.turn_callers, cps.day_clock):
        for a, raw, label in fam():
            protected.append((a, a + len(raw), label))
    refused = [(int(s, 16), "a data length nobody has read") for s in unread]
    refused += [(a, "a reviewed entry the survey no longer lists as such") for a in stale]
    sites = []
    for r, entry, why in select(rows):
        at = int(r["site"], 16)
        b = bytes(img[at:at + 5])
        # a call, or a tail jump (the stub leaves the stack as it finds it)
        if b[0] not in (0xE8, 0xE9) or at + 5 + struct.unpack_from("<i", b, 1)[0] != WAIT:
            refused.append((at, "not a call or jmp rel32 of the wait"))
            continue
        hit = [w for a, e, w in protected if a < at + 5 and at < e]
        if hit:
            refused.append((at, "already patched by " + hit[0]))
            continue
        if any(x in tr.RELOCATED for x in range(at, at + 5)):
            refused.append((at, "holds a base relocation"))
            continue
        sites.append((at, b, r, entry, why))
    wprob = []
    windows, tick_bytes = check_windows(img, secs, wprob)
    refused += [(0, p) for p in wprob]
    latch = [(TICK_CALL, TICK_CALL + 5)] + [(rva, rva + 7) for rva in SKIP_READS]
    for a, e, w in protected:
        for lo, hi in latch:
            if a < hi and lo < e:
                refused.append((lo, "the skip latch overlaps " + w))
    for at, why in refused:
        print("REFUSED %X: %s" % (at, why))
    if refused:
        raise RuntimeError("%d problems; nothing written" % len(refused))
    pool = tr.Pool(CODE_OFFSET)
    entries = emit_stubs(pool)
    size = pool.here()
    code = bytes(pool.code)
    lines = ["// Generated by tools/gen_task_waits.py -- do not edit.",
             "// The scripted tasks' pauses at their stock length and their stepping loops at one",
             "// pass a stock tick: each call of the task wait (main+4567C0) the generator",
             "// selects is retargeted at a stub entry that multiplies its length by N; and the",
             "// skip latch, which lets the skip check see a press from a converted loop.",
             "// docs/animation/task_waits.csv has every call of the wait and its class.",
             "#pragma once", "#include <cstdint>", "",
             '#define TASK_WAITS_MAIN_SHA1 "%s"' % sha,
             "static const uint32_t kTaskWaitRva = 0x%X;" % WAIT,
             "static const uint32_t kTaskWaitNOffset = 0x%X;        // uint32 N" % N_OFFSET,
             "static const uint32_t kTaskWaitScaledOffset = 0x%X;   // pauses scaled" %
             SCALED_OFFSET,
             "static const uint32_t kTaskWaitPlainOffset = 0x%X;    // calls at N = 1" %
             PLAIN_OFFSET,
             "static const uint32_t kTaskWaitTicksOffset = 0x%X;    // stock ticks the scaled "
             "pauses asked for" % TICKS_OFFSET,
             "static const uint32_t kTaskWaitLoopsOffset = 0x%X;   // loop passes scaled" %
             LOOPS_OFFSET,
             "static const uint32_t kTaskWaitArmedOffset = 0x%X;   // the skip check's armed "
             "byte, last tick" % ARMED_OFFSET,
             "static const uint32_t kTaskWaitHistOffset = 0x%X;    // press words, previous "
             "N - 1 ticks" % HIST_OFFSET,
             "static const uint32_t kTaskWaitRingOffset = 0x%X;    // press words, last 4 ticks"
             % RING_OFFSET,
             "static const uint32_t kTaskWaitScratchOffset = 0x%X; // the lea window's copy" %
             SCRATCH_OFFSET,
             "static const uint32_t kTaskWaitCodeOffset = 0x%X;" % CODE_OFFSET,
             "static const uint32_t kTaskWaitPauseEntry = 0x%X;" % entries["pause"],
             "static const uint32_t kTaskWaitLoopEntry = 0x%X;" % entries["loop"],
             "static const uint32_t kTaskWaitTickEntry = 0x%X;" % entries["tick"],
             "static const uint32_t kTaskWaitPoolSize = 0x%X;" % ((size + 15) & ~15), "",
             "static const uint32_t kTaskManagerRva = 0x%X;" % TASK_MANAGER,
             "static const uint32_t kTaskPressRva = 0x%X;           // the pad's press words, 16 "
             "bytes" % PRESS_LO,
             "static const uint32_t kTaskSkipStateRva = 0x%X;       // main+13A7D0's state" %
             SKIP_STATE,
             "// flower_tick's call of the task manager, retargeted at the tick entry",
             "static const uint32_t kTaskWaitTickCallRva = 0x%X;" % TICK_CALL,
             "static const int32_t kTaskWaitTickCallRel = %d;" %
             struct.unpack_from("<i", tick_bytes, 1)[0], "",
             "static const uint8_t kTaskWaitCode[] = {"]
    for j in range(0, len(code), 24):
        lines.append("    " + ",".join("0x%02X" % x for x in code[j:j + 24]) + ",")
    lines += ["};", "",
              "struct TaskWaitFixup { uint32_t field, next, target; };  // rel32 -> main+target",
              "static const TaskWaitFixup kTaskWaitFixups[] = {"]
    lines += ["    {0x%X, 0x%X, 0x%X}," % f for f in pool.fixups]
    lines += ["};", "",
              "// main+13A7D0's two reads of the press words, each replaced by a jmp to its",
              "// pool code and two int3: the bytes as shipped, the pool offset",
              "struct TaskWaitWindow { uint32_t rva; uint8_t orig[7]; uint32_t code; };",
              "static const TaskWaitWindow kTaskWaitWindows[] = {"]
    for (rva, raw), name in zip(windows, ("lea", "mov")):
        lines.append("    {0x%X, {%s}, 0x%X},  // %s" % (
            rva, ", ".join("0x%02X" % x for x in raw), entries[name], SKIP_READS[rva]))
    lines += ["};", "",
              "// a call (E8) or tail jump (E9) of the wait: its rva, its rel32 as shipped, its",
              "// length in stock ticks (0: not a constant), its opcode, its stub entry",
              "// (0 a pause, 1 a loop's pass)",
              "struct TaskWaitSite { uint32_t rva; int32_t rel; uint16_t ticks; uint8_t op, entry; };",
              "static const TaskWaitSite kTaskWaitSites[] = {"]
    for at, b, r, entry, why in sites:
        v = r["value"] or "0"
        if at in DATA_REVIEWED and DATA_REVIEWED[at][0]:
            v = str(DATA_REVIEWED[at][0])
        lines.append("    {0x%X, %d, %s, 0x%02X, %d},  // in %s, %s" % (
            at, struct.unpack_from("<i", b, 1)[0], v, b[0], entry, r["function"], why))
    lines += ["};", ""]
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    kinds = collections.Counter(why for _a, _b, _r, _e, why in sites)
    print("task waits: %d calls retargeted in %d functions (%s), %d bytes of stub code" % (
        len(sites), len({r["function"] for _a, _b, r, _e, _w in sites}),
        ", ".join("%d %s" % (n, k) for k, n in kinds.most_common()), len(code)))
    left = collections.Counter(why.split(":")[0] for r in rows for e, why in [decide(r)]
                               if e is None)
    print("left: " + ", ".join("%d %s" % (n, k) for k, n in left.most_common()))


if __name__ == "__main__":
    main()
