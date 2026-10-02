#!/usr/bin/env python3
"""Verify the day/night clock family (src/day_clock.h) against the stock game.

The DLL self-test (OkamiDayClockSelfTest) maps main.dll without executing game
code, runs the real installer and dumps what it wrote; it also checks the mask
for every combination of switches, runs the overlay's field watch through a
simulated clock and fails every write in turn. This script then checks the
installed bytes against an independent computation and runs the game's real
day/night update -- the dispatcher's call into thunk 4AF770, the update
4AF780, both workers, the clock adder, 4AF6D0 and 4AFBE0 -- under Unicorn,
stock bytes against patched:

  A. N = 1 (the gate open, the stock game): every register, the flags, every
     byte the update wrote, on random states covering every path (frozen, a
     requested jump, delays, transitions, each blocking flag, no player);
  B. N = 2 and 4, every alignment of the frame counter: the patched update
     over N ticks equals the stock update over one, group by group -- the
     clock, the day counter, the controller except its record of the previous
     time, the value it mirrors into [B321C0]+9C -- and every "did the clock
     cross X since the last update" event (4AF610, ported and cross-checked
     against the real function) fires as often, in the same group;
  C. the one known difference: a jump the game requests between stock ticks
     (+0x30) runs on the next tick, not the next stock tick, so the advance
     after it can come up to N-1 ticks early. The clock is then never more
     than one step (kDayStep) ahead of stock, and never behind.

Each stub's counters (entered, ran) must move exactly as the emulation says.
The requested jump's call goes through a third stub that only counts: in A
the patched update must still equal the stock one bit for bit on every path,
the requested jump included, and in A and C that stub must count each request
the update applies exactly once (the field watch times the time-lapses by it).

    .venv/Scripts/python tools/verify_day_clock.py
    --break gate|jump|ret|counter|request  corrupts one thing; the run must fail
"""
import argparse
import csv
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
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn import UC_HOOK_MEM_UNMAPPED, UC_HOOK_INTR
from unicorn import x86_const as U

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.dirname(HERE)
HDR = os.path.join(ROOT, "src", "day_clock.h")

THUNK, UPDATE, CROSS, HUDQ = 0x4AF770, 0x4AF780, 0x4AF610, 0x3F3260
STATS_PTR, HUD_PTR, PLAYER_PTR = 0xB205C0, 0xB321C0, 0xB6B2D0
# (global, bit) that stop the advance or the transition (4AF800, 4AF910)
BLOCKERS = [(0xB6B2A0, 20), (0xB6B2A4, 29), (0xB6B2A4, 13), (0xB6ACC4, 24), (0xB6B2B8, 4),
            (0xB6B2B8, 19), (0xB6B2BC, 19), (0xB6B2AC, 29), (0xB6B2AC, 30), (0xB6B2AC, 25)]
STACK, STACK_SIZE = 0x10000000, 0x10000
FAKE = 0x20000000  # STATS, HUD, PLAYER (2 pages), PLAYER+A8 target
STATS, HUD, PLAYER, PA8 = FAKE, FAKE + 0x1000, FAKE + 0x2000, FAKE + 0x4000
GPRS = ["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "r8", "r9", "r10", "r11",
        "r12", "r13", "r14", "r15"]
REG = {n: getattr(U, "UC_X86_REG_" + n.upper()) for n in GPRS}
SAVED = ["rbx", "rbp", "rsi", "rdi", "r12", "r13", "r14", "r15"]


