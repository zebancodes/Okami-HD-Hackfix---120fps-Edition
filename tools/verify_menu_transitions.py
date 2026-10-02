#!/usr/bin/env python3
"""Verify M2's menu transitions (src/menu_transitions.h) against the game's code.

Three layers, none of which uses the generator's encoders as an oracle:

1. Bytes. The DLL's own installer (OkamiMenuTransitionSelfTest, on a mapped
   main.dll) must produce the pool and the patched bytes that an independent
   relocation of the header gives, and its per-tick update must hold, for
   every fps / context / key / config combination, mask = N-1, s = 1/N and
   each literal slot at K*s (a step) or K**s (a factor), with N = fps over the
   stock context's rate while the family is on and 1 otherwise.

2. Windows. Every relocated window runs under Unicorn, from random machine
   states and every tick residue, at N = 1, 2 and 4, against the ORIGINAL
   instructions with only the documented change applied:
     src    the step operand is multiplied by s for that one instruction;
     dst    the copied step is multiplied by s after the copy;
     count  the counting instruction does not run on ticks with fc & mask;
     gatefn the function returns at once on those ticks.
   Registers, flags, XMM registers (except the proven-dead temporary), every
   byte of game memory written and the exit address must agree. At N = 1 the
   reference is the original code itself.

3. Trajectories. The transition's slide, glide, fade and fade tail and the
   pause menu's drop run tick after tick: the original code at stock 30, and
   the patched image (this family plus the phase-step and decay retargets the
   same functions already carry) at N = 4 and 2, from every starting residue.
   Each phase must last its stock number of stock ticks (within one), and the
   quantities it moves must track stock at stock-tick boundaries: exactly for
   the drop, which runs whole on stock ticks.

    .venv/Scripts/python tools/verify_menu_transitions.py
    --break scale|gate|literal|count corrupts one installed artifact and must fail.
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
from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_HOOK_CODE,
                     UC_HOOK_MEM_WRITE, UC_HOOK_MEM_UNMAPPED)
from unicorn import x86_const as U

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.dirname(HERE)
HDR = os.path.join(ROOT, "src", "menu_transitions.h")
SRC = os.path.join(ROOT, "src")

BASE = 0x180000000
POOL = BASE - 0x4000000
AUX = POOL + 0x100000          # the phase-step / decay retargets' private slots
OBJ = 0x10000000               # the objects the trajectories drive
TRAP = 0x7E0000000000          # imported functions, emulated in Python
SENTINEL = TRAP + 0x800        # return address of every call a test makes
STACK_TOP = 0x7FF000000000
STACK_SIZE = 0x40000
PAGE = 0x1000
FC = 0xB6AC20
FLAG_MASK = 0xCD5
MASK_OFF, SCALE_OFF = 0, 4
GPR_NAMES = "rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
GPRS = [getattr(U, "UC_X86_REG_" + n.upper()) for n in GPR_NAMES]
XMMS = [getattr(U, "UC_X86_REG_XMM%d" % i) for i in range(16)]
KIND = {0: "lin", 1: "exp", 2: "src", 3: "dst", 4: "count", 5: "gatefn"}


def f32(x):
    try:
        return struct.unpack("<f", struct.pack("<f", x))[0]
    except OverflowError:
        # SSE scalar arithmetic overflows to signed infinity; Python's
        # struct.pack rejects an out-of-range float instead.
        return math.copysign(math.inf, x)


def fbits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


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
                for r in re.findall(r"\{\{([^{}]+)\}\}", block("kMenuLiteralOrig"))]
    return dict(sha=re.search(r'MENU_TRANSITIONS_MAIN_SHA1\s+"([0-9a-f]+)"', text).group(1),
                code_off=const("kMenuCodeOffset"), pool_size=const("kMenuPoolSize"),
                code=raw("kMenuCode"), orig=raw("kMenuOrig"), lit_orig=lit_orig,
                fixups=rows("kMenuFixups"), windows=rows("kMenuWindows"),
                sites=rows("kMenuSites"), literals=rows("kMenuLiterals"))


def table_sites(name, struct_name):
    """(rva, constRva, orig 8 bytes) of a phase_steps.h / decay_factors.h table."""
    text = open(os.path.join(SRC, name), encoding="utf-8").read()
    out = []
    for m in re.finditer(r"\{0x([0-9A-F]+), 0x([0-9A-F]+), \{([^}]*)\}\}", text):
        out.append((int(m.group(1), 16), int(m.group(2), 16),
                    bytes(int(b, 16) for b in m.group(3).split(","))))
    return out


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
    """[(rva, bytes)]: each window's jump and NOP padding, each literal's
    instruction with its displacement pointed at its slot."""
    out = []
    for rva, stub, _o, n in hdr["windows"]:
        rel = pool_base + stub - (main_base + rva + 5)
        out.append((rva, b"\xE9" + struct.pack("<i", rel) + b"\x90" * (n - 5)))
    for (rva, _c, slot, _k), orig in zip(hdr["literals"], hdr["lit_orig"]):
        rel = pool_base + slot - (main_base + rva + 8)
        out.append((rva, orig[:4] + struct.pack("<i", rel)))
    return out


def want_n(fps, mode, enabled, muted, shadow, hook, complete):
    if not (enabled and not muted and shadow and hook and complete and fps != 30 and mode in (1, 2)):
        return 1
    return fps // (60 if mode == 1 else 30)


def slot_value(img, const_rva, kind, n):
    k = struct.unpack_from("<f", img, const_rva)[0]
    if n == 1:
        return k
    s = f32(1.0 / n)
    return f32(k * s) if kind == 0 else f32(math.pow(k, s))


def check_modes(path, hdr, img):
    problems = []
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        args = [int(r[k]) for k in ("fps", "mode", "enabled", "muted", "shadow", "hook", "complete")]
        n = want_n(*args)
        if int(r["mask"]) != n - 1 or float(r["scale"]) != f32(1.0 / n):
            problems.append("mode row %s: mask %s scale %s, want N=%d" % (args, r["mask"], r["scale"], n))
            continue
        for rva, const, _slot, kind in hdr["literals"]:
            got, want = f32(float(r["slot%X" % rva])), slot_value(img, const, kind, n)
            # powf may round differently from Python's pow by one ulp
            if abs(fbits(got) - fbits(want)) > (1 if kind == 1 else 0):
                problems.append("slot %X at N=%d is %r, want %r" % (rva, n, got, want))
    return problems, len(rows)


# ---------------------------------------------------------------------------
# emulation
# ---------------------------------------------------------------------------

class _Uc:
    """The engine as an Emu's users see it: a host read or write of an image
    page maps that page first, as the emulated code's own accesses do through
    the unmapped hook. Everything else is the engine's own."""

    def __init__(self, uc, emu):
        self._uc, self._emu = uc, emu
        for name in ("reg_read", "reg_write", "emu_start", "emu_stop", "hook_add", "hook_del",
                     "ctl_flush_tb", "mem_map", "mem_unmap", "mem_protect"):
            setattr(self, name, getattr(uc, name))  # the hot ones, without a lookup

    def mem_read(self, addr, size):
        self._emu.image_in(addr, size)
        return self._uc.mem_read(addr, size)

    def mem_write(self, addr, data):
        self._emu.image_in(addr, len(data))
        return self._uc.mem_write(addr, data)

    def __getattr__(self, name):
        return getattr(self._uc, name)


