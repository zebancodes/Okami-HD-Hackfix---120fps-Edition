#!/usr/bin/env python3
"""Generate src/brush_watch.h: the addresses the Rejuvenation watch reads.

Rejuvenation (the Celestial Brush technique that restores a missing part of an
object) is judged on the CPU, from a mask the GPU renders. The chain, all in
main.dll:

  * the brush object (main+8909C0) is updated once per tick by the dispatcher
    (UPDATE). Its state (+0xC80) runs 0 idle, 1 open, 2 draw, 3 evaluate,
    4-5 countdowns, 6 close. While you draw, a restorable object in view offers
    itself as the candidate (+0xCB8); the first stroke asks the renderer for
    the target mask (a one-tick request, +0xCC8), and a stroke that touches the
    mask engages the target (+0xC84 = the candidate);
  * the renderer (CAPTURE) draws the missing part into GPU render target 10,
    copies it to a CPU-readable texture of the target's own format, maps it and
    samples it on a 256x224 grid, reading each sample as a 4-byte BGRA pixel:
    non-black = mask. The result is kept in the saved mask (SAVED);
  * in state 3 the evaluation (EVAL) copies SAVED to mask 0, paints each
    stroke point into the ink canvas as a square of half-width size/4 at
    (x/2, y/2) (RAST), and counts mask pixels and inked mask pixels (COVER):
    ratio = inked / (masked * 0.4), and a ratio of at least 1 restores it
    (RESULT, BITS).

This generator does not search for new sites. The addresses were found by
reading the decompilation, and every one is checked
here against the instructions that use it, starting from facts that do not
depend on them: the brush init loads "etc/cock/fude_000.dds", the coverage
check multiplies by the double 0.4, the dispatcher and the renderer pass the
brush object in rcx. Any mismatch fails the run, and the runtime also refuses
a main.dll whose SHA1 differs.

    .venv/Scripts/python tools/gen_brush_watch.py
"""
import hashlib
import os

import struct
import sys

import capstone
from capstone import x86_const as X
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import xrefs  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT_H = os.path.join(ROOT, "src", "brush_watch.h")
BASE = 0x180000000
CANVAS_W, CANVAS_H = 0x100, 0xE0  # the ink canvas and masks: x * 0xE0 + y


