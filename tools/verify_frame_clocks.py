#!/usr/bin/env python3
"""Prove the frame-counter clocks (family F5, src/frame_clocks.h) offline.

1. Loads the built DLL into this process and calls its OkamiFrameClockSelfTest
   export, which maps main.dll without running any of it
   (DONT_RESOLVE_DLL_REFERENCES), runs the real install -- the per-tick hook,
   every retargeted read -- widens the gates for 120, 60 and 30 fps, and then
   drives the counters one tick at a time through every combination of fps
   mode, stock context and the A/B key, writing each counter (clocks.csv).

2. Recomputes here, independently, what the installed bytes must be: the hook's
   jump, every read's displacement, the stub (the relocated increment, the
   template with the callback's address, the jump back), every widened mask.

3. Emulates under Unicorn, with main.dll mapped where the DLL loaded it:

     * every read as installed against the original, from random machine
       states: with its counter slot holding v (and the real counter something
       else) it must do exactly what the original does with the counter
       holding v -- registers, flags, exit, memory writes;
     * the hook against the bare increment, with a callback that clobbers
       every register it may and the flags and xmm0-5: registers, flags, all
       xmm and the memory the game can see must end as the increment alone
       leaves them, and the callback must be entered 16-byte aligned;
     * every modulo gate end to end, fed the counters the DLL produced: the
       installed code must fire on exactly the ticks where a new stock tick
       lands on its residue (once per stock tick), and with the fix off on
       exactly the ticks where the original fires. The loading screen's
       rhythm window must read as stock on every tick;
     * every widened mask gate: once per (mask + 1) x N ticks.

4. Checks the counters themselves: the frame counter while the fix is off; S
   and U stepping by at most one per tick, at their rates; each hold counter
   equal to S except where held, and held exactly there. And the loading
   screen's stamps, stored before a change and read after it, through the
   real fade reader and window test: the time since each is kept in seconds
   across every change the patch makes (F9, the A/B key), at the rate the game
   really ticks -- the patched fps, or the stock game's own, 60 in its mode-1
   contexts -- and kept in ticks, as in the stock game, when the stock game
   changes its own mode with the patch off.

    .venv/Scripts/python tools/verify_frame_clocks.py [--dll .build/bin/dinput8.dll]
Exits non-zero on any mismatch.
"""
import argparse
import csv
import ctypes
import os
import random
import re
import shutil
import struct
import sys
import tempfile

try:
    import pefile
    from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_HOOK_MEM_WRITE
    from unicorn import UC_HOOK_CODE
    from unicorn import x86_const as U
except ImportError:
    sys.exit("needs pefile and unicorn: pip install pefile unicorn")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import gen_frame_clocks as gfc  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
HDR = os.path.join(ROOT, "src", "frame_clocks.h")
SRC = os.path.join(ROOT, "src", "dinput8_proxy.cpp")
PAGE = 0x1000
FLAG_MASK = 0xCD5                # CF PF AF ZF SF OF DF
GPRS = [U.UC_X86_REG_RAX, U.UC_X86_REG_RCX, U.UC_X86_REG_RDX, U.UC_X86_REG_RBX,
        U.UC_X86_REG_RSP, U.UC_X86_REG_RBP, U.UC_X86_REG_RSI, U.UC_X86_REG_RDI,
        U.UC_X86_REG_R8, U.UC_X86_REG_R9, U.UC_X86_REG_R10, U.UC_X86_REG_R11,
        U.UC_X86_REG_R12, U.UC_X86_REG_R13, U.UC_X86_REG_R14, U.UC_X86_REG_R15]
GPR_NAMES = "rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
XMMS = [getattr(U, "UC_X86_REG_XMM%d" % i) for i in range(16)]
LOADING_WINDOW = {0, 1, 8, 9}