class Emu:
    """One address space: the image (original or patched), the pool, the
    auxiliary slots, a stack, demand-filled pages for everything else.

    The image is mapped a page at a time, when something first touches it.
    A window runs a few hundred bytes of the 17 MB image, and copying all of
    it into every new engine was 900 of the world pass's 1 450 s (2026-09-25);
    a page reads the same whenever it is mapped, so nothing else changes."""

    def __init__(self, img, pool=None, aux=None, seed=0):
        self.mu = mu = _Uc(Uc(UC_ARCH_X86, UC_MODE_64), self)
        size = (len(img) + PAGE - 1) & ~(PAGE - 1)
        self.img, self.image, self.imaged = img, (BASE, BASE + size), set()
        self.fixed = []
        if pool is not None:
            psize = (len(pool) + PAGE - 1) & ~(PAGE - 1)
            mu.mem_map(POOL, psize, UC_PROT_ALL)
            mu.mem_write(POOL, bytes(pool))
            self.fixed.append((POOL, POOL + psize))
        mu.mem_map(AUX, PAGE, UC_PROT_ALL)
        if aux:
            mu.mem_write(AUX, bytes(aux))
        mu.mem_map(TRAP, PAGE, UC_PROT_ALL)
        mu.mem_write(TRAP, b"\xCC" * PAGE)
        mu.mem_map(STACK_TOP - STACK_SIZE, STACK_SIZE + PAGE, UC_PROT_ALL)
        self.fixed += [(AUX, AUX + PAGE), (TRAP, TRAP + PAGE),
                       (STACK_TOP - STACK_SIZE, STACK_TOP + PAGE)]
        self.seed = seed
        self.demand = set()
        self.written = set()
        self.traps = {}
        self.stop_outside = None
        self.pre = {}            # address -> callable(emu) before it runs
        self.exit = None
        mu.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)
        mu.hook_add(UC_HOOK_MEM_WRITE, self._write)
        mu.hook_add(UC_HOOK_CODE, self._code)

    def _fill(self, page):
        rnd = random.Random((page * 0x9E3779B97F4A7C15 ^ self.seed) & 0xFFFFFFFFFFFFFFFF)
        return bytes(rnd.randbytes(PAGE))

    def map_page(self, page):
        if page in self.demand or page in self.imaged or \
                any(a <= page < b for a, b in self.fixed):
            return True
        try:
            self.mu.mem_map(page, PAGE, UC_PROT_ALL)
        except UcError:
            return False
        if self.image[0] <= page < self.image[1]:
            off = page - BASE
            self.mu._uc.mem_write(page, bytes(self.img[off:off + PAGE]))
            self.imaged.add(page)
            return True
        self.mu._uc.mem_write(page, self._fill(page))
        self.demand.add(page)
        return True

    def image_in(self, addr, size):
        """Maps the image's pages in [addr, addr + size), for a host access."""
        lo, hi = self.image
        if addr >= hi or addr + size <= lo:
            return
        for p in range(max(addr, lo) & ~(PAGE - 1), min(addr + size, hi), PAGE):
            if p not in self.imaged:
                self.map_page(p)

    def _unmapped(self, uc, access, address, size, value, data):
        if address >= 0x800000000000:
            return False
        ok = True
        for p in (address & ~(PAGE - 1), (address + size - 1) & ~(PAGE - 1)):
            ok &= self.map_page(p)
        return ok

    def _write(self, uc, access, address, size, value, data):
        for i in range(size):
            self.written.add(address + i)

    def _code(self, uc, address, size, data):
        if address in self.traps:
            self.traps[address](self)
            rsp = uc.reg_read(U.UC_X86_REG_RSP)
            uc.reg_write(U.UC_X86_REG_RIP, struct.unpack("<Q", uc.mem_read(rsp, 8))[0])
            uc.reg_write(U.UC_X86_REG_RSP, rsp + 8)
            return
        # a reference hook first: a restore can sit on the window's last byte
        f = self.pre.get(address)
        if f:
            f(self)
            if uc.reg_read(U.UC_X86_REG_RIP) != address:
                return  # it redirected (a skip or a return): run from there
        if address == SENTINEL:
            self.exit = address
            uc.emu_stop()
            return
        if self.stop_outside is not None:
            lo, hi = self.stop_outside
            in_pool = POOL <= address < POOL + 0x100000
            if not (lo <= address < hi) and not in_pool:
                self.exit = address
                uc.emu_stop()
                return

    def reg(self, name):
        return self.mu.reg_read(getattr(U, "UC_X86_REG_" + name.upper()))

    def set_reg(self, name, v):
        self.mu.reg_write(getattr(U, "UC_X86_REG_" + name.upper()), v)

    def xmm_low(self, i):
        return struct.unpack("<f", struct.pack("<I", self.mu.reg_read(XMMS[i]) & 0xFFFFFFFF))[0]

    def set_xmm_low(self, i, v):
        x = self.mu.reg_read(XMMS[i])
        self.mu.reg_write(XMMS[i], (x & ~0xFFFFFFFF) | fbits(v))

    def rf(self, addr):
        return struct.unpack("<f", self.mu.mem_read(addr, 4))[0]

    def wf(self, addr, v):
        self.mu.mem_write(addr, struct.pack("<f", v))

    def call(self, fn, rcx, limit=200000):
        """Call main+fn(rcx) and run to its return."""
        rsp = STACK_TOP - 0x2000
        self.mu.mem_write(rsp, struct.pack("<Q", SENTINEL))
        self.set_reg("rsp", rsp)
        self.set_reg("rcx", rcx)
        self.exit = None
        self.stop_outside = None
        self.mu.emu_start(BASE + fn, 0, count=limit)
        if self.exit != SENTINEL:
            raise RuntimeError("main+%X did not return (rip %X)" % (fn, self.reg("rip")))


