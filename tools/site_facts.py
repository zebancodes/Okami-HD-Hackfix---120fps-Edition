#!/usr/bin/env python3
"""Static facts about every animation candidate.

The tracer session can only classify what the route reaches, and the route is
the first hour of the game. Everything later -- most enemies, later areas,
their effects -- comes back "unseen". This classifies from the code instead,
using Ghidra's high p-code for each candidate's function:

  reads     every other read of the same field in the function, and what each
            read feeds: an ordered compare (against a constant, another field,
            or an expression), an equality test, a switch, an array index or a
            pointer dereference, a division (t / length), or a call argument
  step      the stored value: what it is compared against before the store (a
            limit test), whether it is clamped or wrapped on the way (a phi with
            a constant, a mask, a remainder, the wrap helper at 13F2E0)
  writes    other stores to the field in the function (resets and their values)
  sibling   a constant stored to another field of the same object in the same
            basic block -- `state++; timer = 0` makes `state` a state index
  gate      the nearest enclosing branch: does its condition read the pad
            (main+B6B0A0..B6B140, the key table, the cursor-repeat helpers)?
            `if (press & DOWN) cursor++` is a cursor move, not a clock
  step op   the instruction RVA of the arithmetic that makes the new value, and
            which operand is the step -- what the patch families will rewrite

Then a static class with the evidence that decided it:

  clock     bounded (ordered compare or limit), counts down to 0, counts up to
            one value, checked against several scattered event values (0x50,
            0x5F ...), a bit test on a counter (parity gate), wrapping, ratio
            use, or a smoothing shape (lerp, multiplier) -- a per-tick quantity
            if it runs every tick
  state     array index, switch, compared with 3+ small values (0,1,2,3), or
            `state++; t = 0`
  pointer   the field is dereferenced
  input     an integer step whose nearest branch tests a button *press* (a
            held button is a charge timer, which is a clock)
  float     a float stepped with no bound seen (rotation, drift): likely a
            per-tick quantity, weaker evidence
  unknown   none of the above

Each class carries a confidence (strong / medium / weak). Checked against the
sites the existing tables patch: the census marks a site "covered" when its
instruction lies inside a patched byte range, so the state bytes next to a
patched timer (+0xE36, +0xE37) show up as covered too, and are correctly
called state here.

The raw facts are cached in site_facts.json next to the census, so a rule
change can be re-run in seconds with --classify-only.

Writes docs/animation/static_classification.csv and prints how the classes
line up with the 1478 sites the existing tables already patch (known clocks).

    .venv/Scripts/python tools/site_facts.py [--only rva,rva]
Takes a few minutes (only the ~3200 functions holding candidates).
"""
import argparse
import collections
import csv
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcode_census as pc  # noqa: E402  (starts pyghidra)

from ghidra.app.decompiler import DecompInterface  # noqa: E402
from ghidra.base.project import GhidraProject  # noqa: E402
from ghidra.program.model.pcode import PcodeOp  # noqa: E402
from ghidra.util.task import ConsoleTaskMonitor  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
DOCS = os.path.join(ROOT, "docs", "animation")
CENSUS = pc.DEFAULT_OUT
FACTS_CACHE = os.path.join(os.path.dirname(pc.DEFAULT_OUT), "site_facts.json")

PAD_LO, PAD_HI = 0xB6B0A0, 0xB6B140      # pad held/press/release/sticks
PRESS_LO, PRESS_HI = 0xB6B0D8, 0xB6B0E8  # press (and release) edges within it
KEYS_LO, KEYS_HI = 0xB6AD00, 0xB6AED0    # cKs key table
PAD_HELPERS = {0x1843A0, 0x13F410}       # held-direction cursor repeat
WRAP_FN = pc.WRAP

ORDERED = {PcodeOp.INT_LESS, PcodeOp.INT_SLESS, PcodeOp.INT_LESSEQUAL,
           PcodeOp.INT_SLESSEQUAL, PcodeOp.FLOAT_LESS, PcodeOp.FLOAT_LESSEQUAL}
EQUAL = {PcodeOp.INT_EQUAL, PcodeOp.INT_NOTEQUAL, PcodeOp.FLOAT_EQUAL,
         PcodeOp.FLOAT_NOTEQUAL}
