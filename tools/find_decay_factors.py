#!/usr/bin/env python3
"""Find per-tick exponential decay factors in main.dll and emit the C table.

A great deal of the game's smoothing is a per-tick multiply:

    movss xmm0, dword ptr [rsi+0x...]
    mulss xmm0, dword ptr [rip+...]      ; = 0.97
    movss dword ptr [rsi+0x...], xmm0

Applied twice as often at 60 fps that decays twice as fast in real time, so
velocities bleed off, camera smoothing snaps and springs settle early. Unlike a
linear step, the correct conversion is not k/2 but

    k' = k ** timeScale

which is exactly what the engine's own per-mode table at main+0x7A81B8 does: it
stores 0.86 for 30 fps and 0.9274 for 60, and 0.9274 = sqrt(0.86). The port
built that table for one pair of constants and left every other decay alone.

Only factors in [MIN_K, 1) are taken. A multiply that close to 1 is meaningless
unless it is applied repeatedly, which makes it a safe signature for per-tick
decay; the aggressive factors (0.5, 0.2, 0.1) are usually a one-shot "halve the
velocity on impact" and are left alone.

Like the phase steps, this needs no code injection -- the instruction is the
8-byte rip-relative form, so only the 4-byte displacement is rewritten to point
at a private copy of the factor that the patch keeps raised to the time scale.

    python tools/find_decay_factors.py
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
MIN_K = 0.8
# Hand-read multiplies whose store is further than the scan's 8 instructions
# (each read: the field damps once a tick, nothing else reads the product):
# the store may be up to HAND_WINDOW instructions on, still with no call or
# jump between. A wider window for every site would also take sites nobody
# has read (46EE3F +244; and at 12, five +C0 scales). 3AAE2C was since
# read as pl00's per-update lock-on fade and is opted in narrowly.
HAND = {
    0x2981DD: "em52 action 6 (2981B0): its flight speed +1278 *= 0.97 a tick",
    0x2984CD: "em52 action 5 (2984A0): the same",
    0x5D249E: "em86 (5D2050): +544C *= 0.5 a tick while its countdown +5424 runs (15 ticks)",
    0x3AAE2C: "pl00 update (3A9630): +1140 lock-on weight *= 0.97 each tick after a change resets it to 1",
    0x3BBE4D: "pl00 collision helper (3BBC90): sustained contact damps +E48 by 0.7 each update (30 of 30 traced ticks)",
    # 2026-10-02, the near sites: pl00's movement states damp their speed +E48
    # (in a stock tick's units: the accel is the port's x timeScale, the drag
    # the mode-table pair mode_constants.h rewrites) every tick a flag holds
    0x3C48E7: "pl00 3C43C0: +E48 *= 0.6 each tick while +E58 bit 14 is set",
    0x3C50C5: "pl00 3C4D90: +E48 *= 0.6 each tick while +E58 bit 14 is set",
    0x3C9D1F: "pl00 3C9940: +E48 *= 0.6 each tick while +E58 bit 14 is set",
    0x3C5454: "pl00 3C5350: +E48 *= 0.5 each tick while the count +11E6 is not 0",
    0x46EE3F: "camera 46E890: +244 *= 0.8 each tick beside +240's (46EE7B, the scan's own); the "
              "store is 7 instructions on",
}
# These pendulum decays are inside complete, coupled physics updates. Their
# world gate executes the original forces/damping/integration once a stock
# tick, so applying an Nth-root factor inside it would damp too slowly.
STOCK_GATED = {0x55DE71: 0x55D940, 0x55E39E: 0x55E070, 0x55E859: 0x55E520,
               0x22DB0E: 0x22DAD0,
               # ut33's wobble +E14 *= 0.98 (find_phase_steps.STOCK_GATED has its step)
               0x57E3A1: 0x57E020}
HAND_WINDOW = 10
RDATA_LO, RDATA_HI = 0x600000, 0x800000

RIP = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
LOAD = re.compile(r"^(xmm\d+), dword ptr \[(\w+) \+ (0x[0-9a-f]+)\]$")
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
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "rtti_classes.txt")
    if not os.path.exists(path):
        return lambda rva: "?"
    anchors = []
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
        lm = LOAD.match(o)
        if not lm:
            continue
        reg, base, off = lm.groups()
        if base in ("rsp", "rbp", "esp", "ebp"):
            continue          # a stack local, not per-tick object state
        k = kat = kconst = None
        scaled = False
        for j in range(i + 1, min(i + HAND_WINDOW, len(insns))):
            if j >= i + 8 and kat not in HAND:
                break
            a2, m2, o2, s2 = insns[j]
            if m2 == "mulss" and o2.startswith(reg + ",") and s2 == 8:
                t = rip_target(a2, o2, s2)
                if t == TIMESCALE:
                    scaled = True
                elif t and RDATA_LO < t < RDATA_HI:
                    try:
                        v = struct.unpack_from("<f", img, t)[0]
                    except Exception:
                        v = None
                    # a hand-read site may have any factor in (0, 1)
                    if v is not None and (MIN_K <= v < 1.0 or (a2 in HAND and 0 < v < 1.0)):
                        k, kat, kconst = v, a2, t
            elif m2 == "movss":
                sm = STORE.match(o2)
                if (sm and sm.group(2) == off and sm.group(3) == reg
                        and sm.group(1) == base
                        and k is not None and not scaled):
                    rows.append((kat, kconst, k, off, owner(kat), bytes(img[kat:kat + 8])))
                    break
            elif m2 in ("call", "jmp", "ret"):
                break

    # Fail closed if a cadence correction is removed or the original decay
    # is no longer found: this cannot silently drop a runtime correction.
    import gen_world_anims
    gates = {r[2] for r in gen_world_anims.MANIFEST if r[1] == "gatefn"}
    for at, function in STOCK_GATED.items():
        if function not in gates or not any(r[0] == at for r in rows):
            sys.exit("stock-gated decay %X requires gatefn %X and its original decay" %
                     (at, function))
    rows = [r for r in rows if r[0] not in STOCK_GATED]

    missing = sorted(set(HAND) - {r[0] for r in rows})
    if missing:
        sys.exit("hand-read decay sites not found: %s; nothing written"
                 % ", ".join("%X" % a for a in missing))
    rows.sort()
    seen = set()
    uniq = []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        uniq.append(r)

    consts = collections.Counter(r[1] for r in uniq)
    out = [
        "// Generated by tools/find_decay_factors.py -- do not edit by hand.",
        "// See the README section \"Per-tick decay at 60 fps\".",
        "//",
        "// Each entry is one 8-byte `mulss xmm, dword ptr [rip+K]` that damps a float",
        "// field once per tick. The correct 60 fps factor is K ** timeScale, not K/2,",
        "// which is what the engine's own per-mode table does (0.9274 = sqrt(0.86)).",
        "// Only the 4-byte displacement is rewritten, to point at a private copy.",
        "//",
        "// %d instructions over %d distinct factors." % (len(uniq), len(consts)),
        "",
        "struct DecaySite {",
        "    uint32_t rva;       // the mulss instruction",
        "    uint32_t constRva;  // the .rdata float it reads",
        "    uint8_t orig[8];    // exactly what must be there",
        "};",
        "",
        "static const DecaySite kDecaySites[] = {",
    ]
    for rva, const, k, off, cls, raw in uniq:
        body = ", ".join("0x%02X" % b for b in raw)
        out.append("    {0x%06X, 0x%06X, {%s}},  // *= %g  %s +%s"
                   % (rva, const, body, k, cls, off))
    out.append("};")

    dest = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "src", "decay_factors.h"))
    with open(dest, "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("%d instructions over %d factors written to src/decay_factors.h"
          % (len(uniq), len(consts)))
    print("most common: %s"
          % ", ".join("%g x%d" % (k, v)
                      for k, v in collections.Counter(round(r[2], 4) for r in uniq).most_common(8)))


if __name__ == "__main__":
    main()