def mem_ea(emu, ins, op):
    """The operand's address, from a hook at the instruction (a rip operand is
    relative to the next instruction; ins may be decoded at its rva)."""
    m = op.mem
    ea = m.disp
    if m.base == CX.X86_REG_RIP:
        ea += emu.reg("rip") + ins.size
    elif m.base:
        ea += emu.reg(ins.reg_name(m.base))
    if m.index:
        ea += emu.reg(ins.reg_name(m.index)) * m.scale
    return ea & 0xFFFFFFFFFFFFFFFF


def random_state(rnd):
    st = {n: rnd.getrandbits(64) for n in GPR_NAMES}
    # memory operands need pointer-shaped bases, clear of image, pool and stack
    for n in GPR_NAMES:
        if rnd.random() < 0.7:
            st[n] = (0x200000000 + rnd.randrange(0, 1 << 32)) & ~7
    st["rsp"] = STACK_TOP - 0x1000 - 8
    st["flags"] = rnd.getrandbits(12) & FLAG_MASK | 0x2
    xm = []
    for _ in range(16):
        lanes = [fbits(rnd.uniform(-1000, 1000)) for _ in range(4)]
        xm.append(sum(v << (32 * i) for i, v in enumerate(lanes)))
    st["xmm"] = xm
    st["mem_seed"] = rnd.getrandbits(32)
    return st


