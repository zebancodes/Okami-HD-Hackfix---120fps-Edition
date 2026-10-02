#!/usr/bin/env python3
"""Whole-program p-code census of per-tick state updates in main.dll.

    .venv/Scripts/python tools/pcode_census.py [--out PATH] [--only rva,rva]

Why this exists
---------------
Every generator in this directory searches the disassembly for one *encoding*
of one bug shape, and this project's recurring failure is finding one encoding
and missing the others. This works one level up, on Ghidra's high p-code, where
`dec word [rsi+0xE3C]`, `lea eax,[rcx-1]; mov [..],ax` and `sub; mov` are the
same thing: a STORE to a location whose value was computed from a LOAD of that
same location.

For every function it records
  * "self"  -- a store to location L whose value expression reads L
               (x = x + c, x = x - c, x = x * k, x = wrap(x + c),
               x += (t - x) * k, counter++ ...), with the store and load RVAs,
               the value expression (constants left as [g<rva>] references,
               resolved later) and any engine clock read in its backward slice;
  * "clock" -- every read of the frame counter, time scale, frame divider,
               duration shift, fps byte and mode byte (main+B6AC20..B6AC45),
               which is where the port did, or did not, compensate.

Output is JSON lines; tools/animation_inventory.py turns it into the tables in
docs/animation/. A full run over all 27116 functions takes about 7 minutes and
fails to decompile 6 of them (0ECCA0, 0F4B70, 0FB0D0, 1035A0, 376A40, 3ED1C0).

Setup is the same as tools/ghidra_export.py: Temurin JDK 21, Ghidra 12.1.3,
pyghidra in the repo .venv, and the `okami` project already analysed. Set
JAVA_HOME to the JDK first; pyghidra runs the JVM inside python.exe.
"""
import json
import os
import time

GHIDRA = os.environ.get("GHIDRA_INSTALL_DIR", os.path.expanduser(r"~\tools\ghidra_12.1.3_PUBLIC"))
PROJECT_DIR = os.environ.get("OKAMI_GHIDRA_PROJECT", os.path.expanduser(r"~\tools\ghidra_proj"))
DEFAULT_OUT = os.path.expanduser(r"~\tools\pcode_census.jsonl")
os.environ.setdefault("GHIDRA_INSTALL_DIR", GHIDRA)

import pyghidra  # noqa: E402

pyghidra.start(verbose=False)

from ghidra.app.decompiler import DecompInterface  # noqa: E402
from ghidra.base.project import GhidraProject  # noqa: E402
from ghidra.program.model.pcode import PcodeOp  # noqa: E402
from ghidra.util.task import ConsoleTaskMonitor  # noqa: E402

BASE = 0x180000000
CLOCKS = {
    0xB6AC20: "frame",
    0xB6AC38: "tscale",
    0xB6AC3C: "divider",
    0xB6AC40: "shift",
    0xB6AC44: "fps",
    0xB6AC45: "mode",
}
WRAP = 0x13F2E0

OPN = {}
for n in dir(PcodeOp):
    if not n.isupper() or n == "PCODE_MAX":
        continue
    try:
        v = getattr(PcodeOp, n)
    except Exception:
        continue
    if isinstance(v, int):
        OPN[v] = n

CASTS = {PcodeOp.CAST, PcodeOp.COPY, PcodeOp.INT_ZEXT, PcodeOp.INT_SEXT,
         PcodeOp.SUBPIECE, PcodeOp.FLOAT_FLOAT2FLOAT, PcodeOp.FLOAT_INT2FLOAT,
         PcodeOp.FLOAT_TRUNC}
ARITH = {PcodeOp.INT_ADD, PcodeOp.INT_SUB, PcodeOp.FLOAT_ADD, PcodeOp.FLOAT_SUB,
         PcodeOp.FLOAT_MULT, PcodeOp.INT_MULT, PcodeOp.INT_LEFT, PcodeOp.INT_AND,
         PcodeOp.INT_OR, PcodeOp.INT_XOR, PcodeOp.FLOAT_DIV, PcodeOp.INT_RIGHT,
         PcodeOp.INT_SRIGHT, PcodeOp.INT_DIV, PcodeOp.INT_SDIV, PcodeOp.INT_2COMP,
         PcodeOp.FLOAT_NEG}


def rva_of(addr):
    return addr.getOffset() - BASE


def strip(vn, depth=0):
    while vn is not None and depth < 8:
        d = vn.getDef()
        if d is None or d.getOpcode() not in CASTS:
            return vn
        vn = d.getInput(0)
        depth += 1
    return vn