PASS = pc.CASTS | {PcodeOp.INT_ZEXT, PcodeOp.INT_SEXT}
INDEXY = {PcodeOp.INT_MULT, PcodeOp.INT_LEFT, PcodeOp.PTRADD, PcodeOp.INT_ADD,
          PcodeOp.PTRSUB}
STEP_OPS = {PcodeOp.INT_ADD, PcodeOp.INT_SUB, PcodeOp.FLOAT_ADD, PcodeOp.FLOAT_SUB,
            PcodeOp.FLOAT_MULT, PcodeOp.INT_MULT, PcodeOp.INT_LEFT, PcodeOp.INT_RIGHT,
            PcodeOp.INT_SRIGHT}
FIELD = re.compile(r"^(?:INT_ADD|PTRSUB|PTRADD)\((.*),c([0-9a-f]+)\)$")


def split_key(k):
    g = FIELD.match(k)
    if g:
        return g.group(1), int(g.group(2), 16)
    return k, 0


def const_of(vn):
    vn = pc.strip(vn)
    if vn is not None and vn.isConstant():
        return vn.getOffset()
    return None


def other_operand(op, vn_is_input):
    a, b = op.getInput(0), op.getInput(1)
    return b if vn_is_input == 0 else a


def describe_operand(vn):
    c = const_of(vn)
    if c is not None:
        return "#%x" % c
    s = pc.strip(vn)
    d = s.getDef() if s is not None else None
    if d is not None and d.getOpcode() == PcodeOp.LOAD:
        return "field"
    if s is not None and s.isAddress() and s.getAddress().getAddressSpace().getName() == "ram":
        return "global"
    return "expr"


def uses(vn, depth=0, seen=None, masked=False, arith=0):
    """(kind, detail) for every use of a value, looking through casts and a
    few arithmetic steps."""
    if seen is None:
        seen = set()
    if vn is None or depth > 5:
        return
    it = vn.getDescendants()
    while it.hasNext():
        op = it.next()
        tag = str(op.getSeqnum())
        if tag in seen:
            continue
        seen.add(tag)
        oc = op.getOpcode()
        slot = 0 if op.getNumInputs() and op.getInput(0).equals(vn) else 1
        if oc in PASS:
            yield from uses(op.getOutput(), depth + 1, seen, masked, arith)
        elif oc == PcodeOp.INT_AND:
            yield from uses(op.getOutput(), depth + 1, seen, True, arith)
        elif oc in ORDERED:
            yield ("masked-cmp" if masked else "ordered"), describe_operand(other_operand(op, slot))
        elif oc in EQUAL:
            yield ("masked-cmp" if masked else "equal"), describe_operand(other_operand(op, slot))
        elif oc == PcodeOp.BRANCHIND:
            yield "switch", ""
        elif oc in (PcodeOp.LOAD, PcodeOp.STORE) and slot == 1 and op.getInput(1).equals(vn):
            yield ("index" if arith else "deref"), ""
        elif oc in (PcodeOp.FLOAT_DIV, PcodeOp.INT_DIV, PcodeOp.INT_SDIV) and slot == 0:
            yield "ratio", ""
        elif oc in (PcodeOp.INT_REM, PcodeOp.INT_SREM):
            yield "modulo", ""
        elif oc in (PcodeOp.CALL, PcodeOp.CALLIND):
            t = op.getInput(0)
            yield "call", ("%x" % pc.rva_of(t.getAddress())) if t.isAddress() else "ind"
        elif oc in INDEXY and arith < 3:
            yield from uses(op.getOutput(), depth + 1, seen, masked, arith + 1)
        elif oc == PcodeOp.MULTIEQUAL:
            yield from uses(op.getOutput(), depth + 1, seen, masked, arith)
        elif oc == PcodeOp.STORE:
            yield "stored", ""
        else:
            yield "arith", pc.OPN.get(oc, "")