def load_state(emu, st, fc):
    for n, r in zip(GPR_NAMES, GPRS):
        emu.mu.reg_write(r, st[n])
    emu.mu.reg_write(U.UC_X86_REG_EFLAGS, st["flags"])
    for i, v in enumerate(st["xmm"]):
        emu.mu.reg_write(XMMS[i], v)
    emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
    emu.mu.mem_write(STACK_TOP - 0x1000 - 8, struct.pack("<Q", SENTINEL))


def snapshot(emu, skip_xmm, skip_flags):
    out = {n: emu.mu.reg_read(r) for n, r in zip(GPR_NAMES, GPRS)}
    if not skip_flags:
        out["flags"] = emu.mu.reg_read(U.UC_X86_REG_EFLAGS) & FLAG_MASK
    for i in range(16):
        if i not in skip_xmm:
            out["xmm%d" % i] = emu.mu.reg_read(XMMS[i])
    out["exit"] = emu.exit
    return out


def game_writes(emu):
    """Bytes written outside the pool, less the scratch below the stack
    pointer the window leaves: a stub's pushfq / push rax, popped again, is
    dead there (nothing may rely on memory below rsp)."""
    rsp = emu.reg("rsp")
    return {a for a in emu.written
            if not (POOL <= a < POOL + 0x100000) and not (rsp - 0x100 <= a < rsp)}


