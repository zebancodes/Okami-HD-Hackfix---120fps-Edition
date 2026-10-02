#!/usr/bin/env python3
"""Classify every read of the mode byte before family F6 converts any of them
(world_anims.h, groups "mode" and "repeat").

The mode byte main+B6AC45 is 2 in the 30 fps configuration and 1 in the 60 fps
one. The port reads it to pick its frame-rate-dependent constants, and the
patch keeps it at 1 at 120 fps too, so every read hands out the 60 fps answer
there. Most reads are already handled elsewhere; the rest use the byte as a
quantity ("a step times the mode", "n / mode") and run exactly 2x at 120. This
finds every reference (tools/gen_shadow_mode.py's sweep: every encoding, every
pointer route) and puts each in exactly one class:

  write, restore, save, pointer, zero
          maintained by the shadow family (docs/animation/shadow_mode.csv)
  table   a load at (mode - 1) * 4 from a {k**0.5, k} pair, which
          mode_constants.h rewrites to k**timeScale (kModeTables)
  select  the test in front of a 60 fps constant that mode_constants.h
          retargets (kModeSelects)
  multiplier  the guard of an `n * (mode == 1 ? 2 : 1)` in mode_multipliers.h
  F6      a quantity, converted by a world_anims.h site (REVIEWED names it)
  F5      read with a frame-counter clock that frame_clocks.h converts
  engine  flower_tick's own configuration, which must see the pinned byte
  excluded  read by hand, and why it needs nothing
The two mechanical classes (table, select) are recognised from the code; the
others are listed in REVIEWED below, each checked against the instruction it
names. A reference in no class, or in two, is a problem, and
tools/gen_world_anims.py refuses the F6 groups while there is one. A REVIEWED
entry naming an F6 site that the manifest does not hold is a problem too.

    .venv/Scripts/python tools/survey_mode_reads.py
    -> docs/animation/mode_reads.csv
"""
import csv
import os
import re
import struct
import sys

from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_integer_skips as gis  # noqa: E402
import gen_shadow_mode as gsm  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_CSV = os.path.join(ROOT, "docs", "animation", "mode_reads.csv")
SHADOW_CSV = os.path.join(ROOT, "docs", "animation", "shadow_mode.csv")
MODE_CONSTANTS = os.path.join(ROOT, "src", "mode_constants.h")
MODE_MULTIPLIERS = os.path.join(ROOT, "src", "mode_multipliers.h")
MODE = gsm.MODE

