#!/usr/bin/env python
"""Disassemble RVA range with resolved import/export call targets."""
import os
import re
import sys

import pefile

import xrefs

RIP_RE = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")


def main():
    name = sys.argv[1]
    start = int(sys.argv[2], 0)
    end = int(sys.argv[3], 0)
    pe, base, img, text = xrefs.load_bin(name)
    imp_names = xrefs.import_names(pe)
    exp = {}
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            exp[e.address] = e.name.decode() if e.name else f"ord{e.ordinal}"
    insns = xrefs.cached_insns(name)
    for a, m, o, s in insns:
        if not (start <= (a - base) < end):
            continue
        line = f"  {hex(a)}  {m:<8} {o}"
        extra = None
        mo = RIP_RE.search(o)
        if mo:
            disp = int(mo.group(2), 16)
            tgt = a + s + disp if mo.group(1) == "+" else a + s - disp
            rva = tgt - base
            if rva in exp:
                extra = exp[rva]
            if tgt in imp_names:
                extra = imp_names[tgt]
        elif m in ("call", "jmp") and o.startswith("0x"):
            try:
                rva = int(o, 16) - base
                if rva in exp:
                    extra = exp[rva]
            except ValueError:
                pass
        if extra:
            line += f"   ; {extra}"
        print(line)


if __name__ == "__main__":
    main()