def parse_header():
    h = open(HDR, encoding="utf-8").read()

    def block(name):
        return re.search(r"%s\[\] = \{\n(.*?)\n\};" % name, h, re.S).group(1)

    def raw(txt, n):
        return bytes(int(x, 16) for x in txt.split(","))[:n]

    holds = [tuple(int(x) for x in re.match(r"\s*\{(\d+), (\d+)\}", ln).groups())
             for ln in block("kFrameClockHolds").splitlines()]
    reads = []
    for ln in block("kFrameClockReads").splitlines():
        g = re.match(r"\s*\{0x([0-9A-F]+), (\d+), (\d+), (\d+), \{([^}]*)\}\}", ln)
        n = int(g.group(2))
        reads.append({"rva": int(g.group(1), 16), "len": n, "disp_off": int(g.group(3)),
                      "slot": int(g.group(4)), "orig": raw(g.group(5), n)})
    gates = []
    for ln in block("kFrameClockGates").splitlines():
        g = re.match(r"\s*\{0x([0-9A-F]+), (\d+), (\d+), 0x([0-9A-F]+), \{([^}]*)\}\}", ln)
        n = int(g.group(2))
        gates.append({"rva": int(g.group(1), 16), "len": n, "imm_off": int(g.group(3)),
                      "mask": int(g.group(4), 16), "orig": raw(g.group(5), n)})
    tick = int(re.search(r"kFrameClockTickRva = 0x([0-9A-F]+)", h).group(1), 16)
    torig = raw(re.search(r"kFrameClockTickOrig\[\d+\] = \{([^}]*)\}", h).group(1), 16)
    fc = int(re.search(r"kFrameClockCounterRva = 0x([0-9A-F]+)", h).group(1), 16)
    sha = re.search(r'FRAME_CLOCKS_MAIN_SHA1 "([0-9a-f]+)"', h).group(1)
    stamps = [int(x, 16) for x in re.findall(r"0x([0-9A-F]+),", block("kFrameClockStamps"))]
    return {"holds": holds, "reads": reads, "gates": gates, "tick": tick, "tick_orig": torig,
            "fc": fc, "sha": sha, "stamps": stamps}


def rel32(nxt, target):
    r = target - nxt
    assert -2 ** 31 <= r < 2 ** 31, "rel32 out of reach"
    return struct.pack("<i", r)


def stub_template():
    """kFrameClockStub and the callback offset, read from the patch source"""
    import verify_stubs
    src = open(SRC, encoding="utf-8").read()
    raw = verify_stubs.array_bytes(src, "kFrameClockStub")
    at = int(re.search(r"kFrameClockStubFnAt = (\d+)", src).group(1))
    return raw, at


# ---------------------------------------------------------------------------
# emulation
# ---------------------------------------------------------------------------

class Machine:
    def __init__(self, img, main, pages):
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        size = (len(img) + PAGE - 1) & ~(PAGE - 1)
        mu.mem_map(main, size, UC_PROT_ALL)
        mu.mem_write(main, bytes(img))
        for p in sorted(set(pages)):
            try:
                mu.mem_map(p, PAGE, UC_PROT_ALL)
            except UcError:
                pass           # already mapped (two pages of interest share one)
        self.stack = 0x10000000
        while any(abs(self.stack - p) < 0x200000 for p in list(pages) + [main]):
            self.stack += 0x40000000
        mu.mem_map(self.stack - 0x10000, 0x20000, UC_PROT_ALL)
        self.writes = []
        self.entered = []
        mu.hook_add(UC_HOOK_MEM_WRITE, self._write)

    def _write(self, uc, access, address, size, value, data):
        self.writes.append((address, size, value & ((1 << (8 * size)) - 1)))

    def run(self, st, code, start, until, count=4000):
        mu = self.mu
        saved = [(a, bytes(mu.mem_read(a, len(b)))) for a, b in code + list(st["mem"].items())]
        for a, b in code:
            mu.mem_write(a, b)
        mu.ctl_flush_tb()
        for a, b in st["mem"].items():
            mu.mem_write(a, b)
        for r, v in zip(GPRS, st["gpr"]):
            mu.reg_write(r, v)
        for r, v in zip(XMMS, st.get("xmm", [0] * 16)):
            mu.reg_write(r, v)
        mu.reg_write(U.UC_X86_REG_EFLAGS, st["flags"])
        self.writes = []
        err = None
        try:
            mu.emu_start(start, until, count=count)
        except UcError as e:
            err = str(e)
        out = {"err": err, "rip": mu.reg_read(U.UC_X86_REG_RIP),
               "gpr": [mu.reg_read(r) for r in GPRS],
               "xmm": [mu.reg_read(r) for r in XMMS],
               "flags": mu.reg_read(U.UC_X86_REG_EFLAGS) & FLAG_MASK,
               "writes": list(self.writes)}
        for a, b in reversed(saved):
            mu.mem_write(a, b)
        mu.ctl_flush_tb()
        return out


def random_state(rnd, stack):
    gpr = [rnd.getrandbits(64) for _ in range(16)]
    gpr[4] = stack - rnd.randrange(1, 256) * 16          # 16-aligned, as at the hook
    return {"gpr": gpr, "xmm": [rnd.getrandbits(128) for _ in range(16)],
            "flags": 0x2 | (rnd.getrandbits(12) & FLAG_MASK & ~0x400), "mem": {}}


