#!/usr/bin/env python3
"""Find the enemies' own clocks.

An enemy (every em* class) keeps its speed in +1080: 1.0, or 0.25 and 0.6
while something slows it (23A1C5, 2809E9). Its state timers count in its own
time: each update, a float field loses (or gains) the speed,

    movss xmm0, dword ptr [rcx + 0x1438]    ; the timer
    xorps xmm1, xmm1
    comiss xmm0, xmm1
    jbe   done                               ; while it is above 0:
    subss xmm0, dword ptr [rcx + 0x1080]    ;   - speed
    movss dword ptr [rcx + 0x1438], xmm0    ;   stored back

and the enemy's state (a wind-up, a stun, how long it stays hidden) ends when
it crosses a threshold. Some add the speed times its motion factor (+F54,
the product the motion advance 4B9C80 is given as a rate, which it multiplies
by the time scale):

    movss xmm0, dword ptr [rdi + 0x1080]
    mulss xmm0, dword ptr [rdi + 0xf54]     ; this tick's step
    addss xmm0, xmm1                         ; xmm1: the field, loaded before
    movss dword ptr [rdi + 0x53a4], xmm0

Nothing in the port scales either, so at 120 every such state lasts a quarter
of stock's. The tracer's session saw two of them run (2412BD, 247F66: -1 and
-0.0007 a tick, both "clock"), and the static classification calls the rest
per-tick clocks.

This sweeps .text for both shapes, each proven on a run of code that nothing
enters from outside (no branch target, switch destination or data reference
of an address inside it, from tools/gen_tracer.global_pass), with no call,
ret or jmp in it and no other write of the registers; a conditional branch
may leave it:

  src    `subss/addss xmmD, dword ptr [B + 0x1080]`, xmmD loaded from
         [B + D] (movss, or movups/movaps whose low lane is the field)
         before it and stored to [B + D] after it, nothing else touching
         xmmD, and B unchanged: the world animations' srcx kind, the speed
         scaled by s as it is applied (no register borrowed). The result is
         the field's next value on every path (a compare of it with zero
         included);
  dst    `mulss xmmR, dword ptr [B + 0xF54]` right after xmmR was loaded from
         [B + 0x1080], then `addss xmmR, xmmF` with xmmF loaded from [B + D],
         and xmmR stored to [B + D]: the dst kind, the step scaled after the
         multiply.

gen_world_anims.py takes the sites as its "actor" group.

The census (main) classifies every read of the speed in the enemies' code
into docs/animation/actor_steps.csv: clock and step (here), move and vchange
(tools/find_actor_motion.py: a move by the speed, a velocity's change placed
on one tick of each stock period), motion (a move not built, and why), and
what the other reads do (turn, steer, approach, rate, other).

    .venv/Scripts/python tools/find_actor_clocks.py     (prints the census)
"""
import bisect
import collections
import os
import sys

import capstone
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_turn_callers as gtc  # noqa: E402

SPEED, FACTOR = 0x1080, 0xF54
WINDOW = 12
LOADS = ("movss", "movups", "movaps")
ENDS = ("call", "ret", "jmp")


def _mem(i):
    return next((op for op in i.operands if op.type == X.X86_OP_MEM), None)


def _field(i, base):
    """the displacement of a plain [base + disp] operand, else None"""
    m = _mem(i)
    if m is None or m.mem.base != base or m.mem.index or m.mem.segment:
        return None
    return m.mem.disp


def _stores_reg_to(s, base, d, reg):
    return s.mnemonic == "movss" and len(s.operands) == 2 and \
        s.operands[0].type == X.X86_OP_MEM and _field(s, base) == d and \
        s.operands[1].type == X.X86_OP_REG and s.reg_name(s.operands[1].reg) == reg


