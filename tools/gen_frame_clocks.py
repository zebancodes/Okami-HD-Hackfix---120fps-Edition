#!/usr/bin/env python3
"""Generate the frame-counter clock table (family F5).

The global frame counter main+B6AC20 goes up by one per engine tick, and a
lot of the game reads it as a clock: pulses and wobbles fed into a sine,
flipbook cycles, "every 15th frame" effect spawns, the loading screen's dots
and rhythm window, and elapsed-time windows. At 120 fps every one of those
runs four times too fast. frame_gates.h and frame_phases.h already fix the two
simplest encodings; this generator finds every other one.

Nothing here trusts a list. Every instruction in .text that touches the
counter is found by a sweep in every encoding (rip-relative, image-base-
relative, a `lea` of its address, a pointer to it stored as data), and each
one ends up in exactly one class. The generator refuses to write the header
if any reference is left unclassified.

A read's class comes from where its value goes. A forward register slice
follows the loaded value through arithmetic and both directions of every
branch, and records its consumers: a branch on flags the value set, a float
conversion, a table index, a store, a division, a subtraction from a stored
stamp. The rules, in order:

  already covered     the exact instruction is in frame_gates.h/frame_phases.h
  snapshot            compared with a stored copy and stored back: "have I
                      already run this frame". Must keep seeing the real counter.
  elapsed (U)         `counter - stamp` with the stamp a global some read of
                      the counter stores: the loading screen's windows. Their
                      lengths divide by the mode byte, which the patch pins at
                      1, so the family counts 60 Hz-configuration ticks.
  stamp               stored to an object field and nothing else
  buffer parity       `counter & 1` picks one of two per-frame buffers
  mode parity         the layout flipbook's `(counter & 1) == phase` in mode
                      1 -- family F6, left alone here
  mask gate (widen)   `test <counter or counter+phase>, 2^k-1` then a branch:
                      the immediate is widened, as frame_gates.h does
  fps throttle        `counter % (fps / 2)`: the port's own real-time gate
  debug divider       `counter % knob` with a knob nothing writes
  modulo gate (H)     `counter % P == e` by magic multiply: the read goes to a
                      hold counter (below). P and e are measured, not
                      pattern-matched: the instructions from the read to the
                      branch are emulated under Unicorn for every counter value
                      over several periods.
  phase (S)           the value reaches a float conversion or a table index,
                      and any branch on it is a cycle selection
                      `(counter >> s) & m == k` over every k
  mixed               a modulo gate whose value also feeds phases or other
                      compares: decided in MIXED below, with the reason, and the
                      decision checked against the code

The counters (all dwords in one block, rewritten by a hook on flower_tick's own
`inc [frameCounter]`, so they change exactly when the engine's counter does):

  S       the counter at the stock rate of the current context: one step per
          4 ticks at 120 fps in play, per 2 in the 60 Hz menus (the shadow
          mode byte says which). frame_phases.h reads it too.
  H(P,e)  S, except that on the ticks of a stock tick after its first, a value
          congruent to e (mod P) is held back to the one before. A gate
          `x % P == e` then fires once per stock tick instead of N times,
          while every other residue reads exactly as S.
  U       the counter in 60 Hz-configuration ticks (fps / 60 per step).

With the fix off (30 fps mode, the A/B key, Passthrough) every counter is the
frame counter itself, so a retargeted read is the stock instruction.

Outputs
  src/frame_clocks.h                 the tables (checked in)
  docs/animation/frame_clocks.csv    every reference, its class and the evidence

    .venv/Scripts/python tools/gen_frame_clocks.py
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
    from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL
    from unicorn import x86_const as U
except ImportError:
    sys.exit("needs capstone and unicorn: pip install capstone unicorn")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_shadow_mode import REG64, callee_reads, function_of, load_image  # noqa: E402
from gen_shadow_mode import POINTER_ROUTES as SHADOW_ROUTES  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_H = os.path.join(ROOT, "src", "frame_clocks.h")
OUT_CSV = os.path.join(ROOT, "docs", "animation", "frame_clocks.csv")

BASE = 0x180000000
FC = 0xB6AC20          # frame counter
FPS = 0xB6AC44         # fps byte
MODE = 0xB6AC45        # mode byte
TICK_FN = 0x4B63B0     # flower_tick
MASKS = {1, 3, 7, 0xF, 0x1F, 0x3F}
FLAG_READ = re.compile(r"^(j(?!mp)|set|cmov|adc|sbb)")
VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
ARGS = ("rcx", "rdx", "r8", "r9")

# A `lea` of the counter's address is the compiler reusing it as the base of
# the flag block that follows it: every dereference below goes through a
# displacement of 0x680 or more, never the counter itself. Two of them leave
# their function, and those routes were read by hand (gen_shadow_mode.py
# follows the same two for the mode byte, which is at +0x25 from here):
POINTER_ROUTES = {
    0x4B63ED: "flower_tick passes &frameCounter to GXPacket::update for its pacing"
              " callback 4B52B0, which reads [arg+0x25] (the mode byte), not the counter",
    0x4B6869: "flower_startup's memset(&frameCounter, 0, 0x700) of the frame block"
              " (the counter restarts at 0; the counters here rebase when it runs backwards)",
}

# Modulo gates whose value also feeds something other than the gate. Each is
# decided here, and check_mixed() proves the decision against the code by
# emulating the pieces named (start, branch, register):
#   P, e     the hold counter: H(P, e)
#   value    the snippet that leaves the counter mod P in the register (when the
#            compares below test that remainder rather than the counter)
#   event    the branch that must fire once per stock tick: it must fire on
#            exactly e (mod P)
#   repeats  other single-residue branches, which fire on every tick of their
#            stock tick; each must be harmless to repeat, and says why
#   windows  branches testing a range of residues: the held value (e - 1) must
#            be inside the range exactly when e is, so the range reads as stock
#   blip     what the held value does to the value's other readers
MIXED = {
    0x4003E0: dict(
        P=10, e=0, what="cCockLoading: loading-screen dots and rhythm window",
        value=(0x4003DB, 0x4003F5, "esi"),
        event=(0x400596, 0x400598, "esi", "x == 0: dots(+0x70) += 1"),
        repeats=[(0x400549, 0x40054C, "esi",
                  "x == 1: clears the two 'beat already judged' flags (+0x74 bits 20, 21);"
                  " clearing them again on the same stock tick changes nothing")],
        windows=[(0x40044E, 0x400451, "esi"), (0x400453, 0x400459, "esi")],
        blip="none: the only other readers are the window tests"),
    0x3D48E3: dict(
        P=180, e=0, what="screen wobble 3D4830: phases fc*2, fc*4 and a formula toggle",
        value=None, event=(0x3D4953, 0x3D497F, "esi", "x % 180 == 0: toggles +0x5BEC"),
        repeats=[], windows=[],
        blip="the phase reads see one stock step back on the held ticks, once per"
             " 180 stock ticks (6 s): 2-4 degrees of a 0.004-amplitude wobble"),
    0x3D4AE5: dict(
        P=360, e=0, what="screen wobble 3D4A40 (one branch)",
        value=None, event=(0x3D4B3D, 0x3D4B62, "edi", "x % 360 == 0: toggles +0x5BEC"),
        repeats=[], windows=[],
        blip="the phase reads see one stock step back on the held ticks, once per"
             " 360 stock ticks (12 s)"),
    0x3D4B19: dict(
        P=360, e=0, what="screen wobble 3D4A40 (other branch)",
        value=None, event=(0x3D4B3D, 0x3D4B62, "edi", "x % 360 == 0: toggles +0x5BEC"),
        repeats=[], windows=[], blip="as 3D4AE5"),
}

CLASS_ORDER = ["tick", "retarget S", "retarget H", "retarget U", "widen", "covered",
               "snapshot", "stamp", "buffer parity", "mode parity (F6)", "fps throttle",
               "debug divider", "writer", "address", "unresolved"]


# ---------------------------------------------------------------------------
# 1. every reference, every encoding
# ---------------------------------------------------------------------------

def sweep(img, secs):
    """One linear pass over .text. Returns
      refs      every instruction whose memory operand covers the counter
      leas      every lea of its address
      problems  other routes to it (image-base-relative displacements, pointers)
      targets   every direct branch and call target (for the hook's window)
      riprefs   {target: [(rva, writes?)]} for every rip-relative memory operand
      bounds    every instruction start, in order (for looking backwards)"""
    import array
    lo, hi = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    refs, leas, problems = [], [], []
    targets = set()
    riprefs = collections.defaultdict(list)
    bounds = array.array("I")
    pos = lo
    while pos < hi:
        end = min(hi, pos + 0x10000)
        last = pos
        for ins in md.disasm(img[pos:end + 16], pos):
            if ins.address >= end:
                break
            last = ins.address + ins.size
            bounds.append(ins.address)
            g = ins.group
            if (g(capstone.CS_GRP_JUMP) or g(capstone.CS_GRP_CALL)) and ins.operands and                     ins.operands[0].type == X.X86_OP_IMM:
                targets.add(ins.operands[0].imm)
            for op in ins.operands:
                if op.type != X.X86_OP_MEM:
                    continue
                m = op.mem
                size = max(op.size, 1)
                if m.base == X.X86_REG_RIP:
                    t = ins.address + ins.size + m.disp
                    if ins.mnemonic == "lea":
                        if FC <= t < FC + 4:
                            leas.append(ins)
                        continue
                    riprefs[t].append((ins.address, bool(op.access & capstone.CS_AC_WRITE)))
                    if t < FC + 4 and FC < t + size:
                        refs.append(ins)
                elif FC - 8 < m.disp < FC + 4:
                    problems.append((ins.address, "displacement %X (image-base-relative?)"
                                     % m.disp))
        pos = last if last > pos else pos + 1
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a & ~7, b - 8, 8):
            v = struct.unpack_from("<Q", img, off)[0]
            if BASE + FC <= v < BASE + FC + 4:
                problems.append((off, "%s holds the address of the counter" % name))
    return refs, leas, problems, targets, riprefs, bounds


def covered_rvas():
    out = {}
    for fn in ("frame_gates.h", "frame_phases.h"):
        for ln in open(os.path.join(ROOT, "src", fn), encoding="utf-8"):
            g = re.match(r"\s*\{0x([0-9A-F]+),", ln)
            if g:
                out[int(g.group(1), 16)] = fn
    return out


# ---------------------------------------------------------------------------
# 2. where a read's value goes
# ---------------------------------------------------------------------------

class Dis:
    def __init__(self, img, bounds, funcs=None):
        self.img = img
        self.bounds = bounds
        self.funcs = funcs
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.cache = {}

    def __call__(self, a):
        if a not in self.cache:
            self.cache[a] = next(self.md.disasm(self.img[a:a + 16], a))
        return self.cache[a]

    def before(self, a, n):
        """the n instructions straight before a, from the sweep's decode (or,
        without one, from a linear decode of a's function)"""
        if self.bounds is None:
            f = function_of(self.funcs, a)
            if f is None:
                return []
            out, pos = [], f
            while pos < a:
                out.append(self(pos))
                pos += out[-1].size
            return out[-n:] if pos == a else []
        k = bisect.bisect_left(self.bounds, a)
        if k >= len(self.bounds) or self.bounds[k] != a:
            return []
        return [self(x) for x in self.bounds[max(0, k - n):k]]


def r64(ins, r):
    return REG64.get(ins.reg_name(r))


def rip_target(ins, op):
    return ins.address + ins.size + op.mem.disp if op.mem.base == X.X86_REG_RIP else None


def mem_desc(ins, op):
    t = rip_target(ins, op)
    if t is not None:
        return ("g", t)
    return ("m", ins.reg_name(op.mem.base) if op.mem.base else None, op.mem.disp)


Use = collections.namedtuple("Use", "kind at text setter extra")


def writes_flags(i):
    return X.X86_REG_EFLAGS in i.regs_access()[1]


def slice_value(dis, img, funcs, ref):
    """Consumers of the value a read loads, following registers forward through
    both directions of every branch. Returns (uses, cut)."""
    mn = ref.mnemonic
    taint = set()
    if mn in ("mov", "movzx", "movsx", "add"):
        taint.add(r64(ref, ref.operands[0].reg))
    elif mn == "mul":
        taint |= {"rax", "rdx"}
    flags = mn in ("add", "mul", "cmp", "test")
    uses = []
    work = [(ref.address + ref.size, frozenset(taint), flags, ref.address)]
    seen = set()
    steps = 0
    cut = False
    while work:
        pc, t, fl, setter = work.pop()
        while True:
            steps += 1
            if steps > 3000:
                cut = True
                break
            if (pc, t, fl) in seen or (not t and not fl):
                break
            seen.add((pc, t, fl))
            i = dis(pc)
            if i.mnemonic == "nop" or i.mnemonic.startswith("prefetch"):
                pc += i.size        # an alignment nop's [rax+rax] addresses nothing
                continue
            rr, ww = i.regs_access()
            rd = {r64(i, r) for r in rr} - {None}
            wr = {r64(i, r) for r in ww} - {None}
            hit = rd & t
            addr = set()
            for op in i.operands:
                if op.type == X.X86_OP_MEM:
                    for r in (op.mem.base, op.mem.index):
                        if r:
                            addr.add(r64(i, r))
            txt = "%s %s" % (i.mnemonic, i.op_str)
            if FLAG_READ.match(i.mnemonic) and fl:
                uses.append(Use("flag", pc, txt, setter, None))
            if hit & addr and i.mnemonic != "lea":
                uses.append(Use("index", pc, txt, None, None))
            if hit:
                if i.mnemonic.startswith("cvt"):
                    uses.append(Use("cvt", pc, txt, None, None))
                elif i.mnemonic.startswith("mov") and i.operands[0].type == X.X86_OP_MEM:
                    uses.append(Use("store", pc, txt, None, mem_desc(i, i.operands[0])))
                elif i.mnemonic in ("div", "idiv"):
                    uses.append(Use("div", pc, txt, None, None))
                elif i.mnemonic == "sub" and len(i.operands) == 2 and \
                        i.operands[1].type == X.X86_OP_MEM:
                    uses.append(Use("sub_mem", pc, txt, None, mem_desc(i, i.operands[1])))
                else:
                    uses.append(Use("op", pc, txt, None, None))
            if writes_flags(i):
                fl, setter = (True, pc) if hit else (False, setter)
            nt = set(t)
            ops = i.operands
            if i.mnemonic in ("xor", "sub") and len(ops) == 2 and ops[0].type == X.X86_OP_REG \
                    and ops[1].type == X.X86_OP_REG and ops[0].reg == ops[1].reg:
                nt.discard(r64(i, ops[0].reg))
            elif i.mnemonic in ("cmp", "test") or FLAG_READ.match(i.mnemonic) and \
                    i.mnemonic.startswith("j"):
                pass
            elif hit - addr or (hit and i.mnemonic == "lea"):
                nt |= wr
            else:
                nt -= wr
            if i.mnemonic == "call":
                live = t & set(ARGS)
                if live:
                    tgt = ops[0].imm if ops and ops[0].type == X.X86_OP_IMM else None
                    if tgt is None or any(callee_reads(img, funcs, tgt, r) for r in live):
                        uses.append(Use("callarg", pc, txt, None, sorted(live)))
                nt -= VOLATILE
                fl = False
            if i.mnemonic == "ret":
                if "rax" in t:
                    uses.append(Use("return", pc, txt, None, None))
                break
            t = frozenset(nt)
            if i.mnemonic == "jmp":
                if ops[0].type == X.X86_OP_IMM:
                    pc = ops[0].imm
                    continue
                if t:
                    uses.append(Use("escape", pc, txt, None, None))
                break
            if i.mnemonic.startswith("j") and ops and ops[0].type == X.X86_OP_IMM:
                work.append((ops[0].imm, t, fl, setter))
            if i.mnemonic == "int3":
                break
            pc += i.size
    return uses, cut


def flags_consumer(dis, a):
    """The branch that reads the flags an instruction at `a` sets, following
    instructions that leave the flags alone and unconditional jumps. None if
    something overwrites them first."""
    pc = a + dis(a).size
    for _ in range(12):
        i = dis(pc)
        if i.mnemonic.startswith("j") and i.mnemonic != "jmp":
            return i
        if i.mnemonic == "jmp" and i.operands[0].type == X.X86_OP_IMM:
            pc = i.operands[0].imm
            continue
        if writes_flags(i) or i.mnemonic in ("call", "ret", "jmp"):
            return None
        pc += i.size
    return None


# ---------------------------------------------------------------------------
# 3. what a gate computes, by running it
# ---------------------------------------------------------------------------

JCC = {
    "je": lambda f: f & 0x40, "jne": lambda f: not f & 0x40,
    "jb": lambda f: f & 1, "jae": lambda f: not f & 1,
    "jbe": lambda f: f & 0x41, "ja": lambda f: not f & 0x41,
    "js": lambda f: f & 0x80, "jns": lambda f: not f & 0x80,
    "jl": lambda f: bool(f & 0x80) != bool(f & 0x800),
    "jge": lambda f: bool(f & 0x80) == bool(f & 0x800),
    "jle": lambda f: f & 0x40 or bool(f & 0x80) != bool(f & 0x800),
    "jg": lambda f: not f & 0x40 and bool(f & 0x80) == bool(f & 0x800),
}
UREG = {n: getattr(U, "UC_X86_REG_" + n.upper()) for n in
        "rax rbx rcx rdx rsi rdi rbp r8 r9 r10 r11 r12 r13 r14 r15 "
        "eax ebx ecx edx esi edi ebp r8d r9d".split()}


class Emu:
    """main.dll mapped at its preferred base, for running short snippets of it."""
    STACK = 0x10000000

    def __init__(self, img):
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        size = (len(img) + 0xFFF) & ~0xFFF
        mu.mem_map(BASE, size, UC_PROT_ALL)
        mu.mem_write(BASE, bytes(img))
        mu.mem_map(self.STACK - 0x10000, 0x20000, UC_PROT_ALL)
        self.img = img

    def run(self, start, until, fc=None, regs=None, seed=0, code=None):
        """Run start..until (exclusive); EFLAGS and the registers afterwards."""
        mu = self.mu
        saved = []
        for a, b in (code or []):
            saved.append((a, bytes(mu.mem_read(BASE + a, len(b)))))
            mu.mem_write(BASE + a, b)
        mu.ctl_flush_tb()
        for n in ("rax rbx rcx rdx rsi rdi rbp r8 r9 r10 r11 r12 r13 r14 r15").split():
            mu.reg_write(UREG[n], (seed * 0x9E3779B97F4A7C15 + hash(n)) & 0xFFFFFFFF)
        mu.reg_write(U.UC_X86_REG_RSP, self.STACK)
        for n, v in (regs or {}).items():
            mu.reg_write(UREG[n], v)
        if fc is not None:
            mu.mem_write(BASE + FC, struct.pack("<I", fc & 0xFFFFFFFF))
        try:
            mu.emu_start(BASE + start, BASE + until, count=64)
            err = None
        except UcError as e:
            err = str(e)
        out = {"err": err, "flags": mu.reg_read(U.UC_X86_REG_EFLAGS),
               "rip": mu.reg_read(U.UC_X86_REG_RIP) - BASE}
        for n in UREG:
            out[n] = mu.reg_read(UREG[n])
        for a, b in reversed(saved):
            mu.mem_write(BASE + a, b)
        mu.ctl_flush_tb()
        return out


def taken_set(emu, dis, start, jcc_at, xs, via=None, seeds=(1, 2)):
    """For each x: does the branch at jcc_at take, with x in the counter (or, with
    via=reg, in that register)? None if the answer depends on anything but x."""
    j = dis(jcc_at)
    cond = JCC.get(j.mnemonic)
    if cond is None:
        return None
    res = []
    for x in xs:
        outs = set()
        for s in seeds:
            r = emu.run(start, jcc_at, fc=None if via else x,
                        regs={via: x} if via else None, seed=s)
            if r["err"] or r["rip"] != jcc_at:
                return None
            outs.add(bool(cond(r["flags"])))
        if len(outs) != 1:
            return None
        res.append(outs.pop())
    return res


def period_of(bits):
    """(P, residues on the minority side, that side) of a periodic bool list"""
    n = len(bits)
    for p in range(1, n // 3 + 1):
        if all(bits[x] == bits[x % p] for x in range(n)):
            side = sum(bits[:p]) * 2 <= p
            return p, [x for x in range(p) if bits[x] == side], side
    return None, None, None


# ---------------------------------------------------------------------------
# 4. classification
# ---------------------------------------------------------------------------

def divisor_source(dis, div_at):
    """what a div's divisor register was last set from, looking back a few
    instructions: ("fps",) / ("global", rva) / ("other", text)"""
    d = dis(div_at)
    reg = r64(d, d.operands[0].reg) if d.operands[0].type == X.X86_OP_REG else None
    for p in reversed(dis.before(div_at, 10)):
        _rr, ww = p.regs_access()
        if reg in {r64(p, r) for r in ww}:
            mops = [o for o in p.operands if o.type == X.X86_OP_MEM]
            if mops:
                t = rip_target(p, mops[0])
                if t == FPS:
                    return ("fps",)
                if t is not None:
                    return ("global", t)
            if p.mnemonic in ("shr", "sar", "and"):
                continue       # shaping the value it already holds
            if p.mnemonic == "mov" and p.operands[1].type == X.X86_OP_REG:
                reg = r64(p, p.operands[1].reg)
                continue
            return ("other", "%s %s" % (p.mnemonic, p.op_str))
    return ("other", "?")


def global_writers(refs_all, g):
    return [i for i in refs_all if any(
        o.type == X.X86_OP_MEM and o.access & capstone.CS_AC_WRITE and
        rip_target(i, o) == g for o in i.operands)]


def gate_probe(dis, ins, setter):
    """(start, branch) of the straight-line code that decides a modulo gate: from
    the read (or, for `mul [counter]`, from the magic constant loaded into eax
    before it) to the branch on the compare. Emulating start..branch with a
    counter value says whether the gate fires for it."""
    start = ins.address
    if ins.mnemonic == "mul":
        for p in dis.before(ins.address, 8):
            if p.mnemonic == "mov" and p.op_str.startswith("eax, 0x") and \
                    int(p.op_str.split(",")[1], 16) >= 0x80000000:
                start = p.address
    return start, flags_consumer(dis, setter).address


def pointer_uses(dis, img, funcs, lea):
    """Where a `lea reg, [counter]` pointer is dereferenced below +4 (the counter
    itself) or handed to a function that reads it, following the register and
    anything derived from it by lea/mov/add through both directions of every
    branch."""
    bad = []
    work = [(lea.address + lea.size, frozenset({r64(lea, lea.operands[0].reg)}))]
    seen = set()
    steps = 0
    while work:
        pc, t = work.pop()
        while t and (pc, t) not in seen and steps < 5000:
            steps += 1
            seen.add((pc, t))
            i = dis(pc)
            nt = set(t)
            if not (i.mnemonic == "nop" or i.mnemonic.startswith("prefetch")):
                for op in i.operands:
                    if op.type == X.X86_OP_MEM and r64(i, op.mem.base) in t and \
                            i.mnemonic != "lea" and op.mem.disp < 4:
                        bad.append("%X %s %s" % (pc, i.mnemonic, i.op_str))
                _rr, ww = i.regs_access()
                wr = {r64(i, r) for r in ww} - {None}
                src = [o for o in i.operands[1:] if o.type in (X.X86_OP_REG, X.X86_OP_MEM)]
                derives = i.mnemonic in ("lea", "mov", "add") and src and (
                    (src[0].type == X.X86_OP_MEM and i.mnemonic == "lea" and
                     r64(i, src[0].mem.base) in t) or
                    (src[0].type == X.X86_OP_REG and r64(i, src[0].reg) in t))
                if derives:
                    nt |= wr
                elif not (i.mnemonic == "add" and i.operands[0].type == X.X86_OP_REG and
                          r64(i, i.operands[0].reg) in t):
                    nt -= wr
            if i.mnemonic == "call":
                live = nt & set(ARGS)
                tgt = i.operands[0].imm if i.operands[0].type == X.X86_OP_IMM else None
                if live and (tgt is None or any(callee_reads(img, funcs, tgt, r) for r in live)):
                    bad.append("%X passes it to %s" % (pc, i.op_str))
                nt -= VOLATILE
            if i.mnemonic in ("ret", "int3"):
                break
            if i.mnemonic == "jmp":
                if i.operands[0].type != X.X86_OP_IMM:
                    if nt:
                        bad.append("%X escapes through %s" % (pc, i.op_str))
                    break
                pc, t = i.operands[0].imm, frozenset(nt)
                continue
            if i.mnemonic.startswith("j") and i.operands[0].type == X.X86_OP_IMM:
                work.append((i.operands[0].imm, frozenset(nt)))
            t = frozenset(nt)
            pc += i.size
    return bad


def classify(img, funcs, refs, leas, covered, emu, dis, all_mem_writes):
    rows = {}

    def row(ins, cls, evidence, **kw):
        r = {"rva": ins.address, "insn": "%s %s" % (ins.mnemonic, ins.op_str),
             "len": ins.size, "fn": function_of(funcs, ins.address), "cls": cls,
             "evidence": evidence}
        r.update(kw)
        rows[ins.address] = r
        return r

    # the pointer routes: every dereference must be at +4 or beyond
    for ins in leas:
        if ins.address in POINTER_ROUTES:
            row(ins, "address", POINTER_ROUTES[ins.address])
            continue
        bad = pointer_uses(dis, img, funcs, ins)
        # a derived element pointer left in r8 at a one-parameter call: read by
        # hand in gen_shadow_mode.py, and checked by its bytes here too
        hand = SHADOW_ROUTES.get(ins.address)
        if bad and hand and all(bytes(img[r:r + len(b)]) == b for r, b in hand[2]) and \
                all("passes it to" in b for b in bad):
            row(ins, "address", "base of the flag block; %s (gen_shadow_mode.py)" % hand[1])
            continue
        if bad:
            row(ins, "unresolved", "lea of the counter dereferenced near it: " + "; ".join(bad))
        else:
            row(ins, "address", "base of the flag block after the counter: every dereference"
                                " is at +0x680 or beyond")

    # elapsed families: globals the value is subtracted from
    slices = {}
    for ins in refs:
        op = next(o for o in ins.operands if o.type == X.X86_OP_MEM)
        if op.access & capstone.CS_AC_WRITE:
            continue
        if ins.mnemonic in ("mov", "movzx", "movsx", "add", "mul"):
            slices[ins.address] = slice_value(dis, img, funcs, ins)
    stamps = {}
    for a, (uses, _cut) in slices.items():
        for u in uses:
            if u.kind == "sub_mem" and u.extra[0] == "g":
                stamps.setdefault(u.extra[1], set()).add(a)
    elapsed = set(stamps)

    for ins in refs:
        a = ins.address
        op = next(o for o in ins.operands if o.type == X.X86_OP_MEM)
        if op.access & capstone.CS_AC_WRITE:
            if ins.mnemonic == "inc" and function_of(funcs, a) == TICK_FN:
                row(ins, "tick", "flower_tick's own increment: the per-tick hook goes here")
            else:
                row(ins, "writer", "writes the counter (objScroll's init bumps it by one and"
                                   " back around a loop that does not read it)")
            continue
        if a in covered:
            row(ins, "covered", covered[a])
            continue
        if ins.mnemonic == "test":
            imm = ins.operands[1].imm if ins.operands[1].type == X.X86_OP_IMM else None
            j = flags_consumer(dis, a)
            if imm in MASKS and j is not None:
                row(ins, "widen", "test [counter], 0x%X -> %s at %X (a gate every %d ticks)"
                    % (imm, j.mnemonic, j.address, imm + 1),
                    imm_off=ins.size - 1, mask=imm)
            else:
                row(ins, "unresolved", "memory test without a plain branch on it")
            continue
        if ins.mnemonic == "cmp":
            # the second read of `mul [counter]; ...; cmp [counter], eax`
            prev = [p for p in dis.before(a, 4) if p.mnemonic == "mul" and
                    any(o.type == X.X86_OP_MEM and rip_target(p, o) == FC for o in p.operands)]
            if prev:
                row(ins, "pair", "second read of the modulo gate at %X" % prev[-1].address,
                    partner=prev[-1].address)
            else:
                row(ins, "unresolved", "compare of the counter with no multiply before it")
            continue
        uses, cut = slices[a]
        k = collections.Counter(u.kind for u in uses)
        summary = ", ".join("%s %d" % kv for kv in sorted(k.items()))
        setters = sorted({u.setter for u in uses if u.kind == "flag"})
        stores = [u for u in uses if u.kind == "store"]
        ops = [u.text for u in uses]
        if cut:
            row(ins, "unresolved", "slice too long: " + summary)
            continue
        # snapshot: compared with a stored copy, and stored
        snap = []
        for s in setters:
            si = dis(s)
            if si.mnemonic == "cmp" and any(o.type == X.X86_OP_MEM for o in si.operands):
                snap.append(s)
        if snap and stores:
            row(ins, "snapshot", "compared with a stored copy at %s and stored: 'already ran"
                " this frame' (%s)" % (",".join("%X" % s for s in snap), summary))
            continue
        # elapsed family
        fam = {u.extra[1] for u in uses if u.kind == "sub_mem" and u.extra[0] == "g"}
        fam |= {u.extra[1] for u in stores if u.extra[0] == "g" and u.extra[1] in elapsed}
        if fam:
            touch = [u.at for u in uses if u.kind in ("sub_mem", "store") and
                     u.extra[0] == "g" and u.extra[1] in fam]
            row(ins, "retarget U", "elapsed-time family of %s: %s" % (
                ",".join("main+%X" % g for g in sorted(fam)), summary), family=sorted(fam),
                touches=touch)
            continue
        if any(u.extra == ("g", FC) for u in stores):
            row(ins, "writer", "read-increment-store of the counter (objScroll's init bump)")
            continue
        # buffer parity: `& 1` then an address scaled by a buffer size
        if any(t.startswith("and") and t.endswith(", 1") for t in ops) and \
                any(re.match(r"(imul \w+, \w+, 0x[0-9a-f]{5,}|shl \w+, 0x1[0-9a-f])", t)
                    for t in ops):
            row(ins, "buffer parity", "counter & 1 picks one of two per-frame buffers (%s)"
                % summary)
            continue
        # the layout flipbook's parity gate (F6)
        prevs = dis.before(a, 3)
        guarded = any(p.mnemonic == "cmp" and p.operands[0].type == X.X86_OP_MEM and
                      rip_target(p, p.operands[0]) == MODE for p in prevs)
        if guarded and any(re.match(r"and \w+, 1$", t) for t in ops):
            row(ins, "mode parity (F6)", "(counter & 1) in mode 1 only: the layout flipbook's"
                " parity gate, family F6 (%s)" % summary)
            continue
        if stores and not (k["flag"] or k["cvt"] or k["index"] or k["div"]):
            row(ins, "stamp", "stored to %s and nothing else; no read of the counter"
                " subtracts it" % ", ".join("[%s+0x%X]" % (s.extra[1], s.extra[2])
                                             if s.extra[0] == "m" else "main+%X" % s.extra[1]
                                             for s in stores))
            continue
        # register mask gate
        tests = []
        for s in setters:
            si = dis(s)
            if si.mnemonic == "test" and si.operands[1].type == X.X86_OP_IMM and \
                    si.operands[1].imm in MASKS and si.operands[0].type == X.X86_OP_REG:
                tests.append(si)
        divs = [(u.at, divisor_source(dis, u.at)) for u in uses if u.kind == "div"]
        if tests:
            if len(tests) != 1:
                row(ins, "unresolved", "several mask tests: %s" % summary)
                continue
            t = tests[0]
            j = flags_consumer(dis, t.address)
            note = ""
            if divs:
                note = "; on the other path the value also reaches a div by %s, which" \
                       " widening the test does not touch" % "/".join(
                           "the fps byte" if d[1][0] == "fps" else str(d[1]) for d in divs)
            row(ins, "widen", "value -> test %s, 0x%X -> %s at %X (a gate every %d ticks)%s" % (
                t.reg_name(t.operands[0].reg), t.operands[1].imm, j.mnemonic, j.address,
                t.operands[1].imm + 1, note), gate=t)
            continue
        if divs and all(d[1][0] == "fps" for d in divs):
            row(ins, "fps throttle", "counter %% (fps / 2): real time already (%s)" % summary)
            continue
        if divs and all(d[1][0] == "global" for d in divs) and not (k["cvt"] or k["index"]):
            g = divs[0][1][1]
            if not all_mem_writes.get(g):
                row(ins, "debug divider", "counter %% main+%X, which nothing writes (a stripped"
                    " debug divider that is always 0 and skipped)" % g)
                continue
        # modulo gates
        mul = [u for u in uses if u.text.startswith("mul ")] or \
            ([Use("op", a, "mul", None, None)] if ins.mnemonic == "mul" else [])
        if a in MIXED:
            row(ins, "retarget H", "mixed: %s" % MIXED[a]["what"], mixed=MIXED[a],
                period=MIXED[a]["P"], event=MIXED[a]["e"], summary=summary)
            continue
        if mul and setters:
            gate_setters = [s for s in setters if dis(s).mnemonic in ("cmp", "test", "sub")]
            if k["cvt"] or k["index"] or len(gate_setters) != 1:
                row(ins, "unresolved", "modulo with other consumers, not in MIXED: %s" % summary)
                continue
            start, jat = gate_probe(dis, ins, gate_setters[0])
            j = dis(jat)
            bits = taken_set(emu, dis, start, j.address, range(0, 2160))
            if bits is None:
                row(ins, "unresolved", "modulo gate that does not emulate from %X" % start)
                continue
            P, res, side = period_of(bits)
            if P is None or len(res) != 1:
                row(ins, "unresolved", "gate fires on %s of every %s" % (res, P))
                continue
            row(ins, "retarget H", "x %% %d == %d: %s at %X %s (measured over 2160 values)"
                % (P, res[0], j.mnemonic, j.address,
                   "taken" if side else "falls through"), period=P, event=res[0])
            continue
        # a cycle: (counter >> s) & m, with every branch on the value after that
        # reduction -- a selection among the cycle's values, not an event
        shr = [u.at for u in uses if re.match(r"shr \w+, (0x)?[0-9a-f]+$", u.text)]
        msk = [u.at for u in uses if re.match(r"and \w+, (1|3|7|0xf|0x1f|0x3f)$", u.text)]
        if shr and msk and min(shr) < min(msk) and all(s > min(msk) for s in setters):
            row(ins, "retarget S", "cycle: (counter >> s) & m at %X/%X, then %s"
                % (min(shr), min(msk), summary))
            continue
        # phase: conversions and indices, no branch on the value
        if k["cvt"] or k["index"]:
            if setters:
                row(ins, "unresolved", "phase with branches on it: %s" % summary)
                continue
            row(ins, "retarget S", "phase: %s" % summary)
            continue
        row(ins, "unresolved", summary or "no consumer found")

    # pairs take their partner's class
    for a, r in rows.items():
        if r["cls"] == "pair":
            p = rows.get(r["partner"])
            if p and p["cls"] == "retarget H":
                r.update(cls="retarget H", period=p["period"], event=p["event"],
                         evidence=r["evidence"] + ": " + p["evidence"])
            else:
                r["cls"] = "unresolved"
    return rows


def check_mixed(emu, dis, rows):
    """Prove each MIXED decision against the code. Returns problems."""
    probs = []
    for a, r in rows.items():
        m = r.get("mixed")
        if not m:
            continue
        P, e = m["P"], m["e"]
        if m["value"]:
            start, end, reg = m["value"]
            bad = [x for x in range(0, 6 * P)
                   if (emu.run(start, end, fc=x)[reg] & 0xFFFFFFFF) != x % P]
            if bad:
                probs.append("%06X: %s after %X..%X is not x %% %d (x=%d)"
                             % (a, reg, start, end, P, bad[0]))
            xs = range(P)       # the branches test the remainder
        else:
            xs = range(6 * P)   # the branches test the counter itself

        def fires(piece):
            bits = taken_set(emu, dis, piece[0], piece[1], xs, via=piece[2])
            if bits is None:
                return None, None
            side = sum(bits) * 2 <= len(bits)
            return sorted({x % P for x, b in zip(xs, bits) if b == side}), side

        ev, _ = fires(m["event"])
        if ev != [e]:
            probs.append("%06X: the event at %X fires on %s (mod %d), want [%d]"
                         % (a, m["event"][1], ev, P, e))
        for rp in m["repeats"]:
            got, _ = fires(rp)
            if got is None or len(got) != 1 or got == [e]:
                probs.append("%06X: the repeat at %X fires on %s" % (a, rp[1], got))
        if m["windows"]:
            inside = set()
            for w in m["windows"]:
                bits = taken_set(emu, dis, w[0], w[1], xs, via=w[2])
                if bits is None:
                    probs.append("%06X: the window test at %X does not emulate" % (a, w[1]))
                    continue
                inside |= {x % P for x, b in zip(xs, bits) if b}
            if (e in inside) != ((e - 1) % P in inside):
                probs.append("%06X: the window %s holds %d but not %d (or the reverse)"
                             % (a, sorted(inside), e, (e - 1) % P))
            m["window_set"] = sorted(inside)
    return probs


# ---------------------------------------------------------------------------
# 5. the hook site
# ---------------------------------------------------------------------------

def check_tick(img, dis, targets, rows):
    ticks = [r for r in rows.values() if r["cls"] == "tick"]
    if len(ticks) != 1:
        return None, ["%d increments of the counter in flower_tick, want 1" % len(ticks)]
    r = ticks[0]
    a, n = r["rva"], r["len"]
    probs = []
    if n < 5:
        probs.append("the increment is %d bytes, a jump needs 5" % n)
    inside = sorted(t for t in targets if a < t < a + n)
    if inside:
        probs.append("branches land inside the increment: %s" % inside)
    # rsp is 16-aligned at the next call (the ABI), and nothing between moves it
    pc, moved = a + n, []
    for _ in range(16):
        i = dis(pc)
        if i.mnemonic == "call":
            break
        if i.mnemonic in ("push", "pop") or (i.mnemonic in ("sub", "add") and
                                              i.op_str.startswith("rsp")):
            moved.append("%X %s" % (pc, i.mnemonic))
        pc += i.size
    else:
        probs.append("no call within 16 instructions after the increment")
    if moved:
        probs.append("rsp moves before the next call: %s" % moved)
    r["evidence"] += "; %d bytes, nothing branches into it, rsp 16-aligned (the call at %X)" % (
        n, pc)
    return r, probs


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    img, secs, funcs, sha = load_image()
    refs, leas, problems, targets, riprefs, bounds = sweep(img, secs)
    print("main.dll sha1 %s: %d instructions read or write the frame counter, %d lea of it"
          % (sha, len(refs), len(leas)))
    for p in problems:
        print("  OTHER ROUTE %06X %s" % p)
    dis = Dis(img, bounds)
    emu = Emu(img)
    covered = covered_rvas()
    writes = {t: [a for a, w in v if w] for t, v in riprefs.items()}
    rows = classify(img, funcs, refs, leas, covered, emu, dis, writes)
    probs = check_mixed(emu, dis, rows)
    tick, tprobs = check_tick(img, dis, targets, rows)
    probs += tprobs
    # an elapsed family must be closed: every access to one of its stamps is an
    # instruction the slices of its members reached
    reached = collections.defaultdict(set)
    for r in rows.values():
        for g in r.get("family", []):
            reached[g] |= set(r.get("touches", []))
    for g, seen in reached.items():
        others = sorted(a for a, _w in riprefs.get(g, []) if a not in seen)
        if others:
            probs.append("stamp main+%X is also accessed at %s, outside its family"
                         % (g, ", ".join("%X" % a for a in others)))
        else:
            print("elapsed stamp main+%X: all %d accesses are in the family"
                  % (g, len(riprefs.get(g, []))))

    counts = collections.Counter(r["cls"] for r in rows.values())
    print(", ".join("%s %d" % (c, counts[c]) for c in CLASS_ORDER if counts[c]))
    for c in CLASS_ORDER:
        for a in sorted(rows):
            r = rows[a]
            if r["cls"] == c and c not in ("covered",):
                print("  %-16s %06X %-44s %s" % (c, a, r["insn"][:44], r["evidence"]))

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["site", "function", "instruction", "class", "slot", "evidence"])
        for a in sorted(rows):
            r = rows[a]
            slot = ""
            if r["cls"] == "retarget H":
                slot = "H(%d,%d)" % (r["period"], r["event"])
            elif r["cls"] in ("retarget S", "retarget U"):
                slot = r["cls"][-1]
            wr.writerow(["%06X" % a, "%06X" % (r["fn"] or 0), r["insn"], r["cls"], slot,
                         r["evidence"]])

    bad = [r for r in rows.values() if r["cls"] == "unresolved"]
    if bad or probs or problems:
        print("\nNOT WRITING %s: %d unresolved, %d problems, %d other routes"
              % (os.path.relpath(OUT_H, ROOT), len(bad), len(probs), len(problems)))
        for r in bad:
            print("  %06X %s: %s" % (r["rva"], r["insn"], r["evidence"]))
        for p in probs:
            print("  " + p)
        return 1

    holds = sorted({(r["period"], r["event"]) for r in rows.values()
                    if r["cls"] == "retarget H"})
    slot_of = {"retarget S": 0, "retarget U": 1}
    reads, gates = [], []
    for a in sorted(rows):
        r = rows[a]
        if r["cls"].startswith("retarget"):
            ins = dis(a)
            slot = slot_of.get(r["cls"])
            if slot is None:
                slot = 2 + holds.index((r["period"], r["event"]))
            op = next(o for o in ins.operands if o.type == X.X86_OP_MEM)
            assert op.mem.base == X.X86_REG_RIP and ins.disp_offset
            d = ins.disp_offset
            assert ins.address + ins.size + struct.unpack_from("<i", img, a + d)[0] == FC
            assert ins.size <= 8
            reads.append((a, ins.size, d, slot, img[a:a + ins.size], r))
        elif r["cls"] == "widen":
            t = r.get("gate") or dis(a)
            assert t.operands[-1].type == X.X86_OP_IMM and t.size <= 8
            imm_off = t.size - 1
            assert img[t.address + imm_off] == t.operands[-1].imm
            gates.append((t.address, t.size, imm_off, t.operands[-1].imm,
                          img[t.address:t.address + t.size], r, a))
    fn_name = {}
    for r in rows.values():
        fn_name[r["rva"]] = "%06X" % (r["fn"] or 0)

    def hexb(b, n=8):
        return ", ".join("0x%02X" % x for x in (bytes(b) + bytes(n - len(b))))

    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generated by tools/gen_frame_clocks.py -- do not edit by hand.\n")
        f.write("// main.dll sha1 %s\n" % sha)
        f.write("//\n// Family F5: the frame counter main+%X read as\n"
                "// a clock, in the encodings frame_gates.h and frame_phases.h do not cover.\n"
                "// docs/animation/frame_clocks.csv has every one of the %d references to the\n"
                "// counter, its class and the evidence.\n//\n"
                "// kFrameClockReads: a read retargeted, by its rip displacement alone, at a\n"
                "// counter slot the per-tick hook keeps:\n"
                "//   slot 0  S       the counter at the stock rate of the current context\n"
                "//   slot 1  U       the counter in 60 Hz-configuration ticks\n"
                "//   slot 2+ H(P,e)  S with residue e (mod P) held back by one on the ticks of\n"
                "//                   a stock tick after its first (kFrameClockHolds)\n"
                "// kFrameClockGates: a mask test whose immediate is widened, as frame_gates.h.\n"
                "// kFrameClockTick: flower_tick's increment of the counter, where the hook goes.\n"
                "// kFrameClockStamps: the globals U's elapsed family stores U in and subtracts\n"
                "// from it -- every access to them is a member of the family -- which the\n"
                "// hook rebases whenever U changes coordinates or rate.\n"
                % (FC, len(rows)))
        f.write("#pragma once\n#include <cstdint>\n\n")
        f.write('#define FRAME_CLOCKS_MAIN_SHA1 "%s"\n' % sha)
        f.write("static const uint32_t kFrameClockCounterRva = 0x%X;\n" % FC)
        f.write("static const uint32_t kFrameClockTickRva = 0x%X;\n" % tick["rva"])
        f.write("static const uint8_t kFrameClockTickOrig[%d] = {%s};  // %s\n\n" % (
            tick["len"], hexb(img[tick["rva"]:tick["rva"] + tick["len"]], tick["len"]),
            tick["insn"]))
        f.write("struct FrameClockHold {\n    uint16_t period;\n    uint16_t event;\n};\n\n")
        f.write("static const FrameClockHold kFrameClockHolds[] = {\n")
        for i, (P, e) in enumerate(holds):
            who = sorted({fn_name[r[0]] for r in reads if r[3] == 2 + i})
            f.write("    {%d, %d},  // slot %d: %s\n" % (P, e, 2 + i, " ".join(who)))
        f.write("};\n\n")
        f.write("struct FrameClockRead {\n    uint32_t rva;\n    uint8_t len;\n"
                "    uint8_t dispOff;\n    uint8_t slot;\n    uint8_t orig[8];\n};\n\n")
        f.write("static const FrameClockRead kFrameClockReads[] = {\n")
        for a, n, d, slot, raw, r in reads:
            what = r["mixed"]["what"] if r.get("mixed") else r["evidence"].split(":")[0]
            f.write("    {0x%06X, %d, %d, %d, {%s}},  // in %s: %s\n" % (
                a, n, d, slot, hexb(raw), fn_name[a], what[:70]))
        f.write("};\n\n")
        f.write("struct FrameClockGate {\n    uint32_t rva;     // the test instruction\n"
                "    uint8_t len;\n    uint8_t immOff;   // where its mask byte sits\n"
                "    uint8_t mask;     // the stock mask\n    uint8_t orig[8];\n};\n\n")
        f.write("static const FrameClockGate kFrameClockGates[] = {\n")
        for t, n, io, mask, raw, r, ref in gates:
            f.write("    {0x%06X, %d, %d, 0x%02X, {%s}},  // in %s: every %d frames (read at %X)\n"
                    % (t, n, io, mask, hexb(raw), fn_name[ref], mask + 1, ref))
        f.write("};\n\n")
        u_stamps = sorted({g for r in rows.values() if r["cls"] == "retarget U"
                           for g in r.get("family", [])})
        f.write("static const uint32_t kFrameClockStamps[] = {\n")
        for g in u_stamps:
            f.write("    0x%X,  // %d accesses, all in the family\n"
                    % (g, len(riprefs.get(g, []))))
        f.write("};\n")
    print("\nwrote %s (%d reads, %d hold counters, %d gates, hook at %X) and %s" % (
        os.path.relpath(OUT_H, ROOT), len(reads), len(holds), len(gates), tick["rva"],
        os.path.relpath(OUT_CSV, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
