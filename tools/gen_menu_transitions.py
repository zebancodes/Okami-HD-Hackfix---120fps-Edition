#!/usr/bin/env python3
"""Generate M2's first family: the menu transitions.

The transitions still seen running fast at 120 fps (2026-09-23):

  * the scene transition (B4DF40, 4396F0): the model that slides in, glides
    and fades around every options page, the memory card and area changes;
  * the pause menu's opening drop (415B30), a bounce that settles the menu;
  * the HUD fade (cCockBase slot 3, 3F6660), which slides HUD elements;
  * the pause menu's page-icon pulse (4127F0).

Each site is in MANIFEST with the reason it is a per-tick quantity, read from
the code (docs/animation/README.md, "Menu changes at 4x"). Nothing is selected by shape. The
generator proves every site against the binary before emitting it:

  lin    `op xmm, [rip+K]`, 8 bytes: the displacement is pointed at a pool
         slot holding K*s, s being the share of a stock tick a tick is worth
         (1/N). The phase-step mechanism, in this family's own pool.
  exp    the same for a per-tick factor: the slot holds K**s.
  src    `op xmmD, src` whose source is this tick's step: a detour runs
         `movss/movaps xmmT, src; mulss xmmT, [s]; op xmmD, xmmT`, with xmmT a
         volatile register proven dead after the site on every path.
  dst    `movaps xmmD, xmmS` whose result is only this tick's step, consumed
         by the next accumulation: a detour scales xmmD after the copy.
  count  an integer counter step (inc/dec), skipped on the ticks between stock
         ticks, exactly as F1 (gen_integer_skips.emit_gate). A register
         counter must provably load and store the same field, alias included.
  gatefn a whole update function that runs only on stock ticks. For the pause
         drop, per-instruction scaling changes its bounces: stock takes 18
         ticks and bounces 3 times; scaled, 21 and 4. Its callers must not use
         a return value.

Pool layout: [0] the stock-tick mask (0/1/3, as F1), [4] s as a float,
[0x10] per-site counters {ticks, counted, last tick, passes} for the count
and gatefn sites, [0x80] the literal slots, code from 0x100. All of it is data
the runtime keeps from the stock context each tick; at N = 1 (30 fps, F9, the
phase key muted) every stub is the original code.

    .venv/Scripts/python tools/gen_menu_transitions.py
"""
import bisect
import collections
import csv
import os
import struct

from capstone import x86_const as X

import gen_tracer as tr
import gen_integer_skips as gis

ROOT = tr.ROOT
DOCS = os.path.join(ROOT, "docs", "animation")
OUT_H = os.path.join(ROOT, "src", "menu_transitions.h")
OUT_CSV = os.path.join(DOCS, "menu_transitions.csv")
AUDITED_MAIN_SHA1 = "703d292ab2cb50cc9e237e44722dec51d956b79c"

MASK_OFFSET, SCALE_OFFSET, COUNTER_OFFSET, SLOT = 0, 4, 0x10, 16
LITERAL_OFFSET, CODE_OFFSET = 0x80, 0x100
MAX_COUNTERS = (LITERAL_OFFSET - COUNTER_OFFSET) // SLOT
MAX_LITERALS = (CODE_OFFSET - LITERAL_OFFSET) // 4
KIND = {"lin": 0, "exp": 1, "src": 2, "dst": 3, "count": 4, "gatefn": 5}

# The emitted count gate is F1's, reading this family's own pool offsets.
assert gis.MASK_OFFSET == MASK_OFFSET and gis.COUNTER_OFFSET == COUNTER_OFFSET and gis.SLOT == SLOT

