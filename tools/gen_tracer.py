#!/usr/bin/env python3
"""Generate the tracer: one neutral, instrumented stub per animation candidate.

Every non-library candidate in
docs/animation/sites.csv gets a *window* -- a run of whole instructions of at
least five bytes that contains its store -- and the window is replaced by a
jump to a stub that

  * runs the window's instructions unchanged (relocated, with every rip-relative
    operand and branch repointed at the original target);
  * reads the stored field just before and just after the store, and hands both
    values to one shared counting routine, which keeps per site: executions,
    executions that changed the value, ticks active, the longest run of
    consecutive active ticks, ticks with a change, the longest run of those, the
    mode byte values seen and the ticks spent in mode 1 (60 Hz stock context).

A tick is the game's own frame counter (main+B6AC20), read inside the counting
routine, so no per-tick hook is needed and nothing depends on the watcher
thread's timing.

The whole pool is built here, offline, as one byte blob with a fixup list. The
DLL copies the blob next to main.dll, applies the fixups, and writes the jumps.
So the bytes tools/verify_tracer.py emulates are the bytes that run.

Window rules, each of which would otherwise be a crash:
  * no branch target strictly inside a window. Targets are collected from every
    direct branch and call, every return address, every switch table, every
    `lea reg, [rip+X]` into .text, every .pdata function start, and every
    dword/qword in .rdata/.data that is an instruction start in .text (which
    covers exception-handler continuations and function-pointer tables);
  * no call in a window, so no return address ever points into one and every
    ret the game executes still matches a real call;
  * only int3/nop padding may follow a ret or jmp inside a window;
  * no loop/jrcxz, no branch into the window itself;
  * nothing overlapping a hook the DLL installs in Passthrough (the harness);
  * no byte the loader relocates (main.dll is ASLR-enabled).

Outputs
  src/generated/tracer_sites.h      the pool blob, fixups, windows, sites
  docs/animation/tracer_sites.csv   every candidate: its window, or why none

    python tools/gen_tracer.py
    python tools/verify_tracer.py
"""
import array
import collections
import csv
import hashlib
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
SITES_CSV = os.path.join(ROOT, "docs", "animation", "sites.csv")
OUT_H = os.path.join(ROOT, "src", "generated", "tracer_sites.h")
OUT_CSV = os.path.join(ROOT, "docs", "animation", "tracer_sites.csv")
PROXY = os.path.join(ROOT, "src", "dinput8_proxy.cpp")

BASE = 0x180000000
FRAME_COUNTER = 0xB6AC20   # uint32, +1 per tick
MODE_BYTE = 0xB6AC45       # 1 = 60 Hz config, 2 = 30 Hz config
REC_SIZE = 0x50
MAX_BACK = 4
MAX_FWD = 5

# record layout, shared with the DLL (TracerRec) and verify_tracer.py
R_OLD, R_LASTOLD, R_LASTNEW = 0x00, 0x08, 0x10
R_EXEC, R_CHG, R_LASTTICK, R_TICKS = 0x18, 0x1C, 0x20, 0x24
R_RUN, R_MAXRUN, R_CTX, R_LASTCHG = 0x28, 0x2C, 0x30, 0x34
R_CHGTICKS, R_CHGRUN, R_MAXCHGRUN, R_TICKSM1 = 0x38, 0x3C, 0x40, 0x44

GPR = {n: i for i, n in enumerate(
    "rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split())}

KIND_INT, KIND_FLOAT, KIND_X87, KIND_COUNT = 0, 1, 2, 3
RELOCATED = set()   # every byte the loader may rewrite (filled by load_image)


# ---------------------------------------------------------------------------
# image
# ---------------------------------------------------------------------------

def load_image():
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    img = bytearray(pe.get_memory_mapped_image())
    secs = {s.Name.rstrip(b"\0").decode(): (s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize)
            for s in pe.sections}
    pd_rva, pd_size = secs[".pdata"][0], secs[".pdata"][1] - secs[".pdata"][0]
    begins = []
    for off in range(pd_rva, pd_rva + pd_size - 11, 12):
        b, e, u = struct.unpack_from("<III", img, off)
        if b == 0 and e == 0:
            break
        begins.append(b)
    # main.dll is ASLR-enabled: the loader rewrites every qword named in .reloc,
    # so a window holding one would not match its recorded bytes in the game
    for blk in pefile.PE(data=raw).DIRECTORY_ENTRY_BASERELOC:
        for e in blk.entries:
            if e.type:
                RELOCATED.update(range(e.rva, e.rva + 8))
    return img, secs, begins, hashlib.sha1(raw).hexdigest()


TBL = re.compile(r"^(\w+), dword ptr \[(\w+) \+ (\w+)\*4 \+ (0x[0-9a-f]+)\]$")
RIPLEA = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+|\d+)\]")


