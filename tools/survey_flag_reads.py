#!/usr/bin/env python3
"""Classify every reference to the 60 fps flag and the fps byte before the
flag group converts any (world_anims.h, group "flag").

flower_tick (4B63B0) writes the frame configuration each tick: at 30 fps the
time scale 1.0, main+B6AC3C = 4, the 60 fps flag main+B6AC40 = 0 and the fps
byte main+B6AC44 = 30; when the mode byte is 1, the time scale 0.5, B6AC3C =
2, the flag 1 and the fps byte 60. The patch keeps the mode byte at 1 at 120
too, so both read their 60 fps values there. The port writes durations in
ticks as `n << flag` (n stock ticks, 2n at 60) and `seconds x fps`: right at
30 and 60, half the time at 120. This finds every reference (every rip
operand covering B6AC40..B6AC44, rip leas and pointers near them) and puts
each in exactly one class:

  engine  flower_tick's own writes
  rumble  a flag read whose value is, on every path, only the shift count of a
          rumble's length or delay handed to cPad::ActSet (182470): `(n <<
          flag) << 16` in r8d, reached by a call or a tail jump. ActSet queues
          the rumble in one of the pad's 32 slots and cPad::Actuater (1825A0)
          counts each slot's delay and then its length down once a call, once
          a tick: the flag group runs Actuater at the port's 60 Hz (its
          gatefn), so every one of these lengths lasts its stock time.
          Recognised from the code (rumble_read). Also an fps byte read whose
          value is only arithmetic on the way to ActSet's r8d (`3 x (fps /
          30)`, the ten sites FixInputWindows unshifts): fps ticks counted at
          60 Hz are its stock seconds (fps_rumble_read)
  F7      a quantity converted by a flag-group site (REVIEWED names it)
  notyet  read, and not converted yet (REVIEWED says what it is)
A reference in no class is a problem, and tools/gen_world_anims.py refuses the
flag group while there is one, or while the manifest's flag sites and the
REVIEWED F7 entries disagree.

    .venv/Scripts/python tools/survey_flag_reads.py
    -> docs/animation/flag_reads.csv
"""
import bisect
import collections
import csv
import os
import re
import struct
import sys

import capstone
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_turn_callers as gtc  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_CSV = os.path.join(ROOT, "docs", "animation", "flag_reads.csv")
BASE = 0x180000000
FLAG, FPS = 0xB6AC40, 0xB6AC44
NEAR = (0xB6AC3C, 0xB6AC48)
ACTSET, ACTUATER = 0x182470, 0x1825A0
ENGINE = {0x4B6476: "flower_tick: B6AC3C = 4 and the flag = 0, one qword store, at 30 fps",
          0x4B6481: "flower_tick: fps byte = 30",
          0x4B6491: "flower_tick: fps byte = 60 when the mode byte is 1",
          0x4B64AC: "flower_tick: the flag = 1 when the mode byte is 1"}
FPS_NOT_YET = "the fps byte (60 at 60 and 120) as a quantity: %s, half its stock time at " \
    "120; not converted yet"