# (kind, rva, instruction as capstone prints it, extra, reason)
#   lin/exp: extra = (constant rva, value)
#   count:   extra = None for a memory counter, or (load rva, store rva,
#            path from load to store, alias instruction or None)
MANIFEST = [
    # --- the scene transition, B4DF40 (4396F0) ---------------------------
    ("src", 0x439A79, "addss xmm0, dword ptr [rbx + 0x18]", None,
     "scene transition slide (439A50): model x += v(+18) a tick until x <= 25; "
     "v = -4.25 from 439910"),
    ("src", 0x4397D9, "addss xmm0, dword ptr [rbx + 0x18]", None,
     "scene transition glide (4397B0): model x += v(+18) a tick while v decays"),
    ("dst", 0x43983E, "movaps xmm1, xmm2", None,
     "glide: +8 += +1C a tick (680 falling to 0); xmm1 is that step only, "
     "xmm2 goes on to the decay"),
    ("lin", 0x4397FC, "mulss xmm1, dword ptr [rip + 0x278bec]", (0x6B23F0, -0.024),
     "glide: model animation rate(+F54) -= v * 0.024 a tick"),
    ("exp", 0x439884, "mulss xmm2, dword ptr [rip + 0x278b60]", (0x6B23EC, 0.936),
     "glide: +1C *= 0.936 a tick (its sibling +18 is decay_factors 43987C)"),
    ("count", 0x439855, "inc word ptr [rbx + 0x20]", None,
     "glide length: 28 ticks (> 0x1B); F1 refuses it alone because the glide's "
     "displacement was unscaled, and this family scales it"),
    ("lin", 0x439AFE, "addss xmm0, dword ptr [rip + 0x23bf82]", (0x675A88, 14.0),
     "scene transition fade (439AD0 state 3): +C += 14 a tick to 64"),
    ("lin", 0x439BE5, "addss xmm0, dword ptr [rip + 0x23be9b]", (0x675A88, 14.0),
     "the same step in 439BE0"),
    # --- the pause menu -----------------------------------------------------
    ("gatefn", 0x415B30, "mov rax, qword ptr [rcx + 8]", None,
     "pause menu drop (415B30, state 1 of 415A60): v(+90) += 6, p(+8C) += 2v, "
     "bounce -0.43 at p > 0, settles below |v| = 3 and switches the menu to its "
     "60 Hz context; runs whole on stock ticks (scaled: 21 ticks and 4 bounces "
     "against stock 18 and 3)"),
    ("lin", 0x412867, "addss xmm6, dword ptr [rip + 0x265c59]", (0x6784C8, 0.15),
     "pause menu page-icon pulse (4127F0, called every tick by the menu): "
     "phase(+88) += 0.15 through the angle wrap 13F2E0, scale 1 + 0.1 sin"),
    # --- the HUD fade, cCockBase slot 3 --------------------------------------
    ("count", 0x3F66A2, "inc ax",
     (0x3F6693, 0x3F66A5, (0x3F6693, 0x3F6697, 0x3F6699, 0x3F669D, 0x3F66A0, 0x3F66A2),
      0x3F666F),
     "HUD fade in (3F6660): fade(+5A) += 1 a tick up to its length(+58); every "
     "element's position is lerped by fade / length"),
    ("count", 0x3F66BD, "dec ax",
     (0x3F6693, 0x3F66C0, (0x3F6693, 0x3F6697, 0x3F66B8, 0x3F66BB, 0x3F66BD), None),
     "HUD fade out (3F6660): fade(+5A) -= 1 a tick down to 0"),
]

VOLATILE_TEMPS = ("xmm5", "xmm4")   # never call arguments, never return values
FULL_WRITES = {"movaps", "movups", "movdqa", "movdqu", "movapd", "movupd"}
SCALAR_READERS = {"addss", "subss", "comiss", "ucomiss"}


def xmm_index(name):
    return int(name[3:]) if name.startswith("xmm") else None


def containing_function(begins, rva):
    i = bisect.bisect_right(begins, rva) - 1
    return begins[i] if i >= 0 else None


def reads_writes(ins):
    r, w = ins.regs_access()
    return {ins.reg_name(x) for x in r}, {ins.reg_name(x) for x in w}


def full_write(ins, reg):
    """True if the instruction overwrites all of xmm `reg` without reading it."""
    ops = ins.operands
    if not ops or ops[0].type != X.X86_OP_REG or ins.reg_name(ops[0].reg) != reg:
        return False
    mn = ins.mnemonic
    if mn in FULL_WRITES:
        return len(ops) == 2 and not (ops[1].type == X.X86_OP_REG and ins.reg_name(ops[1].reg) == reg)
    if mn in ("movss", "movsd") and len(ops) == 2 and ops[1].type == X.X86_OP_MEM:
        return True   # the load zeroes the upper lanes
    if mn in ("xorps", "xorpd", "pxor") and len(ops) == 2 and ops[1].type == X.X86_OP_REG and \
            ins.reg_name(ops[1].reg) == reg:
        return True
    return False


def xmm_dead_after(dec, ins, reg, bound=200):
    """Prove `reg` is not read after `ins` on any path before it is rewritten.

    Paths end at a full rewrite, a call (it clobbers the volatile register and
    passes no argument in it: VOLATILE_TEMPS are never argument registers) or
    a ret (they are never return values). Any read first, an indirect jump or
    a path too long to follow is a refusal."""
    work, seen = [ins.address + ins.size], set()
    while work:
        at = work.pop()
        if at in seen:
            continue
        seen.add(at)
        if len(seen) > bound:
            return "liveness of %s exceeds the bound" % reg
        seq = dec.run(at, at)
        if not seq or seq[0].address != at:
            return "cannot decode %X for %s liveness" % (at, reg)
        i = seq[0]
        if i.mnemonic in ("call", "ret"):
            continue
        if i.mnemonic in ("int3", "ud2"):
            return "path reaches padding at %X" % at
        rd, _wr = reads_writes(i)
        if full_write(i, reg):
            continue
        if reg in rd:
            return "%s read at %X %s %s" % (reg, at, i.mnemonic, i.op_str)
        if i.mnemonic == "jmp":
            if not tr.is_rel_branch(i):
                return "indirect jump at %X" % at
            work.append(i.operands[0].imm)
            continue
        if i.mnemonic.startswith("j"):
            if not tr.is_rel_branch(i):
                return "indirect branch at %X" % at
            work.append(i.operands[0].imm)
        work.append(at + i.size)
    return None


