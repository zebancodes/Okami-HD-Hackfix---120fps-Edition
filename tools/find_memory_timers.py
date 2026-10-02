#!/usr/bin/env python3
"""Find the memory-operand character timer counters and emit the C table.

tools/find_action_timers.py finds the *register* form of the engine's action
countdown -- load the field, decrement the register, store it back. That is
only half of them. When the compiler has no further use for the value it emits
the count straight against memory instead, and that form is invisible to the
other tool:

    dec   word ptr [rsi+0xE3C]        <- no load, no store, no register
    cmp   word ptr [rsi+0xE3C], 0
    jg    still_running
    inc   byte ptr [rsi+0xE36]        ... otherwise advance the sub-state

Both forms mean the same thing and both run twice as fast at 60 fps. The
memory form accounts for roughly 400 further sites, spread over the same five
duration fields of the shared character object:

    +0xE3C   the main action timer
    +0xE3E   a secondary timer
    +0xE40   a third
    +0xE42   a fourth (count-up only, seen in cBallObj/cEnemyObj/objScroll)
    +0xE76   a fifth

Roughly a third count *up* toward a limit rather than down; both directions are
durations in ticks and both need to advance half as often.

Flags. The register form could be skipped behind pushfq/popfq because the
displaced store preserved the flags anyway. Here the counter *is* the flag
producer: 159 of the sites are `dec word ptr [x+0xE3C]` followed directly by
`jne`, plus a handful of `jns` and `je`. On a skipped tick the answer those
consumers want is always the same -- "not finished yet" -- which is ZF=0 and
SF=0, so the skip path sets exactly that with `test rsp, rsp` (rsp is never
zero and bit 63 is never set in user mode) instead of restoring stale flags.
That is also correct at the boundary: a timer sitting at 0 keeps going for one
more tick and then expires on the next real decrement, which is precisely the
one-tick-later behaviour the fix is for.

Sites whose bytes are shorter than a 5-byte jump, that carry a rip-relative
operand, or that have a known branch target inside them are dropped.

So is any site whose field is used as an *array index* inside the same
function. hm68 is the one case in this build: it steps `+0xE3C` for 60 ticks
and then uses `+0xE3E` to select the next of its sub-objects from a pointer
array at `+0x1318`. That field is a sequence position, not a duration, and
slowing it would change which object is addressed rather than how long
anything lasts. Function bounds come from the PE's .pdata table, so the test
is exact rather than a guess at a range.

    python tools/find_memory_timers.py
"""
import collections
import os
import re
import sys

try:
    import pefile
    import capstone
except ImportError:
    sys.exit("needs pefile and capstone: pip install pefile capstone")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402

BASE_IMAGE = 0x180000000
FIELDS = ("0xe3c", "0xe3e", "0xe40", "0xe42", "0xe76")

MEM = re.compile(r"^(byte|word|dword) ptr \[(\w+) \+ (0x[0-9a-f]+)\]$")
MEM1 = re.compile(r"^(byte|word|dword) ptr \[(\w+) \+ (0x[0-9a-f]+)\], 1$")
RIP = re.compile(r"\[rip [+-] 0x[0-9a-f]+\]")
LOAD = re.compile(r"^(\w+), (?:byte|word|dword) ptr \[(\w+) \+ (0x[0-9a-f]+)\]$")

_Q = {}
for _q, _d, _w, _b in [("rax", "eax", "ax", "al"), ("rbx", "ebx", "bx", "bl"),
                       ("rcx", "ecx", "cx", "cl"), ("rdx", "edx", "dx", "dl"),
                       ("rsi", "esi", "si", "sil"), ("rdi", "edi", "di", "dil"),
                       ("rbp", "ebp", "bp", "bpl"), ("rsp", "esp", "sp", "spl")]:
    for _r in (_q, _d, _w, _b):
        _Q[_r] = _q
for _n in range(8, 16):
    _q = "r%d" % _n
    for _r in (_q, _q + "d", _q + "w", _q + "b"):
        _Q[_r] = _q


def functions(pe):
    """[(begin, end)] from the PE exception table, sorted."""
    try:
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
        out = [(f.struct.BeginAddress, f.struct.EndAddress)
               for f in pe.DIRECTORY_ENTRY_EXCEPTION]
    except Exception:
        return []
    out.sort()
    return out


