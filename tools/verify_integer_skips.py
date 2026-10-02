#!/usr/bin/env python3
"""Verify the F1 UI integer skips against the game's original instructions.

The DLL self-test maps main.dll without executing game code and dumps its real
install. This script independently checks every jump and pool relocation, then
runs every complete displaced window under Unicorn. At N=1 the original and
installed code must agree. At N=2/4, the reference interpreter suppresses only
the counting instruction on non-stock ticks; a LEA still copies the old value
to its destination and a live-flags countdown publishes 'not finished yet'.

Comparisons include all GPRs, XMMs, flags, game-visible memory and exit address.
Boundary counts, incoming carry flags, all tick residues and random machine
states are exercised. No generator encoding routines are used as an oracle.
Each stub also keeps the in-game measurement, a slot per site in the pool:
the ticks its step was reached on, the ticks it counted on, the frame counter
of its last pass, and every pass. Every run that reaches the step must add one
pass; only the first run of a tick adds a tick, and a counted tick exactly when
that tick is a stock tick. The carry-in 0 and 1 runs of each case share one
tick, so a site both reach is passed twice on it, and the second pass must add
a pass and nothing else (the bestiary's loop is passed many times a tick). Every
site must be seen on a counted tick, a skipped tick and such a second pass.
The in-game check holds the live context to each site's
stockHz; that must match the stock trace (docs/animation/classification.csv),
checked here independently.

    .venv/Scripts/python tools/verify_integer_skips.py
    .venv/Scripts/python tools/verify_integer_skips.py --header-only
    --break gate|flags|register|jump|counter|tick|context deliberately corrupts an installed artifact
    and must fail. --header-only verifies generated code before the DLL is built.
"""
import argparse
import csv
import ctypes
import hashlib
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
from unicorn import x86_const as U

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import verify_tracer as vt  # noqa: E402

ROOT = os.path.dirname(HERE)
HDR = os.path.join(ROOT, "src", "integer_skips.h")


def parse_header(path=HDR):
    text = open(path, encoding="utf-8").read()

    def const(name):
        return int(re.search(r"\b%s\s*=\s*(0x[0-9a-fA-F]+|\d+)" % name, text).group(1), 0)

    def block(name):
        return re.search(r"\b%s\[\]\s*=\s*\{(.*?)\n\};" % name, text, re.S).group(1)

    def raw(name):
        return bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})\b", block(name)))

    def rows(name):
        return [tuple(int(v.strip(), 0) for v in row.split(",") if v.strip())
                for row in re.findall(r"\{([^{}]+)\}", block(name))]

    return dict(sha=re.search(r'INTEGER_SKIPS_MAIN_SHA1\s+"([0-9a-f]+)"', text).group(1),
                fc=const("kIntegerSkipFrameCounterRva"), mode=0xB6AC45,
                mask=const("kIntegerSkipMaskOffset"),
                counter_off=const("kIntegerSkipCounterOffset"),
                stride=const("kIntegerSkipCounterStride"),
                code_off=const("kIntegerSkipCodeOffset"),
                pool_size=const("kIntegerSkipPoolSize"), rec_size=0,
                code=raw("kIntegerSkipCode"), orig=raw("kIntegerSkipOrig"),
                fixups=rows("kIntegerSkipFixups"), windows=rows("kIntegerSkipWindows"),
                sites=rows("kIntegerSkipSites"), insns=rows("kIntegerSkipInsns"))


def counters(m, hdr, pool, site):
    """A site's {ticks, counted, last tick, passes} as the stub left them."""
    at = pool + hdr["counter_off"] + hdr["stride"] * site[6]
    return struct.unpack("<IIII", bytes(m.mu.mem_read(at, 16)))


def slot_insn(m, hdr, pool, md, site, field):
    """The instruction in the site's stub that addresses one of its slot's dwords."""
    want = pool + hdr["counter_off"] + hdr["stride"] * site[6] + field
    start = hdr["windows"][site[2]][1]
    later = [w[1] for w in hdr["windows"] if w[1] > start]
    end = min(later) if later else hdr["pool_size"]
    for ins in md.disasm(bytes(m.mu.mem_read(pool + start, end - start)), pool + start):
        if any(op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP and
               ins.address + ins.size + op.mem.disp == want for op in ins.operands):
            return ins
    return None