# rva -> (class, the instruction as capstone prints it, why). F7 entries name
# the flag-group site(s) that convert the quantity.
REVIEWED = {
    0x188315: ("F7", "mov ecx, dword ptr [rip + 0x9e2925]",
               "rumble track waveform and small-motor PWM: gatefn 1882A0 runs the "
               "complete wave sample, pulse accumulator and phase advance at N60, "
               "the same cadence as Actuater's stock flag-sized request durations"),
    0x4BD9DC: ("F7", "mov ecx, dword ptr [rip + 0x6ad25e]",
               "movie continuous small-motor PWM: count 4BDA0A advances the phase "
               "at N60, matching Actuater's flag-sized requests. The phase starts "
               "at zero, adds a byte intensity (or its bounded interpolation), "
               "and subtracts 255 on crossing, so a held phase stays below 255 "
               "and cannot repeat a pulse; external-playhead keyframes remain live"),
    0x3E2ABB: ("F7", "mov ecx, dword ptr [rip + 0x78817f]",
               "the screen fade at 9CED58 (3E2A90, 68 callers: a colour flash or fade over "
               "n ticks, drawn and stepped by 3E2B60): its length +C = (1 << flag) x n, the "
               "elapsed count +E counting up to it a tick: mulflag 3E2ACE"),
}
# the fps byte's reads, by shape, read in their functions
FPS_SHAPES = {
    "shr": "fps / 2 as a count of ticks: a period fc % (fps / 2) in the player's 3B2CF0 "
           "(a sound every half second; the value stays live in ecx up to a call that "
           "takes rcx, so a scaled divisor needs its own kind)",
    "mul": "(fps / 30) x n, a length in ticks",
    "quake": "(fps / 30) x 15 stored to the byte B663D8, a length in ticks of a quake-like "
             "global (B663C8..D8 in the block at B66380, set by about 60 places, most with "
             "constant tick counts; read through a pointer to B66380, the reader not found "
             "yet: the scenery's 364B00 and 370280, the player's 3C1A80 and 3C5EA0)",
    "div": "a count of ticks / fps as seconds (4B1D80, 4FBCB0, 5381A0)",
    "other": "the player's 3A9630 and 3B9A70: fps (x 2) stored to +1144",
}
# The fps byte's half-second waits, read by hand: a field each screen sets to
# fps / 2 and counts down once a call of its per-tick update (the screens'
# vtable update slots; F1 already halves the memory-card screens' own counters
# at 120, so these updates run every tick). fps / 2 ticks are half a second at
# 30 and 60 and a quarter at 120; the flag group's mulstore multiplies the
# value stored by N (2 at 120), so the wait is fps x N / 2 ticks, half a
# second again. The register keeps fps / 2: some setters return it, and a
# state handler's return may be its dispatcher's status.
# `code` is what the reader guard sweeps: every read there of the field must
# be one of `readers` (block copies through another pointer that only cover
# it are listed as such), or the survey reports a problem.
WAITS = {
    0x6C: dict(
        name="the memory-card screens' wait (cMcLoad, cMcSave, cMcBoot: +6C)",
        code=((0x1BE000, 0x1C6000), (0x5FDF00, 0x5FF000)),
        readers={
            0x1BECC8: "1BECA0's countdown: +6C - 1 a call while above 0, then its next step "
                      "(called by the screens' per-tick states)",
            0x1C240A: "a copy of the save data at [+220] (16 bytes from +60), not the screen",
            0x1C3B42: "a copy of the save data (16 bytes from +60), not the screen",
        }),
    0xB0: dict(
        name="the options screen's wait (cOptionScreenSetting: +B0)",
        code=((0x14B200, 0x14D200),),
        readers={
            0x14C45D: "14C450's countdown: +B0 - 1 a call while above 0 (14BD30, the "
                      "screen's update, vtable slot 2, calls it)",
            0x14C66D: "14C620's countdown: +B0 - 1 a call while above 0 (14BD30 calls it)",
            0x14D12A: "a test of the wait against 0 (an item greyed while it runs)",
        }),
}
STORES = ("mov", "movups", "movaps", "movdqu", "movdqa", "movss", "movsd", "movq", "movd")
WAIT_WHY = "%s: fps / 2 ticks, counted down once a tick; half a second at 30 and 60, a " \
    "quarter at 120: mulstore %X, the value stored times N"


def references(img, secs):
    """(refs, problems): every instruction with a rip operand covering the
    flag or the fps byte, and any other route to them."""
    lo, hi = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    refs, problems = [], []
    pos = lo
    while pos < hi:
        end = min(hi, pos + 0x10000)
        last = pos
        for ins in md.disasm(img[pos:end + 16], pos):
            if ins.address >= end:
                break
            last = ins.address + ins.size
            for op in ins.operands:
                if op.type != X.X86_OP_MEM:
                    continue
                m = op.mem
                if m.base == X.X86_REG_RIP:
                    t = ins.address + ins.size + m.disp
                    if ins.mnemonic == "lea":
                        if NEAR[0] <= t < NEAR[1]:
                            problems.append("%X: lea of main+%X" % (ins.address, t))
                        continue
                    size = max(op.size, 1)
                    if t < FLAG + 4 and FLAG < t + size:
                        refs.append((ins.address, "flag"))
                    elif t <= FPS < t + size:
                        refs.append((ins.address, "fps"))
                elif NEAR[0] <= m.disp < NEAR[1]:
                    problems.append("%X: displacement %X (image-base-relative?)"
                                    % (ins.address, m.disp))
        pos = last if last > pos else pos + 1
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a & ~7, b - 8, 8):
            v = struct.unpack_from("<Q", img, off)[0]
            if BASE + NEAR[0] <= v < BASE + NEAR[1]:
                problems.append("%X: %s holds the address main+%X" % (off, name, v - BASE))
    return refs, problems


