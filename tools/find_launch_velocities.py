#!/usr/bin/env python3
"""Find vertical launch velocities that the port scaled by the time scale twice.

The shared character update integrates vertical motion in real time already:

    obj+0xE54   -= timeScale * 0.7          gravity   (main+3AB636)
    transform.y += timeScale * obj+0xE54    position  (main+3AB66B)

Both sides carry the time scale, which makes that an ordinary Euler step with
dt = timeScale, so +0xE54 is a velocity that is independent of the frame rate.
Assigning it `timeScale * constant` therefore scales it a second time, and since
apex height goes as the square of the launch velocity, that leaves a quarter of
the height at 60 fps.

This was proved on the player's jump: main+3B4447 seeds the jump accumulator
with timeScale * 5.0, and undoing that one multiply took the measured rise from
17.3 back to 69, matching 30 fps. The same shape appears throughout the
character state handlers -- knockback, launches, pounces and special moves.

A site counts only if the stored value derives from a time scale read and the
chain does NOT read the field itself: `v = ts * k` is the bug, while
`v = v - ts * k` is the correctly scaled gravity step and must be left alone.

    python tools/find_launch_velocities.py
"""
import bisect
import collections
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
TIMESCALE = 0xB6AC38
FIELD = "0xe54"

RIP = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
STORE = re.compile(r"^dword ptr \[(\w+) \+ (0x[0-9a-f]+)\], (xmm\d+)$")


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


def class_map():
    anchors = []
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "rtti_classes.txt")
    if not os.path.exists(path):
        return lambda rva: "?"
    for ln in open(path):
        p = ln.split()
        if len(p) < 4:
            continue
        for m in p[4:]:
            anchors.append((int(m, 16), p[1]))
    anchors.sort()
    aa = [a for a, _ in anchors]

    def owner(rva):
        i = bisect.bisect_right(aa, rva) - 1
        if i < 0:
            return "?"
        a, n = anchors[i]
        return n.replace(".?AV", "").replace("@@", "") if rva - a < 0x8000 else "?"
    return owner


def main():
    img, insns = disassemble(os.path.join(GAME, "main.dll"))
    owner = class_map()
    rows = []
    for i, (a, m, o, s) in enumerate(insns):
        if m != "movss":
            continue
        sm = STORE.match(o)
        if not sm or sm.group(2) != FIELD:
            continue
        live = {sm.group(3)}
        ts = False
        selfread = False
        const = None
        # Walk back past conditional branches: the gravity step loads +0xE54 and
        # then jumps over the subtract, so stopping at the first branch misses
        # the self-read and misclassifies it as an absolute assignment. Only a
        # call or a return really ends the search. Erring toward "self-read"
        # only ever excludes a site, which is the safe direction.
        for j in range(i - 1, max(0, i - 60), -1):
            a2, m2, o2, s2 = insns[j]
            if m2 in ("ret", "call"):
                break
            dst = o2.split(",")[0].strip()
            if dst not in live:
                continue
            t = rip_target(a2, o2, s2)
            if t == TIMESCALE:
                ts = True
            elif t and 0x600000 < t < 0x800000:
                try:
                    const = struct.unpack_from("<f", img, t)[0]
                except Exception:
                    pass
            if FIELD in o2:
                selfread = True          # v = v +/- something: the gravity step
            src = o2.split(",")[1].strip() if "," in o2 else ""
            if m2 == "movss" and not o2.startswith("dword"):
                live.discard(dst)
            if src.startswith("xmm"):
                live.add(src)
        if ts and not selfread:
            rows.append((a, s, bytes(img[a:a + s]), const, owner(a)))

    rows.sort()
    by = collections.Counter(r[4] for r in rows)
    out = [
        "// Generated by tools/find_launch_velocities.py -- do not edit by hand.",
        "// See the README section \"Launch velocities at 60 fps\".",
        "//",
        "// Each entry stores an absolute vertical velocity into obj+0xE54 that the",
        "// port built as `timeScale * constant`. The integrator scales it again, so",
        "// the launch is half strength at 60 fps and reaches a quarter of the height.",
        "// The detour multiplies the value by 1/timeScale just before the store.",
        "//",
        "// %d sites: %s" % (len(rows), ", ".join("%s x%d" % (n, v) for n, v in by.most_common(8))),
        "",
        "struct LaunchSite {",
        "    uint32_t rva;      // the movss that stores the velocity",
        "    uint8_t reg;       // xmm register it stores from",
        "    uint8_t len;       // instruction length",
        "    uint8_t orig[8];   // exactly what must be there",
        "};",
        "",
        "static const LaunchSite kLaunchSites[] = {",
    ]
    for a, s, raw, const, cls in rows:
        reg = (raw[3] >> 3) & 7
        body = ", ".join("0x%02X" % b for b in raw) + ", 0x00" * (8 - len(raw))
        out.append("    {0x%06X, %d, %d, {%s}},  // %s%s"
                   % (a, reg, s, body, cls,
                      ("  v = ts * %g" % const) if const is not None else ""))
    out.append("};")

    dest = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "src", "launch_velocities.h"))
    with open(dest, "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("%d sites written to src/launch_velocities.h" % len(rows))
    for n, v in by.most_common(12):
        print("   %4d  %s" % (v, n))


if __name__ == "__main__":
    main()
