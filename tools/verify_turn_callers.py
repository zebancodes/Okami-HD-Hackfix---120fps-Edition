#!/usr/bin/env python3
"""Prove the turn-rate fix offline, by the heading gap it leaves.

The measure is the one that defines the fix: from a fixed facing and target,
the gap left after 1/ts updates of the installed angular approach must be the
gap one stock update leaves (the original function, stock mode byte 2, the
shipped table), whatever the caller passes.

1. Loads the built DLL into this process and calls its OkamiTurnRateSelfTest
   export, which maps main.dll without running any of it, runs the real
   installs of the mode constants and the turn rate, and writes the cave, the
   patched bytes and what the watcher's updates leave -- the square-root count,
   the private pairs, the real table -- at 30, 60 and 120 fps, and with the
   movement fixes muted.

2. Recomputes here what the installed bytes must be: the hook's jump, every
   table read's displacement (at its private pair), every bypassed call's
   rel32 (at the relocated prologue).

3. Emulates under Unicorn, main.dll mapped where the DLL loaded it and the cave
   where the DLL allocated it, in every state:

     * every table read as installed: converting, it must read the stock g;
       not converting, exactly what the original read reads in that state;
     * the gap for every table caller's coefficient (all 37 reads, through
       the installed read) and every distinct constant a convert caller passes;
     * two call sites end to end, from the code that builds k to the store of
       the new facing: the jump handler's airborne steering (3B5518..3B554C,
       the caller the review named, a table read) and the player's ground
       turn (3A7378..3A739D, an unscaled constant);
     * every bypassed call as installed: the original function's result with
       the same k, unconverted, even with the hook converting.

    .venv/Scripts/python tools/verify_turn_callers.py [--dll .build/bin/dinput8.dll]
    --break table    emulate the original table reads (the double scaling)
    --break bypass   emulate the original bypassed calls
each of which must then FAIL. Exits non-zero on any mismatch.
"""
import argparse
import csv
import ctypes
import hashlib
import math
import os
import re
import shutil
import struct
import sys
import tempfile

try:
    import capstone
    import pefile
    from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL
    from unicorn import x86_const as U
except ImportError:
    sys.exit("needs pefile, capstone and unicorn: pip install pefile capstone unicorn")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
HDR = os.path.join(ROOT, "src", "turn_callers.h")
CSV = os.path.join(ROOT, "docs", "animation", "turn_callers.csv")
TURN = 0x2DA510
TURN_ORIG = bytes([0x48, 0x83, 0xEC, 0x58, 0x0F, 0x29, 0x74, 0x24, 0x40])
MODE = 0xB6AC45
HEADING = 0xB6B134          # the target heading both end-to-end sites read
PAGE = 0x1000
STACK = 0x7F0000000
SENTINEL = 0x7E0000000      # a return address nothing maps
TOL = 2e-4                  # relative, on the gap: float32 through 1 or 4 updates
XMM = {i: getattr(U, "UC_X86_REG_XMM%d" % i) for i in range(16)}
GPR = {n: getattr(U, "UC_X86_REG_" + n.upper()) for n in
       "rax rbx rcx rdx rsi rdi rbp rsp r8 r9 r10 r11 r12 r13 r14 r15".split()}
FACING, TARGET = -0.3, 2.1  # a gap of 2.4 rad, inside the wrap and well away from PI


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def fbits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def bitsf(u):
    return struct.unpack("<f", struct.pack("<I", u & 0xFFFFFFFF))[0]


def wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a <= -math.pi:
        a += 2 * math.pi
    return a


