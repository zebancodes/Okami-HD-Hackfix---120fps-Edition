#!/usr/bin/env python3
"""Rows for gen_world_anims.MANIFEST from a spec, with the instruction text
and the constants read from main.dll (so a row cannot be mistyped).

    .venv/Scripts/python tools/manifest_rows.py SPEC [--insert]

Spec lines (blank lines skipped):
    # a comment             copied as a comment
    group NAME              the group of the rows after it (default actor)
    KIND RVA [EXTRA] | why  one row

EXTRA: `down`, `float`, `scale:RVA` (("scale", RVA)), `notyet:RVA`, or a
python literal without spaces (a register counter's
`(load,store,(path,...),None)`). lin/sq/blend take the constant from the
instruction's rip operand; a form other than the 8-byte one is flagged.
--insert puts the rows at the end of the MANIFEST; the generator proves
each (tools/gen_world_anims.py prints REFUSED and writes nothing if one
fails).
"""
import os
import struct
import sys
import textwrap

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

BASE = 0x180000000
GEN = os.path.join(HERE, "gen_world_anims.py")


def rows(spec):
    img = pefile.PE(os.path.join(GAME, "main.dll"), fast_load=True).get_memory_mapped_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    group, out = "actor", []
    for raw in open(spec, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith("#"):
            out.append("    " + line)
            continue
        if line.startswith("group "):
            group = line.split()[1]
            continue
        head, _, reason = line.partition("|")
        parts = head.split()
        kind, rva = parts[0], int(parts[1], 16)
        i = next(md.disasm(bytes(img[rva:rva + 16]), BASE + rva, 1))
        text = "%s %s" % (i.mnemonic, i.op_str)
        extra = "None"
        if kind in ("callscale", "callblend") and len(parts) == 2:
            limit_registers = {0x2DA570: "xmm3", 0x2DDF90: "xmm3",
                               0x23A2E0: "xmm1", 0x2DA410: "xmm1",
                               0x2DA460: "xmm1", 0x20EA30: "xmm2",
                               0x20E130: "xmm1", 0x20E030: "xmm2"}
            if i.mnemonic not in ("call", "jmp") or i.operands[0].type != capstone.x86.X86_OP_IMM:
                sys.exit("%X is not a direct call" % rva)
            target = i.operands[0].imm - BASE
            if target not in limit_registers or kind == "callblend" and target != 0x2DA570:
                sys.exit("%X: call signature for %X is not known" % (rva, target))
            extra = '(0x%X, "%s")' % (target, limit_registers[target])
        elif kind in ("lin", "sq", "blend"):
            mem = [op for op in i.operands if op.type == capstone.x86.X86_OP_MEM][0]
            if mem.mem.base != capstone.x86.X86_REG_RIP:
                sys.exit("%X: %s has no rip operand" % (rva, text))
            c = rva + i.size + mem.mem.disp
            extra = "(0x%X, %r)" % (c, struct.unpack_from("<f", img, c)[0])
            if i.size != 8:
                out.append("    # !! %X is %d bytes, not the 8-byte rip form" % (rva, i.size))
        elif len(parts) > 2:
            e = parts[2]
            extra = ('"%s"' % e if e in ("down", "float", "factor", "phase5", "title", "remain", "reg") else
                     '("scale", 0x%X)' % int(e[6:], 16) if e.startswith("scale:") else
                     "0x%X" % int(e[7:], 16) if e.startswith("notyet:") else e)
        head = '    ("%s", "%s", 0x%X, "%s", %s,' % (group, kind, rva, text, extra)
        if len(head) > 100:
            out += ['    ("%s", "%s", 0x%X, "%s",' % (group, kind, rva, text), "     %s," % extra]
        else:
            out.append(head)
        pieces = textwrap.wrap(reason.strip(), 80, break_long_words=False,
                               break_on_hyphens=False)
        for n, p in enumerate(pieces):
            last = n == len(pieces) - 1
            out.append('     "%s%s"%s' % (p.replace('"', '\\"'), "" if last else " ",
                                          ")," if last else ""))
    return out


def main():
    out = rows(sys.argv[1])
    if "--insert" in sys.argv:
        s = open(GEN, encoding="utf-8").read()
        key = "\n]\n\n# Code nothing can reach"
        if s.count(key) != 1:
            sys.exit("cannot find the end of MANIFEST")
        s = s.replace(key, "\n" + "\n".join(out) + key)
        open(GEN, "w", encoding="utf-8").write(s)
        print("inserted %d rows" % sum(1 for ln in out if ln.startswith('    ("')))
    else:
        print("\n".join(out))


if __name__ == "__main__":
    main()
