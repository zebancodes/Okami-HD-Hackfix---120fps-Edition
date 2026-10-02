#!/usr/bin/env python3
"""Audit every caller of the two "turn toward" helpers before their limit is
scaled (world_anims.h, group "turn").

main+20E210 turns an actor's heading (+B4) toward a point, main+20E290 toward
an angle; each moves it by at most a limit a tick, passed in xmm2:

    heading = wrap(heading + clamp(wrap(target - heading), -limit, limit))

world_anims.h scales that limit by s = 1/N inside both functions, which is
right for a caller that passes a limit in stock units (radians per stock tick)
and wrong for one whose limit the engine already compensated (it would be
scaled twice). So, as tools/gen_turn_callers.py does for 2DA510, nothing here
trusts a list: every route to the two functions is found (direct calls and
jumps in a full decode, pointers in data, rip leas), and the limit of each call
is sliced backwards through its function (gen_turn_callers.Slicer) to its
leaves. A call is accepted when

  * every leaf is an .rdata constant, or a field in FIELD_REVIEWED (read by
    hand: what writes it, and that it holds stock units), or the call is in
    MANUAL with the reason;
  * no leaf is a rate global (the time scale, the mode byte, the fps byte, the
    60 fps flag): that would be a compensated limit;
  * its function reads no rate global anywhere, unless RATE_REVIEWED says why
    that read does not select the limit (a slice follows data, not control).

Anything else is a problem, and tools/gen_world_anims.py refuses to emit the
turn sites while there is one.

    .venv/Scripts/python tools/survey_turn_limits.py
    -> docs/animation/turn_limits.csv, every call with its limit and evidence
"""
import bisect
import collections
import csv
import os
import re
import struct
import sys

import capstone
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_turn_callers as gtc  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_CSV = os.path.join(ROOT, "docs", "animation", "turn_limits.csv")
BASE = 0x180000000
TURNS = {0x20E210: "toward a point", 0x20E290: "toward an angle"}
RATE = {0xB6AC38: "time scale", 0xB6AC45: "mode byte", 0xB6AC44: "fps byte",
        0xB6AC40: "60 fps flag"}

# Fields a limit may be built from, read by hand: what writes them.
FIELD_REVIEWED = {
    0x1080: "the enemy's own time multiplier (it also paces +1270's countdown in 2CF9E0): "
            "set only to data constants (1.0, 0.0), none from a rate global",
    0xF54: "the motion playback rate: data, in stock units; the motion advance 4B9C80 "
           "applies the time scale to it (mode_constants.h 4B9CA9)",
    0x1CA0: "set by the setters 26C090 and 26C280 from their float argument; their callers "
            "all pass constants",
    0x1580: "set by 2B5B20 (0.2793) and the setters 2B5FA0, 2B6300, whose callers all pass "
            "constants",
    0x16E0: "set by 2CA3D0 (0.0524), 2C83E0 and the setters 2CA220..2CA540, whose callers "
            "all pass constants; 2C83E0 reads no rate global",
    0x1270: "in the class these callers belong to (290000..2B0000), set only by 2940C0 to "
            "0.2618 (15 degrees)",
    0x1060: "set only to float constants, 0.0873 to pi, by 27 stores in the enemy setups "
            "(and 0 in 4E54F0, 4F9590)",
    0x4FA8: "the class's time in its state (5E..5F: += +1080 * +F54 a tick at 5ECB48, "
            "cleared by each state, thresholds 15, 41, 60, 110 ticks): the limit, whole "
            "degrees of it * 0.5 deg, ramps with that time and is stock units at each tick "
            "(the counter itself is an unconverted enemy timer)",
}
# Calls read by hand, and why their limit is in stock units.
MANUAL = {
    0x304AA7: "the waypoint follower 3049D0 (a leaf: no .pdata): limit = min(its argument "
              "+ (ticks stuck - 30) * 0.017, pi); its callers pass the constants 679C14 and "
              "679C04, and the stuck count (+1272) is on stock ticks in world_anims.h",
    0x62E64C: "the limit is a .data table (7D26C4) indexed by the type: data",
    0x62E870: "as 62E64C: the same .data table (7D26C4)",
    0x2974D2: "a limit built each tick from the angle and distance to the target, times "
              "constants: geometry in stock units; the function reads no rate global",
    0x298EA0: "as 2974D2 (the same class's other state)",
    0x5D1DA6: "a limit that ramps with its own tick count (+53A4) and the distance: stock "
              "units at every tick (the count itself is an unconverted enemy timer)",
}
# Caller functions that read a rate global somewhere, read by hand.
RATE_REVIEWED = {
    0x485390: "its one time-scale read (485875) is gravity on +E54, after the turn; the "
              "limit is the constant 679C74",
}


