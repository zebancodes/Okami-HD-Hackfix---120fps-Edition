#!/usr/bin/env python3
"""Verify the Rejuvenation watch (src/brush_watch_runtime.h) against the game.

1. The DLL self-test (OkamiBrushWatchSelfTest) maps main.dll without running
   it, checks every cited instruction, then plays uses of the brush through
   the watch by writing the brush object's fields the way the game does: no
   target, a capture that writes the mask empty, one that leaves it empty, none
   at all, a stroke beside the mask, too little ink, restored. Each verdict and
   image is checked.
2. The watch recomputes the game's evaluation itself (brushCover). Here the
   game's own code does it under Unicorn: the rasterizer (main+17ECC0) inks the
   points, the coverage check (main+17DC90) counts and divides. On random masks
   and points, edge values included (NaN, huge, negative, sizes of 0 and below,
   points off the canvas, flags cleared, mask bytes with other bits set), the
   ink must match byte for byte and the ratio bit for bit.

    .venv/Scripts/python tools/verify_brush_watch.py [--cases N]
    --break sar|need  changes the game's code under emulation; the run must fail
"""
import argparse
import ctypes
import hashlib
import math
import os
import random
import re
import shutil
import struct
import sys
import tempfile

import capstone
import pefile
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64
from unicorn import x86_const as U

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.dirname(HERE)
HDR = os.path.join(ROOT, "src", "brush_watch.h")
BASE = 0x180000000
STACK, MASKBUF = 0x10000000, 0x20000000
W, H = 256, 224


def header():
    text = open(HDR, encoding="utf-8").read()

    def c(name):
        return int(re.search(r"\b%s\s*=\s*(0x[0-9A-Fa-f]+|\d+)" % name, text).group(1), 0)

    ev = {}
    for m in re.finditer(r"//\s+(rasterizer|coverage check)\s+main\+([0-9A-F]+)", text):
        ev[m.group(1)] = int(m.group(2), 16)
    return dict(sha=re.search(r'BRUSH_WATCH_MAIN_SHA1 "([0-9a-f]+)"', text).group(1),
                points=c("kBrushPointsRva"), size=c("kBrushPointSize"), count=c("kBrushPointCountRva"),
                ratio=c("kBrushRatioRva"), bits=c("kBrushBitsRva"), map=c("kBrushMapRva"),
                rast=ev["rasterizer"], cover=ev["coverage check"])


def self_test(dll_path, main_path):
    work = tempfile.mkdtemp(prefix="okami_brush_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(dll_path, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiBrushWatchSelfTest
    fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
    rc = fn(main_path.encode("mbcs"), work.encode("mbcs"))
    print(open(os.path.join(work, "report.txt")).read().rstrip())
    cover = lib.OkamiBrushCover
    cover.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p,
                      ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_float)]
    cover.restype = ctypes.c_int
    return rc, cover


class Game:
    """main.dll mapped at its base; the rasterizer and the coverage check run as the game's."""

    def __init__(self, raw, h, broken):
        pe = pefile.PE(data=raw)
        img = bytearray(pe.get_memory_mapped_image())
        if broken == "sar":
            # the rasterizer's half-width: size >> 2 becomes size >> 1
            code = bytes(img[h["rast"]:h["rast"] + 0x120])
            at = code.find(bytes.fromhex("41C1F902"))  # sar r9d, 2
            assert at > 0, "no sar r9d, 2 in the rasterizer"
            img[h["rast"] + at + 3] = 1
        if broken == "need":
            img[0x675A50:0x675A58] = struct.pack("<d", 0.5)
        self.h = h
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        mu.mem_map(BASE, (len(img) + 0xFFF) & ~0xFFF)
        mu.mem_write(BASE, bytes(img))
        mu.mem_map(STACK, 0x10000)
        mu.mem_map(MASKBUF, 0x10000)
        self.ret = STACK + 0x100

    def call(self, rva, rcx=0):
        mu = self.mu
        rsp = STACK + 0x8000 - 8
        mu.mem_write(rsp, struct.pack("<Q", self.ret))
        mu.reg_write(U.UC_X86_REG_RSP, rsp)
        mu.reg_write(U.UC_X86_REG_RCX, rcx)
        mu.emu_start(BASE + rva, self.ret, count=50_000_000)

    def evaluate(self, mask, pts, n, ink_rva, masks_rva):
        mu, h = self.mu, self.h
        mu.mem_write(BASE + ink_rva, bytes(W * H))
        mu.mem_write(MASKBUF, mask)
        mu.mem_write(BASE + masks_rva, struct.pack("<Q", MASKBUF))  # mask 0
        mu.mem_write(BASE + h["points"], pts)
        mu.mem_write(BASE + h["count"], struct.pack("<I", n))
        mu.mem_write(BASE + h["bits"], struct.pack("<I", 0))
        mu.mem_write(BASE + h["map"], struct.pack("<H", 0x100))
        self.call(h["rast"])
        self.call(h["cover"], 0)
        ink = bytes(mu.mem_read(BASE + ink_rva, W * H))
        ratio = struct.unpack("<f", bytes(mu.mem_read(BASE + h["ratio"], 4)))[0]
        bits = struct.unpack("<I", bytes(mu.mem_read(BASE + h["bits"], 4)))[0]
        return ink, ratio, bits