# rva of the read -> (class, the instruction as capstone prints it, why).
# F6 entries name the world_anims.h site(s) that convert the quantity.
REVIEWED = {
    0x4769E3: ("F6", "movzx eax, byte ptr [rip + 0x6f425b]",
               "event camera playhead += mode * speed * 0.5: dst 476A12"),
    0x476A9B: ("F6", "movzx eax, byte ptr [rip + 0x6f41a3]",
               "the same step taken back at the path's end: dst 476AB5"),
    0x4B6684: ("F6", "movzx eax, byte ptr [rip + 0x6b45ba]",
               "total play time += mode a tick: count 4B668B"),
    0x407BAB: ("F6", "movzx eax, byte ptr [rip + 0x763093]",
               "HUD timer -= mode a tick: count 407BB2"),
    0x407D46: ("F6", "movzx eax, byte ptr [rip + 0x762ef8]",
               "HUD timer pulse += mode * 0.15: lin 407D54"),
    0x3FB48B: ("F6", "movzx eax, byte ptr [rip + 0x76f7b3]",
               "cCockCtrlWnd pulse += mode * 0.15: lin 3FB499"),
    0x1826CA: ("F6", "movzx eax, byte ptr [rip + 0x9e8574]",
               "cPad held time += mode: count 1826D4 (the store)"),
    0x1B2AA7: ("F6", "cmp byte ptr [rip + 0x9b8197], 1",
               "layout flipbook: hold += 1 on ticks of one parity in mode 1: count2 1B2AC3"),
    0x1C0A6D: ("F6", "movzx ecx, byte ptr [rip + 0x9aa1d1]",
               "memory card: 8 / mode ticks: imuln 1C0A74"),
    0x1C1597: ("F6", "movzx ecx, byte ptr [rip + 0x9a96a7]",
               "memory card: 6 / mode ticks: imuln 1C159E"),
    0x1C640C: ("F6", "movzx ecx, byte ptr [rip + 0x9a4832]",
               "memory card: 210 / mode ticks: imuln 1C6415"),
    0x1C801F: ("F6", "movzx ecx, byte ptr [rip + 0x9a2c1f]",
               "memory card: 210 / mode ticks: imuln 1C8051"),
    0x153F91: ("F6", "cmp byte ptr [rip + 0xa16cad], 1",
               "options slider: held ticks / (60 or 30 by mode) is seconds held; the held "
               "count steps on stock ticks and the step is x s: count 153F8B, lin 153FD4"),
    0x154051: ("F6", "cmp byte ptr [rip + 0xa16bed], 1",
               "the same slider the other way: count 15404B, lin 154088"),
    0x1541C1: ("F6", "cmp byte ptr [rip + 0xa16a7d], 1",
               "the second slider: count 1541BB, lin 154204"),
    0x154281: ("F6", "cmp byte ptr [rip + 0xa169bd], 1",
               "the second slider the other way: count 15427B, lin 1542B8"),
    0x13F679: ("F6", "sub al, byte ptr [rip + 0xa2b5c6]",
               "menu repeat counter -= mode: smode 13F679, notyet 13F675"),
    0x13F6F4: ("F6", "sub al, byte ptr [rip + 0xa2b54b]",
               "menu repeat counter -= mode: smode 13F6F4, notyet 13F6F0"),
    0x184BED: ("F6", "sub al, byte ptr [rip + 0x9e6052]",
               "pad repeat counter -= mode: smode 184BED, notyet 184BE9"),
    0x184C22: ("F6", "sub al, byte ptr [rip + 0x9e601d]",
               "pad repeat counter -= mode: smode 184C22, notyet 184C1E"),
    0x1B5427: ("excluded", "cmp byte ptr [rip + 0x9b5817], 1",
               "the flipbook's parity seed, phase = fc & 1 in mode 1 (1B5380): kept, so the "
               "phase stays 0 or 1 and count2 1B2AC3 composes with the parity at any N"),
    0x187F47: ("excluded", "movzx r8d, byte ptr [rip + 0x9e2cf6]",
               "ControllerManager::Update(0, mode): flower_kernel hands it to each input "
               "device's slot 2, and none uses it (XInput 29C20 never reads r8d; the "
               "DirectInput devices pass it on to InputDevice::Update 21170, which returns 1)"),
    0x400B56: ("F5", "cmp byte ptr [rip + 0x76a0e8], 2",
               "loading screen fade length ((mode != 2) + 1) * n against 437120's elapsed "
               "count, which frame_clocks.h reads in 60 Hz-configuration ticks (U)"),
    0x43715B: ("F5", "movzx ecx, byte ptr [rip + 0x733ae3]",
               "(fc - t0) < 480 / mode, its fc read as U by frame_clocks.h"),
    0x4376E8: ("F5", "movzx ecx, byte ptr [rip + 0x733556]",
               "(fc - t0) < 480 / mode, its fc read as U by frame_clocks.h"),
    0x4B6488: ("engine", "cmp byte ptr [rip + 0x6b47b6], 1",
               "flower_tick: fps 60, time scale 0.5 and the frame divider when the byte is 1"),
    0x4B6708: ("engine", "cmp byte ptr [rip + 0x6b4536], 1",
               "flower_tick: a second update of B69928 (4A3840) in the 30 fps configuration "
               "only; at 60 and 120 the port's own path"),
    # (mode - 1) * 4 lookups whose base the linear scan cannot name: an epilogue's
    # pop, or the loop the load sits in, comes between the prologue's lea and it
    0x3C006C: ("table", "movzx eax, byte ptr [rip + 0x7aabd2]",
               "[rdi + idx*4 + C8], rdi = 7A8150 (lea at 3BFED6): the pair at 7A8218"),
    0x3C568C: ("table", "movzx eax, byte ptr [rip + 0x7a55b2]",
               "[rsi + idx*4 + 20] or [+8], rsi = 7A8150 (lea at 3C5361): 7A8170 or 7A8158"),
    0x4680B8: ("table", "movzx r9d, byte ptr [rip + 0x702b85]",
               "camera: [rdx + idx*4 + 28] after a loop, rdx = 7A8150 (lea at 4680B1): 7A8178"),
    0x468774: ("table", "movzx edx, byte ptr [rip + 0x7024ca]",
               "camera: [r8 + idx*4 + 28], r8 = 7A8150 (lea at 46876D): 7A8178"),
    0x468ABF: ("table", "movzx r8d, byte ptr [rip + 0x70217e]",
               "camera: [r9 + idx*4 + 28], r9 = 7A8150 (lea at 468AB8): 7A8178"),
}
# F6 entries whose world_anims.h sites are not a kind at the read itself
F6_SITES = {int(x, 16) for why in (e[2] for e in REVIEWED.values() if e[0] == "F6")
            for x in re.findall(r"\b(?:dst|count2?|lin|imuln|smode|notyet) ([0-9A-F]{6})\b",
                                why)}


