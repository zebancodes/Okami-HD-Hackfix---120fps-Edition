#!/usr/bin/env python3
"""Prove the draw-distance option offline (dinput8_proxy.cpp, kDrawDistanceSites).

A placed model (cModel and every class under it) is drawn while its view
depth is at most its limit +D72 (a signed word), and fades out over the last
+D74 of that. DrawDistance = k multiplies the limit at the eight places that
decide drawing, fading and updating; the source says why the ten other
readers stay as shipped.

1. Census: every instruction in .text that reads a memory operand covering
   +D72 (any base but rip and rsp), or takes the address of the block around
   it, is one of the readers read by hand below, and the eight scaled are the
   source's table, in its order, with its original bytes. No branch, switch
   table destination or code address in data lands inside a site past its
   first byte (tools/gen_tracer.global_pass): a jump there would enter the
   middle of the detour's `jmp rel32`.
2. Calls the DLL's OkamiDrawDistanceSelfTest at k = 3 (main.dll mapped, not
   run; the real install). Each site must hold a jump to its stub and NOP
   padding, and each stub must decode to what the source's comment says: the
   load as shipped and an imul by the factor slot (movzx's capped at 0x7FFF),
   or push rcx; movsx ecx; imul ecx; the clamp to [-0x8000, 0x7FFF]; cmp ax,
   cx; pop rcx; then a jump back to the next instruction.
3. Flags: after each load site, on the straight line, an instruction writing
   all six arithmetic flags comes before any that reads one (the stub's imul
   leaves them different from the shipped load's).
4. Unicorn: each site patched (through its stub, back to the next
   instruction) against the original with only the documented change, for
   random registers, limits (0, 1000, 5000, 32767, negative, random) and k in
   1..6: every register equal; for the compares the six flags equal too. For
   the loads: r32 = sign- or zero-extended limit times k (the movzx's capped
   at 0x7FFF); for the compares: the shipped compare of ax against the limit
   times k, clamped to a signed word.

    .venv/Scripts/python tools/verify_draw_distance.py
    --break factor   the reference uses k + 1 and must FAIL
"""
import argparse
import ctypes
import os
import random
import re
import shutil
import struct
import sys
import tempfile

import capstone
from capstone import x86_const as X
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL
from unicorn import x86_const as U

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.dirname(HERE)
PROXY = os.path.join(ROOT, "src", "dinput8_proxy.cpp")
LIMIT = 0xD72
PAGE = 0x1000
OBJ = 0x10000000
STACK = 0x7FF000000000
FLAGS = (0x1, 0x4, 0x10, 0x40, 0x80, 0x800)       # CF PF AF ZF SF OF
GPRS = ("RAX", "RBX", "RCX", "RDX", "RSI", "RDI", "RBP", "R8", "R9", "R10", "R11", "R12",
        "R13", "R14", "R15")
# the readers left as shipped, read by hand (dinput8_proxy.cpp, "Draw distance")
KEPT = {
    0x27324C: "a child copies its parent's limit (scaling the read would square k)",
    0x3899AA: "a child copies its parent's limit",
    0x3903F3: "a child copies its parent's limit",
    0x5AB731: "a floor: the limit raised to 2000",
    0x207F21: "the fade width's setup: +D74 = 150 where the limit is 1000 or more",
    0x21BF18: "an ambient sound's timer, run while in range",
    0x21C04F: "an ambient sound's timer, run while in range",
    0x22C673: "a radius handed to 493980 with a position (+1110): an activity range",
    0x22DA94: "the same radius",
    0x2FE54C: "a horizontal distance at which a sound is stopped (198670)",
}
# the address of +D70 taken in classes where +D70 is a cVec (constructor,
# copy, assign): not cModel's depth word and limit
VECTORS = {0x167B50, 0x167E4C, 0x168D49}


def table():
    src = open(PROXY, encoding="utf-8").read()
    body = re.search(r"kDrawDistanceSites\[\]\[2\] = \{(.*?)\n\};", src, re.S).group(1)
    sites = [(int(a, 16), int(b, 16)) for a, b in
             re.findall(r"\{0x([0-9A-F]+), 0x([0-9A-F]+)\}", body)]
    body = re.search(r"kDrawDistanceOrig\[\]\[8\] = \{(.*?)\n\};", src, re.S).group(1)
    orig = [bytes(int(x, 16) for x in re.findall(r"0x([0-9A-F]{2})", row))
            for row in re.findall(r"\{([^{}]+)\}", body)]
    return sites, orig


