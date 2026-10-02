#!/usr/bin/env python3
"""Where a per-tick step goes through the kernel's vectors: the enemies'
motion, shared by tools/find_actor_clocks.py.

tools/step_flow.py follows a step through registers, and refuses at the first
call that reads it. The enemies move by vectors: flower_kernel's cVec, 16
bytes, passed by pointer. A move by the speed is

    movss xmm2, [rbx + 0x1080]      ; the speed
    lea   rdx, [rsp + 0x50]         ; the result's slot
    lea   rcx, [rbx + 0x1cb0]       ; a velocity
    call  cVec::operator*(float)    ; [rsp+50].xyz = v.xyz * speed, .w = 1
    movss xmm2, [rbx + 0xf54]       ; the motion factor
    lea   rdx, [rsp + 0x40]
    mov   rcx, rax                  ; rax = the result's address
    call  cVec::operator*(float)    ; [rsp+40] = [rsp+50] * factor
    lea   rdx, [rsp + 0x40]
    mov   rcx, rbx
    call  2DA3F0                    ; position = matrix x [rsp+40]

and a piece's position += velocity x speed is operator*(float) and then
operator+=(const cVec&) on the field. Every such chain is linear in the speed:
the kernel's operator*(float) makes out.xyz = this.xyz * f and out.w the
default vector's w, 1 (its code; the default is (0, 0, 0, 1), set by the
kernel's static initializer); operator*=(float) scales xyz and keeps w;
operator+= adds xyz and keeps w; cMatrix::Apply(out, M, v) is out = v.x M0 +
v.y M1 + v.z M2 + v.w M3. 2DA3F0 applies the model's own matrix (+50..+8F)
to v and writes the result to [+A8], which cModel's constructor (211BC0)
points at +80, the matrix's translation row: with v.w = 1 that is position +=
M3x3 v, a move by v. 2DA410(obj, d) is the same with v = (0, 0, d, 1): forward
by d. So the speed scaled by s at its read scales the move by s, exactly as a
scalar step's accumulation.

VecFlow.run proves it the way step_flow does, over every path of the
function's control flow, with the step's vector copies in stack slots:

  step     a register holding the step or the step times factors (mulss/divss
           by a non-step, a sign flip): the factors are returned to be checked;
  vstep    a 16-byte stack slot holding a vector linear in the step (xyz), made
           by operator*(float) from a step and any vector, or from a vstep and
           a factor, or by cVec(x, y, z, w) from steps and zeros; scaled in
           place by operator*=(float) and a factor. Its w is known to be 1 when
           it comes from operator*(float), or from the constructor with w 1.0.

A vstep's sinks: operator+= or operator-= into something not on the stack (a
field; the kind of accumulation step_flow allows), 2DA3F0 with w = 1, and a
step passed to 2DA410. Anything else reading a vstep slot refuses: a memory
operand overlapping it (a full 16-byte store ends it), a call given its
address other than as above, a call given its address inside it; so does a
step read by anything but a factor, a step in an xmm argument the callee
reads, a step returned, an indirect jump, a stack address stored to memory.

Stack slots are named by their offset from the entry rsp (Frame): the body's
rsp and a frame pointer rbp are computed from the root's prologue, and a
function whose rsp or rbp changes outside its prologue and epilogues gets no
frame (every vstep then refuses). Which registers hold a stack address at each
instruction comes from a forward dataflow over the whole function (lea, copies,
the kernel's returned pointers), so a `lea rdx, [rsp+0x50]` before the speed's
read counts.
"""
import capstone
from capstone import x86_const as X

import gen_turn_callers as gtc
import step_flow as sf

