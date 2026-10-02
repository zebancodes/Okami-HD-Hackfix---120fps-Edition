#!/usr/bin/env python3
"""Find the character action-timer countdowns in main.dll and emit the C table.

The M2 port compensates for 60 fps in two ways: it multiplies per-tick
quantities by the engine time scale (main+0xB6AC38), and it doubles input
windows by shifting them with the 60 fps flag (main+0xB6AC40). The second is
applied at 318 sites and every one of them feeds cPad::ActSet -- no object
state duration is compensated anywhere.

Those durations live in three adjacent fields of the shared character object
and are counted down a tick at a time:

    +0xE3C   the main action timer   (128 decrement, 21 increment sites)
    +0xE76   a second action timer   ( 70)
    +0xE3E   a secondary timer       ( 43)
    +0xE40   a third                 ( 10)

All four are fields of the shared character object: the decrement sites for
+0xE76 alone are spread over em85, em86, em87, em88, em89, utb2 and friends.

Three more are the enemy base class cEm's own, each counted down once a tick
by its shared helpers (one site each; nothing else in the image matches the
shape at these displacements):

    +0x1138  a status's length: 238DF0 starts it (vtable +118) with a
             duration, and when 238D80 counts it to 0 it ends it (+120)
    +0x113A  a second status length, counted down by 238D80 too
    +0x10D0  the window 238820 opens for the hit total +10D2; 238800 counts
             it down and clears both at 0
Counters belonging to the CriMana video/audio middleware (+0x10, +0x20, +0x30)
look identical in shape but are media playback, not game logic, and are not
touched.

Each countdown is the same shape, a decrement followed immediately by a store
back to the field:

    movzx eax, word ptr [rsi+0xE3C]
    test  ax, ax
    je    done
    dec   ax                 <- 3 bytes
    mov   word ptr [rsi+0xE3C], ax   <- 7 bytes

Because the exit test reads the field on the following tick, skipping the
decrement on alternate ticks makes every one of these timers last twice as
many ticks, which is the same real time at 60 fps as at 30. Patching from the
decrement (rather than the store) keeps the register and the field in step,
which matters because 72 of the sites go on to use the register.

Run from anywhere; writes src/action_timers.h next to this tool's repo.

    python tools/find_action_timers.py
"""
import collections
import json
import os
import re
import sys

try:
    import pefile
    import capstone
except ImportError:
    sys.exit("needs pefile and capstone: pip install pefile capstone")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402  auto-detected Steam install (or OKAMI_DIR)

BASE_IMAGE = 0x180000000
FIELDS = ("0xe3c", "0xe3e", "0xe40", "0xe76", "0x1138", "0x113a", "0x10d0")

LOAD = re.compile(r"^(\w+), (?:dword|word|byte) ptr \[(\w+) \+ (0x[0-9a-f]+)\]$")
STORE = re.compile(r"^(?:dword|word|byte) ptr \[(\w+) \+ (0x[0-9a-f]+)\], (\w+)$")

_FAM = {}
for _q, _d, _w, _b in [
    ("rax", "eax", "ax", "al"), ("rbx", "ebx", "bx", "bl"),
    ("rcx", "ecx", "cx", "cl"), ("rdx", "edx", "dx", "dl"),
    ("rsi", "esi", "si", "sil"), ("rdi", "edi", "di", "dil"),
    ("rbp", "ebp", "bp", "bpl"), ("rsp", "esp", "sp", "spl"),
]:
    for _r in (_q, _d, _w, _b):
        _FAM[_r] = _q
for _n in range(8, 16):
    _q = "r%d" % _n
    for _r in (_q, _q + "d", _q + "w", _q + "b"):
        _FAM[_r] = _q


def fam(reg):
    return _FAM.get(reg.strip())


