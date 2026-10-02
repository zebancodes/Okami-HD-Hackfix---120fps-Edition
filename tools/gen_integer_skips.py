#!/usr/bin/env python3
"""Generate the first, conservative F1 integer-clock patch for the UI.

Selection and emission are separate. Every UI integer census row gets a
decision in integer_skips.csv, including refusals. A trace's clock label is
necessary for this prototype, not sufficient: event/cycle counters are
explicitly excluded, and unsupported data flow or live flags are refused.
Static-only decisions await the same semantic review; ordered comparisons
alone also describe menu cursors, so they must not become timing patches.

The window/relocation engine is shared with gen_tracer. The generated pool
has a private mask byte at offset 0 (0/1/3 for every tick/every second/every
fourth tick). Runtime updates it from the stock context on the frame thread.
Each stub preserves the incoming flags and rax around its gate. Only the
counting instruction is conditional; all displaced surrounding instructions
run unchanged. The whole pool is neutral while its mask is zero. Inside the
saved flags each stub also counts, per site, the ticks its step was reached on
and the ticks it counted on (not passes: see emit_gate), for the in-game check.

    .venv/Scripts/python tools/gen_integer_skips.py
"""
import collections
import csv
import os
import struct

import capstone
from capstone import x86_const as X

import gen_tracer as tr
from gen_shadow_mode import REG64
from gen_turn_callers import patched_ranges

ROOT = tr.ROOT
DOCS = os.path.join(ROOT, "docs", "animation")
OUT_H = os.path.join(ROOT, "src", "integer_skips.h")
OUT_CSV = os.path.join(DOCS, "integer_skips.csv")
# [0] the mask byte; [COUNTER_OFFSET + SLOT*i] four dwords per site for the
# in-game check: the ticks its step was reached on, the ticks it counted on,
# the frame counter at its last pass (what makes those ticks, not passes), and
# every pass, for the log; code from CODE_OFFSET.
MASK_OFFSET, COUNTER_OFFSET, CODE_OFFSET, SLOT = 0, 0x10, 0x400, 16
TICKS, COUNTED, LAST_TICK, PASSES = 0, 4, 8, 12
MAX_SITES = (CODE_OFFSET - COUNTER_OFFSET) // SLOT
SHAPES = {"counter", "int-step", "int-expr"}
AUDITED_MAIN_SHA1 = "703d292ab2cb50cc9e237e44722dec51d956b79c"
COUPLED_GROUPS = ({0x3FDB53, 0x3FDB5D},)

# These are clocks in the trace only because the enclosing event repeats.
# Their upstream clock is already corrected, or they select a state rather
# than measure duration. Never add a second tick gate to those events.
EXCLUDED = {
    0x40059A: "loading dot increment already gated by F5 H(10,0) at 4003E0",
    0x4004F1: "loading minigame reward count, advanced by input judgement",
    0x4006E5: "loading minigame reward count, advanced by input judgement",
    0x43986E: "scene-transition state index +29 after timer +20 expires",
    0x439A38: "scene-transition state index +29, not a duration",
    0x439AC4: "scene-transition state index +29, not a duration",
    0x3FAB2D: "cycle count gated by phase +74, already scaled at 3FAB17",
    0x4234D4: "timer also extends unscaled +FC sliding step at 4234CC; coordinate movement first",
    0x423554: "timer also extends unscaled +FC sliding step at 42354C; coordinate movement first",
    0x43500D: "old-value zero test at 435013 repeats its sound event while count is held",
    0x410739: "old-value completion at 41073F needs state-transition review",
    0x4116EF: "old-value completion at 4116F5 needs state-transition review",
    0x3FE1F0: "zero completion at 3FE1F4 repeats HappyPoint credit while count is held",
    0x3FDB53: "HappyPoint credit loop lasts unpatched queue countdown 3FE1F0; defer whole queue",
    0x3FDB5D: "HappyPoint remaining budget shares the unpatched queue countdown 3FE1F0",
    0x3FD3F3: "count limits unscaled ballistic motion at 3FD3F7..3FD409",
    0x3FD753: "item-info list length after record compaction, not a timer",
    0x41F62B: "count limits unscaled row motion at 41F623",
    0x42036F: "count limits unscaled row motion at 420366",
    0x439855: "count limits unscaled scene-transition displacement at 4397D9",
    0x4022BA: "post-count equality at 4022D2 repeats map-title setup while 120 is held",
    0x406D0E: "count controls unscaled 0.7 decay at 406D25; coordinate decay first",
    0x3FC45B: "fade siblings 3FC467/3FC46D need one rate; 3FC46D has no safe window",
    0x3FC467: "fade siblings 3FC45B/3FC46D need one rate; 3FC46D has no safe window",
    0x3FC46D: "fade siblings need one rate; this increment has no safe window",
}

