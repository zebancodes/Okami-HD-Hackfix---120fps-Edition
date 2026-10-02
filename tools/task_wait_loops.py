#!/usr/bin/env python3
"""What the loop around a task wait does.

A task that yields with wait(1) inside a loop runs one pass a tick. Whether
that is fast at 120 fps depends on the pass: a poll (`while (!ready) wait(1)`)
reads state and looks right at any rate, while a pass that steps something
(an alpha += 0.025, a countdown, a pass counter compared with 60) does N times
stock's work per stock tick. tools/survey_task_waits.py uses this module to
describe, for every call of the wait on a cycle of its function:

  head      the innermost natural loop holding the call (dominator-based;
            the loop's body is every block that reaches its back edge
            without passing the head)
  steps     evidence that the loop's own instructions step state from one
            pass to the next: a read-modify-write of memory (add/sub/inc/dec
            on it, or a store of arithmetic on a load of the same operand), a
            float carried in a callee-saved xmm, or a pass counter (a
            register or stack slot stepped by 1 whose flags or value a
            compare in the loop reads, and that nothing else in the loop
            writes: an inner loop's index is reset in the body)
  pad       what reads the pad state (main+B6B0A0..B6B170: held and pressed
            words, stick, heading) in the loop or anything it calls
  rate      what reads a rate global (the time scale, the mode byte, the fps
            byte, the 60 fps flag, the frame counter) or a mode table
  patched   what another family already rewrites, in the loop or below it

Each flag is a list of sources: "direct" for the loop's own instructions, or
the rva of the call in the loop whose callee tree holds it, so the generator
can waive a callee it has read (gen_task_waits.CALLEES_REVIEWED) and no other.
A callee's tree is followed through direct calls and tail jumps, through
functions with no .pdata (leaves, decoded along their control flow); an
indirect call counts as unknown work, never as a flag.
"""
import bisect
import collections
import contextlib
import io
import os
import sys

import capstone
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_turn_callers as gtc  # noqa: E402

WAIT = 0x4567C0
PAD_LO, PAD_HI = 0xB6B0A0, 0xB6B170
RATE = dict(gtc.RATE_GLOBALS)
RATE[0xB6AC20] = "frame counter"
FARITH = {"addss", "subss", "mulss", "divss", "addsd", "subsd", "mulsd", "divsd"}
IARITH = {"add", "sub", "inc", "dec", "imul", "lea", "neg", "shl", "sar", "shr"}
RMW = {"add", "sub", "inc", "dec", "xadd", "adc", "sbb", "neg"}
SAVED_XMM = {"xmm%d" % n for n in range(6, 16)}


class LeafFunc:
    """A function with no .pdata entry: its instructions along its control
    flow from the entry. A jmp more than 0x400 bytes away is a tail call."""

    def __init__(self, img, md, root):
        self.root = root
        self.ins, self.tails = {}, []
        work = [root]
        while work and len(self.ins) < 400:
            a = work.pop()
            while a not in self.ins:
                try:
                    i = next(md.disasm(img[a:a + 16], a))
                except StopIteration:
                    break
                self.ins[a] = i
                m = i.mnemonic
                if m in ("ret", "int3", "ud2", "hlt"):
                    break
                if m.startswith("j"):
                    op = i.operands[0]
                    if op.type != X.X86_OP_IMM:
                        self.tails.append(None)
                        break
                    if m == "jmp":
                        if abs(op.imm - root) > 0x400:
                            self.tails.append(op.imm)
                            break
                        a = op.imm
                        continue
                    work.append(op.imm)
                a = i.address + i.size
        self.order = sorted(self.ins)
        self.preds = {}