def slice_inputs(vn, depth=0, acc=None, seen=None):
    """globals, loaded constant addresses and call targets in a backward slice"""
    if acc is None:
        acc = set()
    if seen is None:
        seen = set()
    if vn is None or depth > 10:
        return acc
    if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
        acc.add(("g", pc.rva_of(vn.getAddress())))
        return acc
    d = vn.getDef()
    if d is None:
        return acc
    tag = str(d.getSeqnum())
    if tag in seen:
        return acc
    seen.add(tag)
    oc = d.getOpcode()
    if oc == PcodeOp.LOAD:
        k = pc.key(d.getInput(1))
        if k.startswith("c"):
            try:
                acc.add(("g", int(k[1:], 16) - pc.BASE))
            except ValueError:
                pass
        else:
            for g in re.findall(r"g([0-9a-f]+)", k):
                acc.add(("g", int(g, 16)))
            for c in re.findall(r"c(18[0-9a-f]{7})\b", k):
                acc.add(("g", int(c, 16) - pc.BASE))
        return acc
    if oc in (PcodeOp.CALL, PcodeOp.CALLIND):
        t = d.getInput(0)
        if t.isAddress():
            acc.add(("call", pc.rva_of(t.getAddress())))
        return acc
    for i in range(d.getNumInputs()):
        slice_inputs(d.getInput(i), depth + 1, acc, seen)
    return acc


def pad_kind(items):
    """'press' for an edge test (a cursor move), 'held' for a held button or
    stick (a charge timer counts while held), '' for no pad input"""
    held = False
    for kind, v in items:
        if kind == "g" and PRESS_LO <= v < PRESS_HI:
            return "press"
        if kind == "call" and v in PAD_HELPERS:
            return "press"
        if kind == "g" and (PAD_LO <= v < PAD_HI or KEYS_LO <= v < KEYS_HI):
            held = True
    return "held" if held else ""


def block_ops(b):
    out = []
    it = b.getIterator()
    while it.hasNext():
        out.append(it.next())
    return out


def dominators(blocks):
    """immediate dominator index per block index (iterative, small graphs)"""
    n = len(blocks)
    idx = {b.getIndex(): i for i, b in enumerate(blocks)}
    preds = [[idx[b.getIn(j).getIndex()] for j in range(b.getInSize())
              if b.getIn(j).getIndex() in idx] for b in blocks]
    full = set(range(n))
    dom = [full.copy() for _ in range(n)]
    dom[0] = {0}
    changed = True
    rounds = 0
    while changed and rounds < 50:
        changed = False
        rounds += 1
        for i in range(1, n):
            if preds[i]:
                new = set.intersection(*[dom[p] for p in preds[i]]) | {i}
            else:
                new = {i}
            if new != dom[i]:
                dom[i] = new
                changed = True
    idom = [None] * n
    for i in range(1, n):
        strict = dom[i] - {i}
        # the strict dominator dominated by all the others
        for d in strict:
            if all(o in dom[d] for o in strict):
                idom[i] = d
                break
    return idom, idx


def postdominators(blocks, idx):
    """post-dominator set per block index. A site runs regardless of a branch
    when its block post-dominates the branch's block -- the join after
    `if (press) t -= 2;` is not gated by the press, though the press block
    dominates it."""
    n = len(blocks)
    succs = [[idx[b.getOut(j).getIndex()] for j in range(b.getOutSize())
              if b.getOut(j).getIndex() in idx] for b in blocks]
    full = set(range(n))
    pdom = [({i} if not succs[i] else full.copy()) for i in range(n)]
    changed = True
    rounds = 0
    while changed and rounds < 50:
        changed = False
        rounds += 1
        for i in range(n - 1, -1, -1):
            if not succs[i]:
                continue
            new = set.intersection(*[pdom[s] for s in succs[i]]) | {i}
            if new != pdom[i]:
                pdom[i] = new
                changed = True
    return pdom


