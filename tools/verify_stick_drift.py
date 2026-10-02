#!/usr/bin/env python3
"""Prove the stick-drift fix offline (dinput8_proxy.cpp, kStickDriftSites).

The wall recoil (player state 0x2B), its follow-on 0x2C and state 0x48 steer
with the stick each tick:

    v(+0x10E8) = v * table7A81B8[mode - 1] + |stick| * 1.7 / 1024
    position  += RotateY(heading) * (0, 0, v)

The mode constants make the decay k^ts. The fix multiplies the stick term by
f(ts) = ts (1 - k^ts) / (1 - k), so that she moves as far a second, and reaches
her speed as fast, at every tick rate as at 30.

1. Calls the DLL's OkamiStickDriftSelfTest: main.dll mapped without running
   it, the real installs of the mode constants and the three detours, then the
   gain and the decay table's fast entry the watcher leaves at 30, 60 and 120
   fps, muted and switched off.
2. Recomputes the installed bytes: each site's jump and NOPs, each stub's
   relocated multiply (the same 1/1024 constant), its multiply by the gain
   slot, its jump back.
3. Checks every state: gain = f(ts) while on and 1 otherwise, fast = k^ts.
4. Emulates each site under Unicorn, main.dll and the cave where the DLL put
   them, from the multiply to the store to +0x10E8: the stored value must be
   the original's with the stick term multiplied by the gain, bit for bit, for
   random stick magnitudes, velocities and gains.
5. Runs the recurrence itself, stick held, with the values the DLL left: the
   distance covered at every stock tick's time at 60 and 120 fps must track
   30 fps within 1% of the distance, and the settled speed a second within
   0.5%. The unfixed 120 is printed for scale.

    .venv/Scripts/python tools/verify_stick_drift.py
    --break gain    uses gain 1 at 60 and 120 (the shipped code) and must FAIL
    --break square  uses ts^2 (the airborne sites' rule) and must FAIL
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

import capstone
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_HOOK_CODE
from unicorn import x86_const as U

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.dirname(HERE)
PROXY = os.path.join(ROOT, "src", "dinput8_proxy.cpp")
STICK = 0x6AEFD0      # 1/1024
PAGE = 0x1000
OBJ = 0x10000000


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def table():
    src = open(PROXY, encoding="utf-8").read()
    sites = [(int(a, 16), int(b, 16)) for a, b in re.findall(
        r"\{0x([0-9A-F]+), 0x([0-9A-F]+)\},\s*// state",
        re.search(r"kStickDriftSites\[\]\[2\] = \{(.*?)\};", src, re.S).group(1))]
    orig = [bytes(int(x, 16) for x in row.split(","))
            for row in re.findall(r"\{([^{}]+)\}", re.search(
                r"kStickDriftOrig\[\]\[8\] = \{(.*?)\n\};", src, re.S).group(1))]
    return sites, orig


def gain(k, ts, on):
    if not on or not (0.05 < ts < 0.999):
        return 1.0
    return f32(ts * (1.0 - f32(k ** ts)) / (1.0 - k))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--break", dest="broken", choices=("gain", "square"))
    args = ap.parse_args()
    problems = []
    sites, orig = table()
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    img = bytearray(pefile.PE(data=raw, fast_load=True).get_memory_mapped_image())

    # 1. the DLL's own install and updates
    work = tempfile.mkdtemp(prefix="okami_stick_drift_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    fn = ctypes.WinDLL(dll).OkamiStickDriftSelfTest
    fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    rep = open(os.path.join(work, "report.txt")).read()
    if rc:
        print(rep)
        sys.exit("DLL self-test failed (rc %d)" % rc)
    vals = dict(ln.split(None, 1) for ln in rep.splitlines() if len(ln.split()) == 2)
    main_base, cave_base = int(vals["main"], 16), int(vals["cave"], 16)
    k = f32(float(vals["k"]))
    cave = bytearray(open(os.path.join(work, "cave.bin"), "rb").read())
    patched = open(os.path.join(work, "sites.bin"), "rb").read()
    rows = list(csv.DictReader(open(os.path.join(work, "states.csv"))))
    print("1. DLL self-test: %d sites installed, k = %g, %d states" % (len(sites), k, len(rows)))

    # 2. the installed bytes, recomputed
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    stubs = []
    for i, ((site, resume), o) in enumerate(zip(sites, orig)):
        if bytes(img[site:site + 8]) != o:
            problems.append("main+%X no longer holds the audited multiply" % site)
            continue
        got = patched[8 * i:8 * i + 8]
        if got[0] != 0xE9 or got[5:] != b"\x90\x90\x90":
            problems.append("main+%X is not a jump and NOP padding" % site)
            continue
        stub = main_base + site + 5 + struct.unpack_from("<i", got, 1)[0]
        off = stub - cave_base
        ins = list(md.disasm(bytes(cave[off:off + 32]), stub))[:3]
        want = [("mulss", STICK + main_base), ("mulss", cave_base), ("jmp", main_base + resume)]
        for n, (mn, target) in enumerate(want):
            if n >= len(ins) or ins[n].mnemonic != mn:
                problems.append("stub for %X: instruction %d is not %s" % (site, n, mn))
                break
            if mn == "jmp":
                t = ins[n].operands[0].imm
            else:
                op = ins[n].operands[1]
                t = ins[n].address + ins[n].size + op.mem.disp if op.mem.base == capstone.x86.X86_REG_RIP else None
                if ins[n].operands[0].reg != capstone.x86.X86_REG_XMM0:
                    problems.append("stub for %X: instruction %d is not on xmm0" % (site, n))
            if t != target:
                problems.append("stub for %X: instruction %d reaches %s, not %X" % (site, n, t, target))
        stubs.append(stub)
    print("2. installed bytes: %d sites and stubs checked" % len(stubs))

    # 3. the gain and the decay in every state
    for r in rows:
        fps, muted, enabled = int(r["fps"]), int(r["muted"]), int(r["enabled"])
        ts = f32(float(r["ts"]))
        on = fps != 30 and not muted and enabled
        want = gain(k, ts, on)
        g = f32(float(r["gain"]))
        if abs(g - want) > 2e-7:
            problems.append("state %s: gain %r, want %r" % (r["state"], g, want))
        fast = f32(float(r["fast"]))
        # the mode constants write k^ts at 120; at 60, muted, or at 30 they
        # put the shipped entry back rather than recompute it (sqrt(0.86) as
        # shipped is 0.9273600, not the true 0.9273618)
        shipped = struct.unpack_from("<f", img, 0x7A81B8)[0]
        want_fast = f32(k ** 0.25) if fps == 120 and not muted else shipped
        if abs(struct.unpack("<I", struct.pack("<f", fast))[0] -
               struct.unpack("<I", struct.pack("<f", want_fast))[0]) > 1:
            problems.append("state %s: decay %r, want %r" % (r["state"], fast, want_fast))
    print("3. states: %s" % ", ".join("%s gain %.4f decay %.4f" % (r["state"], float(r["gain"]),
                                                                  float(r["fast"])) for r in rows))

    # 4. each site end to end under Unicorn
    mu = Uc(UC_ARCH_X86, UC_MODE_64)
    size = (len(img) + PAGE - 1) & ~(PAGE - 1)
    mu.mem_map(main_base, size, UC_PROT_ALL)
    im = bytearray(img)
    for i, (site, _r) in enumerate(sites):
        im[site:site + 8] = patched[8 * i:8 * i + 8]
    mu.mem_write(main_base, bytes(im))
    mu.mem_map(cave_base, len(cave), UC_PROT_ALL)
    mu.mem_write(cave_base, bytes(cave))
    mu.mem_map(OBJ, 0x4000, UC_PROT_ALL)
    mu.mem_map(0x7FF000000000 - 0x10000, 0x10000, UC_PROT_ALL)
    rnd = random.Random(7)
    runs = 0
    for site, resume in sites:
        # the store to +0x10E8 that follows the add
        store = next(i for i in md.disasm(bytes(img[resume:resume + 16]), resume)
                     if i.mnemonic == "movss" and "0x10e8" in i.op_str)
        base_reg = store.reg_name(store.operands[0].mem.base)
        stop = main_base + store.address + store.size
        for _ in range(64):
            x = f32(rnd.uniform(0, 127 * 1.4143 * 1.7))
            v = f32(rnd.uniform(-10, 10))
            g = f32(rnd.choice([1.0, rnd.uniform(0.01, 1.0)]))
            mu.mem_write(cave_base, struct.pack("<f", g))
            mu.reg_write(U.UC_X86_REG_XMM0, struct.unpack("<I", struct.pack("<f", x))[0])
            mu.reg_write(U.UC_X86_REG_XMM6, struct.unpack("<I", struct.pack("<f", v))[0])
            mu.reg_write(getattr(U, "UC_X86_REG_" + base_reg.upper()), OBJ)
            mu.reg_write(U.UC_X86_REG_RSP, 0x7FF000000000 - 0x1000)
            mu.emu_start(main_base + site, stop, count=16)
            got = struct.unpack("<f", mu.mem_read(OBJ + 0x10E8, 4))[0]
            c = struct.unpack_from("<f", img, STICK)[0]
            want = f32(f32(f32(x * c) * g) + v)
            runs += 1
            if struct.pack("<f", got) != struct.pack("<f", want):
                problems.append("main+%X: stored %r, want %r (x %r, v %r, gain %r)"
                                % (site, got, want, x, v, g))
                break
    print("4. emulation: %d runs over the 3 sites" % runs)

    # 5. the motion itself, stick held, with what the DLL left
    a = f32(f32(127.0 * struct.unpack_from("<f", img, 0x678318)[0]) * struct.unpack_from("<f", img, STICK)[0])
    stock_k = struct.unpack_from("<f", img, 0x7A81BC)[0]
    by = {r["state"]: r for r in rows}

    def run(fps, fast, g, seconds=2.0):
        ticks = int(round(seconds * fps))
        v, pos, out = 0.0, 0.0, []
        for _ in range(ticks):
            v = f32(f32(v * fast) + f32(a * g))
            pos += v
            out.append(pos)
        return out

    stock = run(30, stock_k, 1.0)
    for name, fps in (("60", 60), ("120", 120)):
        ts = f32(float(by[name]["ts"]))
        fast = f32(float(by[name]["fast"]))
        g = f32(float(by[name]["gain"]))
        if args.broken == "gain":
            g = 1.0
        elif args.broken == "square":
            g = f32(ts * ts)
        got = run(fps, fast, g)
        n = fps // 30
        worst = max(abs(got[(j + 1) * n - 1] - stock[j]) for j in range(len(stock))) / stock[-1]
        speed = (got[-1] - got[-1 - fps // 2]) * 2
        want = (stock[-1] - stock[-16]) * 2
        print("5. %s fps: distance within %.3f%% of stock's; settled speed %.1f/s (stock %.1f/s)"
              % (name, 100 * worst, speed, want))
        if worst > 0.01:
            problems.append("%s fps: distance off by %.1f%% of stock's" % (name, 100 * worst))
        if abs(speed - want) > 0.005 * want:
            problems.append("%s fps: settled speed %.1f/s, stock %.1f/s" % (name, speed, want))
    unfixed = run(120, f32(float(by["120"]["fast"])), 1.0)
    print("   unfixed 120 fps for scale: settled %.1f/s, %.1fx stock"
          % ((unfixed[-1] - unfixed[-61]) * 2, (unfixed[-1] - unfixed[-61]) * 2 / ((stock[-1] - stock[-16]) * 2)))

    for p in problems[:20]:
        print("   PROBLEM " + p)
    print("\n%s" % ("FAILED: %d problems" % len(problems) if problems else "stick drift verified"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
