#!/usr/bin/env python3
"""Audit every call of the two turn-step helpers before the steer group scales
them (world_anims.h, group "steer").

  2DDF90(pos, heading, point, limit)   the clamped angle to a point: returns
                                       clamp(angle to the point - heading,
                                       -limit, limit); limit in xmm3
  2DA570(target, cur, k, limit)        the clamped approach: returns
                                       wrap(cur + clamp(wrap(target - cur) * k,
                                       -limit, limit)); k in xmm2, limit in xmm3

Enemies, animals, weapons, objects, the player and the camera turn with them,
and nothing in the port compensates them: a caller that turns by the result
every tick turned 4x as fast at 120. But neither function turns anything
itself, and not every caller uses the result as a turn: some compare it (is
the target in front?), pass it on, or snap to a target once when a state
starts. So nothing is scaled inside them. Each call whose result is this
tick's turn has its rel32 retargeted at a stub that scales the limit by s
(and, for 2DA570, makes the per-tick blend k into 1 - (1 - k)^(1/N)) and
jumps on; the rest are left.

A call is a turn step (selected) when all of these hold:

  * the result is accumulated into one field and stored back there on every
    path, and used for nothing else first (tools/step_flow.py): 2DDF90's
    added to the heading it was given, 2DA570's (already cur + the step)
    stored to the field it was given as cur;
  * the limit is in stock units: every leaf of its slice is an .rdata
    constant or a field in FIELD_REVIEWED (the enemy's speed +1080), and
    for 2DA570 k is a constant in (0, 1). A leaf that is a parameter of the
    function holding the call is resolved at every call of that function
    (it must have no other route in);
  * the limit is not a snap: a constant of pi or more (2DDF90 clamps an
    angle in (-pi, pi], so the whole turn happens in one tick) is left, as
    FixTurnRate leaves k >= 1: a snap is the same at any rate, and it is
    what a one-off facing at the start of a state uses (1D63F0 faces the
    point, then turns its back on it, once);
  * no leaf is a rate global or a mode table (the port's own compensation),
    and the function reads no rate global anywhere unless RATE_REVIEWED says
    why that read does not select the call (a slice follows data, not
    control). The enemies' pad rumbles, `cPad::ActSet(pad, id, (n << 60 fps
    flag) << 16)`, read the flag only for how long the pad shakes and are
    recognised as such (rumble_length);
  * no instruction of the slices, and not the call, is patched by another
    family (it would be scaled already).

A wrapper whose limit is its parameter times stock units, and whose callers
pass a snap as well as stock limits (23A2E0, the enemies' "turn toward
Amaterasu at rate x speed", 170 calls), cannot be scaled inside: each call of
the wrapper is audited instead, as a call of a helper whose limit is that
parameter, and a step has its rel32 retargeted at a stub that scales the
parameter. The wrapper must hand the parameter to nothing but step limits
(param_feeds_limits).

Everything else is left, with its reason: `query` (the result is used for
something else: the flow's first refusal), `snap`, `table` (the port's mode
table), `player` and `camera` (their own reviews: PLAYER, CAMERA), `wrapped`
(a call inside a wrapper whose callers are audited instead), or
`manual-left` (MANUAL, read by hand). A call no rule decides is a PROBLEM,
and tools/gen_world_anims.py refuses to write the steer group while there is
one.

    .venv/Scripts/python tools/survey_turn_steps.py
    -> docs/animation/turn_steps.csv, every call with its limit, k, result
       and decision
"""
import bisect
import collections
import csv
import math
import os
import re
import struct
import sys

import capstone
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_turn_callers as gtc  # noqa: E402
import step_flow  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_CSV = os.path.join(ROOT, "docs", "animation", "turn_steps.csv")
BASE = 0x180000000
POINT, APPROACH = 0x2DDF90, 0x2DA570
HELPERS = {POINT: ("the clamped angle to a point", "xmm3"),
           APPROACH: ("the clamped approach", "xmm3")}
RATE = {0xB6AC38: "time scale", 0xB6AC45: "mode byte", 0xB6AC44: "fps byte",
        0xB6AC40: "60 fps flag"}
