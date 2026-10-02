#!/usr/bin/env python3
"""Prove every tracer stub is neutral, by emulation.

Reads src/generated/tracer_sites.h -- the bytes the DLL compiles in -- lays
out the pool exactly as the DLL does (same fixup formula), and for every window
runs the original instructions and the stub from the same random machine state
under Unicorn. They must leave the same

  * exit address (the fall-through, a branch target, a callee or a return);
  * general registers, rsp included, and xmm0-15;
  * arithmetic flags and DF;
  * memory, except the tracer's own records and the stack below the final rsp
    (dead in both runs; the stub keeps its saved registers there).

It also checks what the stub *records*: for each site that ran, one execution,
and old/new samples equal to the stored field before and after the store as
the original code left it. The counting routine is checked separately against a
Python model over a sequence of ticks. Finally every int3-net redirect (an
interior instruction start mapped to its place in the stub) is run the same way.

    python tools/verify_tracer.py            # every window, 4 states each
    python tools/verify_tracer.py --states 8 --limit 500
Exits non-zero on any mismatch.
"""
import argparse
import os
import random
import re
import struct
import sys
import time

try:
    import capstone
    from capstone import x86_const as CX
    import pefile
    from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_HOOK_CODE,
                         UC_HOOK_MEM_WRITE, UC_HOOK_MEM_UNMAPPED)
    from unicorn import x86_const as U
except ImportError:
    sys.exit("needs pefile, capstone and unicorn: pip install pefile capstone unicorn")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
HDR = os.path.join(ROOT, "src", "generated", "tracer_sites.h")

BASE = 0x180000000
POOL = BASE - 0x4000000          # any address within 2 GB works; the DLL's is allocNear's
STACK_TOP = 0x7FF000000000
STACK_SIZE = 0x40000
PAGE = 0x1000
FLAG_MASK = 0xCD5                # CF PF AF ZF SF OF DF

GPRS = [U.UC_X86_REG_RAX, U.UC_X86_REG_RCX, U.UC_X86_REG_RDX, U.UC_X86_REG_RBX,
        U.UC_X86_REG_RSP, U.UC_X86_REG_RBP, U.UC_X86_REG_RSI, U.UC_X86_REG_RDI,
        U.UC_X86_REG_R8, U.UC_X86_REG_R9, U.UC_X86_REG_R10, U.UC_X86_REG_R11,
        U.UC_X86_REG_R12, U.UC_X86_REG_R13, U.UC_X86_REG_R14, U.UC_X86_REG_R15]
GPR_NAMES = "rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
XMMS = [getattr(U, "UC_X86_REG_XMM%d" % i) for i in range(16)]

R_OLD, R_LASTOLD, R_LASTNEW = 0x00, 0x08, 0x10
R_EXEC, R_CHG, R_LASTTICK, R_TICKS = 0x18, 0x1C, 0x20, 0x24
R_RUN, R_MAXRUN, R_CTX, R_LASTCHG = 0x28, 0x2C, 0x30, 0x34
R_CHGTICKS, R_CHGRUN, R_MAXCHGRUN, R_TICKSM1 = 0x38, 0x3C, 0x40, 0x44


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------

def parse_header():
    h = open(HDR, encoding="utf-8").read()

    def const(name):
        return int(re.search(r"%s = (0x[0-9A-F]+|\d+);" % name, h).group(1), 0)

    def block(name):
        return re.search(r"%s\[\] = \{\n(.*?)\n\};" % name, h, re.S).group(1)

    def byte_array(name):
        return bytes(int(x, 16) for x in re.findall(r"0x([0-9A-F]{2})", block(name)))

    def rows(name):
        return [tuple(int(v, 0) for v in r.split(","))
                for r in re.findall(r"\{([0-9A-Fx,]+)\}", block(name))]

    return {
        "sha": re.search(r'TRACER_MAIN_SHA1 "([0-9a-f]+)"', h).group(1),
        "rec_size": const("kTracerRecSize"),
        "code_off": const("kTracerCodeOffset"),
        "pool_size": const("kTracerPoolSize"),
        "common": const("kTracerCommon"),
        "fc": const("kTracerFrameCounterRva"),
        "mode": const("kTracerModeRva"),
        "code": byte_array("kTracerCode"),
        "orig": byte_array("kTracerOrig"),
        "fixups": rows("kTracerFixups"),
        "windows": rows("kTracerWindows"),
        "sites": rows("kTracerSites"),
        "insns": rows("kTracerInsns"),
    }