def check_windows(img, patched_img, pool_for, hdr, rnd, states, broken):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    problems, runs = [], 0
    sites_by_window = {}
    for site, kind, win, temp, _flags, _counter in hdr["sites"]:
        sites_by_window.setdefault(win, []).append((site, kind, temp))
    for wi, (lo, _stub, _o, n_bytes) in enumerate(hdr["windows"]):
        hi = lo + n_bytes
        insns = {i.address: i for i in md.disasm(bytes(img[lo:hi]), lo)}
        sites = sites_by_window[wi]
        skip_xmm = {t for _s, k, t in sites if KIND[k] == "src"}
        gate_fn = any(KIND[k] == "gatefn" for _s, k, _t in sites)
        for n in (1, 2, 4):
            pool = pool_for(n)
            s = f32(1.0 / n)
            for k in range(states):
                st = random_state(rnd)
                fc = rnd.getrandbits(20) * 4 + (k % 4)
                stock = (fc & (n - 1)) == 0
                results = []
                for variant in ("orig", "patched"):
                    emu = Emu(img if variant == "orig" else patched_img,
                              pool if variant == "patched" else None, seed=st["mem_seed"])
                    load_state(emu, st, fc)
                    if variant == "orig":
                        for site, kind, _t in sites:
                            ins = insns[site]
                            kname = KIND[kind]
                            if kname == "src" and n > 1:
                                op = ins.operands[1]
                                if op.type == CX.X86_OP_MEM:
                                    def pre(e, ins=ins, op=op):
                                        ea = mem_ea(e, ins, op)
                                        e.map_page(ea & ~(PAGE - 1))
                                        e._saved = (ea, bytes(e.mu.mem_read(ea, 4)))
                                        v = struct.unpack("<f", e._saved[1])[0]
                                        e.mu.mem_write(ea, struct.pack("<f", f32(v * s)))

                                    def post(e):
                                        ea, old = e._saved
                                        e.mu.mem_write(ea, old)
                                        for b in range(4):
                                            e.written.discard(ea + b)
                                    emu.pre[site] = pre
                                    emu.pre[site + ins.size] = post
                                else:
                                    src = int(ins.reg_name(op.reg)[3:])

                                    def pre(e, src=src):
                                        e._saved = e.mu.reg_read(XMMS[src])
                                        e.set_xmm_low(src, f32(e.xmm_low(src) * s))

                                    def post(e, src=src):
                                        e.mu.reg_write(XMMS[src], e._saved)
                                    emu.pre[site] = pre
                                    emu.pre[site + ins.size] = post
                            elif kname == "dst" and n > 1:
                                d = int(ins.reg_name(ins.operands[0].reg)[3:])

                                def post(e, d=d):
                                    e.set_xmm_low(d, f32(e.xmm_low(d) * s))
                                emu.pre[site + ins.size] = post
                            elif kname == "count" and not stock:
                                def skip(e, ins=ins):
                                    e.set_reg("rip", BASE + ins.address + ins.size)
                                emu.pre[site] = skip
                            elif kname == "gatefn" and not stock:
                                def ret(e):
                                    rsp = e.reg("rsp")
                                    e.set_reg("rip", struct.unpack("<Q", e.mu.mem_read(rsp, 8))[0])
                                    e.set_reg("rsp", rsp + 8)
                                emu.pre[site] = ret
                    emu.stop_outside = (BASE + lo, BASE + hi)
                    # the image runs at BASE; the pre-hooks are keyed by rva
                    emu.pre = {BASE + a: f for a, f in emu.pre.items()}
                    try:
                        emu.mu.emu_start(BASE + lo, 0, count=500)
                    except UcError as e:
                        emu.exit = "fault %s" % e
                    results.append((snapshot(emu, skip_xmm, gate_fn), emu))
                (a, ea), (b, eb) = results
                runs += 1
                if a != b:
                    diff = [key for key in a if a[key] != b.get(key)]
                    problems.append("window %X N=%d fc&mask=%d: %s differ" % (
                        lo, n, fc & (n - 1), ", ".join(diff[:6])))
                    continue
                wa, wb = game_writes(ea), game_writes(eb)
                if wa != wb:
                    problems.append("window %X N=%d: written addresses differ" % (lo, n))
                    continue
                for addr in sorted(wa):
                    if ea.mu.mem_read(addr, 1) != eb.mu.mem_read(addr, 1):
                        problems.append("window %X N=%d: memory %X differs" % (lo, n, addr))
                        break
    return problems, runs


# ---------------------------------------------------------------------------
# trajectories
# ---------------------------------------------------------------------------