def scalar_step_consumer(dec, ins, reg):
    """For `dst`: the copy's first reader must be a scalar accumulation of it
    (`addss/subss reg, x`), and nothing may read `reg` before that. An
    unconditional `jmp` on the way is followed (33DEF4's -0.03 joins the
    +0.03 branch at the accumulation)."""
    at = ins.address + ins.size
    for _ in range(12):
        seq = dec.run(at, at)
        i = seq[0]
        rd, wr = reads_writes(i)
        if reg in rd:
            ops = i.operands
            if i.mnemonic in ("addss", "subss") and ops[0].type == X.X86_OP_REG and \
                    i.reg_name(ops[0].reg) == reg:
                return None
            return "first reader of %s at %X is %s %s" % (reg, at, i.mnemonic, i.op_str)
        if reg in wr:
            return "%s rewritten at %X before any accumulation" % (reg, at)
        if i.mnemonic == "jmp" and tr.is_rel_branch(i):
            at = i.operands[0].imm
            continue
        if i.mnemonic.startswith("j") or i.mnemonic in ("call", "ret"):
            return "control flow at %X before the accumulation" % at
        at += i.size
    return "no accumulation of %s within 12 instructions" % reg


def direct_sources(img, lo, hi):
    """({target: [(source, size, mnemonic)]} for every direct jump and call,
    the targets of `lea reg, [rip+X]` into .text: code pointers taken)."""
    out = collections.defaultdict(list)
    leas = set()
    md = tr.capstone.Cs(tr.capstone.CS_ARCH_X86, tr.capstone.CS_MODE_64)
    pos = lo
    while pos < hi:
        end = min(hi, pos + 0x10000)
        last = pos
        for a, s, mn, op in md.disasm_lite(bytes(img[pos:end + 16]), pos):
            if a >= end:
                break
            last = a + s
            if (mn[0] == "j" or mn == "call") and op.startswith("0x"):
                out[int(op, 16)].append((a, s, mn))
            elif mn == "lea" and "rip" in op:
                g = tr.RIPLEA.search(op)
                if g:
                    d = int(g.group(2), 0)
                    t = a + s + (d if g.group(1) == "+" else -d)
                    if lo <= t < hi:
                        leas.add(t)
        pos = last if last > pos else pos + 1
    return out, leas


def unwind_entries(img, secs):
    """.pdata begins that are real entries: chained unwind fragments (the
    UNW_FLAG_CHAININFO ranges a prologue splits off) are not."""
    a, b = secs[".pdata"]
    entries = set()
    for off in range(a, b - 11, 12):
        begin, _end, unwind = struct.unpack_from("<III", img, off)
        if begin == 0 and _end == 0:
            break
        if not (img[unwind] >> 3) & 4:
            entries.add(begin)
    return entries


def unwind_chain_fields(img, secs):
    """.rdata offsets of the RUNTIME_FUNCTION copies inside chained UNWIND_INFO
    records: a fragment's record names its parent's range there, which is
    unwind data, not a code pointer."""
    a, b = secs[".pdata"]
    fields = set()
    for off in range(a, b - 11, 12):
        begin, end, unwind = struct.unpack_from("<III", img, off)
        if begin == 0 and end == 0:
            break
        if (img[unwind] >> 3) & 4:
            codes = img[unwind + 2]
            chained = unwind + 4 + 2 * (codes + (codes & 1))
            fields.update((chained, chained + 4, chained + 8))
    return fields


def code_pointers(img, secs, lo, hi, starts):
    """tr.data_references without the chained unwind records' fields."""
    skip = unwind_chain_fields(img, secs)
    found = set()
    for name in (".rdata", ".data"):
        a, b = secs[name]
        for off in range((a + 3) & ~3, b & ~3, 4):
            v = struct.unpack_from("<I", img, off)[0]
            if lo <= v < hi and starts[v] and off not in skip:
                found.add(v)
        for off in range((a + 7) & ~7, b & ~7, 8):
            v = struct.unpack_from("<Q", img, off)[0] - tr.BASE
            if lo <= v < hi and starts[v]:
                found.add(v)
    return found