def rumble_read(fn, a):
    """None if the flag read at `a` (`mov ecx, dword [flag]`) reaches, on every
    path, only `shl r32, cl` shifts whose results (through shl by a constant,
    or, mov, lea) are r8d at a call or tail jump of cPad::ActSet; else why
    not. rcx must be dead or rewritten before anything else reads it."""
    i = fn.ins[a]
    if i.mnemonic != "mov" or i.op_str.split(",")[0] != "ecx":
        return "not mov ecx, [flag]"
    work, seen = [(a + i.size, frozenset(["rcx"]), frozenset())], set()
    reached = False
    while work:
        b, flag, shifted = work.pop()
        if (b, flag, shifted) in seen:
            continue
        seen.add((b, flag, shifted))
        if len(seen) > 400:
            return "walk too long"
        if not flag and not shifted:
            continue
        j = fn.ins.get(b)
        if j is None:
            return "leaves the function at %X" % b
        m = j.mnemonic
        rd, wr = gtc.reads(j), gtc.writes(j)
        nf, ns = set(flag), set(shifted)
        target = j.operands[0].imm if j.operands and j.operands[0].type == X.X86_OP_IMM else None
        if m in ("call", "jmp") and target == ACTSET:
            if not shifted & {"r8"}:
                return "ActSet at %X without a shifted length in r8" % b
            reached = True
            if m == "jmp":
                continue
            nf, ns = set(), set()
            work.append((b + j.size, frozenset(nf), frozenset(ns)))
            continue
        if m == "call":
            if target is None or (shifted & {"rcx", "rdx", "r8", "r9"} and target != 0x182CE0):
                return "a call at %X with the value live" % b
            nf -= gtc.VOL_GPR | {"rax"}
            ns -= gtc.VOL_GPR | {"rax"}
            work.append((b + j.size, frozenset(nf), frozenset(ns)))
            continue
        if m in ("ret", "retf"):
            if shifted:
                return "returns at %X with a shifted value" % b
            continue
        dst = gtc.reg_key(j, j.operands[0].reg) if j.operands and \
            j.operands[0].type == X.X86_OP_REG else None
        if rd & flag:
            if m in ("shl", "sal") and j.op_str.endswith(", cl"):
                ns.add(dst)
            elif m == "and" and dst == "rcx" and j.op_str.endswith("0x1f"):
                pass                                    # the shift count's own mask
            else:
                return "the flag read by %X %s %s" % (b, m, j.op_str)
        elif rd & shifted:
            if m in ("shl", "or", "mov", "lea", "movzx") and dst:
                ns.add(dst)
            elif m.startswith("j"):
                pass
            else:
                return "a shifted length read by %X %s %s" % (b, m, j.op_str)
        for r in wr:
            if r not in (dst,) or not (rd & (flag | shifted)):
                nf.discard(r)
                if not (rd & shifted and r == dst):
                    ns.discard(r)
        if m.startswith("j"):
            if target is None:
                return "an indirect jump at %X" % b
            work.append((target, frozenset(nf), frozenset(ns)))
            if m != "jmp":
                work.append((b + j.size, frozenset(nf), frozenset(ns)))
        else:
            work.append((b + j.size, frozenset(nf), frozenset(ns)))
    return None if reached else "no ActSet reached"


