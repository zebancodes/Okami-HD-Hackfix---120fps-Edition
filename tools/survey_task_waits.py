#!/usr/bin/env python3
"""Survey every call of the task wait before anything converts it.

The game's scripted logic runs in tasks: coroutines on their own threads, woken
by cTaskManager::step (main+456600) once a tick. A task yields with the wait
main+4567C0(task, n): it stores n in the task's countdown (+12), and the step
counts that down by one a tick (4566CB) and wakes the task at 0. So `wait(n)`
lasts n ticks, whatever the frame rate: at 120 fps every timed pause is a
quarter of stock's, and a loop that yields with wait(1) runs four passes per
stock tick. Nothing in the port compensates it.

Whether a wait may be converted depends on what its length is and on what the
loop around it does, so this finds every route to the wait (direct calls and
jumps in a full decode, pointers in data, rip leas) and, for each call:

  * slices edx (n) back to its leaves (gen_turn_callers.Slicer): a constant,
    a field, a parameter, a call's result, or a rate global (the fps byte, the
    mode byte, the time scale, a mode table): a length already in real time;
  * says whether the call sits on a cycle of its function's control flow
    (a loop that yields), and the loop's other calls;
  * records whether its function reads a rate global anywhere;
  * for a call on a cycle, describes its innermost loop (task_wait_loops.py):
    the loop's head, the evidence that a pass steps state (or none: a poll),
    and what in the loop or below it reads the pad or a rate global or is
    already patched, each with its source (the loop itself or the call).

    .venv/Scripts/python tools/survey_task_waits.py
    -> docs/animation/task_waits.csv, one row per call
"""
import bisect
import collections
import csv
import os
import re
import sys

import capstone
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_turn_callers as gtc  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_CSV = os.path.join(ROOT, "docs", "animation", "task_waits.csv")
WAIT = 0x4567C0
RATE = {0xB6AC38: "time scale", 0xB6AC45: "mode byte", 0xB6AC44: "fps byte",
        0xB6AC40: "60 fps flag"}


def references(img, secs):
    """([(site, mnemonic)], [other routes])"""
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
                if int(i.op_str, 16) == WAIT:
                    calls.append((i.address, i.mnemonic))
            elif i.mnemonic == "lea" and "rip" in i.op_str:
                g = re.search(r"rip ([+-]) (0x[0-9a-f]+)", i.op_str)
                if g and i.address + i.size + int(g.group(2), 16) * \
                        (1 if g.group(1) == "+" else -1) == WAIT:
                    other.append((i.address, "lea of the wait"))
        pos = last if last > pos else pos + 1
    import struct
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a & ~3, b - 4, 4):
            if struct.unpack_from("<I", img, off)[0] == WAIT:
                other.append((off, "%s holds its rva" % name))
        for off in range(a & ~7, b - 8, 8):
            if struct.unpack_from("<Q", img, off)[0] == gtc.BASE + WAIT:
                other.append((off, "%s holds its address" % name))
    return calls, other


def on_cycle(fn, at):
    """True if `at` can reach itself through the function's control flow."""
    succs = collections.defaultdict(list)
    for a, ps in fn.preds.items():
        for p in ps:
            succs[p].append(a)
    work, seen = list(succs.get(at, [])), set()
    while work:
        a = work.pop()
        if a == at:
            return True
        if a in seen:
            continue
        seen.add(a)
        work.extend(succs.get(a, []))
    return False


def rate_reads(fn):
    out = []
    for a in fn.order:
        i = fn.ins[a]
        for op in i.operands:
            if op.type == X.X86_OP_MEM:
                t = gtc.rip_target(i, op)
                t = t if t is not None else op.mem.disp
                if t in RATE:
                    out.append("%X %s" % (a, RATE[t]))
    return out