def key(vn, depth=0):
    """canonical string for an address expression"""
    if vn is None:
        return "?"
    if vn.isConstant():
        return "c%x" % vn.getOffset()
    if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
        return "g%x" % rva_of(vn.getAddress())
    if depth > 6:
        return "v%d" % vn.getUniqueId()
    d = vn.getDef()
    if d is None:
        h = vn.getHigh()
        return "in:%s" % (h.getName() if h is not None else vn.toString())
    oc = d.getOpcode()
    if oc in (PcodeOp.CAST, PcodeOp.COPY):
        return key(d.getInput(0), depth + 1)
    if oc == PcodeOp.MULTIEQUAL or oc == PcodeOp.INDIRECT:
        return "v%d" % vn.getUniqueId()
    return "%s(%s)" % (OPN.get(oc, str(oc)),
                       ",".join(key(d.getInput(i), depth + 1)
                                for i in range(d.getNumInputs())))


def loc_of_read(vn):
    """if vn (after casts) is a memory read, return (key, op) else None"""
    vn = strip(vn)
    if vn is None:
        return None
    if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
        return ("g%x" % rva_of(vn.getAddress()), None)
    d = vn.getDef()
    if d is None:
        return None
    if d.getOpcode() == PcodeOp.LOAD:
        return (key(d.getInput(1)), d)
    return None


def expr(vn, prog, depth=0, seen=None):
    """small printable expression, constants resolved"""
    if vn is None:
        return "?"
    if vn.isConstant():
        return "#%x/%d" % (vn.getOffset(), vn.getSize())
    if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
        r = rva_of(vn.getAddress())
        return "[g%x/%d]" % (r, vn.getSize())
    if depth > 5:
        return "..."
    d = vn.getDef()
    if d is None:
        h = vn.getHigh()
        return "in:%s" % (h.getName() if h is not None else "?")
    oc = d.getOpcode()
    if oc in CASTS:
        return expr(d.getInput(0), prog, depth + 1)
    if oc == PcodeOp.LOAD:
        return "[%s/%d]" % (key(d.getInput(1)), vn.getSize())
    if oc == PcodeOp.MULTIEQUAL:
        # a value merged from several branches -- `x - 1.0` on one path and
        # `x - 0.25` on another is still a per-tick step, so keep every branch
        if depth > 3:
            return "phi"
        return "PHI(%s)" % "|".join(expr(d.getInput(i), prog, depth + 1)
                                    for i in range(d.getNumInputs()))
    if oc == PcodeOp.INDIRECT:
        return expr(d.getInput(0), prog, depth + 1)
    if oc == PcodeOp.CALL:
        tgt = d.getInput(0)
        t = "%x" % rva_of(tgt.getAddress()) if tgt.isAddress() else "?"
        return "call_%s(%s)" % (t, ",".join(expr(d.getInput(i), prog, depth + 1)
                                            for i in range(1, d.getNumInputs())))
    return "%s(%s)" % (OPN.get(oc, str(oc)),
                       ",".join(expr(d.getInput(i), prog, depth + 1)
                                for i in range(d.getNumInputs())))


def slice_globals(vn, depth=0, acc=None, seen=None):
    if acc is None:
        acc = set()
    if seen is None:
        seen = set()
    if vn is None or depth > 12:
        return acc
    if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
        acc.add(rva_of(vn.getAddress()))
        return acc
    d = vn.getDef()
    if d is None:
        return acc
    if d.getOpcode() == PcodeOp.MULTIEQUAL:
        tag = str(d.getSeqnum())
        if tag in seen:
            return acc
        seen.add(tag)
    if d.getOpcode() == PcodeOp.LOAD:
        p = d.getInput(1)
        k = key(p)
        if k.startswith("c"):
            try:
                acc.add(int(k[1:], 16) - BASE)
            except ValueError:
                pass
        return acc
    for i in range(d.getNumInputs()):
        slice_globals(d.getInput(i), depth + 1, acc, seen)
    return acc


def find_self(vn, target, depth=0, seen=None):
    """does the value expression contain a read of `target`? returns op/True

    Walks through MULTIEQUAL (phi) nodes: a store of phi(x - 1.0, x - 0.25)
    is a per-tick step on both paths, and stopping at the phi hid every
    conditionally-stepped timer (the first version missed main+195198)."""
    if vn is None or depth > 10:
        return None
    if seen is None:
        seen = set()
    r = loc_of_read(vn)
    if r is not None and r[0] == target:
        return r[1] or True
    vn2 = strip(vn)
    d = vn2.getDef() if vn2 is not None else None
    if d is None or d.getOpcode() == PcodeOp.LOAD:
        return None
    if d.getOpcode() == PcodeOp.MULTIEQUAL:
        tag = str(d.getSeqnum())
        if tag in seen:
            return None
        seen.add(tag)
    if d.getOpcode() == PcodeOp.INDIRECT:
        return find_self(d.getInput(0), target, depth + 1, seen)
    start = 1 if d.getOpcode() == PcodeOp.CALL else 0
    for i in range(start, d.getNumInputs()):
        x = find_self(d.getInput(i), target, depth + 1, seen)
        if x is not None:
            return x
    return None


