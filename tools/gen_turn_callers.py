#!/usr/bin/env python3
"""Audit where every caller of the angular approach gets its coefficient.

main+2DA510 is the angular approach every actor and the camera turn with
(dinput8_proxy.cpp, "How everything in the game turns"). FixTurnRate converts
the coefficient k it is passed in xmm2, once, at the function's entry:

    k' = 1 - (1 - k)^ts

That is right for a caller whose k is a per-tick blend at the stock 30 Hz rate,
and wrong for a caller whose k the engine has already compensated. Those read a
growth factor g from the per-mode table at main+7A82C0.. -- the {g^0.5, g}
pairs mode_constants.h rewrites to {g^ts, g} -- and pass g - 1:

    movzx  eax, byte ptr [mode]            ; 1 fast, 2 stock
    dec    eax
    movsxd rcx, eax
    movss  xmm2, [r12 + rcx*4 + 0x7A82C0]  ; r12 = image base
    subss  xmm2, xmm8                      ; 1.0
    call   2DA510

At 120 fps the table already gives 1.1^0.25 - 1 = 0.0241 there and the hook
converted that again, to 0.0061: a quarter of the stock steering. Stock needs
1 - 0.9^0.25 = 0.0260. And g^ts - 1 is only the engine's approximation of the
right coefficient, a poor one for large g (1.9^0.25 - 1 leaves 4.6 times the
stock gap after one stock tick), so leaving these callers out of the conversion
would not be right either.

So the stock coefficient is recovered and converted once. Each such table
read is retargeted at a private {fast, stock} pair, whose fast slot the DLL
keeps at the stock g while the turn hook converts (the caller then passes
g - 1 and the hook makes it 1 - (2 - g)^ts: one stock tick's gap after 1/ts
ticks) and at the real table's current value while it does not (the site then
reads exactly what it did). Any f(g) the caller builds is handled the same way,
because the hook sees f(stock g), the stock coefficient.

Nothing here trusts a list. Every reference to 2DA510 is found by a sweep in
every encoding, and the coefficient of each call is sliced backwards through
the function's control flow graph -- both sides of every branch, through
nonvolatile registers across calls, through stack slots -- to its leaves:

  convert   every leaf is a constant (or MANUAL says the value is kept in stock
            units, and why): the hook's one conversion is right
  table     a leaf is a mode-table entry read at index (mode - 1), and every
            other leaf is a constant: the read is retargeted
            (src/turn_callers.h)

and a call whose slice touches anything else -- a field, a parameter, a call
result, a global, the time scale, the fps or mode byte other than as that
index, or an instruction another family patches (it would be rescaled already)
-- needs an entry in MANUAL. The generator refuses to write while any call is
undecided or a table read fails its checks (the index must be the mode byte
minus one, the base the image base, the pair the one mode_constants.h lists,
and a `lea` of the table must feed nothing but the read).

Outputs
  src/turn_callers.h                the table reads to retarget (checked in)
  docs/animation/turn_callers.csv   every call, its class and the evidence

    .venv/Scripts/python tools/gen_turn_callers.py
"""
import bisect
import collections
import csv
import os
import re
import struct
import sys

try:
    import capstone
    from capstone import x86_const as X
except ImportError:
    sys.exit("needs capstone and pefile: pip install capstone pefile")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_shadow_mode import REG64, load_image  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_H = os.path.join(ROOT, "src", "turn_callers.h")
OUT_CSV = os.path.join(ROOT, "docs", "animation", "turn_callers.csv")
MODE_H = os.path.join(ROOT, "src", "mode_constants.h")

BASE = 0x180000000
TURN = 0x2DA510
MODE = 0xB6AC45
TIMESCALE = 0xB6AC38
FPS60_FLAG = 0xB6AC40
FPS_BYTE = 0xB6AC44
# globals whose presence in a slice means the engine compensated the value
RATE_GLOBALS = {TIMESCALE: "time scale", FPS60_FLAG: "60 fps flag", FPS_BYTE: "fps byte",
                MODE: "mode byte"}
TABLE_LO, TABLE_HI = 0x7A8150, 0x7A8338
ONE = 1.0
MAX_DEPTH = 8

VOL_XMM = {"xmm%d" % i for i in range(6)}
VOL_GPR = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}