class Sweep:
    def __init__(self, img, secs):
        import gen_tracer as tr
        self.img, self.secs = img, secs
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        lo, hi = secs[".text"]
        starts, targets, switch, _tables = tr.global_pass(img, lo, hi)
        # every address control can arrive at other than by falling through
        self.entries = targets | switch | tr.data_references(img, secs, lo, hi, starts)

    def clean(self, run, reg, base_key, last=None):
        """nothing in run (or at `last`, the instruction that ends it) is
        entered from outside; nothing in run calls, jumps away for good or
        writes reg or the base register (a conditional branch may leave)"""
        if last is not None and last.address in self.entries:
            return False
        for j in run:
            if j.address in self.entries or j.mnemonic in ENDS or j.mnemonic.startswith("loop"):
                return False
            w = gtc.writes(j)
            if reg in w or base_key in w:
                return False
        return True

    def store_after(self, after, base, d, reg, bkey):
        for a, s in enumerate(after):
            if _stores_reg_to(s, base, d, reg):
                return s if self.clean(after[:a], reg, bkey, s) else None
            if reg in gtc.writes(s) or s.mnemonic in ENDS:
                return None
        return None

    def src(self, ins, k, i, base, bkey, reg):
        before, after = ins[max(0, k - WINDOW):k], ins[k + 1:k + 1 + WINDOW]
        for b in range(len(before) - 1, -1, -1):
            j = before[b]
            if reg not in gtc.writes(j):
                continue
            d = _field(j, base) if j.mnemonic in LOADS and \
                j.operands[0].type == X.X86_OP_REG else None
            if d is None or d == SPEED or not self.clean(before[b + 1:], reg, bkey, i):
                return None
            s = self.store_after(after, base, d, reg, bkey)
            return (d, j.address, s.address) if s is not None else None
        return None

    def dst(self, ins, k, i, base, bkey, reg):
        if k == 0:
            return None
        j = ins[k - 1]
        if not (j.mnemonic in LOADS and _field(j, base) == SPEED and
                j.operands[0].type == X.X86_OP_REG and j.reg_name(j.operands[0].reg) == reg):
            return None
        after = ins[k + 1:k + 1 + WINDOW]
        for a, s in enumerate(after):
            if s.mnemonic == "addss" and s.operands[0].type == X.X86_OP_REG and \
                    s.reg_name(s.operands[0].reg) == reg and s.operands[1].type == X.X86_OP_REG:
                if not self.clean(after[:a], reg, bkey, s) or i.address in self.entries:
                    return None
                src = s.reg_name(s.operands[1].reg)
                load = next((j2 for j2 in reversed(ins[max(0, k - WINDOW):k + 1 + a])
                             if src in gtc.writes(j2)), None)
                d = _field(load, base) if load is not None and load.mnemonic in LOADS else None
                if d is None or d in (SPEED, FACTOR):
                    return None
                st = self.store_after(after[a + 1:], base, d, reg, bkey)
                return (d, load.address, st.address) if st is not None else None
            if reg in gtc.writes(s) or s.mnemonic in ENDS:
                return None
        return None

    def run(self):
        """[(rva, kind, instruction text, field disp, load rva, store rva)]"""
        lo, hi = self.secs[".text"]
        out = []
        pos = lo
        while pos < hi:
            end = min(hi, pos + 0x10000)
            ins = list(self.md.disasm(bytes(self.img[pos:end + 64]), pos))
            last = pos
            for k, i in enumerate(ins):
                if i.address >= end:
                    break
                last = i.address + i.size
                if i.mnemonic not in ("subss", "addss", "mulss") or len(i.operands) != 2:
                    continue
                m = i.operands[1]
                if i.operands[0].type != X.X86_OP_REG or m.type != X.X86_OP_MEM or \
                        m.mem.index or not m.mem.base or m.mem.base == X.X86_REG_RIP:
                    continue
                base = m.mem.base
                bkey = gtc.reg_key(i, base)
                reg = i.reg_name(i.operands[0].reg)
                got, kind = None, None
                if i.mnemonic in ("subss", "addss") and m.mem.disp == SPEED:
                    got, kind = self.src(ins, k, i, base, bkey, reg), "srcx"
                elif i.mnemonic == "mulss" and m.mem.disp == FACTOR:
                    got, kind = self.dst(ins, k, i, base, bkey, reg), "dst"
                if got:
                    out.append((i.address, kind, "%s %s" % (i.mnemonic, i.op_str)) + got)
            pos = last if last > pos else pos + 1
        return sorted(set(out))


