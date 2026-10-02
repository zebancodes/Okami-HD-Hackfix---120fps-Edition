#!/usr/bin/env python3
"""Generate the shadow mode byte table.

The mode byte main+B6AC45 is 2 in the stock 30 Hz configuration and 1 in the
60 Hz one, and the stock game switches it: the options pages, the memory-card
screens, the inside of the pause menu and the title run at 60 Hz. The patch
pins it to 1 (the fast configuration, 60 or 120 fps), which loses which context
the stock game would be in. This keeps that information: every instruction
that *maintains* the mode byte is retargeted at a private shadow byte, while
every instruction that *consumes* it keeps reading the real, pinned byte.

Maintaining means:

  write      `mov byte [mode], imm`             -- a context switch
  restore    `mov byte [mode], reg`             -- puts a saved value back
  save       a read whose value reaches a store that some restore reads back
             (the options controller's +0xA88, the memory card's +0xD8)

Nothing here trusts a list. Every instruction in .text that touches the byte is
found by a linear sweep in every encoding (rip-relative, image-base-relative,
wider accesses that overlap it, `lea` of a nearby address), and each one is
classified from Ghidra's high p-code:

  * a read is followed forward through copies, casts, extensions and phi nodes
    to every place its value ends up: a store (and at which object offset), a
    global, a call argument, a return, or a use that consumes it (a compare, an
    index, arithmetic). A read whose value reaches a store at an offset that a
    restore loads from is a save;
  * a restore is followed backward to the load it came from;
  * a read whose value escapes anywhere else (a store no restore reads, a call
    argument, a return) is not retargeted but is listed for review, and so is
    any read that a mode write is control dependent on in the same function.

The generator refuses to write the header if any reference is left
unclassified.

One writer names no address: flower_startup's memset of the whole frame block
writes 0 to the byte. The instructions at the call's return point are emitted
as a detour window (zero_windows), and the DLL's stub there writes that 0 to
the shadow and puts the pinned 1 back in the real byte. The memset only runs
in flower_startup(false), the engine start (flower_tick's reset path calls
flower_startup(true), which skips it), and that normally happens before the
DLL installs. The stub covers an install that wins that race: without it the
real byte would stay 0 -- the retargeted writer that follows now writes the
shadow -- and consumers that divide by the mode would divide by 0.

Outputs
  src/shadow_mode.h                 the retargeted instructions (checked in)
  docs/animation/shadow_mode.csv    every reference, its class and the evidence

    .venv/Scripts/python tools/gen_shadow_mode.py            # Ghidra, ~1 min
    .venv/Scripts/python tools/gen_shadow_mode.py --cached   # from the facts cache
"""
import argparse
import bisect
import collections
import csv
import hashlib
import json
import os
import re
import struct
import sys

try:
    import capstone
    from capstone import x86_const as X
    import pefile
except ImportError:
    sys.exit("needs pefile and capstone: pip install pefile capstone")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT_H = os.path.join(ROOT, "src", "shadow_mode.h")
OUT_CSV = os.path.join(ROOT, "docs", "animation", "shadow_mode.csv")
FACTS = os.path.expanduser(r"~\tools\shadow_mode_facts.json")

BASE = 0x180000000
MODE = 0xB6AC45
NEAR = (0xB6AC00, 0xB6AC60)   # the frame configuration block around it

KIND_WRITE, KIND_RESTORE, KIND_SAVE = 0, 1, 2
KIND_NAME = {KIND_WRITE: "write", KIND_RESTORE: "restore", KIND_SAVE: "save"}


# ---------------------------------------------------------------------------
# 1. every reference, every encoding (capstone)
# ---------------------------------------------------------------------------