def global_pass(img, lo, hi):
    """Linear sweep of .text: instruction starts, branch targets, switch tables."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    starts = bytearray(hi)       # 1 = instruction start
    targets = set()
    tables = set()
    pending = []
    pos = lo
    while pos < hi:
        end = min(hi, pos + 0x10000)
        buf = bytes(img[pos:end + 16])
        last = pos
        for a, s, mn, op in md.disasm_lite(buf, pos):
            if a >= end:
                break
            starts[a] = 1
            last = a + s
            if mn == "call":
                targets.add(a + s)
                if op.startswith("0x"):
                    targets.add(int(op, 16))
            elif mn[0] == "j" and op.startswith("0x"):
                targets.add(int(op, 16))
            elif mn == "lea" and "rip" in op:
                g = RIPLEA.search(op)
                if g:
                    d = int(g.group(2), 0)
                    t = a + s + (d if g.group(1) == "+" else -d)
                    if lo <= t < hi:
                        targets.add(t)
            if pending:
                keep = []
                for tbl, left in pending:
                    if mn == "jmp" and "ptr" not in op and not op.startswith("0x"):
                        tables.add(tbl)
                    elif left > 1:
                        keep.append((tbl, left - 1))
                pending = keep
            if mn == "mov":
                g = TBL.match(op)
                if g:
                    tbl = int(g.group(4), 16)
                    if lo <= tbl < hi:
                        pending.append((tbl, 5))
        pos = last if last > pos else pos + 1
    switch = set()
    for tbl in tables:
        for i in range(4096):
            t = struct.unpack_from("<I", img, tbl + i * 4)[0]
            if not (lo <= t < hi):
                break
            switch.add(t)
    return starts, targets, switch, tables


def data_references(img, secs, lo, hi, starts):
    """Instruction starts in .text named by a dword RVA or a qword VA in data."""
    found = set()
    for name in (".rdata", ".data"):
        a, b = secs[name]
        a4 = (a + 3) & ~3
        dw = array.array("I", bytes(img[a4:b & ~3]))
        for v in dw:
            if lo <= v < hi and starts[v]:
                found.add(v)
        a8 = (a + 7) & ~7
        qw = array.array("Q", bytes(img[a8:b & ~7]))
        blo, bhi = BASE + lo, BASE + hi
        for v in qw:
            if blo <= v < bhi and starts[v - BASE]:
                found.add(v - BASE)
    return found


def protected_ranges():
    src = open(PROXY, encoding="utf-8").read()
    out = []
    g = re.search(r"kHarnessHookRva\s*=\s*0x([0-9A-Fa-f]+)", src)
    if g:
        out.append((int(g.group(1), 16), int(g.group(1), 16) + 5, "harness hook"))
    return out


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------

def read_sites():
    rows = list(csv.DictReader(open(SITES_CSV, encoding="utf-8")))
    by_rva = collections.OrderedDict()
    for r in rows:
        if r["subsystem"] == "library":
            continue
        rva = int(r["site"], 16)
        if rva not in by_rva:
            by_rva[rva] = {"rva": rva, "fn": int(r["function"], 16),
                           "sub": r["subsystem"], "shape": r["shape"]}
    return list(by_rva.values())


class Decoder:
    """Detailed decode of the code around a site, cached per start address."""

    def __init__(self, img, starts):
        self.img = img
        self.starts = starts
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.cache = {}

    def run(self, start, need_to):
        """Instructions decoded from `start` until past `need_to`+64."""
        c = self.cache.get(start)
        if c and c[-1].address + c[-1].size >= need_to + 64:
            return c
        stop = need_to + 96
        out = []
        pos = start
        while pos < stop:
            got = False
            for ins in self.md.disasm(bytes(self.img[pos:stop + 16]), pos):
                out.append(ins)
                pos = ins.address + ins.size
                got = True
                if pos >= stop:
                    break
            if not got:
                break
            if pos < stop:
                break  # undecodable byte: stop the run here
        self.cache[start] = out
        return out

    def around(self, site, fn, fn_last):
        """(insns, index of the site) decoded from a start that is a real boundary.

        `fn_last` is the function's last candidate, so one decode serves them all."""
        starts_try = []
        if fn <= site and site - fn < 0x40000:
            starts_try.append((fn, max(site, fn_last)))
        # fall back to the linear sweep's boundaries a little before the site
        p = site - 1
        back = 0
        while p > 0 and back < 3:
            if self.starts[p]:
                back += 1
                q = p
            p -= 1
            if site - p > 96:
                break
        if back:
            starts_try.append((q, site))
        for st, upto in starts_try:
            insns = self.run(st, upto)
            for i, ins in enumerate(insns):
                if ins.address == site:
                    return insns, i
                if ins.address > site:
                    break
        return None, None


# ---------------------------------------------------------------------------
# instruction classification
# ---------------------------------------------------------------------------