# ---------------------------------------------------------------------------
# the other steps an enemy paces by its speed
# ---------------------------------------------------------------------------
# The enemies' own code: em00..em8f's updates and helpers (the RTTI vtables'
# functions and what only they call fill these two ranges; the player, the
# villagers and the scenery live elsewhere)
ENEMY_CODE = ((0x238000, 0x2DA000), (0x5C0000, 0x5F6000))
# fields a step may be multiplied by besides constants: the speed itself and
# the motion factor (both in stock units per tick, survey_turn_limits.py)
STEP_FIELDS = {SPEED: "the speed", FACTOR: "the motion factor"}
PURE_MATH = ("sinf", "cosf")
RATE = {0xB6AC38: "time scale", 0xB6AC45: "mode byte", 0xB6AC44: "fps byte",
        0xB6AC40: "60 fps flag"}
# Functions holding a step that read a rate global somewhere, read by hand:
# why that read does not select the step. A read of the 60 fps flag that
# tools/survey_flag_reads.py proves is only a rumble's length (rumble_read:
# on every path only the shift of r8d at a call of cPad::ActSet) needs none.
STEP_RATE_REVIEWED = {}
FLAG60 = 0xB6AC40


def math_thunks(img, secs):
    """{thunk rva: name} of the CRT's sinf and cosf: `jmp [IAT]` stubs"""
    import gen_world_anims as gwa
    iat = gwa.iat_names()
    lo, hi = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    out = {}
    for i in md.disasm(bytes(img[0x65D000:0x65E000]), 0x65D000):
        if i.mnemonic == "jmp" and i.op_str.startswith("qword ptr [rip +"):
            name = iat.get(i.address + i.size + int(i.op_str.split("+ ")[1].rstrip("]"), 16))
            if name in PURE_MATH:
                out[i.address] = name
    return out