def header_rvas(path, struct_name):
    text = open(path, encoding="utf-8").read()
    body = re.search(r"%s\[\]\s*=\s*\{(.*?)\n\};" % struct_name, text, re.S).group(1)
    return [int(x, 16) for x in re.findall(r"\{0x([0-9A-F]+)", body)]


def multiplier_guards(path):
    text = open(path, encoding="utf-8").read()
    return {int(x, 16) for x in re.findall(r"guard at ([0-9A-F]+)", text)}


def pdata_entry(img, secs, rva):
    """(begin, end, unwind) of the .pdata entry holding rva, or None"""
    a, b = secs[".pdata"]
    lo, hi = 0, (b - a) // 12
    while lo < hi:
        mid = (lo + hi) // 2
        begin, end, unwind = struct.unpack_from("<III", img, a + 12 * mid)
        if end <= rva:
            lo = mid + 1
        elif begin > rva or begin == 0:
            hi = mid
        else:
            return begin, end, unwind
    return None


def code_ranges(img, secs, rva):
    """The ranges of the function holding rva: its own .pdata range, and each
    parent's through the chained unwind records (a fragment a prologue split
    off names its parent), root last."""
    out = []
    e = pdata_entry(img, secs, rva)
    for _ in range(8):
        if e is None:
            break
        begin, end, unwind = e
        out.append((begin, end))
        if not (img[unwind] >> 3) & 4:
            break
        codes = img[unwind + 2]
        parent = struct.unpack_from("<I", img, unwind + 4 + 2 * (codes + (codes & 1)))[0]
        e = pdata_entry(img, secs, parent)
    return out


def last_lea(md, img, ranges, at, reg):
    """The rva a `lea reg, [rip + d]` puts in reg, if that is reg's last write
    before `at` in the range holding `at`, or failing that the last write in
    each parent's range (a prologue sets a base, a split-off fragment uses
    it). A linear decode: good enough to name the base of a table load, never
    used to patch."""
    for lo, hi in ranges:
        end = at if lo <= at < hi else hi
        last = None
        for i in md.disasm(img[lo:end], lo):
            _r, written = i.regs_access()
            if any(gis.canon(i, w) == reg for w in written):
                last = i
        if last is not None:
            if last.mnemonic == "lea" and last.operands[1].mem.base == X.X86_REG_RIP:
                return (last.address + last.size + last.operands[1].mem.disp) & 0xFFFFFFFF
            return None
    return None


def table_read(md, img, ranges, run, tables):
    """(table, how) for a (mode - 1) * 4 lookup, or None. `run` is the code
    from the read on: the loaded register (and its copies) must be
    decremented (dec, sub 1, lea -1), sign-extended, and used as the *4 index
    of a load at base + displacement = a mode table's 60 fps slot, where the
    base is a rip lea made since the read, or the displacement is itself the
    table's rva (image-base-relative: MSVC's `lea rbp, [__ImageBase]` form),
    or the base's last write before the load is a rip lea (last_lea)."""
    ins = run[0]
    if ins.mnemonic != "movzx" or ins.operands[0].type != X.X86_OP_REG:
        return None
    idx = {gis.canon(ins, ins.operands[0].reg)}
    dec = False
    fwd = {}   # bases set by a rip lea since the read, on the fall-through path
    for i in run[1:48]:
        # the fall-through path only: a conditional branch is stepped over
        if i.mnemonic in ("ret", "call", "jmp"):
            break
        ops = i.operands
        regs = [gis.canon(i, op.reg) if op.type == X.X86_OP_REG else None for op in ops]
        if i.mnemonic == "dec" and regs[0] in idx:
            dec = True
            continue
        if i.mnemonic == "sub" and regs[0] in idx and ops[1].type == X.X86_OP_IMM and \
                ops[1].imm == 1:
            dec = True
            continue
        if i.mnemonic in ("movsxd", "mov", "movzx") and len(ops) == 2 and regs[1] in idx:
            idx.add(regs[0])
            continue
        if i.mnemonic == "lea" and ops[1].mem.index == 0 and ops[1].mem.base and \
                gis.canon(i, ops[1].mem.base) in idx and ops[1].mem.disp == -1:
            idx.add(regs[0])
            dec = True
            continue
        for op in ops:
            if op.type != X.X86_OP_MEM or not op.mem.index:
                continue
            if gis.canon(i, op.mem.index) not in idx or op.mem.scale != 4 or not dec:
                continue
            base = gis.canon(i, op.mem.base) if op.mem.base else None
            if base is None:
                continue
            disp = op.mem.disp & 0xFFFFFFFF
            if base in fwd:
                t, how = (fwd[base] + disp) & 0xFFFFFFFF, "base lea at the read"
            elif disp in tables:
                t, how = disp, "image-base-relative"
            else:
                v = last_lea(md, img, ranges, i.address, base)
                if v is None:
                    continue
                t, how = (v + disp) & 0xFFFFFFFF, "base %s's last lea before %X" % (
                    base, i.address)
            if t in tables:
                return t, how
        _r, written = i.regs_access()
        for w in written:
            idx.discard(gis.canon(i, w))
            fwd.pop(gis.canon(i, w), None)
        if i.mnemonic == "lea" and ops[1].mem.base == X.X86_REG_RIP:
            fwd[regs[0]] = (i.address + i.size + ops[1].mem.disp) & 0xFFFFFFFF
        if not idx:
            break
    return None


