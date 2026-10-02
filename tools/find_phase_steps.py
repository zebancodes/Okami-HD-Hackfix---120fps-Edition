#!/usr/bin/env python3
"""Find per-tick float phase steps in main.dll and emit the C table.

Alongside the integer action timers (see find_action_timers.py) the engine runs
a great many *float* per-tick counters: effect lifetimes, fade and flash meters,
scroll offsets, oscillator phases. They all have the same shape -- load a field,
add or subtract a literal, store it back:

    movss xmm0, dword ptr [rbx+0x19C]
    subss xmm0, dword ptr [rip+...]      ; = 1.0
    movss dword ptr [rbx+0x19C], xmm0
    comiss xmm3, xmm0                    ; ... and check the limit
    jb    ...

698 sites do this with a literal step and only 2 of them consult the engine
time scale, so at 60 fps every one of them advances twice as fast in real time.

Not all of them are per-tick: an event handler that adds a one-off nudge looks
identical in isolation. The discriminator is the limit check. A field that is
stepped and then compared or clamped nearby is a running phase; one that is not
is usually a one-shot. The split is clean -- the clamped sites step by 0.05,
0.1, 0.02, 0.01 while the unclamped ones step by 10, 20, 40, 64, 100 -- so this
tool keeps only the clamped sites with a step of at most `MAX_STEP`.

A second shape is a phase kept inside +-pi: the sum goes through the engine's
angle wrap (`WRAP_FN`, a pure function of xmm0 that returns in xmm0) before
it is stored, so there is a call between the step and the store and no compare
after it:

    movss xmm0, dword ptr [rbx+0x6C]
    addss xmm0, dword ptr [rip+...]      ; = 0.3
    call  wrap
    movss dword ptr [rbx+0x6C], xmm0

The wrap bounds the field like a clamp does, but the same shape also turns an
object round by pi once, so the shape alone decides nothing. A wrap step is
kept only when the tracer session proved it (docs/animation/classification.csv):
the store changed the field on every execution (`clock`), in a stock 30 Hz
context -- the time scale this table follows is 1/N30. Everything else of the
shape is listed and left alone.

The fix needs no code injection. Every one of these instructions is the 8-byte
rip-relative form, so the patch only rewrites the 4-byte displacement to point
at a private copy of the constant, which the patch keeps multiplied by the time
scale. Constants are shared (1.0 is one address used by hundreds of sites), but
because only the named instruction is retargeted, nothing else is affected.

    python tools/find_phase_steps.py
"""
import collections
import csv
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
MAX_STEP = 1.0          # larger literals are one-shot nudges, not phase steps
RDATA_LO, RDATA_HI = 0x600000, 0x800000

WRAP_FN = 0x13F2E0     # wraps xmm0 into +-pi; touches nothing but its own stack
# Steps inside a world gatefn (gen_world_anims.py): the gate runs the whole
# function once a stock tick, so a step scaled to 1/N inside it would advance
# N times too slowly. As find_decay_factors.STOCK_GATED, each is left to its
# gate, and the tool refuses to write if the gate or the step is gone.
STOCK_GATED = {0x57E399: 0x57E020}   # ut33's wobble +E14 += 0.0001047
# Sites with the shape that are not per-tick steps, read by hand. The tool
# refuses to write if one of them is no longer found.
NOT_STEPS = {
    # the sound library's channel mix setup (1D560, linked middleware): beside
    # the -3 dB and -6 dB downmix gains, +54 += 1.0 puts a unit gain in one
    # coefficient of a starting sound's output matrix. It runs when a sound
    # starts, not once a tick; scaled, that channel was mixed at a quarter of
    # its gain at 120 (a half at 60).
    0x1D601: "a mix-matrix coefficient in the sound library",
}
CALLEE_SAVED = {"rbx", "rbp", "rsi", "rdi", "r12", "r13", "r14", "r15"}
CLASSIFICATION = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "..", "docs", "animation", "classification.csv"))

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


def traced_clocks():
    """Store sites the tracer saw change their field on every execution in a
    stock 30 Hz context: the evidence a wrap step needs."""
    with open(CLASSIFICATION, newline="") as fh:
        return {int(r["site"], 16) for r in csv.DictReader(fh)
                if r["class"] == "clock" and r["context"] == "30"}