# flower_kernel's vector functions, by import name
MULF = "??DcVec@math@wk@@QEBA?AV012@M@Z"            # out(rdx).xyz = this(rcx).xyz * xmm2, w 1
MULEQ = "??XcVec@math@wk@@QEAAAEAV012@M@Z"          # this(rcx).xyz *= xmm1, w kept
ADDEQ = "??YcVec@math@wk@@QEAAAEAV012@AEBV012@@Z"   # this(rcx).xyz += other(rdx).xyz, w kept
SUBEQ = "??ZcVec@math@wk@@QEAAAEAV012@AEBV012@@Z"   # this(rcx).xyz -= other(rdx).xyz, w kept
CTOR4 = "??0cVec@math@wk@@QEAA@MMMM@Z"              # this(rcx) = (xmm1, xmm2, xmm3, 5th arg)
CTOR0 = "??0cVec@math@wk@@QEAA@XZ"                  # this(rcx) = (0, 0, 0, 1)
COPY = "??0cVec@math@wk@@QEAA@AEBV012@@Z"           # this(rcx).xyz = other(rdx).xyz, w 1
ASSIGN = "??4cVec@math@wk@@QEAAAEAV012@AEBV012@@Z"  # this(rcx).xyz = other(rdx).xyz, w kept
SUB = "??GcVec@math@wk@@QEBA?AV012@AEBV012@@Z"      # out(rdx).xyz = this(rcx) - other(r8), w 1
ADD = "??HcVec@math@wk@@QEBA?AV012@AEBV012@@Z"      # out(rdx).xyz = this(rcx) + other(r8), w 1
APPLY = "?Apply@cMatrix@math@wk@@SAXAEAVcVec@23@AEBV123@AEBV423@@Z"  # out(rcx) = M(rdx) v(r8)
MOVE, FORWARD = 0x2DA3F0, 0x2DA410
# 1BDE90(out, in, angle) = cMatrix::MakeRotateY(M, angle), Apply(out, M, in);
# 1BDED0 the same about Z: out.xyz = R in.xyz, out.w = in.w (the rotation's
# last row is (0, 0, 0, 1))
ROTATES = {0x1BDE90: "MakeRotateY", 0x1BDED0: "MakeRotateZ"}
# the one pointer argument a function writes (whole, or operator='s xyz) and
# reads nothing through: a vstep passed there is overwritten (the kernel's code)
WRITE_ONLY = {MULF: "rdx", SUB: "rdx", ADD: "rdx", CTOR4: "rcx", CTOR0: "rcx", COPY: "rcx",
              ASSIGN: "rcx", APPLY: "rcx"}
# the float arguments each kernel function reads (the rest it writes first)
KERNEL_XMM = sf.KERNEL_XMM
assert set(KERNEL_XMM) == {MULF, MULEQ, ADDEQ, SUBEQ, CTOR4, CTOR0, COPY, ASSIGN, SUB, ADD,
                           APPLY}
# functions of at most four arguments that touch nothing on the caller's stack
# but through their pointer arguments: a vstep above the home space is safe
SMALL = set(KERNEL_XMM) - {CTOR4} | {MOVE, FORWARD}
# what a function returns in rax: the pointer argument it was given
RET_ARG = {MULF: "rdx", SUB: "rdx", ADD: "rdx", "??KcVec@math@wk@@QEBA?AV012@M@Z": "rdx",
           MULEQ: "rcx", ADDEQ: "rcx", SUBEQ: "rcx", CTOR4: "rcx", CTOR0: "rcx", COPY: "rcx",
           ASSIGN: "rcx"}
ARG_GPR = ("rcx", "rdx", "r8", "r9")
HOME = 0x20             # the callee's home space above the body's rsp
BOUND = 6000


def _mem(i):
    return next((op for op in i.operands if op.type == X.X86_OP_MEM), None)


def _writes_rsp(i):
    return "rsp" in gtc.writes(i) and i.mnemonic not in ("call", "ret")


def edges(fn, switch):
    """{instruction: successors}: the direct edges, and at an indirect jump the
    switch destinations (tools/gen_tracer.global_pass) inside the function.
    Func also gives every instruction without a predecessor the indirect jumps
    as predecessors, which takes in a jump table's bytes decoded as code; these
    edges do not."""
    out = {}
    dests = sorted(t for t in switch if t in fn.ins)
    for a in fn.order:
        i = fn.ins[a]
        ss = [x for x in fn.succs(i) if x in fn.ins]
        if i.mnemonic == "jmp" and i.operands[0].type != X.X86_OP_IMM:
            ss = dests
        out[a] = ss
    return out


def reachable(fn, succ):
    seen, work = set(), [fn.root]
    while work:
        a = work.pop()
        if a in seen or a not in fn.ins:
            continue
        seen.add(a)
        work.extend(succ.get(a, ()))
    return seen


