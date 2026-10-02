#!/usr/bin/env python3
"""Find everything the engine selects from the MODE BYTE instead of the time
scale, and emit the C table.

main+0xB6AC45 is 2 in the 30 fps configuration and 1 in the 60 fps one. The
patch's 120 fps mode leaves it at 1, because that is the branch that runs the
fast configuration at all -- so every site that reads the mode byte and picks a
hard-coded 60 fps value keeps handing out the 60 fps value at 120 fps.

There is far more of this than the frame config itself. The port ships a
complete pre-computed damping table at main+0x7A8150: pairs of
`{k**0.5, k}` for k = 0.99, 0.98, ... 0.05, and the matching growth factors
1.01 ... 1.9, indexed by `(mode - 1) * 4`. That is how the port did per-tick
damping properly, and it is the same square root the patch derives for its own
decay factors -- only here the engine did it for itself, for every constant it
uses, and then only for two frame rates.

At 120 fps every one of those lookups returns the 60 fps root, so everything
damped through the table decays at half the rate it should against the wall
clock. The visible result is Amaterasu sliding: her motion advance is one of
the sites that picks a hard-coded 0.5, so the world moves at the full 120 fps
rate while her animation advances as though the game were still at 60.

Two shapes are emitted:

  tables  -- `{sqrt(k), k}` pairs. The mode-1 slot is rewritten to `k ** ts`,
             which is `k**0.5` at 60 fps (what the engine already shipped) and
             `k**0.25` at 120.
  selects -- `cmp [mode], 1` followed by a choice between 1.0 and 0.5. The 0.5
             is a shared .rdata constant that hundreds of unrelated
             instructions read, so the instruction is retargeted at a private
             copy the patch holds at the live time scale rather than the
             constant being rewritten.

    python tools/find_mode_constants.py
"""
import collections
import math
import os
import re
import struct
import sys

try:
    import pefile
    import capstone
except ImportError:
    sys.exit("needs pefile and capstone: pip install pefile capstone")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402

BASE_IMAGE = 0x180000000
MODE_BYTE = 0xB6AC45
TABLE_LO, TABLE_HI = 0x7A8100, 0x7A8400   # the damping table lives in here
RD_LO, RD_HI = 0x600000, 0x7B0000
HALF = 0x671E08                            # the shared 0.5
RIP = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
TBLIDX = re.compile(r"^(xmm\d+), dword ptr \[(\w+) \+ (\w+)\*4\]$")


def disassemble(path):
    pe = pefile.PE(path, fast_load=True)
    img = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    start, end = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = bytes(img[start:end])
    insns, off = [], 0
    while off < len(code):
        found = False
        for i in md.disasm(code[off:off + 65536], BASE_IMAGE + start + off):
            insns.append((i.address - BASE_IMAGE, i.mnemonic, i.op_str, i.size))
            off = i.address - BASE_IMAGE - start + i.size
            found = True
        if not found:
            off += 1
    return img, insns


def rip_target(a, op, size):
    m = RIP.search(op)
    if not m:
        return None
    d = int(m.group(2), 16)
    return a + size + (d if m.group(1) == "+" else -d)


