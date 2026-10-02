#!/usr/bin/env python3
"""Prove the shadow mode byte install by self-test and emulation.

1. Loads the built DLL into this process and calls its OkamiShadowModeSelfTest
   export, which maps main.dll without running any of it
   (DONT_RESOLVE_DLL_REFERENCES), finds the mode byte the way the game path
   does, runs the real install and switches on, off and on again. It writes
   the bytes each step left in main.dll, and the cave with the shadow byte and
   the memset stubs.

2. Recomputes here, independently, what those bytes must be for the addresses
   the DLL used (each retargeted displacement, each window's jump, each stub)
   and compares them byte for byte. Switching off must leave every site
   exactly as shipped, and switching on again must reproduce the first install.

3. Emulates, under Unicorn, every rewritten instruction as the DLL left it
   against the original, from the same random machine states:

     * a site (write, restore or save), with the real byte holding v in the
       original run and the shadow holding v in the patched run (the real byte
       then holds some other value, so a site still reading it would show):
       registers, flags and the exit address must match, and the patched run
       must make the original's memory writes with the shadow in place of the
       real byte, and no others;
     * a memset return window, entered with the real byte 0 as the memset
       leaves it: registers, flags, exit address and the window's own memory
       writes must match, and the stub must also write 0 to the shadow, 1 to
       the real byte and 1 to its "ran" marker (the byte after the shadow,
       which the watcher logs), and nothing else.

    .venv/Scripts/python tools/verify_shadow_mode.py [--dll .build/bin/dinput8.dll]
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
    from unicorn import x86_const as U
except ImportError:
    sys.exit("needs pefile and unicorn: pip install pefile unicorn")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
HDR = os.path.join(ROOT, "src", "shadow_mode.h")

PAGE = 0x1000
FLAG_MASK = 0xCD5                # CF PF AF ZF SF OF DF
STUB_SIZE = 64
GPRS = [U.UC_X86_REG_RAX, U.UC_X86_REG_RCX, U.UC_X86_REG_RDX, U.UC_X86_REG_RBX,
        U.UC_X86_REG_RSP, U.UC_X86_REG_RBP, U.UC_X86_REG_RSI, U.UC_X86_REG_RDI,
        U.UC_X86_REG_R8, U.UC_X86_REG_R9, U.UC_X86_REG_R10, U.UC_X86_REG_R11,
        U.UC_X86_REG_R12, U.UC_X86_REG_R13, U.UC_X86_REG_R14, U.UC_X86_REG_R15]
GPR_NAMES = "rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()


def parse_header():
    h = open(HDR, encoding="utf-8").read()

    def block(name):
        return re.search(r"%s\[\] = \{\n(.*?)\n\};" % name, h, re.S).group(1)

    sites = []
    for ln in block("kShadowModeSites").splitlines():
        g = re.match(r"\s*\{0x([0-9A-F]+), (\d+), (\d+), (\d+), \{([0-9A-Fx,]+)\}\}", ln)
        sites.append({"rva": int(g.group(1), 16), "len": int(g.group(2)),
                      "disp_off": int(g.group(3)), "kind": int(g.group(4)),
                      "orig": bytes(int(x, 16) for x in g.group(5).split(",")),
                      "text": ln.split("//", 1)[1].strip()})
    windows = []
    for ln in block("kShadowModeZeroWindows").splitlines():
        g = re.match(r"\s*\{0x([0-9A-F]+), (\d+), (\d+), \{\{(\d+), (\d+)\}, \{(\d+), (\d+)\}\}, "
                     r"\{([0-9A-Fx,]+)\}\}", ln)
        n = int(g.group(3))
        fixes = [(int(g.group(4)), int(g.group(5))), (int(g.group(6)), int(g.group(7)))][:n]
        windows.append({"rva": int(g.group(1), 16), "len": int(g.group(2)), "fixes": fixes,
                        "orig": bytes(int(x, 16) for x in g.group(8).split(",")),
                        "text": ln.split("//", 1)[1].strip()})
    return {"sha": re.search(r'SHADOW_MODE_MAIN_SHA1 "([0-9a-f]+)"', h).group(1),
            "mode": int(re.search(r"kShadowModeByteRva = 0x([0-9A-F]+);", h).group(1), 16),
            "sites": sites, "windows": windows}


def rel32(nxt, target):
    r = target - nxt
    assert -2 ** 31 <= r < 2 ** 31, "rel32 out of reach"
    return struct.pack("<i", r)


def expected(hdr, main, shadow, stubs):
    """What the DLL must have written: (site bytes, window bytes, stub bytes)."""
    mode = main + hdr["mode"]
    sites = []
    for s in hdr["sites"]:
        b = bytearray(s["orig"])
        b[s["disp_off"]:s["disp_off"] + 4] = rel32(main + s["rva"] + s["len"], shadow)
        sites.append(bytes(b))
    wins, code = [], []
    for w in hdr["windows"]:
        site, stub = main + w["rva"], stubs[w["rva"]]
        wins.append(b"\xE9" + rel32(site + 5, stub) + b"\xCC" * (w["len"] - 5))
        q = bytearray()
        q += b"\xC6\x05" + rel32(stub + 7, shadow) + b"\x00"
        q += b"\xC6\x05" + rel32(stub + 14, mode) + b"\x01"
        q += b"\xC6\x05" + rel32(stub + 21, shadow + 1) + b"\x01"   # the "ran" marker
        body = bytearray(w["orig"])
        for off, end in w["fixes"]:
            d = struct.unpack_from("<i", w["orig"], off)[0]
            body[off:off + 4] = rel32(stub + len(q) + end, site + end + d)
        q += body
        q += b"\xE9" + rel32(stub + len(q) + 5, site + w["len"])
        code.append(bytes(q))
    return sites, wins, code


# ---------------------------------------------------------------------------
# emulation
# ---------------------------------------------------------------------------

class Machine:
    def __init__(self, img, main, cave, stack):
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        size = (len(img) + PAGE - 1) & ~(PAGE - 1)
        mu.mem_map(main, size, UC_PROT_ALL)
        mu.mem_write(main, bytes(img))
        mu.mem_map(cave, PAGE, UC_PROT_ALL)
        mu.mem_map(stack - 0x10000, 0x20000, UC_PROT_ALL)
        self.stack = stack
        self.writes = []
        mu.hook_add(UC_HOOK_MEM_WRITE, self._write)

    def _write(self, uc, access, address, size, value, data):
        self.writes.append((address, size, value & ((1 << (8 * size)) - 1)))

    def run(self, st, code, start, until, bytes_at):
        """Put each (address, bytes) of `code` in place, set the state, run
        start..until; the result. Everything is put back afterwards."""
        mu = self.mu
        saved = [(a, bytes(mu.mem_read(a, len(b)))) for a, b in code + list(st["mem"].items())]
        for a, b in code:
            mu.mem_write(a, b)
        # Unicorn keeps translated blocks across mem_write: without this, the
        # run after a patched one executes the patched code at the same address
        mu.ctl_flush_tb()
        for a, b in st["mem"].items():
            mu.mem_write(a, b)
        for r, v in zip(GPRS, st["gpr"]):
            mu.reg_write(r, v)
        mu.reg_write(U.UC_X86_REG_EFLAGS, st["flags"])
        self.writes = []
        err = None
        try:
            mu.emu_start(start, until, count=32)
        except UcError as e:
            err = str(e)
        out = {"err": err, "rip": mu.reg_read(U.UC_X86_REG_RIP),
               "gpr": [mu.reg_read(r) for r in GPRS],
               "flags": mu.reg_read(U.UC_X86_REG_EFLAGS) & FLAG_MASK,
               "writes": list(self.writes),
               "bytes": {a: bytes(mu.mem_read(a, 1))[0] for a in bytes_at}}
        for a, b in reversed(saved):
            mu.mem_write(a, b)
        return out


def random_state(rnd, stack):
    gpr = [rnd.getrandbits(64) for _ in range(16)]
    gpr[4] = stack - rnd.randrange(0, 256) * 16
    return {"gpr": gpr, "flags": 0x2 | (rnd.getrandbits(12) & FLAG_MASK & ~0x400)}


def same_regs(a, b):
    d = ["%s %X vs %X" % (n, x, y) for n, x, y in zip(GPR_NAMES, a["gpr"], b["gpr"]) if x != y]
    if a["flags"] != b["flags"]:
        d.append("flags %03X vs %03X" % (a["flags"], b["flags"]))
    if a["rip"] != b["rip"]:
        d.append("exit %X vs %X" % (a["rip"], b["rip"]))
    if a["err"] or b["err"]:
        d.append("fault %s / %s" % (a["err"], b["err"]))
    return d


def emulate(hdr, img, main, shadow, stubs, on_sites, on_wins, cave_img, states):
    mode = main + hdr["mode"]
    cave = shadow & ~(PAGE - 1)
    stack = 0x10000000
    while main - 0x100000 <= stack <= main + len(img) + 0x100000 or \
            cave - 0x100000 <= stack <= cave + 0x100000:
        stack += 0x40000000
    m = Machine(img, main, cave, stack)
    m.mu.mem_write(cave, cave_img)
    rnd = random.Random(0x5AD0)
    bad = 0
    runs = 0
    for s, patched in zip(hdr["sites"], on_sites):
        site = main + s["rva"]
        fails = []
        for k in range(states):
            v = (0, 1, 2, 255)[k] if k < 4 else rnd.randrange(256)
            other = rnd.choice([x for x in range(256) if x != v])
            st = random_state(rnd, stack)
            # original: the real byte holds v, the shadow something else
            st["mem"] = {mode: bytes([v]), shadow: bytes([other])}
            a = m.run(st, [(site, s["orig"])], site, site + s["len"], [mode, shadow])
            # patched: the shadow holds v, the real byte something else
            st["mem"] = {mode: bytes([other]), shadow: bytes([v])}
            b = m.run(st, [(site, patched)], site, site + s["len"], [mode, shadow])
            runs += 2
            d = same_regs(a, b)
            moved = [(mode if w[0] == shadow else w[0], w[1], w[2]) for w in b["writes"]]
            if moved != a["writes"]:
                d.append("writes %s vs %s" % (fmtw(a["writes"]), fmtw(b["writes"])))
            if b["bytes"][mode] != other:
                d.append("the patched run changed the real byte")
            if d:
                fails.append("v=%d: %s" % (v, "; ".join(d)))
        if fails:
            bad += 1
            print("  FAIL %06X %s\n    %s" % (s["rva"], s["text"], "\n    ".join(fails[:3])))
    for w, jump in zip(hdr["windows"], on_wins):
        site = main + w["rva"]
        fails = []
        for k in range(states):
            other = rnd.randrange(1, 256)
            st = random_state(rnd, stack)
            # both enter as the memset leaves them: the real byte 0
            st["mem"] = {mode: b"\x00", shadow: bytes([other])}
            a = m.run(st, [(site, w["orig"])], site, site + w["len"], [mode, shadow])
            b = m.run(st, [(site, jump)], site, site + w["len"], [mode, shadow])
            runs += 2
            d = same_regs(a, b)
            want = [(shadow, 1, 0), (mode, 1, 1), (shadow + 1, 1, 1)] + a["writes"]
            if b["writes"] != want:
                d.append("writes %s, want %s" % (fmtw(b["writes"]), fmtw(want)))
            if (b["bytes"][shadow], b["bytes"][mode]) != (0, 1):
                d.append("after the stub shadow=%d real=%d" % (b["bytes"][shadow], b["bytes"][mode]))
            if d:
                fails.append("; ".join(d))
        if fails:
            bad += 1
            print("  FAIL window %06X %s\n    %s" % (w["rva"], w["text"], "\n    ".join(fails[:3])))
    return bad, runs


def fmtw(ws):
    return "[%s]" % ", ".join("%X:%d=%X" % w for w in ws)


# ---------------------------------------------------------------------------
# the oscillators' frame counter copy (frame_phases.h), the shadow's first user
# ---------------------------------------------------------------------------

def check_slow_frame(path):
    """Problems in the DLL's own run of updateSlowFrame (OkamiSlowFrameSelfTest)."""
    rows = [{k: int(v) for k, v in r.items()} for r in csv.DictReader(open(path))]
    problems = []
    segs = []
    for r in rows:
        if not segs or (segs[-1][0]["fps"], segs[-1][0]["shadow"]) != (r["fps"], r["shadow"]):
            segs.append([])
        segs[-1].append(r)
    prev = None
    for seg in segs:
        fps, shadow = seg[0]["fps"], seg[0]["shadow"]
        n = 0 if fps == 30 else fps // (60 if shadow == 1 else 30)
        name = "%d fps, stock mode %d" % (fps, shadow)
        for r in seg:
            if r["active"] != (n > 0):
                problems.append("%s: tick %d active=%d" % (name, r["tick"], r["active"]))
                break
        if n == 0:
            bad = [r["tick"] for r in seg if r["copy"] != r["counter"]]
            if bad:
                problems.append("%s: the copy is not the counter at tick %d" % (name, bad[0]))
        else:
            # never more than one step per tick, across the switch into it too
            last = prev["copy"] if prev is not None and prev["fps"] != 30 else None
            steps = []
            for r in seg:
                if last is not None and r["copy"] - last not in (0, 1):
                    problems.append("%s: the copy jumps by %d at tick %d"
                                    % (name, r["copy"] - last, r["tick"]))
                    break
                if last is not None and r["copy"] != last:
                    steps.append(r["tick"])
                last = r["copy"]
            gaps = {b - a for a, b in zip(steps, steps[1:])}
            if len(seg) >= 3 * n and gaps != {n}:
                problems.append("%s: steps every %s ticks, want %d" % (name, sorted(gaps), n))
        prev = seg[-1]
    return len(segs), problems


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--states", type=int, default=64, help="random states per site")
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    args = ap.parse_args()

    hdr = parse_header()
    path = os.path.join(GAME, "main.dll")
    pe = pefile.PE(path, fast_load=True)
    img = pe.get_memory_mapped_image()
    import hashlib
    sha = hashlib.sha1(open(path, "rb").read()).hexdigest()
    if sha != hdr["sha"]:
        sys.exit("main.dll sha1 %s is not the build the header was generated from (%s)"
                 % (sha, hdr["sha"]))

    # 1. the DLL's own install, on a mapped main.dll
    work = args.out or tempfile.mkdtemp(prefix="okami_shadow_selftest_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")   # a private copy: its log lands here
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiShadowModeSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    fn.restype = ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    print("DLL self-test (rc %d):\n  %s" % (rc, report.rstrip().replace("\n", "\n  ")))
    fails = 0 if rc == 0 else 1
    vals, stubs = {}, {}
    for ln in report.splitlines():
        p = ln.split()
        if len(p) == 2 and p[0] in ("main", "mode", "shadow"):
            vals[p[0]] = int(p[1], 16)
        elif len(p) == 3 and p[0] == "stub":
            stubs[int(p[1], 16)] = int(p[2], 16)
    if "shadow" not in vals:
        print("no install to check; see %s" % work)
        return 1
    main_base, shadow = vals["main"], vals["shadow"]
    if vals["mode"] != main_base + hdr["mode"]:
        print("FAIL the DLL resolved the mode byte at main+%X" % (vals["mode"] - main_base))
        fails += 1

    # 2. the bytes, against an independent computation
    def split(blob):
        out, pos = [], 0
        for x in hdr["sites"] + hdr["windows"]:
            out.append(blob[pos:pos + x["len"]])
            pos += x["len"]
        assert pos == len(blob), "dump size"
        return out[:len(hdr["sites"])], out[len(hdr["sites"]):]

    on = open(os.path.join(work, "on.bin"), "rb").read()
    on_sites, on_wins = split(on)
    off_sites, off_wins = split(open(os.path.join(work, "off.bin"), "rb").read())
    cave_img = open(os.path.join(work, "cave.bin"), "rb").read()
    want_sites, want_wins, want_code = expected(hdr, main_base, shadow, stubs)
    cave = shadow & ~(PAGE - 1)
    n = len(hdr["sites"]) + len(hdr["windows"])
    wrong = [s["rva"] for s, got, want in zip(hdr["sites"], on_sites, want_sites) if got != want]
    wrong += [w["rva"] for w, got, want in zip(hdr["windows"], on_wins, want_wins) if got != want]
    for w, code in zip(hdr["windows"], want_code):
        off = stubs[w["rva"]] - cave
        if cave_img[off:off + len(code)] != code or len(code) > STUB_SIZE:
            wrong.append(("stub", w["rva"]))
    print("installed bytes: %d sites and %d stub(s) compared, %d differ%s" % (
        n, len(want_code), len(wrong), (": " + ", ".join(map(str, wrong[:5]))) if wrong else ""))
    restored = [x["rva"] for x, got in zip(hdr["sites"] + hdr["windows"], off_sites + off_wins)
                if got != x["orig"]]
    print("switched off: %d of %d sites hold their original bytes" % (n - len(restored), n))
    again = open(os.path.join(work, "on2.bin"), "rb").read() == on
    print("switched on again: %s" % ("identical to the first install" if again else "DIFFERENT"))
    fails += bool(wrong) + bool(restored) + (not again)

    # 3. emulation of the installed bytes against the originals
    bad, runs = emulate(hdr, img, main_base, shadow, stubs, on_sites, on_wins, cave_img,
                        args.states)
    print("emulation: %d sites and %d window(s), %d states each (%d runs): %d mismatch" % (
        len(hdr["sites"]), len(hdr["windows"]), args.states, runs, bad))
    fails += bad

    # 4. the oscillators' frame counter copy follows the shadow
    sf = lib.OkamiSlowFrameSelfTest
    sf.argtypes = [ctypes.c_char_p]
    sf.restype = ctypes.c_int
    if sf(work.encode("mbcs")) != 0:
        print("FAIL the frame counter copy self-test did not run")
        fails += 1
    else:
        nseg, problems = check_slow_frame(os.path.join(work, "slow_frame.csv"))
        print("frame counter copy: %d segments of fps and stock context, %d problem(s)"
              % (nseg, len(problems)))
        for p in problems:
            print("  FAIL " + p)
        fails += len(problems)
    print("\nwork dir %s\n%s" % (work, "FAILED" if fails else "shadow mode verified"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