def disassemble(path):
    pe = pefile.PE(path, fast_load=True)
    img = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    start = text.VirtualAddress
    end = start + text.Misc_VirtualSize
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = bytes(img[start:end])
    insns = []
    off = 0
    while off < len(code):
        found = False
        for i in md.disasm(code[off:off + 65536], BASE_IMAGE + start + off):
            insns.append((i.address - BASE_IMAGE, i.mnemonic, i.op_str, i.size))
            off = i.address - BASE_IMAGE - start + i.size
            found = True
        if not found:
            off += 1
    return img, insns


def find_sites(insns):
    sites = []
    for i, (a, m, o, s) in enumerate(insns):
        if m not in ("mov", "movzx", "movsx"):
            continue
        lm = LOAD.match(o)
        if not lm:
            continue
        dst, base, off = lm.groups()
        if off not in FIELDS:
            continue
        # Most of these count down, but the same fields are counted *up* toward
        # a limit in 30-odd handlers. Both are durations in ticks and both need
        # to advance half as often, so take either direction.
        dec = None
        for j in range(i + 1, min(i + 8, len(insns))):
            a2, m2, o2, s2 = insns[j]
            if m2 in ("dec", "inc") and fam(o2) == fam(dst):
                dec = j
            elif m2 in ("sub", "add") and o2.endswith(", 1") and fam(o2.split(",")[0]) == fam(dst):
                dec = j
            elif m2 == "mov":
                sm = STORE.match(o2)
                if (sm and sm.group(2) == off and fam(sm.group(1)) == fam(base)
                        and fam(sm.group(3)) == fam(dst) and dec is not None):
                    if j == dec + 1:            # only the contiguous shape is patchable
                        sites.append((insns[dec][0], insns[dec][3] + s2, off))
                    break
            elif m2 in ("call", "jmp", "ret"):
                break
    return sites


def branch_targets(insns):
    t = set()
    for a, m, o, s in insns:
        if o.startswith("0x") and (m[0] == "j" or m == "call"):
            t.add(int(o, 16) - BASE_IMAGE)
    return t


def main():
    path = os.path.join(GAME, "main.dll")
    img, insns = disassemble(path)
    sites = find_sites(insns)
    targets = branch_targets(insns)

    kept, dropped = [], []
    for rva, ln, off in sorted(sites):
        if any(rva < t < rva + ln for t in targets):
            dropped.append(rva)          # a branch lands inside; not safe to relocate
            continue
        kept.append((rva, ln, bytes(img[rva:rva + ln]), off))

    by = collections.Counter(k[3] for k in kept)
    out = [
        "// Generated by tools/find_action_timers.py -- do not edit by hand.",
        "// See the README section \"Action timers at 60 fps\" for what these are.",
        "//",
        "// Each entry is one `dec <reg>; mov word ptr [obj+field], <reg>` pair in a",
        "// character state handler: the countdown that gives an action its duration.",
        "// Skipping the decrement on alternate ticks makes the action last the same",
        "// real time at 60 fps as at 30.",
        "//",
        "// %d sites: %s" % (len(kept), ", ".join("%s x%d" % (k, v) for k, v in sorted(by.items()))),
        "",
        "struct TimerSite {",
        "    uint32_t rva;      // the dec instruction",
        "    uint8_t len;       // bytes of dec + store to relocate",
        "    uint8_t orig[11];  // exactly what must be there",
        "};",
        "",
        "static const TimerSite kTimerSites[] = {",
    ]
    for rva, ln, raw, off in kept:
        body = ", ".join("0x%02X" % b for b in raw)
        if ln == 10:
            body += ", 0x00"
        out.append("    {0x%06X, %2d, {%s}},  // +%s" % (rva, ln, body, off))
    out.append("};")

    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "action_timers.h")
    with open(os.path.normpath(dest), "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("%d sites written to src/action_timers.h (%s)"
          % (len(kept), ", ".join("%s x%d" % (k, v) for k, v in sorted(by.items()))))
    if dropped:
        print("skipped %d site(s) with a branch landing inside: %s"
              % (len(dropped), ", ".join("%06X" % d for d in dropped)))


if __name__ == "__main__":
    main()