def census(img, secs):
    """[(rva, text)] of every read of a memory operand covering +D72, and
    every lea of an address within 16 bytes below it"""
    lo, hi = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    out = []
    pos = lo
    while pos < hi:
        end = min(hi, pos + 0x10000)
        last = pos
        for i in md.disasm(bytes(img[pos:end + 16]), pos):
            if i.address >= end:
                break
            last = i.address + i.size
            for n, op in enumerate(i.operands):
                if op.type != X.X86_OP_MEM or op.mem.base in (0, X.X86_REG_RIP, X.X86_REG_RSP):
                    continue
                d = op.mem.disp
                if i.mnemonic == "lea":
                    if LIMIT - 16 < d <= LIMIT:
                        out.append((i.address, "%s %s" % (i.mnemonic, i.op_str)))
                    continue
                if not d <= LIMIT < d + max(op.size, 1) and not d <= LIMIT + 1 < d + max(op.size, 1):
                    continue
                if not op.access & capstone.CS_AC_READ:
                    continue
                if n == 0 and i.mnemonic.startswith("mov"):
                    continue                    # a plain store (capstone flags some as reads)
                out.append((i.address, "%s %s" % (i.mnemonic, i.op_str)))
        pos = last if last > pos else pos + 1
    return out


def flags_dead_after(md, img, at):
    """None if, on the straight line from `at`, an instruction writing all six
    arithmetic flags comes before any reading one"""
    md.detail = True
    for i in md.disasm(bytes(img[at:at + 64]), at):
        ef = i.eflags
        reads = ef & (X.X86_EFLAGS_TEST_CF | X.X86_EFLAGS_TEST_PF | X.X86_EFLAGS_TEST_AF |
                      X.X86_EFLAGS_TEST_ZF | X.X86_EFLAGS_TEST_SF | X.X86_EFLAGS_TEST_OF)
        if reads:
            return "%X %s %s reads a flag first" % (i.address, i.mnemonic, i.op_str)
        writes = [ef & (getattr(X, "X86_EFLAGS_MODIFY_" + f) | getattr(X, "X86_EFLAGS_RESET_" + f, 0) |
                        getattr(X, "X86_EFLAGS_SET_" + f, 0) | getattr(X, "X86_EFLAGS_UNDEFINED_" + f, 0))
                  for f in ("CF", "PF", "AF", "ZF", "SF", "OF")]
        if all(writes):
            return None
        if i.mnemonic.startswith(("j", "call", "ret", "loop")):
            return "%X %s leaves the line before the flags are written" % (i.address, i.mnemonic)
    return "no flag writer within 64 bytes of %X" % at


def sx16(v):
    return v - 0x10000 if v & 0x8000 else v


def emu(image_base, image, extra=()):
    mu = Uc(UC_ARCH_X86, UC_MODE_64)
    size = (len(image) + PAGE - 1) & ~(PAGE - 1)
    mu.mem_map(image_base, size, UC_PROT_ALL)
    mu.mem_write(image_base, bytes(image))
    for base, data in extra:
        mu.mem_map(base, (len(data) + PAGE - 1) & ~(PAGE - 1), UC_PROT_ALL)
        mu.mem_write(base, bytes(data))
    mu.mem_map(OBJ, 0x4000, UC_PROT_ALL)
    mu.mem_map(STACK - 0x10000, 0x10000, UC_PROT_ALL)
    return mu


