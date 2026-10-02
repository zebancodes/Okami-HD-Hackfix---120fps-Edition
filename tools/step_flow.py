#!/usr/bin/env python3
"""Where a per-tick step goes: the proof shared by the steer and actor groups
(tools/survey_turn_steps.py, tools/find_actor_clocks.py).

A step is a value this tick adds to something the object keeps: a heading
turned by clamp(angle, +-limit), an angle phase stepped by speed x K, a
position moved by speed x velocity. Scaling the step by s is right only if the
step does nothing else: it must be accumulated into one field and stored back
there, on every path, and never compared, returned, passed to a call or
stored anywhere else first. Flow.run follows the value forward through the
function's control flow graph (gen_turn_callers.Func: both sides of every
branch, loops until a state repeats) with each register in one role:

  step      the step itself, or the step times factors (mulss/divss by
            something that is not a step, a sign flip): the factors are
            returned for the caller to check, and a step may only be the
            dividend;
  sum F     F + step, F - step or step + F: the field's next value. A copy
            is a sum too; minss/maxss (a clamp) and the angle wrap 13F2E0
            keep it one, and anything may read it. Storing a sum to F
            completes the path (every copy of it is then just a value);
            losing the last copy unstored refuses;
  field F   a plain load of F seen on the way, so `addss xmm, xmmF` can be
            recognised as an accumulation.

F is a memory operand [base + disp] and the base register's value when the
field was read. A write of the base on the way (a call writes rax, rcx, rdx
and r8-r11) ends the sum's claim to F, and its store then refuses. The one
exception is a pure getter (GETTERS): a base returned by the joint lookup
20CFD0(obj, i), looked up again by the same call with the same arguments, is
the same pointer, as long as nothing on the way stores to memory (the stack
aside) or calls anything but the pure functions in PURE; every definition
of the base reaching the read must be such a call. Where the field was read
before the start (a sum handed in, a copy of F kept in a register), its base
is checked with reaching definitions (same_base), and every path back from
the start to the getter must have neither.

At a call, a step or an unstored sum in an xmm register the callee reads
before writing (callee_xmm_args: xmm0-xmm3, its first four float arguments;
any the callee might pass on unread, conservatively) refuses; in any other
volatile register it is clobbered, which ends that copy. A call or tail jump
to one of flower_kernel's vector functions reads only the float arguments
its code reads (KERNEL_XMM). Anything else refuses too: a step read by any
other instruction, a sum modified, a step in rax or xmm0 or an unstored sum
at a return (a step left in another register dies there: the x64 ABI returns
only those two), an indirect jump, a store of a step, a sum stored to another
field, an unbounded walk.
"""
import capstone
from capstone import x86_const as X

import gen_turn_callers as gtc

WRAP = 0x13F2E0         # the angle wrap to (-pi, pi]: xmm0 in, xmm0 out
# math that reads its arguments and writes nothing but registers
PURE = {0x13F2E0: "the angle wrap", 0x2DA570: "the clamped approach",
        0x2DDF90: "the clamped angle to a point", 0x20CFD0: "a model's joint by index"}