def analyse_function(f, iface, monitor, wanted, timeout):
    """facts for every wanted (at, loc) in function f"""
    res = iface.decompileFunction(f, timeout, monitor)
    if res is None or not res.decompileCompleted():
        return None
    hf = res.getHighFunction()
    if hf is None:
        return None
    blocks = list(hf.getBasicBlocks())
    idom, bidx = dominators(blocks) if blocks else ([], {})
    pdom = postdominators(blocks, bidx) if blocks else []
    ops = []
    it = hf.getPcodeOps()
    while it.hasNext():
        ops.append(it.next())
    # every access of every key in the function
    loads = collections.defaultdict(list)    # key -> [output varnode]
    stores = collections.defaultdict(list)   # key -> [op]
    for op in ops:
        oc = op.getOpcode()
        if oc == PcodeOp.LOAD:
            loads[pc.key(op.getInput(1))].append(op.getOutput())
        elif oc == PcodeOp.STORE:
            stores[pc.key(op.getInput(1))].append(op)
        if oc not in (PcodeOp.INDIRECT, PcodeOp.MULTIEQUAL):
            for i in range(op.getNumInputs()):
                vn = op.getInput(i)
                if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
                    loads["g%x" % pc.rva_of(vn.getAddress())].append(vn)
            o = op.getOutput()
            if o is not None and o.isAddress() and \
                    o.getAddress().getAddressSpace().getName() == "ram":
                stores["g%x" % pc.rva_of(o.getAddress())].append(op)
    out = {}
    for at, loc in wanted:
        site_ops = [op for op in stores.get(loc, [])
                    if pc.rva_of(op.getSeqnum().getTarget()) == at]
        if not site_ops:
            out[(at, loc)] = {"error": "store not found"}
            continue
        sop = site_ops[0]
        value = sop.getInput(2) if sop.getOpcode() == PcodeOp.STORE else sop.getOutput()
        fx = collections.defaultdict(list)
        # reads of the field
        seen_vn = set()
        for rv in loads.get(loc, []):
            if rv is None or rv.getUniqueId() in seen_vn:
                continue
            seen_vn.add(rv.getUniqueId())
            for kind, detail in uses(rv):
                fx["read:" + kind].append(detail)
        # the new value: tests on it before or after the store
        if sop.getOpcode() == PcodeOp.STORE:
            for kind, detail in uses(value):
                if kind != "stored":
                    fx["new:" + kind].append(detail)
        # how the new value is made
        vdef = pc.strip(value).getDef() if pc.strip(value) is not None else None
        step_at = step_operand = ""
        if vdef is not None:
            oc = vdef.getOpcode()
            if oc == PcodeOp.MULTIEQUAL:
                consts = [const_of(vdef.getInput(i)) for i in range(vdef.getNumInputs())]
                if any(c is not None for c in consts):
                    fx["new:clamp"].append(",".join("#%x" % c for c in consts if c is not None))
                for i in range(vdef.getNumInputs()):
                    d2 = pc.strip(vdef.getInput(i))
                    d2 = d2.getDef() if d2 is not None else None
                    if d2 is not None and d2.getOpcode() in STEP_OPS and not step_at:
                        vdef = d2
                        break
            oc = vdef.getOpcode()
            if oc == PcodeOp.INT_AND and const_of(vdef.getInput(1)) is not None:
                fx["new:wrap"].append("mask #%x" % const_of(vdef.getInput(1)))
            if oc in (PcodeOp.INT_REM, PcodeOp.INT_SREM):
                fx["new:wrap"].append("rem")
            if oc == PcodeOp.CALL and vdef.getInput(0).isAddress() and \
                    pc.rva_of(vdef.getInput(0).getAddress()) == WRAP_FN:
                fx["new:wrap"].append("wrap fn")
            if oc in STEP_OPS:
                step_at = "%X" % pc.rva_of(vdef.getSeqnum().getTarget())
                roles = []
                for i in range(vdef.getNumInputs()):
                    r = pc.loc_of_read(vdef.getInput(i))
                    if r is not None and r[0] == loc:
                        roles.append("self")
                    else:
                        c = const_of(vdef.getInput(i))
                        roles.append("#%x" % c if c is not None else describe_operand(vdef.getInput(i)))
                step_operand = "%s(%s)" % (pc.OPN.get(oc, ""), ",".join(roles))
        # other writes of the field
        for wop in stores.get(loc, []):
            if wop is sop or wop.equals(sop):
                continue
            wv = wop.getInput(2) if wop.getOpcode() == PcodeOp.STORE else wop.getInput(0)
            c = const_of(wv)
            fx["write"].append("#%x" % c if c is not None else "expr")
        # a constant stored to a sibling field in the same block
        base, off = split_key(loc)
        blk = sop.getParent()
        for bop in block_ops(blk):
            if bop.getOpcode() != PcodeOp.STORE or bop.equals(sop):
                continue
            k = pc.key(bop.getInput(1))
            b2, o2 = split_key(k)
            if b2 == base and o2 != off and const_of(bop.getInput(2)) is not None:
                fx["sibling"].append("+%x=#%x" % (o2, const_of(bop.getInput(2))))
        # the nearest branch the site is control dependent on: a dominating
        # conditional branch that the site's block does not post-dominate
        site_bi = bidx.get(blk.getIndex())
        bi = site_bi
        steps = 0
        while bi is not None and steps < 16:
            bi = idom[bi]
            steps += 1
            if bi is None:
                break
            if site_bi in pdom[bi]:
                continue  # the site runs whichever way this one goes
            bops = block_ops(blocks[bi])
            if bops and bops[-1].getOpcode() == PcodeOp.CBRANCH:
                cond = slice_inputs(bops[-1].getInput(1))
                fx["gate"].append(pad_kind(cond) or "other")
                break
        out[(at, loc)] = {"facts": fx, "step_at": step_at, "step_op": step_operand}
    return out


