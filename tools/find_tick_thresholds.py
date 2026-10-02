#!/usr/bin/env python
"""Inventory every constant the engine compares against a per-tick velocity.

    .venv/Scripts/python tools/find_tick_thresholds.py
    .venv/Scripts/python tools/find_tick_thresholds.py --all      # every field
    .venv/Scripts/python tools/find_tick_thresholds.py --header   # emit the table

obj+0xE48 (horizontal speed) and obj+0xE54 (vertical velocity) are displacements
*per tick*. A constant compared against one of them is therefore also per tick,
and means a different real speed at every tick rate. Every such constant in this
build was written for 30 fps, where a full run is about 3.05 per tick; at 120 fps
the same run is 0.76 per tick and the comparison lands on the other side.

That is a different bug shape from an unscaled quantity: it does not make a value
wrong by a factor, it makes a *different branch run*. Three of them in the
player's jump path were found by hand and fixed as FixAirGates -- the running
jump became unreachable above 30 fps, and airborne momentum was drained by a
block that should never have executed. This tool finds the rest.

Why the dataflow matters
------------------------
A first cut at this used "any rodata constant within eight instructions of a
velocity field reference", which over-reports badly: the constant that happens to
be nearby is usually not the one being compared. This resolves both operands of
each compare by tracking, per xmm register, the instruction that last defined it,
resetting at every branch target so a value is never carried across a join it
does not dominate.

Confidence
----------
Offsets are only meaningful if the object really has the player's velocity block
at +0xE48. That layout is shared: the launch-velocity family (23 sites, already
patched) stores to obj+0xE54 across eighteen classes that are not the player. So
+0xE48 and +0xE54 are reported as `high`; the neighbouring words in the same
block are reported as `low` and are excluded unless --all is given.

Nothing here is wired into the patch. The player sites were fixed only after the
log showed their effect; these need the same treatment one family at a time,
using the harness, before anything is enabled.
"""
import argparse
import bisect
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xrefs  # noqa: E402

RIP = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
MEMFLD = re.compile(r"\[(\w+) \+ 0x([0-9a-f]+)\]")
XMM = re.compile(r"^xmm(\d+)$")

# offsets in the shared velocity block, and how much we trust each reading
FIELDS = {
    0xE48: ("hspeed", "high"),
    0xE54: ("vy", "high"),
    0xE4C: ("vel+4", "low"),
    0xE50: ("vel+8", "low"),
    0xE58: ("vel+16", "low"),
    0xE5C: ("vel+20", "low"),
}
RODATA = (0x600000, 0x700000)


def load_functions():
    """Function starts, from the Ghidra export if it is present."""
    path = os.path.expanduser(r"~\tools\main_decompiled.c")
    hdr = re.compile(r"^// ==== main\+([0-9A-Fa-f]+)\s+(\S+) ====")
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = hdr.match(line)
                if m:
                    out.append((int(m.group(1), 16), m.group(2)))
    out.sort()
    return out