# pure lookups: the same arguments give the same pointer in rax
GETTERS = {0x20CFD0: ("rcx", "rdx")}
ARG_XMM = ("xmm0", "xmm1", "xmm2", "xmm3")
VOLATILE = {"xmm%d" % i for i in range(6)} | gtc.VOL_GPR | {"rax"}
RETURNED = ("rax", "xmm0")
COPIES = ("movaps", "movss", "movups")
SIGN = ("xorps", "andps")
BOUND = 4000
_ARGS = {}
# flower_kernel's vector functions (tools/vec_flow.py): the float arguments
# each one reads, from its code; it writes the others before any read
KERNEL_XMM = {
    "??DcVec@math@wk@@QEBA?AV012@M@Z": {"xmm2"},             # operator*(float) const
    "??XcVec@math@wk@@QEAAAEAV012@M@Z": {"xmm1"},            # operator*=(float)
    "??YcVec@math@wk@@QEAAAEAV012@AEBV012@@Z": set(),        # operator+=
    "??ZcVec@math@wk@@QEAAAEAV012@AEBV012@@Z": set(),        # operator-=
    "??0cVec@math@wk@@QEAA@MMMM@Z": {"xmm1", "xmm2", "xmm3"},  # cVec(x, y, z, w)
    "??0cVec@math@wk@@QEAA@XZ": set(),                       # cVec()
    "??0cVec@math@wk@@QEAA@AEBV012@@Z": set(),               # cVec(const cVec&)
    "??4cVec@math@wk@@QEAAAEAV012@AEBV012@@Z": set(),        # operator=
    "??GcVec@math@wk@@QEBA?AV012@AEBV012@@Z": set(),         # operator-
    "??HcVec@math@wk@@QEBA?AV012@AEBV012@@Z": set(),         # operator+
    "?Apply@cMatrix@math@wk@@SAXAEAVcVec@23@AEBV123@AEBV423@@Z": set(),
}
# {IAT slot rva: import name} of main.dll, loaded on first use: a call or tail
# jump to a kernel function reads only what KERNEL_XMM says
IAT = {}


def _iat():
    if not IAT:
        import gen_world_anims
        IAT.update(gen_world_anims.iat_names())
    return IAT


def mem_op(i):
    return next((op for op in i.operands if op.type == X.X86_OP_MEM), None)


def same_base(sl, at_a, at_b, base):
    """The base register holds the same definitions at both instructions."""
    return sorted(sl.defs(at_a, base)) == sorted(sl.defs(at_b, base))


def canon(t):
    """gen_turn_callers.render with a phi of alternatives that render alike
    collapsed to one (the same constant loaded on two paths)."""
    if t is not None and t[0] == "phi":
        alts = sorted({canon(x) for x in t[1]})
        return alts[0] if len(alts) == 1 else "phi(" + " | ".join(alts) + ")"
    if t is not None and t[0] == "op":
        return "%s(%s, %s)" % (t[2], canon(t[3]), canon(t[4]))
    if t is not None and t[0] == "conv":
        return "%s(%s)" % (t[2], canon(t[3]))
    return gtc.render(t)


def stack_or_none(i):
    """A memory write of `i` outside the stack, or None."""
    for op in i.operands:
        if op.type == X.X86_OP_MEM and op.access & capstone.CS_AC_WRITE and \
                op.mem.base != X.X86_REG_RSP:
            return op
    return None


def callee_xmm_args(img, md, target, depth=0):
    """The xmm0-xmm3 a function reads before it writes them, on some path.
    A call or jump out of it, an indirect branch or an unknown end counts as
    reading every one still unwritten."""
    if target in _ARGS:
        return _ARGS[target]
    out = set()
    work, seen = [(target, frozenset())], set()
    while work and len(seen) < 3000:
        a, written = work.pop()
        if (a, written) in seen:
            continue
        seen.add((a, written))
        try:
            i = next(md.disasm(bytes(img[a:a + 16]), a))
        except StopIteration:
            out |= set(ARG_XMM) - written
            continue
        rd, wr = gtc.reads(i), gtc.writes(i)
        out |= {r for r in ARG_XMM if r in rd and r not in written}
        written = written | {r for r in ARG_XMM if r in wr}
        m = i.mnemonic
        if m == "ret":
            continue
        kernel = None
        if m in ("call", "jmp") and i.operands[0].type == X.X86_OP_MEM and \
                i.operands[0].mem.base == X.X86_REG_RIP:
            kernel = KERNEL_XMM.get(_iat().get(gtc.rip_target(i, i.operands[0])))
        if kernel is not None:
            out |= kernel - written
            if m == "jmp":
                continue
            # the kernel function may keep what it does not read: nothing
            # counts as written after it, so a later read still counts
            work.append((a + i.size, written))
            continue
        if m == "call" or (m.startswith("j") and i.operands[0].type != X.X86_OP_IMM):
            out |= set(ARG_XMM) - written
            continue
        if m == "jmp":
            t = i.operands[0].imm
            if abs(t - a) > 0x4000:                 # a tail jump out of it
                out |= set(ARG_XMM) - written
            else:
                work.append((t, written))
            continue
        if m.startswith("j"):
            work.append((i.operands[0].imm, written))
        work.append((a + i.size, written))
    if work:
        out |= set(ARG_XMM)
    _ARGS[target] = frozenset(out)
    return _ARGS[target]