def int_direction(step_op, size):
    """+1 / -1 for an integer counter step on `self`, else 0"""
    g = re.match(r"^(INT_ADD|INT_SUB)\((self,#([0-9a-f]+)|#([0-9a-f]+),self)\)$", step_op or "")
    if not g:
        return 0
    c = int(g.group(3) or g.group(4), 16)
    bits = 8 * (int(size) if str(size).isdigit() else 4)
    neg = c >> (bits - 1) & 1 if bits else 0
    if g.group(1) == "INT_SUB":
        return -1 if c and not neg else 1
    return -1 if neg else (1 if c else 0)


INTEGER_SHAPES = ("counter", "int-step", "int-expr")


def classify(fx, shape, size):
    """(class, confidence, reason)"""
    if "error" in fx:
        return "unknown", "", fx["error"]
    f = fx["facts"]
    ordered = f.get("read:ordered", []) + f.get("new:ordered", [])
    equal = f.get("read:equal", []) + f.get("new:equal", [])
    eq_consts = sorted({e for e in equal if e.startswith("#")})
    masked = f.get("read:masked-cmp", []) + f.get("new:masked-cmp", [])
    integer = shape in INTEGER_SHAPES
    direction = int_direction(fx.get("step_op", ""), size)
    if f.get("read:deref"):
        return "pointer", "strong", "dereferenced"
    if f.get("read:index"):
        return "state", "strong", "array index"
    if f.get("read:switch"):
        return "state", "strong", "switch"
    if integer and len(eq_consts) >= 3:
        vals = sorted(int(e[1:], 16) for e in eq_consts)
        # a state index is set or stepped forward; a field counted *down* past
        # 15, 8 and 0 is a timer with event points (3B8283)
        if vals[-1] <= 0x10 and direction >= 0:
            return "state", "strong", "compared with %d small values (%s)" % (
                len(vals), ",".join(eq_consts[:5]))
        # a timer checked against the frames its events fire on: 0x50, 0x5F ...
        return "clock", "medium", "compared with %d event values (%s)" % (
            len(vals), ",".join(eq_consts[:5]))
    if integer and direction > 0 and f.get("sibling") and \
            any(s.endswith("=#0") for s in f["sibling"]):
        return "state", "medium", "stepped with a sibling reset (%s)" % f["sibling"][0]
    if integer and f.get("gate") == ["press"]:
        return "input", "medium", "nearest branch tests a button press"
    if ordered:
        return "clock", "strong", "ordered compare (%s)" % ",".join(sorted(set(ordered))[:4])
    if integer and direction < 0 and eq_consts == ["#0"]:
        return "clock", "strong", "counts down to 0"
    if integer and direction > 0 and len(eq_consts) == 1 and eq_consts != ["#0"]:
        return "clock", "strong", "counts up to %s" % eq_consts[0]
    if integer and masked:
        return "clock", "medium", "bit test on a counter (parity/phase gate)"
    if f.get("new:wrap") or f.get("read:modulo"):
        return "clock", "strong", "wraps (%s)" % ",".join((f.get("new:wrap") or ["modulo"])[:2])
    if f.get("read:ratio"):
        return "clock", "strong", "used as a ratio (t / length)"
    if shape in ("lerp", "multiplier"):
        return "clock", "strong", "smoothing shape (%s)" % shape
    if shape == "phase-wrap":
        return "clock", "strong", "phase wrap"
    if f.get("new:clamp"):
        return "clock", "medium", "clamped (%s)" % f["new:clamp"][0]
    if integer and equal:
        return "clock", "weak", "counter compared with %s" % ",".join(sorted(set(equal))[:3])
    if shape in ("float-step", "float-expr"):
        return "float", "weak", "float stepped with no bound seen"
    return "unknown", "", ("no read of the field in its function" if not any(
        k.startswith("read:") for k in f) else "reads feed only arithmetic/calls")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--classify-only", action="store_true",
                    help="reuse the facts cache instead of running Ghidra")
    args = ap.parse_args()
    if args.classify_only:
        results = {int(k, 16): v for k, v in json.load(open(FACTS_CACHE)).items()}
        return write_outputs(results)

    sites = [r for r in csv.DictReader(open(os.path.join(DOCS, "sites.csv"), encoding="utf-8"))
             if r["subsystem"] != "library"]
    by_fn = collections.defaultdict(list)
    census = collections.defaultdict(list)
    for ln in open(CENSUS, encoding="utf-8"):
        d = json.loads(ln)
        if d.get("t") == "self":
            census[(d["f"], d["at"])].append(d["loc"])
    for r in sites:
        f, at = int(r["function"], 16), int(r["site"], 16)
        for loc in census.get((f, at), [])[:1]:
            by_fn[f].append((at, loc))
    if args.only:
        keep = {int(x, 16) for x in args.only.split(",")}
        by_fn = {f: v for f, v in by_fn.items() if f in keep}

    project = GhidraProject.openProject(pc.PROJECT_DIR, "okami", True)
    program = project.openProgram("/", "main.dll", True)
    results = {}
    failed = []
    try:
        monitor = ConsoleTaskMonitor()
        iface = DecompInterface()
        iface.openProgram(program)
        fm = program.getFunctionManager()
        af = program.getAddressFactory().getDefaultAddressSpace()
        t0 = time.time()
        for n, (frva, wanted) in enumerate(sorted(by_fn.items()), 1):
            f = fm.getFunctionAt(af.getAddress(pc.BASE + frva))
            r = None
            if f is not None:
                try:
                    r = analyse_function(f, iface, monitor, wanted, args.timeout)
                except Exception as exc:  # keep going
                    print("  %X: %s" % (frva, str(exc)[:120]))
            if r is None:
                failed.append(frva)
                continue
            for (at, loc), v in r.items():
                results[at] = v
            if n % 250 == 0:
                print("%d/%d functions, %.0f s" % (n, len(by_fn), time.time() - t0), flush=True)
        iface.dispose()
    finally:
        project.close()
    print("functions analysed %d, failed %d %s" % (len(by_fn) - len(failed), len(failed),
                                                   " ".join("%X" % x for x in failed[:8])))
    with open(FACTS_CACHE, "w", encoding="utf-8") as f:
        json.dump({"%X" % k: {"facts": {a: list(b) for a, b in v.get("facts", {}).items()},
                              "step_at": v.get("step_at", ""), "step_op": v.get("step_op", ""),
                              **({"error": v["error"]} if "error" in v else {})}
                   for k, v in results.items()}, f)
    write_outputs(results)


