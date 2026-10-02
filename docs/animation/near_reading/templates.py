#!/usr/bin/env python3
"""Propose verdicts for near sites that match a template read by hand on
2026-10-02 (the animals' state functions repeat a few shapes). Prints spec
lines per template for the sites still without a verdict; nothing is
written. Each template was read in several classes before it was written
down here; a proposal is still read before it goes into a spec.

    .venv/Scripts/python docs/animation/near_reading/templates.py
"""
import collections
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import xrefs  # noqa: E402
import gen_integer_skips as gis  # noqa: E402

BASE = 0x180000000
PLAY_MOTION, TURN_BLEND, WRAP, RAND169 = 0x4BA080, 0x2DA510, 0x13F2E0, 0x169620


def remaining():
    out = subprocess.run([sys.executable, os.path.join(HERE, "remaining.py"), "100000"],
                         capture_output=True, text=True).stdout.splitlines()[1:]
    sites = []
    for line in out:
        p = line.split()
        sites += [(p[0], int(s, 16)) for s in p[2:]]
    return sites


def main():
    insns = [(a - BASE, m, o, s) for a, m, o, s in xrefs.cached_insns("main.dll")]
    idx = {a: k for k, (a, _m, _o, _s) in enumerate(insns)}
    ranges = sorted(gis.patched_ranges())

    def patched(a, size):
        return any(lo < a + size and a < hi for lo, hi, _w in ranges if lo < a + 64)

    def call_to(i, target):
        return i[1] == "call" and i[2] == "0x%x" % (BASE + target)

    found = collections.defaultdict(list)
    for fn, site in remaining():
        k = idx.get(site)
        if k is None:
            continue
        a, m, o, s = insns[k]
        before = insns[max(0, k - 12):k]
        after = insns[k + 1:k + 9]
        if m == "add" and o.startswith("word ptr [") and "+ 0xe3c]" in o and \
                any(call_to(i, RAND169) for i in insns[k - 3:k]):
            found["e3c_bonus"].append((fn, site))
        elif m == "inc" and o.startswith("byte ptr [") and ("+ 0xe36]" in o or "+ 0xe37]" in o) and \
                (any(call_to(i, PLAY_MOTION) for i in before) or
                 any(i[1] == "mov" and "+ 0xe3c], ax" in i[2] for i in insns[k - 6:k + 7])):
            found["substate_start"].append((fn, site))
        elif m == "movss" and o.endswith("+ 0xb4], xmm0") and \
                any(call_to(i, TURN_BLEND) for i in insns[k - 3:k]):
            found["turn_blend"].append((fn, site))
        elif m == "movss" and o.endswith("+ 0xb4], xmm0") and call_to(insns[k - 1], WRAP) and \
                insns[k - 2][1] == "addss" and insns[k - 2][2].endswith("+ 0xb4]") and \
                any(i[1] == "inc" and "+ 0xe36]" in i[2] for i in after):
            found["heading_start"].append((fn, site))
        elif m == "movss" and (o.endswith("+ 0xd24], xmm0") or o.endswith("+ 0xd28], xmm0")) and \
                any(i[1] == "addss" and i[2] == "xmm0, xmm1" for i in insns[k - 3:k]):
            loads = [i for i in insns[k - 14:k] if i[1] == "movss" and i[2].startswith("xmm1, dword ptr [rip")]
            if loads and patched(loads[-1][0], loads[-1][3]):
                found["colour_channel"].append((fn, site, loads[-1][0]))
    for name, rows in found.items():
        print("== %s (%d)" % (name, len(rows)))
        for r in rows:
            print("  " + " ".join(("%X" % x if isinstance(x, int) else x) for x in r))


if __name__ == "__main__":
    main()