class Steps:
    """Every read of the speed in the enemies' code whose value is, on every
    path, only this tick's step of one field: scaled at the read, it scales
    the step (tools/step_flow.py proves the flow).

      movss/movups/movaps xmmD, [B + 0x1080]   the speed loaded (a vector
                load's low lane): kind `step`, xmmD scaled right after;
      mulss xmmD, [B + 0x1080]   a factor times the speed: `step`, the product
                scaled right after; the factor is checked like the others;
      addss/subss xmmD, [B + 0x1080]   a field plus or minus the speed, the
                field loaded from one place and the sum stored back there:
                `srcx`, as the clocks.

    Every factor the step is multiplied or divided by must be an .rdata
    constant, a field in STEP_FIELDS, or sinf/cosf of anything (a shape, not a
    rate). A read whose value is anything else on some path (a turn helper's
    limit: the steer and turn groups; a compare) is not a step and stays. A
    step times a velocity field is find_actor_motion's (Motion.scalar)."""

    def __init__(self, img, secs, clocks=()):
        import step_flow
        self.sf = step_flow
        self.img, self.secs = img, secs
        self._seeded = None
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.roots, self.starts, _e = gtc.pdata_roots(img, secs)
        self.clocks = set(clocks)
        self.math = math_thunks(img, secs)
        self.pr = gtc.patched_ranges()
        self.pstarts = [r[0] for r in self.pr]
        self.fcache = {}

    def func(self, at):
        k = bisect.bisect_right(self.starts, at) - 1
        frag = self.starts[k] if k >= 0 else None
        if frag is None or not any(b <= at < e for b, e in self.roots[frag][1]):
            return None
        root, frags = self.roots[frag]
        if root not in self.fcache:
            self.fcache[root] = gtc.Func(self.img, root, frags, self.md)
        return self.fcache[root]

    def rumble(self, fn, a):
        """the 60 fps flag read at `a` is only a rumble's length"""
        import survey_flag_reads
        return survey_flag_reads.rumble_read(fn, a) is None

    def iat(self):
        """{IAT slot rva: import name}"""
        if not hasattr(self, "_iat"):
            import gen_world_anims as gwa
            self._iat = gwa.iat_names()
        return self._iat

    def rate_seeded(self):
        """{field disp: (rate global, store rva)} for every float store in the
        enemies' code whose value's slice reads a rate global or a mode table:
        a field the port keeps in real time (in some class, on some path)"""
        if self._seeded is not None:
            return self._seeded
        self._seeded = {}
        roots = sorted({r for r, _f in self.roots.values()
                        if any(lo <= r < hi for lo, hi in ENEMY_CODE)})
        for root in roots:
            fn = self.func(root)
            sl = None
            for a in fn.order:
                i = fn.ins[a]
                ops = i.operands
                if i.mnemonic != "movss" or len(ops) != 2 or ops[0].type != X.X86_OP_MEM or \
                        ops[1].type != X.X86_OP_REG or \
                        ops[0].mem.base in (0, X.X86_REG_RIP, X.X86_REG_RSP):
                    continue
                d = ops[0].mem.disp
                if d in self._seeded:
                    continue
                sl = sl or gtc.Slicer(self.img, self.secs, fn)
                for x in gtc.leaves(sl.value(a, gtc.reg_key(i, ops[1].reg))):
                    if x[0] == "rate" or x[0] in ("table", "tablefixed"):
                        self._seeded[d] = (x[2] if x[0] == "rate" else "a mode table", "%X" % a)
                        break
        return self._seeded

    def factor_ok(self, fl, i, idx):
        """None if operand idx of i (its value before i) is a constant, a
        STEP_FIELDS field, or sinf/cosf's result; else why not"""
        op = i.operands[idx]
        if op.type == X.X86_OP_MEM:
            t = gtc.rip_target(i, op)
            if t is not None:
                return None if fl.sl.section(t) == ".rdata" else "a factor from %X" % t
            leaves = [("field", i.address, None, op.mem.disp)]
        else:
            leaves = list(gtc.leaves(fl.sl.value(i.address, gtc.reg_key(i, op.reg))))
        for x in leaves:
            if x[0] == "const" and x[2] is not None:
                continue
            if x[0] == "field" and x[3] in STEP_FIELDS:
                continue
            if x[0] == "callret":
                c = fl.fn.ins.get(x[1])
                if c is not None and c.operands[0].type == X.X86_OP_IMM and \
                        c.operands[0].imm in self.math:
                    continue
            return "a factor %s at %X" % (gtc.render(x), i.address)
        return None

    def prove(self, at, factor_ok=None, sink_ok=None):
        """(kind, field disp, store rvas, None) for a step read at `at`, or
        (None, None, None, why not). find_actor_motion.Motion.scalar passes its
        own factor rule (a velocity field may be a factor) and sink rule (the
        field stepped, from its stores' keys: `sink_ok(flow, at, stores)`, which
        replaces the time-scale check here)."""
        fn = self.func(at)
        if fn is None or at not in fn.ins:
            return None, None, None, "not a decoded instruction of a function"
        i = fn.ins[at]
        m = i.mnemonic
        ops = i.operands
        if len(ops) != 2 or ops[0].type != X.X86_OP_REG or ops[1].type != X.X86_OP_MEM or \
                ops[1].mem.disp != SPEED or ops[1].mem.index:
            return None, None, None, "not a read of the speed into a register"
        reg = gtc.reg_key(i, ops[0].reg)
        fl = self.sf.Flow(self.img, self.secs, fn, self.md)
        factors_before = []
        if m in LOADS:
            kind, roles = "step", {reg: ("step",)}
        elif m == "mulss":
            kind, roles = "step", {reg: ("step",)}
            factors_before = [(at, 0)]
        elif m in ("addss", "subss"):
            f = fl.field_value(at, reg)
            if f is None:
                return None, None, None, "%s does not hold one field" % reg
            kind, roles = "srcx", {reg: ("sum", f)}
        else:
            return None, None, None, "%s reads the speed" % m
        stores, factors, why = fl.run(at + i.size, roles)
        if why:
            return None, None, None, why
        for fa, idx in factors_before + sorted(factors):
            why = (factor_ok or self.factor_ok)(fl, fn.ins[fa], idx)
            if why:
                return None, None, None, why
        disps = sorted({k[1] for _s, k in stores})
        if len(disps) != 1:
            return None, None, None, "accumulates into %d fields" % len(disps)
        if sink_ok is not None:
            why = sink_ok(fl, at, stores)
            if why:
                return None, None, None, why
        elif disps[0] in self.rate_seeded():
            return None, None, None, "+%X is also written from %s (%s): a quantity the port " \
                "compensated somewhere" % ((disps[0],) + self.rate_seeded()[disps[0]])
        touched = {at} | fl.visited | {x for x in fl.sl.touched if x in fn.ins}
        clock = sorted(touched & self.clocks)
        if clock:
            return None, None, None, "the actor clock at %X scales it already" % clock[0]
        pat = sorted({gtc.patched_by(self.pr, self.pstarts, x, fn.ins[x].size)
                      for x in touched} - {None, "world_anims.h", "world_anims.h call"})
        if pat:
            return None, None, None, "already patched by " + ", ".join(pat)
        reads = []
        for a in fn.order:
            for op in fn.ins[a].operands:
                if op.type == X.X86_OP_MEM:
                    t = gtc.rip_target(fn.ins[a], op)
                    if t == FLAG60 and self.rumble(fn, a):
                        continue
                    if t in RATE:
                        reads.append("%X %s" % (a, RATE[t]))
        if reads and fn.root not in STEP_RATE_REVIEWED:
            return None, None, None, "its function reads %s" % ", ".join(reads[:3])
        return kind, disps[0], sorted(s for s, _k in stores), None

    def run(self):
        """[(rva, kind, text, field disp, stores)] and {rva: why not} for every
        read of +1080 in ENEMY_CODE that is not a clock"""
        out, refused = [], {}
        roots = sorted({r for r, _f in self.roots.values()
                        if any(lo <= r < hi for lo, hi in ENEMY_CODE)})
        for root in roots:
            fn = self.func(root)
            for a in fn.order:
                i = fn.ins[a]
                op = next((o for o in i.operands if o.type == X.X86_OP_MEM), None)
                if op is None or op.mem.disp != SPEED or op.mem.index or \
                        not op.mem.base or op.mem.base == X.X86_REG_RIP or \
                        not op.access & capstone.CS_AC_READ or a in self.clocks:
                    continue
                kind, disp, stores, why = self.prove(a)
                if why:
                    refused[a] = why
                else:
                    out.append((a, kind, "%s %s" % (i.mnemonic, i.op_str), disp, stores))
        return sorted(out), refused