def parse_header(path=HDR):
    text = open(path, encoding="utf-8").read()

    def const(name):
        return int(re.search(r"\b%s\s*=\s*(0x[0-9a-fA-F]+|\d+)" % name, text).group(1), 0)

    def block(name):
        return re.search(r"\b%s\[\]\s*=\s*\{(.*?)\n\};" % name, text, re.S).group(1)

    def raw(name):
        return bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})\b", block(name)))

    sites = [(int(a, 16), int(b, 16), int(c, 16), r) for a, b, c, r in re.findall(
        r'\{0x([0-9A-F]+), 0x([0-9A-F]+), 0x([0-9A-F]+), "(\w+)"\}', block("kDayClockSites"))]
    fix = [tuple(int(v, 16) for v in f) for f in re.findall(
        r"\{0x([0-9A-F]+), 0x([0-9A-F]+), 0x([0-9A-F]+)\}", block("kDayClockFixups"))]
    return dict(sha=re.search(r'DAY_CLOCK_MAIN_SHA1\s+"([0-9a-f]+)"', text).group(1),
                clock=const("kDayClockRva"), days=const("kDayCountRva"),
                ctrl=const("kDayControllerRva"), count=const("kDayCountOff"),
                target=const("kDayTargetOff"), delay=const("kDayDelayOff"),
                units=const("kDayUnits"), step=const("kDayStep"), fc=const("kDayFrameCounterRva"),
                mask=const("kDayMaskOffset"), counters=const("kDayCounterOffset"),
                code_off=const("kDayCodeOffset"), pool_size=const("kDayPoolSize"),
                code=raw("kDayClockCode"), orig=raw("kDayClockOrig"), sites=sites, fixups=fix)


def pool_bytes(h, main, pool):
    out = bytearray(h["pool_size"])
    out[h["code_off"]:h["code_off"] + len(h["code"])] = h["code"]
    for field, nxt, target in h["fixups"]:
        struct.pack_into("<i", out, field, main + target - (pool + nxt))
    return bytes(out)


def jump_bytes(h, main, pool):
    """Each site's own opcode (jmp for a tail jump, call for the request) at its stub."""
    return [h["orig"][5 * i:5 * i + 1] + struct.pack("<i", pool + stub - (main + rva + 5))
            for i, (rva, _t, stub, _r) in enumerate(h["sites"])]


def crossed(rec8, rec4, clock, x, units):
    """4AF610: did the clock pass x (a time of day) since the update's record?"""
    if rec8 >= clock:
        return False
    x, cur = x % units, clock % units
    if cur >= rec4:
        return rec4 < x <= cur
    return x <= cur or x > rec4


