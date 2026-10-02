#!/usr/bin/env python3
"""Decompile functions with every C line tagged by the instruction it came from.

    .venv/Scripts/python tools/ghidra_lines.py --out FILE 400370,1B2A50
    .venv/Scripts/python tools/ghidra_lines.py --out FILE --list rvas.txt

Each output line is `RVA | code`, where RVA is the lowest instruction address
that contributed a token to the line, so a site reported by pcode_census.py
(or a patch table entry) can be read in context:

    4003A6 |     uVar1 = FUN_18013f2e0(*(float *)(param_1 + 0x6c) + DAT_180675a30{.rdata=0.3});
    4003BC |     *(undefined4 *)(param_1 + 0x6c) = uVar1;

Every `DAT_18xxxxxxx` in .rdata is annotated with its value (as a float when it
looks like one), which is most of what makes a per-tick step readable.

Same setup as tools/ghidra_export.py; functions are named by RVA, one per
line in --list (anything after the first token is ignored).
"""
import argparse
import os
import re
import struct

GHIDRA = os.environ.get("GHIDRA_INSTALL_DIR", os.path.expanduser(r"~\tools\ghidra_12.1.3_PUBLIC"))
PROJECT_DIR = os.environ.get("OKAMI_GHIDRA_PROJECT", os.path.expanduser(r"~\tools\ghidra_proj"))
os.environ.setdefault("GHIDRA_INSTALL_DIR", GHIDRA)

import pyghidra  # noqa: E402

pyghidra.start(verbose=False)

from ghidra.app.decompiler import DecompInterface  # noqa: E402
from ghidra.app.decompiler.component import DecompilerUtils  # noqa: E402
from ghidra.base.project import GhidraProject  # noqa: E402
from ghidra.util.task import ConsoleTaskMonitor  # noqa: E402

BASE = 0x180000000
DAT = re.compile(r"\b(?:_?DAT|PTR_DAT)_18([0-9a-f]{7})\b")


def annotator(program):
    mem = program.getMemory()
    space = program.getAddressFactory().getDefaultAddressSpace()

    def value(rva):
        addr = space.getAddress(BASE + rva)
        block = mem.getBlock(addr)
        if block is None or not block.isInitialized():
            return None
        name = block.getName()
        try:
            raw = mem.getInt(addr) & 0xFFFFFFFF
        except Exception:
            return None
        f = struct.unpack("<f", struct.pack("<I", raw))[0]
        if raw == 0:
            return "%s=0" % name
        if 1e-6 < abs(f) < 1e7:
            return "%s=%.6g" % (name, f)
        return "%s=0x%x" % (name, raw)

    cache = {}

    def sub(m):
        rva = int(m.group(1), 16)
        if rva not in cache:
            cache[rva] = value(rva)
        v = cache[rva]
        return m.group(0) + ("{%s}" % v if v else "")

    return lambda text: DAT.sub(sub, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--list")
    ap.add_argument("rvas", nargs="?", default="")
    args = ap.parse_args()
    want = [int(x, 16) for x in args.rvas.split(",") if x]
    if args.list:
        want += [int(x.split()[0], 16) for x in open(args.list) if x.strip()]
    project = GhidraProject.openProject(PROJECT_DIR, "okami", True)
    program = project.openProgram("/", "main.dll", True)
    try:
        annotate = annotator(program)
        space = program.getAddressFactory().getDefaultAddressSpace()
        fm = program.getFunctionManager()
        iface = DecompInterface()
        iface.openProgram(program)
        mon = ConsoleTaskMonitor()
        with open(args.out, "w", encoding="utf-8", newline="\n") as out:
            for rva in want:
                f = fm.getFunctionContaining(space.getAddress(BASE + rva))
                if f is None:
                    out.write("// ==== main+%06X: no function\n\n" % rva)
                    continue
                entry = f.getEntryPoint().getOffset() - BASE
                res = iface.decompileFunction(f, 60, mon)
                out.write("// ==== main+%06X  %s ====\n" % (entry, f.getName()))
                if res is None or not res.decompileCompleted():
                    out.write("// DECOMPILATION FAILED\n\n")
                    continue
                for line in DecompilerUtils.toLines(res.getCCodeMarkup()):
                    lo = None
                    toks = []
                    for t in line.getAllTokens():
                        toks.append(t.toString())
                        a = t.getMinAddress()
                        if a is not None:
                            r = a.getOffset() - BASE
                            if lo is None or r < lo:
                                lo = r
                    txt = "  " * line.getIndent() + "".join(toks)
                    if txt.strip():
                        out.write("%s | %s\n" % ("%06X" % lo if lo is not None else "      ",
                                                  annotate(txt)))
                out.write("\n")
        iface.dispose()
    finally:
        project.close()


if __name__ == "__main__":
    main()