def const_value(sl, fn, t, depth=0):
    """The integer t always holds, or None. Folds what the compiler uses to
    build a small constant: `xor r, r`, `lea r, [base + d]` from a known base
    (a zeroed register plus 30 is wait(30)), add/sub/inc/dec of known values,
    and a phi whose alternatives agree."""
    if t is None or depth > 12:
        return None
    k = t[0]
    if k == "imm":
        return t[2]
    if k == "phi":
        vals = {const_value(sl, fn, x, depth + 1) for x in t[1]}
        return vals.pop() if len(vals) == 1 and None not in vals else None
    if k == "opaque":
        i = fn.ins[t[1]]
        ops = i.operands
        if i.mnemonic == "xor" and len(ops) == 2 and ops[0].type == X.X86_OP_REG and \
                ops[1].type == X.X86_OP_REG and ops[0].reg == ops[1].reg:
            return 0
        if i.mnemonic == "or" and len(ops) == 2 and ops[1].type == X.X86_OP_IMM and \
                ops[1].imm & 0xFFFFFFFF == 0xFFFFFFFF:
            return 0xFFFFFFFF   # the compiler's -1 register: or ebx, -1
        return None
    if k == "leacalc":
        i = fn.ins[t[1]]
        m = i.operands[1].mem
        if m.index or not m.base:
            return None
        base = sl.value(i.address, gtc.reg_key(i, m.base))
        v = const_value(sl, fn, base, depth + 1)
        return None if v is None else (v + m.disp) & 0xFFFFFFFF
    if k == "op":
        _k, _a, mn, left, right = t
        lv = const_value(sl, fn, left, depth + 1)
        if mn in ("inc", "dec"):
            return None if lv is None else (lv + (1 if mn == "inc" else -1)) & 0xFFFFFFFF
        rv = const_value(sl, fn, right, depth + 1)
        # the compiler's -1 and 0 registers: or r, -1 and and r, 0, whatever r held
        if mn == "or" and rv is not None and rv & 0xFFFFFFFF == 0xFFFFFFFF:
            return 0xFFFFFFFF
        if mn == "and" and rv is not None and rv & 0xFFFFFFFF == 0:
            return 0
        if lv is None or rv is None:
            return None
        if mn == "add":
            return (lv + rv) & 0xFFFFFFFF
        if mn == "sub":
            return (lv - rv) & 0xFFFFFFFF
    return None


def classify(t, value):
    leaves = list(gtc.leaves(t))
    if any(x[0] in ("rate", "table", "tablefixed") for x in leaves):
        return "rate"
    if value is not None:
        return "pass" if value == 1 else "timed"
    if leaves and all(x[0] == "imm" for x in leaves):
        # a choice between constants, e.g. phi(50 | 35)
        return "pass" if all(x[2] == 1 for x in leaves) else "timed"
    return "data"


def audit(loops=True):
    """(rows, problems)"""
    img, secs, _f, _sha = gtc.load_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    roots, starts, _e = gtc.pdata_roots(img, secs)
    calls, other = references(img, secs)
    problems = ["%X: %s, a route the survey cannot follow" % o for o in other]
    rows, fcache = [], {}
    for at, mn in calls:
        row = dict(site="%X" % at, kind=mn, function="", length="", value="", cls="",
                   loop="", rate_reads="", head="", steps="", pad="", rate="", patched="",
                   calls="")
        rows.append(row)
        k = bisect.bisect_right(starts, at) - 1
        frag = starts[k] if k >= 0 else None
        if frag is None or not any(b <= at < e for b, e in roots[frag][1]):
            row["cls"] = "nofunction"
            continue
        root, frags = roots[frag]
        if root not in fcache:
            fcache[root] = gtc.Func(img, root, frags, md)
        fn = fcache[root]
        row["function"] = "%X" % root
        sl = gtc.Slicer(img, secs, fn)
        t = sl.value(at, "rdx")
        row["length"] = gtc.render(t)
        v = const_value(sl, fn, t)
        if v is not None:
            v &= 0xFFFF   # the countdown is a word
            row["value"] = "%d" % v
        row["cls"] = classify(t, v)
        row["loop"] = "loop" if on_cycle(fn, at) else ""
        row["rate_reads"] = " ".join(rate_reads(fn)[:3])
    if loops:
        import task_wait_loops as twl
        prog = twl.Program()
        for row in rows:
            if not row["loop"]:
                continue
            d = prog.describe(int(row["site"], 16))
            if d is None:
                problems.append("%s: on a cycle but in no natural loop" % row["site"])
                continue
            row["head"] = "%X" % d["head"]
            for k in ("steps", "pad", "rate", "patched"):
                row[k] = " | ".join(d[k])
            row["calls"] = " ".join("%X" % c for c in d["calls"])
    return rows, problems


def main():
    rows, problems = audit()
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    c = collections.Counter((r["cls"], r["loop"]) for r in rows)
    print("task waits: %d calls in %d functions" % (
        len(rows), len({r["function"] for r in rows})))
    for (cls, loop), n in sorted(c.items(), key=lambda x: -x[1]):
        print("  %-10s %-5s %d" % (cls, loop or "-", n))
    vals = collections.Counter(int(r["value"]) for r in rows if r["value"])
    print("  constant lengths:", ", ".join("%d x%d" % (v, n) for v, n in sorted(vals.items())))
    lp = [r for r in rows if r["loop"]]
    c = collections.Counter(("steps" if r["steps"] else "poll",
                             "".join(k[0].upper() if r[k] else "-"
                                     for k in ("pad", "rate", "patched"))) for r in lp)
    print("  loop calls by their innermost loop (steps or poll, P/R/P = pad, rate, patched):")
    for (st, fl), n in sorted(c.items(), key=lambda x: -x[1]):
        print("    %-6s %s %d" % (st, fl, n))
    for p in problems:
        print("PROBLEM " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