UNCOND = {"jmp", "ret", "retf", "iretq", "ud2"}
PADDING = {"int3", "nop"}
NOT_RELOCATABLE = {"jrcxz", "jecxz", "loop", "loope", "loopne", "hlt", "int", "int1",
                   "into", "syscall", "sysenter", "xbegin"}


def is_riprel(ins):
    return any(op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP for op in ins.operands)


def is_call(ins):
    return ins.mnemonic == "call"


def is_rel_branch(ins):
    return (capstone.CS_GRP_JUMP in ins.groups and ins.operands
            and ins.operands[0].type == X.X86_OP_IMM)


def uses_rsp_mem(ins):
    return any(op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RSP for op in ins.operands)


def window_problem(ws, targets, protected):
    """None if the instruction run `ws` can be relocated as one window."""
    lo = ws[0].address
    hi = ws[-1].address + ws[-1].size
    for a, b, what in protected:
        if a < hi and lo < b:
            return "overlaps " + what
    if any(x in RELOCATED for x in range(lo, hi)):
        return "holds a base relocation"
    dead = False
    for k, ins in enumerate(ws):
        if k and ins.address in targets:
            return "branch target inside"
        mn = ins.mnemonic
        if dead:
            if mn not in PADDING:
                return "code after an unconditional transfer"
            continue
        if mn == "int3":
            return "padding"
        if mn in NOT_RELOCATABLE or mn.startswith("loop"):
            return "not relocatable (%s)" % mn
        if is_call(ins):
            # A call in the middle leaves a return address inside the window. At
            # the end it could be emulated as push+jmp, but the callee's ret would
            # then match no call -- fragile under CET shadow stacks -- for 3 sites.
            return "call in window"
        if is_rel_branch(ins):
            t = ins.operands[0].imm
            if lo <= t < hi:
                return "branch into the window"
            b0 = ins.bytes[0]
            if not (b0 in (0xEB, 0xE9) or 0x70 <= b0 <= 0x7F
                    or (b0 == 0x0F and 0x80 <= ins.bytes[1] <= 0x8F)):
                return "prefixed branch"
        # rip-relative is always disp32 in 64-bit mode; capstone's disp_size
        # says 2 under a 0x66 prefix, so check the bytes at disp_offset instead
        if is_riprel(ins):
            mem = next(op for op in ins.operands
                       if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP)
            d = ins.disp_offset
            if not d or bytes(ins.bytes[d:d + 4]) != struct.pack("<i", mem.mem.disp):
                return "rip displacement not where capstone says"
        if mn in UNCOND or (mn == "jmp"):
            dead = True
    return None


def find_window(insns, idx, targets, protected):
    """Smallest valid window around insns[idx]; (lo_index, hi_index) or reason."""
    best = None
    reason = None
    for back in range(0, MAX_BACK + 1):
        for fwd in range(0, MAX_FWD + 1):
            a, b = idx - back, idx + fwd
            if a < 0 or b >= len(insns):
                continue
            ws = insns[a:b + 1]
            size = ws[-1].address + ws[-1].size - ws[0].address
            if size < 5:
                continue
            why = window_problem(ws, targets, protected)
            if why:
                if reason is None:
                    reason = why
                continue
            key = (size, back + fwd, back)
            if best is None or key < best[0]:
                best = (key, a, b)
    if best:
        return best[1], best[2], None
    return None, None, reason or "no run of 5 bytes"


# ---------------------------------------------------------------------------
# encoding
# ---------------------------------------------------------------------------

def rex(w, r, x, b):
    v = 0x40 | (w << 3) | (r << 2) | (x << 1) | b
    return b"" if v == 0x40 else bytes([v])


def modrm_mem(regf, base, index, scale, disp):
    """(rex r/x/b bits, modrm+sib+disp bytes) for [base + index*scale + disp]."""
    ss = {1: 0, 2: 1, 4: 2, 8: 3}[scale]
    r = regf >> 3
    if base is None:
        xi = 4 if index is None else index
        body = bytes([(regf & 7) << 3 | 4, ss << 6 | (xi & 7) << 3 | 5]) + struct.pack("<i", disp)
        return r, (xi >> 3) if index is not None else 0, 0, body
    if disp == 0 and (base & 7) != 5:
        mod, dbytes = 0, b""
    elif -128 <= disp <= 127:
        mod, dbytes = 1, struct.pack("<b", disp)
    else:
        mod, dbytes = 2, struct.pack("<i", disp)
    if index is None and (base & 7) != 4:
        body = bytes([mod << 6 | (regf & 7) << 3 | (base & 7)]) + dbytes
        return r, 0, base >> 3, body
    xi = 4 if index is None else index
    body = bytes([mod << 6 | (regf & 7) << 3 | 4, ss << 6 | (xi & 7) << 3 | (base & 7)]) + dbytes
    return r, (xi >> 3) if index is not None else 0, base >> 3, body