def step_sites(img, secs, clocks, st=None):
    """the manifest rows of the enemies' other steps"""
    own = owners()
    rows = []
    st = st or Steps(img, secs, clocks)
    found, _refused = st.run()
    for rva, kind, text, d, stores in found:
        fn = st.func(rva).root
        who = " ".join(w for w in own.get("%X" % stores[0], "").split() if not w.startswith("+"))
        rows.append(("actor", kind, rva, text, None,
                     "%s: +%X stepped by a multiple of the speed(+1080) a tick in %X (store%s "
                     "%s)" % (who[:40] or "unowned", d, fn, "s" if len(stores) > 1 else "",
                              ", ".join("%X" % s for s in stores))))
    return rows


def owners():
    """{store rva: the classes the static site table assigns it}"""
    import csv
    path = os.path.join(os.path.dirname(HERE), "docs", "animation", "sites.csv")
    return {r["site"]: r["owners"] for r in csv.DictReader(open(path, encoding="utf-8"))}


def sites(img=None, secs=None):
    """the manifest rows for gen_world_anims.py: (group, kind, rva, text, None, reason)"""
    if img is None:
        img, secs, _f, _sha = gtc.load_image()
    own = owners()
    roots, starts, _e = gtc.pdata_roots(img, secs)
    rows = []
    for rva, kind, text, d, load, store in Sweep(img, secs).run():
        k = bisect.bisect_right(starts, rva) - 1
        fn = roots[starts[k]][0] if k >= 0 else 0
        who = " ".join(w for w in own.get("%X" % store, "").split() if not w.startswith("+"))
        what = ("-=" if text.startswith("subss") else "+=") if kind == "srcx" else "+="
        step = "speed(+1080)" if kind == "srcx" else "speed(+1080) x motion factor(+F54)"
        rows.append(("actor", kind, rva, text, None,
                     "%s: clock +%X %s %s a tick in %X (load %X, store %X)" % (
                         who[:40] or "unowned", d, what, step, fn, load, store)))
    return rows


# what a call the speed reaches does with it
CALLEES = {0x20E210: "turn", 0x20E290: "turn", 0x2DDF90: "steer", 0x2DA570: "steer",
           0x23A2E0: "steer", 0x2DA510: "approach", 0x4B9C80: "rate", 0x2DA410: "motion",
           0x20EA30: "motion", 0x20ED50: "motion", 0x239420: "motion", 0x2DA3D0: "motion"}