def random_case(rng, h):
    mask = bytearray(W * H)
    for _ in range(rng.randrange(0, 4)):
        x0, y0 = rng.randrange(-20, W), rng.randrange(-20, H)
        x1, y1 = x0 + rng.randrange(1, 120), y0 + rng.randrange(1, 100)
        v = rng.choice([1, 1, 1, 3, 5, 7])
        for x in range(max(0, x0), min(W, x1)):
            for y in range(max(0, y0), min(H, y1)):
                mask[x * H + y] = v
    for _ in range(rng.randrange(0, 40)):  # bits other than 0: not mask
        mask[rng.randrange(W * H)] = rng.choice([2, 4, 6, 0x80])
    special = [float("nan"), float("inf"), -float("inf"), 3e9, -3e9, -1.0, -0.9, 0.0, 0.5, 1.9,
               511.9, 512.0, 447.9, 448.0, 1e-30]
    n = rng.choice([0, 1, 2, rng.randrange(1, 60), rng.randrange(1, 400), 0x600])
    pts = bytearray(n * h["size"])
    for i in range(n):
        r = pts[i * h["size"]:(i + 1) * h["size"]]
        r[0] = rng.choice([0, 1, 3, 3, 3, 0x81])
        x = rng.choice(special) if rng.random() < 0.05 else rng.uniform(-60, 580)
        y = rng.choice(special) if rng.random() < 0.05 else rng.uniform(-60, 510)
        s = rng.choice(special) if rng.random() < 0.05 else rng.choice([rng.uniform(-10, 140), 21.0,
                                                                         rng.uniform(0, 8)])
        struct.pack_into("<fff", r, 4, x, y, s)
        for k in range(16, h["size"]):
            r[k] = rng.randrange(256)
        pts[i * h["size"]:(i + 1) * h["size"]] = r
    return bytes(mask), bytes(pts), n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--cases", type=int, default=160)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--break", dest="broken", choices=("sar", "need"))
    args = ap.parse_args()
    h = header()
    main_path = os.path.join(GAME, "main.dll")
    raw = open(main_path, "rb").read()
    if hashlib.sha1(raw).hexdigest() != h["sha"]:
        sys.exit("main.dll is not the binary src/brush_watch.h was generated from")
    rc, cover = self_test(args.dll, main_path)
    problems = [] if rc == 0 else ["the DLL self-test failed"]
    text = open(HDR, encoding="utf-8").read()
    ink_rva = int(re.search(r"ink canvas\s+main\+([0-9A-F]+)", text).group(1), 16)
    # the table of mask pointers: the coverage check's lea that is not the ink canvas
    img = pefile.PE(data=raw).get_memory_mapped_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    leas = [i.address + i.size + int(i.op_str.split("0x")[-1].rstrip("]"), 16) - BASE
            for i in md.disasm(img[h["cover"]:h["cover"] + 0x40], BASE + h["cover"])
            if i.mnemonic == "lea" and "[rip + 0x" in i.op_str]
    masks = [a for a in leas if a != ink_rva]
    if len(masks) != 1 or ink_rva not in leas:
        sys.exit("the coverage check's loads are %r" % ["%X" % a for a in leas])
    masks_rva = masks[0]
    game = Game(raw, h, args.broken)
    rng = random.Random(args.seed)
    same_ink = same_ratio = restored = 0
    for k in range(args.cases):
        mask, pts, n = random_case(rng, h)
        try:
            g_ink, g_ratio, g_bits = game.evaluate(mask, pts, n, ink_rva, masks_rva)
        except UcError as e:
            problems.append("case %d: the game's code faulted: %s" % (k, e))
            continue
        w_ink = ctypes.create_string_buffer(W * H)
        counts = (ctypes.c_uint32 * 3)()
        w_ratio = ctypes.c_float()
        cover(mask, pts if pts else b"\0", n, w_ink, counts, ctypes.byref(w_ratio))
        ink_ok = w_ink.raw == g_ink
        ratio_ok = struct.pack("<f", w_ratio.value) == struct.pack("<f", g_ratio) or \
            (math.isnan(g_ratio) and math.isnan(w_ratio.value))
        bits_ok = (g_bits != 0) == (w_ratio.value >= 1.0)
        same_ink += ink_ok
        same_ratio += ratio_ok and bits_ok
        restored += g_bits != 0
        if not (ink_ok and ratio_ok and bits_ok):
            diff = sum(a != b for a, b in zip(w_ink.raw, g_ink))
            problems.append("case %d (%d points): ink %s (%d bytes differ), ratio game %r watch %r, "
                            "game restored %d" % (k, n, "same" if ink_ok else "DIFFERS", diff, g_ratio,
                                                  w_ratio.value, g_bits != 0))
    print("evaluation: %d cases against the game's rasterizer and coverage check: ink the same in %d,"
          " ratio and verdict the same in %d (%d restored)"
          % (args.cases, same_ink, same_ratio, restored))
    for p in problems[:20]:
        print("  FAIL " + p)
    print("FAILED (%d)" % len(problems) if problems else "brush watch verified")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
