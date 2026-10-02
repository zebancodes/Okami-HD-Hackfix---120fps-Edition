#!/usr/bin/env python3
"""Prove the phase-step and decay pools follow the stock context, offline.

The phase steps (src/phase_steps.h) and decay factors (src/decay_factors.h)
read private copies of their constants, which the patch keeps scaled. A copy
used to be scaled by the time scale alone, as if the stock game always ticked
at 30. It ticks at 60 in its mode-1 contexts (options, memory card, pause-menu
interior, title), so the sites that run there ran at half their stock speed at
60 and 120 fps. The scale now doubles in those contexts, on the tick the
shadow mode byte says so.

1. Loads the built DLL into this process and calls its OkamiConstPoolSelfTest
   export, which maps main.dll without running any of it
   (DONT_RESOLVE_DLL_REFERENCES), runs the real install, and drives the slots
   one tick at a time through every combination of fps (120, 60, 30 = the
   patch off), the stock game's mode byte (1, 2, and 0 before the game writes
   it), the phase key, a missing shadow and a bad time scale: through the
   per-tick hook (frameClockOnTick), with a watcher pass before each tick that
   must write nothing, and through the watcher's fallback.

2. Checks, independently:
     * every installed instruction: the shipped bytes with the displacement
       pointing at its constant's slot, and each slot's original value equal to
       the constant in main.dll;
     * every slot after every tick: phase steps exactly original x scale,
       decays original ** scale (the original itself at scale 1), where the
       scale is the time scale (0.25 at 120, 0.5 at 60), doubled in a stock
       60 Hz context, at most 1, and 1 with the patch off or muted;
     * that the slots change on the very tick the context does.

3. Emulates under Unicorn every installed instruction (366 addss/subss and 195
   mulss), with the slots the DLL left in each state, against the original:
   N patched ticks must do what one stock tick does, where N is the ticks per
   stock tick in that state (4 in play at 120, 2 in the 60 Hz menus at 120 and
   in play at 60, 1 in the 60 Hz menus at 60 and at 30 fps, bit for bit).

    .venv/Scripts/python tools/verify_const_pools.py [--dll .build/bin/dinput8.dll]
                                                    [--break context|late|disp]
Exits non-zero on any mismatch. Each --break must make it fail.
"""
import argparse
import csv
import ctypes
import math
import os
import random
import re
import shutil
import struct
import sys
import tempfile

try:
    import pefile
    from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL
    from unicorn import x86_const as U
except ImportError:
    sys.exit("needs pefile and unicorn: pip install pefile unicorn")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
PAGE = 0x1000
XMMS = [getattr(U, "UC_X86_REG_XMM%d" % i) for i in range(8)]
OPS = {0x58: "addss", 0x5C: "subss", 0x59: "mulss"}
# the phase steps the 2026-09-18 tracer session saw running in a stock 60 Hz
# context (docs/animation/classification.csv), reported by name below
TRACED_60 = {0x1C5059: "memory-card save wave", 0x42EEDC: "pause menu",
             0x42EF08: "pause menu", 0x439B48: "scene transition (30 and 60 Hz)"}


def parse_table(name, array):
    h = open(os.path.join(ROOT, "src", name), encoding="utf-8").read()
    body = re.search(r"%s\[\] = \{\n(.*?)\n\};" % array, h, re.S).group(1)
    out = []
    for ln in body.splitlines():
        g = re.match(r"\s*\{0x([0-9A-F]+), 0x([0-9A-F]+), \{([^}]*)\}\},\s*//\s*(.*)", ln)
        out.append({"rva": int(g.group(1), 16), "const": int(g.group(2), 16),
                    "orig": bytes(int(x, 16) for x in g.group(3).split(",")),
                    "text": g.group(4).strip()})
    return out


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def from_bits(u):
    return struct.unpack("<f", struct.pack("<I", u))[0]


def ulp(x):
    x = abs(x)
    if x == 0.0:
        return 2.0 ** -149
    return 2.0 ** (math.frexp(x)[1] - 24)