def audit():
    """(rows, problems)"""
    img, secs, funcs, _sha = gsm.load_image()
    refs, sweep_problems = gsm.sweep(img, secs)
    others, _notes, _zeroes = gsm.resolve_pointer_routes(img, secs, funcs, sweep_problems)
    problems = ["%X: %s" % p for p in others]
    shadow = {int(r["site"], 16): r for r in csv.DictReader(open(SHADOW_CSV, encoding="utf-8"))}
    tables = set(header_rvas(MODE_CONSTANTS, "kModeTables"))
    selects = set(header_rvas(MODE_CONSTANTS, "kModeSelects"))
    guards = multiplier_guards(MODE_MULTIPLIERS)
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    rows = []
    seen = set()
    for ins in refs:
        a = ins.address
        seen.add(a)
        text = "%s %s" % (ins.mnemonic, ins.op_str)
        run = list(md.disasm(img[a:a + 256], a))
        fn = gsm.function_of(funcs, a)
        classes = []
        sh = shadow.get(a)
        if sh and sh["class"] in ("write", "restore", "save"):
            classes.append((sh["class"], "shadow family: " + sh["evidence"]))
        t = table_read(md, img, code_ranges(img, secs, a), run, tables)
        if t is not None:
            classes.append(("table", "(mode - 1) * 4 into the pair at %X (%s), rewritten to "
                            "k**timeScale" % t))
        sel = [r.address for r in run[1:9] if r.address in selects]
        if sel and ins.mnemonic == "cmp":
            classes.append(("select", "picks the 0.5 at %X, retargeted" % sel[0]))
        if a in guards:
            classes.append(("multiplier", "mode_multipliers.h guard"))
        if a in REVIEWED:
            cls, want, why = REVIEWED[a]
            if want != text:
                problems.append("%X: REVIEWED expects %r, the code is %r" % (a, want, text))
            classes.append((cls, why))
        row = dict(site="%X" % a, function="%X" % fn if fn is not None else "",
                   instruction=text, **{"class": "", "evidence": ""})
        if len(classes) != 1:
            problems.append("%X %s: %s" % (a, text, "unclassified" if not classes else
                                           "in %d classes: %s" % (
                                               len(classes), ", ".join(c for c, _ in classes))))
            row["class"] = "PROBLEM"
            row["evidence"] = "; ".join("%s: %s" % c for c in classes)
        else:
            row["class"], row["evidence"] = classes[0]
        rows.append(row)
    for a, (cls, want, _w) in sorted(REVIEWED.items()):
        if a not in seen:
            problems.append("REVIEWED names %X (%s), which reads no mode byte" % (a, want))
    for a, r in sorted(shadow.items()):
        if r["class"] in ("pointer", "zero"):
            rows.append(dict(site=r["site"], function=r["function"],
                             instruction=r["instruction"], **{"class": r["class"]},
                             evidence="shadow family: " + r["evidence"]))
    rows.sort(key=lambda r: int(r["site"], 16))
    return rows, problems


def manifest_problems(manifest):
    """Every F6 site REVIEWED names must be in the manifest, and every mode or
    repeat site of the manifest must be named by a REVIEWED F6 entry."""
    listed = {m[2] for m in manifest if m[0] in ("mode", "repeat")}
    out = ["REVIEWED names F6 site %X, which the manifest does not hold" % a
           for a in sorted(F6_SITES - listed)]
    out += ["manifest site %X is in no REVIEWED F6 entry" % a for a in sorted(listed - F6_SITES)]
    return out


def main():
    rows, problems = audit()
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "function", "instruction", "class", "evidence"])
        w.writeheader()
        w.writerows(rows)
    import collections
    print("mode reads: %d references: %s" % (
        len(rows), dict(collections.Counter(r["class"] for r in rows))))
    import gen_world_anims
    problems += manifest_problems(gen_world_anims.MANIFEST)
    for p in problems:
        print("PROBLEM " + p)
    print("%d problems" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