# Calls whose slice leaves something the rules above cannot decide, decided
# here by reading the code (tools/ghidra_lines.py prints the function with an
# RVA on every line). Each says what k is and why:
#
#   convert  k is a per-tick blend in stock units after all: the hook's one
#            conversion is right
#   bypass   k is not a per-tick blend at all -- an interpolation fraction, or
#            a weight whose schedule already fixes where the blend ends. The
#            call is retargeted past the conversion (src/turn_callers.h).
DEAD = "dead code: nothing references %s -- no call, jump, 8-byte pointer, rva or rip lea"
MANUAL = {
    0x204C6B: ("convert", DEAD % "FUN_180204be0"),
    0x317832: ("convert", DEAD % "FUN_180317810"),
    0x317850: ("convert", DEAD % "FUN_180317810"),
    0x205CA5: ("convert", "k = [obj+0x1178], written only by the setup at 205A60 from its"
                          " 5th argument, and all 16 of its callers pass an .rdata per-tick"
                          " blend (0.1 to 0.4)"),
    0x205CCA: ("convert", "as 205CA5"),
    0x2A55FD: ("convert", "k = [obj+0x1080] * 0.2; this class's code (290000..2B0000) only"
                          " ever sets +0x1080 to the constant 1.0 (294A12, 297E25), and the"
                          " same field scales its 0.10472 rad/tick turn step at 2A559D"),
    0x3233DE: ("convert", "k = 1 / (n + 1), n the countdown [obj+0xE3C] whose decrement at"
                          " 3233E3 is in memory_timers.h: with the timers fixed n holds for"
                          " 1/ts ticks, and the conversion makes those ticks one stock step"),
    0x4B7D40: ("bypass", "k is 4B7700's weight 1/n from the motion advance 4B9C80, n = [obj+0xF50]"
                         " counted down per call: a linear blend that lands on the target at"
                         " n = 1, and the same weight lerps the non-turn channels (4B79C8..)"
                         " unconverted. Converted, the rotations lag them and snap at the end"),
    0x4B7DA6: ("bypass", "as 4B7D40"),
    0x4B7E0C: ("bypass", "as 4B7D40"),
    0x4B7575: ("bypass", "the tail jump of the keyframe interpolator at 4B7509 (a leaf, no"
                         " .pdata): channels 3-5 are angles, and k = t - key is the fraction"
                         " between two keys, not a per-tick blend"),
}
# A slice follows data, not control, so a caller that compensates by branching
# on the mode byte -- `mode == 1 ? turn(0.05) : turn(0.1)` as two calls --
# would slice to two plain constants. Every function holding a convert call
# that reads the mode byte, the 60 fps flag, the fps byte or the time scale
# anywhere must therefore be read and listed here, or the generator refuses.
RATE_REVIEWED = {
    0x243630: "its 0.4 and 0.3 turns are switch cases 1 and 5 of the state; the time scale"
              " and 60 fps flag (243B12, 243BF3, 243C1D) are read by the movement code"
              " after them and select nothing for the turn",
    0x2A1710: "the same code as 243630 (time scale at 2A1BAB), same finding",
    0x3B3FF0: "its convert calls pass k = 1, a snap the hook leaves alone",
    0x3C5350: "its convert call passes k = 1, a snap the hook leaves alone",
    0x3C57A0: "its convert calls pass k = 1, a snap the hook leaves alone",
    0x3C6750: "its convert call passes k = 1, a snap the hook leaves alone",
    0x3CA320: "its convert call passes k = 1, a snap the hook leaves alone",
    0x46B080: "the 0.08 turn toward +0x3B0 is unconditional once +0x3B8 is 0; the mode byte"
              " (46B761) indexes the 7A82D8 table for a later call to 2DA570, a different"
              " function",
    0x47C9D0: "as 46B080 (mode byte at 47D062 for 2DA570)",
    0x47DAB0: "as 46B080 (mode byte at 47E1BF for 2DA570)",
}
for _a in (0x317673, 0x31768F, 0x3176C9, 0x3176E5, 0x31771F, 0x31773B, 0x317775, 0x317791):
    MANUAL[_a] = ("convert", "k = byte [ctl+0x12] / 100: the spine controller 317470's per-tick"
                             " blend percentage, which its caller 317020 puts back to 8 after"
                             " every update; rescaled nowhere")


# ---------------------------------------------------------------------------
# functions and their control flow
# ---------------------------------------------------------------------------