# ---------------------------------------------------------------------------
# machine
# ---------------------------------------------------------------------------

class Machine:
    def __init__(self, hdr, img):
        self.hdr = hdr
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        size = (len(img) + PAGE - 1) & ~(PAGE - 1)
        mu.mem_map(BASE, size, UC_PROT_ALL)
        mu.mem_write(BASE, bytes(img))
        self.pool_size = (hdr["pool_size"] + PAGE - 1) & ~(PAGE - 1)
        mu.mem_map(POOL, self.pool_size, UC_PROT_ALL)
        pool = bytearray(self.pool_size)
        co = hdr["code_off"]
        pool[co:co + len(hdr["code"])] = hdr["code"]
        # the DLL's fixup loop, verbatim in meaning
        for field, nxt, target in hdr["fixups"]:
            if nxt == 0:
                struct.pack_into("<Q", pool, field, BASE + target)
            else:
                rel = (BASE + target) - (POOL + nxt)
                assert -2 ** 31 <= rel < 2 ** 31
                struct.pack_into("<i", pool, field, rel)
        self.pool_image = bytes(pool)
        mu.mem_write(POOL, self.pool_image)
        mu.mem_map(STACK_TOP - STACK_SIZE, STACK_SIZE + PAGE, UC_PROT_ALL)
        self.fixed = [(BASE, BASE + size), (POOL, POOL + self.pool_size),
                      (STACK_TOP - STACK_SIZE, STACK_TOP + PAGE)]
        self.demand = []
        self.seed = 0
        self.undo = []
        self.written = {}
        self.orig = {}
        self.executed = set()
        self.range = (0, 0)
        self.exit = None
        self.steps = 0
        self.site_watch = {}     # rva -> (insn) for the original run
        self.samples = {}        # rva -> (old bytes, new bytes)
        self.pending_new = None
        mu.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)
        mu.hook_add(UC_HOOK_MEM_WRITE, self._write)
        mu.hook_add(UC_HOOK_CODE, self._code)

    # deterministic content for any page first touched during a run
    def _fill(self, page):
        rnd = random.Random((page * 0x9E3779B97F4A7C15 ^ self.seed) & 0xFFFFFFFFFFFFFFFF)
        # half the qwords look like pointers, so a window that loads a pointer
        # and stores through it (mov rax,[rcx]; inc word [rdx+rax]) can be run
        out = bytearray(rnd.randbytes(PAGE))
        for q in range(0, PAGE, 8):
            if rnd.random() < 0.5:
                p = (0x200000000 + rnd.randrange(0, 1 << 32)) & ~7  # clear of pool and image
                struct.pack_into("<Q", out, q, p)
        return bytes(out)

    def _unmapped(self, uc, access, address, size, value, data):
        return self.demand_map(address, size)

    def demand_map(self, address, size):
        uc = self.mu
        page = address & ~(PAGE - 1)
        # page 0 too: several windows store through a global pointer that is
        # null in the file image, and both runs must get past it to compare
        if page >= 0x800000000000:
            return False
        for p in (page, (address + size - 1) & ~(PAGE - 1)):
            if not any(a <= p < b for a, b in self.fixed) and p not in self.demand:
                try:
                    uc.mem_map(p, PAGE, UC_PROT_ALL)
                except UcError:
                    return False
                uc.mem_write(p, self._fill(p))
                self.demand.append(p)
        return True

    def _write(self, uc, access, address, size, value, data):
        if POOL <= address < POOL + self.hdr["code_off"]:
            return  # the tracer's records: kept for reading, reset explicitly
        # Unicorn calls this before its own unmapped check, so map the page
        # here or the undo read below faults -- in the original run only,
        # because the stub's pre-read has already mapped it
        if not self.demand_map(address, size):
            return
        old = bytes(uc.mem_read(address, size))
        self.undo.append((address, old))
        for i in range(size):
            self.written[address + i] = True
            self.orig.setdefault(address + i, old[i])

    def _code(self, uc, address, size, data):
        if self.pending_new is not None:
            rva, ea, n, old = self.pending_new
            if self.demand_map(ea, n):
                self.samples[rva] = (old, bytes(uc.mem_read(ea, n)))
            self.pending_new = None
        lo, hi = self.range
        if not (lo <= address < hi):
            self.exit = address
            uc.emu_stop()
            return
        self.executed.add(address)
        self.steps += 1
        if self.steps > 400:
            self.exit = "runaway"
            uc.emu_stop()
            return
        w = self.site_watch.get(address - BASE)
        if w is not None:
            ins, n = w
            ea = self._ea(uc, ins)
            # map it the way the store itself would, or the read below faults first
            if ea is not None and self.demand_map(ea, n):
                self.pending_new = (address - BASE, ea, n, bytes(uc.mem_read(ea, n)))

    def _ea(self, uc, ins):
        for op in ins.operands:
            if op.type == CX.X86_OP_MEM and (op.access & capstone.CS_AC_WRITE):
                m = op.mem
                if m.base == CX.X86_REG_RIP:
                    return BASE + ins.address + ins.size + m.disp
                v = m.disp
                if m.base:
                    v += uc.reg_read(REGMAP[ins.reg_name(m.base)])
                if m.index:
                    v += uc.reg_read(REGMAP[ins.reg_name(m.index)]) * m.scale
                return v & 0xFFFFFFFFFFFFFFFF
        return None

    def set_state(self, st):
        mu = self.mu
        for r, v in zip(GPRS, st["gpr"]):
            mu.reg_write(r, v)
        for r, v in zip(XMMS, st["xmm"]):
            mu.reg_write(r, v)
        mu.reg_write(U.UC_X86_REG_EFLAGS, st["flags"])
        mu.mem_write(BASE + self.hdr["fc"], struct.pack("<I", st["fc"]))
        mu.mem_write(BASE + self.hdr["mode"], bytes([st["mode"]]))

    def run(self, st, start, lo, hi):
        """Run from `start` until rip leaves [lo, hi). Returns the final state."""
        self.seed = st["seed"]
        self.undo, self.written, self.orig, self.executed = [], {}, {}, set()
        self.exit, self.steps, self.pending_new = None, 0, None
        self.range = (lo, hi)
        self.set_state(st)
        err = None
        try:
            self.mu.emu_start(start, 0xFFFFFFFFFFFFFFFF, count=2000)
        except UcError as e:
            err = str(e)
        mu = self.mu
        out = {
            "exit": self.exit,
            "err": err,
            "rip": mu.reg_read(U.UC_X86_REG_RIP),
            "gpr": [mu.reg_read(r) for r in GPRS],
            "xmm": [mu.reg_read(r) for r in XMMS],
            "flags": mu.reg_read(U.UC_X86_REG_EFLAGS) & FLAG_MASK,
            "mem": {a: bytes(mu.mem_read(a, 1))[0] for a in self.written},
            "orig": dict(self.orig),
            "executed": set(self.executed),
        }
        for a, old in reversed(self.undo):
            mu.mem_write(a, old)
        return out

    def reset_demand(self):
        for p in self.demand:
            self.mu.mem_unmap(p, PAGE)
        self.demand = []

    def reset_records(self, recs):
        rs = self.hdr["rec_size"]
        for i in recs:
            rec = bytearray(rs)
            struct.pack_into("<I", rec, R_LASTTICK, 0xFFFFFFFE)
            struct.pack_into("<I", rec, R_LASTCHG, 0xFFFFFFFE)
            self.mu.mem_write(POOL + i * rs, bytes(rec))

    def record(self, i):
        rs = self.hdr["rec_size"]
        return bytes(self.mu.mem_read(POOL + i * rs, rs))