class Frame:
    """Entry-relative offsets (the return address at 0) of the body's rsp and,
    if the function keeps one, the frame pointer rbp. ok is False when rsp or
    rbp changes anywhere else than in the root's prologue and the epilogues
    (of the code reachable from the entry)."""

    PROLOGUE_MAX = 48

    def __init__(self, fn, live):
        self.fn = fn
        self.live = live
        self.ok, self.why = False, None
        self.rsp = self.rbp = None
        self.epilogue = set()          # rsp writes of epilogues
        cur, regs, seen = 0, {}, set()
        a = fn.root
        for _ in range(self.PROLOGUE_MAX):
            i = fn.ins.get(a)
            if i is None:
                break
            m, ops = i.mnemonic, i.operands
            if m.startswith("j") or m in ("call", "ret"):
                break
            seen.add(a)
            if m == "push":
                cur -= 8
            elif m == "sub" and ops[0].type == X.X86_OP_REG and \
                    i.reg_name(ops[0].reg) == "rsp" and ops[1].type == X.X86_OP_IMM:
                cur -= ops[1].imm
            elif m == "mov" and ops[1].type == X.X86_OP_REG and \
                    i.reg_name(ops[1].reg) == "rsp" and ops[0].type == X.X86_OP_REG:
                regs[gtc.reg_key(i, ops[0].reg)] = cur
                if gtc.reg_key(i, ops[0].reg) == "rbp":
                    self.rbp = cur
            elif m == "lea" and ops[0].type == X.X86_OP_REG and \
                    gtc.reg_key(i, ops[0].reg) == "rbp":
                mm = ops[1].mem
                b = i.reg_name(mm.base) if mm.base else None
                if mm.index:
                    self.why = "rbp set from an index at %X" % a
                    return
                if b == "rsp":
                    self.rbp = cur + mm.disp
                elif b in regs:
                    self.rbp = regs[b] + mm.disp
                else:
                    self.why = "rbp set from %s at %X" % (b, a)
                    return
            elif _writes_rsp(i):
                self.why = "rsp changed at %X in the prologue" % a
                return
            else:
                for w in gtc.writes(i):
                    regs.pop(w, None)
            a += i.size
        self.rsp = cur
        for a in fn.order:
            if a not in live:
                continue
            i = fn.ins[a]
            wr = gtc.writes(i)
            if a in seen or not (_writes_rsp(i) or "rbp" in wr):
                continue
            if self._in_epilogue(a):
                self.epilogue.add(a)
                continue
            if "rbp" in wr and "rsp" not in wr and self.rbp is None:
                continue          # rbp is a plain register here
            self.why = "%s changed at %X outside the prologue and epilogues" % (
                "rsp" if _writes_rsp(i) else "rbp", a)
            return
        self.ok = True

    def _in_epilogue(self, a):
        """a starts or sits in an epilogue: from it to a ret or a jump out of
        the function, only pops, rsp adjustments and restores from the stack."""
        fn = self.fn
        for _ in range(16):
            i = fn.ins.get(a)
            if i is None:
                return False
            m, ops = i.mnemonic, i.operands
            if m == "ret" or (m == "jmp" and (ops[0].type != X.X86_OP_IMM or
                                              ops[0].imm not in fn.ins)):
                return True
            ok = m in ("pop", "int3") or \
                (m in ("add", "lea", "mov") and ops[0].type == X.X86_OP_REG and
                 i.reg_name(ops[0].reg) == "rsp") or \
                (m in ("mov", "movaps", "movups", "movdqa") and ops[1].type == X.X86_OP_MEM and
                 ops[1].mem.base in (X.X86_REG_RSP, X.X86_REG_R11, X.X86_REG_RBP))
            if not ok:
                return False
            a += i.size
        return False

    def base_off(self, i, base):
        """the entry-relative offset a frame register holds in the body"""
        n = i.reg_name(base)
        if n == "rsp":
            return self.rsp
        if n == "rbp" and self.rbp is not None:
            return self.rbp
        return None


class StackAddrs:
    """Which general registers hold a stack address (entry-relative) before
    each instruction, on every path: a forward dataflow, meet = agreement."""

    def __init__(self, fn, frame, iat, succ):
        self.fn, self.frame, self.iat = fn, frame, iat
        self.at = {}
        self.escaped = set()
        work = [(fn.root, ())]
        while work:
            a, st = work.pop()
            old = self.at.get(a)
            if old is not None:
                new = tuple(sorted(set(old) & set(st)))
                if new == old:
                    continue
                st = new
            self.at[a] = st
            i = fn.ins.get(a)
            if i is None:
                continue
            out = tuple(sorted(self.transfer(i, dict(st)).items()))
            for x in succ.get(a, ()):
                work.append((x, out))

    def callee(self, i):
        op = i.operands[0]
        if op.type == X.X86_OP_IMM:
            return op.imm
        if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
            return self.iat.get(gtc.rip_target(i, op))
        return None

    def transfer(self, i, st):
        m, ops = i.mnemonic, i.operands
        if i.address in self.frame.epilogue:
            return {}
        if m == "call":
            t = self.callee(i)
            ret = st.get(RET_ARG[t]) if t in RET_ARG else None
            for r in sf.VOLATILE:
                st.pop(r, None)
            if ret is not None:
                st["rax"] = ret
            return st
        if m == "lea" and ops[0].type == X.X86_OP_REG:
            r = gtc.reg_key(i, ops[0].reg)
            mm = ops[1].mem
            off = None
            if mm.base and not mm.index:
                b = gtc.reg_key(i, mm.base)
                off = self.frame.base_off(i, mm.base)
                if b in ("rsp", "rbp") and off is None:
                    off = None
                elif off is None and b in st:
                    off = st[b]
                if off is not None:
                    off += mm.disp
            if off is None:
                st.pop(r, None)
            else:
                st[r] = off
            return st
        if m == "mov" and len(ops) == 2 and ops[0].type == X.X86_OP_REG and \
                ops[1].type == X.X86_OP_REG and ops[0].size == 8:
            src = gtc.reg_key(i, ops[1].reg)
            dst = gtc.reg_key(i, ops[0].reg)
            if src in st:
                st[dst] = st[src]
            else:
                st.pop(dst, None)
            return st
        # a stack address stored to memory: it may be read back anywhere
        if m in ("mov", "push") and ops and ops[-1].type == X.X86_OP_REG:
            r = gtc.reg_key(i, ops[-1].reg)
            if r in st and (m == "push" or ops[0].type == X.X86_OP_MEM):
                self.escaped.add(st[r])
        for w in gtc.writes(i):
            st.pop(w, None)
        return st

    def reg(self, a, r):
        return dict(self.at.get(a, ())).get(r)

    def operand(self, i, op, regs=None):
        """the entry-relative stack offset a memory operand addresses, None
        when it is not on the stack, "?" when it is on the stack at an unknown
        place (an index). regs: the stack addresses the registers hold, if
        known better than the dataflow's (a path's own)"""
        mm = op.mem
        if not mm.base or mm.base == X.X86_REG_RIP:
            return None
        off = self.frame.base_off(i, mm.base)
        if off is None:
            r = gtc.reg_key(i, mm.base)
            off = regs.get(r) if regs is not None else self.reg(i.address, r)
        if off is None:
            return None
        return "?" if mm.index else off + mm.disp