def pdata_roots(img, secs):
    """{fragment begin: (root begin, [(begin, end) of every fragment])}.
    Shrink-wrapped functions are split into fragments chained to a parent's
    unwind info; slicing has to see all of them as one function."""
    lo, hi = secs[".pdata"]
    ents = []
    for off in range(lo, hi - 11, 12):
        b, e, u = struct.unpack_from("<III", img, off)
        if b == 0 and e == 0:
            break
        ents.append((b, e, u))
    parent = {}
    for b, e, u in ents:
        flags = img[u] >> 3
        if flags & 4:                              # UNW_FLAG_CHAININFO
            n = img[u + 2]
            off = u + 4 + ((n + 1) & ~1) * 2
            pb = struct.unpack_from("<I", img, off)[0]
            parent[b] = pb
        else:
            parent[b] = b
    frags = collections.defaultdict(list)
    for b, e, u in ents:
        r = b
        for _ in range(16):
            if parent.get(r, r) == r:
                break
            r = parent[r]
        frags[r].append((b, e))
    out = {}
    for r, fs in frags.items():
        for b, e in fs:
            out[b] = (r, sorted(fs))
    starts = sorted(out)
    return out, starts, ents


class Func:
    """Every instruction of one function (all its fragments), and the edges."""

    def __init__(self, img, root, frags, md):
        self.root = root
        self.ins = {}
        for b, e in frags:
            pos = b
            while pos < e:
                try:
                    i = next(md.disasm(img[pos:pos + 16], pos))
                except StopIteration:
                    break
                self.ins[i.address] = i
                pos += i.size
        self.order = sorted(self.ins)
        self.preds = collections.defaultdict(list)
        self.indirect = []
        for a in self.order:
            i = self.ins[a]
            if i.mnemonic == "jmp" and i.operands[0].type != X.X86_OP_IMM:
                self.indirect.append(a)
            for s in self.succs(i):
                if s in self.ins:
                    self.preds[s].append(a)
        # The state machines dispatch through image-base-relative tables of
        # RVAs (`jmp rcx`), whose targets have no visible predecessor. Every
        # such instruction is given every indirect jump of the function as a
        # predecessor: more paths than the real ones, never fewer.
        if self.indirect:
            for a in self.order:
                if a != root and not self.preds.get(a):
                    self.preds[a] = list(self.indirect)

    def succs(self, i):
        m = i.mnemonic
        nxt = i.address + i.size
        if m in ("ret", "int3", "ud2", "hlt"):
            return []
        if m.startswith("j"):
            op = i.operands[0]
            if op.type != X.X86_OP_IMM:
                return []
            return [op.imm] if m == "jmp" else [op.imm, nxt]
        return [nxt]


def reg_key(ins, r):
    n = ins.reg_name(r)
    return REG64.get(n, n)


def writes(ins):
    _r, w = ins.regs_access()
    return {reg_key(ins, r) for r in w}


def reads(ins):
    r, _w = ins.regs_access()
    return {reg_key(ins, x) for x in r}


def rip_target(ins, op):
    return ins.address + ins.size + op.mem.disp if op.mem.base == X.X86_REG_RIP else None


def f32(img, a):
    return struct.unpack_from("<f", img, a)[0]


# ---------------------------------------------------------------------------
# backward slice
# ---------------------------------------------------------------------------

