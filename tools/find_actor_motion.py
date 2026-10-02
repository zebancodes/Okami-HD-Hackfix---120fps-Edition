#!/usr/bin/env python3
"""The enemies' own motion: the reads of an
enemy's speed (+1080) that move something, and what else steps the velocities
they move by.

An enemy moves by its speed in four ways, each a step of one tick:

  move      position = matrix x (v * speed * factors): 2DA3F0 (the model's own
            matrix and position, tools/vec_flow.py), cMatrix::Apply inlined on
            a child model, 2DA410 (forward by d * speed);
  fall      20EA30/20ED50(obj, g, dt = speed): position.y += dt * vy(+E54),
            vy -= g * dt (step_flow.Flow proves, from each helper's entry, that
            dt is only those two accumulations);
  add       a field += v * speed by cVec::operator+=: a piece's position +=
            velocity * speed, its velocity += acceleration * speed.

tools/vec_flow.py proves each chain: the speed as read is, on every path, only
that step. At 120 each ran four times a stock tick with stock's step, so the
enemy (and its pieces) moved 4x as fast; the actor clocks already make each
state last its stock time, so a dash covered four times its distance.

Principle 2: the state stays in stock units and only the
application is scaled. A chain that moves a position gets the speed scaled by
s = 1/N as read (kind `step`), every tick. A velocity that changes each tick
(the pieces: vel += acc * speed, vel *= 0.92, vel += (joint - pos) * 0.008)
changes as the effect group's particles do: once per stock period, on the tick
that puts the change where stock's order does (before the position used the
velocity this tick: the period's first tick; after it: the last). Then the
position passes through stock's values at every stock tick and moves in
straight lines between them. The kinds: `zfirst`/`zlast` on the load of the
change's scalar (the speed, or a constant like the 0.008 of a pull toward a
joint), zeroed on the other ticks; `ufirst`/`ulast` on the instruction that
puts a damping factor in xmm1 for operator*=, 1.0 on the other ticks;
`countlast` on a lane's `mulss` by a constant stored back. "Before" and
"after" are read on the straight run of code that holds the change and the
move; a change between two moves of one velocity refuses.

A chain is built only when everything it moves by is in stock units and
changes only where something scales the change:

  factors and the source vector's leaves (tools/vec_flow.VecFlow.vec_leaves,
      through the kernel's constructors, copies, sums, products and the
      rotations 1BDE90/1BDED0) must be constants (.rdata, or a .data global
      nothing writes and no pointer near it escapes), the speed, the motion
      factor +F54 (the animation's own rate: the move follows the animation),
      sin/cos, or a field that is not the moved field itself and whose every
      update from itself (the RMW scan, by displacement: for the enemy's own
      fields anywhere in the enemies' code, for a piece's in its function) is
      accounted for: an actor clock or step on that lane in that function,
      another family's patch in its slice (a decay's root), one of this
      module's chains or companions, a stop (*= 0), or an event read by hand
      (EVENTS: the pieces' bounces). A field seeded from the time scale (the
      port's own compensation: +E48, +E54, +EC0, +EC8,
      find_actor_clocks.Steps.rate_seeded) refuses.
  a velocity is built whole or not at all: every move that uses it, every
      change of it and every companion, or none of them.

    .venv/Scripts/python tools/find_actor_motion.py     (prints the census)
"""
import collections
import os
import sys

import capstone
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_turn_callers as gtc  # noqa: E402
import find_actor_clocks as fac  # noqa: E402
import step_flow as sf  # noqa: E402
import vec_flow as vfm  # noqa: E402

SPEED, FACTOR = fac.SPEED, fac.FACTOR
# helpers given the step as a float argument: {target: the argument}; each is
# proven once from its entry (Motion.helper_ok: step_flow.Flow)
FALLS = {0x20EA30: "xmm2", 0x20ED50: "xmm2"}
# the velocity's height and the fall's own fields: dt's accumulations there
FALL_FIELDS = {(None, 4), (None, 0xE54)}
LOADS = ("movss", "movups", "movaps")
# Updates of a velocity from itself that happen once, when something happens,
# not every tick: read by hand. They stay as the game does them, on whatever
# tick the event falls.
EVENTS = {
    # a piece hits the ground (the height compare before; 5DD109/5DD11B play
    # the landing sound): its bounce count (byte +1) goes up and its velocity
    # bounces, y *= -0.4 and x, z *= 0.75, and x, z *= 0.2 more once +4 is set
    0x5DD14E: "a piece's bounce off the ground (5DBA90)",
    0x5DD153: "a piece's bounce off the ground (5DBA90)",
    0x5DD158: "a piece's bounce off the ground (5DBA90)",
    0x5DD17B: "a piece's bounce off the ground, once +4 is set (5DBA90)",
    0x5DD180: "a piece's bounce off the ground, once +4 is set (5DBA90)",
    0x5DD185: "a piece's bounce off the ground, once +4 is set (5DBA90)",
    # the same bounce in 281AE0: y *= -0.95, x, z *= 0.95, then 0.7 and -0.84
    0x2824C1: "a piece's bounce off the ground (281AE0)",
    0x2824C6: "a piece's bounce off the ground (281AE0)",
    0x2824CB: "a piece's bounce off the ground (281AE0)",
    0x2824EE: "a piece's bounce off the ground, once +4 is set (281AE0)",
    0x2824F3: "a piece's bounce off the ground, once +4 is set (281AE0)",
    0x2824F8: "a piece's bounce off the ground, once +4 is set (281AE0)",
    # the enemies' shared retreat (242760, 242A20: state byte +E36 0, the
    # state's first tick, which sets it to 1): +E10 = Normalize4(its position
    # - Amaterasu's), then x and z doubled (`addss x, x`), vy +E54 = 0. A
    # launch in stock units, set once; the moves by +E10/+E18 (+E18 its z,
    # or a class's own dash speed) go by it
    0x242913: "the retreat's launch, x doubled once (242760, +E36 0 -> 1)",
    0x24291B: "the retreat's launch, z doubled once (242760, +E36 0 -> 1)",
    0x242BA8: "the retreat's launch, x doubled once (242A20, +E36 0 -> 1)",
    0x242BB0: "the retreat's launch, z doubled once (242A20, +E36 0 -> 1)",
}