def function_entry(dec, starts, sources, rva):
    """A function entry without unwind data (a leaf): called directly, and
    after padding or an unconditional transfer."""
    if not any(mn == "call" for _a, _s, mn in sources.get(rva, [])):
        return "not a direct call target"
    phys = physical_predecessor(dec, starts, rva)
    if phys is not None and phys.mnemonic not in tr.UNCOND | tr.PADDING:
        return "falls through from %X %s" % (phys.address, phys.mnemonic)
    return None


def rax_unused_after_calls(dec, sources, fn):
    """Every direct call to `fn` must leave rax unread until it is rewritten:
    the stock-tick gate returns without running the body."""
    md_calls = sources.get(fn, [])
    if not md_calls:
        return None, "no direct caller found"
    rax = {"rax", "eax", "ax", "al", "ah"}
    for a, s, mn in md_calls:
        if mn == "jmp":
            return None, "tail jump to it at %X" % a
        # every path from the call, both sides of each conditional branch,
        # must rewrite rax (or call, or return) before anything reads it
        todo, seen, steps = [a + s], set(), 0
        while todo:
            at = todo.pop()
            if at in seen:
                continue
            seen.add(at)
            steps += 1
            if steps > 48:
                return None, "rax liveness after the call at %X exceeds the bound" % a
            i = dec.run(at, at)[0]
            rd, wr = reads_writes(i)
            if i.mnemonic == "nop":
                rd = set()          # a multi-byte nop's operand is never read
            if rd & rax:
                return None, "rax read at %X after the call at %X" % (at, a)
            if wr & rax or i.mnemonic in ("call", "ret"):
                continue
            if i.mnemonic == "jmp" and tr.is_rel_branch(i):
                todo.append(i.operands[0].imm)
                continue
            if i.mnemonic.startswith("j"):
                if not tr.is_rel_branch(i):
                    return None, "indirect branch at %X before rax is rewritten" % at
                todo += [i.operands[0].imm, at + i.size]
                continue
            todo.append(at + i.size)
    return [a for a, _s, _m in md_calls], None


def physical_predecessor(dec, starts, a):
    """The instruction that ends exactly at `a`, from the linear sweep."""
    for back in range(1, 16):
        p = a - back
        if p >= 0 and starts[p]:
            i = dec.run(p, p)[0]
            if i.address + i.size == a:
                return i
    return None


def entered_only_from(dec, starts, sources, indirect, prev, a, also=()):
    """None if `a` can only be reached from the path's previous instruction
    (or from an instruction in `also`)."""
    if a in indirect:
        return "%X is an indirect branch destination" % a
    for src, _s, mn in sources.get(a, []):
        if src != prev.address and src not in also:
            return "%X is also entered by the %s at %X" % (a, mn, src)
    phys = physical_predecessor(dec, starts, a)
    if phys is not None and phys.address != prev.address and phys.address not in also and \
            phys.mnemonic not in tr.UNCOND:
        return "%X is also entered by falling through %X" % (a, phys.address)
    return None


def counter_store_entry(dec, step, store_at):
    """The instruction that hands a register counter's step to its store:
    the step itself when the store follows it, or a `jmp store` right after
    it (two counters sharing one store, 1C8D80's inc and dec). None if
    neither."""
    if step.address + step.size == store_at:
        return step
    j = dec.run(step.address + step.size, step.address + step.size)
    if j and j[0].mnemonic == "jmp" and tr.is_rel_branch(j[0]) and \
            j[0].operands[0].imm == store_at:
        return j[0]
    return None