def parse_header():
    h = open(HDR, encoding="utf-8").read()
    entries = [int(x, 16) for x in re.findall(r"^\s+0x([0-9A-F]+),  // stock g", h, re.M)]
    reads = []
    for g in re.finditer(r"\{0x([0-9A-F]+), (\d+), (\d+), (\d), (\d+), \{([^}]*)\}\},", h):
        n = int(g.group(2))
        reads.append(dict(rva=int(g.group(1), 16), len=n, disp_off=int(g.group(3)),
                          rip=int(g.group(4)), pair=int(g.group(5)),
                          orig=bytes(int(b, 16) for b in g.group(6).split(","))[:n]))
    bypass = []
    for g in re.finditer(r"\{0x([0-9A-F]+), \{(0x[0-9A-F]{2}(?:, 0x[0-9A-F]{2}){4})\}\},", h):
        bypass.append(dict(rva=int(g.group(1), 16),
                           orig=bytes(int(b, 16) for b in g.group(2).split(","))))
    sha = re.search(r'TURN_CALLERS_MAIN_SHA1 "([0-9a-f]+)"', h).group(1)
    return entries, reads, bypass, sha


class Machine:
    def __init__(self, img, main, cave, cave_bytes):
        self.main = main
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        size = (len(img) + PAGE - 1) & ~(PAGE - 1)
        mu.mem_map(main, size, UC_PROT_ALL)
        mu.mem_write(main, bytes(img))
        self.image = bytes(img)
        mu.mem_map(cave, len(cave_bytes), UC_PROT_ALL)
        mu.mem_write(cave, cave_bytes)
        mu.mem_map(STACK - 0x10000, 0x20000, UC_PROT_ALL)
        mu.mem_map(STACK + 0x100000, PAGE, UC_PROT_ALL)   # scratch objects
        self.obj = STACK + 0x100000

    def w32(self, a, v):
        self.mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))

    def wf(self, a, x):
        self.mu.mem_write(a, struct.pack("<f", x))

    def rf(self, a):
        return struct.unpack("<f", bytes(self.mu.mem_read(a, 4)))[0]

    def code(self, a, raw):
        self.mu.mem_write(a, bytes(raw))
        self.mu.ctl_flush_tb()

    def run(self, start, until, regs=None, xmm=None, push_ret=False, count=0):
        mu = self.mu
        rsp = STACK - 0x800
        if push_ret:
            rsp -= 8
            mu.mem_write(rsp, struct.pack("<Q", SENTINEL))
            until = SENTINEL
        for r in GPR.values():
            mu.reg_write(r, 0)
        mu.reg_write(U.UC_X86_REG_RSP, rsp)
        for n, v in (regs or {}).items():
            mu.reg_write(GPR[n], v)
        for i in range(16):
            mu.reg_write(XMM[i], 0)
        for i, v in (xmm or {}).items():
            mu.reg_write(XMM[i], fbits(v))
        mu.reg_write(U.UC_X86_REG_EFLAGS, 2)
        mu.emu_start(start, until, count=count)
        return mu

    def xmmf(self, i):
        return bitsf(self.mu.reg_read(XMM[i]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    ap.add_argument("--break", dest="brk", default=None, choices=("table", "bypass"),
                    help="emulate the unfixed code at those sites; the run must then FAIL")
    args = ap.parse_args()

    entries, reads, bypass, hsha = parse_header()
    path = os.path.join(GAME, "main.dll")
    sha = hashlib.sha1(open(path, "rb").read()).hexdigest()
    if sha != hsha:
        sys.exit("main.dll sha1 %s is not the build turn_callers.h was generated from (%s)"
                 % (sha, hsha))
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    fails = 0

    # 1. the DLL's own installs
    work = args.out or tempfile.mkdtemp(prefix="okami_turn_selftest_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiTurnRateSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    fn.restype = ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    print("DLL self-test (rc %d): %s" % (rc, report.strip().splitlines()[-1]))
    if rc != 0:
        print(report)
        return 1
    v = {p[0]: int(p[1], 16) for p in (ln.split() for ln in report.splitlines())
         if len(p) == 2 and p[0] in ("main", "cave", "stub", "plain", "pairs", "count", "one",
                                     "zero")}
    base, cave = v["main"], v["cave"]
    cave_bytes = open(os.path.join(work, "cave.bin"), "rb").read()
    states = list(csv.DictReader(open(os.path.join(work, "states.csv"))))
    pe = pefile.PE(path, fast_load=True)
    pe.relocate_image(base)
    img = bytearray(pe.get_memory_mapped_image())
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    # 2. the installed bytes, against an independent computation
    blob = open(os.path.join(work, "sites.bin"), "rb").read()
    wrong = []
    rel = struct.pack("<i", v["stub"] - (base + TURN + 5))
    want_hook = b"\xE9" + rel + b"\x90" * (len(TURN_ORIG) - 5)
    pos = len(TURN_ORIG)
    if blob[:pos] != want_hook:
        wrong.append("hook")
    installed = {}
    for r in reads:
        got = blob[pos:pos + r["len"]]
        pos += r["len"]
        pair = v["pairs"] + 8 * r["pair"]
        d = pair - (base + r["rva"] + r["len"]) if r["rip"] else pair - base
        want = bytearray(r["orig"])
        want[r["disp_off"]:r["disp_off"] + 4] = struct.pack("<i", d)
        if got != bytes(want):
            wrong.append("read %X" % r["rva"])
        installed[r["rva"]] = got
    for b in bypass:
        got = blob[pos:pos + 5]
        pos += 5
        want = b["orig"][:1] + struct.pack("<i", v["plain"] - (base + b["rva"] + 5))
        if got != want:
            wrong.append("bypass %X" % b["rva"])
        installed[b["rva"]] = got
    plain_code = cave_bytes[v["plain"] - cave:v["plain"] - cave + len(TURN_ORIG) + 5]
    want_plain = TURN_ORIG + b"\xE9" + struct.pack(
        "<i", base + TURN + len(TURN_ORIG) - (v["plain"] + len(TURN_ORIG) + 5))
    if plain_code != want_plain:
        wrong.append("the relocated prologue")
    print("installed bytes: hook, %d table reads, %d bypassed calls, the plain entry:"
          " %d differ%s" % (len(reads), len(bypass), len(wrong),
                             (": " + ", ".join(wrong[:6])) if wrong else ""))
    fails += len(wrong)
    if args.brk == "table":
        for r in reads:
            installed[r["rva"]] = r["orig"]
    elif args.brk == "bypass":
        for b in bypass:
            installed[b["rva"]] = b["orig"]

    for a, raw in [(base + TURN, blob[:len(TURN_ORIG)])] + \
            [(base + r["rva"], installed[r["rva"]]) for r in reads] + \
            [(base + b["rva"], installed[b["rva"]]) for b in bypass]:
        img[a - base:a - base + len(raw)] = raw
    m = Machine(img, base, cave, cave_bytes)
    shipped = {e: struct.unpack_from("<f", m.image, e)[0] for e in entries}
    stock_g = {e: struct.unpack_from("<f", m.image, e + 4)[0] for e in entries}

    def load_state(st):
        m.mu.mem_write(v["count"], bytes([int(st["count"])]))
        for i, e in enumerate(entries):
            m.w32(v["pairs"] + 8 * i, int(st["fast%d" % i], 16))
            m.w32(v["pairs"] + 8 * i + 4, int(st["stock%d" % i], 16))
            m.w32(base + e, int(st["table%d" % i], 16))
        m.mu.mem_write(base + MODE, bytes([2 if st["fps"] == "30" else 1]))

    def stock_world():
        """the unpatched game at 30 fps: original bytes, shipped table, mode 2"""
        m.code(base + TURN, TURN_ORIG)
        for r in reads:
            m.code(base + r["rva"], r["orig"])
        for b in bypass:
            m.code(base + b["rva"], b["orig"])
        for e in entries:
            m.wf(base + e, shipped[e])
        m.mu.mem_write(base + MODE, b"\x02")

    def patched_world(st):
        m.code(base + TURN, blob[:len(TURN_ORIG)])
        for r in reads:
            m.code(base + r["rva"], installed[r["rva"]])
        for b in bypass:
            m.code(base + b["rva"], installed[b["rva"]])
        load_state(st)

    def approach(k, facing, target=TARGET, entry=TURN):
        m.run(base + entry, None, xmm={0: target, 1: facing, 2: k}, push_ret=True)
        return m.xmmf(0)

    def read_value(r):
        """what a table read (as currently in memory) leaves in its register"""
        a = base + r["rva"]
        ins = list(md.disasm(bytes(m.mu.mem_read(a, 32)), a, count=2))
        load = ins[1] if r["rip"] else ins[0]
        memop = [o for o in load.operands if o.type == capstone.x86_const.X86_OP_MEM][0]
        mode = bytes(m.mu.mem_read(base + MODE, 1))[0]
        regs = {load.reg_name(memop.mem.index): mode - 1}     # movsxd'd: a 64-bit index
        if not r["rip"]:
            regs[load.reg_name(memop.mem.base)] = base         # the image base
        m.run(a, load.address + load.size, regs=regs)
        return m.xmmf(int(load.reg_name(load.operands[0].reg)[3:]))

    def same_gap(gap, want):
        if abs(want) < 1e-6:                                   # k = 1: a snap
            return abs(gap) < 1e-6
        return abs(gap / want - 1.0) <= TOL

    ticks = {"30": 1, "60": 2, "120": 4}

    # 3a/3b. every table read, and the gap its caller's coefficient leaves
    stock_world()
    stock_read = {r["rva"]: read_value(r) for r in reads}
    stock_gap = {}
    for r in reads:
        k = f32(stock_read[r["rva"]] - 1.0)
        stock_gap[r["rva"]] = wrap(TARGET - approach(k, FACING))
    consts = sorted({float(re.match(r"([0-9.e-]+)@", row["coefficient"]).group(1))
                     for row in rows if row["cls"] == "convert" and
                     re.match(r"[0-9.e-]+@[0-9A-F]+$", row["coefficient"])})
    stock_const = {k: wrap(TARGET - approach(f32(k), FACING)) for k in consts}
    bad_reads, bad_gaps, checked = [], [], 0
    for st in states:
        muted = st["muted"] == "1"
        converting = int(st["count"]) != 0
        n = ticks[st["fps"]]
        # the original read in this state, for the transparency check
        patched_world(st)
        orig_read = {}
        for r in reads:
            m.code(base + r["rva"], r["orig"])
            orig_read[r["rva"]] = read_value(r)
            m.code(base + r["rva"], installed[r["rva"]])
        for r in reads:
            got = read_value(r)
            want = stock_g[entries[r["pair"]]] if converting else orig_read[r["rva"]]
            if fbits(got) != fbits(want):
                bad_reads.append("%s: %X reads %.9g, want %.9g" % (st["state"], r["rva"],
                                                                   got, want))
            if muted:
                continue
            k = f32(got - 1.0)
            facing = FACING
            for _ in range(n):
                facing = approach(k, facing)
            gap = wrap(TARGET - facing)
            checked += 1
            if not same_gap(gap, stock_gap[r["rva"]]):
                bad_gaps.append("%s fps: table read %X (g %.3g): gap %.6f after %d updates,"
                                " stock %.6f after 1" % (st["fps"], r["rva"],
                                                         stock_g[entries[r["pair"]]], gap, n,
                                                         stock_gap[r["rva"]]))
        if muted:
            continue
        for k in consts:
            facing = FACING
            for _ in range(n):
                facing = approach(f32(k), facing)
            gap = wrap(TARGET - facing)
            checked += 1
            if not same_gap(gap, stock_const[k]):
                bad_gaps.append("%s fps: constant %.3g: gap %.6f after %d updates, stock %.6f"
                                % (st["fps"], k, gap, n, stock_const[k]))
    print("table reads: %d x %d states, converting -> the stock g, otherwise the original's"
          " value: %d wrong" % (len(reads), len(states), len(bad_reads)))
    for b in bad_reads[:8]:
        print("  FAIL " + b)
    print("heading gap: %d cases (%d table reads, %d constants: %s) at 30/60/120 fps against"
          " one stock update: %d wrong" % (checked, len(reads), len(consts),
                                           " ".join("%g" % k for k in consts), len(bad_gaps)))
    for b in bad_gaps[:8]:
        print("  FAIL " + b)
    fails += len(bad_reads) + len(bad_gaps)

    # 3c. two call sites end to end
    def jump_handler(facing):
        # 3B5518 movzx eax,[mode] .. 3B553F call 2DA510 .. 3B5544 store -> 3B554C
        m.wf(base + HEADING, TARGET)
        m.run(base + 0x3B5518, base + 0x3B554C,
              regs={"r12": base, "rdi": m.obj}, xmm={8: 1.0, 10: facing})
        return m.rf(m.obj + 0xB4)

    def ground_turn(facing):
        # 3A7378 movss xmm2,[0.6] .. 3A7390 call 2DA510 .. 3A7395 store -> 3A739D
        m.wf(base + HEADING, TARGET)
        m.wf(m.obj + 0xB4, facing)
        m.run(base + 0x3A7378, base + 0x3A739D, regs={"rsi": m.obj})
        return m.rf(m.obj + 0xB4)

    bad_e2e = []
    for name, site in (("jump handler 3B553F (table 7A82C0)", jump_handler),
                       ("ground turn 3A7390 (constant 0.6)", ground_turn)):
        stock_world()
        want = wrap(TARGET - site(FACING))
        line = []
        for st in states:
            if st["muted"] == "1":
                continue
            patched_world(st)
            facing = FACING
            for _ in range(ticks[st["fps"]]):
                facing = site(facing)
            gap = wrap(TARGET - facing)
            ok = same_gap(gap, want)
            line.append("%s %.5f%s" % (st["state"], gap, "" if ok else " WRONG"))
            if not ok:
                bad_e2e.append("%s at %s fps: gap %.6f, stock %.6f" % (name, st["fps"], gap,
                                                                        want))
        print("  %s: stock gap %.5f | %s" % (name, want, " | ".join(line)))
    print("end to end: %d wrong" % len(bad_e2e))
    for b in bad_e2e:
        print("  FAIL " + b)
    fails += len(bad_e2e)

    # 3d. the bypassed calls, with the hook converting at 120
    st120 = next(s for s in states if s["state"] == "120")
    bad_bp = []
    for b in bypass:
        a = base + b["rva"]
        for k in (0.25, 0.5, 0.75):
            stock_world()
            want = approach(f32(k), FACING)            # the original, unconverted
            patched_world(st120)
            if b["orig"][0] == 0xE8:                   # a call: it returns to a + 5
                m.run(a, a + 5, xmm={0: TARGET, 1: FACING, 2: f32(k)})
            else:                                      # a tail jump: to our sentinel
                m.run(a, None, xmm={0: TARGET, 1: FACING, 2: f32(k)}, push_ret=True)
            got = m.xmmf(0)
            if fbits(got) != fbits(want):
                bad_bp.append("%X with k %.2f: %.7f, the original gives %.7f"
                              % (b["rva"], k, got, want))
                break
    print("bypassed calls: %d, with the hook converting at 120 fps, give the original"
          " function's result: %d wrong" % (len(bypass), len(bad_bp)))
    for b in bad_bp:
        print("  FAIL " + b)
    fails += len(bad_bp)

    print("\nwork dir %s\n%s" % (work, "FAILED (%d)" % fails if fails else
                                  "turn rate callers verified"))
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UcError as e:
        sys.exit("emulation fault: %s" % e)