def index_fields(insns, funcs):
    """{(function begin, field): True} where the field is used as an array index."""
    import bisect
    begins = [b for b, _ in funcs]
    bad = {}
    for i, (a, m, o, s) in enumerate(insns):
        if m not in ("mov", "movzx", "movsx", "movsxd"):
            continue
        g = LOAD.match(o)
        if not g:
            continue
        dst, base, off = g.groups()
        if off not in FIELDS:
            continue
        q = _Q.get(dst)
        if not q:
            continue
        for j in range(i + 1, min(i + 5, len(insns))):
            if re.search(r"\[\w+ \+ %s\*[248]" % re.escape(q), insns[j][2]):
                k = bisect.bisect_right(begins, a) - 1
                if k >= 0 and funcs[k][0] <= a < funcs[k][1]:
                    bad[(funcs[k][0], off)] = True
                break
    return bad


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


def branch_targets(insns):
    """Every direct branch destination, so a patch never lands mid-instruction."""
    out = set()
    for a, m, o, s in insns:
        if (m.startswith("j") or m == "call") and o.startswith("0x"):
            out.add(int(o, 16) - BASE_IMAGE)
    return out


def main():
    import bisect
    path = os.path.join(GAME, "main.dll")
    img, insns = disassemble(path)
    funcs = functions(pefile.PE(path, fast_load=True))
    begins = [b for b, _ in funcs]
    indexed = index_fields(insns, funcs)
    targets = branch_targets(insns)
    rows, dropped = [], collections.Counter()
    for a, m, o, s in insns:
        if m in ("dec", "inc"):
            g = MEM.match(o)
            kind = m
        elif m == "sub":
            g = MEM1.match(o)
            kind = "dec"
        elif m == "add":
            g = MEM1.match(o)
            kind = "inc"
        else:
            continue
        if not g:
            continue
        width, base, off = g.groups()
        if off not in FIELDS or base in ("rsp", "rbp"):
            continue
        if RIP.search(o):
            dropped["rip-relative"] += 1
            continue
        if s < 5:
            dropped["shorter than a jmp"] += 1
            continue
        if s > 8:
            dropped["too long for the table"] += 1
            continue
        if any(t in targets for t in range(a + 1, a + s)):
            dropped["branch target inside"] += 1
            continue
        k = bisect.bisect_right(begins, a) - 1
        if k >= 0 and funcs[k][0] <= a < funcs[k][1]                 and (funcs[k][0], off) in indexed:
            dropped["field is an array index here"] += 1
            continue
        rows.append((a, s, kind, width, off, bytes(img[a:a + s])))

    rows.sort()
    fields = collections.Counter(r[4] for r in rows)
    kinds = collections.Counter(r[2] for r in rows)
    out = [
        "// Generated by tools/find_memory_timers.py -- do not edit by hand.",
        "// See the README section \"Durations at 60 fps\".",
        "//",
        "// The memory-operand half of the action countdown: `dec word ptr [obj+field]`",
        "// with no load and no store, which tools/find_action_timers.py cannot see.",
        "// Skipping it on alternate ticks makes the duration last the same real time",
        "// at 60 fps. Here the counter is also the flag producer, so the skip path",
        "// publishes \"not finished yet\" (ZF=0, SF=0) rather than stale flags.",
        "//",
        "// %d sites: %s; %s." % (
            len(rows),
            ", ".join("%s x%d" % (f, n) for f, n in sorted(fields.items())),
            ", ".join("%s x%d" % (k, n) for k, n in sorted(kinds.items()))),
        "",
        "struct MemTimerSite {",
        "    uint32_t rva;     // the dec/inc instruction",
        "    uint8_t len;      // its length, always >= 5 so a jmp fits",
        "    uint8_t orig[8];  // exactly what must be there",
        "};",
        "",
        "static const MemTimerSite kMemTimerSites[] = {",
    ]
    for rva, size, kind, width, off, raw in rows:
        body = ", ".join("0x%02X" % b for b in raw)
        pad = ", ".join(["0x00"] * (8 - len(raw)))
        out.append("    {0x%06X, %d, {%s%s}},  // %s %s %s" % (
            rva, size, body, (", " + pad) if pad else "", kind, width, off))
    out.append("};")

    dest = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "src", "memory_timers.h"))
    with open(dest, "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("%d sites written to src/memory_timers.h" % len(rows))
    print("fields: %s" % dict(fields))
    print("direction: %s" % dict(kinds))
    if dropped:
        print("dropped: %s" % dict(dropped))


if __name__ == "__main__":
    main()