SNAP = math.pi * 0.999

FIELD_REVIEWED = {
    0x1080: "the enemy's speed, its own time multiplier: 1.0, or 0.25 and 0.6 while "
            "slowed (23A1C5, 2809E9), set only from data constants: a limit times it is "
            "in stock units",
}
# the camera: 468000..484000 turn the view and its target with both helpers,
# partly through the per-mode table and the time scale; it is to be read as a
# whole
CAMERA = (0x468000, 0x484000, "the camera, which the port compensates in part: read as a whole "
          "elsewhere")
# Amaterasu (pl00..pl05): her turning is Phase A's (FixTurnRate, measured with
# the F3 harness); what she steers with these helpers is its own review
PLAYER = (0x3A0000, 0x3E0000, "the player's own code (pl00..pl05): her turning is Phase A's, "
          "and these calls are its own review")
# Calls read by hand and left, with why.
NOT_READ = "the limit comes from %s, not read yet: left until it is"
MANUAL = {
    0x24DB65: NOT_READ % "(130 - an integer product) degrees, the product of +E37 and a "
                         "register",
    0x2E5711: NOT_READ % "a getter on the object at 9C1F50 (23AD90) times 0.0873",
    0x38AE87: NOT_READ % "a call's result (38AC0B) times 0.1047",
    0x3909FF: NOT_READ % "a call's result (3904BC) times 0.2094",
    0x390EE7: NOT_READ % "a call's result (390C26) times 0.2094",
    0x3911AD: NOT_READ % "a call's result (390C26) times 0.6981",
    0x3918D0: NOT_READ % "a call's result (391621) times 0.1047",
    # read 2026-10-01: the weapons' aim 39F770, limit = the slow-motion factor
    # (23AD90) x the caller's rate, unscaled: the player group's callblend and
    # callscale rows (docs/animation/unattributed_reading/un_rows44.spec)
    0x39F848: "read: callblend row (player group), k 0.15 and the slow-motion x rate limit",
    0x39F86F: "read: callscale row (player group), the slow-motion x rate limit",
    0x564FFE: NOT_READ % "the short +E3E times 0.1396",
    # calls of the wrapper 23A2E0 (its limit is the parameter x speed)
    0x25A401: NOT_READ % "+E14 x 0.0524, a value the class ramps by speed x 0.3 a tick",
    0x2766F5: NOT_READ % "+E14 x 0.0175, a value the class ramps by speed x 0.3 a tick",
}
# Functions holding a step that read a rate global somewhere, read by hand.
RATE_REVIEWED = {
    0x2488B0: "the time scale (2489A7..248A1A, 248B1C) paces its vertical motion (+EC8) "
              "and a jump's speed; the turn (248B92) takes 0.1134 x speed on every path",
    0x249A90: "as 2488B0: the time scale paces +EC8 and the jump; the turn (249D25) takes "
              "0.1134 x speed on every path",
    0x246E60: "the time scale (247067, 2470BE) scales the forward speed +E48 its states "
              "set; the turns (2470A0, 2471C3: 0.0611 and 1.0472 to 23A2E0) run on every "
              "path through their states",
}


def references(img, secs, targets):
    """(calls, other): direct calls and jumps of any of `targets`, and any
    other route to them (a rip lea, a pointer in data)."""
    lo, hi = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
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
                t = int(i.op_str, 16)
                if t in targets:
                    calls.append((i.address, i.mnemonic, t, bytes(i.bytes)))
            elif i.mnemonic == "lea" and "rip" in i.op_str:
                g = re.search(r"rip ([+-]) (0x[0-9a-f]+)", i.op_str)
                if g:
                    t = i.address + i.size + int(g.group(2), 16) * (1 if g.group(1) == "+" else -1)
                    if t in targets:
                        other.append((i.address, "lea of %X" % t))
        pos = last if last > pos else pos + 1
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a & ~7, b - 8, 8):
            v = struct.unpack_from("<Q", img, off)[0] - BASE
            if v in targets:
                other.append((off, "%s holds the address of %X" % (name, v)))
    return calls, other