class Flow:
    def __init__(self, img, secs, fn, md=None):
        self.img, self.secs, self.fn = img, secs, fn
        self.sl = gtc.Slicer(img, secs, fn)
        if md is None:
            md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
            md.detail = True
        self.md = md

    # --- fields ------------------------------------------------------------
    def tag(self, at, base):
        """("get", X) if every definition of the base reaching `at` is a call of
        one pure getter with the same argument values (X the first of them),
        else None."""
        d = self.sl.defs(at, base)
        if base != "rax" or not d or any(k != "call" for k, _a in d):
            return None
        calls = sorted(a for _k, a in d)
        c = self.fn.ins[calls[0]]
        if c.operands[0].type != X.X86_OP_IMM or c.operands[0].imm not in GETTERS:
            return None
        if not all(self.same_getter(calls[0], x) for x in calls[1:]):
            return None
        return ("get", calls[0])

    def key(self, i, op):
        """(base, disp, tag) of a plain [base + disp] operand, not rip or rsp"""
        m = op.mem
        if not m.base or m.index or m.segment or m.base in (X.X86_REG_RIP, X.X86_REG_RSP):
            return None
        base = gtc.reg_key(i, m.base)
        return (base, m.disp, self.tag(i.address, base))

    def field_value(self, at, reg):
        """The field a register holds before `at`, if one plain load of it
        reaches `at` with the same base there: its key, else None. A base from
        a getter must reach `at` through straight-line code that stores
        nothing and calls nothing impure."""
        t = self.sl.value(at, reg)
        if t[0] != "field" or t[2] is None:
            return None
        base = gtc.REG64.get(t[2], t[2])
        if base in ("rsp", "rip") or not same_base(self.sl, t[1], at, base):
            return None
        tag = self.tag(t[1], base)
        if tag and not self.clean_back(at, base):
            return None
        return (base, t[3], tag)

    def clean_back(self, at, base):
        """Every path back from `at` to the base's definitions stores nothing
        to memory but the stack and calls nothing but PURE."""
        fn = self.fn
        defs = {a for _k, a in self.sl.defs(at, base)}
        work, seen = list(fn.preds.get(at, [])), set()
        while work:
            a = work.pop()
            if a in seen or a in defs:
                continue
            seen.add(a)
            i = fn.ins[a]
            if stack_or_none(i) is not None:
                return False
            if i.mnemonic == "call" and not (i.operands[0].type == X.X86_OP_IMM and
                                             i.operands[0].imm in PURE):
                return False
            ps = fn.preds.get(a, [])
            if not ps:
                return False
            work.extend(ps)
        return True

    def same_getter(self, x1, x2):
        """Two calls of one pure getter with the same argument values (their
        slices render alike: the same definitions and constants)."""
        c1, c2 = self.fn.ins[x1], self.fn.ins[x2]
        t1, t2 = c1.operands[0].imm, c2.operands[0].imm
        if t1 != t2 or t1 not in GETTERS:
            return False
        return all(canon(self.sl.value(x1, r)) == canon(self.sl.value(x2, r))
                   for r in GETTERS[t1])

    # --- the walk ----------------------------------------------------------
    def run(self, start, roles, bound=BOUND):
        """roles: {register: ("step",) | ("sum", key) | ("field", key)} at
        `start`. Returns (stores, factors, why): the (store address, key)
        pairs that complete the accumulation, the (address, operand index) of
        every factor the step was multiplied or divided by, and None, or why
        the flow is not a pure accumulation."""
        fn = self.fn
        stores, factors = set(), set()
        work = [(start, tuple(sorted(roles.items())))]
        seen = set()
        self.visited = set()        # every instruction a live value passed
        while work:
            a, st = work.pop()
            if (a, st) in seen:
                continue
            seen.add((a, st))
            if len(seen) > bound:
                return stores, factors, "walk exceeds %d states" % bound
            role = dict(st)
            live = {r for r, v in role.items() if v[0] in ("step", "sum")}
            if not live:
                continue
            if a not in fn.ins:
                return stores, factors, "leaves the function at %X" % a
            self.visited.add(a)
            i = fn.ins[a]
            m = i.mnemonic
            nxt = a + i.size
            if m == "call":
                why, keep = self._call(i, role, live)
                if why:
                    return stores, factors, why
                work.append((nxt, tuple(sorted(keep.items()))))
                continue
            if m in ("ret", "retf"):
                # what the caller gets back is rax and xmm0 (x64 ABI); a step
                # left in another register dies here, an unstored sum does not
                back = {r for r in live if r in RETURNED or role[r][0] == "sum"}
                if back:
                    return stores, factors, "%s live at the return at %X" % (
                        "/".join(sorted(back)), a)
                continue
            if m in ("int3", "ud2", "hlt"):
                continue
            rd, wr = gtc.reads(i), gtc.writes(i)
            new = dict(role)
            used = live & rd
            ops = i.operands
            op = mem_op(i)
            key = self.key(i, op) if op is not None else None
            dst = gtc.reg_key(i, ops[0].reg) if ops and ops[0].type == X.X86_OP_REG else None
            self._stored = None
            if used:
                why = self._use(i, role, new, used, key, factors, stores)
                if why:
                    return stores, factors, why
                set_by_use = {r for r in new if new.get(r) != role.get(r)}
            else:
                set_by_use = set()
                for r in wr:
                    new.pop(r, None)
                # a plain load of a field: remember it for `addss xmm, xmmF`
                if m in COPIES and dst and dst.startswith("xmm") and key and \
                        op.access & capstone.CS_AC_READ:
                    new[dst] = ("field", key)
                    set_by_use = {dst}
            # a write of a base register ends every claim on its fields; a store
            # to memory ends every getter's
            dirty = self._stored is None and stack_or_none(i) is not None
            for k, v in list(new.items()):
                if v[0] not in ("sum", "field") or k in set_by_use and v[0] == "field":
                    continue
                base, disp, tag = v[1]
                if base in wr - set_by_use or (dirty and tag):
                    if v[0] == "field":
                        del new[k]
                    else:
                        new[k] = ("sum", (None, disp, None))
            why = self._lost(role, new, a, self._stored)
            if why:
                return stores, factors, why
            st2 = tuple(sorted(new.items()))
            if m.startswith("j"):
                if ops[0].type != X.X86_OP_IMM:
                    return stores, factors, "indirect jump at %X" % a
                work.append((ops[0].imm, st2))
                if m != "jmp":
                    work.append((nxt, st2))
            else:
                work.append((nxt, st2))
        if not stores:
            return stores, factors, "no path stores the accumulation"
        return stores, factors, None

    def _call(self, i, role, live):
        a = i.address
        tgt = i.operands[0].imm if i.operands[0].type == X.X86_OP_IMM else None
        wrap = tgt == WRAP and role.get("xmm0", ("",))[0] == "sum"
        kernel = None
        if tgt is None and i.operands[0].type == X.X86_OP_MEM and \
                i.operands[0].mem.base == X.X86_REG_RIP:
            kernel = KERNEL_XMM.get(_iat().get(gtc.rip_target(i, i.operands[0])))
        reads = set(kernel) if kernel is not None else set(ARG_XMM) if tgt is None else \
            set(callee_xmm_args(self.img, self.md, tgt))
        args = (live & reads) - ({"xmm0"} if wrap else set())
        if args:
            return "%s live at the call at %X, which reads it" % ("/".join(sorted(args)), a), None
        keep = {r: v for r, v in role.items() if r not in VOLATILE}
        if wrap:
            keep["xmm0"] = role["xmm0"]
        for k, v in list(keep.items()):
            if v[0] not in ("sum", "field"):
                continue
            base, disp, tag = v[1]
            if base in VOLATILE:
                if tgt in GETTERS and tag and self.same_getter(tag[1], a):
                    keep[k] = (v[0], (base, disp, ("get", a)))
                    continue
            elif not (tag and tgt not in PURE):
                continue
            if v[0] == "field":
                del keep[k]
            else:
                keep[k] = ("sum", (None, disp, None))
        return self._lost(role, keep, a), keep

    @staticmethod
    def _lost(before, after, a, stored=None):
        """A sum whose every copy is gone, unstored."""
        for v in before.values():
            if v[0] == "sum" and v != stored and not any(w == v for w in after.values()):
                if not any(w[0] == "sum" and w[1][1] == v[1][1] for w in after.values()):
                    return "the next value of +%X is dropped unstored at %X" % (v[1][1], a)
        return None

    def _use(self, i, role, new, used, key, factors, stores):
        """Apply an instruction that reads a step or a sum; None, or why not."""
        a, m, ops = i.address, i.mnemonic, i.operands
        reg0 = gtc.reg_key(i, ops[0].reg) if ops and ops[0].type == X.X86_OP_REG else None
        reg1 = gtc.reg_key(i, ops[1].reg) if len(ops) > 1 and ops[1].type == X.X86_OP_REG \
            else None
        r0, r1 = role.get(reg0, ("",)), role.get(reg1, ("",))
        text = "%X %s %s" % (a, m, i.op_str)
        # a copy: the destination takes the source's role
        if m in COPIES and reg0 and reg1 and reg1 in used:
            new[reg0] = r1
            return None
        # a store of a sum to its own field completes the path
        if m == "movss" and ops[0].type == X.X86_OP_MEM and reg1 in used:
            if r1[0] == "sum" and key is not None and r1[1] == key:
                stores.add((a, key))
                self._stored = r1
                for k, v in list(new.items()):
                    if v == r1:
                        del new[k]
                return None
            if r1[0] == "sum" and r1[1][0] is None and key and key[1] == r1[1][1]:
                return "the base of +%X changed before the store at %X" % (key[1], a)
            return "a %s stored to another place at %s" % (r1[0], text)
        if m in ("mulss", "divss") and reg0 in used and r0[0] == "step" and reg1 not in used:
            factors.add((a, 1))
            return None
        if m == "mulss" and reg1 in used and r1[0] == "step" and reg0 not in used:
            factors.add((a, 0))           # the step times a factor held in reg0
            new[reg0] = r1
            return None
        if m in SIGN and reg0 in used and r0[0] == "step" and ops[1].type == X.X86_OP_MEM and \
                ops[1].mem.base == X.X86_REG_RIP:
            return None                   # a sign flip or abs: still the step's size
        if m in ("addss", "subss"):
            if reg0 in used and r0[0] == "step" and reg1 not in used:
                if m == "subss":
                    return "step - x at %s: not an accumulation" % text
                f = key if ops[1].type == X.X86_OP_MEM else self._field_in(i, reg1, role)
                if f is None:
                    return "step + something not a field at %s" % text
                new[reg0] = ("sum", f)
                return None
            if reg1 in used and r1[0] == "step" and reg0 not in used:
                f = self._field_in(i, reg0, role)
                if f is None:
                    return "a step added to something not a field at %s" % text
                new[reg0] = ("sum", f)
                return None
            return "the step or sum modified at %s" % text
        if m in ("minss", "maxss") and reg0 in used and r0[0] == "sum" and reg1 not in used:
            return None                   # a clamp of the next value
        if all(role[r][0] == "sum" for r in used) and not (gtc.writes(i) & set(used)):
            return None                   # the next value read (a compare): its own business
        return "%s read by %s" % ("/".join(sorted(used)), text)

    def _field_in(self, i, reg, role):
        r = role.get(reg)
        if r and r[0] == "field":
            return r[1]
        if r and r[0] in ("step", "sum"):
            return None
        return self.field_value(i.address, reg)