def fps_rumble_read(fn, a):
    """None if the fps byte read at `a` (`movzx r32, byte [fps]`) reaches, on
    every path, only integer arithmetic (mul, shr, shl, imul, lea, mov, movzx,
    or, add) whose results are r8d at a call or tail jump of cPad::ActSet; else
    why not. A call reads its argument registers only (rcx, rdx, r8, r9): a
    copy left in a callee-saved register passes it, and must be rewritten
    before anything else reads it. The pad getter 182CE0 reads none."""
    i = fn.ins[a]
    op = i.operands[0]
    if i.mnemonic != "movzx" or op.type != X.X86_OP_REG:
        return "not movzx r32, [fps]"
    work, seen = [(a + i.size, frozenset([gtc.reg_key(i, op.reg)]))], set()
    reached = False
    while work:
        b, val = work.pop()
        if (b, val) in seen:
            continue
        seen.add((b, val))
        if len(seen) > 400:
            return "walk too long"
        if not val:
            continue
        j = fn.ins.get(b)
        if j is None:
            return "leaves the function at %X" % b
        m = j.mnemonic
        rd, wr = gtc.reads(j), gtc.writes(j)
        nv = set(val)
        target = j.operands[0].imm if j.operands and j.operands[0].type == X.X86_OP_IMM else None
        if m in ("call", "jmp") and target == ACTSET:
            if "r8" not in val or val - {"r8"} & {"rcx", "rdx", "r9"}:
                return "ActSet at %X with the value not only in r8" % b
            reached = True
            if m == "call":
                work.append((b + j.size, frozenset(val - gtc.VOL_GPR - {"rax"})))
            continue
        if m == "call":
            if target != 0x182CE0 and val & {"rcx", "rdx", "r8", "r9"}:
                return "a call at %X with the value in an argument register" % b
            work.append((b + j.size, frozenset(val - gtc.VOL_GPR - {"rax"})))
            continue
        if m in ("ret", "retf"):
            return "returns at %X with the value live" % b
        dst = gtc.reg_key(j, j.operands[0].reg) if j.operands and \
            j.operands[0].type == X.X86_OP_REG else None
        if rd & val:
            if m == "mul" and len(j.operands) == 1:
                nv |= {"rax", "rdx"}
                wr = set()
            elif m in ("shr", "shl", "imul", "lea", "mov", "movzx", "or", "add") and dst:
                nv.add(dst)
                wr = set(wr) - {dst}
            else:
                return "the value read by %X %s %s" % (b, m, j.op_str)
        nv -= set(wr)
        if m.startswith("j"):
            if target is None:
                return "an indirect jump at %X" % b
            work.append((target, frozenset(nv)))
            if m != "jmp":
                work.append((b + j.size, frozenset(nv)))
        else:
            work.append((b + j.size, frozenset(nv)))
    return None if reached else "no ActSet reached"


QUAKE_LENGTH = 0xB663D8


def fps_shape(md, img, a):
    """shr, mul, quake, div or other: what the fps byte read at `a` does next,
    in the straight-line code after it (a leaf without .pdata included)"""
    seq = list(md.disasm(img[a:a + 96], a))
    op = seq[0].operands[0]
    reg = gtc.reg_key(seq[0], op.reg) if op.type == X.X86_OP_REG else None
    for j in seq[1:9]:
        if reg in gtc.reads(j):
            shape = {"shr": "shr", "mul": "mul", "div": "div"}.get(j.mnemonic, "other")
            break
    else:
        return "other"
    if shape == "mul":
        for j in seq[1:16]:
            o = mem_target(j)
            if o == QUAKE_LENGTH and j.mnemonic == "mov":
                return "quake"
    return shape