IMPLICIT_RSP = {"push", "pop", "pushfq", "popfq", "call", "ret", "enter", "leave"}
STRING_OPS = {"movsb", "movsw", "movsq", "stosb", "stosw", "stosd", "stosq",
              "cmpsb", "cmpsw", "cmpsd", "cmpsq", "scasb", "scasw", "scasd", "scasq",
              "lodsb", "lodsw", "lodsd", "lodsq"}


def mem_operand(ins):
    """The written memory operand of a store, or None."""
    for op in ins.operands:
        if op.type == X.X86_OP_MEM and (op.access & capstone.CS_AC_WRITE):
            return op
    return None


def sample_plan(ins):
    """(size, base, index, scale, disp, riprel target) or (0, reason)."""
    op = mem_operand(ins)
    if op is None:
        return 0, "no written memory operand"
    if op.mem.segment != 0:
        return 0, "segment override"
    if ins.addr_size != 8:
        return 0, "32-bit addressing"
    mn = ins.mnemonic
    if mn.split()[0] in IMPLICIT_RSP:
        return 0, "implicit rsp"
    # string ops: movsd is also the SSE store, so tell them apart by operands
    if (mn.startswith("rep") or mn in STRING_OPS
            or sum(o.type == X.X86_OP_MEM for o in ins.operands) > 1):
        return 0, "string op"
    names = set()
    base = index = None
    riprel = None
    if op.mem.base == X.X86_REG_RIP:
        riprel = ins.address + ins.size + op.mem.disp
    elif op.mem.base != 0:
        nm = ins.reg_name(op.mem.base)
        if nm not in GPR:
            return 0, "base " + nm
        base = GPR[nm]
        names.add(nm)
    if op.mem.index != 0:
        nm = ins.reg_name(op.mem.index)
        if nm not in GPR:
            return 0, "index " + nm
        index = GPR[nm]
        names.add(nm)
    _r, written = ins.regs_access()
    for w in written:
        if ins.reg_name(w) in names or ins.reg_name(w) == "rsp":
            return 0, "address register written"
    size = op.size if op.size in (1, 2, 4, 8) else 8
    scale = op.mem.scale if op.mem.scale in (1, 2, 4, 8) else 1
    return (size, base, index, scale, op.mem.disp, riprel), None


def kind_of(ins):
    if ins.mnemonic.startswith("f"):
        return KIND_X87
    for op in ins.operands:
        if op.type == X.X86_OP_REG and ins.reg_name(op.reg).startswith(("xmm", "ymm")):
            return KIND_FLOAT
    return KIND_INT


class Pool:
    """Pool image under construction. Offsets are pool offsets throughout."""

    def __init__(self, code_off):
        self.code_off = code_off
        self.code = bytearray()
        self.fixups = []   # (field, next, target_rva); next == 0 -> abs64 slot

    def here(self):
        return self.code_off + len(self.code)

    def emit(self, b):
        self.code += b

    def game_rel32(self, prefix, target, trailing=b""):
        self.code += prefix
        field = self.here()
        self.code += b"\0\0\0\0" + trailing
        self.fixups.append((field, self.here(), target))

    def pool_rel32(self, prefix, pool_off, trailing=b""):
        self.code += prefix
        nxt = self.here() + 4 + len(trailing)
        self.code += struct.pack("<i", pool_off - nxt) + trailing


def enc_load(pool, dst, plan, rsp_adj):
    """dst <- zero-extended [mem] of the plan's size."""
    size, base, index, scale, disp, riprel = plan
    if size == 1:
        op, w = b"\x0F\xB6", 0
    elif size == 2:
        op, w = b"\x0F\xB7", 0
    elif size == 4:
        op, w = b"\x8B", 0
    else:
        op, w = b"\x8B", 1
    if riprel is not None:
        pool.game_rel32(rex(w, dst >> 3, 0, 0) + op + bytes([(dst & 7) << 3 | 5]), riprel)
        return
    if base == GPR["rsp"]:
        disp += rsp_adj
    r, x, b, body = modrm_mem(dst, base, index, scale, disp)
    pool.emit(rex(w, r, x, b) + op + body)


def mov_rsp_store(reg, d8):
    """mov [rsp+d8], reg64"""
    return rex(1, reg >> 3, 0, 0) + b"\x89" + bytes([0x40 | (reg & 7) << 3 | 4, 0x24, d8])


def mov_rsp_load(reg, d8):
    """mov reg64, [rsp+d8]"""
    return rex(1, reg >> 3, 0, 0) + b"\x8B" + bytes([0x40 | (reg & 7) << 3 | 4, 0x24, d8])


def lea_rsp(d8):
    return b"\x48\x8D\x64\x24" + struct.pack("<b", d8)


