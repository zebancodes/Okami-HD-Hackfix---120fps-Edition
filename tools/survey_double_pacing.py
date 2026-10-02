#!/usr/bin/env python3
"""Audit the world rows that pace on the frame counter's phase (count, count2,
countlast, gatefn, gate0, callgate, and notyet, which holds a branch "not yet"
off that phase) for the two ways of being wrong a row's own proof cannot see:

1. A wait inside one tick. A loop that calls into the game until a result
   changes (`while (busy) f();`) runs inside one tick, where the frame counter
   does not move, so a paced counter its exit waits on counts on every pass or
   never: on 2026-10-01 the exit (4B69A0 -> 494120) hung on the loader's
   barriers. The same goes for the loops task_waits.h paces to one pass a stock
   tick: their passes keep one phase, so a paced row under them counts on every
   pass or on none.
     spin   a paced row reachable (SPIN_DEPTH calls) from a spin loop's exit:
            the call whose result the loop tests, or every call in a loop that
            tests memory
     paced  a paced row reachable (PACED_DEPTH calls) from the calls of a loop
            task_waits.h paces (task_waits.csv `calls`)

2. A double. Another family already scales the thing to real time, so pacing it
   as well makes it N times its stock length (the screen fade 3E2C38 against
   3E2ACE's length x N made every fade 4x long).
     leaf   a count in a function that calls a mode_multipliers.h length leaf
            (a function under LEAF_SIZE bytes holding the site)
     field  a count on a field that a flag/mode length row (or a
            mode_multipliers.h site) within FIELD_SPAN bytes stores
     gate   a gatefn or callgate whose function reaches (GATE_DEPTH calls) a
            site of a family that scales a tick's step (phase steps, decays,
            mode constants and multipliers, turn rates, frame gates and
            clocks, integer skips, the world's own scaled rows)
     data   any world row within DATA_SPAN instructions of a read of a
            constant that a family rewrites in .data rather than in code: the
            run fix's jog parameters and charge frames (dinput8_proxy.cpp
            kJogParams, kChargeFramesRva) and the mode tables
            (mode_constants.h). No patched-range check sees those writes; on
            2026-10-02 rows on Amaterasu's run (3B2CF0) scaled her acceleration
            and paced her sprint charge on top of them, and at 120 she never
            left the jog.

Every finding must be in REVIEWED (read: not a problem, and why) or OPEN (a real
problem left for a later round, and what it does); anything else fails.

    .venv/Scripts/python tools/survey_double_pacing.py
"""
import bisect
import collections
import contextlib
import csv
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_patch_sites as cps  # noqa: E402
import gen_world_anims as gwa  # noqa: E402
import xrefs  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
DOCS = os.path.join(ROOT, "docs", "animation")
BASE = 0x180000000
PACED_KINDS = ("count", "count2", "countlast", "gatefn", "gate0", "callgate", "notyet", "notyetneg",
               "notyetb")
SPIN_DEPTH, PACED_DEPTH, GATE_DEPTH, YIELD_DEPTH = 6, 4, 3, 4
TASK_WAIT = 0x4567C0  # main+4567C0(task, n): a loop that reaches it yields
# functions that run a tick's scaled step a few calls below them
CONSUMERS = {
    0x1B54E0: "the layout update (its tracks run to lengths mode_multipliers.h scales)",
}
LEAF_SIZE, FIELD_SPAN = 0x60, 0x4000
DATA_SPAN = 10  # instructions before a row's site (and 3 after) searched for a data read
STEP_FAMILIES = ("phase_steps.h", "decay_factors.h", "mode_constants.h", "mode_multipliers.h",
                 "turn_callers.h", "frame_gates.h", "frame_clocks.h", "integer_skips.h",
                 "hoisted_decay.h")