def pool_bytes(hdr, main, pool):
    out = bytearray(hdr["pool_size"])
    co = hdr["code_off"]
    out[co:co + len(hdr["code"])] = hdr["code"]
    for field, nxt, target in hdr["fixups"]:
        if nxt:
            struct.pack_into("<i", out, field, main + target - (pool + nxt))
        else:
            struct.pack_into("<Q", out, field, main + target)
    return bytes(out)


def patch_bytes(hdr, main, pool):
    return [b"\xE9" + struct.pack("<i", pool + stub - (main + rva + 5)) + b"\x90" * (n - 5)
            for rva, stub, _orig, n in hdr["windows"]]


def canonical(name):
    if name.startswith("r") and name[1:].rstrip("dwb").isdigit():
        return name.rstrip("dwb")
    for full, aliases in (("rax", "rax eax ax al ah"), ("rbx", "rbx ebx bx bl bh"),
                          ("rcx", "rcx ecx cx cl ch"), ("rdx", "rdx edx dx dl dh"),
                          ("rsi", "rsi esi si sil"), ("rdi", "rdi edi di dil"),
                          ("rbp", "rbp ebp bp bpl"), ("rsp", "rsp esp sp spl")):
        if name in aliases.split():
            return full
    raise ValueError("unsupported register %s" % name)


def write_reg(mu, name, value, size):
    full = canonical(name)
    reg = vt.REGMAP[full]
    value &= (1 << (size * 8)) - 1
    if size >= 4:
        mu.reg_write(reg, value)
    else:
        shift = 8 if name in ("ah", "bh", "ch", "dh") else 0
        bits = ((1 << (size * 8)) - 1) << shift
        mu.reg_write(reg, (mu.reg_read(reg) & ~bits) | (value << shift))


def effective_address(mu, ins, mem):
    addr = mem.disp
    if mem.base == X.X86_REG_RIP:
        addr += vt.BASE + ins.address + ins.size
    elif mem.base:
        addr += mu.reg_read(vt.REGMAP[canonical(ins.reg_name(mem.base))])
    if mem.index:
        addr += mu.reg_read(vt.REGMAP[canonical(ins.reg_name(mem.index))]) * mem.scale
    return addr & 0xFFFFFFFFFFFFFFFF