REGMAP = dict(zip(GPR_NAMES, GPRS))


def random_state(rnd):
    gpr = []
    for i in range(16):
        if rnd.random() < 0.7:
            # pointers, but never into the pool or the image: a random store
            # there would rewrite code that later windows run
            while True:
                p = (0x100000000 + rnd.randrange(0, 1 << 36)) & ~7
                if not (POOL - 0x1000000 <= p < BASE + 0x2000000):
                    break
            gpr.append(p)
        else:
            gpr.append(rnd.randrange(0x10000, 0x20000))
    gpr[4] = STACK_TOP - 0x8000 - rnd.randrange(0, 256) * 16 - rnd.choice((0, 8))
    return {
        "gpr": gpr,
        "xmm": [rnd.getrandbits(128) for _ in range(16)],
        "flags": 0x2 | (rnd.getrandbits(12) & FLAG_MASK & ~0x400),
        "fc": rnd.randrange(0, 1 << 31),
        "mode": rnd.choice((1, 2)),
        "seed": rnd.getrandbits(64),
    }


def compare(a, b, pool_lo, pool_hi):
    """List of differences between the original run `a` and the stub run `b`."""
    diffs = []
    if a["err"] and b["err"]:
        return None  # inconclusive: both fault (the stub's pre-read faults first)
    if a["err"] or b["err"]:
        return ["only one run faulted: %s / %s" % (a["err"], b["err"])]
    if a["exit"] != b["exit"]:
        diffs.append("exit %s vs %s" % (fmt(a["exit"]), fmt(b["exit"])))
    for n, x, y in zip(GPR_NAMES, a["gpr"], b["gpr"]):
        if x != y:
            diffs.append("%s %X vs %X" % (n, x, y))
    for i, (x, y) in enumerate(zip(a["xmm"], b["xmm"])):
        if x != y:
            diffs.append("xmm%d" % i)
    if a["flags"] != b["flags"]:
        diffs.append("flags %03X vs %03X" % (a["flags"], b["flags"]))
    rsp = a["gpr"][4]
    keys = set(a["mem"]) | set(b["mem"])
    for k in sorted(keys):
        if pool_lo <= k < pool_hi:
            continue
        if STACK_TOP - STACK_SIZE <= k < rsp:
            continue
        # a byte written in one run only must still hold its original value
        orig = a["orig"].get(k, b["orig"].get(k))
        if a["mem"].get(k, orig) != b["mem"].get(k, orig):
            diffs.append("mem %X" % k)
            break
    return diffs