class Slicer:
    def __init__(self, img, secs, fn):
        self.img, self.secs, self.fn = img, secs, fn
        self.touched = set()   # every instruction the slice passed through

    def defs(self, at, reg):
        """The instructions that define `reg` on some path reaching `at` (not
        including `at` itself), plus ("entry", ...) / ("call", a) / ("orphan", a)
        where a path ends without one."""
        fn = self.fn
        out, seen = [], set()
        work = list(fn.preds.get(at, []))
        if not work and at != fn.root:
            out.append(("orphan", at))
        while work:
            a = work.pop()
            if a in seen:
                continue
            seen.add(a)
            i = fn.ins[a]
            if i.mnemonic == "call" and (reg in VOL_XMM or reg in VOL_GPR):
                out.append(("call", a))
                continue
            if reg in writes(i):
                out.append(("def", a))
                continue
            ps = fn.preds.get(a, [])
            if not ps:
                out.append(("entry", a) if a == fn.root else ("orphan", a))
            work.extend(ps)
        return out

    def stack_stores(self, at, disp):
        """stores to [rsp + disp] reaching `at`"""
        fn = self.fn
        out, seen = [], set()
        work = list(fn.preds.get(at, []))
        while work:
            a = work.pop()
            if a in seen:
                continue
            seen.add(a)
            i = fn.ins[a]
            hit = False
            for op in i.operands:
                if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RSP and \
                        op.mem.index == 0 and op.mem.disp == disp and \
                        op.access & capstone.CS_AC_WRITE:
                    hit = True
            if i.mnemonic == "lea" and "rsp" in i.op_str:
                out.append(("escape", a))      # the slot's address is taken
                continue
            if hit:
                out.append(("def", a))
                continue
            ps = fn.preds.get(a, [])
            if not ps:
                out.append(("entry", a))
            work.extend(ps)
        return out

    def value(self, at, reg, depth=0):
        """An expression tree for the value of `reg` just before `at`."""
        if depth > MAX_DEPTH:
            return ("deep", at, reg)
        alts = []
        for kind, a in self.defs(at, reg):
            if kind == "def":
                alts.append(self.from_def(a, reg, depth))
            elif kind == "call":
                alts.append(("callret", a, reg))
            elif kind == "entry":
                alts.append(("param", reg))
            else:
                alts.append(("orphan", a, reg))
        if not alts:
            return ("nodef", at, reg)
        return alts[0] if len(alts) == 1 else ("phi", alts)

    def mem(self, i, op, depth):
        """What a memory operand holds."""
        t = rip_target(i, op)
        m = op.mem
        if t is not None:
            if TABLE_LO <= t < TABLE_HI:
                return ("tablefixed", i.address, t)
            if t in RATE_GLOBALS or (t <= MODE < t + max(op.size, 1)):
                return ("rate", i.address, RATE_GLOBALS.get(t, "%X" % t))
            sec = self.section(t)
            if sec == ".rdata":
                return ("const", i.address, t, f32(self.img, t))
            return ("global", i.address, t)
        if TABLE_LO <= m.disp < TABLE_HI:
            return ("table", i.address, m.disp, "base")
        if m.disp in RATE_GLOBALS:
            return ("rate", i.address, RATE_GLOBALS[m.disp])
        base = i.reg_name(m.base) if m.base else None
        if base in ("rsp", "esp") and m.index == 0:
            stores = self.stack_stores(i.address, m.disp)
            alts = []
            for kind, a in stores:
                if kind != "def":
                    alts.append(("stack?", a, m.disp))
                    continue
                si = self.fn.ins[a]
                self.touched.add(a)
                src = [o for o in si.operands if o.type == X.X86_OP_REG]
                if not src:
                    alts.append(("stack?", a, m.disp))
                    continue
                alts.append(self.value(a, reg_key(si, src[0].reg), depth + 1))
            if not alts:
                return ("stack?", i.address, m.disp)
            return alts[0] if len(alts) == 1 else ("phi", alts)
        if m.index and m.disp == 0 and base:
            # [reg + idx*4] -- the base may be a lea of a table
            b = self.value(i.address, REG64.get(base, base), depth + 1)
            if b[0] == "lea" and TABLE_LO <= b[2] < TABLE_HI:
                return ("table", i.address, b[2], "lea", b[1])
        return ("field", i.address, base, m.disp)

    def section(self, t):
        for name, (a, b) in self.secs.items():
            if a <= t < b:
                return name
        return None

    def from_def(self, a, reg, depth):
        i = self.fn.ins[a]
        self.touched.add(a)
        m = i.mnemonic
        ops = i.operands
        if m == "lea" and ops[1].type == X.X86_OP_MEM:
            t = rip_target(i, ops[1])
            if t is not None:
                return ("lea", a, t)
            return ("leacalc", a)
        if m in ("xorps", "pxor", "xorpd") and ops[0].reg == ops[1].reg:
            return ("const", a, None, 0.0)
        if m in ("movss", "movaps", "movups", "movd", "movq", "movsd", "movapd", "mov",
                 "movzx", "movsxd", "movsx", "cvtss2sd", "cvtsd2ss"):
            src = ops[1]
            if src.type == X.X86_OP_MEM:
                v = self.mem(i, src, depth)
                return v if m in ("movss", "movd", "mov", "movaps", "movups", "movq") \
                    else ("conv", a, m, v)
            if src.type == X.X86_OP_REG:
                return self.value(a, reg_key(i, src.reg), depth + 1)
            if src.type == X.X86_OP_IMM:
                return ("imm", a, src.imm)
        if m in ("dec", "inc") and len(ops) == 1:
            return ("op", a, m, self.value(a, reg, depth + 1), None)
        if m in ("addss", "subss", "mulss", "divss", "minss", "maxss", "sqrtss", "add", "sub",
                 "imul", "and", "or", "shl", "shr", "sar", "andps", "orps", "xorps"):
            left = self.value(a, reg, depth + 1) if m != "sqrtss" else None
            src = ops[1] if len(ops) > 1 else None
            if src is None:
                right = None
            elif src.type == X.X86_OP_MEM:
                right = self.mem(i, src, depth)
            elif src.type == X.X86_OP_REG:
                right = self.value(a, reg_key(i, src.reg), depth + 1)
            else:
                right = ("imm", a, src.imm)
            if m == "sqrtss":
                left, right = right, None
            return ("op", a, m, left, right)
        if m.startswith("cvt"):
            src = ops[1]
            inner = self.mem(i, src, depth) if src.type == X.X86_OP_MEM else \
                self.value(a, reg_key(i, src.reg), depth + 1)
            return ("conv", a, m, inner)
        return ("opaque", a, "%s %s" % (m, i.op_str))