def disposition(st, why):
    """What a read of the speed that is no step does instead, from the flow's
    refusal: its class in docs/animation/actor_steps.csv. turn: a limit of
    20E210/20E290 (the turn group); steer: of 2DDF90, 2DA570 or 23A2E0 (the
    steer group, or left there); approach: 2DA510's k (FixTurnRate); rate:
    the motion factor's product, which 4B9C80 multiplies by the time scale;
    clock: an actor clock scales it; motion: a displacement, a velocity or a
    rate field (not yet); other: anything else (a compare, a copy)."""
    import re
    m = re.search(r"(?:at the call at|leaves the function at) ([0-9A-F]+)", why)
    if m:
        a = int(m.group(1), 16)
        fn = st.func(a)
        i = fn.ins.get(a) if fn is not None else None
        if i is not None and i.mnemonic == "call" and i.operands[0].type == X.X86_OP_MEM:
            # flower_kernel's vector math: a velocity scaled by the speed, moved by
            if "cVec" in (st.iat().get(gtc.rip_target(i, i.operands[0])) or ""):
                return "motion"
        t = i.operands[0].imm if i is not None and i.mnemonic == "call" and \
            i.operands[0].type == X.X86_OP_IMM else a
        return CALLEES.get(t, "other")
    if re.search(r"\+ 0xf54\]", why):
        return "rate"
    if re.search(r"\+ 0xe(48|4c|50|54)\]", why):
        return "motion"
    if "already" in why:
        return "clock"
    if why.startswith("a factor") or "compensated" in why:
        return "motion"
    return "other"


def main():
    import csv
    img, secs, _f, _sha = gtc.load_image()
    rows = sites(img, secs)
    c = collections.Counter(r[1] for r in rows)
    fns = {r[5].split(" in ")[1].split()[0] for r in rows}
    print("actor clocks: %d sites in %d functions (%s)" % (
        len(rows), len(fns), ", ".join("%d %s" % (n, k) for k, n in c.items())))
    for r in rows:
        print("  %X %-4s %-42s %s" % (r[2], r[1], r[3], r[5]))
    st = Steps(img, secs, [r[2] for r in rows])
    found, refused = st.run()
    print("actor steps: %d sites (%s); %d other reads of the speed in the enemies' code (%s)" % (
        len(found), ", ".join("%d %s" % (n, k) for k, n in
                              collections.Counter(f[1] for f in found).items()),
        len(refused), ", ".join("%d %s" % (n, k) for k, n in collections.Counter(
            disposition(st, w) for w in refused.values()).most_common())))
    # the motion (tools/find_actor_motion.py): the moves, the velocities'
    # changes, and why each other move is not built
    import find_actor_motion
    _mo, mrows, mrefused = find_actor_motion.census(img, secs, st, rows)
    moved = {r[0]: r for r in mrows}
    print("actor motion: %d reads of the speed (%s), %d companions" % (
        sum(1 for a in moved if a in refused), ", ".join(
            "%d %s" % (n, k) for k, n in collections.Counter(
                moved[a][1] for a in moved if a in refused).items()),
        sum(1 for a in moved if a not in refused)))
    path = os.path.join(os.path.dirname(HERE), "docs", "animation", "actor_steps.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["site", "function", "decision", "kind", "field", "stores", "why"])
        for rva, kind, _text, d, stores in found:
            w.writerow(["%X" % rva, "%X" % st.func(rva).root, "step", kind, "+%X" % d,
                        " ".join("%X" % s for s in stores), ""])
        for rva, why in sorted(refused.items()):
            dec = disposition(st, why)
            if rva in moved:
                m = moved[rva]
                w.writerow(["%X" % rva, "%X" % st.func(rva).root,
                            "move" if m[1] == "step" else "vchange", m[1], "", "", m[3]])
                continue
            if dec == "motion" or rva in mrefused and dec == "other" and \
                    not mrefused[rva].startswith(("not ", "no path", "the step read by")):
                dec, why = "motion", mrefused.get(rva, why)
            w.writerow(["%X" % rva, "%X" % st.func(rva).root, dec, "", "", "", why])
    print("  -> %s" % os.path.relpath(path, os.path.dirname(HERE)))


if __name__ == "__main__":
    main()