class Program:
    def __init__(self):
        self.img, self.secs, _f, self.sha = gtc.load_image()
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.roots, self.starts, _e = gtc.pdata_roots(self.img, self.secs)
        self.ranges = gtc.patched_ranges()
        import check_patch_sites as cps
        with contextlib.redirect_stdout(io.StringIO()):
            for fam in (cps.turn_callers, cps.day_clock):
                for a, raw, label in fam():
                    self.ranges.append((a, a + len(raw), label))
        self.ranges.sort()
        self.rstarts = [r[0] for r in self.ranges]
        self.imports = self._imports()
        self.fcache, self.scache, self.lcache = {}, {}, {}

    def _imports(self):
        import pefile
        from gamedir import GAME
        pe = pefile.PE(os.path.join(GAME, "main.dll"))
        out = {}
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            for imp in d.imports:
                out[imp.address - pe.OPTIONAL_HEADER.ImageBase] = (
                    imp.name.decode() if imp.name else "#%d" % imp.ordinal)
        return out

    def patched(self, a, size):
        return gtc.patched_by(self.ranges, self.rstarts, a, size)

    def func(self, root):
        if root not in self.fcache:
            k = bisect.bisect_right(self.starts, root) - 1
            inside = k >= 0 and any(b <= root < e for b, e in self.roots[self.starts[k]][1])
            if inside and self.roots[self.starts[k]][0] == root:
                r, frags = self.roots[self.starts[k]]
                self.fcache[root] = gtc.Func(self.img, r, frags, self.md)
            else:
                self.fcache[root] = LeafFunc(self.img, self.md, root)
        return self.fcache[root]

    def func_of(self, at):
        k = bisect.bisect_right(self.starts, at) - 1
        return self.func(self.roots[self.starts[k]][0])

    # ---- one instruction ---------------------------------------------------

    def facts(self, fn, a):
        """(rate reads, pad read, call target): the target is an rva, None for
        an indirect call, or an import's name; () when a is no call"""
        i = fn.ins[a]
        if i.mnemonic == "call":
            op = i.operands[0]
            if op.type == X.X86_OP_IMM:
                return [], False, op.imm
            if op.type == X.X86_OP_MEM:
                t = gtc.rip_target(i, op)
                if t is not None and t in self.imports:
                    return [], False, self.imports[t]
            return [], False, None
        rate, pad = [], False
        for op in i.operands:
            if op.type != X.X86_OP_MEM:
                continue
            t = gtc.rip_target(i, op)
            if t is not None:
                if t in RATE:
                    rate.append("%X %s" % (a, RATE[t]))
                elif gtc.TABLE_LO <= t < gtc.TABLE_HI:
                    rate.append("%X mode table" % a)
                if PAD_LO <= t < PAD_HI:
                    pad = True
            elif gtc.TABLE_LO <= op.mem.disp < gtc.TABLE_HI:
                rate.append("%X mode table" % a)
        return rate, pad, ()

    def summary(self, root, depth=0):
        """(rate, pad, patched): the first evidence of each in root's tree, or
        None; memoised, cycles cut"""
        if root in self.scache:
            return self.scache[root]
        self.scache[root] = (None, None, None)
        fn = self.func(root)
        rate = pad = pat = None
        subs = [t for t in getattr(fn, "tails", []) if t is not None]
        for a in fn.order:
            r, p, ct = self.facts(fn, a)
            if r and rate is None:
                rate = r[0]
            if p and pad is None:
                pad = "%X" % a
            fam = self.patched(a, fn.ins[a].size)
            if fam and pat is None:
                pat = "%X %s" % (a, fam)
            if isinstance(ct, int) and ct != WAIT:
                subs.append(ct)
        if depth < 60:
            for c in subs:
                s = self.summary(c, depth + 1)
                rate = rate or (s[0] and "%X > %s" % (c, s[0]))
                pad = pad or (s[1] and "%X > %s" % (c, s[1]))
                pat = pat or (s[2] and "%X > %s" % (c, s[2]))
        self.scache[root] = (rate, pad, pat)
        return self.scache[root]

    # ---- loops -------------------------------------------------------------

    def loops(self, fn):
        if fn.root in self.lcache:
            return self.lcache[fn.root]
        succs = collections.defaultdict(list)
        for a, ps in fn.preds.items():
            for p in ps:
                succs[p].append(a)
        leaders = {fn.root}
        for a in fn.order:
            if len(fn.preds.get(a, [])) != 1:
                leaders.add(a)
            i = fn.ins[a]
            if i.mnemonic.startswith("j") or i.mnemonic == "ret":
                leaders.update(succs.get(a, []))
                if a + i.size in fn.ins:
                    leaders.add(a + i.size)
            for p in fn.preds.get(a, []):
                if p + fn.ins[p].size != a:
                    leaders.add(a)
        bof, bl = {}, {}
        cur, prev_end = None, None
        for a in fn.order:
            if a in leaders or cur is None or a != prev_end:
                cur = a
                bl[cur] = []
            bl[cur].append(a)
            bof[a] = cur
            prev_end = a + fn.ins[a].size
        bs, bp = collections.defaultdict(set), collections.defaultdict(set)
        for b, ins in bl.items():
            for s in succs.get(ins[-1], []):
                if s in bof:
                    bs[b].add(bof[s])
                    bp[bof[s]].add(b)
        entry = bof[fn.root]
        order, seen, stack = [], {entry}, [(entry, iter(sorted(bs[entry])))]
        while stack:
            n, it = stack[-1]
            for s in it:
                if s not in seen:
                    seen.add(s)
                    stack.append((s, iter(sorted(bs[s]))))
                    break
            else:
                order.append(n)
                stack.pop()
        rpo = order[::-1]
        idx = {n: k for k, n in enumerate(rpo)}
        idom, changed = {entry: entry}, True
        while changed:
            changed = False
            for n in rpo[1:]:
                ps = [p for p in bp[n] if p in idom]
                if not ps:
                    continue
                new = ps[0]
                for p in ps[1:]:
                    x, y = p, new
                    while x != y:
                        while idx[x] > idx[y]:
                            x = idom[x]
                        while idx[y] > idx[x]:
                            y = idom[y]
                    new = x
                if idom.get(n) != new:
                    idom[n], changed = new, True

        def dominates(h, t):
            while True:
                if h == t:
                    return True
                if idom.get(t, t) == t:
                    return False
                t = idom[t]

        heads = collections.defaultdict(set)
        for t in seen:
            for h in bs[t]:
                if h in seen and dominates(h, t):
                    body, work = {h}, [t]
                    while work:
                        n = work.pop()
                        if n not in body:
                            body.add(n)
                            work.extend(p for p in bp[n] if p in seen)
                    heads[h] |= body
        self.lcache[fn.root] = (bl, bof, heads)
        return self.lcache[fn.root]

    def innermost(self, fn, at):
        """(head, [instruction addresses]) of the smallest loop holding at"""
        bl, bof, heads = self.loops(fn)
        if at not in bof:
            return None, []
        inner = sorted((len(body), h) for h, body in heads.items() if bof[at] in body)
        if not inner:
            return None, []
        h = inner[0][1]
        return h, sorted(a for b in heads[h] for a in bl[b])

    # ---- stepping ----------------------------------------------------------

    def counters(self, fn, nodes):
        """a register or stack slot stepped by 1 whose flags feed a jcc or
        that a cmp/test in the loop reads, and that nothing else in the loop
        writes: a pass counter (an inner loop's index is reset in the body)"""
        tested, writes, stepped = set(), collections.Counter(), collections.defaultdict(list)
        for a in nodes:
            i = fn.ins[a]
            for r in gtc.writes(i):
                writes[r] += 1
            for op in i.operands:
                if op.type != X.X86_OP_MEM or op.mem.base != X.X86_REG_RSP:
                    continue
                if op.access & capstone.CS_AC_WRITE:
                    writes[("stack", op.mem.disp)] += 1
                if i.mnemonic in ("cmp", "test"):
                    tested.add(("stack", op.mem.disp))
            if i.mnemonic in ("cmp", "test"):
                for op in i.operands:
                    if op.type == X.X86_OP_REG:
                        tested.add(gtc.reg_key(i, op.reg))
        for a in nodes:
            i = fn.ins[a]
            m, ops = i.mnemonic, i.operands
            one = m in ("inc", "dec") or (m in ("add", "sub") and len(ops) == 2 and
                                           ops[1].type == X.X86_OP_IMM and ops[1].imm in (1, -1))
            if m == "lea" and ops[1].type == X.X86_OP_MEM and ops[1].mem.index == 0 and                     ops[1].mem.base and ops[1].mem.disp in (1, -1) and                     gtc.reg_key(i, ops[0].reg) == gtc.reg_key(i, ops[1].mem.base):
                one = True
            if not one:
                continue
            d = ops[0]
            if d.type == X.X86_OP_REG and d.reg != X.X86_REG_RSP:
                key = gtc.reg_key(i, d.reg)
            elif d.type == X.X86_OP_MEM and d.mem.base == X.X86_REG_RSP and d.mem.index == 0:
                key = ("stack", d.mem.disp)
            else:
                continue
            nxt = fn.ins.get(a + i.size)
            flags_used = m != "lea" and nxt is not None and nxt.mnemonic.startswith("j") and                 nxt.mnemonic != "jmp"
            if flags_used or key in tested:
                stepped[key].append(a)
        out = []
        for key, addrs in stepped.items():
            if writes[key] == len(addrs):   # nothing but the steps writes it
                out += ["%X %s %s" % (a, fn.ins[a].mnemonic, fn.ins[a].op_str) for a in addrs]
        return out

    def steps(self, fn, nodes):
        out = []
        loads = set()
        for a in nodes:
            i = fn.ins[a]
            for op in i.operands:
                if op.type == X.X86_OP_MEM and op.access & capstone.CS_AC_READ and \
                        i.mnemonic != "lea":
                    loads.add((op.mem.base, op.mem.index, op.mem.scale, op.mem.disp))
        for k, a in enumerate(nodes):
            i = fn.ins[a]
            m, ops = i.mnemonic, i.operands
            if not ops:
                continue
            d = ops[0]
            if d.type == X.X86_OP_MEM and m in RMW and d.mem.base != X.X86_REG_RSP:
                out.append("%X %s %s" % (a, m, i.op_str))
                continue
            if d.type == X.X86_OP_MEM and d.access & capstone.CS_AC_WRITE and len(ops) == 2 and \
                    m in ("movss", "mov", "movsd", "movd") and ops[1].type == X.X86_OP_REG and \
                    (d.mem.base, d.mem.index, d.mem.scale, d.mem.disp) in loads:
                src = gtc.reg_key(i, ops[1].reg)
                for b in reversed(nodes[max(0, k - 10):k]):
                    bi = fn.ins[b]
                    if src in gtc.writes(bi):
                        if bi.mnemonic in FARITH or bi.mnemonic in IARITH:
                            out.append("%X %s %s (read-modify-write)" % (a, m, i.op_str))
                        break
            if m in FARITH and d.type == X.X86_OP_REG and i.reg_name(d.reg) in SAVED_XMM:
                out.append("%X %s %s (carried)" % (a, m, i.op_str))
        return out + self.counters(fn, nodes)

    def describe(self, at):
        """the loop around the call of the wait at `at`"""
        fn = self.func_of(at)
        head, nodes = self.innermost(fn, at)
        if head is None:
            return None
        pad, rate, pat, calls = [], [], [], []
        for a in nodes:
            r, p, ct = self.facts(fn, a)
            if r:
                rate.append("direct %s" % r[0])
            if p:
                pad.append("direct %X" % a)
            fam = self.patched(a, fn.ins[a].size)
            if fam and a != at:
                pat.append("direct %X %s" % (a, fam))
            if isinstance(ct, int) and ct != WAIT:
                calls.append(ct)
                s = self.summary(ct)
                if s[0]:
                    rate.append("%X %s" % (ct, s[0]))
                if s[1]:
                    pad.append("%X %s" % (ct, s[1]))
                if s[2]:
                    pat.append("%X %s" % (ct, s[2]))
        return dict(head=head, size=len(nodes), steps=self.steps(fn, nodes),
                    calls=sorted(set(calls)), pad=pad, rate=rate, patched=pat)


def sources(evidence):
    """{"direct"} and/or the callee rvas a flag's evidence names"""
    out = set()
    for e in evidence:
        first = e.split()[0]
        out.add("direct" if first == "direct" else int(first, 16))
    return out