def prove_register_counter(dec, starts, sources, indirect, step, extra, joins=()):
    """A register counter (`inc ax` .. `mov [B + d], ax`) must store back the
    field it loaded, along an explicit path the manifest names. Each step of
    the path is proven: fall-through or the taken side of a branch; every
    branch target on it is entered only from the path; the counting register
    and the store's base are written by nothing but the load and the step,
    and the store's base is the load's, or a copy of it made earlier by
    `mov Bstore, Bload` with neither written since. The store follows the
    step, or a `jmp` to it does; it may also be entered from `joins`, the
    store entries of other counter rows the caller proves on the same store."""
    load_at, store_at, path, alias_at = extra
    if path[0] != load_at or path[-1] != step.address:
        return "path must run from the load to the step"
    seq = [dec.run(a, a)[0] for a in path] + [dec.run(store_at, store_at)[0]]
    load, store = seq[0], seq[-1]
    if load.mnemonic not in ("movzx", "mov") or load.operands[1].type != X.X86_OP_MEM:
        return "load at %X is not a field load" % load_at
    if store.mnemonic != "mov" or store.operands[0].type != X.X86_OP_MEM or \
            store.operands[1].type != X.X86_OP_REG:
        return "store at %X is not a plain store" % store_at
    entry = counter_store_entry(dec, step, store_at)
    if entry is None:
        return "store does not follow the step"
    if entry is not step:
        seq.insert(-1, entry)
    lm, sm = load.operands[1].mem, store.operands[0].mem
    if lm.index or sm.index or lm.disp != sm.disp or load.operands[1].size != store.operands[0].size:
        return "load and store are not the same field shape"
    cnt = gis.canon(step, step.operands[0].reg)
    if gis.canon(load, load.operands[0].reg) != cnt or gis.canon(store, store.operands[1].reg) != cnt:
        return "load, step and store do not use one register"
    lbase, sbase = gis.canon(load, lm.base), gis.canon(store, sm.base)
    for k in range(len(path) - 1):
        i, nxt = seq[k], path[k + 1]
        if i.address + i.size == nxt:
            continue
        if i.mnemonic.startswith("j") and tr.is_rel_branch(i) and i.operands[0].imm == nxt:
            continue
        return "path breaks between %X and %X" % (i.address, nxt)
    for k in range(1, len(seq)):
        why = entered_only_from(dec, starts, sources, indirect, seq[k - 1], seq[k].address,
                                joins if k == len(seq) - 1 else ())
        if why:
            return why
    for i in seq[1:-1]:
        _rd, wr = reads_writes(i)
        wr = {gis.REG64.get(r, r) for r in wr}
        if i.address != step.address and cnt in wr:
            return "counting register written at %X" % i.address
        if sbase in wr:
            return "store base %s written at %X" % (sbase, i.address)
        if i.mnemonic == "call":
            return "call on the path at %X" % i.address
    if lbase != sbase:
        if alias_at is None:
            return "store base %s is not the load base %s" % (sbase, lbase)
        al = dec.run(alias_at, alias_at)[0]
        if al.mnemonic != "mov" or len(al.operands) != 2 or \
                gis.canon(al, al.operands[0].reg) != sbase or gis.canon(al, al.operands[1].reg) != lbase:
            return "alias at %X is not mov %s, %s" % (alias_at, sbase, lbase)
        if not alias_at < load_at:
            return "alias must precede the load"
        # straight line from the alias to the load, both bases untouched and
        # nothing entering between them
        prev, at = al, alias_at + al.size
        while at <= load_at:
            why = entered_only_from(dec, starts, sources, indirect, prev, at)
            if why:
                return "alias: " + why
            i = dec.run(at, at)[0]
            if at == load_at:
                break
            _rd, wr = reads_writes(i)
            wr = {gis.REG64.get(r, r) for r in wr}
            # a conditional exit leaves the path without touching a register
            if wr & {lbase, sbase} or i.mnemonic in ("call", "ret", "jmp"):
                return "alias broken at %X" % at
            prev, at = i, at + i.size
    return None


def reencode_load(ins, temp):
    """`op xmmD, m32` -> `movss xmmT, m32`: the same operand bytes."""
    b = bytearray(ins.bytes)
    if b[0] != 0xF3:
        return None, "not an F3-prefixed scalar op"
    k = 1
    rexb = None
    if 0x40 <= b[k] <= 0x4F:
        rexb, k = b[k], k + 1
    if b[k] != 0x0F:
        return None, "unexpected opcode map"
    modrm = b[k + 2]
    if (modrm >> 6) == 0 and (modrm & 7) == 5:
        return None, "rip-relative source"
    t = xmm_index(temp)
    out = bytearray([0xF3])
    rex = (rexb or 0x40) & ~0x04 | (0x04 if t >= 8 else 0)
    if rex != 0x40:
        out.append(rex)
    out += bytes([0x0F, 0x10, (modrm & 0xC7) | ((t & 7) << 3)]) + b[k + 3:]
    return bytes(out), None


def enc_rr(opcode, dst, src, prefix=b"\xF3"):
    """`op xmmD, xmmS` (scalar with F3, packed moves without)."""
    d, s = xmm_index(dst), xmm_index(src)
    rex = 0x40 | (0x04 if d >= 8 else 0) | (0x01 if s >= 8 else 0)
    return prefix + (bytes([rex]) if rex != 0x40 else b"") + bytes([0x0F, opcode, 0xC0 | ((d & 7) << 3) | (s & 7)])


def emit_mulss_scale(pool, reg):
    r = xmm_index(reg)
    pool.pool_rel32(b"\xF3" + (b"\x44" if r >= 8 else b"") + bytes([0x0F, 0x59, ((r & 7) << 3) | 5]),
                    SCALE_OFFSET)


OPCODE = {"addss": 0x58, "subss": 0x5C, "mulss": 0x59}


def emit_src(pool, ins, temp):
    ops = ins.operands
    dst = ins.reg_name(ops[0].reg)
    if ops[1].type == X.X86_OP_MEM:
        load, why = reencode_load(ins, temp)
        if why:
            raise RuntimeError("%X: %s" % (ins.address, why))
        pool.emit(load)
    else:
        pool.emit(enc_rr(0x28, temp, ins.reg_name(ops[1].reg), prefix=b""))   # movaps
    emit_mulss_scale(pool, temp)
    pool.emit(enc_rr(OPCODE[ins.mnemonic], dst, temp))