# Audited against the game's comparisons and the UI inventory, rather than
# trusting the static class's generic ordered-compare heuristic.
STATIC_CLOCKS = {
    0x14635C: "calibration +94 elapsed counter, reset after 300 ticks",
    0x146A3A: "calibration +94 elapsed counter, threshold/reset state machine",
    0x146A7D: "calibration +94 elapsed counter, threshold/reset state machine",
    0x146B94: "calibration +94 elapsed counter, threshold/reset state machine",
    0x146CFC: "calibration +94 elapsed counter, threshold/reset state machine",
    0x146E63: "calibration +94 elapsed counter, threshold/reset state machine",
    0x147D17: "controller selection +8C timeout, limit 480 ticks",
    0x149941: "controller pairing +8C timeout against configured tick limit",
    0x1487ED: "controller setting +90 guarded countdown, zero means finished",
}


def canon(i, reg):
    n = i.reg_name(reg)
    return REG64.get(n, n)


def memory_key(i, op):
    m = op.mem
    if m.base == X.X86_REG_RIP:
        return ("rip", i.address + i.size + m.disp, op.size)
    return (m.segment, m.base, m.index, m.scale, m.disp, op.size)


def reg_writes(i):
    return {canon(i, r) for r in i.regs_access()[1]}


def prove_update(row, insns, step_idx, site_idx, targets):
    """Return (kind, field width, skip bytes, delta) or a refusal.

    Register counters must load the exact field they store. Only straight
    line motion through flag-neutral instructions is accepted between the
    load and count, and between the count and store.
    """
    step, store = insns[step_idx], insns[site_idx]
    ops = step.operands
    if step.mnemonic not in ("inc", "dec", "add", "sub", "lea"):
        return None, "unsupported integer step: " + step.mnemonic
    if step.mnemonic in ("inc", "dec"):
        delta = 1 if step.mnemonic == "inc" else -1
    elif step.mnemonic in ("add", "sub"):
        if len(ops) != 2 or ops[1].type != X.X86_OP_IMM:
            return None, "variable step needs provenance review"
        bits = ops[0].size * 8
        imm = ops[1].imm & ((1 << bits) - 1)
        if imm & (1 << (bits - 1)):
            imm -= 1 << bits
        delta = imm * (1 if step.mnemonic == "add" else -1)
    else:
        if len(ops) != 2 or ops[1].type != X.X86_OP_MEM:
            return None, "unsupported lea"
        m = ops[1].mem
        if not m.base or m.index or m.base == X.X86_REG_RIP:
            return None, "lea is not old value plus an immediate"
        delta = m.disp
    if not delta:
        return None, "zero step"
    if ops[0].size not in (1, 2, 4):
        return None, "only byte, word and dword steps audited"
    if ops[0].type == X.X86_OP_MEM:
        if step.address != store.address:
            return None, "memory step does not identify the census store"
        if ops[0].mem.base == X.X86_REG_RSP or ops[0].mem.index == X.X86_REG_RSP:
            return None, "stack counter is not a UI field"
        return (0, ops[0].size, b"", delta), None
    if ops[0].type != X.X86_OP_REG:
        return None, "unsupported destination"
    if store.mnemonic != "mov" or len(store.operands) != 2 or \
            store.operands[0].type != X.X86_OP_MEM or store.operands[1].type != X.X86_OP_REG:
        return None, "register update does not end in a plain store"
    dst = canon(step, ops[0].reg)
    if dst in ("rsp", "rbp") or canon(store, store.operands[1].reg) != dst:
        return None, "store does not use the counting register"
    if site_idx < step_idx or site_idx - step_idx > 8:
        return None, "store too far from count for prototype"
    address_regs = {canon(store, r) for r in
                    (store.operands[0].mem.base, store.operands[0].mem.index) if r}
    if dst in address_regs:
        return None, "count also changes the store address"
    for i in insns[step_idx + 1:site_idx]:
        if i.mnemonic.startswith("j") or i.mnemonic in ("call", "ret") or \
                reg_writes(i) & (address_regs | {dst}):
            return None, "intervening control flow or register definition"
    src = canon(step, ops[1].mem.base) if step.mnemonic == "lea" else dst
    want_mem = memory_key(store, store.operands[0])
    found = False
    traversed = []
    for i in reversed(insns[max(0, step_idx - 16):step_idx]):
        if i.mnemonic in ("call", "ret", "jmp"):
            break
        if i.mnemonic.startswith("j"):
            # A forward guard which skips the counting path is transparent
            # on the path which reaches this step. Any join into that path
            # is rejected below; no alternate definition can slip through.
            if not tr.is_rel_branch(i) or i.operands[0].imm <= step.address:
                break
            traversed.append(i.address)
            continue
        if reg_writes(i) & address_regs:
            break
        if src not in reg_writes(i):
            traversed.append(i.address)
            continue
        if i.mnemonic in ("mov", "movzx", "movsx") and len(i.operands) == 2 and \
                i.operands[1].type == X.X86_OP_MEM and \
                memory_key(i, i.operands[1]) == want_mem:
            found = not any(a in targets for a in traversed + [step.address])
        break
    if not found:
        return None, "old counting register not proven to load the same field"
    if step.mnemonic != "lea":
        return (1, store.operands[0].size, b"", delta), None
    # lea r32,[r64+imm] writes the low 32 bits and zero-extends. The skip
    # path must do that same extension, copying the pre-count value.
    d, s = tr.GPR[dst], tr.GPR[src]
    skip = tr.rex(0, s >> 3, 0, d >> 3) + bytes([0x89, 0xC0 | ((s & 7) << 3) | (d & 7)])
    return (2, store.operands[0].size, skip, delta), None