def load_image():
    raw = open(os.path.join(GAME, "main.dll"), "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    img = bytes(pe.get_memory_mapped_image())
    secs = {s.Name.rstrip(b"\0").decode(): (s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize)
            for s in pe.sections}
    pd_lo, pd_hi = secs[".pdata"]
    funcs = []
    for off in range(pd_lo, pd_hi - 11, 12):
        b, e, _u = struct.unpack_from("<III", img, off)
        if b == 0 and e == 0:
            break
        funcs.append((b, e))
    funcs.sort()
    return img, secs, funcs, hashlib.sha1(raw).hexdigest()


def sweep(img, secs):
    """(references, problems): every instruction whose memory operand covers
    the mode byte, plus anything that could reach it by another route."""
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
                size = max(op.size, 1)
                if m.base == X.X86_REG_RIP:
                    t = ins.address + ins.size + m.disp
                    if ins.mnemonic == "lea":
                        if NEAR[0] <= t < NEAR[1]:
                            problems.append((ins.address, "lea of main+%X: a pointer into the"
                                             " frame configuration" % t))
                        continue
                    if t <= MODE < t + size:
                        refs.append(ins)
                        if size != 1:
                            problems.append((ins.address, "%d-byte access covering the mode"
                                             " byte" % size))
                elif NEAR[0] <= m.disp < NEAR[1]:
                    # image-base-relative: [reg + 0xB6AC45] with reg = image base
                    problems.append((ins.address, "displacement %X (image-base-relative?)"
                                     % m.disp))
        pos = last if last > pos else pos + 1
    # a pointer to the byte stored as data
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range(a & ~7, b - 8, 8):
            v = struct.unpack_from("<Q", img, off)[0]
            if BASE + NEAR[0] <= v < BASE + NEAR[1]:
                problems.append((off, "%s holds the address main+%X" % (name, v - BASE)))
        for off in range(a & ~3, b - 4, 4):
            v = struct.unpack_from("<I", img, off)[0]
            if v == MODE:
                problems.append((off, "%s holds the rva %X" % (name, v)))
    return refs, problems


def function_of(funcs, rva):
    """.pdata function holding rva; leaf functions have no entry, so fall back
    to the nearest preceding start (Ghidra's function is used where it matters)"""
    starts = [f[0] for f in funcs]
    k = bisect.bisect_right(starts, rva) - 1
    if k >= 0 and funcs[k][0] <= rva < funcs[k][1]:
        return funcs[k][0]
    return None


def function_end(funcs, rva):
    starts = [f[0] for f in funcs]
    k = bisect.bisect_right(starts, rva) - 1
    if k >= 0 and funcs[k][0] <= rva < funcs[k][1]:
        return funcs[k][1]
    return rva + 0x100


# A `lea reg, [rip+X]` into the frame configuration block is a pointer that can
# reach the mode byte at an offset, which no rip-relative scan sees. Each one is
# followed below; the ones whose pointer leaves the function are resolved here,
# by reading the code they reach, and checked by their bytes so a different
# build is refused rather than trusted.
POINTER_ROUTES = {
    # flower_tick hands &frameCounter to GXPacket::update as the argument of its
    # pacing callback, and that callback reads [arg+0x25] -- the mode byte -- as
    # the frame limiter's divisor. A consumer: it must keep seeing the real,
    # pinned byte or the engine would pace at the stock rate.
    0x4B63ED: ("consume", "limiter callback 4B52B0 reads [&frameCounter+0x25]",
               [(0x4B52B0, b"\x0F\xB6\x51\x25")]),
    # flower_startup(false) -- the engine start only; flower_tick's reset path
    # calls flower_startup(true), which skips this -- clears the whole block
    # with memset(&frameCounter, 0, 0x700), which writes
    # 0 to the mode byte. A writer with no displacement to retarget: the DLL
    # detours the call's return point (zero_windows below) to write the same 0
    # to the shadow and put the pinned 1 back in the real byte.
    0x4B6869: ("memset0", "memset(&frameCounter, 0, 0x700) at 4B6876",
               [(0x4B6867, b"\x33\xD2"), (0x4B6870, b"\x41\xB8\x00\x07\x00\x00"),
                (0x4B6876, b"\xE8")]),
    # the loader for etc/core*.dat returns buffer pointers through these two
    # 8-byte out-parameters (main+B6AC28 and B6AC30), which end before B6AC38
    0x4B541B: ("consume", "out-parameter &main+B6AC28 (8 bytes) for FUN_1801afc90",
               [(0x4B5426, b"\x48\x8D\x0D")]),
    0x4B5465: ("consume", "out-parameter &main+B6AC30 (8 bytes) for FUN_1801afe30",
               [(0x4B547C, b"\xE8")]),
    # a bit array at +0x6A4 sharing the block's base: the derived element
    # pointer is still in r8 at a call (and a tail jump) to one-parameter
    # functions. 481B20 and 4561D0 take only rcx, and the first thing each does
    # with an argument register is an import call (cVec::operator=, two
    # parameters; OSCompCalledThreadId, one) that clobbers r8, so r8 is never
    # passed on. callee_reads() cannot see through an import, hence the entry.
    0x4A4113: ("consume", "r8 left over at a call to one-parameter FUN_180481b20",
               [(0x4A41E1, b"\xE8\x3A\xD9\xFD\xFF"),
                (0x481B26, b"\x48\x8B\xD9\x48\x8D\x91\x90\x01\x00\x00")]),
    0x4A42DE: ("consume", "r8 left over at a tail jump to one-parameter FUN_1804561d0",
               [(0x4A4444, b"\xE9\x87\x1D\xFB\xFF"),
                (0x4561D6, b"\x48\x8B\xD9\x48\x83\xC1\x28")]),
}

ARG_REGS = {"rcx", "rdx", "r8", "r9", "ecx", "edx", "r8d", "r9d"}
REG64 = {}
for _r64, _alts in (("rax", "eax ax al"), ("rbx", "ebx bx bl"), ("rcx", "ecx cx cl"),
                    ("rdx", "edx dx dl"), ("rsi", "esi si sil"), ("rdi", "edi di dil"),
                    ("rbp", "ebp bp bpl"), ("rsp", "esp sp spl")):
    for _n in [_r64] + _alts.split():
        REG64[_n] = _r64
for _i in range(8, 16):
    for _s in ("", "d", "w", "b"):
        REG64["r%d%s" % (_i, _s)] = "r%d" % _i


def callee_reads(img, funcs, callee, reg):
    """Does the function at `callee` read `reg` before writing it? A linear
    scan of its body: the first instruction that touches the register decides
    (an import thunk or anything undecodable counts as a read)."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    end = function_end(funcs, callee)
    pos = callee
    for _ in range(400):
        if pos >= end:
            return False
        try:
            ins = next(md.disasm(img[pos:pos + 16], pos))
        except StopIteration:
            return True
        pos += ins.size
        regs_r, regs_w = ins.regs_access()
        if ins.mnemonic == "xor" and len(ins.operands) == 2 and                 ins.operands[0].type == X.X86_OP_REG and ins.operands[1].type == X.X86_OP_REG and                 ins.operands[0].reg == ins.operands[1].reg and                 REG64.get(ins.reg_name(ins.operands[0].reg)) == reg:
            return False
        if reg in {REG64.get(ins.reg_name(r)) for r in regs_r}:
            return True
        if reg in {REG64.get(ins.reg_name(r)) for r in regs_w}:
            return False
        if ins.mnemonic in ("ret", "call") or (ins.mnemonic == "jmp" and "ptr" in ins.op_str):
            return ins.mnemonic != "ret"
    return True


def pointer_routes(img, secs, funcs, problems):
    """Follow every lea into the block through the rest of its function.

    Each tracked register maps to (offset from the lea's target, indexed): a
    `lea r2, [r1 + idx*4 + d]` derives an indexed pointer, `add r1, imm` moves
    one. A fixed-offset access that covers the mode byte is a real reference,
    and so is an indexed one that a non-negative index could carry onto it;
    both are reported through `problems`, as is any other arithmetic on a
    tracked register. Returns {lea rva: (target, [(at, callee or "stored",
    registers)])} for the pointers that leave the function."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    escapes = {}
    for a, _why in [p for p in problems if p[1].startswith("lea of")]:
        ins0 = next(md.disasm(img[a:a + 16], a))
        target = a + ins0.size + ins0.operands[1].mem.disp
        tracked = {REG64[ins0.reg_name(ins0.operands[0].reg)]: (0, False)}
        start = function_of(funcs, a) or a
        end = function_end(funcs, a)
        pos = a + ins0.size
        esc = []
        while pos < end and tracked:
            try:
                ins = next(md.disasm(img[pos:pos + 16], pos))
            except StopIteration:
                break
            pos += ins.size
            derived = None
            for op in ins.operands:
                if op.type != X.X86_OP_MEM or not op.mem.base:
                    continue
                base = REG64.get(ins.reg_name(op.mem.base))
                if base not in tracked:
                    continue
                off, indexed = tracked[base]
                lo_ = target + off + op.mem.disp
                idx = bool(op.mem.index) or indexed
                if ins.mnemonic == "lea":
                    derived = (off + op.mem.disp, idx)
                    continue
                if not idx and lo_ <= MODE < lo_ + max(op.size, 1):
                    problems.append((ins.address, "reaches the mode byte through the"
                                     " pointer from %06X" % a))
                elif idx and lo_ <= MODE:
                    problems.append((ins.address, "an indexed access from main+%X could reach"
                                     " the mode byte (pointer from %06X)" % (lo_, a)))
            regs_r, regs_w = ins.regs_access()
            names_w = {REG64.get(ins.reg_name(r)) for r in regs_w}
            tail = (ins.mnemonic == "jmp" and ins.op_str.startswith("0x")
                    and not start <= int(ins.op_str, 16) < end)
            if ins.mnemonic == "call" or tail:
                live = set(tracked) & {REG64[r] for r in ARG_REGS}
                # a register is only an argument if the callee reads it before
                # writing it; an r8 left over from the loop above is not passed
                # to a one-parameter function
                if live and ins.op_str.startswith("0x"):
                    callee = int(ins.op_str, 16)
                    live = {r for r in live if callee_reads(img, funcs, callee, r)}
                if live:
                    esc.append((ins.address, ins.op_str, sorted(live)))
                for r in ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11"):
                    tracked.pop(r, None)
                if tail:
                    break
                continue
            if ins.mnemonic == "ret":
                break
            if ins.mnemonic == "mov" and len(ins.operands) == 2:
                d, s = ins.operands
                if s.type == X.X86_OP_REG and REG64.get(ins.reg_name(s.reg)) in tracked:
                    src = tracked[REG64[ins.reg_name(s.reg)]]
                    if d.type == X.X86_OP_REG:
                        tracked[REG64[ins.reg_name(d.reg)]] = src
                        continue
                    esc.append((ins.address, "stored", [REG64[ins.reg_name(s.reg)]]))
            if derived is not None:
                dst = REG64[ins.reg_name(ins.operands[0].reg)]
                tracked[dst] = derived
                continue
            if ins.mnemonic in ("add", "sub") and ins.operands[0].type == X.X86_OP_REG and                     REG64.get(ins.reg_name(ins.operands[0].reg)) in tracked and                     ins.operands[1].type == X.X86_OP_IMM:
                r = REG64[ins.reg_name(ins.operands[0].reg)]
                off, idx = tracked[r]
                imm = ins.operands[1].imm
                tracked[r] = (off + (imm if ins.mnemonic == "add" else -imm), idx)
                continue
            redefine = ins.mnemonic == "xor" or (
                ins.mnemonic in ("or", "and") and ins.operands[1].type == X.X86_OP_IMM
                and ins.operands[1].imm in (-1, 0))
            for r in names_w & set(tracked):
                if r in {REG64.get(ins.reg_name(x)) for x in regs_r} and not redefine:
                    problems.append((ins.address, "arithmetic on the pointer from %06X (%s %s)"
                                     % (a, ins.mnemonic, ins.op_str)))
                tracked.pop(r, None)
        if esc:
            escapes[a] = (target, esc)
    return escapes


# ---------------------------------------------------------------------------
# 2. data flow (Ghidra high p-code)
# ---------------------------------------------------------------------------

def ghidra_facts(ref_rvas):
    """{instruction rva: fact dict} for every mode reference in the functions
    Ghidra says hold these instructions (leaf functions have no .pdata entry)."""
    import pcode_census as pc  # starts pyghidra
    from ghidra.app.decompiler import DecompInterface
    from ghidra.base.project import GhidraProject
    from ghidra.program.model.pcode import PcodeOp
    from ghidra.util.task import ConsoleTaskMonitor

    PASS = pc.CASTS | {PcodeOp.MULTIEQUAL, PcodeOp.PIECE}

    def is_mode(vn):
        return (vn is not None and vn.isAddress()
                and vn.getAddress().getAddressSpace().getName() == "ram"
                and pc.rva_of(vn.getAddress()) == MODE)

    def at(op):
        return pc.rva_of(op.getSeqnum().getTarget())

    def sinks(vn, depth=0, seen=None, out=None):
        """where a value ends up, following copies and phi nodes"""
        if seen is None:
            seen, out = set(), []
        if vn is None or depth > 12:
            return out
        it = vn.getDescendants()
        while it.hasNext():
            op = it.next()
            tag = str(op.getSeqnum())
            if tag in seen:
                continue
            seen.add(tag)
            oc = op.getOpcode()
            o = op.getOutput()
            if oc == PcodeOp.STORE:
                if op.getInput(2).equals(vn):
                    out.append({"k": "store", "at": at(op), "addr": pc.key(op.getInput(1))})
                else:
                    out.append({"k": "addr", "at": at(op)})
                continue
            if oc == PcodeOp.INDIRECT:
                if op.getInput(0).equals(vn):
                    sinks(o, depth + 1, seen, out)
                continue
            if o is not None and o.isAddress() and \
                    o.getAddress().getAddressSpace().getName() == "ram" and oc in PASS:
                out.append({"k": "global", "at": at(op), "g": pc.rva_of(o.getAddress())})
                continue
            if oc in PASS:
                sinks(o, depth + 1, seen, out)
            elif oc in (PcodeOp.CALL, PcodeOp.CALLIND):
                t = op.getInput(0)
                out.append({"k": "arg", "at": at(op),
                            "to": ("%X" % pc.rva_of(t.getAddress())) if t.isAddress() else "ind"})
            elif oc == PcodeOp.RETURN:
                out.append({"k": "return", "at": at(op)})
            elif oc == PcodeOp.CBRANCH:
                out.append({"k": "branch", "at": at(op)})
            else:
                out.append({"k": "use", "at": at(op), "op": pc.OPN.get(oc, str(oc))})
        return out

    def source(vn, depth=0):
        """what a stored value was made from: a constant, a load (and where), ..."""
        vn = pc.strip(vn)
        if vn is None:
            return {"k": "?"}
        if vn.isConstant():
            return {"k": "const", "v": vn.getOffset()}
        if vn.isAddress() and vn.getAddress().getAddressSpace().getName() == "ram":
            return {"k": "global", "g": pc.rva_of(vn.getAddress())}
        d = vn.getDef()
        if d is None:
            return {"k": "input"}
        oc = d.getOpcode()
        if oc == PcodeOp.LOAD:
            return {"k": "load", "at": at(d), "addr": pc.key(d.getInput(1))}
        if oc == PcodeOp.PIECE and depth < 8:
            # firstpass rebuilds a 64-bit register from its halves; the byte a
            # consumer takes is in the low one
            return source(d.getInput(1), depth + 1)
        if oc in (PcodeOp.MULTIEQUAL, PcodeOp.INDIRECT) and depth < 4:
            ins = [source(d.getInput(i), depth + 1)
                   for i in range(1 if oc == PcodeOp.INDIRECT else d.getNumInputs())]
            return {"k": "phi", "of": ins}
        return {"k": "expr", "op": pc.OPN.get(oc, str(oc))}

    import site_facts as sf

    def controlling_mode_reads(op, cfg):
        """mode reads in the conditions of the branches this op depends on"""
        # walk up the dominator chain; a CBRANCH whose block this op's block
        # does not post-dominate is one it is control dependent on
        blocks, idom, bidx, pdom = cfg
        found = set()
        me = bidx.get(op.getParent().getIndex())
        bi = me
        for _ in range(32):
            bi = idom[bi] if bi is not None else None
            if bi is None:
                break
            if me in pdom[bi]:
                continue
            bops = sf.block_ops(blocks[bi])
            last = bops[-1] if bops else None
            if last is None or last.getOpcode() != PcodeOp.CBRANCH:
                continue
            stack, seen = [last.getInput(1)], set()
            while stack:
                v = stack.pop()
                if v is None or v.getUniqueId() in seen:
                    continue
                seen.add(v.getUniqueId())
                if is_mode(v):
                    found.add(at(last))
                    continue
                d = v.getDef()
                if d is None or d.getOpcode() in (PcodeOp.CALL, PcodeOp.CALLIND, PcodeOp.LOAD):
                    continue
                for i in range(d.getNumInputs()):
                    stack.append(d.getInput(i))
        return sorted(found)

    def collect(hf, frva, style, facts):
        blocks = list(hf.getBasicBlocks())
        idom, bidx = sf.dominators(blocks) if blocks else ([], {})
        pdom = sf.postdominators(blocks, bidx) if blocks else []
        cfg = (blocks, idom, bidx, pdom)
        it = hf.getPcodeOps()
        while it.hasNext():
            op = it.next()
            oc = op.getOpcode()
            if oc in (PcodeOp.INDIRECT, PcodeOp.MULTIEQUAL):
                continue
            o = op.getOutput()
            if is_mode(o) and oc == PcodeOp.COPY and is_mode(op.getInput(0)):
                continue   # the global carried to a return: not an access
            if is_mode(o):
                k = "%X" % at(op)
                facts.setdefault(k, {"fn": frva, "style": style, "reads": [], "writes": []})
                facts[k]["writes"].append({
                    "src": source(op.getInput(0)) if oc == PcodeOp.COPY
                    else {"k": "expr", "op": pc.OPN.get(oc, str(oc))},
                    "ctrl": controlling_mode_reads(op, cfg)})
            for i in range(op.getNumInputs()):
                if is_mode(op.getInput(i)):
                    k = "%X" % at(op)
                    facts.setdefault(k, {"fn": frva, "style": style, "reads": [], "writes": []})
                    entry = {"op": pc.OPN.get(oc, str(oc)), "slot": i}
                    if oc in PASS:
                        entry["sinks"] = sinks(o)
                    elif oc == PcodeOp.STORE and i == 2:
                        entry["sinks"] = [{"k": "store", "at": at(op),
                                           "addr": pc.key(op.getInput(1))}]
                    elif oc in (PcodeOp.CALL, PcodeOp.CALLIND):
                        entry["sinks"] = [{"k": "arg", "at": at(op), "to": "?"}]
                    else:
                        entry["sinks"] = [{"k": "use", "at": at(op),
                                           "op": pc.OPN.get(oc, str(oc))}]
                    facts[k]["reads"].append(entry)

    project = GhidraProject.openProject(pc.PROJECT_DIR, "okami", True)
    program = project.openProgram("/", "main.dll", True)
    facts = {}
    try:
        monitor = ConsoleTaskMonitor()
        # "firstpass" keeps every p-code op at the address of the instruction
        # it came from (the default style folds a load into its later use, so
        # the read of `movzx eax, [mode]` shows up at some other instruction),
        # while still giving SSA def-use chains through phi nodes. It fails
        # outright on a quarter of these functions ("free varnode has multiple
        # descendants"); for those, "normalize" works, at the cost of moving
        # the odd op to a later instruction, which main() then matches back.
        ifaces = {}
        for style in ("firstpass", "normalize"):
            ifaces[style] = DecompInterface()
            ifaces[style].setSimplificationStyle(style)
            ifaces[style].openProgram(program)
        fm = program.getFunctionManager()
        space = program.getAddressFactory().getDefaultAddressSpace()
        todo = {}
        for r in sorted(ref_rvas):
            f = fm.getFunctionContaining(space.getAddress(BASE + r))
            if f is None:
                facts["fn:%X" % r] = {"error": "no Ghidra function holds this reference"}
                continue
            todo[pc.rva_of(f.getEntryPoint())] = f
        for frva, f in sorted(todo.items()):
            for style in ("firstpass", "normalize"):
                res = ifaces[style].decompileFunction(f, 60, monitor)
                if res is not None and res.decompileCompleted() and res.getHighFunction():
                    collect(res.getHighFunction(), frva, style, facts)
                    break
            else:
                facts["fn:%X" % frva] = {"error": "decompile failed in both styles"}
        for i in ifaces.values():
            i.dispose()
    finally:
        project.close()
    return facts


# ---------------------------------------------------------------------------
# 3. classification
# ---------------------------------------------------------------------------

OFFSET = re.compile(r"^(?:INT_ADD|PTRSUB)\((.*),c([0-9a-f]+)\)$")
PTRADD = re.compile(r"^PTRADD\((.*),c([0-9a-f]+),c([0-9a-f]+)\)$")


def slot_of(addr_key):
    """(base, byte offset) of an address expression, or (key, None)"""
    g = OFFSET.match(addr_key or "")
    if g:
        return g.group(1), int(g.group(2), 16)
    g = PTRADD.match(addr_key or "")
    if g:
        return g.group(1), int(g.group(2), 16) * int(g.group(3), 16)
    if addr_key and addr_key.startswith("in:"):
        return addr_key, 0
    return addr_key, None


def capstone_read_sinks(img, ins):
    """Where a read's value goes, in straight-line code, for the few references
    Ghidra has no function for (small tail-called leaves it never discovered).
    Returns sink dicts in the Ghidra format, or None if the value is still
    unconsumed at a branch."""
    if ins.mnemonic in ("cmp", "test"):
        return [{"k": "use", "at": ins.address, "op": ins.mnemonic}]
    if ins.mnemonic not in ("movzx", "mov", "movsx"):
        return [{"k": "use", "at": ins.address, "op": ins.mnemonic}]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    tracked = {REG64[ins.reg_name(ins.operands[0].reg)]}
    out = []
    pos = ins.address + ins.size
    for _ in range(64):
        if not tracked:
            return out
        nxt = next(md.disasm(img[pos:pos + 16], pos))
        pos += nxt.size
        regs_r, regs_w = nxt.regs_access()
        rd = {REG64.get(nxt.reg_name(r)) for r in regs_r} & tracked
        wr = {REG64.get(nxt.reg_name(r)) for r in regs_w}
        if nxt.mnemonic in ("call", "jmp", "ret") or nxt.mnemonic.startswith("j"):
            if nxt.mnemonic in ("call", "jmp") and tracked & {REG64[r] for r in ARG_REGS}:
                out.append({"k": "arg", "at": nxt.address, "to": nxt.op_str})
                return out
            return out if nxt.mnemonic in ("call", "ret", "jmp") else None
        if rd:
            d = nxt.operands[0] if nxt.operands else None
            if nxt.mnemonic == "mov" and d is not None and d.type == X.X86_OP_MEM:
                out.append({"k": "store", "at": nxt.address,
                            "addr": "INT_ADD(%s,c%x)" % (nxt.reg_name(d.mem.base), d.mem.disp)})
            elif nxt.mnemonic == "mov" and d is not None and d.type == X.X86_OP_REG:
                tracked.add(REG64[nxt.reg_name(d.reg)])
                continue
            else:
                out.append({"k": "use", "at": nxt.address, "op": nxt.mnemonic})
        tracked -= wr
    return None


def rehome(facts, refs):
    """Move each "normalize" fact that landed on an instruction the sweep did
    not find back to its reference: the nearest earlier reference, in the same
    function, of the same direction (read or write), within 0x40 bytes, that
    has no fact of its own and no other reference between the two."""
    by_addr = sorted(refs, key=lambda i: i.address)
    addrs = [i.address for i in by_addr]
    moved = {}
    for k in sorted(k for k in facts if not k.startswith("fn:")):
        a = int(k, 16)
        if a in addrs or facts[k].get("style") != "normalize":
            continue
        j = bisect.bisect_left(addrs, a) - 1
        if j < 0:
            continue
        ins = by_addr[j]
        op = next(o for o in ins.operands if o.type == X.X86_OP_MEM)
        is_write = bool(op.access & capstone.CS_AC_WRITE)
        want = "writes" if is_write else "reads"
        home = "%X" % ins.address
        if a - ins.address > 0x40 or home in facts or home in moved or not facts[k][want]:
            continue
        other = "reads" if is_write else "writes"
        if facts[k][other]:
            continue
        moved[home] = dict(facts[k], moved_from=k)
    for home, f in moved.items():
        facts[home] = f
        del facts[f["moved_from"]]
    return moved


def classify(refs, facts, funcs, img):
    rows = []
    unresolved = []
    # restores first: the offsets they load from define what a save is
    restore_slots = {}
    for ins in refs:
        f = facts.get("%X" % ins.address)
        if not f or not f["writes"]:
            continue
        for w in f["writes"]:
            src = w["src"]
            if src["k"] == "load":
                base, off = slot_of(src["addr"])
                if off is not None:
                    restore_slots.setdefault(off, []).append(ins.address)
    for ins in refs:
        rva = ins.address
        op = next(o for o in ins.operands if o.type == X.X86_OP_MEM)
        writes = bool(op.access & capstone.CS_AC_WRITE)
        reads = bool(op.access & capstone.CS_AC_READ)
        f = facts.get("%X" % rva)
        row = {"rva": rva, "fn": function_of(funcs, rva), "insn": "%s %s" % (ins.mnemonic, ins.op_str),
               "len": ins.size, "disp_off": ins.disp_offset, "kind": None, "retarget": False,
               "evidence": "", "review": ""}
        if writes and reads:
            row["evidence"] = "read-modify-write of the mode byte"
            unresolved.append(row)
        elif writes:
            imm = [o for o in ins.operands if o.type == X.X86_OP_IMM]
            if imm:
                row["kind"] = KIND_WRITE
                row["evidence"] = "writes %d" % imm[0].imm
            else:
                srcs = [w["src"] for w in (f or {}).get("writes", [])]
                loads = [s for s in srcs if s["k"] == "load"]
                if loads:
                    row["kind"] = KIND_RESTORE
                    row["evidence"] = "restores the value loaded from %s at %X" % (
                        loads[0]["addr"], loads[0]["at"])
                elif srcs:
                    row["kind"] = KIND_RESTORE
                    row["evidence"] = "writes a computed value (%s)" % json.dumps(srcs[0])
                    row["review"] = "restore whose source is not a plain load"
                else:
                    row["evidence"] = "register write with no Ghidra fact"
                    unresolved.append(row)
            if row["kind"] is not None:
                row["retarget"] = True
                ctrl = sorted({c for w in (f or {}).get("writes", []) for c in w["ctrl"]})
                if ctrl:
                    row["review"] = (row["review"] + "; " if row["review"] else "") + \
                        "control dependent on a mode test at %s" % ",".join("%X" % c for c in ctrl)
        else:
            if f and f["reads"]:
                sk = [s for r in f["reads"] for s in r.get("sinks", [])]
            else:
                sk = capstone_read_sinks(img, ins)
                if sk is None:
                    row["evidence"] = "no Ghidra function, and the value is live at a branch"
                    unresolved.append(row)
                    rows.append(row)
                    continue
                row["review"] = "no Ghidra function: straight-line capstone trace"
            stores = [s for s in sk if s["k"] == "store"]
            saved = []
            for s in stores:
                _b, off = slot_of(s["addr"])
                if off is not None and off in restore_slots:
                    saved.append((s, off))
            if saved:
                row["kind"] = KIND_SAVE
                row["retarget"] = True
                s, off = saved[0]
                row["evidence"] = "stored to %s at %X, read back by the restore(s) at %s" % (
                    s["addr"], s["at"], ",".join("%X" % r for r in restore_slots[off]))
            else:
                kinds = collections.Counter(s["k"] for s in sk)
                row["evidence"] = "consumed: " + ", ".join(
                    "%s x%d" % kv for kv in sorted(kinds.items()))
                escapes = [s for s in sk if s["k"] in ("store", "global", "arg", "return")]
                if escapes:
                    row["review"] = "value escapes (%s) but no restore reads it back" % "; ".join(
                        "%s%s" % (s["k"], (" " + s.get("addr", s.get("to", "%X" % s.get("g", 0)))))
                        for s in escapes[:3])
        rows.append(row)
    return rows, unresolved, restore_slots


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def resolve_pointer_routes(img, secs, funcs, problems):
    """Split the lea problems off: follow each pointer, and accept the ones that
    stay in their function or are resolved in POINTER_ROUTES. Returns (the
    remaining problems, route notes, the memset writers' return addresses)."""
    leas = [p for p in problems if p[1].startswith("lea of")]
    others = [p for p in problems if not p[1].startswith("lea of")]
    allp = leas + others
    escapes = pointer_routes(img, secs, funcs, allp)   # appends what it finds
    others = [p for p in allp if not p[1].startswith("lea of")]
    notes, zeroes = [], []
    for a, _why in leas:
        if a in escapes and a not in POINTER_ROUTES:
            target, esc = escapes[a]
            others.append((a, "pointer to main+%X leaves its function (%s) and is not"
                           " resolved in POINTER_ROUTES" % (target, "; ".join(
                               "%X %s %s" % (e[0], e[1], ",".join(e[2])) for e in esc))))
            continue
        if a in POINTER_ROUTES:
            kind, text, checks = POINTER_ROUTES[a]
            bad = [c for c in checks if bytes(img[c[0]:c[0] + len(c[1])]) != c[1]]
            if bad:
                others.append((a, "POINTER_ROUTES entry no longer matches the code at %s"
                               % ",".join("%X" % c[0] for c in bad)))
                continue
            notes.append((a, "%s: %s" % (kind, text)))
            if kind == "memset0":
                zeroes.append(checks[-1][0] + 5)   # the call's return address
        else:
            notes.append((a, "stays in its function; no access reaches the mode byte"))
    for a in sorted(set(POINTER_ROUTES) - {a for a, _w in leas}):
        others.append((a, "POINTER_ROUTES names a lea this build does not have"))
    return others, notes, zeroes


def zero_windows(img, secs, zeroes):
    """(windows, problems) for the memset writers' return points.

    The DLL replaces each window -- whole instructions from the return point,
    at least 5 bytes -- with a jump to a stub that writes 0 to the shadow (the
    value memset just wrote to the real byte), writes the pinned 1 back to the
    real byte, runs the window's instructions with their rip operands
    repointed, and jumps back. That is only sound if the window holds no
    branch, call or return, no branch lands strictly inside it, and the loader
    relocates none of its bytes; the branch targets are the tracer's (every
    direct branch and call, return address, switch table, `lea` into .text,
    .pdata start and code address held in data)."""
    import gen_tracer
    timg, tsecs, begins, _sha = gen_tracer.load_image()   # also fills RELOCATED
    lo, hi = secs[".text"]
    starts, targets, switch, _tables = gen_tracer.global_pass(timg, lo, hi)
    targets = targets | switch | set(begins) | gen_tracer.data_references(timg, tsecs, lo, hi, starts)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    windows, problems = [], []
    for z in zeroes:
        insns, pos = [], z
        while pos - z < 5:
            ins = next(md.disasm(img[pos:pos + 16], pos), None)
            if ins is None:
                break
            insns.append(ins)
            pos += ins.size
        ln = pos - z
        why = []
        for ins in insns:
            if set(ins.groups) & {capstone.CS_GRP_JUMP, capstone.CS_GRP_CALL, capstone.CS_GRP_RET,
                                  capstone.CS_GRP_INT, capstone.CS_GRP_IRET}:
                why.append("%X %s is a control transfer" % (ins.address, ins.mnemonic))
            if ins.mnemonic in gen_tracer.NOT_RELOCATABLE:
                why.append("%X %s cannot be relocated" % (ins.address, ins.mnemonic))
        inside = sorted(t for t in targets if z < t < z + ln)
        if inside:
            why.append("branch target(s) inside: %s" % ",".join("%X" % t for t in inside))
        if any(b in gen_tracer.RELOCATED for b in range(z, z + ln)):
            why.append("holds a byte the loader relocates")
        fixes = []
        for ins in insns:
            if gen_tracer.is_riprel(ins):
                # the rip displacement is always 32 bits, whatever disp_size says
                fixes.append((ins.address - z + ins.disp_offset, ins.address - z + ins.size))
        if not insns or ln > 16 or len(fixes) > 2:
            why.append("no window of whole instructions (%d bytes, %d rip operands)"
                       % (ln, len(fixes)))
        if why:
            problems.append((z, "memset return point cannot be detoured: " + "; ".join(why)))
            continue
        windows.append({"rva": z, "len": ln, "orig": bytes(img[z:z + ln]), "fixes": fixes,
                        "insns": "; ".join("%s %s" % (i.mnemonic, i.op_str) for i in insns)})
    return windows, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cached", action="store_true", help="reuse %s" % FACTS)
    args = ap.parse_args()

    img, secs, funcs, sha = load_image()
    refs, problems = sweep(img, secs)
    print("main.dll sha1 %s: %d instructions reference the mode byte" % (sha, len(refs)))
    problems, notes, zeroes = resolve_pointer_routes(img, secs, funcs, problems)
    print("pointer routes into the frame configuration block: %d" % len(notes))
    for a, n in notes:
        print("  %06X %s" % (a, n))
    zwins, zprob = zero_windows(img, secs, zeroes)
    problems += zprob
    for w in zwins:
        print("  memset return point %06X: %d-byte window (%s), %d rip operand(s)"
              % (w["rva"], w["len"], w["insns"], len(w["fixes"])))
    if problems:
        print("OTHER ROUTES TO THE BYTE:")
        for a, why in problems:
            print("  %06X %s" % (a, why))

    facts = None
    if args.cached and os.path.exists(FACTS):
        cache = json.load(open(FACTS, encoding="utf-8"))
        if cache.get("sha") == sha:
            facts = cache["facts"]
            print("facts from cache (%d entries)" % len(facts))
    if facts is None:
        print("decompiling the functions holding %d references ..." % len(refs), flush=True)
        facts = ghidra_facts([i.address for i in refs])
        json.dump({"sha": sha, "facts": facts}, open(FACTS, "w", encoding="utf-8"), indent=0)
    # a reference in a function Ghidra never discovered (a small leaf reached
    # only through a vtable) gets the straight-line capstone trace instead and
    # is listed for review; only a function that exists and fails is an error
    errs = {k: v for k, v in facts.items()
            if k.startswith("fn:") and "no Ghidra function" not in v["error"]}
    for k, v in facts.items():
        if k.startswith("fn:"):
            print("  %s: %s%s" % (k, v["error"], "" if k in errs else " (capstone trace)"))

    moved = rehome(facts, refs)
    if moved:
        print("normalize-style facts matched back to their instruction: %s" % ", ".join(
            "%s<-%s" % (h, f["moved_from"]) for h, f in sorted(moved.items())))
    rows, unresolved, restore_slots = classify(refs, facts, funcs, img)
    for r in rows:
        f = facts.get("%X" % r["rva"])
        if f:
            r["fn"] = f["fn"]
    # every Ghidra fact must correspond to an instruction the sweep found
    swept = {"%X" % i.address for i in refs}
    extra = sorted(k for k in facts if not k.startswith("fn:") and k not in swept)
    if extra:
        print("Ghidra sees mode references the sweep did not: %s" % ", ".join(extra))

    counts = collections.Counter(KIND_NAME.get(r["kind"], "consume") for r in rows)
    print("\n%s" % ", ".join("%s %d" % kv for kv in sorted(counts.items())))
    print("restore slots: %s" % ", ".join("+%X <- %s" % (off, ",".join("%X" % r for r in v))
                                          for off, v in sorted(restore_slots.items())))
    for r in rows:
        if r["retarget"]:
            print("  %-7s %06X in %06X  %-38s %s" % (KIND_NAME[r["kind"]], r["rva"], r["fn"] or 0,
                                                     r["insn"], r["evidence"]))
    review = [r for r in rows if r["review"]]
    if review:
        print("\nfor review (%d):" % len(review))
        for r in review:
            print("  %06X in %06X  %-38s %s" % (r["rva"], r["fn"] or 0, r["insn"], r["review"]))

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["site", "function", "instruction", "class", "retarget", "evidence", "review"])
        for r in rows:
            wr.writerow(["%06X" % r["rva"], "%06X" % (r["fn"] or 0), r["insn"],
                         KIND_NAME.get(r["kind"], "consume"), int(r["retarget"]),
                         r["evidence"], r["review"]])
        for a, n in notes:
            wr.writerow(["%06X" % a, "%06X" % (function_of(funcs, a) or 0),
                         "lea (pointer into the block)",
                         "zero" if n.startswith("memset0") else "pointer", 0, n, ""])

    if unresolved or problems or extra or errs:
        print("\nNOT WRITING %s: %d unresolved references, %d other routes, %d Ghidra-only,"
              " %d functions not decompiled" % (os.path.relpath(OUT_H, ROOT), len(unresolved),
                                                len(problems), len(extra), len(errs)))
        for r in unresolved:
            print("  %06X %s: %s" % (r["rva"], r["insn"], r["evidence"]))
        return 1

    sel = [r for r in rows if r["retarget"]]
    for r in sel:
        d = r["disp_off"]
        disp = struct.unpack_from("<i", img, r["rva"] + d)[0]
        assert r["rva"] + r["len"] + disp == MODE, "%06X: displacement does not name the byte" % r["rva"]
        assert r["len"] <= 16
        for w in zwins:
            assert not (r["rva"] < w["rva"] + w["len"] and w["rva"] < r["rva"] + r["len"]), \
                "%06X overlaps the detour window at %06X" % (r["rva"], w["rva"])
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generated by tools/gen_shadow_mode.py -- do not edit.\n")
        f.write("// main.dll sha1 %s\n" % sha)
        f.write("//\n// Every instruction that maintains the mode byte main+%X: the %d writes\n"
                "// of a constant, the %d restores of a saved value, and the %d reads that\n"
                "// save it for those restores. Each is retargeted, by its rip displacement\n"
                "// alone, at the patch's shadow byte. The other %d references consume the\n"
                "// byte and keep reading the real one. docs/animation/shadow_mode.csv has\n"
                "// the evidence for every reference.\n//\n"
                "// One more writer has no displacement to retarget: at engine start,\n"
                "// flower_startup(false) clears the whole frame block with memset, which\n"
                "// writes 0 to the mode byte. The\n"
                "// instructions at the call's return point are detoured to a stub that\n"
                "// writes 0 to the shadow, puts the pinned 1 back in the real byte, runs\n"
                "// them (rip operands repointed by the fixups) and jumps back. No branch\n"
                "// lands inside the window and none of its bytes is relocated.\n"
                % (MODE, counts["write"], counts["restore"], counts["save"],
                   len(rows) - len(sel)))
        f.write("#pragma once\n#include <cstdint>\n\n")
        f.write('#define SHADOW_MODE_MAIN_SHA1 "%s"\n' % sha)
        f.write("static const uint32_t kShadowModeByteRva = 0x%X;\n\n" % MODE)
        f.write("// kind: 0 writes a constant, 1 restores a saved value, 2 saves the value\n")
        f.write("struct ShadowModeSite {\n    uint32_t rva;\n    uint8_t len;\n"
                "    uint8_t dispOff;\n    uint8_t kind;\n    uint8_t orig[16];\n};\n\n")
        f.write("static const ShadowModeSite kShadowModeSites[] = {\n")
        for r in sel:
            raw = img[r["rva"]:r["rva"] + r["len"]]
            f.write("    {0x%06X, %d, %d, %d, {%s}},  // %s: %s\n" % (
                r["rva"], r["len"], r["disp_off"], r["kind"],
                ",".join("0x%02X" % b for b in raw), KIND_NAME[r["kind"]], r["insn"]))
        f.write("};\n\n")
        f.write("// fix: {offset of a rip displacement in the window, end of its instruction}\n")
        f.write("struct ShadowModeZeroWindow {\n    uint32_t rva;\n    uint8_t len;\n"
                "    uint8_t nFix;\n    uint8_t fix[2][2];\n    uint8_t orig[16];\n};\n\n")
        f.write("static const ShadowModeZeroWindow kShadowModeZeroWindows[] = {\n")
        for w in zwins:
            fx = list(w["fixes"]) + [(0, 0)] * (2 - len(w["fixes"]))
            f.write("    {0x%06X, %d, %d, {{%d, %d}, {%d, %d}}, {%s}},  // %s\n" % (
                w["rva"], w["len"], len(w["fixes"]), fx[0][0], fx[0][1], fx[1][0], fx[1][1],
                ",".join("0x%02X" % b for b in w["orig"]), w["insns"]))
        f.write("};\n")
    print("\nwrote %s (%d sites, %d zero window(s)) and %s" % (
        os.path.relpath(OUT_H, ROOT), len(sel), len(zwins), os.path.relpath(OUT_CSV, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
