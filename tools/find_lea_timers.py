#!/usr/bin/env python3
"""Find the third encoding of the character action countdown and emit the table.

tools/find_action_timers.py finds the countdown written as `dec` through a
register, and tools/find_memory_timers.py finds it written straight against
memory. There is a third form, and it is the one the compiler picks when the
handler needs the value from *before* the count:

    movzx eax, word ptr [rdx+0xE3C]
    lea   eax, [rcx - 1]             <- new = old - 1, without touching flags
    mov   word ptr [rdx+0xE3C], ax
    test  cx, cx                     <- ... and the branch tests the OLD value
    jne   still_running

`dec` would have clobbered the flags and destroyed the old value, so `lea` is
used instead. 107 sites in this build do it, over +0xE3C (101), +0xE3E (4) and
+0xE40 (2), and nine of them count up rather than down.

Skipping the `lea` and its store on alternate ticks is the same fix as the
other two forms, and here it needs no flag work at all: neither instruction
touches the flags, so the stub simply preserves them across its own parity
test, and the `test`/`cmp` that follows reads the untouched load register and
therefore behaves exactly as though this tick had not happened.

What it does need is the register. The `lea` writes a *different* register from
the one it reads (that is true at all 107 sites), and at a few of them the
branch tests the new value rather than the old one. Leaving the destination
untouched on a skipped tick would compare stale contents, so the skip path
copies the old value into it with a synthesised `mov dst, src`. The destination
then holds what the field holds, one tick behind, which is the whole point of
the fix -- and it makes the patch safe at every site regardless of what reads
that register afterwards, rather than only at the ones a fixed look-ahead
window can see.

Sites are dropped if the `lea` and its store are not adjacent, if the pair is
longer than the table's 11 bytes, if a known branch target lands inside them,
or if the field is used as an array index inside the same function (see
find_memory_timers.py for why).

    python tools/find_lea_timers.py
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

LOAD = re.compile(r"^(\w+), (?:byte|word|dword) ptr \[(\w+) \+ (0x[0-9a-f]+)\]$")
STORE = re.compile(r"^(?:byte|word|dword) ptr \[(\w+) \+ (0x[0-9a-f]+)\], (\w+)$")
LEA = re.compile(r"^(\w+), \[(\w+) ([+-]) 1\]$")

REGNO = {"rax": 0, "rcx": 1, "rdx": 2, "rbx": 3, "rsp": 4,
         "rbp": 5, "rsi": 6, "rdi": 7}
for _n in range(8, 16):
    REGNO["r%d" % _n] = _n

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
    out = set()
    for a, m, o, s in insns:
        if (m.startswith("j") or m == "call") and o.startswith("0x"):
            out.add(int(o, 16) - BASE_IMAGE)
    return out


def functions(pe):
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


def main():
    import bisect
    path = os.path.join(GAME, "main.dll")
    img, insns = disassemble(path)
    funcs = functions(pefile.PE(path, fast_load=True))
    begins = [b for b, _ in funcs]
    indexed = index_fields(insns, funcs)
    targets = branch_targets(insns)

    rows, dropped = [], collections.Counter()
    for i, (a, m, o, s) in enumerate(insns):
        if m not in ("mov", "movzx", "movsx"):
            continue
        g = LOAD.match(o)
        if not g:
            continue
        loadreg, base, off = g.groups()
        if off not in FIELDS or base in ("rsp", "rbp"):
            continue
        src = _Q.get(loadreg)
        for j in range(i + 1, min(i + 6, len(insns))):
            a2, m2, o2, s2 = insns[j]
            if m2 in ("call", "ret", "jmp"):
                break
            if m2 != "lea":
                continue
            lg = LEA.match(o2)
            if not lg or _Q.get(lg.group(2)) != src:
                break
            dst = _Q.get(lg.group(1))
            if lg.group(1).startswith("r") and not lg.group(1).endswith("d"):
                dropped["64-bit lea destination"] += 1
                break
            for j2 in range(j + 1, min(j + 4, len(insns))):
                a3, m3, o3, s3 = insns[j2]
                sg = STORE.match(o3)
                if not (m3 == "mov" and sg and sg.group(2) == off
                        and sg.group(1) == base and _Q.get(sg.group(3)) == dst):
                    continue
                if a2 + s2 != a3:
                    dropped["lea and store not adjacent"] += 1
                    break
                span = s2 + s3
                if span > 11:
                    dropped["pair longer than the table"] += 1
                    break
                if any(t in targets for t in range(a2 + 1, a2 + span)):
                    dropped["branch target inside"] += 1
                    break
                k = bisect.bisect_right(begins, a2) - 1
                if k >= 0 and funcs[k][0] <= a2 < funcs[k][1] \
                        and (funcs[k][0], off) in indexed:
                    dropped["field is an array index here"] += 1
                    break
                rows.append((a2, span, REGNO[dst], REGNO[src], off, lg.group(3),
                             bytes(img[a2:a2 + span])))
                break
            break

    rows.sort()
    seen, uniq = set(), []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        uniq.append(r)

    fields = collections.Counter(r[4] for r in uniq)
    signs = collections.Counter(r[5] for r in uniq)
    out = [
        "// Generated by tools/find_lea_timers.py -- do not edit by hand.",
        "// See the README section \"Durations at 60 fps\".",
        "//",
        "// The third encoding of the action countdown: `lea new, [old +/- 1]` followed",
        "// by the store, used where the handler needs the value from before the count",
        "// and so cannot afford `dec`'s flags. Skipping the pair needs no flag work --",
        "// neither instruction touches the flags -- but the skip path must copy the old",
        "// value into the lea's destination, because at a few sites the branch tests",
        "// that register rather than the load register.",
        "//",
        "// %d sites: %s; %s." % (
            len(uniq),
            ", ".join("%s x%d" % (f, n) for f, n in sorted(fields.items())),
            ", ".join("%s x%d" % ("down" if k == "-" else "up", n)
                      for k, n in sorted(signs.items()))),
        "",
        "struct LeaTimerSite {",
        "    uint32_t rva;      // the lea",
        "    uint8_t len;       // bytes of lea + store to relocate",
        "    uint8_t dstReg;    // the lea's destination register, 0-15",
        "    uint8_t srcReg;    // the register holding the pre-count value, 0-15",
        "    uint8_t orig[11];  // exactly what must be there",
        "};",
        "",
        "static const LeaTimerSite kLeaTimerSites[] = {",
    ]
    for rva, span, dst, src, off, sign, raw in uniq:
        body = ", ".join("0x%02X" % b for b in raw)
        pad = ", ".join(["0x00"] * (11 - len(raw)))
        out.append("    {0x%06X, %2d, %2d, %2d, {%s%s}},  // %s %s"
                   % (rva, span, dst, src, body, (", " + pad) if pad else "",
                      "down" if sign == "-" else "up  ", off))
    out.append("};")

    dest = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "src", "lea_timers.h"))
    with open(dest, "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("%d sites written to src/lea_timers.h" % len(uniq))
    print("fields: %s" % dict(fields))
    if dropped:
        print("dropped: %s" % dict(dropped))


if __name__ == "__main__":
    main()
