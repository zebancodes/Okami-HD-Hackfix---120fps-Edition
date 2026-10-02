#!/usr/bin/env python3
"""Verify the task waits (src/task_waits.h) against the game's code.

1. Bytes. The DLL's own installer (OkamiTaskWaitSelfTest, on a mapped
   main.dll) must produce the pool that an independent relocation of the
   header gives; every call it takes over must reach its stub entry (a pause
   or a loop's pass) with its opcode (call or tail jump) unchanged;
   flower_tick's call of the task manager must reach the tick entry; the skip
   check's two reads must be a jmp to their pool code and two int3. Its
   per-tick update must hold N = fps over the stock context's rate while the
   fix is on and 1 otherwise, in every fps / context / switch / key / hook
   state; and a failed write must leave what stays in at N = 1.

2. The wait's two entries, under Unicorn, from random machine states at
   N = 1, 2 and 4 and every length from 0 to 0xFFFF (sampled, with the
   edges): each must reach main+4567C0 with the stack as it found it (the
   caller's return address on top), every register but rax, rdx and the
   flags as they were, and edx the length (N = 1: rdx untouched) or
   min(length x N, 0xFFFF) with rdx's upper half clear (the wait reads only
   dx); its counters must count the call (a pause: scaled and its stock
   ticks; a loop: its passes; N = 1: plain).

3. The skip latch, under Unicorn, tick after tick: the tick entry (run where
   flower_tick calls the task manager) from random machine states must reach
   main+456530 with rcx, rdx, r8, r9, rsp and every callee-saved register as
   it found them; and the two windows run in main+13A7D0 (patched) must
   leave r8 pointing at the press words ORed with the history and rax the
   upper word ORed with its history, every other register as it was. Over
   random press sequences with the skip check arming and disarming: at N = 1
   every read equals the live words; at N = 2 and 4 a reader once every N
   ticks, at any phase, sees every press unless the skip check disarmed in
   between, and no read after a disarm sees a press from before it.

4. The selection, from the code: tools/survey_task_waits.py run again and
   gen_task_waits.select must pick exactly the header's calls with the same
   entries, and each must be a call or jump of the wait in the shipped
   main.dll.

5. What a pause and a pass last: the countdown the task manager keeps (4566CB:
   the word at +12 loses 1 a tick, the task wakes at 0), run on the length
   the stub hands on, at 120 and 60 in play and in a 60 Hz menu: every scaled
   pause must end after its stock time to the tick, and a converted loop
   must make one pass a stock tick.

    .venv/Scripts/python tools/verify_task_waits.py
    --break n|cap|loop|hist corrupts the pool's N, the stub's cap, the loop
    entry's N test, or the history's OR, and must fail.
"""
import argparse
import ctypes
import hashlib
import os
import random
import re
import shutil
import struct
import sys
import tempfile

import pefile
from unicorn import UcError

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import verify_menu_transitions as vmt  # noqa: E402  (the emulator and state helpers)

ROOT = os.path.dirname(HERE)
HDR = os.path.join(ROOT, "src", "task_waits.h")
BASE, POOL = vmt.BASE, vmt.POOL
RET = 0x7E0000000100