def cvec_traps(img, calls):
    """IAT slot of each `call qword ptr [rip+X]` at the given rvas."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    out = {}
    for a in calls:
        ins = next(md.disasm(bytes(img[a:a + 16]), a))
        op = ins.operands[0]
        assert ins.mnemonic == "call" and op.mem.base == CX.X86_REG_RIP, hex(a)
        out[a] = a + ins.size + op.mem.disp
    return out


def copy16(e):
    e.mu.mem_write(e.reg("rcx"), bytes(e.mu.mem_read(e.reg("rdx"), 16)))
    e.set_reg("rax", e.reg("rcx"))


# the imports the slide and glide call: cVec(const cVec&) and operator=
CVEC_CALLS = {0x439A68: copy16, 0x439A8E: copy16, 0x4397C8: copy16, 0x4397EE: copy16}
TRANSITION_FNS = (0x439A50, 0x4397B0, 0x439AD0)


def build_image(img, hdr, pool_base, with_family, n, phase_sites, decay_sites, break_literal):
    """The image as the game runs it: the family's jumps and retargets, and the
    phase-step / decay retargets inside the transition, pointed at AUX slots."""
    im = bytearray(img)
    aux = bytearray(PAGE)
    if with_family:
        for rva, b in patched_bytes(hdr, BASE, pool_base):
            im[rva:rva + len(b)] = b
        slot = 0
        s = f32(1.0 / n)
        for table, sites in (("lin", phase_sites), ("exp", decay_sites)):
            for rva, const, orig in sites:
                if not any(f <= rva < f + 0x200 for f in TRANSITION_FNS):
                    continue
                assert bytes(img[rva:rva + 8]) == orig
                k = struct.unpack_from("<f", img, const)[0]
                v = k if n == 1 else f32(k * s) if table == "lin" else f32(math.pow(k, s))
                struct.pack_into("<f", aux, slot, v)
                struct.pack_into("<i", im, rva + 4, AUX + slot - (BASE + rva + 8))
                slot += 4
    return im, aux


def pool_data(hdr, img, n, broken=None):
    pool = relocated_pool(hdr, BASE, POOL)
    s = f32(1.0 / n)
    pool[MASK_OFF] = (n - 1) if broken != "count" else 0
    struct.pack_into("<f", pool, SCALE_OFF, s if broken != "scale" else 1.0)
    for rva, const, slot, kind in hdr["literals"]:
        v = slot_value(img, const, kind, n)
        if broken == "literal" and rva == 0x4397FC:
            v = struct.unpack_from("<f", img, const)[0]
        struct.pack_into("<f", pool, slot, v)
    if broken == "gate":
        # the pause drop's stub: `je body` becomes `jne body`
        stub = next(st for (rva, st, _o, _n) in hdr["windows"] if rva == 0x415B30)
        code = pool[stub:stub + 0x60]
        k = code.index(b"\x58\x74") + 1
        pool[stub + k] = 0x75
    return pool


def run_phase(img, hdr, n, residue, phase, start, phase_sites, decay_sites, broken, cap=4000):
    """Ticks of one phase; returns the per-tick samples."""
    im, aux = build_image(img, hdr, POOL, n is not None, n or 1, phase_sites, decay_sites,
                          broken == "literal")
    pool = pool_data(hdr, img, n, broken) if n is not None else None
    emu = Emu(im, pool, aux)
    traps = cvec_traps(img, CVEC_CALLS)
    for i, (call, slot) in enumerate(traps.items()):
        addr = TRAP + 0x10 * i
        emu.mu.mem_write(BASE + slot, struct.pack("<Q", addr))
        emu.traps[addr] = CVEC_CALLS[call]
    emu.map_page(OBJ)
    for p in range(OBJ, OBJ + 0x6000, PAGE):
        emu.map_page(p)
        emu.mu.mem_write(p, b"\0" * PAGE)
    T, M, P, PM = OBJ, OBJ + 0x1000, OBJ + 0x3000, OBJ + 0x4000
    emu.mu.mem_write(T, struct.pack("<Q", M))
    emu.mu.mem_write(M + 0xA8, struct.pack("<Q", P))
    start(emu, T, M, P, PM)
    fc = 0x1000 + residue
    samples = []
    fn, obj, state_at, done = PHASES[phase]
    for tick in range(cap):
        emu.mu.mem_write(BASE + FC, struct.pack("<I", fc))
        emu.call(fn, obj(T, PM))
        samples.append(SAMPLE[phase](emu, T, M, P, PM))
        fc += 1
        if emu.mu.mem_read(state_at(T, PM), 1)[0] == done:
            return samples
    raise RuntimeError("%s did not end in %d ticks" % (phase, cap))


def start_slide(x0):
    def f(e, T, M, P, PM):
        e.wf(P, x0)
        e.wf(T + 0x18, -4.25)
        e.mu.mem_write(T + 0x22, b"\1")
        e.mu.mem_write(T + 0x29, b"\1")
    return f


def start_glide(e, T, M, P, PM):
    e.wf(P, 25.0)
    e.wf(T + 0x18, -4.25)
    e.mu.mem_write(T + 0x1C, struct.pack("<I", 0xC26AF598))
    e.wf(T + 0x8, 680.0)
    e.wf(M + 0xF54, 1.3)
    e.mu.mem_write(T + 0x22, b"\1")
    e.mu.mem_write(T + 0x29, b"\2")


def start_fade(e, T, M, P, PM):
    e.wf(T + 0x10, 1.0)
    e.mu.mem_write(T + 0x29, b"\1")


def start_tail(e, T, M, P, PM):
    e.wf(T + 0xC, 0.0)
    e.mu.mem_write(T + 0x29, b"\3")


def start_drop(e, T, M, P, PM):
    e.wf(PM + 0x8C, -514.0)
    e.wf(PM + 0x90, 0.0)
    e.mu.mem_write(PM + 0x99, b"\1")


PHASES = {  # function, its this, the state byte, the state it ends in
    "slide": (0x439A50, lambda T, PM: T, lambda T, PM: T + 0x29, 2),
    "glide": (0x4397B0, lambda T, PM: T, lambda T, PM: T + 0x29, 3),
    "fade": (0x439AD0, lambda T, PM: T, lambda T, PM: T + 0x29, 2),
    "fade tail": (0x439AD0, lambda T, PM: T, lambda T, PM: T + 0x29, 4),
    "drop": (0x415B30, lambda T, PM: PM, lambda T, PM: PM + 0x99, 2),
}
SAMPLE = {
    "slide": lambda e, T, M, P, PM: (e.rf(P),),
    "glide": lambda e, T, M, P, PM: (e.rf(P), e.rf(T + 8), e.rf(M + 0xF54)),
    "fade": lambda e, T, M, P, PM: (e.rf(T + 0x10),),
    "fade tail": lambda e, T, M, P, PM: (e.rf(T + 0xC),),
    "drop": lambda e, T, M, P, PM: (e.rf(PM + 0x8C), e.rf(PM + 0x90)),
}
# how far a scaled quantity may drift from stock at a stock-tick boundary, as a
# share of the distance it travels over the phase: 0 for the drop, which runs
# whole on stock ticks; the glide integrates a decaying velocity sub-tick by
# sub-tick where stock applies it once a tick
TOLERANCE = {"slide": 1e-5, "glide": 0.06, "fade": 1e-4, "fade tail": 0.25, "drop": 0.0}


def check_trajectories(img, hdr, phase_sites, decay_sites, broken):
    problems, runs, report = [], 0, []
    cases = [("slide", start_slide(x0)) for x0 in (200.0, 431.5, 680.0)] + \
            [("glide", start_glide), ("fade", start_fade), ("fade tail", start_tail),
             ("drop", start_drop)]
    for phase, start in cases:
        stock = run_phase(img, hdr, None, 0, phase, start, phase_sites, decay_sites, broken)
        k0 = len(stock)
        span = [max(abs(stock[-1][i] - stock[0][i]), 1e-6) for i in range(len(stock[0]))]
        worst_d, worst_q = 0, 0.0
        for n in (2, 4):
            for residue in range(n):
                got = run_phase(img, hdr, n, residue, phase, start, phase_sites, decay_sites, broken)
                runs += 1
                # the phase starts on any tick: its first stock tick comes after
                # (n - residue) % n ticks here
                lead = (n - (0x1000 + residue) % n) % n
                ticks = len(got)
                d = ticks / n - k0
                worst_d = max(worst_d, abs(d))
                if abs(d) > 1.0:
                    problems.append("%s at N=%d residue %d: %d ticks = %.2f stock ticks, stock %d"
                                    % (phase, n, residue, ticks, ticks / n, k0))
                    continue
                # compare at stock-tick boundaries while both are running: after
                # j*n ticks for what moves every tick; for the drop, which moves
                # only on stock ticks, after its j-th stock tick
                for j in range(1, min(k0, (ticks - lead) // n)):
                    at = lead + (j - 1) * n if phase == "drop" else j * n - 1
                    a, b = stock[j - 1], got[at]
                    for i in range(len(a)):
                        q = abs(a[i] - b[i]) / span[i]
                        worst_q = max(worst_q, q)
                        if q > TOLERANCE[phase] + 1e-9:
                            problems.append("%s at N=%d residue %d: stock tick %d, value %d is %r, "
                                            "stock %r" % (phase, n, residue, j, i, b[i], a[i]))
                            break
                    else:
                        continue
                    break
        report.append("%-10s stock %3d ticks; at N=2,4 within %.2f stock ticks, worst drift %.4f"
                      " of its travel" % (phase, k0, worst_d, worst_q))
    return problems, runs, report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--states", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--break", dest="broken", choices=("scale", "gate", "literal", "count"))
    args = ap.parse_args()
    hdr = parse_header()
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    if hashlib.sha1(raw).hexdigest() != hdr["sha"]:
        sys.exit("main.dll is not the binary the header describes")
    img = bytearray(pefile.PE(data=raw, fast_load=True).get_memory_mapped_image())
    problems = []

    # 1. the DLL's own install, against the header relocated independently
    work = tempfile.mkdtemp(prefix="okami_menu_transitions_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiMenuTransitionSelfTest
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
        if installed[MASK_OFF] != 0 or struct.unpack_from("<f", installed, SCALE_OFF)[0] != 1.0:
            problems.append("installed pool is not at N = 1 after the self-test")
        patched = open(os.path.join(work, "patched.bin"), "rb").read()
        expect = b"".join(b for _rva, b in patched_bytes(hdr, main_base, pool_base))
        # the literals were dumped whole (8 bytes); the table gives them whole too
        if patched != expect:
            problems.append("installed jumps / displacements differ from the header's")
        mode_problems, nmodes = check_modes(os.path.join(work, "modes.csv"), hdr, img)
        problems += mode_problems
        print("1. install: pool, %d jumps, %d retargets and %d control combinations checked"
              % (len(hdr["windows"]), len(hdr["literals"]), nmodes))
        print("   " + "\n   ".join(ln for ln in report.splitlines()[2:-1]))

    # 2. every window against the original with only the documented change
    rnd = random.Random(args.seed)
    im = bytearray(img)
    for rva, b in patched_bytes(hdr, BASE, POOL):
        if any(rva == w[0] for w in hdr["windows"]):
            im[rva:rva + len(b)] = b
    wprob, wruns = check_windows(img, im, lambda n: pool_data(hdr, img, n, args.broken), hdr,
                                 rnd, args.states, args.broken)
    problems += wprob
    print("2. windows: %d runs (%d windows x N=1,2,4 x %d states), %d problems"
          % (wruns, len(hdr["windows"]), args.states, len(wprob)))

    # 3. whole phases, tick after tick, against stock
    phase_sites = table_sites("phase_steps.h", "PhaseSite")
    decay_sites = table_sites("decay_factors.h", "DecaySite")
    tprob, truns, trep = check_trajectories(img, hdr, phase_sites, decay_sites, args.broken)
    problems += tprob
    print("3. trajectories: %d runs, %d problems" % (truns, len(tprob)))
    for ln in trep:
        print("   " + ln)

    for p in problems[:25]:
        print("   PROBLEM " + p)
    print("\n%s" % ("FAILED: %d problems" % len(problems) if problems else "all checks passed"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