class Fail(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Fail(msg)


def main():
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    sha = hashlib.sha1(raw).hexdigest()
    pe = pefile.PE(data=raw)
    need(pe.OPTIONAL_HEADER.ImageBase == BASE, "unexpected image base")
    img = pe.get_memory_mapped_image()
    funcs = sorted((e.struct.BeginAddress, e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    # a chunk split off a function (chained unwind info) belongs to its parent
    parent = {}
    for e in pe.DIRECTORY_ENTRY_EXCEPTION:
        u = e.unwindinfo
        if u is not None and u.Flags & 4 and isinstance(getattr(u, "FunctionEntry", None), int):
            parent[e.struct.BeginAddress] = u.FunctionEntry
    ins = xrefs.cached_insns("main.dll")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def fn_of(rva):
        for lo, hi in funcs:
            if lo <= rva < hi:
                while lo in parent:
                    lo = parent[lo]
                    hi = next(h for low, h in funcs if low == lo)
                return lo, hi
        return None

    def body(rva, limit=0x3000):
        """Straight decode of a function and every chunk chained to it (or of a
        leaf, which has no .pdata entry, up to its first ret)."""
        fn = fn_of(rva)
        if not fn:
            out = []
            for i in md.disasm(img[rva:rva + limit], BASE + rva):
                out.append(i)
                if i.mnemonic == "ret":
                    break
            return out
        ranges = [fn]
        for lo, hi in funcs:
            top = lo
            while top in parent:
                top = parent[top]
            if top == fn[0] and lo != fn[0]:
                ranges.append((lo, hi))
        out = []
        for lo, hi in sorted(ranges):
            out += list(md.disasm(img[lo:hi], BASE + lo))
        return out

    def rip(i):
        for op in i.operands:
            if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
                return i.address + i.size + op.mem.disp - BASE
        return None

    def mem_disp(i, n=0):
        return i.operands[n].mem.disp

    def calls_after_lea_rcx(target_fn, lo, hi):
        """rip targets of `lea rcx, [rip+X]` directly before a call to target_fn."""
        out = []
        for k in range(len(ins) - 1):
            a, m, o, _s = ins[k]
            if not lo <= a - BASE < hi or m != "lea" or not o.startswith("rcx, [rip"):
                continue
            a2, m2, o2, _s2 = ins[k + 1]
            if m2 == "call" and o2 == hex(BASE + target_fn):
                out.append((a - BASE, xrefs.rip_target(ins[k]) - BASE))
        return out

    evidence = []
    cited = {}

    def cite(*items):
        """Instructions the runtime checks byte for byte before it reads anything."""
        for it in items:
            if isinstance(it, int):
                it = next(md.disasm(img[it:it + 16], BASE + it))
            cited[it.address - BASE] = bytes(it.bytes)

    # -- the brush object: what the init that loads the brush texture is given
    s = img.find(b"etc/cock/fude_000.dds\0")
    need(s > 0, "no brush texture string")
    refs = [a - BASE for a, _m, _o, _s in ins if xrefs.rip_target((a, _m, _o, _s)) == BASE + s]
    need(len(refs) == 1, "the brush texture is referenced %d times" % len(refs))
    init = fn_of(refs[0])[0]
    objs = calls_after_lea_rcx(init, 0, 1 << 32)
    need(len({o for _a, o in objs}) == 1, "the brush init is given %r" % objs)
    brush = objs[0][1]
    cite(objs[0][0], objs[0][0] + 7)
    evidence.append(("brush object", brush, "lea rcx before the call to the brush init main+%X at "
                     "main+%X (the init loads etc/cock/fude_000.dds)" % (init, objs[0][0])))

    # -- UPDATE: the one function the dispatcher calls with the brush object;
    # its state is the switch index: mov eax, [reg+K]; dec eax; ...; cmp eax, 5; ja
    targets = set()
    for k in range(len(ins) - 1):
        a, m, o, _s = ins[k]
        if m == "lea" and o.startswith("rcx, [rip") and xrefs.rip_target(ins[k]) == BASE + brush:
            a2, m2, o2, _s2 = ins[k + 1]
            if m2 == "call" and o2.startswith("0x"):
                targets.add(int(o2, 16) - BASE)
    dispatch_calls = [t for t in targets if any(
        c[1] == brush for c in calls_after_lea_rcx(t, 0x4BA500, 0x4BAC00))]
    need(len(dispatch_calls) == 1, "the dispatcher calls %r with the brush object" % dispatch_calls)
    update = dispatch_calls[0]
    state_off = None
    ub = body(update)
    for n, i in enumerate(ub[:-8]):
        if i.mnemonic == "mov" and i.op_str.startswith("eax, dword ptr [r") and \
                ub[n + 1].mnemonic == "dec" and ub[n + 1].op_str == "eax":
            tail = ub[n + 2:n + 10]
            if any(t.mnemonic == "cmp" and t.op_str == "eax, 5" for t in tail) and \
                    any(t.mnemonic == "ja" for t in tail):
                state_off = mem_disp(i, 1)
                cite(i, ub[n + 1])
                evidence.append(("state", state_off, "switch index at main+%X in the update main+%X "
                                 "(mov eax; dec eax; cmp eax, 5; ja: states 1-6, 0 the default)"
                                 % (i.address - BASE, update)))
                break
    need(state_off is not None, "no state switch in the update main+%X" % update)

    # the stroke count: cmp [rip+X], 0x1f; jge in the update (at most 30 strokes)
    strokes = None
    for n, i in enumerate(ub[:-1]):
        if i.mnemonic == "cmp" and i.op_str.endswith(", 0x1f") and rip(i) and ub[n + 1].mnemonic == "jge":
            strokes = rip(i)
            cite(i)
            evidence.append(("stroke count", strokes, "cmp [rip], 0x1f; jge at main+%X"
                             % (i.address - BASE)))
            break
    need(strokes is not None, "no stroke-count limit in the update")

    # -- COVER: the function that scales by the double 0.4, tests mask bit 0,
    # ORs a success bit into a global, and treats map 0x312 apart
    covers = []
    for lo, hi in funcs:
        if hi - lo > 0x400 or lo in parent:
            continue
        b = body(lo)
        if any(i.mnemonic == "mulsd" and rip(i) and struct.unpack_from("<d", img, rip(i))[0] == 0.4
               for i in b) and any(i.mnemonic == "test" and i.op_str.startswith("byte ptr [r")
                                   and i.op_str.endswith("], 1") for i in b) and \
                any(i.mnemonic == "or" and rip(i) and i.op_str.startswith("dword ptr [rip") for i in b) and \
                any(i.mnemonic == "mov" and i.op_str == "eax, 0x312" for i in b):
            covers.append((lo, b))
    need(len(covers) == 1, "expected one coverage check, found %d" % len(covers))
    cover, cb = covers[0]
    need_rva = next(rip(i) for i in cb if i.mnemonic == "mulsd")
    ratio = [rip(i) for i in cb if i.mnemonic == "movss" and rip(i) and i.op_str.startswith("dword ptr [rip")]
    need(len(set(ratio)) == 1, "the coverage check stores %r" % ratio)
    ratio = ratio[0]
    result = [rip(i) for i in cb if i.mnemonic == "mov" and rip(i) and i.op_str.startswith("dword ptr [rip")]
    bits = [rip(i) for i in cb if i.mnemonic == "or" and rip(i) and i.op_str.startswith("dword ptr [rip")]
    need(len(set(result)) == 1 and len(bits) == 1, "result %r, bits %r" % (result, bits))
    result, bits = result[0], bits[0]
    mapv = [rip(cb[n]) for n in range(1, len(cb)) if cb[n].mnemonic == "cmp" and rip(cb[n])
            and cb[n - 1].mnemonic == "mov" and cb[n - 1].op_str == "eax, 0x312"]
    need(len(mapv) == 1, "no map compare in the coverage check")
    mapv = mapv[0]
    masks = [rip(i) for i in cb if i.mnemonic == "lea" and rip(i)]
    cite(*[i for i in cb if rip(i) in (need_rva, ratio, result, bits, mapv)])
    need(len(masks) == 2, "the coverage check loads %r" % masks)
    evidence += [("coverage check", cover, "mulsd by the double 0.4 at main+%X; test byte [mask], 1"
                  % need_rva),
                 ("ratio", ratio, "the one float the coverage check stores"),
                 ("result", result, "the dword it sets to the mask's index + 1 on success"),
                 ("success bits", bits, "the dword it ORs 1 << index into"),
                 ("map id", mapv, "compared with 0x312 (the one map with seven masks)")]

    # -- EVAL: the caller of COVER, which tests the engaged target and the candidate
    callers = {fn_of(a - BASE)[0] for a, m, o, _s in ins if m == "call" and o == hex(BASE + cover)}
    need(len(callers) == 1, "the coverage check has callers %r" % callers)
    ev = callers.pop()
    eb = body(ev)
    need(any(i.mnemonic == "mov" and rip(i) == bits and i.op_str.endswith(", edi") for i in eb[:8]),
         "the evaluation does not clear the success bits first")
    engaged = [mem_disp(eb[n], 1) for n in range(len(eb) - 3)
               if eb[n].mnemonic == "mov" and eb[n].op_str.startswith("eax, dword ptr [rcx + ")
               and any(t.mnemonic == "js" for t in eb[n + 1:n + 5])]
    need(len(engaged) == 1, "no engaged-target test in the evaluation")
    engaged = engaged[0]
    cand = [mem_disp(i) for i in eb if i.mnemonic == "cmp" and i.op_str.startswith("dword ptr [rcx + ")
            and i.op_str.endswith(", 0x22")]
    need(len(cand) == 1, "no candidate compare in the evaluation")
    cand = cand[0]
    # memcpy(SAVED, INK, 0xE000): mov r8d, 0xe000; lea rdx, [INK]; lea rcx, [SAVED]
    saved = ink = None
    for n in range(len(eb) - 2):
        if eb[n].mnemonic == "mov" and eb[n].op_str == "r8d, 0xe000" and \
                eb[n + 1].op_str.startswith("rdx, [rip") and eb[n + 2].op_str.startswith("rcx, [rip"):
            ink, saved = rip(eb[n + 1]), rip(eb[n + 2])
            break
    need(saved is not None, "no saved-mask copy in the evaluation")
    need(ink in masks and masks.count(ink) == 1, "the coverage check's canvas is not the evaluation's")
    cite(*[i for i in eb if rip(i) in (bits, saved, ink)])
    cite(*[i for i in eb if i.mnemonic in ("mov", "cmp") and i.op_str.startswith(("eax, dword ptr [rcx + ",
                                                                                 "dword ptr [rcx + "))
           and i.operands and any(op.type == X.X86_OP_MEM and op.mem.disp in (engaged, cand)
                                  for op in i.operands)])
    evidence += [("evaluation", ev, "the only caller of the coverage check"),
                 ("engaged target", engaged, "mov eax, [rcx+K]; ...; js (returns at once if < 0)"),
                 ("candidate", cand, "cmp [rcx+K], 0x22 (one special target)"),
                 ("saved mask", saved, "memcpy(saved, ink, 0xE000) in the evaluation"),
                 ("ink canvas", ink, "the same copy's source; the coverage check reads it")]

    # -- RAST: the evaluation's callee that ORs 1 into the ink canvas per point
    rasts = []
    for i in eb:
        if i.mnemonic == "call" and i.operands[0].type == X.X86_OP_IMM:
            t = i.operands[0].imm - BASE
            tb = body(t)
            if any(rip(j) == ink and j.mnemonic == "lea" for j in tb) and \
                    any(j.mnemonic == "or" and j.op_str.startswith("byte ptr [r") for j in tb):
                rasts.append((t, tb))
    need(len({r[0] for r in rasts}) == 1, "the evaluation's rasterizer: %r" % [r[0] for r in rasts])
    rast, rb = rasts[0]
    npts = [rip(i) for i in rb[:4] if i.mnemonic == "mov" and i.op_str.startswith("eax, dword ptr [rip")]
    need(len(npts) == 1, "the rasterizer's point count")
    npts = npts[0]
    px = [(i.op_str.split(",")[0], rip(i)) for i in rb if i.mnemonic == "lea" and rip(i) and rip(i) != ink]
    need(len(px) == 1, "the rasterizer's point base: %r" % px)
    preg, px = px[0]
    flag = [mem_disp(i) for i in rb if i.mnemonic == "cmp" and i.op_str.startswith("byte ptr [%s" % preg)
            and i.op_str.endswith(", 0")]
    cvt = [mem_disp(i, 1) for i in rb if i.mnemonic == "cvttss2si"]
    stride = [i.operands[1].imm for i in rb if i.mnemonic == "add" and i.op_str.startswith(preg + ", ")]
    sar = [i.operands[1].imm for i in rb if i.mnemonic == "sar"]
    need(flag == [-4] and sorted(cvt) == [0, 4, 8] and stride == [0xB0] and sorted(sar) == [1, 1, 2],
         "point layout: flag %r, floats %r, stride %r, shifts %r" % (flag, cvt, stride, sar))
    need(any(i.mnemonic == "cmp" and i.op_str.endswith(", 0xdf") for i in rb) and
         any(i.mnemonic == "cmp" and i.op_str.endswith(", 0xff") for i in rb) and
         any(i.mnemonic == "add" and i.op_str.endswith(", 0xe0") for i in rb),
         "the canvas is not 256 x 224, x-major")
    cite(*[i for i in rb if (i.mnemonic in ("mov", "lea") and rip(i) in (npts, px)) or
           i.mnemonic == "cvttss2si" or (i.mnemonic == "cmp" and i.op_str.startswith("byte ptr [")) or
           (i.mnemonic == "add" and i.op_str.startswith(preg + ", "))])
    evidence += [("rasterizer", rast, "the evaluation's callee that ORs 1 into the ink canvas"),
                 ("points", px - 4, "records of 0xB0: flag byte, then x, y, size floats; a point "
                  "inks a square of half-width (int)size >> 2 at ((int)x >> 1, (int)y >> 1)"),
                 ("point count", npts, "the number of records the rasterizer inks")]

    # -- CAPTURE and its request: the renderer calls REQ(brush) then CAPTURE
    req_off = capture = None
    for k in range(len(ins) - 6):
        a, m, o, _s = ins[k]
        if m == "lea" and o.startswith("rcx, [rip") and xrefs.rip_target(ins[k]) == BASE + brush and \
                ins[k + 1][1] == "call" and ins[k + 1][2].startswith("0x"):
            getter = int(ins[k + 1][2], 16) - BASE
            gb = body(getter, 0x20)
            if len(gb) == 2 and gb[0].op_str.startswith("eax, dword ptr [rcx + ") and gb[1].mnemonic == "ret":
                tail = ins[k + 2:k + 7]
                nxt = [int(t[2], 16) - BASE for t in tail if t[1] == "call" and t[2].startswith("0x")]
                if nxt and any(rip(i) == saved for i in body(nxt[0])):
                    req_off, capture = mem_disp(gb[0], 1), nxt[0]
                    cite(gb[0], a - BASE, ins[k + 1][0] - BASE)
                    evidence.append(("capture request", req_off, "getter main+%X, called by the renderer "
                                     "at main+%X before the capture" % (getter, a - BASE)))
                    evidence.append(("capture", capture, "renders the target to RT 10, copies it to a "
                                     "texture of its own format, maps it, fills the saved mask"))
                    break
    need(req_off is not None, "no capture request in the renderer")
    need(len({brush, state_off, engaged, cand, req_off}) == 5, "offsets collide")

    lines = ["// Generated by tools/gen_brush_watch.py -- do not edit.",
             "// What the Rejuvenation watch reads (brush_watch_runtime.h). Each address is",
             "// checked against the instructions that use it; the evidence is below.",
             "#pragma once", "#include <cstdint>", "",
             '#define BRUSH_WATCH_MAIN_SHA1 "%s"' % sha,
             "static const uint32_t kBrushRva = 0x%X;            // the brush object" % brush,
             "static const uint32_t kBrushStateOff = 0x%X;       // 0 idle .. 3 evaluate .. 6 close"
             % state_off,
             "static const uint32_t kBrushEngagedOff = 0x%X;     // the engaged target, -1 none" % engaged,
             "static const uint32_t kBrushCandidateOff = 0x%X;   // the target on offer, -1 none" % cand,
             "static const uint32_t kBrushRequestOff = 0x%X;     // mask capture requested (one tick)"
             % req_off,
             "static const uint32_t kBrushSavedMaskRva = 0x%X;  // 256 x 224 bytes, x * 224 + y" % saved,
             "static const uint32_t kBrushPointsRva = 0x%X;     // records of kBrushPointSize" % (px - 4),
             "static const uint32_t kBrushPointSize = 0xB0;      // +0 flag, +4 x, +8 y, +0xC size",
             "static const uint32_t kBrushPointCountRva = 0x%X; // records the evaluation inks" % npts,
             "static const uint32_t kBrushStrokeCountRva = 0x%X;" % strokes,
             "static const uint32_t kBrushRatioRva = 0x%X;      // inked / (masked * 0.4)" % ratio,
             "static const uint32_t kBrushBitsRva = 0x%X;       // non-zero: restored" % bits,
             "static const uint32_t kBrushMapRva = 0x%X;        // a word; 0x312 has seven masks" % mapv,
             "static const double kBrushNeed = %r;" % struct.unpack_from("<d", img, need_rva)[0],
             "static const int kBrushCanvasW = %d, kBrushCanvasH = %d;" % (CANVAS_W, CANVAS_H), "",
             "// Every instruction below is checked byte for byte before the watch starts.",
             "struct BrushEvidence { uint32_t rva; uint8_t len; uint8_t bytes[15]; };",
             "static const BrushEvidence kBrushEvidence[] = {"]
    lines += ["    {0x%X, %d, {%s}}," % (r, len(b), ", ".join("0x%02X" % x for x in b))
              for r, b in sorted(cited.items())]
    lines += ["};", "", "// Evidence:"]
    lines += ["//   %-16s %-12s %s" % (what, ("+0x%X" if v < 0x10000 else "main+%X") % v, why)
              for what, v, why in evidence]
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    for what, v, why in evidence:
        print("%-16s %-12s %s" % (what, ("+0x%X" if v < 0x10000 else "main+%X") % v, why))
    print("%d instructions cited" % len(cited))
    print("wrote %s; sha1 %s" % (os.path.relpath(OUT_H, ROOT), sha))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as e:
        sys.exit("gen_brush_watch: %s" % e)