def leaves(t):
    if t is None:
        return
    k = t[0]
    if k == "phi":
        for x in t[1]:
            yield from leaves(x)
    elif k == "op":
        yield from leaves(t[3])
        yield from leaves(t[4])
    elif k == "conv":
        yield from leaves(t[3])
    else:
        yield t


def render(t):
    if t is None:
        return "-"
    k = t[0]
    if k == "phi":
        return "phi(" + " | ".join(render(x) for x in t[1]) + ")"
    if k == "op":
        return "%s(%s, %s)" % (t[2], render(t[3]), render(t[4]))
    if k == "conv":
        return "%s(%s)" % (t[2], render(t[3]))
    if k == "const":
        return "%.6g" % t[3] if t[2] is None else "%.6g@%X" % (t[3], t[2])
    if k == "table":
        return "table[%X]%s" % (t[2], "" if t[3] == "base" else " via lea %X" % t[4])
    if k == "field":
        return "[%s+%X]@%X" % (t[2], t[3], t[1])
    if k == "param":
        return "param(%s)" % t[1]
    if k == "callret":
        return "ret(%s @%X)" % (t[2], t[1])
    if k == "rate":
        return "RATE(%s @%X)" % (t[2], t[1])
    if k == "global":
        return "global[%X]@%X" % (t[2], t[1])
    if k == "imm":
        return "#%X" % t[2]
    if k == "lea":
        return "lea %X" % t[2]
    return "%s@%X" % (k, t[1]) if len(t) > 1 and isinstance(t[1], int) else str(t)


# ---------------------------------------------------------------------------
# table reads: the index, the base, the pair
# ---------------------------------------------------------------------------

def mode_pairs():
    """{fast-slot rva: (shipped fast, stock)} from mode_constants.h"""
    out = {}
    for ln in open(MODE_H, encoding="utf-8"):
        g = re.match(r"\s*\{0x([0-9A-F]+), ([-0-9.e]+)f, ([-0-9.e]+)f, \d\}", ln)
        if g:
            out[int(g.group(1), 16)] = (float(g.group(2)), float(g.group(3)))
    return out


def is_mode_minus_one(sl, at, reg):
    """The index register holds mode - 1: movzx of the mode byte, dec (or
    sub 1 / lea -1), sign or zero extension. Every path must agree."""
    t = sl.value(at, reg)

    def mode_byte(x):
        while x is not None and x[0] == "conv" and x[2] in ("movzx", "movsx"):
            x = x[3]
        return x is not None and x[0] == "rate" and x[2] == "mode byte"

    def ok(x):
        if x[0] == "phi":
            return all(ok(y) for y in x[1])
        if x[0] == "op" and x[2] == "dec":
            return mode_byte(x[3])
        if x[0] == "op" and x[2] == "sub" and x[4] is not None and x[4][0] == "imm" and \
                x[4][2] == 1:
            return mode_byte(x[3])
        return False
    return ok(t), render(t)


def is_image_base(sl, at, reg):
    t = sl.value(at, reg)

    def ok(x):
        if x[0] == "phi":
            return all(ok(y) for y in x[1])
        return x[0] == "lea" and x[2] == 0
    return ok(t), render(t)


def lea_feeds_only(fn, lea_at, reg, load_at):
    """A `lea reg, [table]` whose value reaches nothing but the one read."""
    seen, work = set(), [s for s in fn.succs(fn.ins[lea_at]) if s in fn.ins]
    while work:
        a = work.pop()
        if a in seen:
            continue
        seen.add(a)
        i = fn.ins[a]
        if reg in reads(i) and a != load_at:
            return False, "also read at %X" % a
        if reg in writes(i) and a != load_at:
            continue
        if i.mnemonic == "ret" and reg == "rax":
            return False, "reaches the return at %X" % a
        if i.mnemonic == "call" and reg in VOL_GPR:
            continue                       # clobbered by the call
        work.extend(s for s in fn.succs(i) if s in fn.ins)
    return True, ""


# ---------------------------------------------------------------------------
# every reference to 2DA510
# ---------------------------------------------------------------------------

