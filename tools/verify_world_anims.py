#!/usr/bin/env python3
"""Verify the world animations (src/world_anims.h) against the game's code.

Four layers, none of which uses the generator's encoders as an oracle:

1. Bytes. The DLL's own installer (OkamiWorldAnimSelfTest, on a mapped
   main.dll) must produce the pool and the patched bytes that an independent
   relocation of the header gives. Its per-tick update must hold, for every
   fps / context / key / master / group combination, each group's mask = N-1,
   s = 1/N, each step slot at K*s, each wind slot at K*s^2 and each blend slot
   at 1 - (1 - K)^(1/N) (by float square roots, blend_ref), with N = fps over
   the stock context's rate while that group is on and 1 otherwise. The
   self-test also checks the in-game measurement's verdicts and every failed
   write.

2. Windows. Every relocated window runs under Unicorn, from random machine
   states and every tick residue, at N = 1, 2 and 4, against the ORIGINAL
   instructions with only the documented change applied:
     src    the step operand is multiplied by s for that one instruction;
     dst    the step is multiplied by s right after the instruction;
     pre    the destination (the step) is multiplied by s right before it;
     dstarg, argscale  the loaded step component, or the copied limit, is
            multiplied by s right after;
     root   the factor f > 0 left by the instruction becomes f^(1/N): one
            float square root per halving, rounded as sqrtss rounds;
     zfirst, zlast  the result is zeroed, and ufirst, ulast set to 1.0, except
            on the first (fc & mask == 0) or last ((fc + 1) & mask == 0) tick
            of each stock period;
     count  the counting instruction does not run on ticks with fc & mask;
     countlast  the multiply (or the rate's added change) does not run except
            on the last tick;
     scaledadd  the call of cVec::operator+= (emulated as flower_kernel does
            it: xyz added, w kept) adds s times its argument;
     floor1 at N > 1, the reloaded float the manifest names is raised to 1.0
            (maxss: NaN too) before the join's first instruction runs;
     gatefn the function returns at once on those ticks;
     gate0  the function returns eax = 0 at once on those ticks;
     count2 the counting instruction does not run on ticks with
            fc & ((N-1) << 1);
     notyet on ticks with fc & mask the test does not run and ZF, SF and OF
            are cleared ("above zero");
     smode  as count, and on the other ticks at N > 1 it subtracts the
            stock context's mode (1 or 2, both tried) in place of the real
            byte;
     imuln  eax (the quotient) is multiplied by N right after the div;
     mulstore  the dword the store wrote is multiplied by N right after it,
            every register as the original leaves it;
     immstore  a finite float encoded as `mov m32, imm32` is written as K*s;
            only the generator-proven-dead xmm temporary may differ;
     step   as dst: the speed as read is multiplied by s.
   Every retargeted call (callscale, callblend: the steer group's turn steps
   and the actor group's forward steps of the imps' kick) runs from its call
   instruction to its target's entry against the original call: the same
   registers, return address and memory, except the limit register (xmm3;
   xmm1 for 23A2E0 and 2DA410's distance) times s and, for 2DA570, its per-tick
   blend k made 1 - (1 - k)^(1/N) as float square roots give it (k outside
   (0, 1) and NaN left alone), with its other lanes kept.
   A counter whose flags something reads (a countdown's jns) also has ZF and
   SF cleared on a skipped tick, as F1's do: which ones is derived from the
   code (gen_integer_skips.flag_policy), not taken from the generator. The real
   mode byte is 1 at N > 1, as the patch pins it, and 1 or 2 at N = 1.
   Registers, flags (where live), XMM registers (except the proven-dead
   temporary), every byte of game memory written and the exit address must
   agree. At N = 1 the reference is the original code itself; the one
   difference allowed is a signalling NaN made quiet by the multiply by 1.0,
   which the original's own next arithmetic does too. Registers are random,
   except the base of a memory operand the reference reads or rewrites itself
   (floor1, src, scaledadd's arguments): a pointer, since Unicorn truncates
   some non-canonical addresses a CPU would fault on.

3. Trajectories of the real functions, tick after tick: objScroll's UV scroll
   (35D5B0), the talk head-bob (3043C0), both turn helpers (20E210, 20E290:
   the heading must be stock's at every stock tick) and one particle through the effect
   engine's shared step (1928F0 and slots 9-15, flower_kernel's cVec and the
   CRT's sinf/cosf emulated in Python), the original code at stock 30 against
   the patched image at N = 4 and 2, from every starting residue. The scroll
   must track stock at every stock-tick boundary (modulo its wrap); the
   head-bob's weight must, and its frame must until its first wrap, after
   which each loop may run short by the documented 0.75 stock tick. The
   turn steps' helpers run through a stub every tick (2DDF90 added to the
   heading, 2DA570's approach stored back) must track stock at every stock
   tick (check_steer says how closely). The
   particle's integer state (age, keyframe, flipbook, wobble phases) must be
   stock's exactly at every stock tick and it must die on stock's stock tick.
   Started on a stock period's first tick, its floats (position, velocity,
   scale, rotation, spin, turbulence) must be stock's at every stock tick to
   float rounding. Started anywhere else, it moves lead/N of a tick on its
   first rates before their first stock update, a one-time offset: each float
   must stay within one stock step of stock's plus one first step, at every
   stock tick of its life. One enemy piece (5CC3E0's second state, straight
   code from 5CCBEB: a pull toward a joint, position += velocity * speed,
   velocity += acceleration * speed, damping by 0.92, the actor group's
   zfirst, step, zlast and ulast): started on a period's first tick its
   position and velocity must be stock's at every stock tick to float
   rounding; started mid-period it takes its first velocity change with
   less than a tick's move, and the offset must stay under 1.5 first steps
   and settle to under half its early size.

4. The swing step's physics, as a model (not the game's code, which calls
   fifteen flower_kernel math imports): the recurrence 1BA350 runs -- gravity,
   wind push, x += v, a length constraint to the anchor, v = (x - x_old) * f --
   stock at 30, fixed and unfixed at 120 and 60, from 1 rad out, compared at
   the same real times. The fixed pendulum must stay within 0.08 rad of stock
   (check_swing says why it is not exact) and the unfixed one 3x further.

5. F6 in real time, the real instructions tick after tick: the stock game (30
   ticks a second with the mode byte at 2, or 60 with it at 1 in its 60 Hz
   menus) against the patched one at 120 and 60 with the byte at 1. The
   menus' repeat (13F670) must fire as often as stock in each context, every
   fire within a stock tick of stock's; the layout flipbook's hold (1B2AA7)
   30 times a second for both parity phases; the event camera's playhead
   (4769E3) must cover stock's distance in the same time; the HUD timer
   (407BAB) must run out after the same time. The flag group's screen fade and
   rumble last their stock time, and the memory-card screens' wait (1BECA0,
   fps / 2 ticks) its stock half second, within a stock tick.

    .venv/Scripts/python tools/verify_world_anims.py
    --break scale|root|gate|literal|mask2|smode|intn corrupts one installed
    artifact and must fail.
"""
import argparse
import csv
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
from capstone import x86_const as CX
import pefile
from unicorn import UcError
from unicorn import x86_const as U

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import verify_menu_transitions as vmt  # noqa: E402  (the emulator and state helpers)
import gen_integer_skips as gis  # noqa: E402  (F1's flag liveness, derived from the code)
import gen_tracer as tr  # noqa: E402

ROOT = os.path.dirname(HERE)
HDR = os.path.join(ROOT, "src", "world_anims.h")

BASE, POOL, OBJ, TRAP, PAGE = vmt.BASE, vmt.POOL, vmt.OBJ, vmt.TRAP, vmt.PAGE
FC = vmt.FC
FLOOR1 = {0x19525E: ("rbx", 0x19C)}   # the manifest's (base, disp) per floor1 site
KIND = {0: "lin", 1: "sq", 2: "src", 3: "dst", 4: "pre", 5: "root", 6: "gatefn",
        7: "count", 8: "gate0", 9: "dstarg", 10: "zfirst", 11: "zlast", 12: "ufirst",
        13: "ulast", 14: "countlast", 15: "floor1", 16: "scaledadd", 17: "argscale",
        18: "count2", 19: "notyet", 20: "smode", 21: "imuln", 22: "srcx", 23: "step",
        24: "callscale", 25: "callblend", 26: "mulflag", 27: "callgate", 28: "mulstore",
        29: "blend", 30: "blendr", 31: "srcblend", 32: "immstore", 33: "srcroot", 34: "notyetneg", 35: "notyetb", 36: "dstn"}
CALL_KINDS = ("callscale", "callblend", "callgate")
MODE = 0xB6AC45        # the real mode byte, pinned at 1 by the patch at 60 and 120
ZF, SF, OF, CF = 0x40, 0x80, 0x800, 0x1
f32, fbits = vmt.f32, vmt.fbits


def parse_header(path=HDR):
    text = open(path, encoding="utf-8").read()

    def const(name):
        return int(re.search(r"\b%s\s*=\s*(0x[0-9a-fA-F]+|\d+)" % name, text).group(1), 0)

    def block(name):
        return re.search(r"\b%s\[\]\s*=\s*\{(.*?)\n\};" % name, text, re.S).group(1)

    def raw(name):
        return bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})\b", block(name)))

    def rows(name):
        return [tuple(int(v.strip(), 0) for v in r.split(",") if v.strip())
                for r in re.findall(r"\{([^{}]+)\}", block(name))]

    lit_orig = [bytes(int(x, 16) for x in re.findall(r"0x([0-9A-F]{2})", r))
                for r in re.findall(r"\{\{([^{}]+)\}\}", block("kWorldLiteralOrig"))]
    names = re.findall(r'"(\w+)"', re.search(r"kWorldGroupName\[\]\s*=\s*\{(.*?)\};",
                                               text).group(1))
    return dict(sha=re.search(r'WORLD_ANIMS_MAIN_SHA1\s+"([0-9a-f]+)"', text).group(1),
                names=names, intn=const("kWorldIntNOffset"),
                stride=const("kWorldGroupStride"), zero=const("kWorldZeroOffset"),
                code_off=const("kWorldCodeOffset"), pool_size=const("kWorldPoolSize"),
                groups=const("kWorldGroups"),
                code=raw("kWorldCode"), orig=raw("kWorldOrig"), lit_orig=lit_orig,
                fixups=rows("kWorldFixups"), windows=rows("kWorldWindows"),
                sites=rows("kWorldSites"), literals=rows("kWorldLiterals"),
                calls=rows("kWorldCalls") if "kWorldCalls[]" in text else [],
                call_ops=raw("kWorldCallOps") if "kWorldCallOps[]" in text else None)


def call_ops(hdr):
    """each call's opcode as shipped (E8 a call, E9 a tail jump), in kWorldCalls' order"""
    ops = hdr.get("call_ops")
    if ops is None:
        return bytes([0xE8]) * len(hdr["calls"])
    if len(ops) != len(hdr["calls"]):
        raise RuntimeError("world_anims.h: kWorldCallOps and kWorldCalls differ in length")
    return ops


def relocated_pool(hdr, main_base, pool_base):
    pool = bytearray(hdr["pool_size"])
    co = hdr["code_off"]
    pool[co:co + len(hdr["code"])] = hdr["code"]
    for field, nxt, target in hdr["fixups"]:
        if nxt == 0:
            struct.pack_into("<Q", pool, field, main_base + target)
        else:
            rel = main_base + target - (pool_base + nxt)
            assert -2 ** 31 <= rel < 2 ** 31
            struct.pack_into("<i", pool, field, rel)
    return pool


def patched_bytes(hdr, main_base, pool_base):
    out = []
    for rva, stub, _o, n in hdr["windows"]:
        rel = pool_base + stub - (main_base + rva + 5)
        out.append((rva, b"\xE9" + struct.pack("<i", rel) + b"\x90" * (n - 5)))
    for (rva, _c, slot, _k, _g), orig in zip(hdr["literals"], hdr["lit_orig"]):
        rel = pool_base + slot - (main_base + rva + 8)
        out.append((rva, orig[:4] + struct.pack("<i", rel)))
    for (rva, stub, _target), op in zip(hdr["calls"], call_ops(hdr)):
        rel = pool_base + stub - (main_base + rva + 5)
        out.append((rva, bytes([op]) + struct.pack("<i", rel)))
    return out


def want_n(fps, mode, master, group_on, muted, shadow, hook, complete, name="", real=1):
    """N as the runtime must set it. The mode group (F6) runs the port's "step x
    mode" sites at fps / 60 while the real mode byte reads 1, with or without a
    stock context; every other group at fps over the stock context's rate."""
    if name in ("mode", "flag"):
        if not (master and group_on and not muted and hook and complete and fps != 30):
            return 1
        return fps // 60 if real == 1 else 1
    if not (master and group_on and not muted and shadow and hook and complete and fps != 30
            and mode in (1, 2)):
        return 1
    return fps // (60 if mode == 1 else 30)


def slot_value(img, const_rva, kind, n):
    k = struct.unpack_from("<f", img, const_rva)[0]
    if n == 1:
        return k
    if kind == 29:      # blend: 1 - (1 - k)^(1/N), the root chain's float steps
        return blend_ref(f32(k), n)
    s = f32(1.0 / n)
    return f32(k * s) if kind == 0 else f32(f32(k * s) * s)


def check_modes(path, hdr, img, broken=None):
    problems = []
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        fps, mode, real, master, groups, muted, shadow, hook, complete = (
            int(r[k]) for k in ("fps", "mode", "real", "master", "groups", "muted", "shadow",
                                "hook", "complete"))
        ns = []
        for g in range(hdr["groups"]):
            name = hdr["names"][g]
            n = want_n(fps, mode, master, groups >> g & 1, muted, shadow, hook, complete, name,
                       real)
            ns.append(n)
            smode = mode if name == "repeat" and n > 1 else 0
            got = (int(r["mask%d" % g]), float(r["scale%d" % g]), int(r["mask2_%d" % g]),
                   int(r["smode%d" % g]), int(r["intn%d" % g]))
            if got != (n - 1, f32(1.0 / n), (n - 1) << 1, smode, n):
                problems.append("mode row %s group %s: mask, s, mask2, smode, N %s, want N=%d"
                                " smode %d" % ([fps, mode, real, master, groups, muted, shadow,
                                                hook, complete], name, got, n, smode))
        for rva, const, _slot, kind, g in hdr["literals"]:
            # --break literal: expect K*s where the family wants K*s^2
            want = slot_value(img, const, 0 if broken == "literal" else kind, ns[g])
            got = f32(float(r["slot%X" % rva]))
            if fbits(got) != fbits(want):
                problems.append("slot %X at N=%d is %r, want %r" % (rva, ns[g], got, want))
    return problems, len(rows)