class Emu:
    def __init__(self, h, img, main, pool=None, code=None, jumps=None):
        self.h, self.main, self.pool = h, main, pool
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_64)
        size = (len(img) + 0xFFF) & ~0xFFF
        mu.mem_map(main, size)
        mu.mem_write(main, bytes(img))
        mu.mem_write(main + HUDQ, b"\xB0\x00\xC3")  # the HUD query: mov al, imm; ret
        mu.mem_map(STACK, STACK_SIZE)
        mu.mem_map(FAKE, 0x5000)
        self.ret = STACK + 0x100  # never executed: emu_start stops there
        if pool is not None:
            mu.mem_map(pool, (len(code) + 0xFFF) & ~0xFFF)  # its own pages: blocks are packed
            mu.mem_write(pool, code)
            for (rva, _t, _s, _r), j in zip(h["sites"], jumps):
                mu.mem_write(main + rva, j)
        self.writes = set()
        self.visits = []
        self.err = None
        mu.hook_add(UC_HOOK_MEM_WRITE, self._write)
        mu.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)
        mu.hook_add(UC_HOOK_INTR, self._intr)
        watch = [main + t for _r, t, _s, _n in h["sites"]]
        if pool is not None:
            watch += [pool + s for _r, _t, s, _n in h["sites"]]
        for a in watch:
            mu.hook_add(UC_HOOK_CODE, self._visit, begin=a, end=a)

    def _write(self, uc, access, addr, size, value, data):
        if not (STACK <= addr < STACK + STACK_SIZE):
            for k in range(size):
                self.writes.add(addr + k)

    def _unmapped(self, uc, access, addr, size, value, data):
        self.err = "unmapped access at %X" % addr
        return False

    def _intr(self, uc, intno, data):
        self.err = "interrupt %d at %X" % (intno, uc.reg_read(U.UC_X86_REG_RIP))
        uc.emu_stop()

    def _visit(self, uc, addr, size, data):
        self.visits.append(addr)

    def u32(self, a):
        return struct.unpack("<I", bytes(self.mu.mem_read(a, 4)))[0]

    def put(self, a, fmt, v):
        self.mu.mem_write(a, struct.pack(fmt, v))

    def set_state(self, st):
        h, m, mu = self.h, self.main, self.mu
        mu.mem_write(m + h["ctrl"], st["ctrl"])
        self.put(m + h["clock"], "<I", st["clock"])
        self.put(m + h["days"], "<H", st["days"])
        for a in {g for g, _b in BLOCKERS}:
            self.put(m + a, "<I", st["globals"].get(a, 0))
        self.put(m + STATS_PTR, "<Q", STATS)
        self.put(m + HUD_PTR, "<Q", HUD)
        self.put(m + PLAYER_PTR, "<Q", PLAYER if st["player"] else 0)
        self.put(STATS + 0x360, "<I", st["frozen"])
        self.put(PLAYER + 0xA8, "<Q", PA8)
        self.put(PA8 + 4, "<f", 1.0)
        self.put(PLAYER + 0xE50, "<f", 1.0 if st["grounded"] else 2.0)
        mu.mem_write(m + HUDQ + 1, bytes([st["hudq"]]))
        self.regs = st["regs"]

    def tick(self, fc):
        mu, m = self.mu, self.main
        self.put(m + self.h["fc"], "<I", fc & 0xFFFFFFFF)
        for n in GPRS:
            mu.reg_write(REG[n], self.regs[n])
        mu.reg_write(U.UC_X86_REG_RCX, m + self.h["ctrl"])
        rsp = STACK + 0x8000 - 8  # at a call: 16-aligned before the return address
        mu.reg_write(U.UC_X86_REG_RSP, rsp)
        self.put(rsp, "<Q", self.ret)
        mu.reg_write(U.UC_X86_REG_EFLAGS, 0x202 | self.regs["flags"])
        self.writes, self.visits, self.err = set(), [], None
        try:
            mu.emu_start(m + THUNK, self.ret, count=20000)
        except UcError as e:
            self.err = self.err or str(e)
        pc = mu.reg_read(U.UC_X86_REG_RIP)
        if not self.err and pc != self.ret:
            self.err = "stopped at %X" % pc
        out = {n: mu.reg_read(REG[n]) for n in GPRS}
        out["flags"] = mu.reg_read(U.UC_X86_REG_EFLAGS) & 0x8D5
        if not self.err:
            if out["rsp"] != rsp + 8:
                self.err = "rsp %X at return, want %X" % (out["rsp"], rsp + 8)
            for n in SAVED:
                if out[n] != self.regs[n]:
                    self.err = "%s not preserved" % n
        return out

    def world(self):
        """What the day clock is, apart from the update's record of the previous time."""
        h, m = self.h, self.main
        c = bytearray(self.mu.mem_read(m + h["ctrl"], 0x40))
        c[4:0xC] = b"\0" * 8
        return (self.u32(m + h["clock"]), bytes(self.mu.mem_read(m + h["days"], 2)), bytes(c),
                self.u32(HUD + 0x9C), self.u32(STATS + 0x360))

    def record(self):
        c = self.main + self.h["ctrl"]
        return self.u32(c + 8), self.u32(c + 4), self.u32(self.main + self.h["clock"])

    def counters(self):
        n = 2 * len(self.h["sites"])
        return struct.unpack("<%dI" % n, bytes(self.mu.mem_read(self.pool + self.h["counters"], 4 * n)))