def references(img, secs):
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
                if t in TURNS:
                    calls.append((i.address, i.mnemonic, t))
            elif i.mnemonic == "lea" and "rip" in i.op_str:
                g = re.search(r"rip ([+-]) (0x[0-9a-f]+)", i.op_str)
                if g:
                    t = i.address + i.size + int(g.group(2), 16) * (1 if g.group(1) == "+" else -1)
                    if t in TURNS:
                        other.append((i.address, "lea of %X" % t))
        pos = last if last > pos else pos + 1
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a & ~7, b - 8, 8):
            v = struct.unpack_from("<Q", img, off)[0] - BASE
            if v in TURNS:
                other.append((off, "%s holds the address of %X" % (name, v)))
    return calls, other


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


def audit():
    """(rows, problems)"""
    img, secs, _f, _sha = gtc.load_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    roots, starts, _e = gtc.pdata_roots(img, secs)
    calls, other = references(img, secs)
    problems = ["%X: %s, a route the audit cannot follow" % o for o in other]
    rows, fcache, reviewed = [], {}, set()
    for at, kind, target in calls:
        row = dict(site="%X" % at, kind=kind, target="%X" % target, function="", limit="",
                   status="", evidence="")
        rows.append(row)
        k = bisect.bisect_right(starts, at) - 1
        frag = starts[k] if k >= 0 else None
        if frag is None or not any(b <= at < e for b, e in roots[frag][1]):
            if at in MANUAL:
                row.update(status="manual", evidence="no .pdata function holds it; " + MANUAL[at])
            else:
                row.update(status="PROBLEM", evidence="no .pdata function holds it")
            continue
        root, frags = roots[frag]
        if root not in fcache:
            fcache[root] = gtc.Func(img, root, frags, md)
        fn = fcache[root]
        row["function"] = "%X" % root
        sl = gtc.Slicer(img, secs, fn)
        t = sl.value(at, "xmm2")
        row["limit"] = gtc.render(t)
        leaves = list(gtc.leaves(t))
        rates = [x for x in leaves if x[0] in ("rate", "table", "tablefixed")]
        fields = sorted({x[3] for x in leaves if x[0] == "field"})
        odd = [x for x in leaves if x[0] not in ("const", "field", "rate", "table", "tablefixed")]
        notes = []
        if rates:
            row["status"] = "PROBLEM"
            notes.append("a rate or mode-table leaf: the limit may be compensated already")
        elif at in MANUAL:
            row["status"] = "manual"
            notes.append(MANUAL[at])
        elif odd:
            row["status"] = "PROBLEM"
            notes.append("leaves the rules cannot decide: " +
                         ", ".join(gtc.render(x) for x in odd[:3]))
        else:
            unknown = [f for f in fields if f not in FIELD_REVIEWED]
            if unknown:
                row["status"] = "PROBLEM"
                notes.append("fields not reviewed: " + ", ".join("+%X" % f for f in unknown))
            else:
                row["status"] = "stock"
                notes.append("constants" + ("" if not fields else " and reviewed fields " +
                                            ", ".join("+%X" % f for f in fields)))
        reads = rate_reads(fn)
        if reads:
            if root in RATE_REVIEWED:
                reviewed.add(root)
                notes.append("its function reads %s: %s" % (", ".join(reads[:3]),
                                                            RATE_REVIEWED[root]))
            else:
                row["status"] = "PROBLEM"
                notes.append("its function reads %s: read it and add it to RATE_REVIEWED"
                             % ", ".join(reads[:3]))
        row["evidence"] = "; ".join(notes)
    for a in sorted(set(RATE_REVIEWED) - reviewed):
        problems.append("%X: stale RATE_REVIEWED entry" % a)
    for a in sorted(set(MANUAL) - {int(r["site"], 16) for r in rows}):
        problems.append("%X: stale MANUAL entry" % a)
    problems += ["%s: %s" % (r["site"], r["evidence"]) for r in rows if r["status"] == "PROBLEM"]
    return rows, problems


def main():
    rows, problems = audit()
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = collections.Counter((r["target"], r["status"]) for r in rows)
    print("%d calls: %s" % (len(rows), ", ".join("%s %s %d" % (t, s, n)
                                                for (t, s), n in sorted(by.items()))))
    for p in problems:
        print("PROBLEM " + p)
    print("turn limits: %s" % ("all in stock units" if not problems else
                                "%d problems" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