def emit_dst(pool, ins):
    tr.emit_relocated(pool, ins, None)
    emit_mulss_scale(pool, ins.reg_name(ins.operands[0].reg))


def emit_fn_gate(pool, counter):
    """At a function's entry: count as F1 does, then return at once on a tick
    between stock ticks. Flags are dead at a call boundary; rax is saved."""
    slot = COUNTER_OFFSET + SLOT * counter

    def jcc8(opcode):
        pool.emit(bytes([opcode, 0]))
        return len(pool.code)

    def land(at):
        pool.code[at - 1] = len(pool.code) - at

    pool.emit(b"\x50")                                           # push rax
    pool.pool_rel32(b"\xFF\x05", slot + gis.PASSES)
    pool.game_rel32(b"\x8B\x05", tr.FRAME_COUNTER)               # mov eax, [fc]
    pool.pool_rel32(b"\x3B\x05", slot + gis.LAST_TICK)
    same = jcc8(0x74)
    pool.pool_rel32(b"\x89\x05", slot + gis.LAST_TICK)
    pool.pool_rel32(b"\xFF\x05", slot + gis.TICKS)
    pool.pool_rel32(b"\x84\x05", MASK_OFFSET)
    skipped = jcc8(0x75)
    pool.pool_rel32(b"\xFF\x05", slot + gis.COUNTED)
    land(same)
    land(skipped)
    pool.pool_rel32(b"\x84\x05", MASK_OFFSET)                    # test [mask], al
    pool.emit(b"\x58")                                           # pop rax
    run = jcc8(0x74)                                             # jz body
    pool.emit(b"\xC3")                                           # ret: not a stock tick
    land(run)