def scan_function(f, iface, monitor, prog, out, timeout):
    res = iface.decompileFunction(f, timeout, monitor)
    if res is None or not res.decompileCompleted():
        return False
    hf = res.getHighFunction()
    if hf is None:
        return False
    frva = rva_of(f.getEntryPoint())
    it = hf.getPcodeOps()
    while it.hasNext():
        op = it.next()
        oc = op.getOpcode()
        tgt_key = None
        value = None
        if oc == PcodeOp.STORE:
            tgt_key = key(op.getInput(1))
            value = op.getInput(2)
        else:
            o = op.getOutput()
            if (o is not None and o.isAddress()
                    and o.getAddress().getAddressSpace().getName() == "ram"
                    and oc not in (PcodeOp.INDIRECT, PcodeOp.MULTIEQUAL)
                    and not (0x670000 <= rva_of(o.getAddress()) < 0x792000)
                    and not (oc == PcodeOp.COPY and op.getInput(0).isAddress()
                             and op.getInput(0).getAddress().equals(o.getAddress()))):
                tgt_key = "g%x" % rva_of(o.getAddress())
                value = o
        # clock reads
        for i in (range(op.getNumInputs()) if oc not in (PcodeOp.INDIRECT, PcodeOp.MULTIEQUAL) else ()):
            vn = op.getInput(i)
            if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
                r = rva_of(vn.getAddress())
                if r in CLOCKS:
                    out.write(json.dumps({"t": "clock", "f": frva, "clk": CLOCKS[r],
                                          "at": rva_of(op.getSeqnum().getTarget()),
                                          "op": OPN.get(oc),
                                          "use": expr(op.getOutput(), prog) if op.getOutput() is not None else ""}) + "\n")
        if oc == PcodeOp.LOAD:
            k = key(op.getInput(1))
            if k.startswith("c"):
                try:
                    r = int(k[1:], 16) - BASE
                except ValueError:
                    r = None
                if r in CLOCKS:
                    out.write(json.dumps({"t": "clock", "f": frva, "clk": CLOCKS[r],
                                          "at": rva_of(op.getSeqnum().getTarget()),
                                          "op": "LOAD", "use": ""}) + "\n")
        if tgt_key is None:
            continue
        # value: the computing op (for STORE, def of input 2)
        if oc == PcodeOp.STORE:
            vdef = strip(value).getDef() if strip(value) is not None else None
            vexpr = expr(value, prog)
        else:
            vdef = op
            vexpr = "%s(%s)" % (OPN.get(oc), ",".join(expr(op.getInput(i), prog)
                                                      for i in range(op.getNumInputs())))
        if vdef is None:
            continue
        hit = None
        if oc == PcodeOp.STORE:
            hit = find_self(value, tgt_key)
        else:
            for i in range(op.getNumInputs()):
                hit = find_self(op.getInput(i), tgt_key)
                if hit is not None:
                    break
        if hit is None:
            continue
        gl = sorted(slice_globals(value) if oc == PcodeOp.STORE else
                    set().union(*[slice_globals(op.getInput(i)) for i in range(op.getNumInputs())]))
        clk = [CLOCKS[g] for g in gl if g in CLOCKS]
        load_at = rva_of(hit.getSeqnum().getTarget()) if hit is not True else None
        out.write(json.dumps({
            "t": "self", "f": frva,
            "at": rva_of(op.getSeqnum().getTarget()),
            "ld": load_at,
            "loc": tgt_key,
            "sz": value.getSize() if value is not None else 0,
            "e": vexpr,
            "g": ["%x" % g for g in gl],
            "clk": clk,
        }) + "\n")
    return True


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--only", default="", help="comma list of function RVAs (hex)")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()
    project = GhidraProject.openProject(PROJECT_DIR, "okami", True)
    program = project.openProgram("/", "main.dll", True)
    try:
        monitor = ConsoleTaskMonitor()
        iface = DecompInterface()
        iface.openProgram(program)
        fm = program.getFunctionManager()
        funcs = list(fm.getFunctions(True))
        if args.only:
            want = {int(x, 16) for x in args.only.split(",")}
            funcs = [f for f in funcs if rva_of(f.getEntryPoint()) in want]
        t0 = time.time()
        failed = 0
        with open(args.out, "w", encoding="utf-8") as out:
            for n, f in enumerate(funcs, 1):
                try:
                    if not scan_function(f, iface, monitor, program, out, args.timeout):
                        failed += 1
                        out.write(json.dumps({"t": "fail", "f": rva_of(f.getEntryPoint())}) + "\n")
                except Exception as exc:  # keep going
                    failed += 1
                    out.write(json.dumps({"t": "err", "f": rva_of(f.getEntryPoint()), "x": str(exc)[:200]}) + "\n")
                if n % 1000 == 0:
                    print("%d/%d %.0fs failed=%d" % (n, len(funcs), time.time() - t0, failed), flush=True)
        print("done %d functions, %d failed, %.0fs" % (len(funcs), failed, time.time() - t0))
        iface.dispose()
    finally:
        project.close()


if __name__ == "__main__":
    main()