def emit_pre(pool, plan, rec):
    """Record the field's value before the store. Touches no flags."""
    _size, base, index, _s, _d, _rip = plan
    busy = {base, index}
    scratch = next(r for r in (0, 1, 2, 8, 9, 10, 11) if r not in busy)
    pool.emit(lea_rsp(-16) + mov_rsp_store(scratch, 0))
    enc_load(pool, scratch, plan, 16)
    # mov [rip + rec.old], scratch
    pool.pool_rel32(rex(1, scratch >> 3, 0, 0) + b"\x89" + bytes([(scratch & 7) << 3 | 5]),
                    rec + R_OLD)
    pool.emit(mov_rsp_load(scratch, 0) + lea_rsp(16))


def emit_post(pool, plan, rec, common):
    """Load the new value into rdx, rec into rcx, call the counter."""
    pool.emit(lea_rsp(-0x20) + mov_rsp_store(1, 0) + mov_rsp_store(2, 8) + b"\x9C")
    if plan:
        enc_load(pool, 2, plan, 0x28)
    else:
        pool.emit(b"\x31\xD2")                      # xor edx, edx (flags saved)
    pool.pool_rel32(b"\x48\x8D\x0D", rec)            # lea rcx, [rip + rec]
    pool.pool_rel32(b"\xE8", common)                 # call common
    pool.emit(b"\x9D" + mov_rsp_load(2, 8) + mov_rsp_load(1, 0) + lea_rsp(0x20))


def emit_common(pool):
    """The shared counter. rcx = record, rdx = new value. Keeps rax; flags,
    rcx and rdx are restored by the caller."""
    labels, jumps = {}, []

    def jcc8(opc, label):
        pool.emit(bytes([opc, 0]))
        jumps.append((pool.here() - 1, label))

    def lab(name):
        labels[name] = pool.here()

    def rip32(prefix, target_rva):
        pool.game_rel32(prefix, target_rva)

    start = pool.here()
    pool.emit(b"\x50")                                   # push rax
    pool.emit(b"\xFF\x41" + bytes([R_EXEC]))             # inc dword [rcx+exec]
    pool.emit(b"\x48\x8B\x41" + bytes([R_OLD]))          # mov rax, [rcx+old]
    pool.emit(b"\x48\x39\xD0")                           # cmp rax, rdx
    jcc8(0x74, "nochg")                                  # je nochg
    pool.emit(b"\xFF\x41" + bytes([R_CHG]))              # inc dword [rcx+chg]
    pool.emit(b"\x48\x89\x41" + bytes([R_LASTOLD]))      # mov [rcx+lastOld], rax
    pool.emit(b"\x48\x89\x51" + bytes([R_LASTNEW]))      # mov [rcx+lastNew], rdx
    rip32(b"\x8B\x05", FRAME_COUNTER)                    # mov eax, [rip+fc]
    pool.emit(b"\x8B\x51" + bytes([R_LASTCHG]))          # mov edx, [rcx+lastChg]
    pool.emit(b"\x39\xD0")                               # cmp eax, edx
    jcc8(0x74, "nochg")
    pool.emit(b"\x89\x41" + bytes([R_LASTCHG]))          # mov [rcx+lastChg], eax
    pool.emit(b"\xFF\x41" + bytes([R_CHGTICKS]))         # inc dword [rcx+chgTicks]
    pool.emit(b"\xFF\xC2")                               # inc edx
    pool.emit(b"\x39\xD0")                               # cmp eax, edx
    jcc8(0x75, "cnew")                                   # jne cnew
    pool.emit(b"\xFF\x41" + bytes([R_CHGRUN]))           # inc dword [rcx+chgRun]
    jcc8(0xEB, "cchk")                                   # jmp cchk
    lab("cnew")
    pool.emit(b"\xC7\x41" + bytes([R_CHGRUN]) + struct.pack("<I", 1))
    lab("cchk")
    pool.emit(b"\x8B\x51" + bytes([R_CHGRUN]))           # mov edx, [rcx+chgRun]
    pool.emit(b"\x3B\x51" + bytes([R_MAXCHGRUN]))        # cmp edx, [rcx+maxChgRun]
    jcc8(0x76, "nochg")                                  # jbe nochg
    pool.emit(b"\x89\x51" + bytes([R_MAXCHGRUN]))
    lab("nochg")
    rip32(b"\x8B\x05", FRAME_COUNTER)                    # mov eax, [rip+fc]
    pool.emit(b"\x8B\x51" + bytes([R_LASTTICK]))         # mov edx, [rcx+lastTick]
    pool.emit(b"\x39\xD0")                               # cmp eax, edx
    jcc8(0x74, "done")
    pool.emit(b"\x89\x41" + bytes([R_LASTTICK]))
    pool.emit(b"\xFF\x41" + bytes([R_TICKS]))
    pool.emit(b"\xFF\xC2")
    pool.emit(b"\x39\xD0")
    jcc8(0x75, "new")
    pool.emit(b"\xFF\x41" + bytes([R_RUN]))
    jcc8(0xEB, "chk")
    lab("new")
    pool.emit(b"\xC7\x41" + bytes([R_RUN]) + struct.pack("<I", 1))
    lab("chk")
    pool.emit(b"\x8B\x51" + bytes([R_RUN]))
    pool.emit(b"\x3B\x51" + bytes([R_MAXRUN]))
    jcc8(0x76, "ctx")
    pool.emit(b"\x89\x51" + bytes([R_MAXRUN]))
    lab("ctx")
    rip32(b"\x0F\xB6\x15", MODE_BYTE)                    # movzx edx, byte [rip+mode]
    pool.emit(b"\x83\xE2\x1F")                           # and edx, 31
    pool.emit(b"\x0F\xAB\x51" + bytes([R_CTX]))          # bts [rcx+ctx], edx
    pool.emit(b"\x83\xFA\x01")                           # cmp edx, 1
    jcc8(0x75, "done")
    pool.emit(b"\xFF\x41" + bytes([R_TICKSM1]))          # inc dword [rcx+ticksM1]
    lab("done")
    pool.emit(b"\x58\xC3")                               # pop rax; ret
    for at, name in jumps:
        rel = labels[name] - (at + 1)
        assert -128 <= rel <= 127
        pool.code[at - pool.code_off] = rel & 0xFF
    return start