def parse_header(path=HDR):
    text = open(path, encoding="utf-8").read()

    def const(name):
        return int(re.search(r"\b%s\s*=\s*(-?0x[0-9a-fA-F]+|-?\d+)" % name, text).group(1), 0)

    def block(name):
        return re.search(r"\b%s\[\]\s*=\s*\{(.*?)\n\};" % name, text, re.S).group(1)

    code = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-F]{2})\b", block("kTaskWaitCode")))
    fixups = [tuple(int(v, 0) for v in r.split(","))
              for r in re.findall(r"\{(0x[0-9A-F]+, 0x[0-9A-F]+, 0x[0-9A-F]+)\}",
                                  block("kTaskWaitFixups"))]
    sites = [(int(a, 16), int(rel), int(t), int(op, 16), int(e)) for a, rel, t, op, e in
             re.findall(r"\{0x([0-9A-F]+), (-?\d+), (\d+), 0x([0-9A-F]{2}), (\d)\}",
                        block("kTaskWaitSites"))]
    windows = [(int(a, 16), bytes(int(x, 16) for x in orig.split(",")), int(c, 16))
               for a, orig, c in re.findall(r"\{0x([0-9A-F]+), \{([0-9A-Fx, ]+)\}, 0x([0-9A-F]+)\}",
                                            block("kTaskWaitWindows"))]
    names = dict(n_off="kTaskWaitNOffset", scaled="kTaskWaitScaledOffset",
                 plain="kTaskWaitPlainOffset", ticks="kTaskWaitTicksOffset",
                 loops="kTaskWaitLoopsOffset", armed="kTaskWaitArmedOffset",
                 hist="kTaskWaitHistOffset", ring="kTaskWaitRingOffset",
                 scratch="kTaskWaitScratchOffset", code_off="kTaskWaitCodeOffset",
                 pause="kTaskWaitPauseEntry", loop="kTaskWaitLoopEntry",
                 tick="kTaskWaitTickEntry", size="kTaskWaitPoolSize", wait="kTaskWaitRva",
                 manager="kTaskManagerRva", press="kTaskPressRva", skip="kTaskSkipStateRva",
                 tick_call="kTaskWaitTickCallRva", tick_rel="kTaskWaitTickCallRel")
    out = {k: const(v) for k, v in names.items()}
    out.update(sha=re.search(r'TASK_WAITS_MAIN_SHA1\s+"([0-9a-f]+)"', text).group(1),
               code=code, fixups=fixups, sites=sites, windows=windows)
    return out


def relocated_pool(hdr, main_base, pool_base):
    pool = bytearray(hdr["size"])
    co = hdr["code_off"]
    pool[co:co + len(hdr["code"])] = hdr["code"]
    for field, nxt, target in hdr["fixups"]:
        rel = main_base + target - (pool_base + nxt)
        assert -2 ** 31 <= rel < 2 ** 31
        struct.pack_into("<i", pool, field, rel)
    return pool


def want_n(fps, mode, fix, muted, shadow, hook, complete):
    if not (fix and not muted and shadow and hook and complete and fps != 30 and mode in (1, 2)):
        return 1
    return fps // (60 if mode == 1 else 30)


def entry_of(hdr, e):
    return hdr["loop"] if e else hdr["pause"]