def fps_wait_read(md, img, a):
    """(field, store rva, None) if the fps byte read at `a` is halved and
    stored as a WAITS wait on the straight line: `movzx r32, byte [fps]`, then
    `shr r32, 1` and `mov dword [B + d], r32` (d a WAITS field, `a` in its
    code, B not r), nothing between them writing r32 or leaving the line.
    What r32 does after the store does not matter: mulstore scales the stored
    value only and keeps the register. Else (None, None, why)."""
    seq = list(md.disasm(img[a:a + 64], a))
    i0 = seq[0]
    ops = i0.operands
    if i0.mnemonic != "movzx" or ops[0].type != X.X86_OP_REG or ops[0].size != 4:
        return None, None, "not movzx r32, byte [fps]"
    r = gtc.reg_key(i0, ops[0].reg)
    halved = False
    for j in seq[1:8]:
        jo = j.operands
        text = "%X %s %s" % (j.address, j.mnemonic, j.op_str)
        if j.mnemonic in ("call", "ret", "retf") or j.mnemonic.startswith(("j", "loop")):
            return None, None, "%s before the store" % text
        if r in gtc.reads(j):
            if j.mnemonic == "shr" and not halved and jo[0].type == X.X86_OP_REG and \
                    gtc.reg_key(j, jo[0].reg) == r and jo[1].type == X.X86_OP_IMM and \
                    jo[1].imm == 1:
                halved = True
                continue
            if halved and j.mnemonic == "mov" and jo[0].type == X.X86_OP_MEM and \
                    jo[0].size == 4 and jo[1].type == X.X86_OP_REG and \
                    gtc.reg_key(j, jo[1].reg) == r and \
                    jo[0].mem.base not in (0, X.X86_REG_RIP, X.X86_REG_RSP) and \
                    not jo[0].mem.index and gtc.reg_key(j, jo[0].mem.base) != r:
                d = jo[0].mem.disp
                if d not in WAITS or not any(lo <= a < hi for lo, hi in WAITS[d]["code"]):
                    return None, None, "stored to +%X at %s, no wait read by hand" % (d, text)
                return d, j.address, None
            return None, None, "read by %s" % text
        if r in gtc.writes(j):
            return None, None, "rewritten at %s" % text
    return None, None, "no store of it on the straight line"