def emit_relocated(pool, ins, slot_for_call):
    b = bytes(ins.bytes)
    if is_call(ins):
        pool.pool_rel32(b"\xFF\x35", slot_for_call)     # push qword [rip+slot]
        if ins.operands[0].type == X.X86_OP_IMM:
            pool.game_rel32(b"\xE9", ins.operands[0].imm)
            return
        m = ins.modrm_offset
        jb = bytearray(b)
        jb[m] = (jb[m] & 0xC7) | (4 << 3)               # FF /2 -> FF /4
        if is_riprel(ins):
            d = ins.disp_offset
            pool.game_rel32(bytes(jb[:d]), ins.address + ins.size + ins.operands[0].mem.disp,
                            bytes(jb[d + 4:]))
        else:
            pool.emit(bytes(jb))
        return
    if is_rel_branch(ins):
        t = ins.operands[0].imm
        if b[0] in (0xEB, 0xE9):
            pool.game_rel32(b"\xE9", t)
        elif 0x70 <= b[0] <= 0x7F:
            pool.game_rel32(bytes([0x0F, 0x80 | (b[0] & 0xF)]), t)
        else:
            pool.game_rel32(bytes([0x0F, b[1]]), t)
        return
    if is_riprel(ins):
        d = ins.disp_offset
        mem = next(op for op in ins.operands
                   if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP)
        pool.game_rel32(b[:d], ins.address + ins.size + mem.mem.disp, b[d + 4:])
        return
    pool.emit(b)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    img, secs, pdata_begins, sha = load_image()
    lo, hi = secs[".text"]
    print("main.dll sha1 %s, .text %06X-%06X" % (sha, lo, hi))
    starts, targets, switch, tables = global_pass(img, lo, hi)
    print("linear sweep: %d instruction starts, %d direct targets, %d switch tables"
          " (%d destinations)" % (sum(starts), len(targets), len(tables), len(switch)))
    datarefs = data_references(img, secs, lo, hi, starts)
    print("data references to instruction starts: %d" % len(datarefs))
    targets |= switch | datarefs | set(pdata_begins)
    protected = protected_ranges()
    print("protected: %s" % ", ".join("%06X-%06X %s" % p for p in protected))

    sites = read_sites()
    print("candidates (non-library, unique stores): %d" % len(sites))
    dec = Decoder(img, starts)

    # ---- 1. a window per site -------------------------------------------
    refused = {}
    per_site = {}
    fn_last = collections.defaultdict(int)
    for s in sites:
        fn_last[s["fn"]] = max(fn_last[s["fn"]], s["rva"])
    for s in sites:
        insns, idx = dec.around(s["rva"], s["fn"], fn_last[s["fn"]])
        if insns is None:
            refused[s["rva"]] = "not an instruction start"
            continue
        if mem_operand(insns[idx]) is None:
            # Ghidra artifacts (SUBPIECE(0,#0), COPY(PHI(0|0))) on reads,
            # compares and stack adjustments: nothing is stored, nothing to trace
            refused[s["rva"]] = "not a store (census artifact)"
            continue
        a, b, why = find_window(insns, idx, targets, protected)
        if why:
            refused[s["rva"]] = why
            continue
        per_site[s["rva"]] = (insns, a, b)

    # ---- 2. merge windows that overlap ----------------------------------
    spans = sorted((insns[a].address, insns[b].address + insns[b].size, rva)
                   for rva, (insns, a, b) in per_site.items())
    windows = []   # [lo, hi, [site rvas], insns list]
    for w_lo, w_hi, rva in spans:
        insns, a, b = per_site[rva]
        if windows and w_lo < windows[-1][1]:
            prev = windows[-1]
            m_lo, m_hi = prev[0], max(prev[1], w_hi)
            run = [i for i in prev[3] if m_lo <= i.address < m_hi]
            tail = [i for i in insns if prev[3][-1].address < i.address < m_hi]
            run = run + tail
            contiguous = all(run[k].address + run[k].size == run[k + 1].address
                             for k in range(len(run) - 1))
            why = None if contiguous else "overlapping window not contiguous"
            if not why:
                why = window_problem(run, targets, protected)
            if why:
                refused[rva] = "merge: " + why
                continue
            prev[1] = m_hi
            prev[2].append(rva)
            prev[3] = run
        else:
            windows.append([w_lo, w_hi, [rva], insns[a:b + 1]])

    # ---- 3. layout --------------------------------------------------------
    site_info = {s["rva"]: s for s in sites}
    ordered = []   # final site order = record order
    for w in windows:
        for rva in sorted(w[2]):
            ordered.append(rva)
    rec_index = {rva: i for i, rva in enumerate(ordered)}
    nslots = sum(1 for w in windows if is_call(w[3][-1]))
    rec_off = 0
    slot_off = (len(ordered) * REC_SIZE + 0xFFF) & ~0xFFF
    code_off = (slot_off + nslots * 8 + 0xFFF) & ~0xFFF
    pool = Pool(code_off)
    common = emit_common(pool)
    while len(pool.code) % 16:
        pool.emit(b"\xCC")

    # ---- 4. stubs ---------------------------------------------------------
    win_rows = []
    insn_rows = []
    site_rows = {}
    no_sample = collections.Counter()
    slot_i = 0
    for wi, (w_lo, w_hi, rvas, run) in enumerate(windows):
        stub = pool.here()
        here_sites = set(rvas)
        slot = None
        if is_call(run[-1]):
            slot = slot_off + slot_i * 8
            pool.fixups.append((slot, 0, w_hi))
            slot_i += 1
        dead = False
        for k, ins in enumerate(run):
            if dead:
                continue
            start_here = pool.here()
            plan = None
            transfer = (ins.mnemonic in UNCOND or is_call(ins)
                        or capstone.CS_GRP_JUMP in ins.groups)
            is_site = ins.address in here_sites
            if is_site:
                rec = rec_off + rec_index[ins.address] * REC_SIZE
                if transfer:
                    # nothing after a call or jump runs in the stub: count first
                    no_sample["control transfer"] += 1
                    emit_post(pool, None, rec, common)
                    site_rows[ins.address] = (wi, 0, KIND_COUNT)
                else:
                    plan, why = sample_plan(ins)
                    if plan == 0:
                        plan = None
                        no_sample[why] += 1
                    if plan:
                        emit_pre(pool, plan, rec)
            if k:
                insn_rows.append((ins.address, start_here))
            emit_relocated(pool, ins, slot)
            if is_site and not transfer:
                emit_post(pool, plan, rec, common)
                site_rows[ins.address] = (wi, plan[0] if plan else 0,
                                          kind_of(ins) if plan else KIND_COUNT)
            if ins.mnemonic in UNCOND or is_call(ins):
                dead = True
        if not dead:
            pool.game_rel32(b"\xE9", w_hi)
        win_rows.append((w_lo, stub, w_hi - w_lo))
        while len(pool.code) % 4:
            pool.emit(b"\xCC")

    pool_size = pool.here()
    # ---- 5. self-check: every stub decodes cleanly ------------------------
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = bytes(pool.code)
    pos, bad = 0, 0
    while pos < len(code):
        got = False
        for a, s, mn, op in md.disasm_lite(code[pos:pos + 4096], pos):
            pos = a + s
            got = True
        if not got:
            bad += 1
            pos += 1
    assert bad == 0, "%d undecodable bytes in the pool" % bad

    # ---- 6. outputs -------------------------------------------------------
    orig = bytearray()
    subs = sorted({site_info[r]["sub"] for r in ordered})
    sub_index = {s: i for i, s in enumerate(subs)}
    os.makedirs(os.path.dirname(OUT_H), exist_ok=True)
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generated by tools/gen_tracer.py -- do not edit.\n")
        f.write("// main.dll sha1 %s; %d sites in %d windows.\n" % (sha, len(ordered), len(windows)))
        f.write("#pragma once\n#include <cstdint>\n\n")
        f.write('#define TRACER_MAIN_SHA1 "%s"\n' % sha)
        f.write("static const uint32_t kTracerRecSize = 0x%X;\n" % REC_SIZE)
        f.write("static const uint32_t kTracerSlotOffset = 0x%X;\n" % slot_off)
        f.write("static const uint32_t kTracerCodeOffset = 0x%X;\n" % code_off)
        f.write("static const uint32_t kTracerPoolSize = 0x%X;\n" % pool_size)
        f.write("static const uint32_t kTracerCommon = 0x%X;\n" % common)
        f.write("static const uint32_t kTracerFrameCounterRva = 0x%X;\n" % FRAME_COUNTER)
        f.write("static const uint32_t kTracerModeRva = 0x%X;\n\n" % MODE_BYTE)
        f.write("static const unsigned char kTracerCode[] = {\n")
        for i in range(0, len(code), 32):
            f.write(",".join("0x%02X" % x for x in code[i:i + 32]) + ",\n")
        f.write("};\n\n")
        f.write("struct TracerFixup { uint32_t field; uint32_t next; uint32_t target; };"
                "  // next == 0: 8-byte absolute\n")
        f.write("static const TracerFixup kTracerFixups[] = {\n")
        for fld, nxt, tgt in pool.fixups:
            f.write("{0x%X,0x%X,0x%X},\n" % (fld, nxt, tgt))
        f.write("};\n\n")
        f.write("struct TracerWindow { uint32_t rva; uint32_t stub; uint32_t orig; uint32_t len; };\n")
        f.write("static const TracerWindow kTracerWindows[] = {\n")
        for w_lo, stub, ln in win_rows:
            f.write("{0x%X,0x%X,0x%X,%d},\n" % (w_lo, stub, len(orig), ln))
            orig += img[w_lo:w_lo + ln]
        f.write("};\n\n")
        f.write("static const unsigned char kTracerOrig[] = {\n")
        for i in range(0, len(orig), 32):
            f.write(",".join("0x%02X" % x for x in orig[i:i + 32]) + ",\n")
        f.write("};\n\n")
        f.write("// kind: 0 int, 1 float (xmm), 2 x87, 3 count only (no sample)\n")
        f.write("struct TracerSite { uint32_t rva; uint32_t window; uint8_t sample;"
                " uint8_t kind; uint16_t sub; };\n")
        f.write("static const TracerSite kTracerSites[] = {\n")
        for rva in ordered:
            wi, sz, kind = site_rows[rva]
            f.write("{0x%X,%d,%d,%d,%d},\n" % (rva, wi, sz, kind, sub_index[site_info[rva]["sub"]]))
        f.write("};\n\n")
        f.write("static const char* const kTracerSubsystems[] = {\n")
        for s in subs:
            f.write('"%s",\n' % s)
        f.write("};\n\n")
        f.write("// every instruction start inside a window after its first, for the int3 net\n")
        f.write("struct TracerInsn { uint32_t rva; uint32_t stub; };\n")
        f.write("static const TracerInsn kTracerInsns[] = {\n")
        for rva, st in sorted(insn_rows):
            f.write("{0x%X,0x%X},\n" % (rva, st))
        f.write("};\n")

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["site", "subsystem", "shape", "window", "window_len", "sample", "kind",
                     "refused"])
        wi_of = {}
        for wi, (w_lo, _s, ln) in enumerate(win_rows):
            wi_of[wi] = (w_lo, ln)
        for s in sites:
            rva = s["rva"]
            if rva in site_rows:
                wi, sz, kind = site_rows[rva]
                w_lo, ln = wi_of[wi]
                wr.writerow(["%06X" % rva, s["sub"], s["shape"], "%06X" % w_lo, ln, sz,
                             "int float x87 count".split()[kind], ""])
            else:
                wr.writerow(["%06X" % rva, s["sub"], s["shape"], "", "", "", "",
                             refused.get(rva, "?")])

    print("\nwindows: %d holding %d sites (%d merged into a shared window)"
          % (len(windows), len(ordered), len(ordered) - len(windows)))
    print("refused: %d" % len(refused))
    for why, n in collections.Counter(refused.values()).most_common():
        print("  %5d  %s" % (n, why))
    print("count only (no value sample): %d" % sum(no_sample.values()))
    for why, n in no_sample.most_common():
        print("  %5d  %s" % (n, why))
    lens = collections.Counter(ln for _a, _b, ln in win_rows)
    print("window lengths: %s" % ", ".join("%d:%d" % kv for kv in sorted(lens.items())))
    print("calls at a window end: %d" % nslots)
    print("pool: %d KB (records %d KB, code %d KB), %d fixups"
          % (pool_size // 1024, len(ordered) * REC_SIZE // 1024, len(code) // 1024,
             len(pool.fixups)))
    by_sub = collections.Counter(site_info[r]["sub"].split(":")[0] for r in ordered)
    all_sub = collections.Counter(s["sub"].split(":")[0] for s in sites)
    print("coverage by subsystem:")
    for k in sorted(all_sub):
        print("  %-18s %5d / %5d" % (k, by_sub.get(k, 0), all_sub[k]))
    print("\nwrote %s\nwrote %s" % (os.path.relpath(OUT_H, ROOT), os.path.relpath(OUT_CSV, ROOT)))


if __name__ == "__main__":
    main()