def main():
    img, insns = disassemble(os.path.join(GAME, "main.dll"))
    proven = traced_clocks()
    kept = []
    wraps = []            # (step_at, const, step, off, store, kept?)
    for i, (a, m, o, s) in enumerate(insns):
        if m != "movss":
            continue
        lm = LOAD.match(o)
        if not lm:
            continue
        reg, base, off = lm.groups()
        if base in ("rsp", "rbp", "esp", "ebp"):
            continue          # a stack local, not per-tick object state
        step = None
        step_at = None
        step_const = None
        step_j = wrap_j = None
        for j in range(i + 1, min(i + 10, len(insns))):
            a2, m2, o2, s2 = insns[j]
            if m2 in ("addss", "subss") and o2.startswith(reg + ","):
                t = rip_target(a2, o2, s2)
                if t and RDATA_LO < t < RDATA_HI and s2 == 8:
                    try:
                        step = struct.unpack_from("<f", img, t)[0]
                    except Exception:
                        step = None
                    step_at, step_const, step_j = a2, t, j
            elif m2 == "movss":
                sm = STORE.match(o2)
                if (sm and sm.group(2) == off and sm.group(3) == reg
                        and sm.group(1) == base
                        and step is not None):
                    if wrap_j is not None:
                        if j == wrap_j + 1 and 0.0 < abs(step) <= MAX_STEP:
                            wraps.append((step_at, step_const, step, off, a2, a2 in proven))
                        break
                    clamped = any(insns[k][1] in ("comiss", "ucomiss", "maxss", "minss")
                                  for k in range(i, min(i + 14, len(insns))))
                    if clamped and 0.0 < abs(step) <= MAX_STEP:
                        kept.append((step_at, step_const, step, off))
                    break
            elif (m2 == "call" and wrap_j is None and step_j == j - 1 and reg == "xmm0"
                  and base in CALLEE_SAVED and o2 == hex(BASE_IMAGE + WRAP_FN)):
                wrap_j = j    # the angle wrap: the sum comes back in xmm0, base kept
            elif m2 in ("call", "jmp", "ret"):
                break
    kept += [w[:4] for w in wraps if w[5]]

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gen_world_anims
    gates = {r[2] for r in gen_world_anims.MANIFEST if r[1] == "gatefn"}
    for at, function in STOCK_GATED.items():
        if function not in gates or not any(k[0] == at for k in kept):
            sys.exit("stock-gated step %X requires gatefn %X and its original step; "
                     "nothing written" % (at, function))
    kept = [k for k in kept if k[0] not in STOCK_GATED]
    for at, why in NOT_STEPS.items():
        if not any(k[0] == at for k in kept):
            sys.exit("NOT_STEPS site %X (%s) is no longer found; nothing written" % (at, why))
    kept = [k for k in kept if k[0] not in NOT_STEPS]

    kept.sort()
    seen = set()
    rows = []
    for rva, const, step, off in kept:
        if rva in seen:            # one instruction, one entry
            continue
        seen.add(rva)
        rows.append((rva, const, step, off, bytes(img[rva:rva + 8])))

    consts = collections.Counter(r[1] for r in rows)
    out = [
        "// Generated by tools/find_phase_steps.py -- do not edit by hand.",
        "// See the README section \"Per-tick phase steps at 60 fps\".",
        "//",
        "// Each entry is one 8-byte `addss/subss xmm, dword ptr [rip+K]` that advances",
        "// a float field once per tick -- an effect lifetime, a fade meter, a scroll",
        "// offset, an oscillator phase. Only the 4-byte displacement is rewritten, to",
        "// point at a private copy of K that the patch keeps scaled by the time scale.",
        "//",
        "// %d instructions over %d distinct constants." % (len(rows), len(consts)),
        "",
        "struct PhaseSite {",
        "    uint32_t rva;       // the addss/subss instruction",
        "    uint32_t constRva;  // the .rdata float it reads",
        "    uint8_t orig[8];    // exactly what must be there",
        "};",
        "",
        "static const PhaseSite kPhaseSites[] = {",
    ]
    for rva, const, step, off, raw in rows:
        body = ", ".join("0x%02X" % b for b in raw)
        out.append("    {0x%06X, 0x%06X, {%s}},  // %+g -> +%s"
                   % (rva, const, body, step, off))
    out.append("};")

    dest = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "src", "phase_steps.h"))
    with open(dest, "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("%d instructions over %d constants written to src/phase_steps.h"
          % (len(rows), len(consts)))
    print("most common steps: %s"
          % ", ".join("%g x%d" % (k, v)
                      for k, v in collections.Counter(round(r[2], 4) for r in rows).most_common(8)))
    for step_at, const, step, off, store, ok in sorted(wraps):
        print("wrap step %06X %+g -> +%s (store %06X): %s"
              % (step_at, step, off, store,
                 "kept, traced per-tick at 30" if ok else "left alone, not traced per-tick at 30"))


if __name__ == "__main__":
    main()