class Motion:
    def __init__(self, img, secs, steps, switch):
        self.img, self.secs, self.st = img, secs, steps
        self.switch = switch
        self.md = steps.md
        self.iat = steps.iat()
        self.vf = {}
        self._rmw = None
        self._globals = None
        self._helpers = {}

    # --- per function ---------------------------------------------------------
    def flow(self, fn):
        if fn.root not in self.vf:
            self.vf[fn.root] = vfm.VecFlow(self.img, self.secs, fn, self.md, self.iat,
                                           self.switch, helpers=FALLS)
        return self.vf[fn.root]

    def rmw(self):
        """{field disp: {rva: (function, base register, the slice's
        instructions)}}: every update of a field from itself in the enemies'
        code: a float store whose value's slice reads the same displacement,
        operator*=, += or -= in place on it, or a copy into it of a vector
        built from it.

        On the way it keeps self.feeds, {(disp, width): {rva}}: the other
        fields such an update reads (a velocity added to a position, a damping
        factor), and the fields of the vector a move (2DA3F0) or a forward step
        (2DA410) goes by, a float 4 wide and a vector 16. A field there is a
        rate: a step of it is a velocity's change (Motion.scalar_ok)."""
        if self._rmw is not None:
            return self._rmw
        out = collections.defaultdict(dict)
        feeds = self.feeds = collections.defaultdict(set)

        def feed(leaves, a, own=None):
            for x in leaves:
                if x[0] == "field" and x[-1] != own:
                    feeds[(x[-1], 4)].add(a)
                elif x[0] == "vfield" and x[2] != own:
                    feeds[(x[2], 16)].add(a)
        roots = sorted({r for r, _f in self.st.roots.values()
                        if any(lo <= r < hi for lo, hi in fac.ENEMY_CODE)})
        for root in roots:
            fn = self.st.func(root)
            vf = self.flow(fn)
            for a in fn.order:
                i = fn.ins[a]
                ops = i.operands
                if i.mnemonic == "movss" and ops[0].type == X.X86_OP_MEM and \
                        ops[1].type == X.X86_OP_REG and \
                        ops[0].mem.base not in (0, X.X86_REG_RIP, X.X86_REG_RSP):
                    d = ops[0].mem.disp
                    vf.sl.touched = set()
                    lv = list(gtc.leaves(vf.sl.value(a, gtc.reg_key(i, ops[1].reg))))
                    if any(x[0] == "field" and x[3] == d for x in lv):
                        out[d][a] = (root, gtc.reg_key(i, ops[0].mem.base),
                                     frozenset((x, fn.ins[x].size) for x in
                                               vf.sl.touched | {a} if x in fn.ins), d)
                        feed(lv, a, d)
                elif i.mnemonic == "call" and vf.frame.ok:
                    t = vf.callee(i)
                    if t == vfm.MOVE:
                        feed(vf._vec_ptr(a, "rdx", 0, set()), a)
                        continue
                    if t == vfm.FORWARD:
                        feed(vf._float_leaves(a, "xmm1"), a)
                        continue
                    if t not in (vfm.MULEQ, vfm.ADDEQ, vfm.SUBEQ, vfm.ASSIGN, vfm.COPY):
                        continue
                    dd = vf.dest(a, "rcx")
                    if not dd or dd[0] != "field":
                        continue
                    base = gtc.REG64.get(dd[1], dd[1])
                    if t in (vfm.MULEQ, vfm.ADDEQ, vfm.SUBEQ):
                        out[dd[2]][a] = (root, base, frozenset({(a, i.size)}), dd[2])
                        feed(vf._float_leaves(a, "xmm1") if t == vfm.MULEQ else
                             vf._vec_ptr(a, "rdx", 0, set()), a, dd[2])
                        continue
                    src = vf.addrs.reg(a, "rdx")
                    if src is not None:
                        lv = vf.vec_leaves(a, src)
                        if any(x[0] == "field" and x[2] == dd[2] for x in lv):
                            out[dd[2]][a] = (root, base, frozenset({(a, i.size)}), dd[2])
                            feed(lv, a, dd[2])
        self._rmw = dict(out)
        return self._rmw

    def self_updates(self, d):
        """{rva: (function, base, slice)} of the updates from itself of a field
        whose float or vector covers displacement d (a vector's lanes: d, d-4,
        d-8, d-C)"""
        r = self.rmw()
        out = {}
        for k in (0, 4, 8, 12):
            out.update(r.get(d - k, {}))
        return out

    def lane_updates(self, d):
        """the updates from itself of any lane of the vector at displacement d"""
        r = self.rmw()
        out = {}
        for k in (0, 4, 8, 12):
            out.update(r.get(d + k, {}))
        return out

    def accounted(self, rva, info, d=None):
        """an update from itself that something already scales: an actor clock
        or step of the same field (the lane it writes) in that function, one of
        this module's own chains or companions, an event, or another family's
        patch of an instruction in its slice"""
        root, _base, touched, disp = info
        if (root, disp) in self.clock_fields or rva in self.own or rva in EVENTS:
            return True
        return any(gtc.patched_by(self.pr, self.pstarts, x, n) not in
                   (None, "world_anims.h", "world_anims.h call") for x, n in touched)

    def const_global(self, t):
        """A .data global nothing in .text writes: no rip-relative write covers
        it, and every `lea` of an address up to 1 KiB below it (a table it may
        sit in) is only read through before its register is written again, on
        the straight-line code after it (the enemies' .data keeps small index
        tables beside their float constants)."""
        if self._globals is None:
            md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
            md.detail = True
            lo, hi = self.secs[".text"]
            writes, leas = [], []
            pos = lo
            while pos < hi:
                last = pos
                run = list(md.disasm(bytes(self.img[pos:min(hi, pos + 0x10000) + 64]), pos))
                for k, i in enumerate(run):
                    if i.address >= pos + 0x10000:
                        break
                    last = i.address + i.size
                    for op in i.operands:
                        if op.type != X.X86_OP_MEM or op.mem.base != X.X86_REG_RIP:
                            continue
                        g = gtc.rip_target(i, op)
                        if i.mnemonic == "lea":
                            leas.append((g, self._lea_reads_only(run[k:k + 24])))
                        elif op.access & capstone.CS_AC_WRITE:
                            writes.append((g, max(op.size, 1)))
                pos = last if last > pos else pos + 1
            self._globals = (writes, leas)
        writes, leas = self._globals
        if any(g < t + 4 and t < g + size for g, size in writes):
            return False
        return all(ok for g, ok in leas if g <= t < g + 0x400)

    @staticmethod
    def _lea_reads_only(run):
        """the register a `lea` (run[0]) sets is only a load's base or index
        until it is written again or the straight line ends"""
        r = gtc.reg_key(run[0], run[0].operands[0].reg)
        for i in run[1:]:
            for op in i.operands:
                if op.type == X.X86_OP_REG and gtc.reg_key(i, op.reg) == r and \
                        op.access & capstone.CS_AC_READ:
                    return False                # copied, compared, added to
                if op.type == X.X86_OP_MEM and op.access & capstone.CS_AC_WRITE and \
                        r in (gtc.reg_key(i, op.mem.base) if op.mem.base else None,
                              gtc.reg_key(i, op.mem.index) if op.mem.index else None):
                    return False                # a store through it
            if i.mnemonic == "call":
                # a callee may write through an argument, or keep a saved one
                return r in gtc.VOL_GPR and r not in ("rcx", "rdx", "r8", "r9")
            if i.mnemonic == "ret":
                return True
            if i.mnemonic.startswith("j"):
                return False
            if r in gtc.writes(i):
                return True
        return False

    # --- the leaves of what a chain moves by ------------------------------------
    def leaf_ok(self, x, c):
        """None if a leaf of a factor or of the source vector of chain c is in
        stock units and changes only where something scales its change; else
        why not. A field of the enemy itself (its base the register the speed
        was read through) counts every update from itself in the enemies'
        code; a field of a piece the function keeps (another base) those in
        the function."""
        k = x[0]
        if k == "const" or k == "sincos":
            return None
        if k == "global":
            return None if self.const_global(x[1]) else "a factor from global %X" % x[1]
        if k in ("field", "vfield", "ptr"):
            d = x[2]
            base = gtc.REG64.get(x[1], x[1]) if x[1] else None
            if d in (SPEED, FACTOR):
                return None
            if (base, d) in c["sinks_fields"]:
                return "+%X is also what it moves (a pull toward something, a blend)" % d
            seeded = self.st.rate_seeded()
            lanes = (0, 4, 8, 12) if k == "vfield" else (0, -4, -8, -12)
            if any(d + j in seeded for j in lanes):
                return "+%X is written from the time scale (%s): the port compensates it" % (
                    d, next(seeded[d + j][1] for j in lanes if d + j in seeded))
            own = base == c["enemy"]
            upd = self.lane_updates(d) if k == "vfield" else self.self_updates(d)
            left = sorted(a for a, info in upd.items()
                          if (own or (info[0] == c["root"] and info[1] == base)) and
                          not self.accounted(a, info, d))
            if left:
                return "+%X is updated from itself at %s, which nothing scales" % (
                    d, ", ".join("%X" % u for u in left[:4]))
            return None
        return "a factor %s" % (x[1] if k == "?" else str(x))

    def leaves(self, vf, factors, sources):
        """the leaves of every factor and source vector of a chain"""
        out = set()
        fn = vf.fn
        for at, src in sources:
            if src[0] == "stack":
                for x in vf.vec_leaves(at, src[1]):
                    if x[0] == "callret":
                        c = fn.ins.get(x[1])
                        x = ("sincos",) if c is not None and \
                            c.operands[0].type == X.X86_OP_IMM and \
                            c.operands[0].imm in self.st.math else ("?", "ret@%X" % x[1])
                    out.add(x)
            elif src[0] == "field":
                out.add(("vfield",) + tuple(src[1:]))
            elif src[0] == "ptr":
                out.add(src)
            else:
                out.add(("?", "the source at %X" % at))
        for fa, w in factors:
            if isinstance(w, str):
                regs = [(fa, w)]
            else:
                ins = fn.ins[fa]
                op = ins.operands[w]
                if op.type == X.X86_OP_MEM:
                    t = gtc.rip_target(ins, op)
                    if t is not None:
                        out.add(("const", t) if vf.sl.section(t) == ".rdata" else ("global", t))
                    else:
                        out.add(("field", ins.reg_name(op.mem.base), op.mem.disp))
                    continue
                regs = [(fa, gtc.reg_key(ins, op.reg))]
            for a, r in regs:
                for x in gtc.leaves(vf.sl.value(a, r)):
                    if x[0] == "const":
                        out.add(("const", x[2]) if x[2] is not None else ("const", 0))
                    elif x[0] == "field":
                        out.add(("field", x[2], x[3]))
                    elif x[0] == "global":
                        out.add(("global", x[2]))
                    elif x[0] == "callret":
                        c = fn.ins.get(x[1])
                        if c is not None and c.operands[0].type == X.X86_OP_IMM and \
                                c.operands[0].imm in self.st.math:
                            out.add(("sincos",))
                        else:
                            out.add(("?", gtc.render(x)))
                    else:
                        out.add(("?", gtc.render(x)))
        return out

    # --- one chain ----------------------------------------------------------------
    def chain(self, at):
        """Prove the read at `at` (the speed, or a companion's scalar load).
        Returns (vf, sinks, factors, sources, why)."""
        fn = self.st.func(at)
        if fn is None or at not in fn.ins:
            return None, set(), set(), set(), "not a decoded instruction of a function"
        i = fn.ins[at]
        ops = i.operands
        if len(ops) != 2 or ops[0].type != X.X86_OP_REG or \
                not i.reg_name(ops[0].reg).startswith("xmm"):
            return None, set(), set(), set(), "not a load into an xmm register"
        vf = self.flow(fn)
        reg = gtc.reg_key(i, ops[0].reg)
        factors0 = set()
        if i.mnemonic == "mulss":
            factors0.add((at, 0))
        elif i.mnemonic not in LOADS:
            return vf, set(), set(), set(), "%s is not a load" % i.mnemonic
        sinks, factors, why = vf.run(at + i.size, {reg: ("step",)})
        if why:
            return vf, sinks, factors, set(), why
        # a fall helper's other float argument (g) must be a constant
        for a, kind, what in sinks:
            if kind == "call":
                why = self.helper_ok(what) or self.helper_args_ok(vf, a, what)
                if why:
                    return vf, sinks, factors, set(), why
        return vf, sinks, factors | factors0, set(vf.sources), None

    # --- scalar moves -----------------------------------------------------------
    def scalar(self, at):
        """A read of the speed whose value is only one float field's step
        (find_actor_clocks.Steps.prove: tools/step_flow.py's flow, and the step
        finder's other checks), where a factor may be a field (a velocity lane,
        a rate): the stepped field must be the model's position through +A8
        (x, y or z; the translation row 2DA3F0 moves) or a field of the enemy
        itself. Returns a dict for scalar_ok, or (stage, why): stage "flow"
        when the value is not such a step at all, "checks" when it is and
        something else refuses it."""
        factors, sink, fls = [], [], []

        def factor(fl, i, idx):
            factors.append((i.address, idx))
            return None

        def sink_ok(fl, a, stores):
            fls.append(fl)
            got = self.scalar_sink(fl, a, stores)
            if isinstance(got, str):
                return got
            sink.append(got)
            return None
        kind, _d, stores, why = self.st.prove(at, factor_ok=factor, sink_ok=sink_ok)
        if why:
            return ("checks" if fls else "flow"), why
        fl = fls[0]
        where, d, enemy = sink[0]
        return dict(kind=kind, fl=fl, root=fl.fn.root, factors=factors, stores=stores,
                    where=where, disp=d, enemy=enemy)

    def scalar_sink(self, fl, at, stores):
        """("pos", lane, enemy) if every store goes through a pointer loaded
        from the enemy's +A8 (the enemy register the same at the speed's read
        and at that load), ("own", disp, enemy) if every store is to the enemy
        register itself, as it was at the read; else why not"""
        i = fl.fn.ins[at]
        m = next(op.mem for op in i.operands if op.type == X.X86_OP_MEM)
        enemy = gtc.reg_key(i, m.base)
        got = set()
        for s, (base, d, tag) in stores:
            if base is None:
                return "the base of +%X changes before its store at %X" % (d, s)
            loads = list(gtc.leaves(fl.sl.value(s, base)))
            if d in (0, 4, 8) and loads and all(
                    x[0] == "field" and x[3] == 0xA8 and x[2] and
                    gtc.REG64.get(x[2], x[2]) == enemy and sf.same_base(fl.sl, at, x[1], enemy)
                    for x in loads):
                got.add(("pos", d))
            elif base == enemy and tag is None and sf.same_base(fl.sl, at, s, enemy):
                got.add(("own", d))
            else:
                return "a step of +%X of %s at %X: not the enemy's own field or its position" % (
                    d, base, s)
        if len(got) != 1:
            return "steps %s" % ", ".join("%s +%X" % g for g in sorted(got))
        where, d = got.pop()
        return where, d, enemy

    def scalar_ok(self, sc, rates):
        """None if a proven scalar step (Motion.scalar) moves by stock units
        only: a field of the enemy's own that it steps is no rate (nothing
        adds it to another field or moves by it: its change would be a
        velocity's, placed on one tick of each stock period, not yet for a
        float) and not written from the time scale; each factor's leaves pass
        leaf_ok, and a factor field is the enemy's own. Else why not."""
        d, enemy = sc["disp"], sc["enemy"]
        if sc["where"] == "own":
            seeded = self.st.rate_seeded()
            hit = next((d + j for j in (0, -4, -8, -12) if d + j in seeded), None)
            if hit is not None:
                return "+%X is written from the time scale (%s): the port compensates it" % (
                    d, seeded[hit][1])
            by = sorted(a for (f, w), rs in rates.items() if f <= d < f + w
                        for a in rs if a not in sc["own"])
            if by:
                return "+%X is a rate (read by %s into another field's step or a move): " \
                    "its change is a velocity's" % (d, ", ".join("%X" % a for a in by[:3]))
        c = dict(sinks_fields={((enemy if sc["where"] == "own" else "pos"), d)},
                 enemy=enemy, root=sc["root"])
        for x in sorted(self.leaves(sc["fl"], sc["factors"], []), key=str):
            if x[0] in ("field", "vfield", "ptr") and x[2] not in (SPEED, FACTOR) and \
                    gtc.REG64.get(x[1], x[1]) != enemy:
                return "a factor from +%X of %s, not the enemy's own" % (x[2], x[1])
            why = self.leaf_ok(x, c)
            if why:
                return why
        return None

    def helper_ok(self, target):
        """the helper accumulates its dt into the position's y and +E54 only"""
        if target not in self._helpers:
            fn = self.st.func(target)
            fl = sf.Flow(self.img, self.secs, fn, self.md)
            stores, factors, why = fl.run(target, {FALLS[target]: ("step",)})
            if not why:
                keys = {(None, k[1]) for _s, k in stores}
                if keys - FALL_FIELDS:
                    why = "%X accumulates dt into %s" % (target, sorted(keys))
            if not why:
                for a, idx in factors:
                    ins = fn.ins[a]
                    op = ins.operands[idx]
                    ok = op.type == X.X86_OP_MEM and op.mem.disp == 0xE54 or \
                        op.type == X.X86_OP_REG and \
                        gtc.render(fl.sl.value(a, gtc.reg_key(ins, op.reg))) == "param(xmm1)"
                    if not ok:
                        why = "%X multiplies dt by %s %s" % (target, ins.mnemonic, ins.op_str)
            self._helpers[target] = why
        return self._helpers[target]

    def helper_args_ok(self, vf, a, target):
        for x in gtc.leaves(vf.sl.value(a, "xmm1")):
            if x[0] != "const":
                return "the fall at %X is given g = %s" % (a, gtc.render(x))
        return None

    # --- order on a straight run of code ----------------------------------------
    def order(self, vf, changes, uses):
        """True if the changes come before the moves that use the rate on
        their straight run of code (the period's first tick), False if after
        or with no use on their run (the last), None if a use precedes one
        change and follows another, or both"""
        pre = any(self.before(vf, x, u) for x in changes for u in uses)
        post = any(self.before(vf, u, x) for x in changes for u in uses)
        if pre and post:
            return None
        return pre

    def before(self, vf, a, b, limit=400):
        """b follows a on a straight run: from a, one successor at a time (a
        call's is the next instruction), without leaving the function"""
        at = a
        for _ in range(limit):
            if at == b:
                return True
            ss = vf.succ.get(at, [])
            if len(ss) != 1:
                return False
            at = ss[0]
        return False

    # --- the census -----------------------------------------------------------------
    def run(self, candidates, clock_fields):
        """candidates: the reads of the speed nothing else took. Returns
        (rows, refused): rows (rva, kind, text, why it is that kind) for the
        manifest, refused {rva: why}."""
        self.clock_fields = set(clock_fields)
        self.own = set()
        self.pr = gtc.patched_ranges()
        self.pstarts = [r[0] for r in self.pr]
        chains, refused, scalars = {}, {}, {}
        for a in candidates:
            vf, sinks, factors, sources, why = self.chain(a)
            if why:
                # a float field stepped by the speed times a field (a scalar
                # velocity lane, a rate): no vector, so tools/step_flow.py's
                # proof instead; judged below, once every chain is known
                sc = self.scalar(a)
                if isinstance(sc, dict):
                    sc["own"] = {a} | set(sc["stores"])
                    scalars[a] = sc
                elif sc[0] == "checks":
                    why = sc[1]
                refused[a] = why
                continue
            fn = vf.fn
            i = fn.ins[a]
            m = next(op.mem for op in i.operands if op.type == X.X86_OP_MEM)
            enemy = gtc.reg_key(i, m.base)
            kinds = {k for _s, k, _w in sinks}
            fields = {(gtc.REG64.get(w[1], w[1]), w[2]) for _s, k, w in sinks
                      if k in ("add", "sub")}
            chains[a] = dict(vf=vf, root=fn.root, sinks=sinks, factors=factors, sources=sources,
                             enemy=enemy, kinds=kinds, sinks_fields=fields,
                             uses={(gtc.REG64.get(s[1], s[1]), s[2]): at for at, s in sources
                                   if s[0] == "field"})
        all_chains = dict(chains)
        # a rate: a field a chain moves something by (vel, or acc for vel)
        rates = collections.defaultdict(dict)     # root -> {(base, disp): [use rvas]}
        for a, c in chains.items():
            for key, at in c["uses"].items():
                rates[c["root"]].setdefault(key, []).append(at)
        for a, c in chains.items():
            c["change"] = sorted(f for f in c["sinks_fields"] if f in rates[c["root"]])
            if c["change"] and (len(c["sinks_fields"]) != 1 or c["kinds"] - {"add", "sub"}):
                refused[a] = "changes a velocity and moves something else"
        for a in refused:
            chains.pop(a, None)
        # every update of a rate from itself in its function (each lane of the
        # vector): a chain's change, an event, or a companion placed here
        companions = {}                            # rva -> (kind, why, rate key)
        bad_rates = {}
        members = collections.defaultdict(set)     # rate key -> chains using or changing it
        for a, c in chains.items():
            for k in list(c["uses"]) + c["change"]:
                members[(c["root"],) + k].add(a)
        for root, rs in rates.items():
            vf = next(c["vf"] for c in chains.values() if c["root"] == root)
            for (base, d), uses in rs.items():
                key = (root, base, d)
                sinks_here = {s for c in chains.values() if c["root"] == root and
                              (base, d) in c["change"] for s, _k, _w in c["sinks"]}
                self.own |= sinks_here
                for x, info in sorted(self.lane_updates(d).items()):
                    if info[0] != root or info[1] != base or x in sinks_here or x in EVENTS:
                        continue
                    if self.accounted(x, info, d):
                        continue        # another family scales it already (a decay's root)
                    got = self.companion(vf, x, base, d, uses, info)
                    if isinstance(got, str):
                        bad_rates[key] = "+%X of %s: %s" % (d, base, got)
                        break
                    at, kind, why = got
                    if kind is not None:
                        companions[at] = (kind, why, key)
                    self.own.add(x)
        # what each chain moves by
        for a, c in sorted(chains.items()):
            bad = [bad_rates[(c["root"],) + k] for k in list(c["uses"]) + c["change"]
                   if (c["root"],) + k in bad_rates]
            if bad:
                refused[a] = "a velocity it uses or changes is not scaled whole: " + bad[0]
                continue
            why = next((w for w in (self.leaf_ok(x, c) for x in
                                    self.leaves(c["vf"], c["factors"], c["sources"])) if w), None)
            if why:
                refused[a] = why
        # a velocity is scaled whole or not at all: its moves, its changes and
        # its companions together
        grow = True
        while grow:
            grow = False
            for key, ms in members.items():
                if key not in bad_rates:
                    out = sorted(m for m in ms if m in refused)
                    if not out:
                        continue
                    bad_rates[key] = "+%X of %s: the chain at %X is refused (%s)" % (
                        key[2], key[1], out[0], refused[out[0]])
                for m in ms:
                    if m not in refused:
                        refused[m] = "a velocity it uses or changes is not scaled whole: " + \
                            bad_rates[key]
                        grow = True
        rows = []
        # the scalar steps: a field is a rate if an update of another field
        # reads it, a move goes by it (rmw's feeds), or any chain's factors or
        # source vectors have it (every chain, built or not)
        self.rmw()
        frates = collections.defaultdict(set)
        for k, v in self.feeds.items():
            frates[k] |= v
        for a, c in all_chains.items():
            for x in self.leaves(c["vf"], c["factors"], c["sources"]):
                if x[0] in ("field", "vfield"):     # a ptr's vector is not at +d
                    frates[(x[2], 4 if x[0] == "field" else 16)].add(a)
        for a, sc in scalars.items():
            for x in self.leaves(sc["fl"], sc["factors"], []):
                if x[0] in ("field", "vfield"):     # a ptr's vector is not at +d
                    frates[(x[2], 4 if x[0] == "field" else 16)].add(a)
        for a, sc in sorted(scalars.items()):
            why = self.scalar_ok(sc, frates)
            if why:
                refused[a] = why
                continue
            del refused[a]
            i = sc["fl"].fn.ins[a]
            what = "the model's position %s (through +A8)" % "xyz"[sc["disp"] // 4] \
                if sc["where"] == "pos" else "+%X of %s" % (sc["disp"], sc["enemy"])
            rows.append((a, sc["kind"], "%s %s" % (i.mnemonic, i.op_str),
                         "moves %s by x * speed(+1080) in %X, a float step (store%s %s)" % (
                             what, sc["root"], "s" if len(sc["stores"]) > 1 else "",
                             ", ".join("%X" % s for s in sc["stores"]))))
        for a, c in sorted(chains.items()):
            if a in refused:
                continue
            text = "%s %s" % (c["vf"].fn.ins[a].mnemonic, c["vf"].fn.ins[a].op_str)
            what = ", ".join(sorted(self.describe(s) for s in c["sinks"]))
            if c["change"]:
                key = c["change"][0]
                first = self.order(c["vf"], [s for s, _k, _w in c["sinks"]],
                                   rates[c["root"]][key])
                if first is None:
                    refused[a] = "the change of +%X sits between two moves that use it" % key[1]
                    continue
                kind = "zfirst" if first else "zlast"
                rows.append((a, kind, text, "velocity +%X of %s += x * speed(+1080) in %X "
                             "(%s), %s the move that uses it: on the %s tick of each stock "
                             "period" % (key[1], key[0], c["root"], what,
                                         "before" if first else "after",
                                         "first" if first else "last")))
            else:
                rows.append((a, "step", text, "moves by x * speed(+1080) in %X: %s" % (
                    c["root"], what)))
        for at, (kind, why, key) in sorted(companions.items()):
            if key in bad_rates:
                continue
            fn = self.st.func(at)
            i = fn.ins[at]
            rows.append((at, kind, "%s %s" % (i.mnemonic, i.op_str), why))
        self.rows = {r[0]: r for r in rows}
        self.bad_rates = bad_rates
        return rows, refused

    def describe(self, sink):
        a, k, w = sink
        if k == "move":
            return "moves %s at %X" % ("its child model" if w else "the model", a)
        if k == "forward":
            return "forward at %X" % a
        if k == "call":
            return "falls through %X at %X" % (w, a)
        return "+%X of %s %s= at %X" % (w[2], w[1], "+" if k == "add" else "-", a)

    def companion(self, vf, x, base, d, uses, info):
        """The update x of rate +d (on base) from itself, as a change this module
        places on one tick of each stock period: operator*= by a factor (ufirst/
        ulast on the instruction that puts it in xmm1), += a vector made by
        operator*(float) from a loaded scalar (zfirst/zlast on the load), or one
        lane stored back times a constant (countlast on the multiply).
        (rva, kind, why) or why not."""
        fn = vf.fn
        i = fn.ins[x]
        t = vf.callee(i) if i.mnemonic == "call" else None
        if i.mnemonic == "movss" and i.operands[0].type == X.X86_OP_MEM:
            return self.lane_companion(vf, x, base, d, uses)
        if t == vfm.MULEQ and vf.const_at(x, "xmm1") == 0.0:
            # *= 0: the rate stopped, the same on whichever tick it runs
            return x, None, "stop"
        if t == vfm.MULEQ:
            reg = "xmm1"
            defs = vf.sl.defs(x, reg)
            if len(defs) != 1 or defs[0][0] != "def":
                return "the factor of %X is not one load" % x
            load = defs[0][1]
            li = fn.ins[load]
            ok = li.mnemonic == "movss" and li.operands[1].type == X.X86_OP_MEM or \
                li.mnemonic in ("movaps", "movss") and li.operands[1].type == X.X86_OP_REG
            if not ok or not self.before(vf, load, x, 12):
                return "the factor of %X is not put in xmm1 just before it" % x
            first = self.order(vf, [x], uses)
            if first is None:
                return "%X sits between two moves that use the velocity" % x
            kind = "ufirst" if first else "ulast"
            return load, kind, "velocity +%X of %s *= %s a tick in %X (at %X), %s the move " \
                "that uses it: kept on the %s tick of each stock period, 1.0 on the others" % (
                    d, base, li.op_str.split(", ")[1], fn.root, x,
                    "before" if first else "after", "first" if first else "last")
        if t in (vfm.ADDEQ, vfm.SUBEQ):
            off = vf.addrs.reg(x, "rdx")
            if off is None:
                return "the change added at %X is not a stack vector" % x
            # the operator*(float) that made it, and its scalar's load
            p, made = x, None
            for _ in range(40):
                ps = vf.fn.preds.get(p, [])
                if len(ps) != 1:
                    break
                p = ps[0]
                pi = fn.ins[p]
                if pi.mnemonic == "call" and vf.callee(pi) == vfm.MULF and \
                        vf.addrs.reg(p, "rdx") == off:
                    made = p
                    break
            if made is None:
                return "the change added at %X is not operator*(float)'s result" % x
            defs = vf.sl.defs(made, "xmm2")
            if len(defs) != 1 or defs[0][0] != "def":
                return "the scalar of %X is not one load" % made
            load = defs[0][1]
            li = fn.ins[load]
            if li.mnemonic != "movss" or li.operands[1].type != X.X86_OP_MEM:
                return "the scalar of %X is %s %s" % (made, li.mnemonic, li.op_str)
            sinks, _factors, why = vf.run(load + li.size, {"xmm2": ("step",)})
            if why:
                return "its scalar at %X: %s" % (load, why)
            if {s for s, _k, _w in sinks} != {x}:
                return "its scalar at %X also reaches %s" % (
                    load, ", ".join("%X" % s for s, _k, _w in sinks))
            first = self.order(vf, [x], uses)
            if first is None:
                return "%X sits between two moves that use the velocity" % x
            kind = "zfirst" if first else "zlast"
            return load, kind, "velocity +%X of %s += v * %s a tick in %X (at %X), %s the " \
                "move that uses it: on the %s tick of each stock period" % (
                    d, base, li.op_str.split(", ")[1], fn.root, x,
                    "before" if first else "after", "first" if first else "last")
        return "%X %s %s" % (x, i.mnemonic, i.op_str)

    def lane_companion(self, vf, x, base, d, uses):
        """`movss [base + d'], xmmS` storing back one lane of the rate times a
        constant: xmmS was loaded from the same field and multiplied once by
        `mulss xmmS, m32` (.rdata) on the straight run before x, nothing else
        writing it. After the move that uses the rate, the multiply runs on the
        last tick of each stock period only (countlast)."""
        fn = vf.fn
        i = fn.ins[x]
        m = i.operands[0].mem
        reg = gtc.reg_key(i, i.operands[1].reg)
        want = (base, m.disp)
        load = mul = None
        at = x
        for _ in range(16):
            ps = [p for p in fn.preds.get(at, []) if p in vf.live]
            if len(ps) != 1:
                break
            at = ps[0]
            pi = fn.ins[at]
            if reg not in gtc.writes(pi):
                if pi.mnemonic in ("call", "ret") or pi.mnemonic.startswith("j"):
                    break
                continue
            ops = pi.operands
            if pi.mnemonic == "mulss" and mul is None and ops[1].type == X.X86_OP_MEM and \
                    ops[1].mem.base == X.X86_REG_RIP and \
                    vf.sl.section(gtc.rip_target(pi, ops[1])) == ".rdata":
                mul = pi
                continue
            if pi.mnemonic == "movss" and ops[1].type == X.X86_OP_MEM and \
                    (gtc.reg_key(pi, ops[1].mem.base), ops[1].mem.disp) == want and \
                    not ops[1].mem.index and sf.same_base(vf.sl, at, x, want[0]):
                load = pi
            break
        if load is None or mul is None:
            return "%X stores +%X back from something else than one constant multiply" % (
                x, m.disp)
        first = self.order(vf, [x], uses)
        if first is not False:
            return "%X damps +%X before the move that uses it" % (x, m.disp)
        return mul.address, "countlast", "velocity +%X of %s, lane +%X *= %g a tick in %X " \
            "(stored at %X), after the move that uses it: on the last tick of each stock " \
            "period only" % (d, base, m.disp, gtc.f32(self.img, gtc.rip_target(
                mul, mul.operands[1])), fn.root, x)

    def prove(self, rva):
        """(kind, None) for a row of the last run, else (None, why)"""
        r = getattr(self, "rows", {}).get(rva)
        return (r[1], None) if r else (None, "not a motion site")


def clock_fields(st, clocks, found):
    """{(function, field disp)} the actor clocks and steps already scale"""
    out = set()
    for _group, _kind, rva, _text, _extra, reason in clocks:
        out.add((int(reason.split(" in ")[1].split()[0], 16),
                 int(reason.split("clock +")[1].split()[0], 16)))
    for rva, _kind, _text, d, _stores in found:
        out.add((st.func(rva).root, d))
    return out


def census(img, secs, st=None, clocks=None):
    """(Motion, rows, refused) over every read of the speed the clocks and
    steps did not take"""
    import gen_tracer as tr
    clocks = clocks if clocks is not None else fac.sites(img, secs)
    st = st or fac.Steps(img, secs, [r[2] for r in clocks])
    _s, _t, switch, _tb = tr.global_pass(img, *secs[".text"])
    mo = Motion(img, secs, st, switch)
    found, refused = st.run()
    rows, why = mo.run(sorted(refused), clock_fields(st, clocks, found))
    return mo, rows, why


def main():
    img, secs, _f, _sha = gtc.load_image()
    mo, rows, refused = census(img, secs)
    kinds = collections.Counter(r[1] for r in rows)
    print("actor motion: %d sites (%s)" % (len(rows), ", ".join(
        "%d %s" % (n, k) for k, n in sorted(kinds.items()))))
    for r in rows:
        print("  %X %-6s %-42s %s" % (r[0], r[1], r[2], r[3]))
    print("refused: %d" % len(refused))
    for a, w in sorted(refused.items()):
        print("  %X %s" % (a, w))


if __name__ == "__main__":
    main()