def run(mu, start, stop, regs, limit):
    mu.mem_write(OBJ + LIMIT, struct.pack("<H", limit & 0xFFFF))
    for r, v in regs.items():
        mu.reg_write(getattr(U, "UC_X86_REG_" + r), v)
    mu.reg_write(U.UC_X86_REG_RSP, STACK - 0x1000)
    mu.reg_write(U.UC_X86_REG_EFLAGS, 0x202)
    mu.emu_start(start, stop, count=64)
    return ({r: mu.reg_read(getattr(U, "UC_X86_REG_" + r)) for r in GPRS + ("RSP",)},
            mu.reg_read(U.UC_X86_REG_EFLAGS),
            struct.unpack("<H", mu.mem_read(OBJ + LIMIT, 2))[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--break", dest="broken", choices=("factor",))
    args = ap.parse_args()
    problems = []
    sites, orig = table()
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    img = bytearray(pe.get_memory_mapped_image())
    secs = {s.Name.rstrip(b"\0").decode(): (s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize)
            for s in pe.sections}
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    # 1. every reader of the limit, read by hand
    scaled = [s for s, _r in sites]
    found = census(img, secs)
    known = set(scaled) | set(KEPT) | VECTORS
    for a, text in found:
        if a not in known:
            problems.append("%X %s reads +D72 and was not read by hand" % (a, text))
    missing = known - {a for a, _t in found}
    for a in sorted(missing):
        problems.append("%X was read by hand but the census does not find it" % a)
    for (site, resume), o in zip(sites, orig):
        if resume - site != len(o) or bytes(img[site:resume]) != o:
            problems.append("main+%X: the table's bytes are not the game's instruction" % site)
    import gen_tracer as tr
    lo, hi = secs[".text"]
    starts, targets, switch, _tables = tr.global_pass(img, lo, hi)
    ways_in = targets | switch | tr.data_references(img, secs, lo, hi, starts)
    for site, resume in sites:
        inside = sorted(t for t in ways_in if site < t < resume)
        if inside:
            problems.append("main+%X: control can arrive at %s, inside the detour" % (
                site, ", ".join("%X" % t for t in inside)))
    print("1. census: %d reads of +D72 (and addresses near it) in .text: %d scaled, %d kept, "
          "%d another class's vector; no way into a site past its first byte" % (
              len(found), len(scaled), len(KEPT), len(VECTORS)))

    # 2. the DLL's own install at k = 3, and its bytes
    work = tempfile.mkdtemp(prefix="okami_draw_distance_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    fn = ctypes.WinDLL(dll).OkamiDrawDistanceSelfTest
    fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int], ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"), 3)
    rep = open(os.path.join(work, "report.txt")).read()
    if rc:
        print(rep)
        sys.exit("DLL self-test failed (rc %d)" % rc)
    vals = dict(ln.split(None, 1) for ln in rep.splitlines() if len(ln.split()) == 2)
    main_base, cave_base = int(vals["main"], 16), int(vals["cave"], 16)
    cave = bytearray(open(os.path.join(work, "cave.bin"), "rb").read())
    patched = open(os.path.join(work, "sites.bin"), "rb").read()
    if struct.unpack_from("<i", cave, 0)[0] != 3:
        problems.append("the factor slot holds %d, not 3" % struct.unpack_from("<i", cave, 0)[0])
    factor_slot = cave_base
    for i, ((site, resume), o) in enumerate(zip(sites, orig)):
        n = resume - site
        got = patched[8 * i:8 * i + n]
        if got[0] != 0xE9 or got[5:] != b"\x90" * (n - 5):
            problems.append("main+%X is not a jump and NOP padding" % site)
            continue
        stub = main_base + site + 5 + struct.unpack_from("<i", got, 1)[0]
        ins = list(md.disasm(bytes(cave[stub - cave_base:stub - cave_base + 96]), stub))
        texts = []
        for j in ins:
            op = next((x for x in j.operands if x.type == X.X86_OP_MEM), None)
            t = "%s %s" % (j.mnemonic, j.op_str)
            if op is not None and op.mem.base == X.X86_REG_RIP:
                target = j.address + j.size + op.mem.disp
                t = re.sub(r"\[rip [+-] 0x[0-9a-f]+\]", "[k]" if target == factor_slot else
                           "[%X]" % target, t)
            if j.mnemonic.startswith("j") and j.operands[0].type == X.X86_OP_IMM:
                target = j.operands[0].imm
                t = "%s %s" % (j.mnemonic, "back" if target == main_base + resume else
                               "+%d" % (target - j.address - j.size))
            texts.append(t)
            if j.mnemonic == "jmp" and t == "jmp back":
                break
        first = next(md.disasm(o, site))
        orig_text = "%s %s" % (first.mnemonic, first.op_str)
        if o[:2] == b"\x66\x3b":
            mem = orig_text.split(", ", 1)[1]
            want = ["push rcx", "movsx ecx, %s" % mem, "imul ecx, dword ptr [k]",
                    "cmp ecx, 0x7fff", "jle +5", "mov ecx, 0x7fff",
                    "cmp ecx, 0xffff8000", "jge +5", "mov ecx, 0xffff8000",
                    "cmp ax, cx", "pop rcx", "jmp back"]
        else:
            reg = first.reg_name(first.operands[0].reg)
            want = [orig_text, "imul %s, dword ptr [k]" % reg]
            if first.mnemonic == "movzx":
                want += ["cmp eax, 0x7fff", "jbe +5", "mov eax, 0x7fff"]
            want += ["jmp back"]
        if texts != want:
            problems.append("stub for %X decodes to %s, want %s" % (site, texts, want))
    print("2. DLL self-test at k = 3: %s of %d sites installed; jumps, padding and stubs "
          "decoded" % (vals.get("done"), len(sites)))

    # 3. the flags a load stub leaves
    for (site, resume), o in zip(sites, orig):
        if o[:2] == b"\x66\x3b":
            continue
        why = flags_dead_after(md, img, resume)
        if why:
            problems.append("after main+%X: %s" % (site, why))
    print("3. flags: dead after each of the %d load sites" %
          sum(1 for o in orig if o[:2] != b"\x66\x3b"))

    # 4. every site under Unicorn, patched against the original
    im = bytearray(img)
    for i, (site, resume) in enumerate(sites):
        im[site:resume] = patched[8 * i:8 * i + resume - site]
    rnd = random.Random(11)
    runs = 0
    limits = [0, 1, 100, 1000, 5000, 32767, -1, -100, -32768, 0x7FFF]
    for (site, resume), o in zip(sites, orig):
        first = next(md.disasm(o, site))
        mem = next(x for x in first.operands if x.type == X.X86_OP_MEM)
        base = first.reg_name(mem.mem.base).upper()
        compare = o[:2] == b"\x66\x3b"
        for k in (1, 2, 3, 4, 5, 6):
            cave[0:4] = struct.pack("<i", k)
            patched_mu = emu(main_base, im, [(cave_base, cave)])
            orig_mu = emu(main_base, img)
            kk = k + 1 if args.broken == "factor" else k
            for trial in range(24):
                limit = limits[trial] if trial < len(limits) else rnd.randrange(-32768, 32768)
                regs = {r: rnd.getrandbits(64) for r in GPRS}
                regs[base] = OBJ
                got_regs, got_flags, got_mem = run(patched_mu, main_base + site,
                                                   main_base + resume, regs, limit)
                if compare:
                    v = max(-0x8000, min(0x7FFF, sx16(limit & 0xFFFF) * kk))
                    ref_regs, ref_flags, _m = run(orig_mu, main_base + site, main_base + resume,
                                                  regs, v)
                else:
                    ref_regs, ref_flags, _m = run(orig_mu, main_base + site, main_base + resume,
                                                  regs, limit)
                    reg = first.reg_name(first.operands[0].reg)
                    name = {"eax": "RAX", "ecx": "RCX", "edx": "RDX", "r8d": "R8",
                            "r9d": "R9"}[reg]
                    if first.mnemonic == "movzx":
                        v = min((limit & 0xFFFF) * kk, 0x7FFF)
                    else:
                        v = (sx16(limit & 0xFFFF) * kk) & 0xFFFFFFFF
                    ref_regs[name] = v
                runs += 1
                bad = [r for r in GPRS + ("RSP",) if got_regs[r] != ref_regs[r]]
                if compare:
                    bad += ["flag %X" % f for f in FLAGS if (got_flags ^ ref_flags) & f]
                if got_mem != limit & 0xFFFF:
                    bad.append("the limit in memory")
                if bad:
                    problems.append("main+%X k=%d limit %d: %s differ" % (site, k, limit,
                                                                         ", ".join(bad)))
                    break
    print("4. emulation: %d runs over the %d sites (k = 1..6)" % (runs, len(sites)))

    for p in problems[:20]:
        print("   PROBLEM " + p)
    print("\n%s" % ("FAILED: %d problems" % len(problems) if problems else "draw distance verified"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