def pool_data(hdr, img, n, broken=None, smode=2):
    """The pool at N for every group (as the runtime leaves it); smode is the
    stock context's mode the repeat group holds at N > 1."""
    pool = relocated_pool(hdr, BASE, POOL)
    s = f32(1.0 / n)
    for g in range(hdr["groups"]):
        pool[hdr["stride"] * g] = (n - 1) if broken != "gate" else 0
        pool[hdr["stride"] * g + 1] = ((n - 1) << 1) if broken != "mask2" else 0
        sm = smode if n > 1 and hdr["names"][g] == "repeat" else 0
        pool[hdr["stride"] * g + 2] = (3 - sm if sm and broken == "smode" else sm)
        struct.pack_into("<I", pool, hdr["intn"] + 4 * g, n if broken != "intn" else 1)
        struct.pack_into("<f", pool, hdr["stride"] * g + 4, s if broken != "scale" else 1.0)
    struct.pack_into("<f", pool, hdr["zero"], 0.0 if broken != "root" else 1e30)
    struct.pack_into("<f", pool, hdr["zero"] + 4, 1.0)
    for rva, const, slot, kind, _g in hdr["literals"]:
        v = slot_value(img, const, kind, n)
        struct.pack_into("<f", pool, slot, v)
    return pool


def root_ref(v, n):
    """sqrtss once per halving, each rounded to float, only for v > 0."""
    if not v > 0:
        return v
    for _ in range({1: 0, 2: 1, 4: 2}[n]):
        v = f32(math.sqrt(v))
    return v


def quiet_lanes(v):
    """A 128-bit XMM value with every signalling-NaN lane made quiet. A stub
    that multiplies a loaded step by s = 1.0 quiets a signalling NaN one
    instruction before the original's own arithmetic would: the same value from
    then on, and never in game data."""
    out = 0
    for k in range(4):
        lane = (v >> (32 * k)) & 0xFFFFFFFF
        if (lane & 0x7F800000) == 0x7F800000 and lane & 0x7FFFFF and not lane & 0x400000:
            lane |= 0x400000
        out |= lane << (32 * k)
    return out


def vmt_hex(v):
    """A snapshot value for a problem line: an XMM register's low lane as a
    float and its bits, anything else in hex."""
    if isinstance(v, int) and v >= 1 << 32:
        lo = v & 0xFFFFFFFF
        return "%r (%08X)" % (struct.unpack("<f", struct.pack("<I", lo))[0], lo)
    return "%X" % v if isinstance(v, int) else repr(v)


def snapshot(emu, skip_xmm, skip_flags):
    snap = vmt.snapshot(emu, skip_xmm, skip_flags)
    return {k: quiet_lanes(v) if k.startswith("xmm") else v for k, v in snap.items()}


def read_byte(emu, addr):
    try:
        return bytes(emu.mu.mem_read(addr, 1))
    except UcError:
        return None