# Capstone reports reads and writes separately for every arithmetic flag.
FLAGS = ("CF", "PF", "AF", "ZF", "SF", "OF")
READ_FLAG = {f: getattr(X, "X86_EFLAGS_TEST_" + f, 0) for f in FLAGS}
WRITE_FLAG = {f: sum(getattr(X, "X86_EFLAGS_" + kind + "_" + f, 0)
                     for kind in ("MODIFY", "RESET", "SET", "UNDEFINED")) for f in FLAGS}


def arithmetic_eflags(i):
    # Capstone shares an eflags/fpu_flags union: SSE/FPU metadata is not an
    # integer flag use. Only instructions known to affect RFLAGS enter this
    # liveness computation; ordinary moves/SSE arithmetic preserve them.
    mn = i.mnemonic
    flag_ops = {"inc", "dec", "add", "sub", "adc", "sbb", "and", "or", "xor", "neg",
                "cmp", "test", "shl", "shr", "sar", "sal", "rol", "ror", "rcl", "rcr",
                "mul", "imul", "div", "idiv", "bt", "btc", "btr", "bts", "bsf", "bsr",
                "comiss", "ucomiss", "comisd", "ucomisd", "fcomi", "fucomi", "fcomip",
                "fucomip", "clc", "stc", "cmc", "sahf", "lahf", "pushfq", "popfq"}
    return i.eflags if mn in flag_ops or mn.startswith(("j", "cmov", "set")) else 0


def flag_policy(dec, step, delta, cmov=False):
    """Walk both successor paths until the affected flags are overwritten.

    The only synthesised result admitted is an ordinary countdown's ZF/SF
    continuation, as in memory_timers (with cmov, also equality and sign
    clamps, which read the synthetic nonzero/nonnegative flags). All other live flag
    uses are refused.
    Calls end flag liveness (Windows x64 has no flag arguments/results).
    """
    if step.mnemonic == "lea":
        return 0, "lea preserves flags"
    initial = frozenset(f for f in FLAGS if arithmetic_eflags(step) & WRITE_FLAG[f])
    work, seen, consumers = [(step.address + step.size, initial)], set(), set()
    while work:
        at, live = work.pop()
        if not live or (at, live) in seen:
            continue
        if len(seen) > 160:
            return None, "flag liveness exceeds prototype bound"
        seen.add((at, live))
        seq = dec.run(at, at)
        if not seq or seq[0].address != at:
            return None, "cannot decode flag consumer"
        i = seq[0]
        if i.mnemonic in ("call", "ret", "retf"):
            continue
        if i.mnemonic in ("int3", "ud2"):
            return None, "flag path reaches padding"
        ef = arithmetic_eflags(i)
        used = {f for f in live if ef & READ_FLAG[f]}
        if used:
            ok = ("jne", "je", "jns") + (("cmove", "cmovne", "cmovs", "cmovns") if cmov else ())
            if delta != -1 or i.mnemonic not in ok or \
                    not used <= {"ZF", "SF"}:
                return None, "live flags consumed by %X %s" % (at, i.mnemonic)
            consumers.add((at, i.mnemonic))
        remaining = frozenset(f for f in live if not ef & WRITE_FLAG[f])
        if not remaining:
            continue
        if i.mnemonic.startswith("j"):
            if not tr.is_rel_branch(i):
                return None, "indirect flag-consumer path"
            work.append((i.operands[0].imm, remaining))
            if i.mnemonic != "jmp":
                work.append((at + i.size, remaining))
        else:
            work.append((at + i.size, remaining))
    if consumers:
        return 1, "countdown not finished: " + ", ".join("%X %s" % x for x in sorted(consumers))
    return 0, "arithmetic flags overwritten before use"