def write_outputs(results):
    sites = [r for r in csv.DictReader(open(os.path.join(DOCS, "sites.csv"), encoding="utf-8"))
             if r["subsystem"] != "library"]
    rows = []
    classes = collections.Counter()
    vs_covered = collections.defaultdict(collections.Counter)
    for r in sites:
        at = int(r["site"], 16)
        fx = results.get(at)
        if fx is None:
            cls, conf, why = "unknown", "", "function not analysed"
            facts, step_at, step_op = {}, "", ""
        else:
            cls, conf, why = classify(fx, r["shape"], r["size"])
            facts = fx.get("facts", {})
            step_at, step_op = fx.get("step_at", ""), fx.get("step_op", "")
        classes[cls] += 1
        if r["covered_by"]:
            vs_covered[r["covered_by"]][cls] += 1
        rows.append({
            "site": r["site"], "function": r["function"], "subsystem": r["subsystem"],
            "shape": r["shape"], "size": r["size"], "static_class": cls, "confidence": conf,
            "reason": why,
            "step_at": step_at, "step_op": step_op,
            "facts": "; ".join("%s=%s" % (k, ",".join(sorted(set(v)))[:60])
                               for k, v in sorted(facts.items())),
            "covered_by": r["covered_by"],
        })
    with open(os.path.join(DOCS, "static_classification.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("static classes: %s" % ", ".join("%s %d" % kv for kv in classes.most_common()))
    print("\nagainst sites the existing tables patch (known per-tick quantities):")
    for fam, c in sorted(vs_covered.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(c.values())
        print("  %-24s %4d  %s" % (fam, tot, ", ".join("%s %d" % kv for kv in c.most_common())))
    print("\nwrote docs/animation/static_classification.csv")


if __name__ == "__main__":
    main()