def pe_import_names():
    import pefile as _pe
    pe = _pe.PE(os.path.join(GAME, "main.dll"), fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    return {imp.address - base: imp.name.decode()
            for entry in pe.DIRECTORY_ENTRY_IMPORT for imp in entry.imports if imp.name}


def check_windows(img, patched_img, pool_for, hdr, rnd, states, only_window=None):
    selected_windows = ({only_window} if isinstance(only_window, int) else
                        set(only_window) if only_window is not None else None)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    pe_imports = pe_import_names()
    problems, runs = [], 0
    sites_by_window = {}
    for site, kind, _g, win, temp, _counter, _probe, _role in hdr["sites"]:
        if KIND[kind] not in CALL_KINDS:     # a call's `window` indexes the calls
            sites_by_window.setdefault(win, []).append((site, kind, temp))
    # a skipped counter whose flags something reads (a countdown's jns) leaves
    # ZF and SF clear, "not finished", as F1's do: which ones, from the code
    dec = tr.Decoder(img, None)
    synth = set()
    for site, kind, _g, _w, _t, _c, _p, _r in hdr["sites"]:
        if KIND[kind] == "count":
            ins = dec.run(site, site)[0]
            if gis.flag_policy(dec, ins, -1, cmov=True)[0] == 1:
                synth.add(site)
    for wi, (lo, _stub, _o, n_bytes) in enumerate(hdr["windows"]):
        hi = lo + n_bytes
        insns = {i.address: i for i in md.disasm(bytes(img[lo:hi]), lo)}
        sites = sites_by_window[wi]
        skip_xmm = {t for _s, k, t in sites if KIND[k] in ("src", "floor1", "blendr",
                                                           "srcblend", "srcroot", "immstore")}
        # imuln: the div leaves the flags undefined and the stub's imul sets
        # them; the generator proved them dead after it
        skip_flags = any(KIND[k] in ("gatefn", "gate0", "root", "blendr", "floor1", "imuln",
                                     "mulflag", "mulstore", "srcblend", "srcroot")
                         for _s, k, _t in sites)
        # A lone count whose flags have no reader may leave different flags at
        # this artificial window boundary. The generator proves them dead.
        if len(sites) == 1 and KIND[sites[0][1]] == "count":
            ci = dec.run(sites[0][0], sites[0][0])[0]
            skip_flags |= gis.flag_policy(dec, ci, -1, cmov=True)[0] == 0
        calls = any(KIND[k] == "scaledadd" for _s, k, _t in sites)
        if calls:
            # the call it replaces leaves xmm0-5 and the flags undefined (x64 ABI)
            skip_xmm |= {0, 1, 2, 3, 4, 5}
            skip_flags = True
        pools = {}
        for n in (1, 2, 4):
            s = f32(1.0 / n)
            for k in range(states):
                # the repeat group's stock mode at N > 1: 2 (play) or 1 (a 60 Hz menu)
                smode = 1 + (k & 1)
                if (n, smode) not in pools:
                    pools[n, smode] = pool_for(n, smode)
                pool = pools[n, smode]
                # the real mode byte: pinned at 1 at N > 1, either at N = 1
                real = 1 if n > 1 else 1 + (k >> 1 & 1)
                st = vmt.random_state(rnd)
                if any(KIND[kk] == "imuln" for _s, kk, _t in sites):
                    # the game zeroes edx before each of these divs; a random
                    # one would overflow the quotient (#DE) in both runs alike
                    st["rdx"] = 0
                # roots need a positive factor now and then, not only noise
                if any(KIND[kk] == "root" for _s, kk, _t in sites) and k % 2:
                    st["xmm"][0] = (st["xmm"][0] & ~0xFFFFFFFF) | fbits(rnd.uniform(0.01, 1.2))
                # a compare srcx's value near its limit now and then (random
                # floats would almost never fall between s x limit and limit)
                for fs, fk, _t in sites:
                    ci = insns[fs]
                    if KIND[fk] == "srcx" and ci.mnemonic in ("comiss", "ucomiss") and k % 2:
                        lim = 16.0
                        cop = ci.operands[1]
                        if cop.type == CX.X86_OP_MEM and cop.mem.base == CX.X86_REG_RIP:
                            lim = struct.unpack_from("<f", img, fs + ci.size + cop.mem.disp)[0]
                        x = int(ci.reg_name(ci.operands[0].reg)[3:])
                        st["xmm"][x] = (st["xmm"][x] & ~0xFFFFFFFF) | \
                            fbits(rnd.uniform(0.0, 2 * abs(lim)))
                # Exercise both multiply factors and division denominators,
                # including guards, rather than only random float noise.
                for fs, fk, _t in sites:
                    sop = insns[fs].operands[-1]
                    if KIND[fk] == "srcblend" and k % 2 and sop.type == CX.X86_OP_REG:
                        x = int(insns[fs].reg_name(sop.reg)[3:])
                        value = (2.0, 3.0, 10.0, 100.0)[(k // 2) % 4] \
                            if insns[fs].mnemonic == "divss" else rnd.uniform(0.0, 1.0)
                        st["xmm"][x] = (st["xmm"][x] & ~0xFFFFFFFF) | fbits(value)
                # a blendr's factor in (0, 1) now and then: its operands small
                for fs, fk, _t in sites:
                    if KIND[fk] == "blendr" and k % 2:
                        for op in insns[fs].operands:
                            if op.type == CX.X86_OP_REG:
                                x = int(insns[fs].reg_name(op.reg)[3:])
                                st["xmm"][x] = (st["xmm"][x] & ~0xFFFFFFFF) | \
                                    fbits(rnd.uniform(0.0, 0.5))
                # a floor1 site dereferences its base, and the reference scales a
                # memory src operand in place: a pointer, as in the game.
                # (Unicorn faults on some non-canonical addresses and truncates
                # others, where a CPU always faults: the emulated read would
                # miss the value the reference scaled.)
                for fs, fk, _t in sites:
                    if KIND[fk] == "floor1":
                        st[FLOOR1[fs][0]] = (0x200000000 + rnd.randrange(0, 1 << 32)) & ~7
                    if KIND[fk] in ("mulstore", "immstore"):
                        # The reference rewrites what the store wrote: use a
                        # canonical pointer, as in the game, so Unicorn cannot
                        # truncate the address.
                        st[insns[fs].reg_name(insns[fs].operands[0].mem.base)] = \
                            (0x200000000 + rnd.randrange(0, 1 << 32)) & ~7
                    if KIND[fk] in ("src", "srcx", "srcblend") and \
                            insns[fs].operands[1].type == CX.X86_OP_MEM:
                        m = insns[fs].operands[1].mem
                        for r in (m.base, m.index):
                            if r and r != CX.X86_REG_RIP:
                                st[insns[fs].reg_name(r)] = \
                                    (0x200000000 + rnd.randrange(0, 1 << 28)) & ~7
                    if KIND[fk] == "scaledadd":
                        for r in ("rcx", "rdx"):
                            st[r] = (0x200000000 + rnd.randrange(0, 1 << 32)) & ~15
                fc = rnd.getrandbits(20) * 4 + (k % 4)
                if selected_windows is not None and lo not in selected_windows:
                    continue
                stock = (fc & (n - 1)) == 0
                results = []
                for variant in ("orig", "patched"):
                    emu = vmt.Emu(img if variant == "orig" else patched_img,
                                  pool if variant == "patched" else None, seed=st["mem_seed"])
                    emu.pre = ChainedHooks()
                    if calls:
                        bind_imports(emu, pe_imports, add_scale=s if variant == "orig" else None)
                    vmt.load_state(emu, st, fc)
                    emu.mu.mem_write(BASE + MODE, bytes([real]))
                    if variant == "orig":
                        for site, kind, _t in sites:
                            ins = insns[site]
                            kname = KIND[kind]
                            # srcx: (xmmD / s op src) * s is exactly xmmD op s*src,
                            # the same reference as src's scaled copy
                            if kname in ("src", "srcx") and n > 1:
                                op = ins.operands[1]
                                if op.type == CX.X86_OP_MEM:
                                    def pre(e, ins=ins, op=op, key=site):
                                        ea = vmt.mem_ea(e, ins, op)
                                        e.map_page(ea & ~(PAGE - 1))
                                        double = ins.mnemonic in ("addsd", "subsd")
                                        width, fmt = (8, "<d") if double else (4, "<f")
                                        if not hasattr(e, "_source_saved"):
                                            e._source_saved = {}
                                        old = bytes(e.mu.mem_read(ea, width))
                                        e._source_saved[key] = (ea, old)
                                        v = struct.unpack(fmt, old)[0]
                                        scaled = v * s if double else f32(v * s)
                                        e.mu.mem_write(ea, struct.pack(fmt, scaled))

                                    def post(e, key=site):
                                        saved = getattr(e, "_source_saved", {}).pop(key, None)
                                        if saved is None:
                                            return
                                        ea, old = saved
                                        e.mu.mem_write(ea, old)
                                        for b in range(len(old)):
                                            e.written.discard(ea + b)
                                else:
                                    src = int(ins.reg_name(op.reg)[3:])

                                    def pre(e, src=src, key=site, double=ins.mnemonic in ("addsd", "subsd")):
                                        if not hasattr(e, "_source_saved"):
                                            e._source_saved = {}
                                        e._source_saved[key] = e.mu.reg_read(vmt.XMMS[src])
                                        if double:
                                            old = e.mu.reg_read(vmt.XMMS[src])
                                            value = struct.unpack("<d", (old & ((1 << 64) - 1)).to_bytes(8, "little"))[0]
                                            bits = int.from_bytes(struct.pack("<d", value * s), "little")
                                            e.mu.reg_write(vmt.XMMS[src], (old & ~((1 << 64) - 1)) | bits)
                                        else:
                                            e.set_xmm_low(src, f32(e.xmm_low(src) * s))

                                    def post(e, src=src, key=site):
                                        saved = getattr(e, "_source_saved", {}).pop(key, None)
                                        if saved is not None:
                                            e.mu.reg_write(vmt.XMMS[src], saved)
                                emu.pre[site] = pre
                                emu.pre[site + ins.size] = post
                            elif kname in ("srcblend", "srcroot") and n > 1:
                                op = ins.operands[1]
                                if op.type == CX.X86_OP_MEM:
                                    def pre(e, ins=ins, op=op, n=n, kind=kname, key=site):
                                        ea = vmt.mem_ea(e, ins, op)
                                        e.map_page(ea & ~(PAGE - 1))
                                        if not hasattr(e, "_source_saved"):
                                            e._source_saved = {}
                                        old = bytes(e.mu.mem_read(ea, 4))
                                        e._source_saved[key] = (ea, old)
                                        v = struct.unpack("<f", old)[0]
                                        scaled = (divisor_blend_ref(v, n) if ins.mnemonic == "divss" else
                                                  blend_ref(v, n)) if kind == "srcblend" else root_ref(v, n)
                                        e.mu.mem_write(ea, struct.pack("<f", scaled))

                                    def post(e, key=site):
                                        saved = getattr(e, "_source_saved", {}).pop(key, None)
                                        if saved is None:
                                            return
                                        ea, old = saved
                                        e.mu.mem_write(ea, old)
                                        for b in range(4):
                                            e.written.discard(ea + b)
                                else:
                                    src = int(ins.reg_name(op.reg)[3:])

                                    def pre(e, src=src, n=n, kind=kname, divide=ins.mnemonic == "divss", key=site):
                                        if not hasattr(e, "_source_saved"):
                                            e._source_saved = {}
                                        e._source_saved[key] = e.mu.reg_read(vmt.XMMS[src])
                                        value = e.xmm_low(src)
                                        scaled = (divisor_blend_ref(value, n) if divide else
                                                  blend_ref(value, n)) if kind == "srcblend" else root_ref(value, n)
                                        e.set_xmm_low(src, scaled)

                                    def post(e, src=src, key=site):
                                        saved = getattr(e, "_source_saved", {}).pop(key, None)
                                        if saved is not None:
                                            e.mu.reg_write(vmt.XMMS[src], saved)
                                emu.pre[site] = pre
                                emu.pre[site + ins.size] = post
                            elif kname in ("dst", "dstarg", "argscale", "step") and n > 1:
                                d = int(ins.reg_name(ins.operands[0].reg)[3:])

                                def post(e, d=d):
                                    e.set_xmm_low(d, f32(e.xmm_low(d) * s))
                                emu.pre[site + ins.size] = post
                            elif kname == "dstn" and n > 1:
                                d = int(ins.reg_name(ins.operands[0].reg)[3:])

                                def post(e, d=d):
                                    e.set_xmm_low(d, f32(e.xmm_low(d) / s))
                                emu.pre[site + ins.size] = post
                            elif kname in ("zfirst", "zlast", "ufirst", "ulast"):
                                keep = stock if kname.endswith("first") else \
                                    ((fc + 1) & (n - 1)) == 0
                                if not keep:
                                    d = int(ins.reg_name(ins.operands[0].reg)[3:])
                                    value = fbits(1.0) if kname[0] == "u" else 0

                                    def post(e, d=d, value=value):
                                        e.mu.reg_write(vmt.XMMS[d], value)
                                    emu.pre[site + ins.size] = post
                            elif kname == "floor1" and n > 1:
                                base, disp = FLOOR1[site]

                                def pre(e, base=base, disp=disp):
                                    ea = e.reg(base) + disp   # canonical: drawn so below
                                    e.map_page(ea & ~(PAGE - 1))
                                    e.map_page((ea + 3) & ~(PAGE - 1))
                                    v = struct.unpack("<f", e.mu.mem_read(ea, 4))[0]
                                    e.mu.mem_write(ea, struct.pack("<f", v if v > 1.0 else 1.0))
                                    # a store, as the stub's: host writes are not hooked
                                    e.written.update(range(ea, ea + 4))
                                emu.pre[site] = pre
                            elif kname == "countlast" and ((fc + 1) & (n - 1)) != 0:
                                def skip(e, ins=ins):
                                    e.set_reg("rip", BASE + ins.address + ins.size)
                                emu.pre[site] = skip
                            elif kname == "count" and not stock:
                                def skip(e, ins=ins, clear=(ZF | SF) if site in synth else 0):
                                    fl = e.mu.reg_read(U.UC_X86_REG_EFLAGS)
                                    e.mu.reg_write(U.UC_X86_REG_EFLAGS, fl & ~clear)
                                    e.set_reg("rip", BASE + ins.address + ins.size)
                                emu.pre[site] = skip
                            elif kname == "count2" and fc & ((n - 1) << 1):
                                def skip(e, ins=ins):
                                    e.set_reg("rip", BASE + ins.address + ins.size)
                                emu.pre[site] = skip
                            elif kname in ("notyet", "notyetneg", "notyetb") and not stock:
                                # Tests/cmp do not run. AND must still update
                                # its register, then only its branch flags are
                                # forced to the "not yet" path. The AND is done
                                # here and skipped, as a test is: a flags write
                                # in the hook after it is lost when that hook
                                # is the window's end (Unicorn's lazy flags).
                                if ins.mnemonic == "and" and (
                                        len(ins.operands) != 2 or
                                        ins.operands[0].type != CX.X86_OP_REG or
                                        ins.operands[1].type != CX.X86_OP_IMM):
                                    raise RuntimeError("notyet %X: and of a form the "
                                                       "reference does not model" % site)

                                def notyet(e, ins=ins, negative=kname == "notyetneg",
                                           below=kname == "notyetb"):
                                    fl = e.mu.reg_read(U.UC_X86_REG_EFLAGS)
                                    if ins.mnemonic == "and":
                                        r = ins.reg_name(ins.operands[0].reg)
                                        e.set_reg(r, e.reg(r) & ins.operands[1].imm)
                                        fl &= ~CF   # AND clears CF (and OF, below)
                                    e.mu.reg_write(U.UC_X86_REG_EFLAGS,
                                                   (fl & ~(ZF | SF | OF)) | (SF if negative else 0) |
                                                   (CF if below else 0))
                                    e.set_reg("rip", BASE + ins.address + ins.size)
                                emu.pre[site] = notyet
                            elif kname == "smode" and not stock:
                                def skip(e, ins=ins):
                                    e.set_reg("rip", BASE + ins.address + ins.size)
                                emu.pre[site] = skip
                            elif kname == "smode" and n > 1:
                                # subtracts the stock context's mode, not the real byte
                                def pre(e, smode=smode):
                                    e._mode = bytes(e.mu.mem_read(BASE + MODE, 1))
                                    e.mu.mem_write(BASE + MODE, bytes([smode]))

                                def post(e):
                                    e.mu.mem_write(BASE + MODE, e._mode)
                                emu.pre[site] = pre
                                emu.pre[site + ins.size] = post
                            elif kname == "imuln" and n > 1:
                                def post(e, n=n):
                                    e.set_reg("rax", (e.reg("rax") * n) & 0xFFFFFFFF)
                                emu.pre[site + ins.size] = post
                            elif kname == "mulflag" and n > 1:
                                r = vmt_reg64(ins.reg_name(ins.operands[0].reg))

                                def post(e, n=n, r=r):
                                    e.set_reg(r, (e.reg(r) * n) & 0xFFFFFFFF)
                                emu.pre[site + ins.size] = post
                            elif kname == "mulstore" and n > 1:
                                m = ins.operands[0].mem
                                base, disp = ins.reg_name(m.base), m.disp

                                def post(e, n=n, base=base, disp=disp):
                                    ea = (e.reg(base) + disp) & 0xFFFFFFFFFFFFFFFF
                                    v = struct.unpack("<I", e.mu.mem_read(ea, 4))[0]
                                    e.mu.mem_write(ea, struct.pack("<I", (v * n) & 0xFFFFFFFF))
                                    e.written.update(range(ea, ea + 4))
                                emu.pre[site + ins.size] = post
                            elif kname == "immstore" and n > 1:
                                op = ins.operands[0]
                                value = struct.unpack_from("<f", bytes(ins.bytes),
                                                           ins.imm_offset)[0]

                                def post(e, ins=ins, op=op, value=value, s=s):
                                    ea = vmt.mem_ea(e, ins, op)
                                    e.mu.mem_write(ea, struct.pack("<f", f32(value * s)))
                                    e.written.update(range(ea, ea + 4))
                                emu.pre[site + ins.size] = post
                            elif kname == "pre" and n > 1:
                                d = int(ins.reg_name(ins.operands[0].reg)[3:])

                                def pre(e, d=d):
                                    e.set_xmm_low(d, f32(e.xmm_low(d) * s))
                                emu.pre[site] = pre
                            elif kname == "root" and n > 1:
                                d = int(ins.reg_name(ins.operands[0].reg)[3:])

                                def post(e, d=d):
                                    e.set_xmm_low(d, root_ref(e.xmm_low(d), n))
                                emu.pre[site + ins.size] = post
                            elif kname == "blendr" and n > 1:
                                d = int(ins.reg_name(ins.operands[0].reg)[3:])

                                def post(e, d=d):
                                    e.set_xmm_low(d, blend_ref(e.xmm_low(d), n))
                                emu.pre[site + ins.size] = post
                            elif kname in ("gatefn", "gate0") and not stock:
                                def ret(e, zero=kname == "gate0"):
                                    rsp = e.reg("rsp")
                                    if zero:
                                        e.set_reg("rax", 0)
                                    e.set_reg("rip", struct.unpack("<Q", e.mu.mem_read(rsp, 8))[0])
                                    e.set_reg("rsp", rsp + 8)
                                emu.pre[site] = ret
                    emu.stop_outside = (BASE + lo, BASE + hi)
                    emu.pre = {BASE + a: f for a, f in emu.pre.items()}
                    try:
                        emu.mu.emu_start(BASE + lo, 0, count=500)
                    except UcError as e:
                        emu.exit = "fault %s" % e
                    snap = snapshot(emu, skip_xmm, skip_flags)
                    if "flags" in snap and any(site in synth for site, _kind, _temp in sites):
                        # Only ZF/SF can reach a countdown consumer. Other
                        # arithmetic flags are dead on every successor path.
                        snap["flags"] &= ZF | SF
                    if not stock and any(KIND[kind] in ("notyet", "notyetneg", "notyetb") and
                                         insns[site].mnemonic == "and"
                                         for site, kind, _temp in sites):
                        # The following branch reads ZF only. PF from the
                        # register-preserving AND is dead on both paths, and
                        # Unicorn differs on it at the window boundary.
                        if "flags" in snap:
                            snap["flags"] &= ZF | SF | OF
                    results.append((snap, emu))
                (a, ea), (b, eb) = results
                runs += 1
                if a != b:
                    diff = [key for key in a if a[key] != b.get(key)]
                    problems.append("window %X N=%d fc&mask=%d: %s differ (%s: %s, patched %s)" % (
                        lo, n, fc & (n - 1), ", ".join(diff[:6]), diff[0],
                        vmt_hex(a[diff[0]]), vmt_hex(b.get(diff[0]))))
                    continue
                wa, wb = vmt.game_writes(ea), vmt.game_writes(eb)
                if any(KIND[k] in ("gatefn", "gate0") for _s, k, _t in sites):
                    # an entry gate's push rax / pushfq land in the frame the
                    # prologue then allocates: below the entry rsp, above the
                    # final one, never read by the function before it writes it
                    entry_rsp = st["rsp"]
                    wb = {a for a in wb if a in wa or not (eb.reg("rsp") <= a < entry_rsp)}
                if wa != wb:
                    problems.append("window %X N=%d: written addresses differ" % (lo, n))
                    continue
                for addr in sorted(wa):
                    # a write that faulted (both runs fault alike) left nothing to read
                    va, vb = read_byte(ea, addr), read_byte(eb, addr)
                    if va != vb:
                        # Python's reference cVec::operator+= uses struct.pack
                        # for float32 rounding; SSE keeps a NaN operand's
                        # payload. Both results are NaN, but their payload
                        # bytes need not agree.
                        if calls and st["rcx"] <= addr < st["rcx"] + 12:
                            lane = st["rcx"] + (addr - st["rcx"]) // 4 * 4
                            aa = struct.unpack("<f", ea.mu.mem_read(lane, 4))[0]
                            bb = struct.unpack("<f", eb.mu.mem_read(lane, 4))[0]
                            if math.isnan(aa) and math.isnan(bb):
                                continue
                        problems.append("window %X N=%d state=%d fc=%X: memory %X differs "
                                        "(%s vs %s), rcx=%X rdx=%X, dst=%s vs %s, src=%s" %
                                        (lo, n, k, fc, addr, va.hex() if va else None,
                                         vb.hex() if vb else None, st["rcx"], st["rdx"],
                                         f4(ea, st["rcx"]), f4(eb, st["rcx"]),
                                         f4(ea, st["rdx"])))
                        break
    return problems, runs


# ---------------------------------------------------------------------------
# trajectories of the real functions
# ---------------------------------------------------------------------------

def image_for(img, hdr, n):
    """(image, pool) as the game runs them at N; the original at N = None."""
    if n is None:
        return bytearray(img), None
    im = bytearray(img)
    for rva, b in patched_bytes(hdr, BASE, POOL):
        im[rva:rva + len(b)] = b
    return im, pool_data(hdr, img, n)


def trap_fn(emu, rva, fn):
    """Replace main+rva by a Python function run at its entry, then return."""
    def hook(e):
        fn(e)
        rsp = e.reg("rsp")
        e.set_reg("rip", struct.unpack("<Q", e.mu.mem_read(rsp, 8))[0])
        e.set_reg("rsp", rsp + 8)
    emu.pre[BASE + rva] = hook


def zero_pages(emu, lo, size):
    for p in range(lo, lo + size, PAGE):
        emu.map_page(p)
        emu.mu.mem_write(p, b"\0" * PAGE)


def check_player_speed_cap(img, hdr, pool_for):
    """The three independently verified rows in 3B75B8 compose to
    min(E48 + 2*s, 3*s). Directed values around the cap keep a missing scaled
    immediate store (or a mistakenly unscaled compare) from hiding behind the
    individual-window checks."""
    player = hdr["names"].index("player")
    literal_kinds = {rva: (KIND[kind], group)
                     for rva, _const, _slot, kind, group in hdr["literals"]}
    site_kinds = {site: (KIND[kind], group)
                  for site, kind, group, *_rest in hdr["sites"]}
    want_sites = ((0x3B75C0, literal_kinds, "lin"),
                  (0x3B75C8, site_kinds, "srcx"),
                  (0x3B75D9, site_kinds, "immstore"))
    problems = []
    for site, table, kind in want_sites:
        if table.get(site) != (kind, player):
            problems.append("player speed cap site %X is not player %s" % (site, kind))
    if problems:
        return problems, 0

    patched = bytearray(img)
    for rva, b in patched_bytes(hdr, BASE, POOL):
        patched[rva:rva + len(b)] = b
    cases = (-1.0, 0.0, 0.125, 0.999, 1.0, 1.001, 2.999, 3.0, 4.0)
    runs = 0
    for n in (1, 2, 4):
        s = f32(1.0 / n)
        step, cap = f32(2.0 * s), f32(3.0 * s)
        pool = pool_for(n)
        for stock_value in cases:
            value = f32(stock_value * s)       # +E48 is already in current-rate units
            summed = f32(value + step)
            want = cap if summed > cap else summed
            emu = vmt.Emu(patched, pool)
            zero_pages(emu, OBJ, 0x2000)
            emu.set_reg("rdi", OBJ)
            emu.set_reg("rsp", vmt.STACK_TOP - 0x1000)
            emu.mu.mem_write(OBJ + 0xE48, struct.pack("<f", value))
            emu.stop_outside = (BASE + 0x3B75B8, BASE + 0x3B75E3)
            try:
                emu.mu.emu_start(BASE + 0x3B75B8, 0, count=200)
            except UcError as e:
                problems.append("player speed cap N=%d x=%r faulted: %s" %
                                (n, value, e))
                runs += 1
                continue
            got = emu.rf(OBJ + 0xE48)
            runs += 1
            if emu.exit != BASE + 0x3B75E3 or fbits(got) != fbits(want):
                problems.append("player speed cap N=%d x=%r: exit %s, got %r, want %r" %
                                (n, value, "%X" % emu.exit if isinstance(emu.exit, int)
                                 else repr(emu.exit), got, want))
    return problems, runs


SKY_CASES = [  # placement flags word (+A), U step byte (+14), V step byte (+15), materials
    (0x0000, 100, -37, 2),     # per material, speed 1, wrapped
    (0x0040, 127, 5, 1),       # speed 0.1
    (0x0080, -90, 64, 3),      # every material, no wrap
    (0x00C0, 33, -128, 2),     # both
]


def run_sky(img, hdr, n, residue, case, ticks):
    flags, du, dv, mats = case
    im, pool = image_for(img, hdr, n)
    emu = vmt.Emu(im, pool)
    zero_pages(emu, OBJ, 0x8000)
    O, D, M = OBJ, OBJ + 0x2000, OBJ + 0x3000
    emu.mu.mem_write(O + 0xED8, struct.pack("<Q", D))
    emu.mu.mem_write(D + 0xA, struct.pack("<H", flags))
    emu.mu.mem_write(D + 0x14, struct.pack("<bb", du, dv))
    emu.mu.mem_write(O + 0xD75, bytes([mats]))
    emu.mu.mem_write(O + 0xD48, struct.pack("<Q", M))
    for i in range(mats):
        m = M + 0x800 * i
        emu.mu.mem_write(m + 0x5F8, struct.pack("<Q", m + 0x800 if i + 1 < mats else 0))
        emu.wf(m + 0x60, 0.3 - 0.2 * i)
        emu.wf(m + 0x64, -0.7 + 0.1 * i)
    fc = 0x1000 + residue
    out = []
    for _ in range(ticks):
        emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
        emu.call(0x35D5B0, O)
        out.append(tuple(emu.rf(M + 0x800 * i + off) for i in range(mats) for off in (0x60, 0x64)))
        fc += 1
    return out


# ---------------------------------------------------------------------------
# F6: the real instructions, tick after tick, stock against patched in time
# ---------------------------------------------------------------------------

def f6_emu(img, hdr, n, smode, real):
    """An emulator on the original image (n None) or the patched one at N,
    with the real mode byte set."""
    if n is None:
        emu = vmt.Emu(bytearray(img), None)
    else:
        im = bytearray(img)
        for rva, b in patched_bytes(hdr, BASE, POOL):
            im[rva:rva + len(b)] = b
        emu = vmt.Emu(im, pool_data(hdr, img, n, None, smode))
    emu.mu.mem_write(BASE + MODE, bytes([real]))
    zero_pages(emu, OBJ, 0x4000)
    return emu


def f6_run(emu, lo, hi, fc):
    """Run main+[lo, hi) from lo with the frame counter at fc; the exit rva."""
    emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
    emu.set_reg("rsp", vmt.STACK_TOP - 0x1000)
    emu.stop_outside = (BASE + lo, BASE + hi)
    emu.exit = None
    emu.mu.emu_start(BASE + lo, 0, count=400)
    return emu.exit - BASE


def repeat_fires(img, hdr, n, smode, real, ticks, fc0):
    """hxNavigationController's first counter (13F670-13F68B) held down for
    `ticks` ticks: the ticks it fired on (13F6C4, where the game reloads 4)."""
    emu = f6_emu(img, hdr, n, smode, real)
    r13 = OBJ + 0x200
    emu.set_reg("r13", r13)
    emu.set_reg("rbp", OBJ + 0x1000)
    emu.mu.mem_write(r13 - 0x79, bytes([4]))
    fires = []
    for t in range(ticks):
        out = f6_run(emu, 0x13F670, 0x13F68B, fc0 + t)
        if out == 0x13F6C4:
            emu.mu.mem_write(r13 - 0x79, bytes([4]))
            fires.append(t)
        elif out != 0x13F68B:
            raise RuntimeError("repeat left at %X" % out)
    return fires


def flip_holds(img, hdr, n, real, ticks, fc0, phase):
    """The layout flipbook's hold step (1B2AA7-1B2ACA): holds counted."""
    emu = f6_emu(img, hdr, n, 2, real)
    rcx, r10 = OBJ + 0x100, OBJ + 0x400
    emu.set_reg("rcx", rcx)
    emu.set_reg("r10", r10)
    emu.mu.mem_write(rcx + 0x2F, bytes([phase]))
    holds = 0
    for t in range(ticks):
        emu.mu.mem_write(r10 + 0x86, b"\0")
        f6_run(emu, 0x1B2AA7, 0x1B2ACA, fc0 + t)
        holds += emu.mu.mem_read(r10 + 0x86, 1)[0]
    return holds


def playhead_after(img, hdr, n, real, ticks, fc0, speed):
    """The event camera's playhead step (4769E3-476A26), `ticks` ticks."""
    emu = f6_emu(img, hdr, n, 2, real)
    rbx, path = OBJ + 0x100, OBJ + 0x800
    emu.set_reg("rbx", rbx)
    emu.wf(rbx + 0x2D4, speed)
    emu.mu.mem_write(rbx + 0x340, struct.pack("<Q", path))
    emu.mu.mem_write(path + 4, struct.pack("<H", 60000))
    for t in range(ticks):
        f6_run(emu, 0x4769E3, 0x476A26, fc0 + t)
    return emu.rf(rbx + 0x348)


def timer_ticks(img, hdr, n, real, start, fc0, limit):
    """The HUD timer's countdown (407BAB-407BC1) from `start`: the tick +89
    is set on (it went below 0)."""
    emu = f6_emu(img, hdr, n, 2, real)
    rcx = OBJ + 0x100
    emu.set_reg("rcx", rcx)
    emu.mu.mem_write(rcx + 0x84, struct.pack("<i", start))
    for t in range(limit):
        f6_run(emu, 0x407BAB, 0x407BC1, fc0 + t)
        if emu.mu.mem_read(rcx + 0x89, 1)[0]:
            return t
    return None


def check_f6(img, hdr):
    """Real time, the stock game against the patched one: the stock game runs
    30 ticks a second with the mode byte at 2 in play, 60 with it at 1 in its
    60 Hz menus; the patch runs 120 (or 60) with it at 1."""
    problems, runs, report = [], 0, []
    # the repeat: fires a second in each context, and when
    for ctx, stock_mode, stock_hz in (("play", 2, 30), ("60 Hz menu", 1, 60)):
        secs = 3
        stock = [t / stock_hz for t in repeat_fires(img, hdr, None, 0, stock_mode,
                                                    secs * stock_hz, 0x4000)]
        for fps in (120, 60):
            n = fps // stock_hz
            if n < 1:
                continue
            for residue in range(4):
                fires = [t / fps for t in repeat_fires(img, hdr, n if n > 1 else None,
                                                       stock_mode, 1 if n > 1 else stock_mode,
                                                       secs * fps, 0x4000 + residue)]
                runs += 1
                if len(fires) != len(stock) or any(abs(a - b) > 1.0 / stock_hz
                                                   for a, b in zip(fires, stock)):
                    problems.append("repeat in %s at %d fps residue %d: %d fires, stock %d"
                                    % (ctx, fps, residue, len(fires), len(stock)))
        unfixed = len(repeat_fires(img, hdr, None, 0, 1, secs * 120, 0x4000))
        report.append("repeat in %s: %.1f a second at %d Hz stock, the same at 120 and 60 "
                      "fixed (every fire within a stock tick of stock's); unfixed 120: %.1f"
                      % (ctx, len(stock) / secs, stock_hz, unfixed / secs))
    # the flipbook: holds a second, both parity phases
    for phase in (0, 1):
        stock30 = flip_holds(img, hdr, None, 2, 30, 0x4000, phase)
        stock60 = flip_holds(img, hdr, None, 1, 60, 0x4000, phase)
        fixed = flip_holds(img, hdr, 2, 1, 120, 0x4000, phase)
        at60 = flip_holds(img, hdr, 1, 1, 60, 0x4000, phase)
        unfixed = flip_holds(img, hdr, None, 1, 120, 0x4000, phase)
        runs += 5
        if not (stock30 == stock60 == fixed == at60 == 30) or unfixed != 60:
            problems.append("flipbook phase %d: holds a second %d at 30, %d at 60, %d fixed "
                            "120, %d fixed 60, %d unfixed 120" % (phase, stock30, stock60,
                                                                  fixed, at60, unfixed))
    report.append("layout flipbook: 30 holds a second at 30, 60 and fixed 120, both phases "
                  "(unfixed 120: 60)")
    # the event camera's playhead over 2 s
    speed = 1.5
    stock = playhead_after(img, hdr, None, 2, 60, 0x4000, speed)
    for fps, n in ((120, 2), (60, 1)):
        got = playhead_after(img, hdr, n if n > 1 else None, 1, 2 * fps, 0x4000, speed)
        runs += 1
        if abs(got - stock) > 1e-3 * stock:
            problems.append("playhead after 2 s at %d fps: %r, stock %r" % (fps, got, stock))
    unfixed = playhead_after(img, hdr, None, 1, 240, 0x4000, speed)
    report.append("event camera playhead after 2 s: %.2f at stock 30, the same at 120 and 60 "
                  "fixed; unfixed 120: %.2f" % (stock, unfixed))
    # the HUD timer: a 10 s countdown (600 in 1/60 s)
    stock = timer_ticks(img, hdr, None, 2, 600, 0x4000, 1000)
    for residue in range(2):
        got = timer_ticks(img, hdr, 2, 1, 600, 0x4000 + residue, 3000)
        runs += 1
        if got is None or abs(got / 120 - stock / 30) > 1.0 / 30:
            problems.append("HUD timer at 120 residue %d: %s ticks, stock %d at 30" % (
                residue, got, stock))
    unfixed = timer_ticks(img, hdr, None, 1, 600, 0x4000, 3000)
    report.append("HUD timer from 10 s: runs out after %.2f s at stock 30 and fixed 120; "
                  "unfixed 120: %.2f s" % (stock / 30, unfixed / 120))
    return problems, runs, report


FLAG60 = 0xB6AC40      # the 60 fps flag: 0 at 30 fps, 1 when the mode byte is 1


def flag_emu(img, hdr, n, real):
    """f6_emu with the 60 fps flag set as flower_tick sets it: 1 when the mode
    byte is 1."""
    emu = f6_emu(img, hdr, n, 2, real)
    emu.mu.mem_write(BASE + FLAG60, struct.pack("<I", 1 if real == 1 else 0))
    return emu


def call_fn(emu, fn, regs, stack=(), fc=0x4000):
    """Call main+fn with the registers set and the stack arguments from
    [rsp + 0x28] on; run to its return."""
    emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
    rsp = vmt.STACK_TOP - 0x2000
    emu.mu.mem_write(rsp, struct.pack("<Q", vmt.SENTINEL))
    for k, v in enumerate(stack):
        emu.mu.mem_write(rsp + 0x28 + 8 * k, struct.pack("<Q", v))
    emu.set_reg("rsp", rsp)
    for r, v in regs.items():
        emu.set_reg(r, v)
    emu.exit = None
    emu.stop_outside = None
    emu.mu.emu_start(BASE + fn, 0, count=20000)
    if emu.exit != vmt.SENTINEL:
        raise RuntimeError("main+%X did not return" % fn)


def fade_length(img, hdr, n, real, ticks):
    """The screen fade's length in ticks as 3E2A90 sets it (+C) for a fade of
    `ticks`: 3E2B60 steps +E up to it once a tick."""
    emu = flag_emu(img, hdr, n, real)
    fade = OBJ + 0x300
    call_fn(emu, 0x3E2A90, {"rcx": fade, "rdx": 0, "r8": 8, "r9": 0},
            (0x80FFFFFF, 0xFFFFFF, ticks))
    return struct.unpack("<H", emu.mu.mem_read(fade + 0xC, 2))[0]


def rumble_ticks(img, hdr, n, real, length, fc0, limit):
    """A rumble cPad::ActSet(pad, 0x1000000, (length << flag) << 16) queues, as
    the enemies' code queues one, then cPad::Actuater every tick: the ticks
    until its slot is empty again."""
    emu = flag_emu(img, hdr, n, real)
    pad = OBJ + 0x1000
    emu.mu.mem_write(pad, b"\0" * 0x280)
    shifted = (length << (1 if real == 1 else 0)) << 16
    call_fn(emu, 0x182470, {"rcx": pad, "rdx": 0x1000000, "r8": shifted}, fc=fc0)
    if not emu.mu.mem_read(pad, 1)[0]:
        raise RuntimeError("cPad::ActSet queued nothing")
    for t in range(limit):
        call_fn(emu, 0x1825A0, {"rcx": pad}, fc=fc0 + t)
        if not emu.mu.mem_read(pad, 1)[0]:
            return t + 1
    return None


FPS_BYTE = 0xB6AC44    # 30 at 30 fps, 60 when the mode byte is 1
MC_WAIT, MC_WAIT_DONE = 0x1BECA0, 0x1BECDA


def wait_ticks(img, hdr, n, real, fps, limit):
    """The memory-card screens' countdown 1BECA0 called once a tick on a fresh
    screen (+1FC = 0): its first call sets the wait +6C to fps / 2 (the
    mulstore at 1BECC5), and each call counts it down. The ticks until a call
    finds it at 0 and goes on to its next step (1BECDA)."""
    emu = flag_emu(img, hdr, n, real)
    emu.mu.mem_write(BASE + FPS_BYTE, bytes([fps]))
    screen = OBJ + 0x800
    emu.mu.mem_write(screen, b"\0" * 0x200)
    for t in range(limit):
        rsp = vmt.STACK_TOP - 0x2000
        emu.mu.mem_write(rsp, struct.pack("<Q", vmt.SENTINEL))
        emu.set_reg("rsp", rsp)
        emu.set_reg("rcx", screen)
        emu.exit = None
        emu.stop_outside = (BASE + MC_WAIT, BASE + MC_WAIT_DONE)
        emu.mu.emu_start(BASE + MC_WAIT, 0, count=2000)
        if emu.exit == BASE + MC_WAIT_DONE:
            return t + 1
        if emu.exit != vmt.SENTINEL:
            raise RuntimeError("1BECA0 left at %X" % ((emu.exit or 0) - BASE))
    return None


def check_flag(img, hdr):
    """The flag group in real time: the screen fade (3E2A90's length, which
    3E2B60 steps once a tick) and a rumble (ActSet's slot, which Actuater
    counts down once a tick) must last their stock time at 120, the fade
    exactly, the rumble within a stock tick (Actuater runs on every other
    tick), where unfixed they last half of it. A memory-card wait (fps / 2
    ticks, counted down once a tick) must last its stock half second at 120
    and 60 within a stock tick."""
    problems, runs, report = [], 0, []
    stock = wait_ticks(img, hdr, None, 2, 30, 200)
    got = wait_ticks(img, hdr, 2, 1, 60, 400)
    at60 = wait_ticks(img, hdr, 1, 1, 60, 400)
    unfixed = wait_ticks(img, hdr, None, 1, 60, 400)
    runs += 1
    if None in (stock, got, at60) or abs(got / 120.0 - stock / 30.0) > 1.0 / 30 or \
            abs(at60 / 60.0 - stock / 30.0) > 1.0 / 30:
        problems.append("memory-card wait: %s ticks at 120, %s at 60, stock %s at 30" % (
            got, at60, stock))
    else:
        report.append("memory-card wait: %.3f s at stock 30, %.3f s at fixed 120 and %.3f s "
                      "at 60; unfixed 120: %.3f s" % (stock / 30.0, got / 120.0, at60 / 60.0,
                                                      unfixed / 120.0))
    for ticks in (10, 30, 45):
        stock = fade_length(img, hdr, None, 2, ticks)
        got = fade_length(img, hdr, 2, 1, ticks)
        at60 = fade_length(img, hdr, 1, 1, ticks)
        unfixed = fade_length(img, hdr, None, 1, ticks)
        runs += 1
        if got / 120.0 != stock / 30.0 or at60 / 60.0 != stock / 30.0:
            problems.append("fade of %d: %d ticks at 120, %d at 60, stock %d at 30" % (
                ticks, got, at60, stock))
        report.append("screen fade of %d: %.3f s at stock 30, %.3f s at fixed 120 and %.3f s "
                      "at 60; unfixed 120: %.3f s" % (ticks, stock / 30.0, got / 120.0,
                                                      at60 / 60.0, unfixed / 120.0))
    # The port's own 60 fps rumble is one stock tick shorter than stock's: ActSet
    # doubles the length but not the delay (the argument's low half + 1), and
    # the slot clears on the port's next tick. The fix runs it at 120 exactly
    # as the port runs it at 60, give or take the gate's phase (a port tick).
    for length in (5, 15, 30):
        stock = rumble_ticks(img, hdr, None, 2, length, 0x4000, 400)
        port = rumble_ticks(img, hdr, None, 1, length, 0x4000, 800)   # at 60: N = 1
        worst = 0.0
        for residue in range(2):
            got = rumble_ticks(img, hdr, 2, 1, length, 0x4000 + residue, 800)
            runs += 1
            if got is None or abs(got / 120.0 - port / 60.0) > 1.0 / 60 + 1e-9:
                problems.append("rumble of %d at 120 residue %d: %s ticks, the port %s at 60" %
                                (length, residue, got, port))
                continue
            worst = max(worst, abs(got / 120.0 - port / 60.0))
        if abs(port / 60.0 - stock / 30.0) > 1.0 / 30 + 1e-9:
            problems.append("rumble of %d: the port at 60 %.3f s, stock %.3f s" % (
                length, port / 60.0, stock / 30.0))
        report.append("rumble of %d: %.3f s at stock 30, %.3f s as the port runs it at 60, "
                      "fixed 120 within %.3f s of that; unfixed 120: %.3f s" % (
                          length, stock / 30.0, port / 60.0, worst, port / 120.0))
    return problems, runs, report


def wrapped_diff(a, b, wraps):
    d = abs(a - b)
    return min(d, abs(d - 2.0), abs(d - 1.0)) if wraps else d


def check_sky(img, hdr):
    problems, runs, report = [], 0, []
    for case in SKY_CASES:
        k0 = 60
        stock = run_sky(img, hdr, None, 0, case, k0)
        worst = 0.0
        for n in (2, 4):
            for residue in range(n):
                got = run_sky(img, hdr, n, residue, case, k0 * n)
                runs += 1
                for j in range(1, k0):
                    a, b = stock[j - 1], got[j * n - 1]
                    for x, y in zip(a, b):
                        d = wrapped_diff(x, y, not case[0] & 0x80)
                        worst = max(worst, d)
                        if d > 2e-5:
                            problems.append("sky case %s N=%d residue %d stock tick %d: %r vs %r"
                                            % (case, n, residue, j, y, x))
                            break
                    else:
                        continue
                    break
        report.append("sky flags %04X steps %+d/%+d: 60 stock ticks, worst |dUV| %.2g"
                      % (case[0], case[1], case[2], worst))
    return problems, runs, report


def run_bob(img, hdr, n, residue, talk_ticks, quiet_ticks, length):
    im, pool = image_for(img, hdr, n)
    emu = vmt.Emu(im, pool)
    zero_pages(emu, OBJ, 0x8000)
    H, P, F = OBJ, OBJ + 0x3000, OBJ + 0x5000
    # the motion file: [F] = 1, [F + 4] = 0x100, [F + 0x100 + 0x80] = 0x200: the track at F+0x200
    emu.mu.mem_write(H + 0xE80, struct.pack("<Q", F))
    emu.mu.mem_write(F, struct.pack("<I", 1))
    emu.mu.mem_write(F + 4, struct.pack("<I", 0x100))
    emu.mu.mem_write(F + 0x180, struct.pack("<Q", 0x200))
    emu.mu.mem_write(F + 0x204, struct.pack("<H", length))
    emu.mu.mem_write(P + 0xA0, struct.pack("<Q", P + 0x400))
    trap_fn(emu, 0x20CFD0, lambda e: e.set_reg("rax", P))            # part 4: the head

    def sample(e):  # 4B9690(track, 4, channel, frame): a smooth key value
        e.set_xmm_low(0, f32(1.0 + 0.01 * e.xmm_low(3)))
    trap_fn(emu, 0x4B9690, sample)
    trap_fn(emu, 0x13F2E0, lambda e: None)                          # wrap: identity here
    trap_fn(emu, 0x212150, lambda e: None)                          # matrix build
    for i, (call, slot) in enumerate(vmt.cvec_traps(img, [0x304513]).items()):
        addr = TRAP + 0x100 + 0x10 * i                              # cVec::cVec(): no state
        emu.mu.mem_write(BASE + slot, struct.pack("<Q", addr))
        emu.traps[addr] = lambda e: e.set_reg("rax", e.reg("rcx"))
    fc = 0x1000 + residue
    out = []
    for t in range((talk_ticks + quiet_ticks) * (n or 1)):
        talking = t < talk_ticks * (n or 1)
        emu.mu.mem_write(H + 0x11FC, struct.pack("<I", 0x80000000 if talking else 0))
        emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
        emu.call(0x3043C0, H)
        out.append((emu.rf(H + 0x12F0), emu.rf(H + 0x12EC)))
        fc += 1
    return out


def check_bob(img, hdr):
    problems, runs, report = [], 0, []
    for length in (12, 31):
        talk, quiet = 3 * length, 8
        stock = run_bob(img, hdr, None, 0, talk, quiet, length)
        worst_w = worst_f = 0.0
        for n in (2, 4):
            for residue in range(n):
                got = run_bob(img, hdr, n, residue, talk, quiet, length)
                runs += 1
                for j in range(1, talk + quiet):
                    (ws, fs), (wg, fg) = stock[j - 1], got[j * n - 1]
                    worst_w = max(worst_w, abs(ws - wg))
                    if abs(ws - wg) > 1e-5:
                        problems.append("head-bob weight L=%d N=%d residue %d stock tick %d: "
                                        "%r vs %r" % (length, n, residue, j, wg, ws))
                        break
                    # the frame, while talking: exact until the first wrap, then
                    # each loop may run short by (n-1)/n of a stock tick
                    if j < talk:
                        loops = j // length
                        want = fs if loops == 0 else None
                        if want is not None:
                            worst_f = max(worst_f, abs(fs - fg))
                            if abs(fs - fg) > 1e-4:
                                problems.append("head-bob frame L=%d N=%d residue %d stock tick %d:"
                                                " %r vs %r" % (length, n, residue, j, fg, fs))
                                break
                # the loop period: frames reset to 0 once per loop
                resets = [t for t in range(1, talk * n) if got[t][1] < got[t - 1][1]]
                if len(resets) >= 2:
                    period = (resets[-1] - resets[0]) / (len(resets) - 1) / n
                    short = length - period
                    if not 0 <= short <= (n - 1) / n + 1e-9:
                        problems.append("head-bob loop L=%d N=%d: %.3f stock ticks, stock %d"
                                        % (length, n, period, length))
        report.append("head-bob L=%d: weight within %.2g of stock at every stock tick; frame within"
                      " %.2g until its first wrap; loops at most 0.75 stock tick short" % (
                          length, worst_w, worst_f))
    return problems, runs, report


# ---------------------------------------------------------------------------
# one particle through the effect engine's shared step
# ---------------------------------------------------------------------------

def touch(e, addr, n):
    """Map what a host-side access will touch, as the emulator's demand
    mapping would for an emulated one."""
    for page in range(addr & ~(PAGE - 1), addr + n, PAGE):
        e.map_page(page)


def f4(e, addr):
    touch(e, addr, 16)
    return list(struct.unpack("<4f", e.mu.mem_read(addr, 16)))


def w4(e, addr, v):
    touch(e, addr, 16)
    e.mu.mem_write(addr, struct.pack("<4f", *(f32(x) for x in v)))
    e.written.update(range(addr, addr + 16))   # a store, as the import's own


def import_handlers():
    """flower_kernel's cVec and the CRT's float math, by import name. Stock and
    patched runs share them, so they need only be deterministic."""
    def ctor4(e):
        rsp = e.reg("rsp")
        w = struct.unpack("<f", e.mu.mem_read(rsp + 0x28, 4))[0]
        w4(e, e.reg("rcx"), [e.xmm_low(1), e.xmm_low(2), e.xmm_low(3), w])
        e.set_reg("rax", e.reg("rcx"))

    def copy(e):
        e.mu.mem_write(e.reg("rcx"), bytes(e.mu.mem_read(e.reg("rdx"), 16)))
        e.set_reg("rax", e.reg("rcx"))

    def default(e):
        e.set_reg("rax", e.reg("rcx"))

    def add_xyz(e):
        a, b = f4(e, e.reg("rdx")), f4(e, e.reg("r8"))
        w = f4(e, e.reg("rcx"))[3]                  # flower_kernel keeps the destination's w
        w4(e, e.reg("rcx"), [a[0] + b[0], a[1] + b[1], a[2] + b[2], w])

    def add_assign(e):
        a, b = f4(e, e.reg("rcx")), f4(e, e.reg("rdx"))
        w4(e, e.reg("rcx"), [a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3]])
        e.set_reg("rax", e.reg("rcx"))

    def sub_vec(e):
        # cVec cVec::operator-(const cVec&) const: rcx this, rdx the result, r8
        a, b = f4(e, e.reg("rcx")), f4(e, e.reg("r8"))
        w4(e, e.reg("rdx"), [a[0] - b[0], a[1] - b[1], a[2] - b[2], a[3]])
        e.set_reg("rax", e.reg("rdx"))

    def mul_assign(e):
        a, k = f4(e, e.reg("rcx")), e.xmm_low(1)
        w4(e, e.reg("rcx"), [a[0] * k, a[1] * k, a[2] * k, a[3]])
        e.set_reg("rax", e.reg("rcx"))

    def mul_float(e):
        # cVec cVec::operator*(float) const: rcx this, rdx the result, xmm2;
        # the result's w is the kernel's default vector's, 1
        a, k = f4(e, e.reg("rcx")), e.xmm_low(2)
        w4(e, e.reg("rdx"), [a[0] * k, a[1] * k, a[2] * k, 1.0])
        e.set_reg("rax", e.reg("rdx"))

    return {
        "??0cVec@math@wk@@QEAA@MMMM@Z": ctor4,
        "??0cVec@math@wk@@QEAA@AEBV012@@Z": copy,
        "??0cVec@math@wk@@QEAA@XZ": default,
        "??4cVec@math@wk@@QEAAAEAV012@AEBV012@@Z": copy,
        "?AddXYZ@cVec@math@wk@@SAXAEAV123@AEBV123@1@Z": add_xyz,
        "??YcVec@math@wk@@QEAAAEAV012@AEBV012@@Z": add_assign,
        "??XcVec@math@wk@@QEAAAEAV012@M@Z": mul_assign,
        "sinf": lambda e: e.set_xmm_low(0, f32(math.sin(e.xmm_low(0)))),
        "atanf": lambda e: e.set_xmm_low(0, f32(math.atan(e.xmm_low(0)))),
        "atan2f": lambda e: e.set_xmm_low(0, f32(math.atan2(e.xmm_low(0), e.xmm_low(1)))),
        "??GcVec@math@wk@@QEBA?AV012@AEBV012@@Z": sub_vec,
        "??DcVec@math@wk@@QEBA?AV012@M@Z": mul_float,
        "cosf": lambda e: e.set_xmm_low(0, f32(math.cos(e.xmm_low(0)))),
    }


def bind_imports(emu, pe_imports, add_scale=None):
    """Every IAT slot to a trap; an import without a handler faults loudly.
    With add_scale, cVec::operator+= adds that multiple of its argument: the
    reference for a scaledadd site."""
    handlers = import_handlers()
    if add_scale is not None:
        def scaled(e):
            # the replacement stores x, y and z; operator+= also rewrote w
            # unchanged, which leaves the same memory
            a, b = f4(e, e.reg("rcx")), f4(e, e.reg("rdx"))
            xyz = [f32(f32(b[i] * add_scale) + a[i]) for i in range(3)]
            e.mu.mem_write(e.reg("rcx"), struct.pack("<3f", *xyz))
            e.written.update(range(e.reg("rcx"), e.reg("rcx") + 12))
            e.set_reg("rax", e.reg("rcx"))
        handlers["??YcVec@math@wk@@QEAAAEAV012@AEBV012@@Z"] = scaled
    for i, (slot, name) in enumerate(sorted(pe_imports.items())):
        # a page of their own, clear of the emulator's return sentinel
        addr = IMPORT_TRAPS + 0x8 * i
        emu.map_page(addr & ~(PAGE - 1))
        emu.mu.mem_write(BASE + slot, struct.pack("<Q", addr))

        def missing(e, name=name):
            raise RuntimeError("import %s called without a handler" % name)
        emu.traps[addr] = handlers.get(name, missing)


def wrap_angle(e):
    x = e.xmm_low(0)
    e.set_xmm_low(0, f32((x + math.pi) % (2 * math.pi) - math.pi))


P_VT, P_DATA = 0x1000, 0x2000
IMPORT_TRAPS = TRAP + 0x10000
P_SLOTS = {9: 0x18FF60, 10: 0x190AD0, 11: 0x18FBD0, 12: 0x190DA0, 13: 0x190D00,
           14: 0x191110, 15: 0x191090}


def run_particle(img, hdr, n, residue, pe_imports, ticks):
    im, pool = image_for(img, hdr, n)
    emu = vmt.Emu(im, pool)
    zero_pages(emu, OBJ, 0x8000)
    bind_imports(emu, pe_imports)
    trap_fn(emu, 0x13F2E0, wrap_angle)
    trap_fn(emu, 0x18D030, lambda e: None)                        # the setters' dirty mark
    trap_fn(emu, 0x1921A0, lambda e: (e.mu.mem_write(e.reg("rdx"), b"\0" * 16),
                                      e.set_reg("rax", e.reg("rdx"))))
    trap_fn(emu, 0x191F40, lambda e: e.set_xmm_low(0, 1.0))       # key colour and alpha
    dead = []
    kill = TRAP + 0x100
    emu.traps[kill] = lambda e: dead.append(True)
    P, V, D = OBJ, OBJ + P_VT, OBJ + P_DATA
    emu.mu.mem_write(P, struct.pack("<Q", V))
    for k in range(16):
        emu.mu.mem_write(V + 8 * k, struct.pack("<Q", kill if k == 7 else
                                               BASE + P_SLOTS[k] if k in P_SLOTS else kill))
    emu.mu.mem_write(P + 0x138, struct.pack("<Q", D))
    w4(emu, P + 0x40, [1, 1, 1, 1])                                 # scale
    w4(emu, P + 0x50, [0, 0, 0, 1])                                 # rotation
    w4(emu, P + 0x60, [0, 0, 0, 1])                                 # position
    emu.mu.mem_write(P + 0x150, struct.pack("<I", (1 << 26) | (1 << 25) | (1 << 12) | (1 << 11)))
    w4(emu, P + 0x160, [1.5, 2.0, -0.7, 0.0])                       # velocity
    emu.wf(P + 0x16C, 0.97)                                         # drag
    w4(emu, P + 0x170, [0.0, -0.08, 0.01, 0.0])                     # acceleration
    emu.mu.mem_write(P + 0x17C, b"\x02")                            # scale growth mode 2
    for off, v in ((0x180, 1.0), (0x184, 1.0), (0x188, 0.3), (0x18C, -0.1),
                   (0x190, 0.9), (0x194, 0.95)):
        emu.wf(P + off, v)
    emu.mu.mem_write(P + 0x198, struct.pack("<hhhh", 30, 20, 40, 25))  # wobble amps, rates
    w4(emu, P + 0x1B4, [0.05, 0.1, -0.02, 0.0])                     # angular velocity
    emu.mu.mem_write(P + 0x262, struct.pack("<H", 60))              # lifetime
    emu.mu.mem_write(P + 0x266, struct.pack("<h", 7))               # keys
    emu.mu.mem_write(P + 0x26C, bytes([2, 2, 0, 4, 2]))             # flipbook reload, hold, cell, 4x2
    emu.wf(P + 0x294, 0.2)                                          # turbulence amplitude
    emu.wf(P + 0x298, 0.05)                                         # its phase rate
    emu.mu.mem_write(D + 4, struct.pack("<I", 1 << 21))             # turbulence on
    for off, v in ((0x2A4, 1.0), (0x2A8, 0.5), (0x2AC, 0.8)):
        emu.wf(D + off, v)
    emu.mu.mem_write(D + 0x2B0, struct.pack("<bbbbbbh", 10, -7, 5, 0, 3, -2, 5))
    emu.mu.mem_write(D + 0x295, b"\x09")                            # spin 9/90 a tick
    fc = 0x1000 + residue
    out = []
    for _ in range(ticks):
        emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
        emu.call(0x1928F0, P)
        fc += 1
        if dead:
            out.append(None)
            break
        ints = struct.unpack("<HH", emu.mu.mem_read(P + 0x260, 4)) + \
            tuple(emu.mu.mem_read(P + 0x26D, 2)) + struct.unpack("<hh", emu.mu.mem_read(P + 0x1A0, 4))
        floats = f4(emu, P + 0x60)[:3] + f4(emu, P + 0x160)[:3] + [emu.rf(P + 0x180), emu.rf(P + 0x184)] \
            + f4(emu, P + 0x50)[:3] + [emu.rf(P + 0x27C), emu.rf(P + 0x294), emu.rf(P + 0x298),
                                       emu.rf(P + 0x288)]
        out.append((ints, floats))
    return out


FLOAT_NAMES = ["pos x", "pos y", "pos z", "vel x", "vel y", "vel z", "scale x", "scale y",
               "rot x", "rot y", "rot z", "spin", "turb amp", "turb rate", "turb phase"]
ANGLES = {8, 9, 10, 11, 14}


def check_particle(img, hdr):
    import pefile as _pe
    pe = _pe.PE(os.path.join(GAME, "main.dll"), fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    pe_imports = {imp.address - base: imp.name.decode()
                  for entry in pe.DIRECTORY_ENTRY_IMPORT for imp in entry.imports if imp.name}
    problems, runs = [], 0
    stock = run_particle(img, hdr, None, 0, pe_imports, 80)
    k0 = len(stock) - 1 if stock[-1] is None else len(stock)
    live = stock[:k0]
    span = [max(max(abs(t[1][i] - live[0][1][i]) for t in live), 1e-3) for i in range(len(live[0][1]))]
    worst = [0.0] * len(span)
    exact_worst, between_worst = 0.0, 0.0
    for n in (2, 4):
        for residue in range(n):
            got = run_particle(img, hdr, n, residue, pe_imports, 80 * n)
            runs += 1
            died = len(got) - 1 if got[-1] is None else None
            lead = (n - (0x1000 + residue) % n) % n     # ticks before the first stock tick
            if died is None or abs((died - lead) / n + 1 - k0) > 1.0:
                problems.append("particle N=%d residue %d: died after %s ticks, stock after %d "
                                "stock ticks" % (n, residue, died, k0))
                continue
            for j in range(1, k0 - 1):
                at = lead + (j - 1) * n + (n - 1)
                if at >= died:
                    break
                (ia, fa), (ib, fb) = live[j - 1], got[at]
                if ia != ib:
                    problems.append("particle N=%d residue %d stock tick %d: integers %s, stock %s"
                                    % (n, residue, j, ib, ia))
                    break
                fnext = live[j][1]
                for i, (x, y, z) in enumerate(zip(fa, fb, fnext)):
                    def diff(u, v, i=i):
                        d = u - v
                        if i in ANGLES:
                            d = (d + math.pi) % (2 * math.pi) - math.pi
                        return d
                    if lead == 0:
                        q = abs(diff(y, x)) / span[i]
                        exact_worst = max(exact_worst, q)
                        worst[i] = max(worst[i], q)
                        if q > 1e-4:
                            problems.append("particle N=%d residue 0 stock tick %d: %s %r, stock %r"
                                            % (n, j, FLOAT_NAMES[i], y, x))
                    else:
                        # born mid-period, it moved lead/N of a tick on its first
                        # rates before their first stock update: at most one
                        # stock step from stock now plus one first step, and
                        # that offset must not grow
                        first = abs(diff(live[1][1][i], live[0][1][i]))
                        bound = abs(diff(z, x)) + first + 1e-4 * span[i]
                        d = abs(diff(y, x))
                        between_worst = max(between_worst, d / span[i])
                        if d > bound:
                            problems.append("particle N=%d residue %d stock tick %d: %s %r, stock "
                                            "%r, more than a stock step and a first step apart"
                                            % (n, residue, j, FLOAT_NAMES[i], y, x))
    report = ["particle: dies after %d stock ticks at 30, 2 and 4 alike; integers exact at every "
              "stock tick; floats from a period's first tick within %.1e of their travel of "
              "stock's, from other residues within %.1e of it (a step and a first step at most)"
              % (k0, exact_worst, between_worst)]
    return problems, runs, report


# ---------------------------------------------------------------------------
# one enemy piece: a pull, a move, an acceleration and a damping a tick
# ---------------------------------------------------------------------------

PIECE_LO, PIECE_HI = 0x5CCBEB, 0x5CCC8D     # 5CC3E0's second state, straight code
PIECE_NAMES = ["pos x", "pos y", "pos z", "vel x", "vel y", "vel z"]


def run_piece(img, hdr, n, residue, pe_imports, ticks):
    """5CCBEB-5CCC8D a tick: vel += (joint - pos) * 0.008, pos += vel * speed,
    vel += acc * speed, vel *= 0.92, with the enemy (speed 0.6) in r14, the
    piece in rsi and 20CFD0 answering the joint. [(pos, vel)] after each tick."""
    im, pool = image_for(img, hdr, n)
    emu = vmt.Emu(im, pool)
    zero_pages(emu, OBJ, 0x8000)
    bind_imports(emu, pe_imports)
    enemy, piece, joint, where = OBJ, OBJ + 0x2000, OBJ + 0x3000, OBJ + 0x3100
    emu.wf(enemy + 0x1080, 0.6)
    w4(emu, piece + 0x10, [3.0, 12.0, -5.0, 1.0])                  # position
    w4(emu, piece + 0x20, [0.8, 1.5, -0.4, 0.0])                   # velocity
    w4(emu, piece + 0x30, [0.0, -0.3, 0.05, 0.0])                  # acceleration
    w4(emu, where, [0.0, 20.0, 4.0, 1.0])                          # the joint's position
    emu.mu.mem_write(joint + 0xA8, struct.pack("<Q", where))
    trap_fn(emu, 0x20CFD0, lambda e: e.set_reg("rax", joint))       # the model's joint 1
    out = []
    fc = 0x1000 + residue
    for _ in range(ticks):
        emu.set_reg("r14", enemy)
        emu.set_reg("rsi", piece)
        at = f6_run(emu, PIECE_LO, PIECE_HI, fc)
        if at != PIECE_HI:
            raise RuntimeError("the piece's block left at %X" % at)
        fc += 1
        out.append(f4(emu, piece + 0x10)[:3] + f4(emu, piece + 0x20)[:3])
    return out


def check_piece(img, hdr, ticks=120):
    """Started on a period's first tick, the piece passes through stock's
    position and velocity at every stock tick. Started mid-period, it takes
    its first velocity change with less than a tick's move: an offset of about
    one first step, which the pull swings and the damping settles. It must
    stay under 1.5 first steps and shrink to under half its early size."""
    import pefile as _pe
    pe = _pe.PE(os.path.join(GAME, "main.dll"), fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    pe_imports = {imp.address - base: imp.name.decode()
                  for entry in pe.DIRECTORY_ENTRY_IMPORT for imp in entry.imports if imp.name}
    problems, runs = [], 0
    stock = run_piece(img, hdr, None, 0, pe_imports, ticks)
    span = [max(max(abs(t[i] - stock[0][i]) for t in stock), 1e-3) for i in range(6)]
    first = [max(abs(stock[1][i] - stock[0][i]) for i in lanes) for lanes in
             ((0, 1, 2), (3, 4, 5))]
    exact, offset, unfixed = 0.0, 0.0, 0.0
    for n in (2, 4):
        for residue in range(n):
            got = run_piece(img, hdr, n, residue, pe_imports, ticks * n)
            runs += 1
            lead = (n - (0x1000 + residue) % n) % n
            devs = []
            for j in range(1, ticks - 1):
                at = lead + (j - 1) * n + (n - 1)
                d = [abs(got[at][i] - stock[j - 1][i]) for i in range(6)]
                if lead == 0:
                    q = max(d[i] / span[i] for i in range(6))
                    exact = max(exact, q)
                    if q > 1e-4:
                        i = max(range(6), key=lambda i: d[i] / span[i])
                        problems.append("piece N=%d stock tick %d: %s %r, stock %r" % (
                            n, j, PIECE_NAMES[i], got[at][i], stock[j - 1][i]))
                    continue
                devs.append(max(max(d[:3]) / first[0], max(d[3:]) / first[1]))
            if devs:
                q = len(devs) // 4
                early, late = max(devs[:q]), max(devs[-q:])
                offset = max(offset, max(devs))
                if max(devs) > 1.5 or late > 0.5 * early:
                    problems.append("piece N=%d residue %d: offset up to %.2f first steps, "
                                    "%.2f early and %.2f late" % (n, residue, max(devs), early,
                                                                   late))
    # the unpatched game at 120: the same block every tick, unscaled
    raw = run_piece(img, hdr, None, 0, pe_imports, ticks * 4)
    for j in range(1, ticks // 4):
        unfixed = max(unfixed, max(abs(raw[4 * j - 1][i] - stock[j - 1][i]) / span[i]
                                   for i in range(3)))
    if unfixed < 0.5:
        problems.append("piece: the unpatched block at 120 is only %.2f off stock; the check "
                        "would not see a wrong fix" % unfixed)
    report = ["piece (5CC3E0: pull, move, acceleration, damping): from a period's first tick "
              "within %.1e of its travel of stock's at every stock tick; started mid-period at "
              "most %.2f first steps off, settling; unfixed 120 %.2f of its travel off"
              % (exact, offset, unfixed)]
    return problems, runs, report


# ---------------------------------------------------------------------------
# turning toward a target
# ---------------------------------------------------------------------------

def run_turn(img, hdr, n, residue, fn, limit, start, target, ticks, pe_imports):
    """The real 20E210 (toward a point) or 20E290 (toward an angle), every
    tick, from heading `start` toward `target`; the heading after each tick."""
    im, pool = image_for(img, hdr, n)
    emu = vmt.Emu(im, pool)
    zero_pages(emu, OBJ, 0x4000)
    bind_imports(emu, pe_imports)
    trap_fn(emu, 0x13F2E0, wrap_angle)
    O, POS, TGT = OBJ, OBJ + 0x1000, OBJ + 0x1100
    emu.mu.mem_write(O + 0xA8, struct.pack("<Q", POS))
    w4(emu, POS, [0.0, 0.0, 0.0, 1.0])
    w4(emu, TGT, [100.0 * math.sin(target), 0.0, 100.0 * math.cos(target), 1.0])
    emu.wf(O + 0xB4, start)
    fc = 0x1000 + residue
    out = []
    for _ in range(ticks):
        emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
        emu.set_xmm_low(1, target)                    # 20E290's angle
        emu.set_xmm_low(2, limit)
        emu.set_reg("rdx", TGT)                       # 20E210's point
        rsp = vmt.STACK_TOP - 0x2000
        emu.mu.mem_write(rsp, struct.pack("<Q", vmt.SENTINEL))
        emu.set_reg("rsp", rsp)
        emu.set_reg("rcx", O)
        emu.exit = None
        emu.stop_outside = None
        emu.mu.emu_start(BASE + fn, 0, count=20000)
        if emu.exit != vmt.SENTINEL:
            raise RuntimeError("main+%X did not return" % fn)
        out.append(emu.rf(O + 0xB4))
        fc += 1
    return out


def check_turn(img, hdr):
    """At every stock tick the heading must be stock's: while the limit holds
    it back each tick gains limit/N, and on the tick it reaches the target it
    stops there, as stock's does."""
    pe_imports = pe_import_names()
    problems, runs, worst = [], 0, 0.0
    for fn in (0x20E210, 0x20E290):
        for limit, start, target in ((0.2618, 0.0, 2.5), (0.0873, -3.0, 3.0), (3.1416, 1.0, -2.0),
                                     (0.1047, 2.9, -2.9)):
            stock = run_turn(img, hdr, None, 0, fn, limit, start, target, 40, pe_imports)
            for n in (2, 4):
                for residue in range(n):
                    got = run_turn(img, hdr, n, residue, fn, limit, start, target, 40 * n,
                                   pe_imports)
                    runs += 1
                    for j in range(1, 40):
                        d = abs(got[j * n - 1] - stock[j - 1])
                        d = min(d, abs(d - 2 * math.pi))
                        worst = max(worst, d)
                        if d > 2e-4:
                            problems.append("turn %X limit %g from %g to %g at N=%d residue %d, "
                                            "stock tick %d: %r, stock %r" % (
                                                fn, limit, start, target, n, residue, j,
                                                got[j * n - 1], stock[j - 1]))
                            break
    report = ["turns: 20E210 and 20E290, 4 cases each, the heading within %.1e rad of stock's at "
              "every stock tick" % worst]
    return problems, runs, report


# ---------------------------------------------------------------------------
# the turn steps (group steer): retargeted calls
# ---------------------------------------------------------------------------
# Each target's limit register, from its signature (MS x64: the nth argument in
# xmm(n-1)): 2DDF90(pos, heading, point, limit) and 2DA570(target, cur, k,
# limit) take it fourth, 23A2E0(enemy, rate) second. 2DA570's k is a per-tick
# blend. 2DA410(obj, d), the forward step (pos += M x (0, 0, d)), takes its
# distance second: the actor group's imp kick. 2DA460 uses the same second
# argument for a wp03 forward/sideways motion step. 20EA30(obj, g, dt, ...), the
# fall (y += dt x vy, vy -= g x dt, dt read nowhere else), takes dt third: the
# weapons' updates pass their slow-motion factor. 20E130(obj, d), a forward step
# in the heading's plane (x, z += R(+B0) x (0, 0, d)), takes d second.
# 20E030(obj, point, limit) turns the heading toward a point by at most limit.
LIMIT_XMM = {0x2DDF90: 3, 0x2DA570: 3, 0x23A2E0: 1,
             0x2DA410: 1, 0x2DA460: 1, 0x20EA30: 2, 0x20E130: 1, 0x20E030: 2}
BLEND = {0x2DA570}
ALREADY_BLEND_SCALED = {0x482C8C, 0x482CB5, 0x482FF1, 0x48306C,
                        0x4830DF, 0x483137, 0x483189,
                        # camera modes whose k is a 7A82D8 / 7A8330 mode-table
                        # value minus one (mode_constants rewrites the slot)
                        0x46B7A3, 0x47AA70, 0x47AAC9, 0x47AB22, 0x47ACBA,
                        0x47D0A4, 0x47E201}
BLEND_CASES = (0.2, 0.05, 0.3, 0.999, 0.001, 0.0, 1.0, -0.5, 1.5, float("nan"))


def vmt_reg64(name):
    """the 64-bit register a 32-bit name writes (zero-extending it)"""
    import gen_shadow_mode
    return gen_shadow_mode.REG64.get(name, name)


def blend_ref(k, n):
    """1 - (1 - k)^(1/N) as the stub must compute it: 1 - k and the result
    rounded to float, one sqrtss per halving; k outside (0, 1) (NaN included)
    and N = 1 leave it as it was."""
    if n == 1 or not 0 < k < 1:
        return k
    return f32(1.0 - root_ref(f32(1.0 - k), n))


def divisor_blend_ref(divisor, n):
    """A delta/divisor easing step, preserving the original division at N=1.
    Nonpositive, <=1 and NaN divisors keep the original game's semantics.
    """
    if n == 1 or not divisor > 1:
        return divisor
    coefficient = blend_ref(f32(1.0 / divisor), n)
    return f32(1.0 / coefficient) if coefficient else float("inf")


def check_calls(img, patched_img, pool_for, hdr, rnd, states, only_call=None):
    """Every retargeted call, run from its call instruction to its target's
    entry, the patched image against the original: the same registers (xmm4
    and xmm5 aside for a blend: volatile, no argument of 2DA570, its scratch;
    the flags aside: dead at a call), the same return address and memory,
    except the limit register's low lane times s and, for 2DA570, k made
    blend_ref(k, N)."""
    problems, runs = [], 0
    kinds = {site: KIND[k] for site, k, *_ in hdr["sites"]}
    pools = {}
    ops = {c[0]: op for c, op in zip(hdr["calls"], call_ops(hdr))}
    for rva, _stub, target in hdr["calls"]:
        if only_call is not None and rva not in only_call:
            continue
        kname = kinds.get(rva)
        if kname == "callgate":
            gp, gr = check_gate_call(img, patched_img, pool_for, rva, target, rnd, states)
            problems += gp
            runs += gr
            continue
        want_kind = ("callblend" if target in BLEND and rva not in ALREADY_BLEND_SCALED
                     else "callscale")
        if target not in LIMIT_XMM:
            problems.append("call %X targets %X, whose limit register is not known here"
                            % (rva, target))
            continue
        if kname != want_kind:
            problems.append("call %X of %X is %s, not %s" % (rva, target, kname, want_kind))
            continue
        if bytes(img[rva:rva + 5]) != bytes([ops[rva]]) + struct.pack("<i", target - (rva + 5)):
            problems.append("main+%X is not `call %X`" % (rva, target))
            continue
        r = LIMIT_XMM[target]
        skip = {4, 5} if want_kind == "callblend" else set()
        for n in (1, 2, 4):
            s = f32(1.0 / n)
            if n not in pools:
                pools[n] = pool_for(n, 2)
            for k in range(states):
                st = vmt.random_state(rnd)
                kv = None
                if want_kind == "callblend":
                    kv = BLEND_CASES[k % len(BLEND_CASES)] if k % 2 else rnd.uniform(0.001, 0.999)
                    st["xmm"][2] = (st["xmm"][2] & ~0xFFFFFFFF) | fbits(kv)
                fc = rnd.getrandbits(20) * 4 + (k % 4)
                results = []
                for variant in ("orig", "patched"):
                    emu = vmt.Emu(img if variant == "orig" else patched_img,
                                  pools[n] if variant == "patched" else None, seed=st["mem_seed"])
                    vmt.load_state(emu, st, fc)

                    def stop(e):
                        e.exit = BASE + target
                        e.mu.emu_stop()
                    emu.pre = {BASE + target: stop}
                    emu.stop_outside = None
                    try:
                        emu.mu.emu_start(BASE + rva, 0, count=200)
                    except UcError as e:
                        emu.exit = "fault %s" % e
                    results.append((snapshot(emu, skip, True), emu))
                (a, ea), (b, eb) = results
                runs += 1
                want = dict(a)
                low = struct.unpack("<f", struct.pack("<I", a["xmm%d" % r] & 0xFFFFFFFF))[0]
                want["xmm%d" % r] = quiet_lanes((a["xmm%d" % r] & ~0xFFFFFFFF) |
                                                fbits(f32(low * s)))
                if kv is not None:
                    want["xmm2"] = quiet_lanes((a["xmm2"] & ~0xFFFFFFFF) |
                                               fbits(blend_ref(f32(kv), n)))
                if a["exit"] != BASE + target:
                    problems.append("call %X: the original does not reach %X" % (rva, target))
                    break
                if want != b:
                    diff = [key for key in want if want[key] != b.get(key)]
                    problems.append("call %X N=%d%s: %s differ (%s: want %s, got %s)" % (
                        rva, n, "" if kv is None else " k=%r" % kv, ", ".join(diff[:4]), diff[0],
                        vmt_hex(want[diff[0]]), vmt_hex(b.get(diff[0]))))
                    break
                ret = struct.unpack("<Q", eb.mu.mem_read(eb.reg("rsp"), 8))[0]
                # a call pushed its return address; a tail jump left the caller's
                want_ret = BASE + rva + 5 if ops[rva] == 0xE8 else \
                    struct.unpack("<Q", ea.mu.mem_read(ea.reg("rsp"), 8))[0]
                wa, wb = vmt.game_writes(ea), vmt.game_writes(eb)
                if ret != want_ret or wa != wb or any(
                        read_byte(ea, x) != read_byte(eb, x) for x in wa):
                    problems.append("call %X N=%d: return address or memory differs" % (rva, n))
                    break
    return problems, runs


# the yes/no functions a callgate may answer for: the skip check
GATE_TARGETS = {0x13A7D0, 0x433250, 0x4331D0, 0x4332E0, 0x433360}
# and the void calls the generator gates ("void": rax unread after the call):
# call site -> its update (or a sound play whose result the caller drops:
# vtca 375FF0's phase sound, cDogLikeHm 4873A0's +E36 sounds)
VOID_GATE_CALLS = {0x626404: 0x623540, 0x376136: 0x44E470, 0x48762A: 0x44E3C0}


def check_gate_call(img, patched_img, pool_for, rva, target, rnd, states):
    """A callgate: on a stock tick (fc & (N-1) == 0) the patched call reaches
    its target exactly as the original does (flags aside, dead at a call);
    on the others it returns to the caller at once with rax = 0 and the rest
    of the machine as it was."""
    problems, runs = [], 0
    if target not in GATE_TARGETS and VOID_GATE_CALLS.get(rva) != target:
        return ["callgate %X targets %X, not a function known to answer yes/no in al"
                % (rva, target)], 0
    if bytes(img[rva:rva + 5]) != b"\xE8" + struct.pack("<i", target - (rva + 5)):
        return ["main+%X is not `call %X`" % (rva, target)], 0
    for n in (1, 2, 4):
        pool = pool_for(n, 2)
        for k in range(states):
            st = vmt.random_state(rnd)
            fc = rnd.getrandbits(20) * 4 + (k % 4)
            stock = (fc & (n - 1)) == 0
            results = []
            for variant in ("orig", "patched"):
                emu = vmt.Emu(img if variant == "orig" else patched_img,
                              pool if variant == "patched" else None, seed=st["mem_seed"])
                vmt.load_state(emu, st, fc)

                def stop(e, where):
                    e.exit = where
                    e.mu.emu_stop()
                emu.pre = {BASE + target: lambda e: stop(e, BASE + target),
                           BASE + rva + 5: lambda e: stop(e, BASE + rva + 5)}
                emu.stop_outside = None
                try:
                    emu.mu.emu_start(BASE + rva, 0, count=200)
                except UcError as e:
                    emu.exit = "fault %s" % e
                results.append((snapshot(emu, set(), True), emu))
            (a, ea), (b, eb) = results
            runs += 1
            if stock:
                want = a
            else:
                want = dict(st_regs(st), exit=BASE + rva + 5, rax=0)
                want.update({key: a[key] for key in a if key.startswith("xmm")})
            if want != b:
                diff = [key for key in want if want[key] != b.get(key)]
                problems.append("callgate %X N=%d fc&mask=%d: %s differ (%s: want %s, got %s)"
                                % (rva, n, fc & (n - 1), ", ".join(diff[:4]), diff[0],
                                   vmt_hex(want[diff[0]]), vmt_hex(b.get(diff[0]))))
                break
            wa, wb = vmt.game_writes(ea), vmt.game_writes(eb)
            if stock and (wa != wb or any(read_byte(ea, x) != read_byte(eb, x) for x in wa)):
                problems.append("callgate %X N=%d: memory differs" % (rva, n))
                break
            if not stock and wb:
                problems.append("callgate %X N=%d: writes game memory between stock ticks"
                                % (rva, n))
                break
    return problems, runs


class ChainedHooks(dict):
    """emu.pre for a window's reference run: a second hook at one address runs
    after the first (unless the first redirected) instead of replacing it. One
    site's restore can sit on the next site's address (two srcroot rows on
    adjacent mulss instructions of one source register)."""

    def __setitem__(self, at, f):
        old = self.get(at)
        if old is not None:
            def both(e, a=old, b=f, at=at):
                a(e)
                if e.reg("rip") == BASE + at:
                    b(e)
            f = both
        dict.__setitem__(self, at, f)


def st_regs(st):
    """a random state's general registers, as vmt.snapshot names them"""
    return {name: st[name] for name in vmt.GPR_NAMES}


def call_stub(hdr, target):
    """The first retargeted call of `target`: its stub."""
    return next(stub for rva, stub, t in sorted(hdr["calls"]) if t == target)


def run_steer(img, hdr, n, target, args, start, ticks, pe_imports, fixed=True):
    """The real 2DDF90 or 2DA570 every tick, the way a turn step's caller uses
    it: heading += 2DDF90(pos, heading, point, limit), or cur = 2DA570(goal,
    cur, k, limit). At n None the original function once a stock tick; else
    through the first retargeted call's stub (or, fixed False, the original
    function every tick). The angle after each tick."""
    im, pool = image_for(img, hdr, 1 if n is None else n)
    emu = vmt.Emu(im, pool)
    zero_pages(emu, OBJ, 0x4000)
    bind_imports(emu, pe_imports)
    trap_fn(emu, 0x13F2E0, wrap_angle)
    POS, TGT = OBJ + 0x1000, OBJ + 0x1100
    entry = POOL + call_stub(hdr, target) if n is not None and fixed else BASE + target
    angle, out = start, []
    for _ in range(ticks):
        if target == 0x2DDF90:
            goal, limit = args
            w4(emu, POS, [0.0, 0.0, 0.0, 1.0])
            w4(emu, TGT, [100.0 * math.sin(goal), 0.0, 100.0 * math.cos(goal), 1.0])
            emu.set_reg("rcx", POS)
            emu.set_reg("r8", TGT)
            emu.set_xmm_low(1, angle)
            emu.set_xmm_low(3, limit)
        else:
            goal, k, limit = args
            emu.set_xmm_low(0, goal)
            emu.set_xmm_low(1, angle)
            emu.set_xmm_low(2, k)
            emu.set_xmm_low(3, limit)
        rsp = vmt.STACK_TOP - 0x2000
        emu.mu.mem_write(rsp, struct.pack("<Q", vmt.SENTINEL))
        emu.set_reg("rsp", rsp)
        emu.exit = None
        emu.stop_outside = None
        emu.mu.emu_start(entry, 0, count=20000)
        if emu.exit != vmt.SENTINEL:
            raise RuntimeError("main+%X did not return" % target)
        if target == 0x2DDF90:
            x = f32(angle + emu.xmm_low(0))            # addss, then the wrap
            angle = f32((x + math.pi) % (2 * math.pi) - math.pi)
        else:
            angle = emu.xmm_low(0)
        out.append(angle)
    return out


def check_steer(img, hdr):
    """Both turn helpers through their stubs, tick after tick, against stock
    at every stock tick. 2DDF90's step is the clamp of the angle to the point
    by the limit: while the limit holds it back each tick gains limit/N, and
    on the tick it reaches the point it stops there, as stock's does: within
    2e-4 rad. 2DA570's is clamp((goal - cur) * k, +-limit): the clamped
    stretch gains limit/N a tick, the proportional one keeps (1 - k)^(1/N) of
    the gap a tick, (1 - k) a stock tick. Only the stock tick in which the
    clamp lets go differs, by less than limit/N of the stock step, and the
    difference then shrinks with the gap: within 0.3 x limit of stock at every
    stock tick, where the unfixed approach runs 4x (2x) ahead."""
    pe_imports = pe_import_names()
    problems, runs, report = [], 0, []
    worst = 0.0
    for goal, limit, start in ((2.5, 0.2618, 0.0), (-3.0, 0.0873, 3.0), (-2.0, 0.1047, 1.0),
                               (2.9, 0.0349, -2.9)):
        stock = run_steer(img, hdr, None, 0x2DDF90, (goal, limit), start, 40, pe_imports)
        for n in (2, 4):
            got = run_steer(img, hdr, n, 0x2DDF90, (goal, limit), start, 40 * n, pe_imports)
            runs += 1
            for j in range(1, 40):
                d = abs(got[j * n - 1] - stock[j - 1])
                d = min(d, abs(d - 2 * math.pi))
                worst = max(worst, d)
                if d > 2e-4:
                    problems.append("2DDF90 to %g limit %g at N=%d, stock tick %d: %r, stock %r"
                                    % (goal, limit, n, j, got[j * n - 1], stock[j - 1]))
                    break
    report.append("steer: 2DDF90 through its stub, 4 cases, the heading within %.1e rad of "
                  "stock's at every stock tick" % worst)
    worst_rel, worst_unfixed = 0.0, float("inf")
    for goal, k, limit, start in ((2.5, 0.2, 0.0698, 0.0), (-2.0, 0.05, 0.1047, 1.5),
                                  (1.0, 0.3, 0.2793, -1.0), (0.5, 0.2, 0.0035, 0.0),
                                  (0.3, 0.08, 1.0, 0.0)):
        stock = run_steer(img, hdr, None, 0x2DA570, (goal, k, limit), start, 60, pe_imports)
        for n in (2, 4):
            got = run_steer(img, hdr, n, 0x2DA570, (goal, k, limit), start, 60 * n, pe_imports)
            raw = run_steer(img, hdr, n, 0x2DA570, (goal, k, limit), start, 60 * n, pe_imports,
                            fixed=False)
            runs += 1
            dev = max(abs(got[j * n - 1] - stock[j - 1]) for j in range(1, 60))
            off = max(abs(raw[j * n - 1] - stock[j - 1]) for j in range(1, 60))
            worst_rel = max(worst_rel, dev / limit)
            worst_unfixed = min(worst_unfixed, off / max(dev, 1e-9))
            if dev > 0.3 * limit:
                problems.append("2DA570 to %g k %g limit %g at N=%d: %.4f rad from stock (limit "
                                "%g)" % (goal, k, limit, n, dev, limit))
            if off < 3 * dev:
                problems.append("2DA570 to %g k %g limit %g at N=%d: unfixed is not 3x further "
                                "from stock than fixed" % (goal, k, limit, n))
    report.append("steer: 2DA570 through its stub, 5 cases, within %.3f of a limit of stock's at "
                  "every stock tick; unfixed at least %.0fx further" % (worst_rel, worst_unfixed))
    return problems, runs, report


# ---------------------------------------------------------------------------
# the swing step's physics, modelled
# ---------------------------------------------------------------------------

def swing_model(ticks_per_s, ts, s, fixed, f, wind=0.0, seconds=3.0):
    """1BA350's recurrence in 2D: anchor at 0, bob at length L; v is a per-tick
    displacement. `fixed` applies this family's three factors (gravity s,
    wind s^2, damping f^s); the port's own ts on gravity is always there.
    Returns the bob's angle at every stock tick (1/30 s)."""
    L, g = 30.0, 0.4
    x, y = L * math.sin(1.0), -L * math.cos(1.0)
    vx = vy = 0.0
    out = []
    per = ticks_per_s // 30
    for t in range(int(seconds * ticks_per_s)):
        ox, oy = x, y
        vy -= ts * g * (s if fixed else 1.0)
        vx += wind * (s * s if fixed else 1.0)
        x, y = x + vx, y + vy
        r = math.hypot(x, y)
        x, y = x * L / r, y * L / r
        k = f ** s if fixed else f
        vx, vy = (x - ox) * k, (y - oy) * k
        if (t + 1) % per == 0:
            out.append(math.atan2(x, -y))
    return out


def check_swing():
    """The same pendulum at 30, and at 120 and 60 fixed and unfixed, compared
    at the same real times. It starts 1 rad out. The fixed one must stay
    within 0.08 rad of stock and the unfixed one must be at least 3x further.

    The fixed one is not exact: stock's coarse step damps each tick's gravity
    impulse in the same tick (v = f * (v - g)), so its effective gravity is
    g*f a stock tick, where the finer steps give about g*f^(s/2). A lightly
    damped bone (f = 0.95) then sways ~1.3% faster than stock at 120, which
    shows as 0.07 rad of phase after two swings; at the default f = 0.85 the
    swing is gone within a second and the gap is 0.03 rad. Matching it would
    need a gravity factor that depends on each bone's f."""
    problems, report = [], []
    for f, wind in ((0.95, 0.0), (0.85, 0.0), (0.85, 0.05)):
        stock = swing_model(30, 1.0, 1.0, True, f, wind)
        worst = {}
        for name, args in (("fixed 120", (120, 0.25, 0.25, True)),
                           ("fixed 60", (60, 0.5, 0.5, True)),
                           ("unfixed 120", (120, 0.25, 0.25, False)),
                           ("unfixed 60", (60, 0.5, 0.5, False))):
            got = swing_model(*args, f, wind)
            worst[name] = max(abs(a - b) for a, b in zip(stock, got))
        for name in ("fixed 120", "fixed 60"):
            if worst[name] > 0.08:
                problems.append("swing model f=%.2f wind=%.2f %s: %.3f rad from stock"
                                % (f, wind, name, worst[name]))
        for fps in ("120", "60"):
            if worst["unfixed " + fps] < 3 * worst["fixed " + fps]:
                problems.append("swing model f=%.2f wind=%.2f: unfixed %s is not 3x further "
                                "from stock than fixed" % (f, wind, fps))
        report.append("swing model f=%.2f wind %.2f: worst angle vs stock over 3 s: fixed 120 %.3f"
                      " rad, fixed 60 %.3f; unfixed 120 %.3f, unfixed 60 %.3f"
                      % (f, wind, worst["fixed 120"], worst["fixed 60"], worst["unfixed 120"],
                         worst["unfixed 60"]))
    return problems, report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--states", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--only-window", type=lambda s: int(s, 16), action="append", default=None,
                    help="verify only these windows; repeat for a focused batch")
    ap.add_argument("--only-call", type=lambda s: int(s, 16), action="append", default=None,
                    help="verify only these calls; repeat for a focused batch")
    ap.add_argument("--break", dest="broken",
                    choices=("scale", "root", "gate", "literal", "mask2", "smode", "intn"))
    args = ap.parse_args()
    hdr = parse_header()
    if args.only_window:
        missing = set(args.only_window) - {w[0] for w in hdr["windows"]}
        if missing:
            sys.exit("unknown window(s): " + ", ".join("%X" % w for w in sorted(missing)))
    if args.only_call:
        missing = set(args.only_call) - {c[0] for c in hdr["calls"]}
        if missing:
            sys.exit("unknown call(s): " + ", ".join("%X" % c for c in sorted(missing)))
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    if hashlib.sha1(raw).hexdigest() != hdr["sha"]:
        sys.exit("main.dll is not the binary the header describes")
    img = bytearray(pefile.PE(data=raw, fast_load=True).get_memory_mapped_image())
    problems = []

    # 1. the DLL's own install, against the header relocated independently
    work = tempfile.mkdtemp(prefix="okami_world_anims_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiWorldAnimSelfTest
    fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    print("DLL self-test (rc %d): %s" % (rc, report.strip().splitlines()[-1]))
    if rc:
        print(report)
        problems.append("DLL self-test failed")
    else:
        vals = dict(ln.split(None, 1) for ln in report.splitlines() if len(ln.split()) == 2)
        main_base, pool_base = int(vals["main"], 16), int(vals["pool"], 16)
        installed = open(os.path.join(work, "pool.bin"), "rb").read()
        want = relocated_pool(hdr, main_base, pool_base)
        co = hdr["code_off"]
        if installed[co:] != bytes(want[co:]):
            problems.append("installed stub code differs from the independently relocated header")
        for g in range(hdr["groups"]):
            if installed[hdr["stride"] * g] != 0 or \
                    struct.unpack_from("<f", installed, hdr["stride"] * g + 4)[0] != 1.0:
                problems.append("installed pool group %d is not at N = 1 after the self-test" % g)
        if struct.unpack_from("<f", installed, hdr["zero"])[0] != 0.0:
            problems.append("installed zero constant is not 0.0")
        patched = open(os.path.join(work, "patched.bin"), "rb").read()
        expect = b"".join(b for _rva, b in patched_bytes(hdr, main_base, pool_base))
        if patched != expect:
            problems.append("installed jumps / displacements differ from the header's")
        mode_problems, nmodes = check_modes(os.path.join(work, "modes.csv"), hdr, img,
                                            args.broken)
        problems += mode_problems
        print("1. install: pool, %d jumps, %d retargets, %d calls and %d control combinations "
              "checked" % (len(hdr["windows"]), len(hdr["literals"]), len(hdr["calls"]), nmodes))
        print("   " + "\n   ".join(ln for ln in report.splitlines()[2:-1]))

    # 2. every window against the original with only the documented change
    rnd = random.Random(args.seed)
    im = bytearray(img)
    for rva, b in patched_bytes(hdr, BASE, POOL):
        if any(rva == w[0] for w in hdr["windows"]):
            im[rva:rva + len(b)] = b
    broken_pool = args.broken if args.broken in ("scale", "root", "gate", "mask2", "smode",
                                                 "intn") else None
    wprob, wruns = check_windows(img, im,
                                 lambda n, sm=2: pool_data(hdr, img, n, broken_pool, sm), hdr,
                                 rnd, args.states, args.only_window if args.only_window else
                                 ([] if args.only_call else None))
    problems += wprob
    print("2. windows: %d runs (%d windows x N=1,2,4 x %d states), %d problems"
          % (wruns, len(set(args.only_window)) if args.only_window else
             (0 if args.only_call else len(hdr["windows"])),
             args.states, len(wprob)))

    if args.only_call:
        imc = bytearray(img)
        for rva, b in patched_bytes(hdr, BASE, POOL):
            imc[rva:rva + len(b)] = b
        cprob, cruns = check_calls(img, imc,
                                  lambda n, sm=2: pool_data(hdr, img, n, broken_pool, sm),
                                  hdr, rnd, args.states, set(args.only_call))
        problems += cprob
        print("   calls: %d runs (%d calls x N=1,2,4 x %d states), %d problems" %
              (cruns, len(set(args.only_call)), args.states, len(cprob)))

    if args.only_window or args.only_call:
        for p in problems[:25]:
            print("   PROBLEM " + p)
        print("\n%s" % ("FAILED: %d problems" % len(problems) if problems else
                         "focused checks passed"))
        return 1 if problems else 0

    capprob, capruns = check_player_speed_cap(
        img, hdr, lambda n: pool_data(hdr, img, n, broken_pool))
    problems += capprob
    print("   player speed cap: %d compound runs, %d problems" %
          (capruns, len(capprob)))

    # 2b. every retargeted call against the original call
    imc = bytearray(img)
    for rva, b in patched_bytes(hdr, BASE, POOL):
        imc[rva:rva + len(b)] = b
    cprob, cruns = check_calls(img, imc, lambda n, sm=2: pool_data(hdr, img, n, broken_pool, sm),
                               hdr, rnd, max(4, args.states // 4))
    problems += cprob
    print("   calls: %d runs (%d calls x N=1,2,4 x %d states), %d problems"
          % (cruns, len(hdr["calls"]), max(4, args.states // 4), len(cprob)))

    # 3. the real functions, tick after tick, against stock
    sprob, sruns, srep = check_sky(img, hdr)
    bprob, bruns, brep = check_bob(img, hdr)
    pprob, pruns, prep = check_particle(img, hdr)
    tprob, truns, trep = check_turn(img, hdr)
    gprob, gruns, grep = check_steer(img, hdr)
    eprob, eruns, erep = check_piece(img, hdr)
    problems += sprob + bprob + pprob + tprob + gprob + eprob
    print("3. trajectories: %d runs, %d problems" % (
        sruns + bruns + pruns + truns + gruns + eruns,
        len(sprob) + len(bprob) + len(pprob) + len(tprob) + len(gprob) + len(eprob)))
    for ln in srep + brep + prep + erep + trep + grep:
        print("   " + ln)

    # 4. the swing physics, modelled
    mprob, mrep = check_swing()
    problems += mprob
    print("4. swing model: %d problems" % len(mprob))
    for ln in mrep:
        print("   " + ln)

    # 5. F6: the port's mode quantities and the menus' repeat in real time
    fprob, fruns, frep = check_f6(img, hdr)
    lprob, lruns, lrep = check_flag(img, hdr)
    fprob += lprob
    fruns += lruns
    frep += lrep
    problems += fprob
    print("5. F6 and the flag group in real time: %d runs, %d problems" % (fruns, len(fprob)))
    for ln in frep:
        print("   " + ln)

    for p in problems[:25]:
        print("   PROBLEM " + p)
    print("\n%s" % ("FAILED: %d problems" % len(problems) if problems else "all checks passed"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