ACTSET, GETPAD = 0x182470, 0x182CE0      # cPad::ActSet(pad, id, length << 16), GetGlobalPad


def rumble_length(fn, a):
    """The read at `a` is `mov ecx, [60 fps flag]` whose only use is `shl r32,
    cl` of a rumble length handed to cPad::ActSet in r8d, in straight-line code
    (the enemies' pad rumbles: `(n << flag) << 16`). Such a read selects
    nothing but how long the pad shakes."""
    i = fn.ins[a]
    if i.mnemonic != "mov" or i.op_str.split(",")[0] != "ecx":
        return False
    shifted = None
    b = a + i.size
    for _ in range(24):
        j = fn.ins.get(b)
        if j is None or fn.preds.get(b, []) != [fn.order[fn.order.index(b) - 1]]:
            return False
        rd, wr = gtc.reads(j), gtc.writes(j)
        if j.mnemonic == "shl" and j.op_str.endswith(", cl") and shifted is None:
            shifted = gtc.reg_key(j, j.operands[0].reg)
        elif "rcx" in rd and shifted is None:
            return False
        if j.mnemonic == "call":
            t = j.operands[0].imm if j.operands[0].type == X.X86_OP_IMM else None
            if t == ACTSET:
                return shifted is not None
            if t != GETPAD:
                return False
        b += j.size
    return False


def rate_reads(fn):
    """Every read of a rate global, but the 60 fps flag's reads that only
    lengthen a pad rumble (rumble_length)."""
    out = []
    for a in fn.order:
        i = fn.ins[a]
        for op in i.operands:
            if op.type == X.X86_OP_MEM:
                t = gtc.rip_target(i, op)
                t = t if t is not None else op.mem.disp
                if t in RATE and not (t == 0xB6AC40 and rumble_length(fn, a)):
                    out.append("%X %s" % (a, RATE[t]))
    return out


def judge(leaves, helper):
    """(verdict, note) for a limit's leaves, params excluded: "stock", "snap",
    "table", or None and why not"""
    consts = [x for x in leaves if x[0] == "const"]
    fields = sorted({x[3] for x in leaves if x[0] == "field"})
    if any(x[0] in ("rate", "table", "tablefixed") for x in leaves):
        return "table", "a rate or mode-table leaf: compensated by the port"
    odd = [x for x in leaves if x[0] not in ("const", "field")]
    if odd:
        return None, "leaves the rules cannot decide: " + ", ".join(gtc.render(x) for x in odd[:3])
    unknown = [f for f in fields if f not in FIELD_REVIEWED]
    if unknown:
        return None, "fields not reviewed: " + ", ".join("+%X" % f for f in unknown)
    if any(c[3] is None or not c[3] > 0 for c in consts):
        return None, "a constant that is not positive"
    if helper == POINT and any(c[3] >= SNAP for c in consts):
        return "snap", "a limit of %g: the whole turn in one tick" % max(c[3] for c in consts)
    return "stock", "constants" + ("" if not fields else " and " +
                                   ", ".join("+%X" % f for f in fields))