def main():
    img, secs, begins, sha = tr.load_image()
    if sha != AUDITED_MAIN_SHA1:
        raise RuntimeError("main.dll %s is not the audited build %s" % (sha, AUDITED_MAIN_SHA1))
    begins = sorted(begins)
    lo, hi = secs[".text"]
    starts, targets, switch, _tables = tr.global_pass(img, lo, hi)
    sources, leas = direct_sources(img, lo, hi)
    # entered other than by a direct branch: switch destinations, code
    # pointers in data or taken by lea, and the unwind data's real entries
    indirect = switch | code_pointers(img, secs, lo, hi, starts) | leas |         unwind_entries(img, secs)
    # windows keep the tracer's conservative set: every pdata range start too
    targets |= indirect | set(begins) | tr.data_references(img, secs, lo, hi, starts)
    dec = tr.Decoder(img, starts)
    protected = [r for r in gis.patched_ranges() if "menu_transitions" not in r[2]]
    import check_patch_sites as cps
    for a, raw, label in cps.turn_callers():
        protected.append((a, a + len(raw), label))
    for a, raw, label in cps.day_clock():
        protected.append((a, a + len(raw), label))
    # literal sites are rewritten in place: no window may carry one away
    own_literals = [(rva, rva + 8, "menu_transitions literal")
                    for kind, rva, *_ in MANIFEST if kind in ("lin", "exp")]

    rows, literals, detours = [], [], []
    for kind, rva, text, extra, reason in MANIFEST:
        row = dict(site="%X" % rva, kind=kind, instruction=text, reason=reason,
                   function="", status="refused", proof="", window="", stub="", temp="")
        rows.append(row)
        fn = rva if kind == "gatefn" else containing_function(begins, rva)
        row["function"] = "%X" % fn if fn is not None else ""
        insns, idx = dec.around(rva, fn, rva) if fn is not None else (None, None)
        if insns is None:
            row["proof"] = "not a decoded instruction"
            continue
        ins = insns[idx]
        got = "%s %s" % (ins.mnemonic, ins.op_str)
        if got != text:
            row["proof"] = "instruction is %s" % got
            continue
        for a, b, what in protected:
            if a < rva + ins.size and rva < b:
                row["proof"] = "already patched by " + what
                break
        if row["proof"]:
            continue
        if kind in ("lin", "exp"):
            const_rva, want = extra
            mem = next((op.mem for op in ins.operands if op.type == X.X86_OP_MEM), None)
            if ins.size != 8 or mem is None or mem.base != X.X86_REG_RIP or ins.disp_offset != 4:
                row["proof"] = "not the 8-byte rip form"
                continue
            if ins.address + ins.size + mem.disp != const_rva:
                row["proof"] = "reads %X, not %X" % (ins.address + ins.size + mem.disp, const_rva)
                continue
            value = struct.unpack_from("<f", img, const_rva)[0]
            if struct.pack("<f", value) != struct.pack("<f", want):
                row["proof"] = "constant is %r, not %r" % (value, want)
                continue
            literals.append(dict(rva=rva, const=const_rva, kind=KIND[kind],
                                 orig=bytes(ins.bytes), row=row))
            row.update(status="selected", proof="%s = %g at %X" % (
                "K*s" if kind == "lin" else "K**s", value, const_rva))
            continue
        info = dict(site=rva, kind=kind, ins=ins, row=row, temp=None, flags=0, counter=None)
        if kind == "src":
            last = None
            for temp in VOLATILE_TEMPS:
                last = xmm_dead_after(dec, ins, temp)
                if last is None:
                    info["temp"] = temp
                    break
            if info["temp"] is None:
                row["proof"] = last
                continue
            if ins.operands[1].type == X.X86_OP_MEM:
                _b, why = reencode_load(ins, info["temp"])
                if why:
                    row["proof"] = why
                    continue
            row["temp"] = info["temp"]
            row["proof"] = "%s dead after the site on every path" % info["temp"]
        elif kind == "dst":
            why = scalar_step_consumer(dec, ins, ins.reg_name(ins.operands[0].reg))
            if why:
                row["proof"] = why
                continue
            row["proof"] = "the copy's first reader is its accumulation"
        elif kind == "count":
            step = ins
            if extra is None:
                if step.operands[0].type != X.X86_OP_MEM:
                    row["proof"] = "memory counter expected"
                    continue
                skip = b""
            else:
                why = prove_register_counter(dec, starts, sources, indirect, step, extra)
                if why:
                    row["proof"] = why
                    continue
                skip = b""
            delta = 1 if step.mnemonic == "inc" else -1
            flags, why = gis.flag_policy(dec, step, delta)
            if flags is None:
                row["proof"] = why
                continue
            info["flags"], info["skip"] = flags, skip
            row["proof"] = why + ("" if extra is None else "; load %X and store %X one field" % extra[:2])
        elif kind == "gatefn":
            why = function_entry(dec, starts, sources, rva)
            if why:
                row["proof"] = why
                continue
            callers, why = rax_unused_after_calls(dec, sources, rva)
            if why:
                row["proof"] = why
                continue
            row["proof"] = "entry; callers %s ignore rax" % ", ".join("%X" % c for c in callers)
        if kind == "gatefn":
            # the gate must sit at the entry itself: extend forward only
            a, b = idx, idx
            while insns[b].address + insns[b].size - insns[a].address < 5:
                b += 1
            why = tr.window_problem(insns[a:b + 1], targets - {rva}, protected + own_literals)
        else:
            a, b, why = tr.find_window(insns, idx, targets, protected + own_literals)
        if why:
            row["proof"] += "; window: " + why
            continue
        run = insns[a:b + 1]
        # the temp must stay dead across the rest of the window too: the
        # liveness walk starts right after the site, so it covers it
        info.update(run=run, lo=run[0].address, hi=run[-1].address + run[-1].size)
        detours.append(info)
        row["status"] = "selected"

    # one window per run of instructions; overlapping picks merge
    windows = []
    for d in sorted(detours, key=lambda d: (d["lo"], d["hi"])):
        if windows and d["lo"] < windows[-1]["hi"]:
            w = windows[-1]
            merged = {i.address: i for i in w["run"] + d["run"]}
            run = [merged[x] for x in sorted(merged)]
            why = tr.window_problem(run, targets, protected + own_literals)
            if why or any(x.address + x.size != y.address for x, y in zip(run, run[1:])):
                raise RuntimeError("cannot merge windows at %X: %s" % (d["lo"], why))
            w.update(hi=max(w["hi"], d["hi"]), run=run)
            w["sites"].append(d)
        else:
            windows.append(dict(lo=d["lo"], hi=d["hi"], run=d["run"], sites=[d]))
    counters = [d for w in windows for d in w["sites"] if d["kind"] in ("count", "gatefn")]
    if len(counters) > MAX_COUNTERS:
        raise RuntimeError("more counter sites than slots")
    if len(literals) > MAX_LITERALS:
        raise RuntimeError("more literals than slots")
    for n, d in enumerate(counters):
        d["counter"] = n

    pool = tr.Pool(CODE_OFFSET)
    orig = bytearray()
    win_rows, site_rows = [], []
    for wi, w in enumerate(windows):
        stub = pool.here()
        orig_off = len(orig)
        orig += b"".join(bytes(i.bytes) for i in w["run"])
        by_at = {d["site"]: d for d in w["sites"]}
        dead = False
        for i in w["run"]:
            if dead:
                continue
            d = by_at.get(i.address)
            if d is None:
                tr.emit_relocated(pool, i, None)
            elif d["kind"] == "src":
                emit_src(pool, i, d["temp"])
            elif d["kind"] == "dst":
                emit_dst(pool, i)
            elif d["kind"] == "count":
                gis.emit_gate(pool, i, d["skip"], d["flags"], d["counter"])
            elif d["kind"] == "gatefn":
                emit_fn_gate(pool, d["counter"])
                tr.emit_relocated(pool, i, None)
            if i.mnemonic in tr.UNCOND:
                dead = True
        if not dead:
            pool.game_rel32(b"\xE9", w["hi"])
        win_rows.append((w["lo"], stub, orig_off, w["hi"] - w["lo"]))
        for d in w["sites"]:
            d["row"].update(window="%X" % w["lo"], stub="%X" % stub)
            temp = xmm_index(d["temp"]) if d["temp"] else 0xFF
            site_rows.append((d["site"], KIND[d["kind"]], wi, temp, d["flags"],
                              0xFF if d["counter"] is None else d["counter"]))
        while pool.here() % 16:
            pool.emit(b"\xCC")
    lit_rows = []
    for n, l in enumerate(literals):
        lit_rows.append((l["rva"], l["const"], LITERAL_OFFSET + 4 * n, l["kind"]))
        l["row"]["window"] = "slot %X" % (LITERAL_OFFSET + 4 * n)

    lines = ["// Generated by tools/gen_menu_transitions.py -- do not edit.",
             "// M2 menu transitions: every site, its proof and its reason are in",
             "// docs/animation/menu_transitions.csv.",
             "#pragma once", "#include <cstdint>", "",
             '#define MENU_TRANSITIONS_MAIN_SHA1 "%s"' % sha,
             "static const uint32_t kMenuFrameCounterRva = 0x%X;" % tr.FRAME_COUNTER,
             "static const uint32_t kMenuMaskOffset = 0x%X;   // uint8: 0/1/3, as F1" % MASK_OFFSET,
             "static const uint32_t kMenuScaleOffset = 0x%X;  // float: 1/N" % SCALE_OFFSET,
             "static const uint32_t kMenuCounterOffset = 0x%X;  // {ticks, counted, last tick, passes}"
             % COUNTER_OFFSET,
             "static const uint32_t kMenuCounterStride = %d;" % SLOT,
             "static const uint32_t kMenuCodeOffset = 0x%X;" % CODE_OFFSET,
             "static const uint32_t kMenuPoolSize = 0x%X;" % pool.here(),
             "// site kinds: 0 lin K*s, 1 exp K**s, 2 scaled source, 3 scaled copy,",
             "// 4 counter skipped between stock ticks, 5 function run on stock ticks only",
             ""]
    for name, data in (("kMenuCode", pool.code), ("kMenuOrig", orig)):
        lines.append("static const uint8_t %s[] = {" % name)
        for j in range(0, len(data), 24):
            lines.append("    " + ",".join("0x%02X" % x for x in data[j:j + 24]) + ",")
        lines += ["};", ""]
    lines += ["struct MenuLiteralOrig { uint8_t b[8]; };",
              "static const MenuLiteralOrig kMenuLiteralOrig[] = {"]
    lines += ["    {{" + ",".join("0x%02X" % x for x in l["orig"]) + "}},  // %X" % l["rva"]
              for l in literals]
    lines += ["};", ""]
    tables = [
        ("MenuFixup", "uint32_t field, next, target;", "kMenuFixups", pool.fixups),
        ("MenuWindow", "uint32_t rva, stub, orig; uint16_t len;", "kMenuWindows", win_rows),
        ("MenuSite", "uint32_t site; uint8_t kind, window, temp, flags, counter;", "kMenuSites",
         sorted(site_rows)),
        ("MenuLiteral", "uint32_t rva, constRva, slot; uint8_t kind;", "kMenuLiterals", lit_rows),
    ]
    for typ, fields, name, trows in tables:
        lines += ["struct %s { %s };" % (typ, fields), "static const %s %s[] = {" % (typ, name)]
        lines += ["    {" + ", ".join("0x%X" % v for v in r) + "}," for r in trows]
        lines += ["};", ""]
    refused = [r for r in rows if r["status"] != "selected"]
    if refused:
        for r in refused:
            print("REFUSED %s %s: %s" % (r["site"], r["kind"], r["proof"]))
        raise RuntimeError("%d manifest site(s) failed their proof; nothing written" % len(refused))
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print("menu transitions: %d sites (%s), %d windows, %d literals, %d fixups, %d pool bytes"
          % (len(rows), dict(collections.Counter(r["kind"] for r in rows)), len(windows),
             len(literals), len(pool.fixups), pool.here()))
    for r in rows:
        print("  %s %-6s %-8s %s" % (r["site"], r["kind"], r["window"], r["proof"]))


if __name__ == "__main__":
    main()