def random_state(rng, h, jump_ok=True):
    units, step = h["units"], h["step"]
    thresholds = [180000, 900000, 1170000, 1350000, 1710000, 0, 1707000, 1440000]
    day = rng.randrange(0, 40)
    pick = rng.random()
    if pick < 0.5:
        tod = (rng.choice(thresholds) - rng.randrange(0, 40) * step - rng.randrange(0, step)) % units
    else:
        tod = rng.randrange(units)
    clock = day * units + tod
    ctrl = bytearray(0x40)
    flags0 = rng.choice([0, 0, 0, 4, 1, 2, 8, rng.getrandbits(4)])
    struct.pack_into("<I", ctrl, 0, flags0)
    struct.pack_into("<Q", ctrl, 0x10, rng.choice([0, 0x1111]))
    struct.pack_into("<Q", ctrl, 0x18, rng.choice([0, 0x2222]))
    count = rng.choice([0] * 5 + [rng.randrange(1, 100)])
    struct.pack_into("<H", ctrl, h["count"], count)
    struct.pack_into("<I", ctrl, h["target"], (clock + rng.randrange(0, 2 * units)) & 0xFFFFFFFF)
    jump = jump_ok and rng.random() < 0.08
    ctrl[0x30] = 1 if jump else 0
    struct.pack_into("<I", ctrl, 0x2C, clock + rng.randrange(0, units))
    struct.pack_into("<I", ctrl, h["delay"], rng.choice([0] * 5 + [1, 2, 3]))
    struct.pack_into("<I", ctrl, 8, rng.getrandbits(32))
    struct.pack_into("<I", ctrl, 4, rng.getrandbits(32))
    glob = {}
    if rng.random() < 0.2:
        g, b = rng.choice(BLOCKERS)
        glob[g] = 1 << b
    regs = {n: rng.getrandbits(64) for n in GPRS}
    regs["flags"] = rng.choice([0, 1, 0x40, 0x80, 0x801, 0x8D5])
    return dict(ctrl=bytes(ctrl), clock=clock, days=rng.randrange(0x10000), globals=glob,
                player=rng.random() < 0.9, grounded=rng.random() < 0.85,
                frozen=0x4000000 if rng.random() < 0.05 else 0,
                hudq=1 if rng.random() < 0.1 else 0, regs=regs)