# (check, row site, the spin/loop/length/site it was found against) -> why it is fine
REVIEWED = {
    ("paced", 0x443E44, 0x44A160): "the sound play 44A160 updates the sound it starts once; "
        "its every-tick update is the sound manager's walk (448D30 -> 4437A0), on stock ticks",
    ("paced", 0x444301, 0x44A160): "as 443E44",
    ("paced", 0x444559, 0x44A160): "as 443E44",
    ("paced", 0x444714, 0x44A160): "as 443E44",
    ("paced", 0x451A30, 0x44A160): "as 443E44; 451A30's every-tick callers are 455B7F/455BAF",
    ("paced", 0x443E44, 0x44C200): "as 443E44 (44C200 is a thunk into the sound play 44D560 "
        "with a default volume)",
    ("paced", 0x444301, 0x44C200): "as 443E44",
    ("paced", 0x444559, 0x44C200): "as 443E44",
    ("paced", 0x444714, 0x44C200): "as 443E44",
    ("paced", 0x451A30, 0x44C200): "as 443E44",
    ("spin", 0x1928F6, 0x1A02A0): "1A26B0 runs 1A02A0 until it has spawned +30E particles; "
        "1A02A0 counts +264 itself, unpaced, and this is a new particle's first step (its "
        "age +260), which the exit does not read",
    ("spin", 0x19292C, 0x1A02A0): "as 1928F6 (a new particle's fade window +277)",
    ("spin", 0x4BDA0A, 0x493E20): "the movie rumble's PWM phase; none of 493E20's idle "
        "tests (23C0C0, 210580, 210640, 49D500, 447130, 4A3F10) reads it",
    ("spin", 0x23D789, 0x493E20): "a battle record's elapsed time +40; the battle list's "
        "idle test 23C0C0 reads the list's +88, not it",
    ("gate", 0x410540, 0x1B4F00): "cSSScroll opening samples its scale track (1B4F00 -> "
        "1B4860) at a time it counts itself; nothing under it advances a track",
    ("gate", 0x411570, 0x1B4F00): "as 410540, the closing",
    ("gate", 0x5ABF60, 0x4BA080): "4BA080 starts a motion and stores its blend length "
        "(4BA141, x N); the blend advances in the motion advance, every tick",
    ("gate", 0x48BEB0, 0x48BF00): "48BF00 reaches 3E2A90, which starts a screen fade (its "
        "length x N, 3E2ACE); the fade advances in 3E2B60, every tick",
    ("paced", 0x476805, 0x4A0900): "4A0900 calls the camera update 4763F0 (4A0F8F) right "
        "after 481A10 set the transition length +290 = +292 = r13d, zeroed at 4A0942 and "
        "never written again: that pass takes 4767F3's je past the count; the count runs from "
        "the per-tick camera update (4BA500 -> 475C70 -> 4763F0, or 46D5A0's helpers)",
}
# data: the row and a mode-table read beside it were read together
REVIEWED.update({
    ("data", 0x3B0A5D, 0x7A8150): "pl00 3B06F0: the lea of the 7A8150 table at 3B0A1C is for "
        "a later call; the row scales the launch velocity +E10 added to x",
    ("data", 0x47D0A4, 0x7A82D8): "camera 47C9D0: the yaw factor is the 7A82D8 entry minus one, "
        "which mode_constants corrects; the row scales only the turn limit",
    ("data", 0x47D0A9, 0x7A82D8): "camera 47C9D0: the count +398 is the yaw request's duration, not "
        "the table's factor",
    ("data", 0x47E201, 0x7A82D8): "as 47D0A4 (camera mode 47DAB0)",
    ("data", 0x47E206, 0x7A82D8): "as 47D0A9 (camera mode 47DAB0)",
    ("data", 0x46B7A3, 0x7A82D8): "as 47D0A4 (camera mode 46B080)",
    ("data", 0x46B7A8, 0x7A82D8): "as 47D0A9 (camera mode 46B080)",
    ("data", 0x479A1B, 0x7A82C0): "camera 4797A0: the blend is on its own 0.1 (the distance "
        "+200 toward 7A7C0C); the 7A82C0 entry feeds +1FC, which mode_constants corrects",
})
OPEN = {}


def data_fixed():
    """{rva: name} of every byte a family rewrites in .data"""
    out = {}
    src = open(os.path.join(ROOT, "src", "dinput8_proxy.cpp"), encoding="utf-8").read()
    body = re.search(r"kJogParams\[\] = \{(.*?)\n\};", src, re.S).group(1)
    for rva, what in re.findall(r'\{0x([0-9A-F]+), [-0-9.e]+f, (?:-?\d+|JOG_BLEND), "([^"]+)"\}',
                                body):
        for i in range(4):
            out[int(rva, 16) + i] = "run fix: " + what
    charge = int(re.search(r"kChargeFramesRva = 0x([0-9A-F]+)", src).group(1), 16)
    for i in range(4):
        out[charge + i] = "run fix: charge frames"
    mc = open(os.path.join(ROOT, "src", "mode_constants.h"), encoding="utf-8").read()
    for rva in re.findall(r"\{0x([0-9A-F]+), [-0-9.e]+f, [-0-9.e]+f, \d\}", mc):
        for i in range(8):
            out[int(rva, 16) + i] = "mode table %s" % rva
    return out


RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def functions(pe):
    """The .pdata starts that begin a function: a chained entry (UNW_FLAG_CHAININFO,
    a shrink-wrapped stretch of its parent) is not one."""
    import pefile
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    return sorted(set(f.struct.BeginAddress for f in pe.DIRECTORY_ENTRY_EXCEPTION
                      if not (f.unwindinfo is not None and f.unwindinfo.Flags & 4)))


DISP = re.compile(r"\[(r\w+)(?: \+ \w+\*\d+)? \+ (0x[0-9a-f]+)\]")


def fields(op):
    return set(int(d, 16) for r, d in DISP.findall(op) if r not in ("rip", "rsp"))


def main():
    pe, _base, _img, _text = xrefs.load_bin("main.dll")
    insns = [(a - BASE, m, o, s) for a, m, o, s in xrefs.cached_insns("main.dll")]
    idx = {a: k for k, (a, _m, _o, _s) in enumerate(insns)}
    # .pdata has no entry for a leaf without a frame (1B8C20, the length leaves):
    # every direct call's target starts a function too, and so does the first
    # instruction after a ret or jmp and its int3 padding (4117B0, a dispatcher
    # with no frame and no caller, right after 411570)
    starts = set(functions(pe))
    for k, (a, m, o, s) in enumerate(insns):
        if m == "call" and o.startswith("0x"):
            try:
                starts.add(int(o, 16) - BASE)
            except ValueError:
                pass
        elif m in ("ret", "jmp") and k + 1 < len(insns) and insns[k + 1][1] == "int3":
            j = k + 1
            while j < len(insns) and insns[j][1] == "int3":
                j += 1
            if j < len(insns):
                starts.add(insns[j][0])
    starts = sorted(starts)

    def fn_of(a):
        return starts[bisect.bisect_right(starts, a) - 1]

    def fn_end(f):
        k = bisect.bisect_right(starts, f)
        return starts[k] if k < len(starts) else f + 0x1000

    def target(o):
        try:
            return int(o, 16) - BASE
        except ValueError:
            return None

    callees = collections.defaultdict(set)
    for a, m, o, s in insns:
        if m in ("call", "jmp") and o.startswith("0x"):
            t = target(o)
            if t is None:
                continue
            f, g = fn_of(a), fn_of(t)
            if m == "jmp" and g == f:
                continue
            callees[f].add(g)

    def reach(roots, depth):
        seen = {r: 0 for r in roots}
        q = collections.deque(roots)
        while q:
            f = q.popleft()
            if seen[f] < depth:
                for g in callees.get(f, ()):
                    if g not in seen:
                        seen[g] = seen[f] + 1
                        q.append(g)
        return seen

    with contextlib.redirect_stdout(io.StringIO()):
        img = cps.load_image()
        sites, _detours, _loads = cps.all_sites(img)
    # every row the generator wrote with world_anims.h, the flag group's surveyed
    # lengths (mulstore) too, which MANIFEST does not list
    rows = [(r["group"], r["kind"], int(r["site"], 16), r["instruction"]) for r in
            csv.DictReader(open(os.path.join(DOCS, "world_anims.csv"), encoding="utf-8"))]
    if not {s for _g, _k, s, _i in rows} >= {r[2] for r in gwa.MANIFEST}:
        sys.exit("world_anims.csv is older than gen_world_anims.MANIFEST: run the generator")
    paced = [(g, k, s, i) for g, k, s, i in rows if k in PACED_KINDS]

    def paced_root(kind, site, ins):
        """The function the row paces: a gatefn's own, a callgate's callee."""
        if kind in ("gatefn", "gate0"):
            return site
        if kind == "callgate":
            m = re.search(r"call 0x([0-9a-f]+)", ins)
            return fn_of(int(m.group(1), 16)) if m else None
        return fn_of(site)

    def placed_in(kind, site, ins):
        """Where the row's pacing happens: a callgate's at its call, in its caller."""
        return fn_of(site) if kind == "callgate" else paced_root(kind, site, ins)

    found = []  # (check, row site, against, text)

    # 1. spins: back-jumps within a function over a short body with a call and
    # no induction; a linked-list walk (mov r, [r + d]; test r, r) is not one,
    # nor a loop that yields: one whose calls reach the task wait, a pass a tick
    yields = set(reach([TASK_WAIT], 0))
    rev = collections.defaultdict(set)
    for f, gs in callees.items():
        for g in gs:
            rev[g].add(f)
    q = collections.deque([(TASK_WAIT, 0)])
    while q:
        f, d = q.popleft()
        if d < YIELD_DEPTH:
            for g in rev.get(f, ()):
                if g not in yields:
                    yields.add(g)
                    q.append((g, d + 1))
    JCC = re.compile(r"^j(?!mp)")
    roots_spin = collections.defaultdict(list)  # a call the loop's exit depends on -> the loops
    for k, (a, m, o, s) in enumerate(insns):
        if not JCC.match(m) or not o.startswith("0x"):
            continue
        t = target(o)
        if t is None or t >= a or a - t > 0x50 or t not in idx or fn_of(t) != fn_of(a):
            continue
        body = insns[idx[t]:k + 1]
        calls = [b for b in body if b[1] == "call" and b[2].startswith("0x")]
        if not calls or len(body) > 10:
            continue
        if any(b[1] in ("add", "sub", "inc", "dec") and not b[2].startswith("rsp") for b in body):
            continue
        if any(b[1] == "mov" and re.match(r"(\w+), qword ptr \[\1 \+", b[2]) for b in body):
            continue
        if any(fn_of(target(b[2])) in yields for b in calls):
            continue
        for b in calls:  # the exit's test reads a result or memory any of them may change
            roots_spin[fn_of(target(b[2]))].append(a)
    spin_reach = {}
    for f, loops in roots_spin.items():
        for g, d in reach([f], SPIN_DEPTH).items():
            spin_reach.setdefault(g, (loops[0], f, d))
    for g, kind, site, ins in paced:
        r = placed_in(kind, site, ins)
        if r in spin_reach:
            loop, f, d = spin_reach[r]
            found.append(("spin", site, f, "%s %X under the spin at %X (its exit %X, %d calls)"
                          % (kind, site, loop, f, d)))

    # task_waits.h's paced loops
    patched = set(r for r, (fam, _l, _r) in sites.items() if fam == "task_waits.h")
    loop_calls = collections.defaultdict(set)
    for r in csv.DictReader(open(os.path.join(DOCS, "task_waits.csv"), encoding="utf-8")):
        if r["cls"] == "pass" and r["loop"] == "loop" and int(r["site"], 16) in patched:
            for c in r["calls"].split():
                loop_calls[int(c, 16)].add(int(r["site"], 16))
    paced_reach = {}
    for f in loop_calls:
        for g, d in reach([f], PACED_DEPTH).items():
            paced_reach.setdefault(g, []).append((f, d))
    for g, kind, site, ins in paced:
        r = placed_in(kind, site, ins)
        for f, d in paced_reach.get(r, ()):
            found.append(("paced", site, f, "%s %X under %X, called from the paced loop at %s "
                          "(%d calls)" % (kind, site, f, ",".join("%X" % x for x in
                                                                   sorted(loop_calls[f])), d)))

    # 2. doubles
    mm = [rva for rva, (fam, _l, _r) in sites.items() if fam == "mode_multipliers.h"]
    leaves = {fn_of(rva) for rva in mm if fn_end(fn_of(rva)) - fn_of(rva) < LEAF_SIZE}
    lengths = []  # (site, label, fields it stores)
    for rva in mm:
        lengths.append((rva, "mode_multipliers.h", None))
    for g, kind, site, ins in rows:
        if g in ("flag", "mode") and kind not in PACED_KINDS:
            lengths.append((site, "world %s/%s" % (g, kind), None))
    lens = []
    for site, label, _ in lengths:
        k = idx.get(site)
        if k is None:
            continue
        stored = set()
        for a, m, o, s in insns[k:k + 12]:
            if a >= fn_end(fn_of(site)):
                break
            dst = o.split(",")[0].strip()
            if m.startswith("mov") and dst.startswith(("word", "dword", "byte")):
                stored = fields(dst)
                break
        lens.append((site, label, stored or fields(insns[k][2])))
    for g, kind, site, ins in paced:
        if kind not in ("count", "count2", "countlast"):
            continue
        f = fn_of(site)
        for c in callees.get(f, ()):
            if c in leaves:
                found.append(("leaf", site, c, "count %X in %X runs to a length from %X, which "
                              "mode_multipliers.h scales" % (site, f, c)))
        k = idx.get(site)
        own = fields(insns[k][2]) if k is not None else set()
        if k is not None and not own:  # a register count: the field it loaded
            for a, m, o, s in insns[max(0, k - 6):k]:
                if m.startswith("mov") and "ptr" in o.split(",", 1)[-1]:
                    own |= fields(o.split(",", 1)[1])
        for lsite, label, stored in lens:
            if lsite != site and own & stored and abs(lsite - site) < FIELD_SPAN:
                found.append(("field", site, lsite, "count %X on +%s, which %s at %X stores "
                              "as a length" % (site, ",".join("%X" % x for x in sorted(own & stored)),
                                               label, lsite)))
    step_by_fn = collections.defaultdict(list)
    for rva, (fam, _l, _r) in sites.items():
        if fam in STEP_FAMILIES:
            step_by_fn[fn_of(rva)].append((rva, fam))
    for g, kind, site, ins in rows:
        if kind not in PACED_KINDS + ("pre",):
            step_by_fn[fn_of(site)].append((site, "world %s/%s" % (g, kind)))
    for fn, what in CONSUMERS.items():
        step_by_fn[fn].append((fn, what))
    for g, kind, site, ins in paced:
        if kind not in ("gatefn", "gate0", "callgate"):
            continue
        r = paced_root(kind, site, ins)
        if r is None:
            continue
        hits = collections.defaultdict(list)
        for fn, d in reach([r], GATE_DEPTH).items():
            for rva, fam in step_by_fn.get(fn, ()):
                if not (fam.startswith("world") and d == 0):  # its own body: the generator's proof
                    hits[fn].append((rva, fam, d))
        # report by the first function on the way (the layout update, the motion advance...)
        for fn, hs in hits.items():
            first = fn
            par = {r: None}
            q = collections.deque([r])
            while q:
                x = q.popleft()
                for y in callees.get(x, ()):
                    if y not in par:
                        par[y] = x
                        q.append(y)
            path = [fn]
            while par.get(path[-1]) is not None:
                path.append(par[path[-1]])
            first = path[-2] if len(path) > 1 else fn
            found.append(("gate", site, first, "%s %X reaches %s" % (
                kind, site, "; ".join("%X %s in %X (%d calls)" % (rva, fam, fn, d)
                                      for rva, fam, d in hs[:3]))))

    # data: a row beside a read of a constant another family rewrites in .data
    fixed = data_fixed()
    for g, kind, site in ((r[0], r[1], r[2]) for r in gwa.MANIFEST):
        k = idx.get(site)
        if k is None:
            continue
        for a, m, o, s in insns[max(0, k - DATA_SPAN):k + 4]:
            hit = RIP.search(o)
            if not hit:
                continue
            t = a + s + int(hit.group(2), 16) * (1 if hit.group(1) == "+" else -1)
            if t in fixed:
                base = t - next(i for i in range(8) if fixed.get(t - i - 1) != fixed[t])
                found.append(("data", site, base, "%s %s %X beside %X %s %s, which %s rewrites"
                              % (g, kind, site, a, m, o, fixed[t])))

    # verdicts: a finding is keyed by (check, site, the function it was found against)
    problems, seen = [], set()
    for check, site, against, text in found:
        key = (check, site, against)
        if key in seen:
            continue
        seen.add(key)
        tag = '("%s", 0x%X, 0x%X)' % key
        if key in REVIEWED:
            print("reviewed  %s %s" % (tag, text))
        elif key in OPEN:
            print("OPEN      %s %s -- %s" % (tag, text, OPEN[key]))
        else:
            problems.append(text)
            print("PROBLEM   %s %s" % (tag, text))
    stale = [k for k in list(REVIEWED) + list(OPEN) if k not in seen]
    for k in stale:
        problems.append("stale entry %s %X %X: no longer found" % k)
        print("PROBLEM   stale entry %s %X %X" % k)
    print("%d paced rows; %d spin exits, %d paced task loops; %d findings: %d reviewed, %d open, "
          "%d problems" % (len(paced), len(roots_spin), len(loop_calls), len(seen),
                           sum(1 for k in seen if k in REVIEWED), sum(1 for k in seen if k in OPEN),
                           len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