def references(img, secs):
    """Direct calls and jumps (checked against a full decode), and any other
    route to the function: a pointer to it in data, a rip lea of it."""
    lo, hi = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    calls, other = [], []
    pos = lo
    while pos < hi:
        end = min(hi, pos + 0x10000)
        last = pos
        for i in md.disasm(img[pos:end + 16], pos):
            if i.address >= end:
                break
            last = i.address + i.size
            if i.mnemonic in ("call", "jmp") and i.op_str.startswith("0x"):
                if int(i.op_str, 16) == TURN:
                    calls.append((i.address, i.mnemonic))
            elif "rip" in i.op_str and i.mnemonic == "lea":
                g = re.search(r"rip ([+-]) (0x[0-9a-f]+)", i.op_str)
                if g:
                    t = i.address + i.size + int(g.group(2), 16) * (1 if g.group(1) == "+" else -1)
                    if t == TURN:
                        other.append((i.address, "lea of 2DA510"))
        pos = last if last > pos else pos + 1
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a & ~7, b - 8, 8):
            if struct.unpack_from("<Q", img, off)[0] == BASE + TURN:
                other.append((off, "%s holds its address" % name))
    return calls, other


def patched_ranges():
    """[(start, end, family)] of every instruction another family rewrites."""
    import contextlib
    import io
    import check_patch_sites as cps
    with contextlib.redirect_stdout(io.StringIO()):
        img, _lo, _hi = cps.load_image()
        sites = cps.read_tables(img)
        for rva in cps.input_windows():
            sites[rva] = ("input windows", 2, b"")
        for rva, raw, label in cps.scale_detours():
            sites[rva] = (label, len(raw), raw)
        hoist, loads = cps.hoisted_decay()
        for rva, raw, label in hoist:
            sites[rva] = (label, len(raw), raw)
        for rva, raw, label in cps.shadow_mode():
            sites[rva] = (label, len(raw), raw)
        for rva, raw, label in cps.frame_clocks():
            sites[rva] = (label, len(raw), raw)
        for rva, raw, label in cps.integer_skips():
            sites[rva] = (label, len(raw), raw)
        menus, menu_literals = cps.menu_transitions()
        for rva, raw, label in menus + menu_literals:
            sites[rva] = (label, len(raw), raw)
        worlds, world_literals = cps.world_anims()
        for rva, raw, label in worlds + world_literals:
            sites[rva] = (label, len(raw), raw)
    out = []
    for rva, (fam, n, _raw) in sites.items():
        if fam == "turn_callers.h":
            continue
        out.append((rva, rva + max(n, 1), fam))
    out.sort()
    return out