def emit_gate(pool, step, skip_bytes, flags, counter):
    slot = COUNTER_OFFSET + SLOT * counter

    def jcc8(opcode):
        pool.emit(bytes([opcode, 0]))
        return len(pool.code)

    def land(at):
        pool.code[at - 1] = len(pool.code) - at

    pool.emit(b"\x9C\x50")                                  # pushfq; push rax
    # The measurement changes only inside the saved flags. A site in a loop is
    # reached once per element, and a loop that drops an element when its
    # count runs out (the bestiary grid) reaches it more often on the ticks
    # before a count than after it. Per pass, the counted share would then
    # read above 1/N; per tick it is 1/N whatever the population does.
    pool.pool_rel32(b"\xFF\x05", slot + PASSES)             # inc dword [passes]
    pool.game_rel32(b"\x8B\x05", tr.FRAME_COUNTER)          # mov eax, [fc]
    pool.pool_rel32(b"\x3B\x05", slot + LAST_TICK)          # cmp eax, [last]
    same = jcc8(0x74)                                       # je gate: seen this tick
    pool.pool_rel32(b"\x89\x05", slot + LAST_TICK)          # mov [last], eax
    pool.pool_rel32(b"\xFF\x05", slot + TICKS)              # inc dword [ticks]
    pool.pool_rel32(b"\x84\x05", MASK_OFFSET)               # test [mask], al
    skipped = jcc8(0x75)                                    # jnz gate
    pool.pool_rel32(b"\xFF\x05", slot + COUNTED)            # inc dword [counted]
    land(same)
    land(skipped)
    pool.pool_rel32(b"\x84\x05", MASK_OFFSET)               # gate: test [mask], al
    pool.emit(b"\x58\x0F\x85")                              # pop rax; jnz skip
    branch = len(pool.code)
    pool.emit(b"\0" * 4)
    pool.emit(b"\x9D")
    tr.emit_relocated(pool, step, None)
    pool.emit(b"\xE9")
    join = len(pool.code)
    pool.emit(b"\0" * 4)
    struct.pack_into("<i", pool.code, branch, len(pool.code) - branch - 4)
    pool.emit(b"\x9D" + skip_bytes)
    if flags:
        # Publish only the countdown consumers' ZF=0/SF=0. Unlike TEST,
        # this preserves incoming CF for INC/DEC, as well as PF/AF/OF and
        # control flags. The liveness proof rejects all other output uses.
        pool.emit(b"\x9C\x81\x24\x24\x3F\xFF\xFF\xFF\x9D")
    struct.pack_into("<i", pool.code, join, len(pool.code) - join - 4)