def wait_reader_problems(img):
    """Every read, in a WAITS field's code, of a memory operand covering the
    field (not rip or rsp; a lea of it too) that its readers do not list."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    out = []
    for d, w in sorted(WAITS.items()):
        seen = set()
        for lo, hi in w["code"]:
            pos = lo
            while pos < hi:
                last = pos
                for i in md.disasm(img[pos:hi + 16], pos):
                    if i.address >= hi:
                        break
                    last = i.address + i.size
                    for op in i.operands:
                        if op.type != X.X86_OP_MEM or op.mem.base in (
                                0, X.X86_REG_RIP, X.X86_REG_RSP):
                            continue
                        size = max(op.size, 1)
                        if not (op.mem.disp <= d < op.mem.disp + size or
                                d <= op.mem.disp < d + 4):
                            continue
                        if i.mnemonic != "lea" and not op.access & capstone.CS_AC_READ:
                            continue
                        if i.mnemonic in STORES and op is i.operands[0]:
                            continue            # a plain store (capstone flags some as reads)
                        seen.add(i.address)
                        if i.address not in w["readers"]:
                            out.append("%X %s %s reads %s, not a reader read by hand" % (
                                i.address, i.mnemonic, i.op_str, w["name"]))
                pos = last if last > pos else pos + 1
        out += ["%X: a reader of %s that the code no longer has" % (a, w["name"])
                for a in sorted(set(w["readers"]) - seen)]
    return out


def mulstore_rows(rows, img=None):
    """the flag group's mulstore manifest rows for the survey's F7 fps reads:
    (group, kind, the store's rva, its text, the read's rva, reason)"""
    import re
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    if img is None:
        img = gtc.load_image()[0]
    out = []
    for r in rows:
        if r["what"] == "fps" and r["class"] == "F7" and "mulstore" in r["evidence"]:
            store = int(re.search(r"mulstore ([0-9A-F]+)", r["evidence"]).group(1), 16)
            i = next(md.disasm(img[store:store + 16], store))
            out.append(("flag", "mulstore", store, "%s %s" % (i.mnemonic, i.op_str),
                        int(r["site"], 16), r["evidence"]))
    return out


def mem_target(j):
    """the address of a rip operand of `j`, or None"""
    for o in j.operands:
        if o.type == X.X86_OP_MEM and o.mem.base == X.X86_REG_RIP:
            return j.address + j.size + o.mem.disp
    return None


def audit():
    """(rows, problems)"""
    img, secs, _f, _sha = gtc.load_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    roots, starts, _e = gtc.pdata_roots(img, secs)
    refs, problems = references(img, secs)
    problems = list(problems)
    fcache, rows, seen_reviewed = {}, [], set()
    for a, what in refs:
        k = bisect.bisect_right(starts, a) - 1
        frag = starts[k] if k >= 0 else None
        fn = None
        if frag is not None and any(b <= a < e for b, e in roots[frag][1]):
            root, frags = roots[frag]
            if root not in fcache:
                fcache[root] = gtc.Func(img, root, frags, md)
            fn = fcache[root]
        i = fn.ins.get(a) if fn is not None else next(md.disasm(img[a:a + 16], a))
        text = "%s %s" % (i.mnemonic, i.op_str)
        row = dict(site="%X" % a, function="%X" % fn.root if fn else "", what=what,
                   instruction=text, **{"class": ""}, evidence="")
        rows.append(row)
        if a in REVIEWED:
            seen_reviewed.add(a)
            cls, want, why = REVIEWED[a]
            if text != want:
                problems.append("%X: REVIEWED says %s, the code is %s" % (a, want, text))
            row.update(**{"class": cls}, evidence=why)
        elif a in ENGINE:
            row.update(**{"class": "engine"}, evidence=ENGINE[a])
        elif what == "flag" and fn is not None:
            why = rumble_read(fn, a)
            if why is None:
                row.update(**{"class": "rumble"},
                           evidence="a rumble length for cPad::ActSet: the gate on "
                                    "cPad::Actuater %X" % ACTUATER)
            else:
                row.update(**{"class": "PROBLEM"}, evidence=why)
        elif what == "fps" and fn is not None and fps_rumble_read(fn, a) is None:
            row.update(**{"class": "rumble"},
                       evidence="a rumble length for cPad::ActSet from the fps byte, (fps / "
                                "30) x n ticks: the gate on cPad::Actuater %X counts it at "
                                "60 Hz, its stock time" % ACTUATER)
        elif what == "fps" and fps_wait_read(md, img, a)[2] is None:
            d, store, _why = fps_wait_read(md, img, a)
            row.update(**{"class": "F7"}, evidence=WAIT_WHY % (WAITS[d]["name"], store))
        elif what == "fps":
            shape = fps_shape(md, img, a)
            row.update(**{"class": "notyet"}, evidence=FPS_NOT_YET % FPS_SHAPES[shape])
        else:
            row.update(**{"class": "PROBLEM"}, evidence="not in a .pdata function")
    for a in sorted(set(REVIEWED) - seen_reviewed):
        problems.append("%X: stale REVIEWED entry" % a)
    problems += wait_reader_problems(img)
    problems += ["%s: %s" % (r["site"], r["evidence"]) for r in rows if r["class"] == "PROBLEM"]
    return rows, problems


def f7_sites():
    """the flag-group sites the REVIEWED F7 entries name"""
    return {int(x, 16) for why in (e[2] for e in REVIEWED.values() if e[0] == "F7")
            for x in re.findall(r"\b(?:mulflag|gatefn|count) ([0-9A-F]{6})\b", why)} | {ACTUATER}


def manifest_problems(manifest, rows=()):
    """Every flag site the survey names must be in the manifest, and every
    flag-group site of the manifest named by the survey (the REVIEWED F7
    entries' sites, and the stores of the waits among `rows`)."""
    listed = {m[2] for m in manifest if m[0] == "flag"}
    named = f7_sites() | {m[2] for m in mulstore_rows(rows)}
    out = ["the survey names flag site %X, which the manifest does not hold" % a
           for a in sorted(named - listed)]
    out += ["manifest flag site %X is named by no survey entry" % a
            for a in sorted(listed - named)]
    return out


def main():
    rows, problems = audit()
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = collections.Counter((r["what"], r["class"]) for r in rows)
    print("flag reads: %d references: %s" % (
        len(rows), ", ".join("%s %s %d" % (w, c, n) for (w, c), n in sorted(by.items()))))
    import gen_world_anims
    problems += manifest_problems(gen_world_anims.MANIFEST + mulstore_rows(rows), rows)
    for p in problems:
        print("PROBLEM " + p)
    print("%d problems" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