def check_install(args, hdr, path):
    problems = []
    work = tempfile.mkdtemp(prefix="okami_task_waits_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiTaskWaitSelfTest
    fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    lines = [ln for ln in report.strip().splitlines()]
    print("DLL self-test (rc %d): %s" % (rc, lines[-1]))
    if rc:
        print(report)
        return ["DLL self-test failed"], 0
    vals = dict(ln.split(None, 1) for ln in lines if len(ln.split()) == 2)
    main_base, pool_base = int(vals["main"], 16), int(vals["pool"], 16)
    installed = open(os.path.join(work, "pool.bin"), "rb").read()
    want = relocated_pool(hdr, main_base, pool_base)
    co = hdr["code_off"]
    if installed[co:] != bytes(want[co:]):
        problems.append("installed stub differs from the independently relocated header")
    patched = open(os.path.join(work, "patched.bin"), "rb").read()
    k = 0
    for rva, _rel, _t, op, e in hdr["sites"]:
        b = patched[k:k + 5]
        k += 5
        to = main_base + rva + 5 + struct.unpack_from("<i", b, 1)[0]
        if b[0] != op or to != pool_base + entry_of(hdr, e):
            problems.append("installed main+%X does not reach its stub entry with its opcode" %
                            rva)
    b = patched[k:k + 5]
    k += 5
    if b[0] != 0xE8 or main_base + hdr["tick_call"] + 5 + struct.unpack_from("<i", b, 1)[0] != \
            pool_base + hdr["tick"]:
        problems.append("flower_tick's call of the task manager does not reach the tick entry")
    for rva, _orig, code in hdr["windows"]:
        b = patched[k:k + 7]
        k += 7
        if b[0] != 0xE9 or b[5:] != b"\xCC\xCC" or \
                main_base + rva + 5 + struct.unpack_from("<i", b, 1)[0] != pool_base + code:
            problems.append("the skip check's read at main+%X is not a jmp to its window" % rva)
    rows = 0
    for ln in open(os.path.join(work, "modes.csv")).read().splitlines()[1:]:
        fps, mode, fix, muted, shadow, hook, complete, n = (int(x) for x in ln.split(","))
        rows += 1
        w = want_n(fps, mode, fix, muted, shadow, hook, complete)
        if n != w:
            problems.append("mode row %s: N %d, want %d" % (ln, n, w))
    print("1. install: stub, %d calls, the task manager's call, %d windows and %d control "
          "states checked; %s" % (len(hdr["sites"]), len(hdr["windows"]), rows, lines[-2]))
    return problems, rows


def broken_pool(hdr, broken):
    pool = relocated_pool(hdr, BASE, POOL)
    if broken == "cap":
        k = bytes(pool).find(b"\x3D\xFF\xFF\x00\x00", hdr["code_off"])
        pool[k + 1:k + 5] = struct.pack("<I", 0xFFFFFFFF)
    if broken == "loop":
        # the loop entry's cmp dword [N], 1: compare with 0x7F instead
        pool[hdr["loop"] + 6] = 0x7F
    if broken == "hist":
        # the tick entry's first cmp r11d, 2: never OR a past tick in
        k = bytes(pool).find(b"\x41\x83\xFB\x02", hdr["tick"])
        pool[k + 3] = 0x7F
    return pool


def run_entry(img, hdr, pool, st, length, entry):
    emu = vmt.Emu(img, pool, seed=st["mem_seed"])
    vmt.load_state(emu, st, 0x1000)
    emu.set_reg("rdx", (st["rdx"] & ~0xFFFFFFFF) | length)
    rsp = emu.reg("rsp")
    emu.mu.mem_write(rsp, struct.pack("<Q", RET))
    before = {n: emu.reg(n) for n in vmt.GPR_NAMES}
    emu.stop_outside = (POOL, POOL)   # anything outside the pool stops it
    emu.exit = None
    try:
        emu.mu.emu_start(POOL + entry, 0, count=64)
    except UcError as e:
        return before, None, "fault %s" % e, emu
    after = {n: emu.reg(n) for n in vmt.GPR_NAMES}
    return before, after, emu.exit, emu


def check_entries(img, hdr, rnd, states, broken):
    problems, runs = [], 0
    edges = [0, 1, 2, 3, 30, 470, 0x3FFF, 0x4000, 0x4001, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF]
    offs = (hdr["scaled"], hdr["plain"], hdr["ticks"], hdr["loops"])
    for e, name in ((0, "pause"), (1, "loop")):
        for n in (1, 2, 4):
            pool = broken_pool(hdr, broken)
            struct.pack_into("<I", pool, hdr["n_off"], n if broken != "n" else 1)
            for k in range(states):
                length = edges[k] if k < len(edges) else rnd.randrange(0, 0x10000)
                st = vmt.random_state(rnd)
                before, after, exit_, emu = run_entry(img, hdr, pool, st, length,
                                                      entry_of(hdr, e))
                runs += 1
                tag = "%s entry, N=%d length %d" % (name, n, length)
                if after is None or exit_ != BASE + hdr["wait"]:
                    problems.append("%s: left the stub at %s" % (tag, exit_))
                    continue
                for r in vmt.GPR_NAMES:
                    if r not in ("rax", "rdx") and after[r] != before[r]:
                        problems.append("%s: %s changed" % (tag, r))
                if struct.unpack("<Q", emu.mu.mem_read(after["rsp"], 8))[0] != RET:
                    problems.append("%s: the return address is not on top" % tag)
                if n == 1:
                    if after["rdx"] != before["rdx"]:
                        problems.append("%s: rdx changed" % tag)
                    want_counts = (0, 1, 0, 0)
                else:
                    want = min(length * n, 0xFFFF)
                    if after["rdx"] != want:
                        problems.append("%s: rdx %X, want %X" % (tag, after["rdx"], want))
                    want_counts = (1, 0, length, 0) if e == 0 else (0, 0, 0, 1)
                got = tuple(struct.unpack("<I", emu.mu.mem_read(POOL + o, 4))[0] for o in offs)
                base = tuple(struct.unpack_from("<I", pool, o)[0] for o in offs)
                moved = tuple((g - b) & 0xFFFFFFFF for g, b in zip(got, base))
                if moved != want_counts:
                    problems.append("%s: counters moved by %s, want %s" % (tag, moved,
                                                                          want_counts))
    return problems, runs


# ---------------------------------------------------------------------------
# 3. the skip latch
# ---------------------------------------------------------------------------

class Latch:
    """One emulated address space, kept from tick to tick: the patched skip
    check's windows in the image, the pool at N."""

    def __init__(self, img, hdr, pool, n, seed):
        self.hdr = hdr
        patched = bytearray(img)
        for rva, _orig, code in hdr["windows"]:
            patched[rva] = 0xE9
            struct.pack_into("<i", patched, rva + 1, POOL + code - (BASE + rva + 5))
            patched[rva + 5:rva + 7] = b"\xCC\xCC"
        self.emu = vmt.Emu(patched, pool, seed=seed)
        self.emu.mu.mem_write(POOL + hdr["n_off"], struct.pack("<I", n))

    def pool_q(self, off):
        return struct.unpack("<Q", self.emu.mu.mem_read(POOL + off, 8))[0]

    def tick(self, lo, hi, armed, st):
        """flower_tick's call of the task manager, from state st"""
        emu, hdr = self.emu, self.hdr
        emu.mu.mem_write(BASE + hdr["press"], struct.pack("<QQ", lo, hi))
        emu.mu.mem_write(BASE + hdr["skip"], bytes([armed]))
        vmt.load_state(emu, dict(st, mem_seed=0), 0x1000)
        rsp = emu.reg("rsp")
        emu.mu.mem_write(rsp, struct.pack("<Q", BASE + hdr["tick_call"] + 5))
        before = {n: emu.reg(n) for n in vmt.GPR_NAMES}
        emu.stop_outside = (POOL, POOL)
        emu.exit = None
        emu.mu.emu_start(POOL + hdr["tick"], 0, count=200)
        after = {n: emu.reg(n) for n in vmt.GPR_NAMES}
        top = struct.unpack("<Q", emu.mu.mem_read(after["rsp"], 8))[0]
        return before, after, emu.exit, top

    def window(self, rva, nxt, st):
        emu = self.emu
        vmt.load_state(emu, dict(st, mem_seed=0), 0x1000)
        before = {n: emu.reg(n) for n in vmt.GPR_NAMES}
        emu.stop_outside = (BASE + rva, BASE + rva + 5)
        emu.exit = None
        emu.mu.emu_start(BASE + rva, 0, count=64)
        after = {n: emu.reg(n) for n in vmt.GPR_NAMES}
        return before, after, emu.exit

    def read(self, rnd):
        """what main+13A7D0 reads for the press words: (lo via the lea
        window, hi via the lea window, hi via the mov window), and problems"""
        hdr = self.hdr
        probs = []
        (lea_rva, _o, _c), (mov_rva, _o2, _c2) = hdr["windows"]
        st = vmt.random_state(rnd)
        before, after, exit_ = self.window(lea_rva, lea_rva + 7, st)
        if exit_ != BASE + lea_rva + 7:
            probs.append("the lea window left at %s" % exit_)
        for r in vmt.GPR_NAMES:
            if r != "r8" and after[r] != before[r]:
                probs.append("the lea window changed %s" % r)
        lo, hi1 = struct.unpack("<QQ", self.emu.mu.mem_read(after["r8"], 16))
        st = vmt.random_state(rnd)
        before, after, exit_ = self.window(mov_rva, mov_rva + 7, st)
        if exit_ != BASE + mov_rva + 7:
            probs.append("the mov window left at %s" % exit_)
        for r in vmt.GPR_NAMES:
            if r != "rax" and after[r] != before[r]:
                probs.append("the mov window changed %s" % r)
        return (lo, hi1, after["rax"]), probs


def check_latch(img, hdr, rnd, ticks, broken):
    problems, runs = [], 0
    saved = {"rcx", "rdx", "r8", "r9", "rsp", "rbx", "rbp", "rsi", "rdi", "r12", "r13", "r14",
             "r15"}
    for n in (1, 2, 4):
        for seq in range(3):
            lt = Latch(img, hdr, broken_pool(hdr, broken), n, rnd.getrandbits(32))
            live, armed, disarm_at, reads = [], 0, [], []
            for t in range(ticks):
                # a press on about one tick in five, some of them two ticks
                # apart; the skip check arms and disarms now and then
                lo = rnd.getrandbits(64) if rnd.random() < 0.2 else 0
                hi = rnd.getrandbits(64) if rnd.random() < 0.2 else 0
                if rnd.random() < 0.08:
                    armed = 0 if armed else rnd.choice((1, 1, 0xFF))
                live.append((lo, hi))
                st = vmt.random_state(rnd)
                before, after, exit_, top = lt.tick(lo, hi, armed, st)
                runs += 1
                if exit_ != BASE + hdr["manager"]:
                    problems.append("N=%d tick %d: the tick entry left at %s" % (n, t, exit_))
                    continue
                if top != BASE + hdr["tick_call"] + 5:
                    problems.append("N=%d tick %d: the return address is not on top" % (n, t))
                for r in saved:
                    if after[r] != before[r]:
                        problems.append("N=%d tick %d: the tick entry changed %s" % (n, t, r))
                if t and reads and reads[-1][2] and not armed:
                    disarm_at.append(t)
                got, probs = lt.read(rnd)
                problems += ["N=%d tick %d: %s" % (n, t, p) for p in probs]
                reads.append((got, t, armed))
            # the reads against the live words and the press history
            last_disarm = [max([d for d in disarm_at if d <= t], default=-1)
                           for t in range(ticks)]
            for (lo_r, hi1_r, hi_r), t, _a in reads:
                if hi1_r != hi_r:
                    problems.append("N=%d tick %d: the two windows' upper words differ" % (n, t))
                if n == 1 and (lo_r, hi_r) != live[t]:
                    problems.append("N=1 tick %d: a read differs from the live words" % t)
                # never a press from before the last disarm, nor older than N ticks
                allowed_lo = allowed_hi = 0
                for u in range(max(0, t - n + 1, last_disarm[t]), t + 1):
                    allowed_lo |= live[u][0]
                    allowed_hi |= live[u][1]
                if u := (lo_r & ~allowed_lo) | (hi_r & ~allowed_hi):
                    problems.append("N=%d tick %d: a read holds a press it should not (%X)" %
                                    (n, t, u))
            if n > 1:
                for phase in range(n):
                    seen_lo = {}
                    for (lo_r, hi1_r, hi_r), t, _a in reads:
                        if t % n == phase:
                            seen_lo[t] = (lo_r, hi_r)
                    for t, (lo, hi) in enumerate(live):
                        nxt = t + (phase - t) % n
                        if nxt >= ticks or not (lo or hi):
                            continue
                        if any(t < d <= nxt for d in disarm_at):
                            continue   # a disarm in between forgets it, as it should
                        rl, rh = seen_lo[nxt]
                        if (lo & rl) != lo or (hi & rh) != hi:
                            problems.append("N=%d phase %d: the press of tick %d is missed at "
                                            "tick %d" % (n, phase, t, nxt))
    return problems, runs


def check_selection(img, hdr):
    import survey_task_waits as stw
    import gen_task_waits as gtw
    rows, sproblems = stw.audit()
    want = {(int(r["site"], 16), e) for r, e, _why in gtw.select(rows)}
    got = {(s[0], s[4]) for s in hdr["sites"]}
    problems = ["survey: " + p for p in sproblems]
    problems += ["main+%X (entry %d) should be taken over and is not" % a
                 for a in sorted(want - got)]
    problems += ["main+%X (entry %d) is taken over but the selection does not pick it" % a
                 for a in sorted(got - want)]
    for rva, rel, _t, op, _e in hdr["sites"]:
        b = bytes(img[rva:rva + 5])
        if b[0] != op or struct.unpack_from("<i", b, 1)[0] != rel or \
                rva + 5 + rel != hdr["wait"]:
            problems.append("main+%X is not the call or jump of the wait the header says" % rva)
    b = bytes(img[hdr["tick_call"]:hdr["tick_call"] + 5])
    if b[0] != 0xE8 or struct.unpack_from("<i", b, 1)[0] != hdr["tick_rel"] or \
            hdr["tick_call"] + 5 + hdr["tick_rel"] != hdr["manager"]:
        problems.append("main+%X is not flower_tick's call of the task manager" % hdr["tick_call"])
    for rva, orig, _c in hdr["windows"]:
        if bytes(img[rva:rva + 7]) != orig:
            problems.append("main+%X is not the skip check's read the header says" % rva)
    return problems, len(rows)


def countdown(word):
    ticks = 0
    while True:            # the task manager's step, once a tick
        ticks += 1
        word = (word - 1) & 0xFFFF
        if word == 0:
            return ticks


def check_durations(hdr):
    """The countdown (4566CB: add word [+12], 0xFFFF; wake at 0) on what the
    stub hands on: the pause in real time against stock's, a loop's pass."""
    problems, report = [], []
    lengths = sorted({t for _r, _rel, t, _op, e in hdr["sites"] if t and not e})
    loops = sum(1 for s in hdr["sites"] if s[4])
    for ctx, stock_hz in (("play", 30), ("a 60 Hz menu", 60)):
        for fps in (120, 60):
            n = fps // stock_hz
            if n < 1:
                continue
            worst = 0.0
            for t in lengths:
                ticks = countdown(min(t * n, 0xFFFF) if n > 1 else t)
                d = abs(ticks / fps - t / stock_hz)
                worst = max(worst, d)
                if d > 1e-9:
                    problems.append("a %d-tick pause in %s at %d fps lasts %.4f s, stock %.4f"
                                    % (t, ctx, fps, ticks / fps, t / stock_hz))
            passes = countdown(n if n > 1 else 1)
            if abs(passes / fps - 1 / stock_hz) > 1e-9:
                problems.append("a loop's pass in %s at %d fps lasts %d ticks" % (ctx, fps,
                                                                                 passes))
            report.append("%d lengths (%d to %d ticks) in %s at %d fps: every pause ends "
                          "after its stock time (worst %.1e s); %d loop waits pass once a "
                          "stock tick" % (len(lengths), min(lengths), max(lengths), ctx, fps,
                                          worst, loops))
    return problems, report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--states", type=int, default=400)
    ap.add_argument("--ticks", type=int, default=160)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--break", dest="broken", choices=("n", "cap", "loop", "hist"))
    args = ap.parse_args()
    hdr = parse_header()
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    if hashlib.sha1(raw).hexdigest() != hdr["sha"]:
        sys.exit("main.dll is not the binary the header describes")
    img = bytearray(pefile.PE(data=raw, fast_load=True).get_memory_mapped_image())
    problems, _rows = check_install(args, hdr, path)
    rnd = random.Random(args.seed)
    sprob, sruns = check_entries(img, hdr, rnd, args.states, args.broken)
    problems += sprob
    print("2. entries: %d runs (pause and loop, N = 1, 2, 4), %d problems" % (sruns, len(sprob)))
    lprob, lruns = check_latch(img, hdr, rnd, args.ticks, args.broken)
    problems += lprob
    print("3. skip latch: %d ticks run (N = 1, 2, 4, three sequences each), %d problems" % (
        lruns, len(lprob)))
    cprob, ncalls = check_selection(img, hdr)
    problems += cprob
    print("4. selection: %d calls surveyed, %d taken over (%d loop waits), %d problems" % (
        ncalls, len(hdr["sites"]), sum(1 for s in hdr["sites"] if s[4]), len(cprob)))
    dprob, drep = check_durations(hdr)
    problems += dprob
    print("5. durations: %d problems" % len(dprob))
    for ln in drep:
        print("   " + ln)
    for p in problems[:25]:
        print("   PROBLEM " + p)
    print("\n%s" % ("FAILED: %d problems" % len(problems) if problems else "all checks passed"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