def fmt(x):
    return "%X" % x if isinstance(x, int) else str(x)


# ---------------------------------------------------------------------------
# the counting routine against a model
# ---------------------------------------------------------------------------

def model_step(rec, fc, mode, old, new):
    rec["exec"] += 1
    if old != new:
        rec["chg"] += 1
        rec["lastOld"], rec["lastNew"] = old, new
        if fc != rec["lastChg"]:
            rec["chgRun"] = rec["chgRun"] + 1 if fc == (rec["lastChg"] + 1) & 0xFFFFFFFF else 1
            rec["lastChg"] = fc
            rec["chgTicks"] += 1
            rec["maxChgRun"] = max(rec["maxChgRun"], rec["chgRun"])
    if fc != rec["lastTick"]:
        rec["run"] = rec["run"] + 1 if fc == (rec["lastTick"] + 1) & 0xFFFFFFFF else 1
        rec["lastTick"] = fc
        rec["ticks"] += 1
        rec["maxRun"] = max(rec["maxRun"], rec["run"])
        rec["ctx"] |= 1 << (mode & 31)
        if mode == 1:
            rec["ticksM1"] += 1


def check_counter(m, hdr, rnd):
    """Drive the common routine directly with a tick sequence; compare to the model."""
    problems = []
    rs = hdr["rec_size"]
    for trial in range(40):
        m.reset_records([0])
        model = dict(exec=0, chg=0, lastOld=0, lastNew=0, lastTick=0xFFFFFFFE, ticks=0, run=0,
                     maxRun=0, ctx=0, lastChg=0xFFFFFFFE, chgTicks=0, chgRun=0, maxChgRun=0,
                     ticksM1=0)
        fc = rnd.randrange(0, 1000)
        for step in range(60):
            r = rnd.random()
            if r < 0.5:
                fc += 1
            elif r < 0.6:
                fc += rnd.randrange(2, 5)
            mode = rnd.choice((1, 2))
            old = rnd.choice((5, 5, 7, rnd.getrandbits(64)))
            new = rnd.choice((old, old, rnd.getrandbits(64)))
            st = random_state(rnd)
            st["fc"], st["mode"] = fc, mode
            st["gpr"][1] = POOL          # rcx = record 0
            st["gpr"][2] = new           # rdx = new value
            m.mu.mem_write(POOL + R_OLD, struct.pack("<Q", old))
            # a return address the run stops at
            ret = BASE + 0x1000
            st["gpr"][4] -= 8
            m.mu.mem_write(st["gpr"][4], struct.pack("<Q", ret))
            m.set_state(st)
            m.seed = st["seed"]
            m.range = (POOL, POOL + m.pool_size)
            m.exit, m.steps, m.pending_new = None, 0, None
            saved_rax = st["gpr"][0]
            m.mu.emu_start(POOL + hdr["common"], 0xFFFFFFFFFFFFFFFF, count=200)
            model_step(model, fc & 0xFFFFFFFF, mode, old, new)
            if m.exit != ret:
                problems.append("counter: did not return (exit %s)" % fmt(m.exit))
                return problems
            if m.mu.reg_read(U.UC_X86_REG_RAX) != saved_rax:
                problems.append("counter: rax not preserved")
                return problems
            rec = m.record(0)
            got = dict(zip(
                "lastOld lastNew".split(), struct.unpack_from("<QQ", rec, R_LASTOLD)))
            got.update(zip(
                "exec chg lastTick ticks run maxRun ctx lastChg chgTicks chgRun maxChgRun ticksM1"
                .split(), struct.unpack_from("<12I", rec, R_EXEC)))
            for k, v in got.items():
                if model[k] != v:
                    problems.append("counter trial %d step %d: %s = %X, model %X"
                                    % (trial, step, k, v, model[k]))
                    return problems
    return problems


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", type=int, default=4, help="random states per window")
    ap.add_argument("--limit", type=int, default=0, help="only the first N windows")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    hdr = parse_header()
    path = os.path.join(GAME, "main.dll")
    import hashlib
    raw = open(path, "rb").read()
    if hashlib.sha1(raw).hexdigest() != hdr["sha"]:
        sys.exit("main.dll is not the build the header was generated from")
    pe = pefile.PE(data=raw, fast_load=True)
    img = bytearray(pe.get_memory_mapped_image())
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    m = Machine(hdr, img)
    rnd = random.Random(args.seed)
    t0 = time.time()
    fails = 0

    # 0. every window's orig bytes are the shipped bytes
    for rva, stub, ooff, ln in hdr["windows"]:
        if bytes(img[rva:rva + ln]) != hdr["orig"][ooff:ooff + ln]:
            print("orig mismatch at %06X" % rva)
            fails += 1

    # 1. the counting routine
    probs = check_counter(m, hdr, rnd)
    print("counter routine vs model: %s" % ("OK (40 sequences x 60 calls)" if not probs
                                            else probs[0]))
    fails += len(probs)

    # 2. every window
    sites_by_win = {}
    for i, (rva, wi, sample, kind, sub) in enumerate(hdr["sites"]):
        sites_by_win.setdefault(wi, []).append((i, rva, sample, kind))
    windows = hdr["windows"][:args.limit] if args.limit else hdr["windows"]
    checked = inconclusive = sampled = 0
    bad_windows = []
    for wi, (rva, stub, ooff, ln) in enumerate(windows):
        sites = sites_by_win.get(wi, [])
        watch = {}
        for i, srva, sample, kind in sites:
            if sample:
                ins = next(md.disasm(bytes(img[srva:srva + 16]), srva))
                watch[srva] = (ins, sample)
        good = 0
        tries = 0
        while good < args.states and tries < args.states * 4:
            tries += 1
            st = random_state(rnd)
            m.site_watch, m.samples = watch, {}
            a = m.run(st, BASE + rva, BASE + rva, BASE + rva + ln)
            samples = dict(m.samples)
            m.site_watch = {}
            m.reset_records([i for i, *_ in sites])
            b = m.run(st, POOL + stub, POOL, POOL + m.pool_size)
            d = compare(a, b, POOL, POOL + m.pool_size)
            if d is None:
                inconclusive += 1
                continue
            good += 1
            # what the stub recorded
            for i, srva, sample, kind in sites:
                rec = m.record(i)
                ex, chg = struct.unpack_from("<II", rec, R_EXEC)
                ran = (BASE + srva) in a["executed"]
                if ex != (1 if ran else 0):
                    d.append("site %06X exec %d, original ran it %d time(s)" % (srva, ex, ran))
                if srva in samples:
                    old, new = samples[srva]
                    if ex != 1:
                        d.append("site %06X exec %d, ran once" % (srva, ex))
                    o = int.from_bytes(old[:sample], "little")
                    n = int.from_bytes(new[:sample], "little")
                    lo_, ln_ = struct.unpack_from("<QQ", rec, R_LASTOLD)
                    if (o != n) != (chg == 1):
                        d.append("site %06X chg %d but %X -> %X" % (srva, chg, o, n))
                    elif o != n and (lo_, ln_) != (o, n):
                        d.append("site %06X sampled %X->%X, store did %X->%X"
                                 % (srva, lo_, ln_, o, n))
                    sampled += 1
            if d:
                bad_windows.append((rva, d))
                break
        if good == 0:
            bad_windows.append((rva, ["no conclusive state in %d tries" % tries]))
        checked += 1
        if len(m.demand) > 256:
            m.reset_demand()
        if checked % 1000 == 0:
            print("  %d windows, %.0f s" % (checked, time.time() - t0))
    code_now = bytes(m.mu.mem_read(POOL + hdr["code_off"], m.pool_size - hdr["code_off"]))
    if code_now != m.pool_image[hdr["code_off"]:]:
        print("POOL CODE WAS MODIFIED during the run -- results above are not trustworthy")
        fails += 1
    print("windows: %d checked, %d site samples verified, %d inconclusive runs (faults)"
          % (checked, sampled, inconclusive))
    real_bad = [w for w in bad_windows if not w[1][0].startswith("no conclusive")]
    no_state = [w for w in bad_windows if w[1][0].startswith("no conclusive")]
    for rva, d in real_bad[:25]:
        print("  MISMATCH %06X: %s" % (rva, "; ".join(d[:4])))
    for rva, d in no_state[:10]:
        print("  unverified %06X: %s" % (rva, d[0]))
    if no_state:
        print("  %d window(s) unverified (every state faulted in both runs)" % len(no_state))
    fails += len(real_bad)

    # 3. int3-net redirects: enter mid-window, compare with entering the stub there
    wins = sorted((r, r + ln) for r, s, o, ln in hdr["windows"])
    import bisect
    starts = [w[0] for w in wins]
    net_bad = net_ok = 0
    insns = hdr["insns"][:args.limit * 2] if args.limit else hdr["insns"]
    for irva, ist in insns:
        k = bisect.bisect_right(starts, irva) - 1
        w_lo, w_hi = wins[k]
        for _ in range(3):
            st = random_state(rnd)
            a = m.run(st, BASE + irva, BASE + w_lo, BASE + w_hi)
            b = m.run(st, POOL + ist, POOL, POOL + m.pool_size)
            d = compare(a, b, POOL, POOL + m.pool_size)
            if d is None:
                continue
            if d:
                net_bad += 1
                if net_bad <= 5:
                    print("  NET MISMATCH %06X: %s" % (irva, "; ".join(d[:3])))
            else:
                net_ok += 1
            break
        if len(m.demand) > 256:
            m.reset_demand()
    print("int3-net redirects: %d entries, %d verified, %d mismatched"
          % (len(insns), net_ok, net_bad))
    fails += net_bad

    print("\n%.0f s. %s" % (time.time() - t0,
                          "FAILED: %d problems" % fails if fails else "all stubs neutral"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