class WOne:
    """The stack slots whose w lane certainly holds 1.0 before each
    instruction: made by a kernel function that sets it (operator*(float), -,
    +, the copy and default constructors, cVec(x, y, z, 1.0)), kept by those
    that keep it (operator=, +=, -=, *=), lost to anything else that may write
    it (a store over +C, a call given a stack address or any address stored
    away, an epilogue)."""

    SETS = {MULF: "rdx", SUB: "rdx", ADD: "rdx", COPY: "rcx", CTOR0: "rcx"}
    KEEPS = {ASSIGN, ADDEQ, SUBEQ, MULEQ, MULF, SUB, ADD, COPY, CTOR0, CTOR4, APPLY,
             "?GetLength@cVec@math@wk@@SAMAEBV123@@Z",
             "?GetDistance@cVec@math@wk@@SAMAEBV123@0@Z"}

    def __init__(self, vf):
        fn, addrs = vf.fn, vf.addrs
        self.at = {}
        work = [(fn.root, frozenset())]
        while work:
            a, st = work.pop()
            old = self.at.get(a)
            if old is not None:
                new = old & st
                if new == old:
                    continue
                st = new
            self.at[a] = st
            i = fn.ins.get(a)
            if i is None:
                continue
            out = frozenset(self.transfer(vf, addrs, i, set(st)))
            for x in vf.succ.get(a, ()):
                work.append((x, out))

    def transfer(self, vf, addrs, i, st):
        a = i.address
        if a in vf.frame.epilogue:
            return set()
        if i.mnemonic == "call":
            t = vf.callee(i)
            ptr = {r: addrs.reg(a, r) for r in ARG_GPR}
            if t not in self.KEEPS:
                if addrs.escaped or any(p is not None for p in ptr.values()):
                    return set()
                return st
            if t in self.SETS and ptr[self.SETS[t]] is not None:
                st.add(ptr[self.SETS[t]])
            if t == CTOR4 and ptr["rcx"] is not None:
                (st.add if vf.arg5(a) == 1.0 else st.discard)(ptr["rcx"])
            if t == APPLY and ptr["rcx"] is not None:
                st.discard(ptr["rcx"])
            return st
        for op in i.operands:
            if op.type == X.X86_OP_MEM and op.access & capstone.CS_AC_WRITE and \
                    i.mnemonic != "lea":
                off = addrs.operand(i, op)
                if off == "?":
                    return set()
                if off is not None:
                    st -= {s for s in st if off < s + 16 and s + 12 < off + max(op.size, 1)}
        return st