def scale_of(r, context=True):
    """What one tick is worth, as a fraction of a stock tick. context=False is
    the rule before this change: the time scale alone."""
    if r["fps"] == 30 or r["muted"] or r["bad"]:
        return 1.0
    ts = 0.25 if r["fps"] == 120 else 0.5
    if context and r["shadow"] and r["mode"] == 1:
        ts *= 2.0
    return min(ts, 1.0)


def want_slots(origs, kind, s):
    if kind == "phase":
        return [bits(f32(o * s)) for o in origs]
    return [bits(o) if s >= 0.999 else bits(f32(o ** s)) for o in origs]


def split_hex(txt):
    return [int(txt[i:i + 8], 16) for i in range(0, len(txt), 8)]


class Machine:
    """main.dll mapped where the DLL loaded it, plus the two pool pages."""

    def __init__(self, img, main, pages):
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        mu.mem_map(main, (len(img) + PAGE - 1) & ~(PAGE - 1), UC_PROT_ALL)
        mu.mem_write(main, bytes(img))
        for p in sorted(set(pages)):
            mu.mem_map(p, PAGE, UC_PROT_ALL)

    def step(self, at, code, reg, x, times):
        """Run the 8-byte instruction `code` at `at` `times` times, xmm<reg>
        starting at x; the low float and whether the upper lanes survived."""
        mu = self.mu
        mu.mem_write(at, code)
        mu.ctl_flush_tb()
        upper = 0x0123456789ABCDEF_FEDCBA98 << 32
        mu.reg_write(XMMS[reg], upper | bits(x))
        for _ in range(times):
            mu.emu_start(at, at + len(code), count=1)
        v = mu.reg_read(XMMS[reg])
        return from_bits(v & 0xFFFFFFFF), (v >> 32) == (upper >> 32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--values", type=int, default=3, help="starting values per site and state")
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    ap.add_argument("--break", dest="brk", default=None, choices=("context", "late", "disp"),
                    help="corrupt one thing the DLL produced; the run must then FAIL"
                         " (context: the old time-scale-only slots in 60 Hz contexts;"
                         " late: every change lands one tick late; disp: one displacement"
                         " points at the next slot)")
    args = ap.parse_args()

    tables = {"phase": parse_table("phase_steps.h", "kPhaseSites"),
              "decay": parse_table("decay_factors.h", "kDecaySites")}
    path = os.path.join(GAME, "main.dll")
    pe = pefile.PE(path, fast_load=True)
    img = bytearray(pe.get_memory_mapped_image())
    fails = 0
    for kind, sites in tables.items():
        bad = [s["rva"] for s in sites if bytes(img[s["rva"]:s["rva"] + 8]) != s["orig"]]
        if bad:
            sys.exit("main.dll is not the build %s was generated from (main+%X differs)"
                     % (kind, bad[0]))

    # 1. the DLL's own install and run, on a mapped main.dll
    work = args.out or tempfile.mkdtemp(prefix="okami_pools_selftest_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")   # a private copy: its log lands here
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiConstPoolSelfTest
    fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    print("DLL self-test (rc %d):\n  %s" % (rc, report.rstrip().replace("\n", "\n  ")))
    if rc != 0:
        print("\nwork dir %s\nFAILED" % work)
        return 1
    vals = {}
    for ln in report.splitlines():
        p = ln.split()
        if p and p[0] in ("main", "phase", "decay"):
            vals[p[0]] = int(p[1], 16)
    main_base = vals["main"]

    # 2a. the installed instructions and the pools' layout
    pools = {"phase": [], "decay": []}
    for r in csv.DictReader(open(os.path.join(work, "pools.csv"), newline="")):
        pools[r["pool"]].append((int(r["rva"], 16), int(r["orig"], 16)))
    blob = open(os.path.join(work, "sites.bin"), "rb").read()
    installed, pos = {}, 0
    for kind in ("phase", "decay"):
        for s in tables[kind]:
            installed[(kind, s["rva"])] = blob[pos:pos + 8]
            pos += 8
    assert pos == len(blob), "sites.bin size"
    if args.brk == "disp":
        s = tables["phase"][len(tables["phase"]) // 2]
        b = bytearray(installed[("phase", s["rva"])])
        b[4:8] = struct.pack("<i", struct.unpack_from("<i", b, 4)[0] + 4)
        installed[("phase", s["rva"])] = bytes(b)
    wrong = []
    for kind, sites in tables.items():
        order = []                      # slots in first-use order, as poolSlotFor makes them
        for s in sites:
            if s["const"] not in order:
                order.append(s["const"])
        got = [c for c, _ in pools[kind]]
        if got != order:
            wrong.append("%s pool layout %s..., want %s..." % (kind, got[:4], order[:4]))
        for c, o in pools[kind]:
            if o != struct.unpack_from("<I", img, c)[0]:
                wrong.append("%s slot for main+%X holds %08X, main.dll %08X"
                             % (kind, c, o, struct.unpack_from("<I", img, c)[0]))
        for s in sites:
            slot = vals[kind] + 4 * order.index(s["const"])
            want = bytearray(s["orig"])
            want[4:8] = struct.pack("<i", slot - (main_base + s["rva"] + 8))
            if installed[(kind, s["rva"])] != bytes(want):
                wrong.append("%s main+%X: %s, want %s" % (kind, s["rva"],
                             installed[(kind, s["rva"])].hex(), bytes(want).hex()))
    n_sites = len(tables["phase"]) + len(tables["decay"])
    print("\ninstalled: %d instructions over %d + %d slots, %d wrong"
          % (n_sites, len(pools["phase"]), len(pools["decay"]), len(wrong)))
    for w in wrong[:10]:
        print("  FAIL " + w)
    fails += len(wrong)

    # 2b. every slot after every tick
    rows = []
    for r in csv.DictReader(open(os.path.join(work, "ticks.csv"), newline="")):
        row = {k: int(r[k]) for k in ("tick", "fps", "mode", "muted", "shadow", "bad", "n",
                                      "watcher_wrote")}
        row["path"] = r["path"]
        row["phase"], row["decay"] = split_hex(r["phase"]), split_hex(r["decay"])
        rows.append(row)
    origs = {k: [from_bits(o) for _, o in pools[k]] for k in pools}
    if args.brk == "context":
        for r in rows:
            if scale_of(r) != scale_of(r, context=False):
                for k in ("phase", "decay"):
                    r[k] = want_slots(origs[k], k, scale_of(r, context=False))
    elif args.brk == "late":
        shifted = [dict(r) for r in rows]
        for i in range(1, len(rows)):
            if scale_of(rows[i]) != scale_of(rows[i - 1]):
                for k in ("phase", "decay"):
                    shifted[i][k] = rows[i - 1][k]
        rows = shifted
    bad_ticks, changes, contexts = [], 0, set()
    for i, r in enumerate(rows):
        s = scale_of(r)
        what = "tick %d (%s, %d fps, mode %d, muted %d, shadow %d%s)" % (
            r["tick"], r["path"], r["fps"], r["mode"], r["muted"], r["shadow"],
            ", bad time scale" if r["bad"] else "")
        if i and s != scale_of(rows[i - 1]):
            changes += 1
        contexts.add((r["fps"], r["mode"] if r["shadow"] else -1, r["muted"]))
        if r["n"] != round(1.0 / s):
            bad_ticks.append("%s: shows /%d, want /%d" % (what, r["n"], round(1.0 / s)))
        if r["path"] == "hook" and r["watcher_wrote"]:
            bad_ticks.append("%s: the watcher wrote the slots while the hook keeps them" % what)
        if r["phase"] != want_slots(origs["phase"], "phase", s):
            k = next(j for j, (a, b) in enumerate(zip(r["phase"], want_slots(
                origs["phase"], "phase", s))) if a != b)
            bad_ticks.append("%s: phase slot %d holds %g, want %g x %g" % (
                what, k, from_bits(r["phase"][k]), origs["phase"][k], s))
        for k, (got, o) in enumerate(zip(r["decay"], origs["decay"])):
            want = o if s >= 0.999 else o ** s
            if (s >= 0.999 and got != bits(o)) or abs(from_bits(got) - want) > ulp(want):
                bad_ticks.append("%s: decay slot %d holds %.9g, want %.9g ** %g" % (
                    what, k, from_bits(got), o, s))
                break
    print("slots: %d ticks, %d changes of scale, %d states, %d wrong"
          % (len(rows), changes, len(contexts), len(bad_ticks)))
    for b in bad_ticks[:10]:
        print("  FAIL " + b)
    fails += len(bad_ticks)

    # 3. every instruction under Unicorn: N patched ticks against one stock tick
    # the slots of one hook tick of each fps and stock context, shadow in, not
    # muted (the per-tick check above has already tied every tick to its state)
    states = {}
    for r in rows:
        key = (r["fps"], r["mode"])
        if (r["path"] == "hook" and r["shadow"] and not r["muted"] and not r["bad"]
                and r["fps"] != 30 and r["mode"] in (1, 2) and key not in states):
            states[key] = r
    for fps, mode in ((120, 2), (120, 1), (60, 2), (60, 1)):
        if (fps, mode) not in states:
            sys.exit("the self-test has no settled %d fps mode %d tick" % (fps, mode))
    off = next(r for r in rows if r["fps"] == 30)
    states[(30, off["mode"])] = off
    m = Machine(img, main_base, [vals["phase"] & ~(PAGE - 1), vals["decay"] & ~(PAGE - 1)])
    rnd = random.Random(0xC0057)
    emu_bad, runs, headline = [], 0, []
    for kind, sites in tables.items():
        order = [c for c, _ in pools[kind]]
        for s in sites:
            at, code = main_base + s["rva"], s["orig"]
            op, reg = OPS.get(code[2]), (code[3] >> 3) & 7
            if code[:2] != b"\xF3\x0F" or op is None or code[3] & 0xC7 != 0x05:
                emu_bad.append("%s main+%X is not an 8-byte addss/subss/mulss [rip]"
                               % (kind, s["rva"]))
                continue
            k = struct.unpack_from("<f", img, s["const"])[0]
            xs = [1.0] + [f32(rnd.uniform(-64.0, 64.0)) for _ in range(args.values - 1)]
            stock = {x: m.step(at, code, reg, x, 1)[0] for x in xs}
            for (fps, mode), r in states.items():
                n = round(1.0 / scale_of(r))
                m.mu.mem_write(vals[kind], struct.pack("<%dI" % len(r[kind]), *r[kind]))
                for x in xs:
                    got, upper = m.step(at, installed[(kind, s["rva"])], reg, x, n)
                    runs += 1
                    want = stock[x]
                    if kind == "phase":
                        tol = (n + 1) * ulp(max(abs(x), abs(want), abs(k)))
                    else:
                        tol = 4 * (n + 1) * 2.0 ** -24 * max(abs(want), 1e-30)
                    ok = upper and (got == want if n == 1 else abs(got - want) <= tol)
                    if not ok:
                        emu_bad.append("%s main+%X (%s) at %d fps mode %d: %d ticks from %g"
                                       " give %.9g, one stock tick %.9g%s"
                                       % (kind, s["rva"], s["text"], fps, mode, n, x, got, want,
                                          "" if upper else ", upper lanes changed"))
                if kind == "phase" and s["rva"] in TRACED_60 and (fps, mode) == (120, 1):
                    new = f32(from_bits(r["phase"][order.index(s["const"])]))
                    old = f32(k * 0.25)
                    sign = -1.0 if op == "subss" else 1.0
                    headline.append("  main+%X %-32s %d ticks advance %+.6g (one stock tick"
                                    " %+.6g); the time scale alone gave %+.6g"
                                    % (s["rva"], TRACED_60[s["rva"]], n, sign * n * new,
                                       sign * k, sign * n * old))
    print("emulation: %d sites x %d states x %d values = %d runs, %d wrong"
          % (n_sites, len(states), len(xs), runs, len(emu_bad)))
    for b in emu_bad[:10]:
        print("  FAIL " + b)
    fails += len(emu_bad)
    print("\nthe phase steps the tracer saw in a stock 60 Hz context, at 120 fps there:")
    print("\n".join(headline))
    print("\nwork dir %s\n%s" % (work, "FAILED" if fails else "phase-step and decay pools verified"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