class Survey:
    def __init__(self):
        self.img, self.secs, _f, _sha = gtc.load_image()
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.roots, self.starts, _e = gtc.pdata_roots(self.img, self.secs)
        self.pr = gtc.patched_ranges()
        self.pstarts = [r[0] for r in self.pr]
        self.fcache = {}
        self._callers = None

    def func(self, at):
        k = bisect.bisect_right(self.starts, at) - 1
        frag = self.starts[k] if k >= 0 else None
        if frag is None or not any(b <= at < e for b, e in self.roots[frag][1]):
            return None
        root, frags = self.roots[frag]
        if root not in self.fcache:
            self.fcache[root] = gtc.Func(self.img, root, frags, self.md)
        return self.fcache[root]

    def callers(self, fn_root):
        """(calls, other routes) of a function"""
        return references(self.img, self.secs, {fn_root})

    def leaves_at(self, fn, at, reg, depth=0):
        """[(leaves, where)]: the leaves of reg at `at`, a parameter of the
        function resolved at each of its calls (one row per call), or a
        problem string"""
        sl = step_flow.Flow(self.img, self.secs, fn, self.md).sl
        t = sl.value(at, reg)
        leaves = list(gtc.leaves(t))
        params = sorted({x[1] for x in leaves if x[0] == "param"})
        rest = [x for x in leaves if x[0] != "param"]
        touched = {x for x in sl.touched if x in fn.ins}
        if not params:
            return [(rest, "", touched)]
        if depth or len(params) > 1:
            return "the limit is %s" % gtc.render(t)
        calls, other = self.callers(fn.root)
        if other or not calls:
            return "the limit is its parameter %s, and %X has %s" % (
                params[0], fn.root, "other routes in" if other else "no callers")
        out = []
        for c, mn, _t, _raw in calls:
            cf = self.func(c)
            if cf is None or mn != "call":
                return "%X reaches %X by %s outside a function" % (c, fn.root, mn)
            sub = self.leaves_at(cf, c, params[0], depth + 1)
            if isinstance(sub, str):
                return sub
            for lv, _w, tc in sub:
                out.append((rest + lv, "%X" % c, touched | tc))
        return out

    def patched(self, fn, touched):
        return sorted({gtc.patched_by(self.pr, self.pstarts, x, fn.ins[x].size)
                       for x in touched if x in fn.ins} -
                      {None, "world_anims.h", "world_anims.h call"})


def param_feeds_limits(img, md, fn, reg, step_calls):
    """The parameter `reg` (and its copies and products) reaches nothing but
    the limit register of the calls in step_calls, from the function's entry:
    any other call it is live at must not read it (step_flow.callee_xmm_args)."""
    work, seen = [(fn.root, frozenset([reg]))], set()
    while work:
        a, t = work.pop()
        if (a, t) in seen or not t:
            continue
        seen.add((a, t))
        if a not in fn.ins:
            return "leaves the function at %X" % a
        i = fn.ins[a]
        m = i.mnemonic
        rd, wr = gtc.reads(i), gtc.writes(i)
        nt = set(t)
        if m == "call":
            live = t & set(step_flow.ARG_XMM)
            lim = step_calls.get(a)
            if lim is not None:
                if live != {lim}:
                    return "the step call at %X gets %s" % (a, "/".join(sorted(live)) or "none")
            elif live:
                tgt = i.operands[0].imm if i.operands[0].type == X.X86_OP_IMM else None
                reads = set(step_flow.ARG_XMM) if tgt is None else \
                    set(step_flow.callee_xmm_args(img, md, tgt))
                if live & reads:
                    return "reaches the call at %X in %s" % (a, "/".join(sorted(live & reads)))
            nt -= step_flow.VOLATILE
            work.append((a + i.size, frozenset(nt)))
            continue
        if m in ("ret", "retf"):
            continue
        if rd & t:
            ops = i.operands
            ok = m in ("mulss", "movaps", "movss") and ops[0].type == X.X86_OP_REG and \
                (len(ops) < 2 or ops[1].type != X.X86_OP_MEM or m == "mulss")
            if not ok:
                return "read by %X %s %s" % (a, m, i.op_str)
            nt |= {gtc.reg_key(i, ops[0].reg)}
        else:
            nt -= wr
        if m.startswith("j"):
            if i.operands[0].type != X.X86_OP_IMM:
                return "indirect jump at %X" % a
            work.append((i.operands[0].imm, frozenset(nt)))
            if m != "jmp":
                work.append((a + i.size, frozenset(nt)))
        else:
            work.append((a + i.size, frozenset(nt)))
    return None