class Machine(vt.Machine):
    """Reuse the tracer's memory model, not its generated instruction semantics."""

    def __init__(self, hdr, img):
        super().__init__(hdr, img)
        self.allowed = []
        self.reference = False
        self.skip = False
        self.ops = {}
        self.decode = {}
        self.inputs = {}
        self.sources = {}

    def _code(self, uc, address, size, data):
        if not any(lo <= address < hi for lo, hi in self.allowed):
            self.exit = address
            uc.emu_stop()
            return
        self.executed.add(address)
        self.steps += 1
        if self.steps > 400:
            self.exit = "runaway"
            uc.emu_stop()
            return
        if not self.reference:
            return
        rva = address - vt.BASE
        ins = self.decode.get(rva)
        if ins is None:
            return
        site = self.ops.get(rva)
        if site is not None:
            _store, _step, _window, width, flags, kind, *_ = site
            dst = ins.operands[0]
            if dst.type == X.X86_OP_MEM:
                self.inputs[rva] = ("mem", effective_address(uc, ins, dst.mem), width)
            else:
                nm = ins.reg_name(dst.reg)
                source = ins.reg_name(ins.operands[1].mem.base) if kind == 2 else nm
                self.inputs[rva] = self.sources.get(canonical(source), ("reg", source, width))
            if self.skip:
                if kind == 2:
                    # A no-step LEA still defines its output as the old counter.
                    mem = ins.operands[1].mem
                    assert mem.base and not mem.index, "unsupported LEA skip oracle"
                    value = uc.reg_read(vt.REGMAP[canonical(ins.reg_name(mem.base))])
                    write_reg(uc, ins.reg_name(dst.reg), value, dst.size)
                if flags:
                    # Only the countdown's tested ZF/SF change. In particular,
                    # DEC preserves carry, which may remain live past the gate.
                    ef = uc.reg_read(U.UC_X86_REG_EFLAGS)
                    uc.reg_write(U.UC_X86_REG_EFLAGS, ef & ~0xC0)
                uc.reg_write(U.UC_X86_REG_RIP, address + size)
                return
        # Remember simple loads in the displaced prefix. Boundary tests seed
        # the source field so both original and stub arrive with the same count.
        if ins.mnemonic in ("mov", "movzx", "movsx", "movsxd") and len(ins.operands) == 2:
            dst, src = ins.operands
            if dst.type == X.X86_OP_REG:
                key = canonical(ins.reg_name(dst.reg))
                if src.type == X.X86_OP_MEM:
                    self.sources[key] = ("mem", effective_address(uc, ins, src.mem), src.size)
                elif src.type == X.X86_OP_REG:
                    self.sources[key] = self.sources.get(canonical(ins.reg_name(src.reg)),
                                                        ("reg", ins.reg_name(src.reg), src.size))
                else:
                    self.sources.pop(key, None)

    def run_window(self, state, window, sites, original, skip, patch=None, entry=None):
        rva, stub, ooff, n = window
        self.reference, self.skip = original, skip
        self.ops = {s[1]: s for s in sites}
        self.inputs, self.sources = {}, {}
        self.allowed = [(vt.BASE + rva, vt.BASE + rva + n)] if original else [
            (vt.POOL + self.hdr["code_off"], vt.POOL + self.hdr["pool_size"]),
            (vt.BASE + rva, vt.BASE + rva + 5)]
        at = vt.BASE + rva
        saved = bytes(self.mu.mem_read(at, n))
        if patch is not None:
            self.mu.mem_write(at, patch)
            self.mu.ctl_flush_tb()
        start = entry if entry is not None else at
        out = self.run(state, start, 0, 0)
        if patch is not None:
            self.mu.mem_write(at, saved)
            self.mu.ctl_flush_tb()
        return out


def prepare_boundary(machine, state, window, sites, value):
    """Seed actual counter inputs found by executing the displaced prefix."""
    probe = machine.run_window(state, window, sites, True, False)
    if probe["err"]:
        return [], False
    undo = []
    for kind, where, width in machine.inputs.values():
        v = value & ((1 << (8 * width)) - 1)
        if kind == "mem":
            if not machine.demand_map(where, width):
                return undo, False
            undo.append((where, bytes(machine.mu.mem_read(where, width))))
            machine.mu.mem_write(where, v.to_bytes(width, "little"))
        else:
            full = canonical(where)
            i = vt.GPR_NAMES.index(full)
            old = state["gpr"][i]
            shift = 8 if where in ("ah", "bh", "ch", "dh") else 0
            mask = ((1 << (8 * width)) - 1) << shift
            state["gpr"][i] = (old & ~mask) | (v << shift)
    return undo, True