class VecFlow:
    def __init__(self, img, secs, fn, md, iat, switch, helpers=None):
        self.img, self.secs, self.fn, self.md, self.iat = img, secs, fn, md, iat
        self.helpers = helpers or {}
        self.sl = gtc.Slicer(img, secs, fn)
        self.succ = edges(fn, switch)
        self.live = reachable(fn, self.succ)
        self.frame = Frame(fn, self.live)
        self.addrs = StackAddrs(fn, self.frame, iat, self.succ) if self.frame.ok else None

    def callee(self, i):
        op = i.operands[0]
        if op.type == X.X86_OP_IMM:
            return op.imm
        if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
            return self.iat.get(gtc.rip_target(i, op))
        return None

    def dest(self, a, reg, depth=0):
        """What a pointer argument that is not on the stack points at, as the
        code built it on every path: ("field", base, disp, at) for `lea r, [B +
        d]` at `at`, ("ptr", base, disp, at) for `mov r, [B + d]` (a pointer the
        object keeps, as the position +A8), or None."""
        got = set()
        for kind, d in self.sl.defs(a, reg):
            if kind != "def" or depth > 4:
                return None
            i = self.fn.ins[d]
            ops = i.operands
            if i.mnemonic == "mov" and ops[1].type == X.X86_OP_REG:
                x = self.dest(d, gtc.reg_key(i, ops[1].reg), depth + 1)
            elif i.mnemonic in ("lea", "mov") and ops[1].type == X.X86_OP_MEM and \
                    ops[1].mem.base and not ops[1].mem.index and \
                    ops[1].mem.base not in (X.X86_REG_RIP, X.X86_REG_RSP):
                x = ("field" if i.mnemonic == "lea" else "ptr",
                     i.reg_name(ops[1].mem.base), ops[1].mem.disp, d)
            else:
                x = None
            if x is None:
                return None
            got.add(x)
        if len({g[:3] for g in got}) != 1:
            return None
        # several definitions alike (the same lea on two paths): the first
        return sorted(got)[0]

    def wone(self):
        if not hasattr(self, "_wone"):
            self._wone = WOne(self)
        return self._wone

    # --- where a vector comes from -----------------------------------------
    def vec_leaves(self, a, off, depth=0, seen=None):
        """What the stack vector at `off` holds before `a`, as the leaves of
        its construction: ("field", base, disp) for a vector or a float read
        from an object, ("const", value), ("callret", at) for a float a call
        returned, ("?", why) for anything this does not follow. It walks back
        over single-predecessor code to the last write of the slot (a kernel
        call given its address as the output, or operator*= and += in place)
        and follows that write's inputs."""
        seen = set() if seen is None else seen
        if (a, off) in seen:
            return set()        # around a loop: its other ways in hold the writes
        if depth > 8:
            return {("?", "deep at %X" % a)}
        seen.add((a, off))
        fn = self.fn
        at = a
        for _ in range(200):
            ps = [p for p in fn.preds.get(at, []) if p in self.live]
            if len(ps) != 1:
                # a join: every path's last write
                if not ps:
                    return {("?", "no writer before %X" % at)}
                out = set()
                for p in ps:
                    out |= self._vec_at(p, off, depth + 1, seen)
                return out
            at = ps[0]
            got = self._vec_write(at, off, depth, seen)
            if got is not None:
                return got
        return {("?", "too far back from %X" % a)}

    def _vec_at(self, at, off, depth, seen):
        got = self._vec_write(at, off, depth, seen)
        return got if got is not None else self.vec_leaves(at, off, depth, seen)

    def _float_leaves(self, a, reg):
        out = set()
        for x in gtc.leaves(self.sl.value(a, reg)):
            if x[0] == "const":
                out.add(("const", x[3]))
            elif x[0] == "field":
                out.add(("field", x[2], x[3]))
            elif x[0] == "callret":
                out.add(("callret", x[1]))
            elif x[0] == "global":
                out.add(("global", x[2]))
            else:
                out.add(("?", gtc.render(x)))
        return out

    def _vec_ptr(self, a, reg, depth, seen):
        """the leaves of the vector a pointer argument points at"""
        off = self.addrs.reg(a, reg)
        if off is not None:
            return self.vec_leaves(a, off, depth + 1, seen)
        d = self.dest(a, reg)
        if d is None:
            return {("?", "%s at %X" % (reg, a))}
        return {("vfield", d[1], d[2]) if d[0] == "field" else ("ptr", d[1], d[2])}

    def _vec_write(self, at, off, depth, seen):
        """None if the instruction at `at` does not write the slot, else the
        leaves of what it leaves there"""
        i = self.fn.ins[at]
        if i.mnemonic != "call":
            for op in i.operands:
                if op.type == X.X86_OP_MEM and op.access & capstone.CS_AC_WRITE and \
                        i.mnemonic != "lea":
                    o = self.addrs.operand(i, op)
                    if o == "?" or (o is not None and o < off + 16 and off < o + op.size):
                        return {("?", "a store at %X" % at)}
            return None
        t = self.callee(i)
        ptr = {r: self.addrs.reg(at, r) for r in ARG_GPR}
        w = WRITE_ONLY.get(t)
        inplace = {MULEQ: "rcx", ADDEQ: "rcx", SUBEQ: "rcx"}.get(t)
        if t in ROTATES and ptr.get("rcx") == off:
            # out = R(angle) in: a rotation, no change of size; the angle is a
            # direction, not a quantity
            return self._vec_ptr(at, "rdx", depth, seen)
        if w and ptr.get(w) == off:
            if t == MULF:
                return self._vec_ptr(at, "rcx", depth, seen) | self._float_leaves(at, "xmm2")
            if t in (SUB, ADD):
                return self._vec_ptr(at, "rcx", depth, seen) | self._vec_ptr(at, "r8", depth, seen)
            if t == CTOR4:
                return set().union(*(self._float_leaves(at, r) for r in ("xmm1", "xmm2", "xmm3")))
            if t == CTOR0:
                return {("const", 0.0)}
            if t in (COPY, ASSIGN):
                return self._vec_ptr(at, "rdx", depth, seen)
            if t == APPLY:
                return self._vec_ptr(at, "rdx", depth, seen) | self._vec_ptr(at, "r8", depth, seen)
            return {("?", "%s at %X" % (t, at))}
        if inplace and ptr.get(inplace) == off:
            prior = self.vec_leaves(at, off, depth + 1, seen)
            if t == MULEQ:
                return prior | self._float_leaves(at, "xmm1")
            return prior | self._vec_ptr(at, "rdx", depth, seen)
        if any(p is not None and p <= off < p + 16 for p in ptr.values()) and \
                t not in KERNEL_XMM and t not in WOne.KEEPS:
            return {("?", "passed to %s at %X" % (t if isinstance(t, str) else "%X" % (t or 0),
                                                  at))}
        return None

    def const_at(self, a, reg):
        """the constant a register holds before `a` on every path, or None"""
        vals = set()
        for x in gtc.leaves(self.sl.value(a, reg)):
            if x[0] != "const":
                return None
            vals.add(x[3])
        return vals.pop() if len(vals) == 1 else None

    def arg5(self, a):
        """the constant stored to the fifth argument's slot ([rsp+0x20]) on the
        straight-line code before the call at `a`, or None"""
        ps = self.fn.preds.get(a, [])
        for _ in range(24):
            if len(ps) != 1:
                return None
            p = self.fn.ins[ps[0]]
            op = _mem(p)
            if p.mnemonic in ("call", "ret") or p.mnemonic.startswith("j"):
                return None
            if op is not None and op.access & capstone.CS_AC_WRITE and \
                    op.mem.base == X.X86_REG_RSP and op.mem.disp == 0x20 and not op.mem.index:
                src = p.operands[1]
                if p.mnemonic == "movss" and src.type == X.X86_OP_REG:
                    return self.const_at(p.address, gtc.reg_key(p, src.reg))
                return None
            ps = self.fn.preds.get(p.address, [])
        return None

    def run(self, start, roles, bound=BOUND):
        """roles: {register: ("step",)} at `start`. Returns (sinks, factors,
        why): sinks as (call address, kind, what), factors as (address, register
        or operand index), and None or why the step is not only a move."""
        fn = self.fn
        if not self.frame.ok:
            return set(), set(), "no stack frame: %s" % self.frame.why
        if start not in self.live:
            return set(), set(), "%X is not reached from the entry by known edges" % start
        sinks, factors = set(), set()
        self.sources = set()
        # the stack addresses the registers hold, per path from here on
        ad0 = self.addrs.at.get(start, ())
        work = [(start, tuple(sorted(roles.items())), (), ad0)]
        seen = set()
        self.visited = set()
        while work:
            a, regs, slots, ads = work.pop()
            if (a, regs, slots, ads) in seen:
                continue
            seen.add((a, regs, slots, ads))
            if len(seen) > bound:
                return sinks, factors, "walk exceeds %d states" % bound
            role, vs, ad = dict(regs), dict(slots), dict(ads)
            if not role and not vs:
                continue
            if a not in fn.ins:
                if role:
                    return sinks, factors, "leaves the function at %X" % a
                continue
            self.visited.add(a)
            i = fn.ins[a]
            m = i.mnemonic
            nxt = a + i.size
            if m == "call":
                why = self._call(i, role, vs, ad, sinks, factors)
                if why:
                    return sinks, factors, why
                ad = self.addrs.transfer(i, ad)
                work.append((nxt, tuple(sorted(role.items())), tuple(sorted(vs.items())),
                             tuple(sorted(ad.items()))))
                continue
            if m in ("ret", "retf"):
                back = set(role) & set(sf.RETURNED)
                if back:
                    return sinks, factors, "%s live at the return at %X" % (
                        "/".join(sorted(back)), a)
                continue
            if m in ("int3", "ud2", "hlt"):
                continue
            if a in self.frame.epilogue:
                vs = {}               # the frame is torn down: its slots are dead
            why = self._memory(i, vs, ad)
            if why:
                return sinks, factors, why
            why = self._scalar(i, role, factors)
            if why:
                return sinks, factors, why
            ad = self.addrs.transfer(i, ad)
            st = (tuple(sorted(role.items())), tuple(sorted(vs.items())),
                  tuple(sorted(ad.items())))
            if m.startswith("j"):
                if i.operands[0].type != X.X86_OP_IMM:
                    return sinks, factors, "indirect jump at %X" % a
                work.append((i.operands[0].imm,) + st)
                if m != "jmp":
                    work.append((nxt,) + st)
            else:
                work.append((nxt,) + st)
        if not sinks:
            return sinks, factors, "no path moves anything by the step"
        return sinks, factors, None

    # --- pieces of the walk -------------------------------------------------
    def _overlap(self, vs, off, size):
        return [s for s in vs if off < s + 16 and s < off + size]

    def _overwrite(self, vs, off, a):
        """a whole 16-byte write at `off`: ends the vstep there; None, or why
        not (it would leave part of one)"""
        hit = self._overlap(vs, off, 16)
        if hit and hit != [off]:
            return "the call at %X overwrites part of the vector step at %X" % (a, hit[0])
        vs.pop(off, None)
        return None

    def _memory(self, i, vs, ad):
        """A memory operand touching a vstep slot: a full 16-byte store ends
        it, anything else refuses."""
        if not vs or i.mnemonic == "lea":
            return None
        for op in i.operands:
            if op.type != X.X86_OP_MEM:
                continue
            off = self.addrs.operand(i, op, ad)
            if off is None:
                continue
            text = "%X %s %s" % (i.address, i.mnemonic, i.op_str)
            if off == "?":
                return "an indexed stack access while a vector step is live at %s" % text
            hit = self._overlap(vs, off, max(op.size, 1))
            if not hit:
                continue
            if op.access == capstone.CS_AC_WRITE and hit == [off] and op.size == 16 and \
                    i.mnemonic in ("movaps", "movups", "movdqa", "movdqu"):
                del vs[off]
                continue
            return "the vector step at %X read or written at %s" % (hit[0], text)
        return None

    def _scalar(self, i, role, factors):
        """A step in a register: copies and factors keep it, a write ends it,
        anything else reading it refuses."""
        if not role:
            return None
        rd, wr = gtc.reads(i), gtc.writes(i)
        used = set(role) & rd
        m, ops = i.mnemonic, i.operands
        text = "%X %s %s" % (i.address, m, i.op_str)
        if not used:
            for r in wr:
                role.pop(r, None)
            return None
        reg0 = gtc.reg_key(i, ops[0].reg) if ops and ops[0].type == X.X86_OP_REG else None
        reg1 = gtc.reg_key(i, ops[1].reg) if len(ops) > 1 and ops[1].type == X.X86_OP_REG \
            else None
        if m in sf.COPIES and reg0 and reg1 and reg1 in used:
            role[reg0] = role[reg1]
            return None
        if m in ("mulss", "divss") and reg0 in used and reg1 not in used:
            factors.add((i.address, 1))
            return None
        if m == "mulss" and reg1 in used and reg0 not in used:
            factors.add((i.address, 0))
            role[reg0] = role[reg1]
            return None
        if m in sf.SIGN and reg0 in used and ops[1].type == X.X86_OP_MEM and \
                ops[1].mem.base == X.X86_REG_RIP:
            return None
        return "the step read by %s" % text

    def _call(self, i, role, vs, ad, sinks, factors):
        a = i.address
        t = self.callee(i)
        ptr = {r: ad.get(r) for r in ARG_GPR}
        for r, off in ptr.items():
            if off is None:
                continue
            hit = self._overlap(vs, off, 1)
            if hit and hit != [off]:
                return "%s points inside the vector step at %X at the call at %X" % (r, hit[0], a)
        rsp = self.frame.rsp
        if self._overlap(vs, rsp, HOME):
            return "a vector step in the callee's home space at the call at %X" % a
        if t not in SMALL and self._overlap(vs, rsp + HOME, 0x20):
            return "a vector step where the call at %X may read stack arguments" % a
        if any(s in self.addrs.escaped for s in vs):
            return "a vector step's slot address is stored to memory (call at %X)" % a
        vin = {r for r, off in ptr.items() if off is not None and off in vs}
        steps = {r for r in role if r in sf.ARG_XMM}
        # the call's one output, written whole (or its xyz, operator=): a vstep
        # there ends once the inputs are decided
        out_reg = WRITE_ONLY.get(t)
        out = ptr.get(out_reg) if out_reg else None
        ins = vin - {out_reg}
        new = None                  # (slot, w flag) the call leaves a vstep in
        if t == MULF:
            f_step, src_v = "xmm2" in steps, "rcx" in ins
            if ins - {"rcx"}:
                return "a vector step passed to operator*(float) in %s at %X" % (
                    "/".join(sorted(ins)), a)
            if f_step and src_v:
                return "the step times a vector step at %X" % a
            if f_step or src_v:
                if out is None:
                    return "operator*(float) at %X stores a step outside the stack" % a
                if not f_step:
                    factors.add((a, "xmm2"))
                else:
                    # the vector the step scales: a velocity kept in the
                    # object, or one this tick builds on the stack
                    src = ptr["rcx"]
                    self.sources.add((a, ("stack", src) if src is not None else
                                      (self.dest(a, "rcx") or (None,))[:3]))
                new = (out, 1)
        elif t == MULEQ:
            if "xmm1" in steps:
                return "the step as a vector's factor at %X" % a
            if ins - {"rcx"}:
                return "a vector step passed to operator*= at %X" % a
            if "rcx" in ins:
                factors.add((a, "xmm1"))
        elif t in (ADDEQ, SUBEQ):
            if "rcx" in ins or ins - {"rdx"}:
                return "a vector step added to at %X" % a
            if "rdx" in ins:
                if ptr["rcx"] is not None:
                    return "a vector step accumulated on the stack at %X" % a
                what = self.dest(a, "rcx")
                if what is None:
                    return "a vector step added into something unknown at %X" % a
                sinks.add((a, "add" if t == ADDEQ else "sub", what[:3]))
        elif t in (ASSIGN, COPY):
            if ins - {"rdx"}:
                return "a vector step passed to a copy in %s at %X" % ("/".join(sorted(ins)), a)
            if "rdx" in ins:
                if out is None:
                    return "a vector step copied outside the stack at %X" % a
                # operator= keeps the destination's w; the copy constructor sets 1
                new = (out, 1 if t == COPY or vs.get(out) == 1 or
                       out in self.wone().at.get(a, ()) else 0)
        elif t == CTOR4:
            comps = [r for r in ("xmm1", "xmm2", "xmm3") if r in steps]
            if ins:
                return "a vector step passed to cVec(x, y, z, w) at %X" % a
            if comps:
                if out is None:
                    return "cVec(x, y, z, w) at %X builds a step outside the stack" % a
                for r in ("xmm1", "xmm2", "xmm3"):
                    if r not in comps and self.const_at(a, r) != 0.0:
                        return "cVec(x, y, z, w) at %X: %s is neither the step nor 0" % (a, r)
                new = (out, 1 if self.arg5(a) == 1.0 else 0)
        elif t == APPLY:
            # cMatrix::Apply(out, M, v) with out = [B+A8] and M = B+50 is 2DA3F0
            # inlined for the object B (a child model)
            if ins - {"r8"}:
                return "a vector step passed to cMatrix::Apply in %s at %X" % (
                    "/".join(sorted(ins)), a)
            if "r8" in ins:
                if vs[ptr["r8"]] != 1:
                    return "cMatrix::Apply at %X moves by a vector whose w is not known to " \
                        "be 1" % a
                o, m = self.dest(a, "rcx"), self.dest(a, "rdx")
                if not (o and m and o[0] == "ptr" and o[2] == 0xA8 and m[0] == "field" and
                        m[2] == 0x50 and o[1] == m[1] and
                        sf.same_base(self.sl, o[3], m[3], gtc.REG64.get(o[1], o[1]))):
                    return "cMatrix::Apply at %X is not an object's move: out %s, M %s" % (
                        a, o and o[:3], m and m[:3])
                sinks.add((a, "move", ("child", o[1], 0x80)))
        elif t == MOVE:
            if ins - {"rdx"}:
                return "a vector step passed to 2DA3F0 in %s at %X" % ("/".join(sorted(ins)), a)
            if steps & set(sf.callee_xmm_args(self.img, self.md, MOVE)):
                return "%s live at the call at %X, which reads it" % ("/".join(sorted(steps)), a)
            if "rdx" in ins:
                if vs[ptr["rdx"]] != 1:
                    return "2DA3F0 at %X moves by a vector whose w is not known to be 1" % a
                sinks.add((a, "move", None))
        elif t == FORWARD:
            if ins:
                return "a vector step passed to 2DA410 at %X" % a
            reads = set(sf.callee_xmm_args(self.img, self.md, FORWARD))
            if (steps & reads) - {"xmm1"}:
                return "%s live at the call at %X, which reads it" % ("/".join(sorted(steps)), a)
            if "xmm1" in steps:
                sinks.add((a, "forward", None))
        elif isinstance(t, int) and t in self.helpers:
            # a helper given the step as a float argument (the caller proves
            # what the helper does with it: find_actor_motion.FALLS)
            if ins:
                return "a vector step passed to %X at %X" % (t, a)
            if self.helpers[t] in steps:
                sinks.add((a, "call", t))
        elif ins:
            return "a vector step passed in %s to the call at %X" % ("/".join(sorted(ins)), a)
        # a step in a float argument the callee reads, other than as above
        reads = KERNEL_XMM[t] if t in KERNEL_XMM else \
            set(sf.callee_xmm_args(self.img, self.md, t)) if isinstance(t, int) else \
            set(sf.ARG_XMM)
        taken = {MULF: {"xmm2"}, CTOR4: {"xmm1", "xmm2", "xmm3"}, FORWARD: {"xmm1"}}.get(t, set())
        if isinstance(t, int) and t in self.helpers:
            taken = {self.helpers[t]}
        if (steps & reads) - taken:
            return "%s live at the call at %X, which reads it" % (
                "/".join(sorted((steps & reads) - taken)), a)
        if out is not None:
            why = self._overwrite(vs, out, a)
            if why:
                return why
        if new is not None:
            vs[new[0]] = new[1]
        for r in list(role):
            if r in sf.VOLATILE:
                del role[r]
        return None