def patched_by(ranges, starts, a, size):
    k = bisect.bisect_right(starts, a + size - 1) - 1
    while k >= 0 and ranges[k][1] > a - 16:
        s, e, fam = ranges[k]
        if s < a + size and a < e:
            return fam
        k -= 1
    return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    img, secs, _funcs, sha = load_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    roots, starts, _ents = pdata_roots(img, secs)
    pairs = mode_pairs()
    if not pairs:
        sys.exit("no pairs in %s" % MODE_H)
    ranges = patched_ranges()
    rstarts = [r[0] for r in ranges]

    calls, other = references(img, secs)
    problems = ["%X: %s" % o for o in other]
    rows, loads, users = [], {}, collections.defaultdict(list)
    fcache = {}
    for at, kind in calls:
        k = bisect.bisect_right(starts, at) - 1
        frag = starts[k] if k >= 0 else None
        if frag is None or not any(b <= at < e for b, e in roots[frag][1]):
            if at in MANUAL:
                rows.append(dict(site="%X" % at, kind=kind, function="", cls=MANUAL[at][0],
                                 coefficient="", evidence="no .pdata function holds it;"
                                 " MANUAL: %s" % MANUAL[at][1]))
            else:
                rows.append(dict(site="%X" % at, kind=kind, function="", cls="unresolved",
                                 coefficient="", evidence="no .pdata function holds it"))
            continue
        root, frags = roots[frag]
        if root not in fcache:
            fcache[root] = Func(img, root, frags, md)
        fn = fcache[root]
        if at not in fn.ins:
            rows.append(dict(site="%X" % at, kind=kind, function="%X" % root, cls="unresolved",
                             coefficient="", evidence="not on an instruction boundary"))
            continue
        sl = Slicer(img, secs, fn)
        t = sl.value(at, "xmm2")
        text = render(t)
        lv = list(leaves(t))
        notes = []
        fam = sorted({patched_by(ranges, rstarts, a, fn.ins[a].size) for a in sl.touched} -
                     {None})
        tables = [x for x in lv if x[0] == "table"]
        others = [x for x in lv if x[0] not in ("table", "const")]
        if at in MANUAL:
            # read by hand: the rules below are not trusted for this call
            cls = MANUAL[at][0]
            if fam:
                notes.append("slice passes through %s" % ", ".join(fam))
            if others:
                notes.append("leaves: %s" % ", ".join(render(x) for x in others))
            notes.append("MANUAL: %s" % MANUAL[at][1])
        elif fam:
            cls = "unresolved"
            notes.append("slice passes through %s" % ", ".join(fam))
        elif tables and not others:
            cls, bad = "table", []
            for tb in tables:
                load_at = tb[1]
                li = fn.ins[load_at]
                memop = [o for o in li.operands if o.type == X.X86_OP_MEM][0]
                idx = li.reg_name(memop.mem.index)
                okx, why = is_mode_minus_one(sl, load_at, REG64.get(idx, idx))
                if not okx:
                    bad.append("index at %X is %s" % (load_at, why))
                entry = tb[2]
                if entry not in pairs:
                    bad.append("%X is not a mode_constants.h pair" % entry)
                elif (f32(img, entry), f32(img, entry + 4)) != \
                        (struct.unpack("<f", struct.pack("<f", pairs[entry][0]))[0],
                         struct.unpack("<f", struct.pack("<f", pairs[entry][1]))[0]):
                    bad.append("%X does not hold the pair mode_constants.h lists" % entry)
                if tb[3] == "base":
                    base = li.reg_name(memop.mem.base)
                    okb, why = is_image_base(sl, load_at, REG64.get(base, base))
                    if not okb:
                        bad.append("base at %X is %s" % (load_at, why))
                    patch = dict(rva=load_at, len=li.size, disp_off=li.disp_offset,
                                 rip=0, entry=entry, orig=bytes(li.bytes))
                else:
                    lea_at = tb[4]
                    lea = fn.ins[lea_at]
                    lreg = reg_key(lea, lea.operands[0].reg)
                    okl, why = lea_feeds_only(fn, lea_at, lreg, load_at)
                    if not okl:
                        bad.append("lea at %X: %s" % (lea_at, why))
                    patch = dict(rva=lea_at, len=lea.size, disp_off=lea.disp_offset,
                                 rip=1, entry=entry, orig=bytes(lea.bytes))
                if patched_by(ranges, rstarts, patch["rva"], patch["len"]):
                    bad.append("%X is patched by another family" % patch["rva"])
                prev = loads.get(patch["rva"])
                if prev and prev != patch:
                    bad.append("%X read two ways" % patch["rva"])
                loads[patch["rva"]] = patch
                users[patch["rva"]].append(at)
            if bad:
                cls = "unresolved"
                notes += bad
            else:
                notes.append("stock coefficient recovered from %s" %
                             ", ".join("%X" % x[2] for x in tables))
        elif not others:
            cls = "convert"
            notes.append("constant: the hook's conversion is the only one")
        else:
            cls = "unresolved"
            notes.append("leaves: %s" % ", ".join(render(x) for x in others))
        rows.append(dict(site="%X" % at, kind=kind, function="%X" % root, cls=cls,
                         coefficient=text, evidence="; ".join(notes)))

    # control dependence on a rate test (RATE_REVIEWED above)
    reviewed = set()
    for r in rows:
        if r["cls"] != "convert" or not r["function"]:
            continue
        root = int(r["function"], 16)
        fn = fcache[root]
        rate_reads = []
        for a in fn.order:
            i = fn.ins[a]
            for op in i.operands:
                if op.type != X.X86_OP_MEM:
                    continue
                t = rip_target(i, op)
                t = t if t is not None else op.mem.disp
                if t in RATE_GLOBALS:
                    rate_reads.append("%X" % a)
        if not rate_reads:
            continue
        if root in RATE_REVIEWED:
            reviewed.add(root)
            r["evidence"] += "; the function reads a rate global (%s): %s" % (
                " ".join(rate_reads[:4]), RATE_REVIEWED[root])
        else:
            r["cls"] = "unresolved"
            r["evidence"] += "; the function reads a rate global at %s -- read it and add it" \
                             " to RATE_REVIEWED" % " ".join(rate_reads[:4])
    for a in sorted(set(RATE_REVIEWED) - reviewed):
        problems.append("%X: stale RATE_REVIEWED entry" % a)

    counts = collections.Counter(r["cls"] for r in rows)
    print("%d references to main+%X: %d calls/jumps, %d other routes"
          % (len(calls) + len(other), TURN, len(calls), len(other)))
    for c in ("convert", "table", "bypass", "unresolved"):
        print("  %-10s %d%s" % (c, counts[c], " (%d read by hand)" % sum(
            1 for r in rows if r["cls"] == c and "MANUAL" in r["evidence"]) if c != "unresolved"
            else ""))
    unresolved = [r for r in rows if r["cls"] == "unresolved"]
    for r in unresolved:
        print("  UNRESOLVED %s in %s: k = %s -- %s" % (r["site"], r["function"],
                                                      r["coefficient"], r["evidence"]))
    for p in problems:
        print("  PROBLEM " + p)
    stale = sorted(set(MANUAL) - {int(r["site"], 16) for r in rows})
    for a in stale:
        print("  STALE MANUAL entry %X (no call there)" % a)
    if unresolved or problems or stale:
        sys.exit("refusing to write: decide every call first")
    bypass = []
    for r in rows:
        if r["cls"] != "bypass":
            continue
        a = int(r["site"], 16)
        raw = bytes(img[a:a + 5])
        if raw[0] not in (0xE8, 0xE9) or a + 5 + struct.unpack_from("<i", raw, 1)[0] != TURN:
            sys.exit("bypass %X is not a rel32 call or jump to %X" % (a, TURN))
        if patched_by(ranges, rstarts, a, 5):
            sys.exit("bypass %X is patched by another family" % a)
        bypass.append((a, raw))

    entries = sorted({p["entry"] for p in loads.values()})
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["site", "kind", "function", "cls", "coefficient",
                                          "evidence"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: int(r["site"], 16)))

    def hexb(b):
        b = bytes(b) + b"\0" * (10 - len(b))
        return ", ".join("0x%02X" % x for x in b)
    lines = [
        "// Generated by tools/gen_turn_callers.py -- do not edit by hand.",
        "// main.dll sha1 %s" % sha,
        "//",
        "// The angular approach main+2DA510 has %d callers, and the turn hook's"
        % len(calls),
        "// conversion is right for %d of them: they pass a per-tick blend in stock"
        % counts["convert"],
        "// units. %d build theirs from the per-mode table (g - 1, g from a {g^0.5, g}"
        % counts["table"],
        "// pair of mode_constants.h), which the engine has already compensated: each",
        "// of those table reads is retargeted at a private {fast, stock} pair, so",
        "// that the hook sees the stock coefficient and converts it once. %d pass"
        % counts["bypass"],
        "// something that is not a per-tick blend at all, and call past the",
        "// conversion. docs/animation/turn_callers.csv has every caller, its class",
        "// and the coefficient's slice.",
        "#pragma once",
        "#include <cstdint>",
        "",
        '#define TURN_CALLERS_MAIN_SHA1 "%s"' % sha,
        "",
        "// the mode-table pairs the callers read (the fast slot; the stock one follows)",
        "static const uint32_t kTurnPairEntries[] = {",
    ]
    for e in entries:
        lines.append("    0x%X,  // stock g = %.9g" % (e, f32(img, e + 4)))
    lines += [
        "};",
        "",
        "// a read of one of them, by the displacement that names it",
        "struct TurnTableRead {",
        "    uint32_t rva;     // the instruction holding the displacement",
        "    uint8_t len;",
        "    uint8_t dispOff;  // where the displacement sits in it",
        "    uint8_t ripRel;   // 1: `lea r, [rip+d]`; 0: `[imageBase + idx*4 + d]`",
        "    uint8_t pair;     // index into kTurnPairEntries",
        "    uint8_t orig[10];",
        "};",
        "",
        "static const TurnTableRead kTurnTableReads[] = {",
    ]
    for rva in sorted(loads):
        p = loads[rva]
        lines.append("    {0x%X, %d, %d, %d, %d, {%s}},  // %X for the call at %s"
                     % (rva, p["len"], p["disp_off"], p["rip"], entries.index(p["entry"]),
                        hexb(p["orig"]), p["entry"],
                        ", ".join("%X" % c for c in sorted(set(users[rva])))))
    lines += [
        "};",
        "",
        "// a call (E8) or tail jump (E9) that is retargeted past the conversion",
        "struct TurnBypass {",
        "    uint32_t rva;",
        "    uint8_t orig[5];",
        "};",
        "",
        "static const TurnBypass kTurnBypass[] = {",
    ]
    for a, raw in bypass:
        lines.append("    {0x%X, {%s}},  // %s" % (a, ", ".join("0x%02X" % x for x in raw),
                                               MANUAL[a][1][:60].rstrip() + "..."))
    lines += ["};", ""]
    open(OUT_H, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print("wrote %s (%d reads of %d pairs, %d bypassed calls) and %s"
          % (os.path.relpath(OUT_H, ROOT), len(loads), len(entries), len(bypass),
             os.path.relpath(OUT_CSV, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
