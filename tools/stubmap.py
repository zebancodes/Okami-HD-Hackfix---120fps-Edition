#!/usr/bin/env python
"""Resolve flower_kernel export stubs (jmp real) to real RVAs."""
import os
import sys

import xrefs


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "flower_kernel.dll"
    pe, base, img, text = xrefs.load_bin(name)
    insns = xrefs.cached_insns(name)
    by_addr = {(a, m, o, s) for a, m, o, s in insns}
    exp = {}
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            exp[e.address] = e.name.decode() if e.name else f"ord{e.ordinal}"
    pats = [p.lower() for p in sys.argv[2:]]
    for rva in sorted(exp):
        nm = exp[rva]
        if pats and not any(p in nm.lower() for p in pats):
            continue
        # find instruction exactly at this rva
        insn = next((i for i in insns if i[0] - base == rva), None)
        if insn and insn[1] == "jmp" and insn[2].startswith("0x"):
            try:
                real = int(insn[2], 16) - base
                print(f"{hex(rva)} {nm}  ->  real rva {hex(real)} va {hex(base+real)}")
            except ValueError:
                print(f"{hex(rva)} {nm}  (jmp {insn[2]})")
        else:
            print(f"{hex(rva)} {nm}  (direct)")


if __name__ == "__main__":
    main()
