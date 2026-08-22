#!/usr/bin/env python
"""Find call sites of imported functions (via IAT jump thunks) in a PE."""
import re
import sys

import xrefs

RIP_RE = xrefs.RIP_RE


def build_thunks(pe, base, insns):
    """Map thunk stub VA -> import name (stub = jmp qword ptr [rip + IAT] or jmp [rip - ...])."""
    imp = xrefs.import_names(pe)
    # IAT slot VA -> import name
    iat_va = {base + rva: name for rva, name in imp.items()}
    thunks = {}
    for a, m, o, s in insns:
        if m != "jmp":
            continue
        mo = RIP_RE.search(o)
        if not mo:
            continue
        disp = int(mo.group(2), 16)
        tgt = a + s + disp if mo.group(1) == "+" else a + s - disp
        if tgt in iat_va:
            thunks[a] = iat_va[tgt]
    return thunks, iat_va


def main():
    name, pat = sys.argv[1], sys.argv[2]
    pe, base, img, text = xrefs.load_bin(name)
    insns = xrefs.cached_insns(name)
    thunks, iat_va = build_thunks(pe, base, insns)
    rx = re.compile(pat)
    targets = set()
    for stub, nm in thunks.items():
        if rx.search(nm):
            targets.add(stub)
    direct_iat = set()
    for rva, nm in xrefs.import_names(pe).items():
        if rx.search(nm):
            direct_iat.add(base + rva)
    print(f"targets: {[hex(t) for t in sorted(targets)]} IAT: {[hex(t) for t in sorted(direct_iat)]}")
    for a, m, o, s in insns:
        if m not in ("call", "jmp"):
            continue
        if o.startswith("0x"):
            try:
                t = int(o, 16)
                if t in targets:
                    nm = thunks[t]
                    print(f"{hex(a)} {m} {o}   ; {nm}")
            except ValueError:
                pass
        else:
            mo = RIP_RE.search(o)
            if mo:
                disp = int(mo.group(2), 16)
                t = a + s + disp if mo.group(1) == "+" else a + s - disp
                if t in direct_iat or t in iat_va:
                    nm = iat_va.get(t, iat_va.get(t))
                    print(f"{hex(a)} {m} {o}   ; {nm}")


if __name__ == "__main__":
    main()