def write_header(pool, windows, selected, sha):
    orig, win_rows, maps, site_rows = bytearray(), [], [], []
    counters = {}
    if sum(len(w[3]) for w in windows) > MAX_SITES:
        raise RuntimeError("more sites than counter slots (%d); move CODE_OFFSET" % MAX_SITES)
    for wi, w in enumerate(windows):
        lo, hi, run, infos = w
        stub = pool.here()
        orig_off = len(orig)
        orig.extend(b"".join(bytes(i.bytes) for i in run))
        steps = {s["step"]: s for s in infos}
        dead = False
        for i in run:
            if dead:
                continue
            maps.append((i.address, pool.here()))
            if i.address in steps:
                s = steps[i.address]
                counters[s["site"]] = len(counters)
                emit_gate(pool, i, s["skip"], s["flags"], counters[s["site"]])
            else:
                tr.emit_relocated(pool, i, None)
            if i.mnemonic in tr.UNCOND:
                dead = True
        if not dead:
            pool.game_rel32(b"\xE9", hi)
        win_rows.append((lo, stub, orig_off, hi - lo))
        for s in infos:
            site_rows.append((s["site"], s["step"], wi, s["width"], s["flags"], s["kind"],
                              counters[s["site"]], s["stock_hz"]))
            s["row"]["window"] = "%X" % lo
            s["row"]["stub"] = "%X" % stub
        while pool.here() % 16:
            pool.emit(b"\xCC")
    lines = ["// Generated by tools/gen_integer_skips.py -- do not edit.",
             "// UI prototype: unsupported or unaudited sites are recorded as refused in the CSV.",
             "#pragma once", "#include <cstdint>", "",
             '#define INTEGER_SKIPS_MAIN_SHA1 "%s"' % sha,
             "static const uint32_t kIntegerSkipFrameCounterRva = 0x%X;" % tr.FRAME_COUNTER,
             "static const uint32_t kIntegerSkipMaskOffset = 0;",
             "static const uint32_t kIntegerSkipCounterOffset = 0x%X;"
             "  // {ticks, counted, last tick, passes} per site" % COUNTER_OFFSET,
             "static const uint32_t kIntegerSkipCounterStride = %d;" % SLOT,
             "static const uint32_t kIntegerSkipCodeOffset = 0x%X;" % CODE_OFFSET,
             "static const uint32_t kIntegerSkipPoolSize = 0x%X;" % pool.here(), ""]
    for name, data in (("kIntegerSkipCode", pool.code), ("kIntegerSkipOrig", orig)):
        lines.append("static const uint8_t %s[] = {" % name)
        for j in range(0, len(data), 24):
            lines.append("    " + ",".join("0x%02X" % b for b in data[j:j + 24]) + ",")
        lines += ["};", ""]
    tables = [
        ("IntegerSkipFixup", "uint32_t field, next, target;", "kIntegerSkipFixups", pool.fixups),
        ("IntegerSkipWindow", "uint32_t rva, stub, orig; uint16_t len;", "kIntegerSkipWindows", win_rows),
        ("IntegerSkipInsn", "uint32_t rva, stub;", "kIntegerSkipInsns", maps),
        # stockHz: the one stock tick rate the tracer session (Passthrough, the
        # stock game) saw the site run at, 30 or 60; 0 if it saw both or never
        # saw it run. The in-game check judges the live context against it.
        ("IntegerSkipSite",
         "uint32_t site, step, window; uint8_t width, flags, kind, counter, stockHz;",
         "kIntegerSkipSites", sorted(site_rows)),
    ]
    for typ, fields, name, rows in tables:
        lines += ["struct %s { %s };" % (typ, fields), "static const %s %s[] = {" % (typ, name)]
        lines += ["    {" + ", ".join("0x%X" % n for n in r) + "}," for r in rows]
        lines += ["};", ""]
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def main():
    img, secs, begins, sha = tr.load_image()
    if sha != AUDITED_MAIN_SHA1:
        raise RuntimeError("main.dll %s is not the build whose UI semantics were audited (%s); "
                           "refusing to reuse the manual site decisions" % (sha, AUDITED_MAIN_SHA1))
    lo, hi = secs[".text"]
    starts, targets, switch, _tables = tr.global_pass(img, lo, hi)
    targets |= switch | tr.data_references(img, secs, lo, hi, starts) | set(begins)
    dec = tr.Decoder(img, starts)
    protected = [r for r in patched_ranges() if "integer_skip" not in r[2]]
    # The turn generator omits its own output from its dependency set. F1
    # must still protect those installed retargets when choosing windows.
    import check_patch_sites as cps
    for a, raw, label in cps.turn_callers():
        protected.append((a, a + len(raw), label))
    # Coverage means the counting instruction itself is already patched;
    # overlap with a surrounding relocation window is a different refusal.
    exact = {}
    for a, _b, family in protected:
        if family in ("action_timers.h", "memory_timers.h", "lea_timers.h"):
            # These three tables explicitly identify their first instruction
            # as the count. Other displaced instructions are merely relocated
            # and must not be reported as already compensated.
            exact[a] = family
    rows = list(csv.DictReader(open(os.path.join(DOCS, "classification.csv"), encoding="utf-8")))
    census = {r["site"]: r for r in csv.DictReader(open(os.path.join(DOCS, "sites.csv"), encoding="utf-8"))}
    audit, selected = [], []
    for r in rows:
        if r["subsystem"] != "ui" or r["shape"] not in SHAPES:
            continue
        a, step_at, fn = int(r["site"], 16), int(r["step_at"] or r["site"], 16), int(r["function"], 16)
        out = dict(site=r["site"], step="%X" % step_at, function=r["function"],
                   shape=r["shape"], trace_class=r["class"], trace_context=r["context"],
                   decision=r["decision"],
                   static_class=r["static_class"], confidence=r["static_confidence"],
                   owners=census.get(r["site"], {}).get("owners", ""), status="refused",
                   reason="", window="", stub="", width="", flags="", kind="")
        audit.append(out)
        if a in EXCLUDED:
            out["reason"] = EXCLUDED[a]
            continue
        if step_at in exact:
            out["status"], out["reason"] = "covered", "exact counting instruction in " + exact[step_at]
            continue
        if a not in STATIC_CLOCKS and (r["decision"] != "patch" or r["class"] not in ("clock", "gated-clock")):
            out["reason"] = "static-only clock needs semantic review" if r["decision"] == "patch-static" \
                else "classification decision " + r["decision"]
            continue
        insns, step_idx = dec.around(step_at, fn, max(a, step_at))
        if insns is None:
            out["reason"] = "step is not a decoded instruction"
            continue
        site_idx = next((n for n, i in enumerate(insns) if i.address == a), None)
        if site_idx is None:
            out["reason"] = "store not in the step's straight decode"
            continue
        info, why = prove_update(r, insns, step_idx, site_idx, targets)
        if why:
            out["reason"] = why
            continue
        kind, width, skip, delta = info
        flags, why = flag_policy(dec, insns[step_idx], delta)
        if flags is None:
            out["reason"] = why
            continue
        wa, wb, reason = tr.find_window(insns, step_idx, targets, protected)
        if reason:
            out["reason"] = "window: " + reason
            continue
        run = insns[wa:wb + 1]
        selected.append(dict(site=a, step=step_at, kind=kind, width=width, skip=skip, flags=flags,
                             lo=run[0].address, hi=run[-1].address + run[-1].size, run=run, row=out,
                             stock_hz={"30": 30, "60": 60}.get(r["context"], 0)))
        out.update(reason=(STATIC_CLOCKS[a] + "; " if a in STATIC_CLOCKS else "") + why,
                   width=width, flags=flags, kind=kind)
    # HappyPoint simultaneously increments credited points and decrements the
    # remaining budget. Never accept just one side of that accounting pair.
    for group in COUPLED_GROUPS:
        present = {s["site"] for s in selected} & group
        if present and present != group:
            for s in selected:
                if s["site"] in group:
                    s["row"]["reason"] = "coupled credited/remaining counters must both be supported"
            selected = [s for s in selected if s["site"] not in group]
    windows = []
    for s in sorted(selected, key=lambda s: (s["lo"], s["hi"])):
        if windows and s["lo"] < windows[-1][1]:
            w = windows[-1]
            merged = {i.address: i for i in w[2] + s["run"]}
            run = [merged[a] for a in sorted(merged)]
            contiguous = all(a.address + a.size == b.address for a, b in zip(run, run[1:]))
            why = tr.window_problem(run, targets, protected) if contiguous else "noncontiguous overlap"
            if why:
                s["row"]["reason"] = "merge: " + why
                continue
            if any(t["step"] == s["step"] for t in w[3]):
                s["row"]["reason"] = "another census row names the same counting instruction"
                continue
            w[1], w[2] = max(w[1], s["hi"]), run
            w[3].append(s)
        else:
            windows.append([s["lo"], s["hi"], s["run"], [s]])
        s["row"]["status"] = "selected"
    final_sites = {s["site"] for w in windows for s in w[3]}
    for group in COUPLED_GROUPS:
        if final_sites & group and final_sites & group != group:
            raise RuntimeError("window merging split coupled counters %s; refusing a partial patch" %
                               ", ".join("%X" % a for a in sorted(group)))
    if not windows:
        raise RuntimeError("no supported UI clocks; refusing an empty patch")
    pool = tr.Pool(CODE_OFFSET)
    write_header(pool, windows, selected, sha)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(sorted(audit, key=lambda r: int(r["site"], 16)))
    print("UI integer candidates: %d; %s" % (len(audit), dict(collections.Counter(r["status"] for r in audit))))
    print("%d windows, %d fixups, %d pool bytes; sha1 %s" %
          (len(windows), len(pool.fixups), pool.here(), sha))
    for why, count in collections.Counter(r["reason"] for r in audit if r["status"] == "refused").most_common(12):
        print("  refused %3d: %s" % (count, why))


if __name__ == "__main__":
    main()