def main():
    img, insns = disassemble(os.path.join(GAME, "main.dll"))

    # ---- which table bases are actually indexed off the mode byte? ---------
    used = set()
    for i, (a, m, o, s) in enumerate(insns):
        if rip_target(a, o, s) != MODE_BYTE:
            continue
        base = None
        for j in range(i, min(i + 14, len(insns))):
            a2, m2, o2, s2 = insns[j]
            if m2 == "lea":
                t = rip_target(a2, o2, s2)
                if t and TABLE_LO <= t < TABLE_HI:
                    base = t
            elif base is not None and m2 in ("movss", "mov") and TBLIDX.match(o2):
                used.add(base)
                break
            elif m2 in ("call", "ret"):
                break

    # ---- every {sqrt(k), k} pair in the table region -----------------------
    tables = []
    for rva in range(TABLE_LO, TABLE_HI, 4):
        try:
            v60 = struct.unpack_from("<f", img, rva)[0]
            v30 = struct.unpack_from("<f", img, rva + 4)[0]
        except Exception:
            break
        if not (0.01 < v60 < 3.0 and 0.01 < v30 < 3.0):
            continue
        if abs(v30 - 1.0) < 1e-9:
            continue
        if abs(v60 - math.sqrt(v30)) > max(1e-4, abs(v30) * 1e-4):
            continue
        tables.append((rva, v60, v30, rva in used))
    # the pairs sit on an 8-byte stride; drop anything that overlaps its
    # predecessor, which is a coincidence rather than a table entry
    pruned, last = [], -8
    for rva, v60, v30, direct in tables:
        if rva - last < 8:
            continue
        pruned.append((rva, v60, v30, direct))
        last = rva
    tables = pruned

    # ---- cmp [mode], 1 ... movss xmm, [0.5] -------------------------------
    selects = []
    for i, (a, m, o, s) in enumerate(insns):
        if m != "cmp" or rip_target(a, o, s) != MODE_BYTE:
            continue
        for j in range(i + 1, min(i + 10, len(insns))):
            a2, m2, o2, s2 = insns[j]
            if m2 == "movss" and s2 == 8 and rip_target(a2, o2, s2) == HALF:
                selects.append((a2, bytes(img[a2:a2 + s2])))
            if m2 in ("call", "ret"):
                break

    out = [
        "// Generated by tools/find_mode_constants.py -- do not edit by hand.",
        "// See the README section \"120 fps and the mode byte\".",
        "//",
        "// The engine picks its frame-rate-dependent constants by testing the mode",
        "// byte (main+0xB6AC45), which is 1 for the fast configuration whether that is",
        "// 60 fps or 120. Every one of these therefore returns the 60 fps value at",
        "// 120 fps, and everything damped or advanced through them runs at half the",
        "// rate it should.",
        "//",
        "// %d damping table entries and %d selected constants." % (len(tables), len(selects)),
        "",
        "// A pre-computed {k**0.5, k} pair indexed by (mode - 1). The mode-1 slot is",
        "// rewritten to k**timeScale, which reproduces the shipped value at 60 fps.",
        "struct ModeTable {",
        "    uint32_t rva;     // the mode-1 slot",
        "    float fast;       // what the engine ships there (k**0.5)",
        "    float stock;      // the mode-2 slot, k itself",
        "    uint8_t indexed;  // 1 if a mode-byte lookup reaches this entry directly",
        "};",
        "",
        "static const ModeTable kModeTables[] = {",
    ]
    for rva, v60, v30, direct in tables:
        out.append("    {0x%06X, %.9gf, %.9gf, %d},%s"
                   % (rva, v60, v30, 1 if direct else 0,
                      "   // read by a mode-byte lookup" if direct else ""))
    out += [
        "};",
        "",
        "// `movss xmm, dword ptr [rip+0.5]` on the 60 fps side of a mode-byte test.",
        "// 0.5 is shared, so the instruction is retargeted rather than the constant",
        "// rewritten.",
        "struct ModeSelect {",
        "    uint32_t rva;      // the movss",
        "    uint8_t orig[8];   // exactly what must be there",
        "};",
        "",
        "static const ModeSelect kModeSelects[] = {",
    ]
    for rva, raw in selects:
        out.append("    {0x%06X, {%s}},"
                   % (rva, ", ".join("0x%02X" % b for b in raw)))
    out.append("};")

    dest = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "src", "mode_constants.h"))
    with open(dest, "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("%d table entries (%d reached by a mode lookup) and %d selects -> "
          "src/mode_constants.h"
          % (len(tables), sum(1 for t in tables if t[3]), len(selects)))
    print("table range: %06X..%06X" % (tables[0][0], tables[-1][0]) if tables else "none")
    for rva, raw in selects:
        print("  select at %06X" % rva)


if __name__ == "__main__":
    main()