def audit():
    """(rows, problems). A row per call of a helper, and per call of a
    wrapper; `reg` is the register the stub scales."""
    sv = Survey()
    img, secs = sv.img, sv.secs
    calls, other = references(img, secs, set(HELPERS))
    problems = ["%X: %s, a route the audit cannot follow" % o for o in other]
    rows, reviewed, used_manual = [], set(), set()
    wrappers = {}      # wrapper root: (param register, {inner call: limit register})
    for at, kind, helper, raw in calls:
        row = dict(site="%X" % at, kind=kind, helper="%X" % helper, function="", reg="",
                   limit="", k="", result="", decision="", evidence="", bytes=raw.hex().upper())
        rows.append(row)
        fn = sv.func(at)
        if fn is None:
            row.update(decision="PROBLEM", evidence="no .pdata function holds it")
            continue
        root = fn.root
        row["function"] = "%X" % root
        fl = step_flow.Flow(img, secs, fn, sv.md)
        sl = fl.sl
        row["limit"] = gtc.render(sl.value(at, "xmm3"))
        row["reg"] = "xmm3"
        notes = []
        kfail = None
        if helper == APPROACH:
            kv = sl.value(at, "xmm2")
            row["k"] = gtc.render(kv)
            kl = list(gtc.leaves(kv))
            if any(x[0] in ("rate", "table", "tablefixed") for x in kl):
                kfail = "table"
            elif not (kl and all(x[0] == "const" and x[3] is not None and 0 < x[3] < 1
                                 for x in kl)):
                kfail = "k is not a constant in (0, 1): " + row["k"][:60]
        # the result
        if kind != "call":
            why = "a tail jump: the result is returned to the caller's caller"
        elif helper == POINT:
            _st, _fa, why = fl.run(at + 5, {"xmm0": ("step",)})
        else:
            f = fl.field_value(at, "xmm1")
            if f is None:
                why = "cur is not one field: " + gtc.render(sl.value(at, "xmm1"))[:60]
            else:
                _st, _fa, why = fl.run(at + 5, {"xmm0": ("sum", f)})
        row["result"] = why or "accumulated and stored"
        region = next((r for r in (CAMERA, PLAYER) if r[0] <= root < r[1]), None)
        if region:
            row["decision"] = "camera" if region is CAMERA else "player"
            row["evidence"] = region[2]
            continue
        if at in MANUAL:
            used_manual.add(at)
            row["decision"], row["evidence"] = "manual-left", MANUAL[at]
            continue
        if why:
            row["decision"], row["evidence"] = "query", ""
            continue
        if kfail:
            row["decision"] = "table" if kfail == "table" else "PROBLEM"
            row["evidence"] = "k from a rate or mode table: compensated by the port" \
                if kfail == "table" else kfail
            continue
        res = sv.leaves_at(fn, at, "xmm3")
        if isinstance(res, str):
            row["decision"], row["evidence"] = "PROBLEM", res
            continue
        verdicts = [(judge(lv, helper), w, tc) for lv, w, tc in res]
        if any(v is None for (v, _n), _w, _t in verdicts) and not verdicts[0][1]:
            row["decision"] = "PROBLEM"
            row["evidence"] = "; ".join(n for (v, n), _w, _t in verdicts if v is None)[:300]
            continue
        kinds = {v for (v, _n), _w, _t in verdicts}
        touched = set().union(*(tc for _v, _w, tc in verdicts)) | {at}
        pat = sv.patched(fn, touched)
        if pat:
            row["decision"], row["evidence"] = "patched", "already scaled by " + ", ".join(pat)
            continue
        reads = rate_reads(fn)
        if reads and root not in RATE_REVIEWED:
            row["decision"] = "PROBLEM"
            row["evidence"] = "its function reads %s: read it and add it to RATE_REVIEWED" \
                % ", ".join(reads[:3])
            continue
        if reads:
            reviewed.add(root)
            notes.append("its function reads %s: %s" % (", ".join(reads[:3]),
                                                        RATE_REVIEWED[root]))
        if kinds == {"stock"}:
            row["decision"] = "step"
            notes.insert(0, "; ".join(sorted({n for (_v, n), _w, _t in verdicts})) +
                         (" (at every call of %X)" % root if verdicts[0][1] else ""))
        elif kinds <= {"snap", "table"} and len(kinds) == 1:
            row["decision"] = kinds.pop()
            notes.insert(0, verdicts[0][0][1])
        elif verdicts[0][1]:
            # a parameter stock at some calls and not at others: each is audited
            params = sorted({x[1] for x in gtc.leaves(sl.value(at, "xmm3")) if x[0] == "param"})
            row["decision"] = "wrapped"
            notes.insert(0, "the limit is %s's %s, stock at some calls and not at others: "
                            "each call of %X is audited" % ("%X" % root, params[0], root))
            wrappers.setdefault(root, (params[0], {}))[1][at] = "xmm3"
        else:
            row["decision"] = "PROBLEM"
            notes.insert(0, "verdicts " + ", ".join(sorted(kinds)))
        row["evidence"] = "; ".join(n for n in notes if n)
    # the wrappers' calls
    for root, (reg, inner) in sorted(wrappers.items()):
        fn = sv.func(root)
        why = param_feeds_limits(img, sv.md, fn, reg, inner)
        wcalls, _other = sv.callers(root)
        for at, kind, _t, raw in wcalls:
            row = dict(site="%X" % at, kind=kind, helper="%X" % root, function="", reg=reg,
                       limit="", k="", result="the wrapper's", decision="", evidence="",
                       bytes=raw.hex().upper())
            rows.append(row)
            cf = sv.func(at)
            row["function"] = "%X" % cf.root if cf else ""
            if why:
                row["decision"] = "PROBLEM"
                row["evidence"] = "%X's parameter %s: %s" % (root, reg, why)
                continue
            sl = step_flow.Flow(img, secs, cf, sv.md).sl
            t = sl.value(at, reg)
            row["limit"] = gtc.render(t)
            region = next((r for r in (CAMERA, PLAYER) if r[0] <= cf.root < r[1]), None)
            if region:
                row["decision"] = "camera" if region is CAMERA else "player"
                row["evidence"] = region[2]
                continue
            if at in MANUAL:
                used_manual.add(at)
                row["decision"], row["evidence"] = "manual-left", MANUAL[at]
                continue
            if kind != "call":
                row["decision"] = "PROBLEM"
                row["evidence"] = "a tail jump into the wrapper"
                continue
            (v, note) = judge(list(gtc.leaves(t)), POINT)
            pat = sv.patched(cf, {x for x in sl.touched if x in cf.ins} | {at})
            reads = rate_reads(cf)
            if v is None:
                row["decision"], row["evidence"] = "PROBLEM", note
            elif pat:
                row["decision"], row["evidence"] = "patched", "already scaled by " + ", ".join(pat)
            elif v != "stock":
                row["decision"], row["evidence"] = v, note
            elif reads and cf.root not in RATE_REVIEWED:
                row["decision"] = "PROBLEM"
                row["evidence"] = "its function reads %s: read it and add it to " \
                    "RATE_REVIEWED" % ", ".join(reads[:3])
            else:
                if reads:
                    reviewed.add(cf.root)
                row["decision"] = "step"
                row["evidence"] = "%s; %X turns the heading by it every call" % (note, root)
    for a in sorted(set(RATE_REVIEWED) - reviewed):
        problems.append("%X: stale RATE_REVIEWED entry" % a)
    for a in sorted(set(MANUAL) - used_manual):
        problems.append("%X: stale MANUAL entry" % a)
    problems += ["%s: %s" % (r["site"], r["evidence"]) for r in rows if r["decision"] == "PROBLEM"]
    return rows, problems


def selected(rows):
    """[(call rva, target, register, blend, call bytes)] of the turn steps:
    blend is True for 2DA570's calls (k converted too)"""
    return [(int(r["site"], 16), int(r["helper"], 16), r["reg"],
             int(r["helper"], 16) == APPROACH, bytes.fromhex(r["bytes"]))
            for r in rows if r["decision"] == "step"]


def main():
    rows, problems = audit()
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = collections.Counter((r["helper"], r["decision"]) for r in rows)
    print("%d calls: %s" % (len(rows), ", ".join("%s %s %d" % (h, d, n)
                                                for (h, d), n in sorted(by.items()))))
    for p in problems:
        print("PROBLEM " + p)
    print("turn steps: %s" % ("every call decided" if not problems else
                               "%d problems" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