def self_test(args, h, path):
    work = args.out or tempfile.mkdtemp(prefix="okami_day_clock_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiDayClockSelfTest
    fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    print(report.rstrip())
    vals = dict(ln.split(None, 1) for ln in report.splitlines() if len(ln.split()) == 2)
    return rc, work, int(vals.get("main", "0"), 16), int(vals.get("pool", "0"), 16)


def check_modes(path):
    bad, rows = [], list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        fps, mode = int(r["fps"]), int(r["mode"])
        on = (int(r["enabled"]) and not int(r["muted"]) and fps > 30 and mode in (1, 2)
              and int(r["shadow"]) and int(r["hook"]) and int(r["complete"]))
        want = fps // (60 if mode == 1 else 30) - 1 if on else 0
        if int(r["mask"]) != want:
            bad.append("mask %s, want %d for %s" % (r["mask"], want, dict(r)))
    print("runtime mask: %d cases, %d wrong" % (len(rows), len(bad)))
    return bad if rows else ["no mask cases"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--states", type=int, default=160)
    ap.add_argument("--groups", type=int, default=48)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--break", dest="broken", choices=("gate", "jump", "ret", "counter", "request"))
    args = ap.parse_args()
    h = parse_header()
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    if hashlib.sha1(raw).hexdigest() != h["sha"]:
        sys.exit("main.dll is not the binary src/day_clock.h was generated from")
    problems = []
    rc, work, main_base, pool = self_test(args, h, path)
    if rc:
        return 1
    code = open(os.path.join(work, "pool.bin"), "rb").read()
    if code != pool_bytes(h, main_base, pool):
        problems.append("installed pool differs from the independently relocated header")
    got = open(os.path.join(work, "sites.bin"), "rb").read()
    jumps = jump_bytes(h, main_base, pool)
    if got != b"".join(jumps):
        problems.append("installed tail jumps differ from the expected rel32s")
    problems += check_modes(os.path.join(work, "modes.csv"))
    pe = pefile.PE(data=raw)
    pe.relocate_image(main_base)
    img = bytearray(pe.get_memory_mapped_image())
    for i, (rva, target, _s, _r) in enumerate(h["sites"]):
        if img[rva:rva + 5] != h["orig"][5 * i:5 * i + 5] or \
                struct.unpack_from("<i", img, rva + 1)[0] != target - (rva + 5):
            problems.append("original tail jump mismatch at main+%X" % rva)

    code = bytearray(code)
    if args.broken == "jump":
        j = bytearray(jumps[0])
        struct.pack_into("<i", j, 1, struct.unpack_from("<i", j, 1)[0] + 1)
        jumps[0] = bytes(j)
    if args.broken == "ret":
        s0 = h["sites"][0][2]
        assert code[s0 + 33] == 0xC3
        code[s0 + 33] = 0x90
    if args.broken == "counter":
        s0 = h["sites"][0][2]
        assert code[s0 + 22:s0 + 24] == b"\xFF\x05"
        code[s0 + 22:s0 + 28] = b"\x90" * 6
    if args.broken == "request":
        # the request's stub stops counting
        sr = next(s for _r, _t, s, role in h["sites"] if role == "request")
        assert code[sr:sr + 2] == b"\xFF\x05"
        code[sr:sr + 6] = b"\x90" * 6
    orig = Emu(h, img, main_base)
    pat = Emu(h, img, main_base, pool, bytes(code), jumps)
    stub_entry = {pool + s: i for i, (_r, _t, s, _n) in enumerate(h["sites"])}
    worker_entry = {main_base + t: i for i, (_r, t, _s, _n) in enumerate(h["sites"])}
    req_site = next(i for i, (_r, _t, _s, role) in enumerate(h["sites"]) if role == "request")
    units = h["units"]
    xs = [180000, 270000, 900000, 990000, 1170000, 1260000, 1350000, 1440000, 1710000,
          1800000, 1707000, 1710000, 1709900]

    def set_mask(n):
        pat.mu.mem_write(pool + h["mask"], bytes([0 if args.broken == "gate" else n - 1]))

    def expect_counters(before, visits_list, fcs, n):
        """Each tick that reached a tail jump enters its stub once; it runs the
        worker when the tick is a stock tick. Each requested jump the update
        applies enters the request's stub once, on any tick, and nothing else."""
        want = list(before)
        for visits, fc in zip(visits_list, fcs):
            for a in visits:
                if a in stub_entry:
                    i = stub_entry[a]
                    want[2 * i] += 1
                    if (fc & (n - 1)) == 0 and h["sites"][i][3] != "request":
                        want[2 * i + 1] += 1
        return [w & 0xFFFFFFFF for w in want]

    # ---- the port of 4AF610 against the real function -----------------
    rng = random.Random(args.seed)
    port_bad = 0
    for _ in range(2000):
        rec8, rec4 = rng.getrandbits(32), rng.randrange(units)
        clock = rng.choice([rec8 + rng.randrange(0, 5000), rng.getrandbits(32)]) & 0xFFFFFFFF
        x = rng.choice(xs + [rng.getrandbits(32), clock % units, rec4])
        mu = orig.mu
        orig.put(main_base + h["clock"], "<I", clock)
        orig.put(main_base + h["ctrl"] + 8, "<I", rec8)
        orig.put(main_base + h["ctrl"] + 4, "<I", rec4)
        mu.reg_write(U.UC_X86_REG_RCX, main_base + h["ctrl"])
        mu.reg_write(U.UC_X86_REG_RDX, x)
        mu.reg_write(U.UC_X86_REG_RSP, STACK + 0x8000 - 8)
        orig.put(STACK + 0x8000 - 8, "<Q", orig.ret)
        mu.emu_start(main_base + CROSS, orig.ret, count=100)
        if bool(mu.reg_read(U.UC_X86_REG_RAX) & 0xFF) != crossed(rec8, rec4, clock, x, units):
            port_bad += 1
    print("4AF610 port: 2000 cases, %d differ" % port_bad)
    if port_bad:
        problems.append("the port of 4AF610 differs from the real function in %d cases" % port_bad)

    # ---- A: the gate open is the stock game --------------------------------
    set_mask(1)
    paths = {}
    for k in range(args.states):
        st = random_state(rng, h)
        fc = rng.getrandbits(32)
        orig.set_state(st)
        pat.set_state(st)
        c0 = pat.counters()
        ro, rp = orig.tick(fc), pat.tick(fc)
        if orig.err or pat.err:
            problems.append("A%d: %s / %s" % (k, orig.err, pat.err))
            continue
        diff = [n for n in ro if ro[n] != rp[n]]
        touched = sorted(orig.writes | (pat.writes - set(range(pool, pool + 0x10000))))
        mem = [a for a in touched
               if orig.mu.mem_read(a, 1) != pat.mu.mem_read(a, 1)]
        worker = sorted({worker_entry[a] for a in orig.visits if a in worker_entry})
        pworker = sorted({worker_entry[a] for a in pat.visits if a in worker_entry})
        if diff or mem or worker != pworker:
            problems.append("A%d: registers %s, %d bytes differ (first %s), workers %s vs %s" % (
                k, diff, len(mem), "%X" % mem[0] if mem else "-", worker, pworker))
        c1 = pat.counters()
        if list(c1) != expect_counters(c0, [pat.visits], [0], 1):
            problems.append("A%d: counters %s -> %s" % (k, c0, c1))
        key = ("frozen" if st["frozen"] else "jump" if st["ctrl"][0x30] else
               ("transition" if worker == [1] else "advance" if worker == [0] else "none"))
        paths[key] = paths.get(key, 0) + 1
    print("A. N=1: %d states, paths %s" % (args.states, paths))

    # ---- B: N ticks of the patched update are one stock tick ----------------
    groups_checked = crossings = transitions_done = 0
    for n in (2, 4):
        for k in range(args.states // 4):
            st = random_state(rng, h, jump_ok=False)
            for r in range(n):
                orig.set_state(st)
                pat.set_state(st)
                set_mask(n)
                fc0 = (rng.getrandbits(30) * n + r) & 0xFFFFFFFF
                had_count = struct.unpack_from("<H", st["ctrl"], h["count"])[0]
                for g in range(args.groups):
                    orig.tick(g)
                    ref_hits = [crossed(*orig.record(), x, units) for x in xs]
                    hits = [0] * len(xs)
                    c0, visits, fcs = pat.counters(), [], []
                    for s in range(n):
                        fc = fc0 + g * n + s
                        pat.tick(fc)
                        visits.append(pat.visits)
                        fcs.append(fc)
                        for i, x in enumerate(xs):
                            hits[i] += crossed(*pat.record(), x, units)
                        if pat.err:
                            break
                    if orig.err or pat.err:
                        problems.append("B N%d state %d align %d group %d: %s / %s" % (
                            n, k, r, g, orig.err, pat.err))
                        break
                    groups_checked += 1
                    crossings += sum(ref_hits)
                    if orig.world() != pat.world():
                        ow, pw = orig.world(), pat.world()
                        problems.append("B N%d state %d align %d group %d: clock %d vs %d%s" % (
                            n, k, r, g, ow[0], pw[0], "" if ow[1:] == pw[1:] else ", controller/day differ"))
                        break
                    if [int(b) for b in ref_hits] != hits:
                        problems.append("B N%d state %d align %d group %d: crossings %s vs %s" % (
                            n, k, r, g, [int(b) for b in ref_hits], hits))
                        break
                    if list(pat.counters()) != expect_counters(c0, visits, fcs, n):
                        problems.append("B N%d state %d align %d group %d: counters" % (n, k, r, g))
                        break
                    if len(problems) > 20:
                        break
                if had_count and struct.unpack_from(
                        "<H", bytes(orig.mu.mem_read(main_base + h["ctrl"] + h["count"], 2)))[0] == 0:
                    transitions_done += 1
                if len(problems) > 20:
                    break
    # whole sky changes, as the tracer saw them (90 steps), after a 2-tick delay
    for n in (2, 4):
        for r in range(n):
            st = random_state(rng, h, jump_ok=False)
            c = bytearray(st["ctrl"])
            struct.pack_into("<H", c, h["count"], 90)
            struct.pack_into("<I", c, h["delay"], 2)
            target = st["clock"] - st["clock"] % units + 1350000 + units
            struct.pack_into("<I", c, h["target"], target)
            st.update(ctrl=bytes(c), globals={}, frozen=0, player=True, grounded=True, hudq=0)
            orig.set_state(st)
            pat.set_state(st)
            set_mask(n)
            fc0 = (rng.getrandbits(30) * n + r) & 0xFFFFFFFF
            for g in range(95):
                orig.tick(g)
                for s in range(n):
                    pat.tick(fc0 + g * n + s)
                if orig.world() != pat.world() or orig.err or pat.err:
                    problems.append("B sky change N%d align %d: differs at group %d" % (n, r, g))
                    break
                groups_checked += 1
            else:
                left = struct.unpack("<H", bytes(pat.mu.mem_read(main_base + h["ctrl"] + h["count"], 2)))[0]
                if left or pat.world()[0] != target + 3 * h["step"]:
                    problems.append("B sky change N%d align %d: %d steps left, clock %d, want %d" % (
                        n, r, left, pat.world()[0], target + 3 * h["step"]))
                transitions_done += 1
    print("B. N=2,4: %d groups equal to stock, %d crossings each fired once in its group, "
          "%d transitions run to the end" % (groups_checked, crossings, transitions_done))

    # ---- C: a jump requested between stock ticks ----------------------------
    worst = 0
    jumped = 0
    for n in (2, 4):
        for k in range(args.states // 8):
            st = random_state(rng, h, jump_ok=False)
            c = bytearray(st["ctrl"])
            c[0x30] = 1
            struct.pack_into("<H", c, h["count"], 0)
            struct.pack_into("<I", c, h["delay"], 0)
            st["ctrl"] = bytes(c)
            st["frozen"] = 0
            for r in range(n):
                orig.set_state(st)
                pat.set_state(st)
                set_mask(n)
                fc0 = (rng.getrandbits(30) * n + r) & 0xFFFFFFFF
                applied = pat.counters()[2 * req_site]
                for g in range(16):
                    orig.tick(g)
                    for s in range(n):
                        pat.tick(fc0 + g * n + s)
                    d = (pat.world()[0] - orig.world()[0]) & 0xFFFFFFFF
                    if d > h["step"] or orig.err or pat.err:
                        problems.append("C N%d align %d group %d: patched clock %+d from stock" % (
                            n, r, g, d if d < 0x80000000 else d - 0x100000000))
                        break
                    worst = max(worst, d)
                # the one request, applied once, and counted once by its stub
                got = (pat.counters()[2 * req_site] - applied) & 0xFFFFFFFF
                if got != 1:
                    problems.append("C N%d align %d: the request stub counted %d, want 1" % (
                        n, r, got))
                jumped += 1
    print("C. %d requested jumps between stock ticks: the clock at most %d ahead of stock "
          "(one step is %d)" % (jumped, worst, h["step"]))

    for p in problems[:25]:
        print("  FAIL " + p)
    print("FAILED (%d)" % len(problems) if problems else "day clock verified")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