def diff(a, b, xmm=False):
    d = ["%s %X vs %X" % (n, x, y) for n, x, y in zip(GPR_NAMES, a["gpr"], b["gpr"]) if x != y]
    if a["flags"] != b["flags"]:
        d.append("flags %03X vs %03X" % (a["flags"], b["flags"]))
    if xmm:
        d += ["xmm%d differs" % i for i, (x, y) in enumerate(zip(a["xmm"], b["xmm"])) if x != y]
    if a["rip"] != b["rip"]:
        d.append("exit %X vs %X" % (a["rip"], b["rip"]))
    if a["err"] or b["err"]:
        d.append("fault %s / %s" % (a["err"], b["err"]))
    return d


# ---------------------------------------------------------------------------
# the counters the DLL produced
# ---------------------------------------------------------------------------

def load_clocks(path, holds, nstamps):
    rows = []
    for r in csv.DictReader(open(path)):
        rows.append({k: int(v) for k, v in r.items()})
    for r in rows:
        r["H"] = [r["H%d_%d" % h] for h in holds]
        r["on"] = r["fps"] != 30 and not r["muted"]
        r["n"] = (r["fps"] // (60 if r["mode"] == 1 else 30)) if r["on"] else 0
        r["n60"] = r["fps"] // 60 if r["on"] else 0
        # fps is the patch's mode (30: off) and mode the stock game's mode
        # byte. The game ticks at the patched fps, or with the patch off at
        # the stock game's own rate: 60 in mode 1, 30 in mode 2. The loading
        # code reads the real byte: pinned at 1 while patched, the stock
        # game's own with the patch off.
        r["stock"] = r["fps"] == 30
        r["hz"] = (60 if r["mode"] == 1 else 30) if r["stock"] else r["fps"]
        r["real"] = r["mode"] if r["stock"] else 1
        r["uhz"] = 60 if r["on"] else r["hz"]           # U's ticks per second
        r["stamp"] = [r["stamp%d" % i] for i in range(nstamps)]
        r["set"] = [r["set%d" % i] for i in range(nstamps)]
    prev = None
    for r in rows:
        r["first"] = prev is None or r["S"] != prev["S"]
        prev = r
    return rows


def check_clocks(rows, holds):
    probs = []
    segs = []
    for r in rows:
        key = (r["fps"], r["mode"], r["muted"])
        if not segs or segs[-1][0] != key:
            segs.append((key, []))
        segs[-1][1].append(r)
    prev = None
    for key, seg in segs:
        name = "%d fps, stock mode %d%s" % (key[0], key[1], ", muted" if key[2] else "")
        on = seg[0]["on"]
        if not on:
            bad = [r["tick"] for r in seg
                   if not (r["S"] == r["U"] == r["counter"] and
                           all(h == r["counter"] for h in r["H"]))]
            if bad:
                probs.append("%s: a counter is not the frame counter at tick %d" % (name, bad[0]))
        else:
            for which, rate in (("S", seg[0]["n"]), ("U", seg[0]["n60"])):
                last = prev[which] if prev is not None and prev["on"] else None
                steps = []
                for r in seg:
                    if last is not None and r[which] - last not in (0, 1):
                        probs.append("%s: %s jumps by %d at tick %d"
                                     % (name, which, r[which] - last, r["tick"]))
                        break
                    if last is not None and r[which] != last:
                        steps.append(r["tick"])
                    last = r[which]
                gaps = {b - a for a, b in zip(steps, steps[1:])}
                if len(seg) >= 3 * rate and gaps != {rate}:
                    probs.append("%s: %s steps every %s ticks, want %d"
                                 % (name, which, sorted(gaps), rate))
        # the hold counters, on every tick of every segment
        for r in seg:
            for (P, e), h in zip(holds, r["H"]):
                held = r["on"] and not r["first"] and r["S"] % P == e
                want = (r["S"] - 1 if r["S"] else P - 1) if held else r["S"]
                if h != want:
                    probs.append("%s: H(%d,%d) is %d at tick %d, want %d"
                                 % (name, P, e, h, r["tick"], want))
                    break
                fires = h % P == e
                stock = r["S"] % P == e and (r["first"] or not r["on"])
                if fires != stock:
                    probs.append("%s: H(%d,%d) fires=%d at tick %d, stock tick fires=%d"
                                 % (name, P, e, fires, r["tick"], stock))
                    break
        prev = seg[-1]
    return len(segs), probs


def stamp_ages(rows, nstamps):
    """Per tick and stamp: (seconds since the stamp was stored, fps or A/B
    changes since), or None before its first store.

    Wall seconds, except across the stock game changing its own mode with the
    patch off: the stock game counts its windows in its own ticks, which
    become ticks of the new rate, and the patch switched off must not change
    that. So there the age keeps its ticks, not its seconds."""
    out, age, prev = [], [None] * nstamps, None
    for r in rows:
        key = (r["fps"], r["muted"])
        stock_change = prev is not None and key == (prev["fps"], prev["muted"]) and             r["stock"] and r["hz"] != prev["hz"]
        for i in range(nstamps):
            if age[i] is not None:
                secs, trans = age[i]
                if stock_change:
                    secs = secs * prev["hz"] / r["hz"]
                changed = prev is not None and key != (prev["fps"], prev["muted"])
                age[i] = (secs + 1.0 / r["hz"], trans + changed)
            if r["set"][i]:
                age[i] = (0.0, 0)
        out.append(list(age))
        prev = r
    return out


def stamp_tol(trans):
    # a rebase floors, losing under one tick of the new rate (30 Hz at worst),
    # and U itself steps once per 1/60 s
    return (trans + 1) / 30.0 + 1 / 60.0


def check_stamps(rows, ages, nstamps):
    """U - stamp, in seconds at U's current rate, must be the wall time since the
    stamp was stored, through every fps change and A/B toggle since."""
    probs, checked, carried = [], 0, 0
    for r, age in zip(rows, ages):
        for i in range(nstamps):
            if age[i] is None:
                continue
            secs, trans = age[i]
            got = ((r["U"] - r["stamp"][i]) & 0xFFFFFFFF) / r["uhz"]
            checked += 1
            carried += trans > 0
            if abs(got - secs) > stamp_tol(trans) and len(probs) < 10:
                probs.append("stamp %d at tick %d (%d fps%s, %d change(s) since it was"
                             " stored): %.3f s old by U, %.3f s by the clock"
                             % (i, r["tick"], r["fps"], ", muted" if r["muted"] else "", trans,
                                got, secs))
    return checked, carried, probs


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--states", type=int, default=48, help="random states per read")
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    ap.add_argument("--break", dest="brk", default=None,
                    choices=("disp", "stub-align", "stub-xmm", "gate", "hold", "stamp"),
                    help="corrupt one thing after the self-test; the run must then FAIL"
                         " (stamp: never rebase the loading screen's stamps)")
    args = ap.parse_args()

    hdr = parse_header()
    path = os.path.join(GAME, "main.dll")
    import hashlib
    sha = hashlib.sha1(open(path, "rb").read()).hexdigest()
    if sha != hdr["sha"]:
        sys.exit("main.dll sha1 %s is not the build the header was generated from (%s)"
                 % (sha, hdr["sha"]))
    fails = 0

    # 1. the DLL's own install, on a mapped main.dll
    work = args.out or tempfile.mkdtemp(prefix="okami_clocks_selftest_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiFrameClockSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    fn.restype = ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    print("DLL self-test (rc %d): %s" % (rc, report.strip().splitlines()[-1]))
    if rc != 0:
        print(report)
        return 1
    vals = {}
    for ln in report.splitlines():
        p = ln.split()
        if len(p) == 2 and p[0] in ("main", "slots", "stub", "fn"):
            vals[p[0]] = int(p[1], 16)
    main_base, slots, stub, cb = vals["main"], vals["slots"], vals["stub"], vals["fn"]
    fc = main_base + hdr["fc"]
    pe = pefile.PE(path, fast_load=True)
    pe.relocate_image(main_base)
    img = pe.get_memory_mapped_image()

    # 2. the bytes, against an independent computation
    site = main_base + hdr["tick"]
    tl = len(hdr["tick_orig"])
    blob = open(os.path.join(work, "sites.bin"), "rb").read()
    want_hook = b"\xE9" + rel32(site + 5, stub) + b"\x90" * (tl - 5)
    got_hook, pos = blob[:tl], tl
    wrong = [] if got_hook == want_hook else ["hook"]
    installed = {}
    for r in hdr["reads"]:
        got = blob[pos:pos + r["len"]]
        pos += r["len"]
        want = bytearray(r["orig"])
        want[r["disp_off"]:r["disp_off"] + 4] = rel32(main_base + r["rva"] + r["len"],
                                                      slots + 4 * r["slot"])
        installed[r["rva"]] = got
        if got != bytes(want):
            wrong.append("%06X" % r["rva"])
    tmpl, fn_at = stub_template()
    want_stub = bytearray()
    d = struct.unpack_from("<i", hdr["tick_orig"], 2)[0]
    want_stub += hdr["tick_orig"][:2] + rel32(stub + tl, site + tl + d)   # inc [rip+counter]
    t = bytearray(tmpl)
    t[fn_at:fn_at + 8] = struct.pack("<Q", cb)
    want_stub += t
    want_stub += b"\xE9" + rel32(stub + len(want_stub) + 5, site + tl)
    got_stub = open(os.path.join(work, "stub.bin"), "rb").read()
    if got_stub != bytes(want_stub):
        wrong.append("stub")
    gblob = open(os.path.join(work, "gates.bin"), "rb").read()
    per = sum(g["len"] for g in hdr["gates"])
    widened = {}
    for k, shift in enumerate((2, 1, 0)):
        pos = k * per
        for g in hdr["gates"]:
            got = gblob[pos:pos + g["len"]]
            pos += g["len"]
            want = bytearray(g["orig"])
            want[g["imm_off"]] = ((g["mask"] + 1) << shift) - 1
            widened[(g["rva"], shift)] = got
            if got != bytes(want):
                wrong.append("gate %06X at shift %d" % (g["rva"], shift))
    print("installed bytes: hook, %d reads, the %d-byte stub, %d gates x 3 modes: %d differ%s"
          % (len(hdr["reads"]), len(got_stub), len(hdr["gates"]), len(wrong),
             (": " + ", ".join(wrong[:6])) if wrong else ""))
    fails += len(wrong)

    # --break: corrupt one thing the DLL produced, to show the checks below see it
    if args.brk == "disp":
        r = hdr["reads"][len(hdr["reads"]) // 2]
        b = bytearray(installed[r["rva"]])
        b[r["disp_off"]] = (b[r["disp_off"]] + 4) & 0xFF      # the next slot over
        installed[r["rva"]] = bytes(b)
    elif args.brk == "stub-align":
        got_stub = got_stub[:tl] + got_stub[tl + 1:] + b"\x90"   # no pushfq
    elif args.brk == "stub-xmm":
        k = got_stub.index(bytes([0xF3, 0x0F, 0x6F, 0x5C, 0x24, 0x50]))
        got_stub = got_stub[:k] + b"\x90" * 6 + got_stub[k + 6:]  # xmm3 not restored
    elif args.brk == "gate":
        g = hdr["gates"][0]
        b = bytearray(widened[(g["rva"], 2)])
        b[g["imm_off"]] = ((g["mask"] + 1) << 1) - 1                 # 60 fps's mask at 120
        widened[(g["rva"], 2)] = bytes(b)
    m = Machine(img, main_base, [slots & ~(PAGE - 1), stub & ~(PAGE - 1), cb & ~(PAGE - 1),
                                 (cb & ~(PAGE - 1)) + PAGE])
    rnd = random.Random(0xF5C1)

    # 3a. every read as installed, against the original
    bad_reads = []
    for r in hdr["reads"]:
        a = main_base + r["rva"]
        slot = slots + 4 * r["slot"]
        for k in range(args.states):
            v = (0, 1, 14, 15, 359, 360, 0xFFFF, 0xFFFFFFFF)[k] if k < 8 else rnd.getrandbits(32)
            other = rnd.getrandbits(32)
            st = random_state(rnd, m.stack)
            st["mem"] = {fc: struct.pack("<I", v), slot: struct.pack("<I", other)}
            x = m.run(st, [(a, r["orig"])], a, a + r["len"], count=1)
            st["mem"] = {fc: struct.pack("<I", other), slot: struct.pack("<I", v)}
            y = m.run(st, [(a, installed[r["rva"]])], a, a + r["len"], count=1)
            dd = diff(x, y)
            if x["writes"] != y["writes"]:
                dd.append("writes differ")
            if dd:
                bad_reads.append("%06X v=%X: %s" % (r["rva"], v, "; ".join(dd)))
                break
    print("reads: %d emulated against the original, %d states each: %d mismatch"
          % (len(hdr["reads"]), args.states, len(bad_reads)))
    for b in bad_reads:
        print("  FAIL " + b)
    fails += len(bad_reads)

    # 3b. the hook against the bare increment
    #     the callback: clobber every volatile register, xmm0-5 and the flags
    clob = bytearray()
    for reg_code, rex in ((0, 0x48), (1, 0x48), (2, 0x48), (0, 0x49), (1, 0x49), (2, 0x49),
                          (3, 0x49)):
        clob += bytes([rex, 0xB8 + reg_code]) + struct.pack("<Q", rnd.getrandbits(64))
    for x in range(6):          # movq xmmX, rax
        clob += bytes([0x66, 0x48, 0x0F, 0x6E, 0xC0 | (x << 3)])
    clob += b"\x48\x01\xC8"     # add rax, rcx: new flags
    clob += b"\xC3"             # ret
    entered = []

    def at_cb(uc, address, size, data):
        if address == cb:
            entered.append(uc.reg_read(U.UC_X86_REG_RSP))
    m.mu.hook_add(UC_HOOK_CODE, at_cb, begin=cb, end=cb)
    m.mu.mem_write(stub, got_stub)
    m.mu.mem_write(cb, bytes(clob))
    bad_hook = []
    for k in range(args.states):
        st = random_state(rnd, m.stack)
        st["mem"] = {fc: struct.pack("<I", rnd.getrandbits(32))}
        x = m.run(st, [(site, hdr["tick_orig"])], site, site + tl, count=1)
        del entered[:]
        y = m.run(st, [(site, got_hook)], site, site + tl)
        rsp0 = st["gpr"][4]
        seen = [w for w in y["writes"] if not (rsp0 - 0x400 <= w[0] < rsp0)]
        dd = diff(x, y, xmm=True)
        if seen != x["writes"]:
            dd.append("writes %s vs %s" % (seen, x["writes"]))
        if len(entered) != 1 or entered[0] % 16 != 8:
            dd.append("callback entered %d time(s), rsp %% 16 = %s"
                      % (len(entered), [e % 16 for e in entered]))
        if dd:
            bad_hook.append("; ".join(dd))
    print("hook: %d states, stub + clobbering callback vs the increment alone: %d mismatch"
          % (args.states, len(bad_hook)))
    for b in bad_hook[:3]:
        print("  FAIL " + b)
    fails += len(bad_hook)

    # 4. the counters themselves
    nst = len(hdr["stamps"])
    rows = load_clocks(os.path.join(work, "clocks.csv"), hdr["holds"], nst)
    if args.brk == "hold":
        for row in rows:
            row["H"] = [row["S"]] * len(row["H"])   # a copy that never holds
    if args.brk == "stamp":
        kept = [None] * nst                          # the value each was stored with
        for row in rows:
            for i in range(nst):
                if row["set"][i]:
                    kept[i] = row["stamp"][i]
                if kept[i] is not None:
                    row["stamp"][i] = kept[i]
    nseg, probs = check_clocks(rows, hdr["holds"])
    print("counters: %d ticks in %d segments of fps, stock context and the A/B key:"
          " %d problem(s)" % (len(rows), nseg, len(probs)))
    for p in probs[:10]:
        print("  FAIL " + p)
    fails += len(probs)

    # 4b. the loading screen's stamps, carried through every change after them
    ages = stamp_ages(rows, nst)
    checked, carried, sprobs = check_stamps(rows, ages, nst)
    print("loading stamps: %d ticks x stamp checked, %d after an fps or A/B change:"
          " U - stamp is the time since the stamp: %d problem(s)"
          % (checked, carried, len(sprobs)))
    for p in sprobs:
        print("  FAIL " + p)
    fails += len(sprobs)

    # 3c. every gate end to end, fed those counters
    unrel = pefile.PE(path, fast_load=True).get_memory_mapped_image()
    funcs = gfc.load_image()[2]
    dis = gfc.Dis(unrel, None, funcs)

    by_slot = {}
    for r in hdr["reads"]:
        by_slot.setdefault(r["slot"], []).append(r)
    bad_gates, checked = [], 0
    for i, (P, e) in enumerate(hdr["holds"]):
        reads = by_slot.get(2 + i, [])
        # group the reads by the gate they feed
        probes = {}
        for r in reads:
            if r["rva"] in gfc.MIXED:
                continue
            ins = dis(r["rva"])
            if ins.mnemonic == "cmp":
                continue                 # the second read of a mul/cmp pair
            uses, _cut = gfc.slice_value(dis, unrel, funcs, ins)
            setters = sorted({u.setter for u in uses if u.kind == "flag" and
                              dis(u.setter).mnemonic in ("cmp", "test", "sub")})
            start, jat = gfc.gate_probe(dis, ins, setters[0])
            probes[(start, jat)] = [x for x in reads if start <= x["rva"] < jat]
        for (start, jat), members in probes.items():
            cond = gfc.JCC[dis(jat).mnemonic]
            code_on = [(main_base + x["rva"], installed[x["rva"]]) for x in members]
            code_off = [(main_base + x["rva"], x["orig"]) for x in members]
            memo = {}

            def fire(x, on):
                if (x, on) not in memo:
                    st = {"gpr": [0x1000 * (q + 1) for q in range(16)], "flags": 2,
                          "mem": {fc: struct.pack("<I", 0 if on else x),
                                  slots + 4 * (2 + i): struct.pack("<I", x)}}
                    st["gpr"][4] = m.stack - 0x100
                    o = m.run(st, code_on if on else code_off, main_base + start,
                              main_base + jat, count=64)
                    if o["err"] or o["rip"] != main_base + jat:
                        raise RuntimeError("gate %X did not reach its branch: %s"
                                           % (start, o["err"]))
                    memo[(x, on)] = bool(cond(o["flags"]))
                return memo[(x, on)]
            # which side is the event: the one taken on the residue
            ev = fire(e, False)
            wrong_ticks = []
            for row in rows:
                got = fire(row["H"][i], True) == ev
                want = row["S"] % P == e and row["first"] if row["on"] else \
                    fire(row["counter"], False) == ev
                if got != want:
                    wrong_ticks.append(row["tick"])
            checked += 1
            if wrong_ticks:
                bad_gates.append("H(%d,%d) gate %X..%X (%s): wrong on %d ticks, first %d"
                                 % (P, e, start, jat, ",".join("%X" % x["rva"] for x in members),
                                    len(wrong_ticks), wrong_ticks[0]))
            else:
                n_on = [row for row in rows if row["on"]]
                fired = sum(1 for row in n_on if fire(row["H"][i], True) == ev)
                stock = sum(1 for row in n_on if row["first"] and row["S"] % P == e)
                print("  H(%d,%d) gate %06X: installed code fires %d times over %d ticks at 60/120,"
                      " once per stock tick (%d), and as the original at 30"
                      % (P, e, start, fired, len(n_on), stock))

    # the mixed sites, through their pieces
    for rva, mx in sorted(gfc.MIXED.items()):
        r = next(x for x in hdr["reads"] if x["rva"] == rva)
        i = r["slot"] - 2
        a = main_base + rva
        reg_of = {"esi": U.UC_X86_REG_RSI, "edi": U.UC_X86_REG_RDI}

        def value(x, piece_reg):
            """what the installed read (and the value snippet) leave in the register"""
            st = {"gpr": [0x2000 * (q + 1) for q in range(16)], "flags": 2,
                  "mem": {fc: b"\0\0\0\0", slots + 4 * r["slot"]: struct.pack("<I", x)}}
            st["gpr"][4] = m.stack - 0x100
            if mx["value"]:
                s0, s1, _reg = mx["value"]
                o = m.run(st, [(a, installed[rva])], main_base + s0, main_base + s1, count=64)
            else:
                o = m.run(st, [(a, installed[rva])], a, a + r["len"], count=1)
            return o["gpr"][GPRS.index(reg_of[piece_reg])] & 0xFFFFFFFF

        def taken(piece, v):
            st = {"gpr": [0x3000 * (q + 1) for q in range(16)], "flags": 2, "mem": {}}
            st["gpr"][4] = m.stack - 0x100
            st["gpr"][GPRS.index(reg_of[piece[2]])] = v
            o = m.run(st, [], main_base + piece[0], main_base + piece[1], count=64)
            return bool(gfc.JCC[dis(piece[1]).mnemonic](o["flags"]))
        ev_side = taken(mx["event"], value(mx["e"], mx["event"][2]) if mx["value"] else mx["e"])
        memo = {}
        wrong_ticks = []
        for row in rows:
            v = row["H"][i]
            if v not in memo:
                val = value(v, mx["event"][2])
                memo[v] = (taken(mx["event"], val) == ev_side,
                           any(taken(w, val) for w in mx["windows"]))
            fired, inside = memo[v]
            want = (row["S"] % mx["P"] == mx["e"] and row["first"]) if row["on"] else \
                row["counter"] % mx["P"] == mx["e"]
            if fired != want:
                wrong_ticks.append(row["tick"])
            if mx["windows"]:
                if inside != ((row["S"] % mx["P"]) in LOADING_WINDOW):
                    wrong_ticks.append(row["tick"])
        checked += 1
        if wrong_ticks:
            bad_gates.append("mixed %06X: wrong on %d ticks, first %d"
                             % (rva, len(wrong_ticks), wrong_ticks[0]))
        else:
            print("  mixed %06X (%s): the event fires once per stock tick%s"
                  % (rva, mx["what"], ", the window reads as stock on every tick"
                     if mx["windows"] else ""))
    print("gates end to end: %d checked over %d ticks: %d wrong" % (checked, len(rows),
                                                                    len(bad_gates)))
    for b in bad_gates:
        print("  FAIL " + b)
    fails += len(bad_gates)

    # 3d. the widened mask gates
    bad_w = []
    for g in hdr["gates"]:
        t = dis(g["rva"])
        j = gfc.flags_consumer(dis, g["rva"])
        cond = gfc.JCC[j.mnemonic]
        start = g["rva"]
        if t.mnemonic == "test" and "rip" not in t.op_str:
            start = dis.before(g["rva"], 1)[0].address      # the read feeding the test
        for shift in (2, 1, 0):
            code = [(main_base + g["rva"], widened[(g["rva"], shift)])]
            fired = []
            for x in range(0, 4 * 256):
                st = {"gpr": [0x4000 * (q + 1) for q in range(16)], "flags": 2,
                      "mem": {fc: struct.pack("<I", x)}}
                st["gpr"][0] = 5                      # a per-object phase, for et08's add
                st["gpr"][4] = m.stack - 0x100
                o = m.run(st, code, main_base + start, main_base + j.address, count=8)
                if o["err"] or o["rip"] != main_base + j.address:
                    bad_w.append("%06X does not reach its branch" % g["rva"])
                    break
                fired.append(not cond(o["flags"]))   # every gate here is `jne skip`
            period = (g["mask"] + 1) << shift
            ticks = [x for x, f in enumerate(fired) if f]
            if {b - a for a, b in zip(ticks, ticks[1:])} != {period}:
                bad_w.append("%06X at shift %d fires every %s, want %d" % (
                    g["rva"], shift, sorted({b - a for a, b in zip(ticks, ticks[1:])}), period))
    print("widened gates: %d x 3 modes, fire once per (mask + 1) x N ticks: %d wrong"
          % (len(hdr["gates"]), len(bad_w)))
    for b in bad_w:
        print("  FAIL " + b)
    fails += len(bad_w)

    # 3e. the loading screen's own code, fed those counters and stamps: the fade
    #     reader 437120 (U - B31984) and the window test in 4376C0
    #     ((U - B31988) < 480 / mode, which opens the fade). The window must be
    #     open exactly while the time since B31988 is inside it, in the
    #     current mode's terms: 8 s with the fix on or in the stock game (30 Hz
    #     in mode 2, 60 Hz in mode 1), 4 s at 120 with the fix off (the unfixed
    #     game), whatever changed since.
    bad_l = []
    by_rva = {r["rva"]: r for r in hdr["reads"]}
    if sorted(hdr["stamps"]) != [0xB31984, 0xB31988] or 0x437120 not in by_rva or \
            0x4376F1 not in by_rva:
        bad_l.append("the loading family is not the one this check was written for")
    else:
        ret = main_base + 0x43712D                  # int3 padding: stop before it
        W = {n: main_base + a for n, a in (("open", 0xB31980), ("done", 0xB31981),
                                           ("flags", 0xB217C4), ("fading", 0x7A9C00),
                                           ("mode", 0xB6AC45), ("fade", 0xB31984),
                                           ("win", 0xB31988))}

        def call(start, mem, rva):
            st = {"gpr": [0x5000 * (q + 1) for q in range(16)], "flags": 2, "mem": dict(mem)}
            st["gpr"][4] = m.stack - 0x208
            st["mem"][st["gpr"][4]] = struct.pack("<Q", ret)
            return m.run(st, [(main_base + rva, installed[rva])], main_base + start, ret,
                         count=64)
        fade_n = win_n = 0
        for k, (row, age) in enumerate(zip(rows, ages)):
            if age[0] is None or age[1] is None:
                continue
            nxt = rows[k + 1] if k + 1 < len(rows) else row
            edge = (row["fps"], row["muted"]) != (nxt["fps"], nxt["muted"]) or \
                (k and (row["fps"], row["muted"]) != (rows[k - 1]["fps"], rows[k - 1]["muted"]))
            if k % 3 and not edge:
                continue
            base_mem = {slots + 4: struct.pack("<I", row["U"]),
                        fc: struct.pack("<I", row["counter"])}
            mem = dict(base_mem)
            mem[W["fade"]] = struct.pack("<I", row["stamp"][0])
            o = call(0x437120, mem, 0x437120)
            e = o["gpr"][0] & 0xFFFFFFFF
            secs, trans = age[0]
            fade_n += 1
            if o["err"] or abs(e / row["uhz"] - secs) > stamp_tol(trans):
                bad_l.append("fade reader at tick %d (%d fps%s): %d ticks = %.3f s, the clock"
                             " says %.3f s" % (row["tick"], row["fps"],
                                               ", muted" if row["muted"] else "", e,
                                               e / row["uhz"], secs))
            mode = row["real"]
            window = (480 // mode) / row["uhz"]
            secs, trans = age[1]
            if abs(secs - window) <= stamp_tol(trans):
                continue                            # on the edge either way
            mem = dict(base_mem)
            mem.update({W["open"]: b"\x01", W["done"]: b"\x00",
                        W["flags"]: struct.pack("<I", 1 << 18), W["fading"]: b"\x00",
                        W["mode"]: bytes([mode]), W["win"]: struct.pack("<I", row["stamp"][1])})
            o = call(0x4376C0, mem, 0x4376F1)
            inside = any(a == W["fading"] and v == 1 for a, _s, v in o["writes"])
            win_n += 1
            if o["err"] or inside != (secs < window):
                bad_l.append("window test at tick %d (%d fps%s): %s, %.3f s into a %.1f s"
                             " window" % (row["tick"], row["fps"],
                                          ", muted" if row["muted"] else "",
                                          "open" if inside else "closed", secs, window))
        print("loading code: fade reader on %d ticks, window test on %d, through every fps"
              " and A/B change: %d wrong" % (fade_n, win_n, len(bad_l)))
    for b in bad_l[:10]:
        print("  FAIL " + b)
    fails += len(bad_l)

    print("\nwork dir %s\n%s" % (work, "FAILED (%d)" % fails if fails else
                                  "frame-counter clocks verified"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