def player_states(img, base):
    """The functions the player's state dispatcher can reach.

    main+3AF020 bounds the state byte (pl00+0xE35) at 0x5E and jumps through a
    table of RVAs at main+3AF8A0; each arm is `mov rcx, rbx; call <handler>`.
    A threshold inside one of these is player movement code and the harness can
    exercise it directly, which makes it a far better next target than a site in
    an actor nobody has a test for.
    """
    out = set()
    for i in range(0x5F):
        try:
            off = struct.unpack_from("<I", img, 0x3AF8A0 + i * 4)[0]
        except Exception:
            break
        if not (0x100000 <= off <= 0x700000):
            continue
        if img[off] == 0x48 and img[off + 3] == 0xE8:
            rel = struct.unpack_from("<i", img, off + 4)[0]
            out.add(off + 8 + rel)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include the low-confidence offsets")
    ap.add_argument("--header", action="store_true", help="emit a C table")
    args = ap.parse_args()

    pe, base, img, text = xrefs.load_bin("main.dll")
    insns = xrefs.cached_insns("main.dll")
    funcs = load_functions()
    faddr = [f[0] for f in funcs]

    # every branch target, so a register definition is never carried over a join
    targets = set()
    for a, m, o, s in insns:
        if o.startswith("0x"):
            try:
                targets.add(int(o, 16))
            except ValueError:
                pass

    def ripval(a, s, o):
        mo = RIP.search(o)
        if not mo:
            return None
        d = int(mo.group(2), 16)
        return (a + s + d) if mo.group(1) == "+" else (a + s - d)

    def f32(addr):
        try:
            return struct.unpack_from("<f", img, addr - base)[0]
        except Exception:
            return None

    def classify(a, s, operand):
        """-> ('const', value, rva) | ('field', off) | None"""
        mo = MEMFLD.search(operand)
        # `dword ptr [rip + 0x...]` also matches MEMFLD, with "rip" as the base
        # and the displacement as the offset -- it is a constant load, not a
        # field, and testing the base register is the only way to tell them
        # apart once capstone has prefixed the size.
        if mo and mo.group(1) != "rip":
            off = int(mo.group(2), 16)
            if off in FIELDS:
                return ("field", off)
            return None
        t = ripval(a, s, operand)
        if t is not None and RODATA[0] <= t - base < RODATA[1]:
            v = f32(t)
            if v is not None and abs(v) > 1e-9:
                return ("const", v, t - base)
        return None

    defs = {}
    hits = []
    for a, m, o, s in insns:
        if a in targets:
            defs = {}  # a join: nothing known about any register here
        ops = [x.strip() for x in o.split(",", 1)]

        if m in ("comiss", "ucomiss", "cmpss") and len(ops) == 2:
            left = XMM.match(ops[0])
            resolved = []
            for side, txt in ((left, ops[0]), (XMM.match(ops[1]), ops[1])):
                if side:
                    resolved.append(defs.get(int(side.group(1))))
                else:
                    resolved.append(classify(a, s, txt))
            k, v = resolved
            pair = None
            if k and v:
                if k[0] == "const" and v[0] == "field":
                    pair = (v[1], k[1], k[2])
                elif k[0] == "field" and v[0] == "const":
                    pair = (k[1], v[1], v[2])
            if pair:
                off, val, crva = pair
                name, conf = FIELDS[off]
                if (conf == "high" or args.all) and abs(k[1] if k[0] == "const"
                                                           else v[1]) > 1e-6:
                    j = bisect.bisect_right(faddr, a - base) - 1
                    owner = funcs[j] if j >= 0 else (0, "?")
                    hits.append((a - base, off, name, conf, val, crva, owner))

        # track xmm definitions
        if len(ops) == 2:
            d = XMM.match(ops[0])
            if d:
                r = int(d.group(1))
                if m in ("movss", "movaps", "movapd", "movq", "movd"):
                    src = XMM.match(ops[1])
                    defs[r] = defs.get(int(src.group(1))) if src else classify(a, s, ops[1])
                elif m in ("xorps", "xorpd", "pxor") and ops[0] == ops[1]:
                    defs[r] = ("const", 0.0, 0)
                else:
                    defs[r] = None  # arithmetic: no longer a nameable value

    states = player_states(img, base)
    player = [h for h in hits if 0x3A0000 <= h[6][0] < 0x3D0000]
    other = [h for h in hits if not (0x3A0000 <= h[6][0] < 0x3D0000)]
    fixed = {0x3B4149, 0x3B41E6, 0x3B5466}

    print("per-tick velocity thresholds (dataflow-resolved)\n")
    print("%-10s %-8s %-6s %-12s %-22s %s"
          % ("site", "field", "conf", "constant", "in function", "status"))
    for group, label in ((player, "PLAYER"), (other, "other actors")):
        print("\n---- %s: %d site(s) ----" % (label, len(group)))
        for rva, off, name, conf, val, crva, owner in sorted(group):
            status = "FIXED (FixAirGates)" if rva in fixed else ""
            if not status and owner[0] in states:
                status = "player state handler -- harness can reach this"
            print("main+%-6X %-8s %-6s %-12.6g %-22s %s"
                  % (rva, name, conf, val, owner[1][:22], status))

    print("\n%d total, %d in the player (%d already fixed), %d elsewhere"
          % (len(hits), len(player), len([h for h in player if h[0] in fixed]), len(other)))
    byfn = {}
    for h in other:
        byfn.setdefault(h[6], []).append(h)
    print("%d distinct non-player functions affected" % len(byfn))
    reachable = [h for h in hits if h[6][0] in states and h[0] not in fixed]
    print("%d unfixed site(s) sit in one of the %d player state handlers, so the harness"
          % (len(reachable), len(states)))
    print("can exercise them directly -- those are the ones worth doing next:")
    for h in sorted(reachable):
        print("   main+%-8X %-8s vs %-8.6g in main+%X" % (h[0], h[2], h[4], h[6][0]))

    # ---- the second half of the same family: copies of the accelerate block --
    #
    # The threshold and the acceleration are two halves of one block, and the
    # block is duplicated once per player state that steers in the air. The
    # watchpoint that originally found it could only ever see the copy that was
    # executing, so searching for the *shape* is the only way to find the rest.
    TS = 0xB6AC38
    seq = list(insns)
    copies = []
    for i, (a, m, o, sz) in enumerate(seq):
        if m != "mulss":
            continue
        t = ripval(a, sz, o)
        if t is None or t - base != TS:
            continue
        for j in range(i + 1, min(i + 10, len(seq))):
            b, m2, o2, _ = seq[j]
            if m2 == "movss" and "+ 0xe48]" in o2 and o2.startswith("dword ptr"):
                k = bisect.bisect_right(faddr, a - base) - 1
                copies.append((a - base, b - base, funcs[k] if k >= 0 else (0, "?")))
                break
    done = {0x3B547C, 0x3BE265, 0x3C32F9, 0x3C9BE0}
    print("")
    print("copies of the airborne `v += ts*a` block (a time-scale multiply whose")
    print("result is added into +0xE48): %d found" % len(copies))
    for mul, st, owner in sorted(copies):
        inplayer = 0x3A0000 <= owner[0] < 0x3D0000
        tag = "patched" if mul in done else ("PLAYER, unpatched" if inplayer else "non-player")
        print("   main+%-8X -> store main+%-8X in main+%-8X %s" % (mul, st, owner[0], tag))
    left = [c for c in copies if c[0] not in done]
    print("   %d patched, %d not (all %d remaining are outside the player)"
          % (len(copies) - len(left), len(left),
             len([c for c in left if not (0x3A0000 <= c[2][0] < 0x3D0000)])))

    # ---- the stick drift: the same steering, into +0x10E8, with no time scale --
    #
    # Three more player states steer with the stick while something else moves
    # her (the wall recoil 0x2B after an attack hits a wall, its follow-on
    # 0x2C, and 0x48): v(+0x10E8) = v * k + |stick| * 1.7 / 1024, then
    # position += v. The decay reads the port's per-mode table (7A81B8, so the
    # mode constants already make it k^ts), but the stick term has no time
    # scale at all. At 120 fps the speed settles 15x stock: the "pinball"
    # wall bounce of 2026-09-23. Found by shape: a multiply by the 1/1024
    # stick constant whose result is stored to +0x10E8 within four
    # instructions, with no time-scale multiply between.
    STICK = 0x6AEFD0
    drift = []
    for i, (a, m, o, sz) in enumerate(seq):
        if m != "mulss" or ripval(a, sz, o) is None or ripval(a, sz, o) - base != STICK:
            continue
        timed = False
        for j in range(i + 1, min(i + 5, len(seq))):
            b, m2, o2, sz2 = seq[j]
            if m2 == "mulss" and ripval(b, sz2, o2) is not None and ripval(b, sz2, o2) - base == TS:
                timed = True
            if m2 == "movss" and "+ 0x10e8]" in o2 and o2.startswith("dword ptr"):
                k = bisect.bisect_right(faddr, a - base) - 1
                drift.append((a - base, sz, b - base, timed, funcs[k] if k >= 0 else (0, "?")))
                break
    drift_done = {0x3C2358, 0x3C2913, 0x3C7255}
    print("")
    print("copies of the stick drift (the 1/1024 stick term stored to +0x10E8): %d found"
          % len(drift))
    for mul, sz, st, timed, owner in sorted(drift):
        tag = "has a time scale" if timed else ("patched" if mul in drift_done else "UNPATCHED")
        print("   main+%-8X -> store main+%-8X in main+%-8X %s" % (mul, st, owner[0], tag))
    missing = [d for d in drift if not d[3] and d[0] not in drift_done]
    stale = drift_done - {d[0] for d in drift}
    print("   %d without a time scale, %d of them patched; %d listed but not found"
          % (sum(1 for d in drift if not d[3]), sum(1 for d in drift if d[0] in drift_done),
             len(stale)))
    if args.header:
        print("\n// stick drift, for dinput8_proxy.cpp's kStickDriftSites / kStickDriftOrig")
        for mul, sz, _st, timed, owner in sorted(drift):
            if not timed:
                raw = bytes(img[mul:mul + sz]) if isinstance(img, (bytes, bytearray)) else b""
                print("    {0x%06X, 0x%06X},  // in main+%X; %s" % (
                    mul, mul + sz, owner[0], " ".join("%02X" % x for x in raw)))
    if missing or stale:
        sys.exit(1)

    if args.header:
        print("\n// generated by tools/find_tick_thresholds.py -- NOT wired into the patch")
        for rva, off, name, conf, val, crva, owner in sorted(hits):
            print("    {0x%06X, 0x%04X},  // %s %g in main+%X" % (rva, off, name, val, owner[0]))


if __name__ == "__main__":
    main()