def check_controls(path, hdr):
    if not os.path.isfile(path):
        return ["DLL self-test did not write modes.csv"]
    bad = []
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for row in rows:
        fps, mode = int(row["fps"]), int(row["mode"])
        on = (int(row["enabled"]) and not int(row["muted"]) and fps > 30
              and mode in (1, 2)
              and all(int(row.get(gate, "1")) for gate in ("shadow", "hook", "complete")))
        stock = 60 if mode == 1 else 30
        want = max(1, fps // stock) - 1 if on else 0
        if int(row["mask"]) != want:
            bad.append("control %s: mask %s, want %d" % (row, row["mask"], want))
    if not rows:
        bad.append("no runtime control cases")
    print("runtime mask: %d cases, %d wrong" % (len(rows), len(bad)))
    return bad


def check_stock_context(hdr):
    """Each site's stockHz, which the in-game check holds the live context to,
    must be the one stock rate the tracer session saw it run at (the context
    column of classification.csv), or 0 where it saw both or never saw it."""
    path = os.path.join(ROOT, "docs", "animation", "classification.csv")
    traced = {int(r["site"], 16): r["context"] for r in csv.DictReader(open(path, newline=""))}
    bad = []
    for s in hdr["sites"]:
        want = {"30": 30, "60": 60}.get(traced.get(s[0], ""), 0)
        got = s[7] if len(s) > 7 else None
        if got != want:
            bad.append("site %X: stockHz %s in the header, the stock trace says %s (%r)"
                       % (s[0], got, want, traced.get(s[0])))
    held = sum(1 for s in hdr["sites"] if len(s) > 7 and s[7])
    print("stock context: %d of %d sites held to the trace, %d wrong"
          % (held, len(hdr["sites"]), len(bad)))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--header-only", action="store_true")
    ap.add_argument("--states", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--break", dest="broken",
                    choices=("gate", "flags", "register", "jump", "counter", "tick", "context"))
    args = ap.parse_args()
    hdr = parse_header()
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    if hashlib.sha1(raw).hexdigest() != hdr["sha"]:
        sys.exit("main.dll is not the binary the F1 header describes")
    problems = []
    if args.broken == "context":
        # a 30 Hz site recorded as 60 Hz: the in-game check would then call
        # its right context wrong, and a wrong one right
        k = next(i for i, s in enumerate(hdr["sites"]) if s[7] == 30)
        hdr["sites"][k] = hdr["sites"][k][:7] + (60,)
    problems += check_stock_context(hdr)
    main_base, pool = vt.BASE, vt.POOL
    code = pool_bytes(hdr, main_base, pool)
    patches = patch_bytes(hdr, main_base, pool)
    if not args.header_only:
        work = args.out or tempfile.mkdtemp(prefix="okami_integer_skips_")
        os.makedirs(work, exist_ok=True)
        dll = os.path.join(work, "dinput8.dll")
        shutil.copy2(args.dll, dll)
        lib = ctypes.WinDLL(dll)
        fn = lib.OkamiIntegerSkipSelfTest
        fn.argtypes, fn.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int
        rc = fn(path.encode("mbcs"), work.encode("mbcs"))
        report = open(os.path.join(work, "report.txt")).read()
        print("DLL self-test (rc %d): %s" % (rc, report.strip().splitlines()[-1]))
        if rc:
            print(report)
            return 1
        vals = dict(ln.split(None, 1) for ln in report.splitlines() if len(ln.split()) == 2)
        main_base, pool = int(vals["main"], 16), int(vals["pool"], 16)
        expected = pool_bytes(hdr, main_base, pool)
        code = open(os.path.join(work, "pool.bin"), "rb").read()
        if code != expected:
            problems.append("installed pool differs from independently relocated header")
        expected_patches = patch_bytes(hdr, main_base, pool)
        actual = open(os.path.join(work, "windows.bin"), "rb").read()
        if actual != b"".join(expected_patches):
            problems.append("installed window bytes differ from expected jumps and NOP padding")
        patches = []
        pos = 0
        for _rva, _stub, _orig, n in hdr["windows"]:
            patches.append(actual[pos:pos + n])
            pos += n
        problems += check_controls(os.path.join(work, "modes.csv"), hdr)
        print("install: %d windows, %d pool bytes" % (len(patches), len(code)))
    vt.BASE, vt.POOL = main_base, pool
    pe = pefile.PE(data=raw)
    if pe.OPTIONAL_HEADER.ImageBase != main_base:
        pe.relocate_image(main_base)
    img = bytearray(pe.get_memory_mapped_image())
    m = Machine(hdr, img)
    m.mu.mem_write(pool, code)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    groups = {}
    for site in hdr["sites"]:
        groups.setdefault(site[2], []).append(site)
    for rva, _stub, ooff, n in hdr["windows"]:
        if bytes(img[rva:rva + n]) != hdr["orig"][ooff:ooff + n]:
            problems.append("original bytes mismatch at main+%X" % rva)
        for ins in md.disasm(bytes(img[rva:rva + n]), rva):
            m.decode[ins.address] = ins
    if args.broken == "jump":
        p = bytearray(patches[0])
        p[1] ^= 1
        patches[0] = bytes(p)
    # The corruption checks alter the actual pool, never the reference model.
    if args.broken == "counter":
        # drop the first site's counted-tick increment
        ins = slot_insn(m, hdr, pool, md, hdr["sites"][0], 4)
        if ins is None or ins.mnemonic != "inc":
            sys.exit("cannot inject counter: no counted increment in the first stub")
        m.mu.mem_write(ins.address, b"\x90" * ins.size)
    if args.broken == "tick":
        # every pass a new tick, as before: drop the branch after the last-tick compare
        ins = slot_insn(m, hdr, pool, md, hdr["sites"][0], 8)
        je = None
        if ins is not None and ins.mnemonic == "cmp":
            je = next(md.disasm(bytes(m.mu.mem_read(ins.address + ins.size, 2)),
                                ins.address + ins.size), None)
        if je is None or je.mnemonic != "je":
            sys.exit("cannot inject tick: no same-tick branch in the first stub")
        m.mu.mem_write(je.address, b"\x90" * je.size)
    if args.broken in ("flags", "register"):
        sequence = b"\x9C\x81\x24\x24\x3F\xFF\xFF\xFF\x9D" if args.broken == "flags" else None
        selected = None
        for wi, window in enumerate(hdr["windows"]):
            if any(s[4] if args.broken == "flags" else s[5] == 2 for s in groups.get(wi, [])):
                start = window[1]
                end = hdr["windows"][wi + 1][1] if wi + 1 < len(hdr["windows"]) else len(code)
                body = bytes(m.mu.mem_read(pool + start, end - start))
                if sequence is not None:
                    at = body.find(sequence)
                    if at >= 0:
                        selected = (pool + start + at, b"\x90" * len(sequence))
                else:
                    for ins in md.disasm(body, pool + start):
                        if ins.mnemonic == "mov" and len(ins.operands) == 2 and all(
                                op.type == X.X86_OP_REG for op in ins.operands):
                            selected = (ins.address, b"\x90" * ins.size)
                            break
                if selected:
                    break
        if selected is None and args.broken == "register":
            # The current audited prototype may contain no LEA copies. Still
            # prove its scratch register saves matter by restoring RAX into
            # RCX instead, using an equally sized, valid POP instruction.
            for ins in md.disasm(bytes(m.mu.mem_read(pool + hdr["code_off"],
                                                    len(code) - hdr["code_off"])),
                                 pool + hdr["code_off"]):
                if ins.mnemonic == "pop" and ins.op_str == "rax":
                    selected = (ins.address, b"\x59")
                    break
        if selected is None:
            sys.exit("cannot inject %s: no eligible stub" % args.broken)
        m.mu.mem_write(*selected)
    rng = random.Random(args.seed)
    cases = skipped = neutral = 0
    counted_checks = [0]
    repeats = 0
    stock_sites, skipped_sites = set(), set()
    # The measurement's model: the tick each site last ran on. Each (value,
    # mask, residue) is a new tick; its carry-in 0 and 1 runs share it, so a
    # site reached in both is passed twice on one tick.
    last = {s[0]: counters(m, hdr, pool, s)[2] for s in hdr["sites"]}
    tick_paths = {s[0]: set() for s in hdr["sites"]}
    serial = 0
    for wi, window in enumerate(hdr["windows"]):
        sites = groups.get(wi, [])
        widths = {s[3] for s in sites}
        bounds = sorted({0, 1, 2} | {v for w in widths for v in
                        ((1 << (w * 8 - 1)) - 1, 1 << (w * 8 - 1), (1 << (w * 8)) - 1)})
        values = bounds + [None] * args.states
        for value in values:
            for mask in (0, 1, 3):
                for residue in range(mask + 1):
                    serial += 1
                    for carry in (0, 1):
                        st = vt.random_state(rng)
                        st["fc"] = 0x100 + 4 * serial + residue
                        st["flags"] = (st["flags"] & ~0x401) | carry | (carry << 10)
                        undo, ready = prepare_boundary(m, st, window, sites, value) if value is not None else ([], True)
                        try:
                            if not ready:
                                problems.append("cannot seed boundary at main+%X" % window[0])
                                continue
                            ref = m.run_window(st, window, sites, True, bool(residue))
                            m.mu.mem_write(pool + hdr["mask"], bytes([0 if args.broken == "gate" else mask]))
                            before = [counters(m, hdr, pool, s) for s in sites]
                            got = m.run_window(st, window, sites, False, False, patches[wi])
                            diff = vt.compare(ref, got, pool, pool + hdr["pool_size"])
                            cases += 1
                            skipped += bool(residue)
                            neutral += mask == 0
                            seen = {s[1] for s in sites if main_base + s[1] in ref["executed"]}
                            # the in-game measurement: a pass for every run
                            # through the step; on the first of its tick, a
                            # tick, and a counted tick exactly when it counts
                            for s, c0 in zip(sites, before):
                                c1 = counters(m, hdr, pool, s)
                                ran = s[1] in seen
                                new = ran and last[s[0]] != st["fc"]
                                if new:
                                    last[s[0]] = st["fc"]
                                repeats += ran and not new
                                if ran:
                                    tick_paths[s[0]].add(
                                        "repeat" if not new else "skipped" if residue else "counted")
                                want = (int(new), int(new and not residue), last[s[0]], int(ran))
                                moved = ((c1[0] - c0[0]) & 0xFFFFFFFF, (c1[1] - c0[1]) & 0xFFFFFFFF,
                                         c1[2], (c1[3] - c0[3]) & 0xFFFFFFFF)
                                if moved != want and diff is not None:
                                    diff = diff + ["measurement of %X: ticks %+d, counted %+d, last "
                                                   "%X, passes %+d; want %+d, %+d, %X, %+d" % (
                                                       s[0], *moved, *want)]
                                counted_checks[0] += 1
                            (skipped_sites if residue else stock_sites).update(seen)
                            if diff is None:
                                problems.append("inconclusive faults at main+%X" % window[0])
                            elif diff:
                                problems.append("main+%X N%d tick%d old=%s CF%d: %s" % (
                                    window[0], mask + 1, residue, value, carry, "; ".join(diff[:3])))
                        finally:
                            for addr, old in reversed(undo):
                                m.mu.mem_write(addr, old)
                        if len(problems) >= 25:
                            break
                    if len(problems) >= 25:
                        break
                if len(problems) >= 25:
                    break
            if len(problems) >= 25:
                break
        if len(problems) >= 25:
            break
        if len(m.demand) > 256:
            m.reset_demand()
    expected_sites = {s[1] for s in hdr["sites"]}
    if expected_sites - stock_sites:
        problems.append("counting paths not exercised: " + ", ".join(
            "%X" % s for s in sorted(expected_sites - stock_sites)))
    if expected_sites - skipped_sites:
        problems.append("skip paths not exercised: " + ", ".join(
            "%X" % s for s in sorted(expected_sites - skipped_sites)))
    # every site's measurement seen on a counted tick, a skipped tick, and a
    # second pass on one tick
    short = sorted(a for a, p in tick_paths.items() if p != {"counted", "skipped", "repeat"})
    if short:
        problems.append("measurement paths not exercised: " + ", ".join(
            "%X (%s)" % (a, "/".join(sorted(tick_paths[a])) or "none") for a in short))
    print("emulation: %d cases (%d N1, %d skipped ticks), %d windows; %d counter checks, "
          "%d of them a second pass on the same tick" % (
              cases, neutral, skipped, len(hdr["windows"]), counted_checks[0], repeats))
    for problem in problems[:25]:
        print("  FAIL " + problem)
    print("FAILED (%d)" % len(problems) if problems else "integer skips verified")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
