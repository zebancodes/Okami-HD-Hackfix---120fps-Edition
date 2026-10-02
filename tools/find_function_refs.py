#!/usr/bin/env python3
"""Show direct, RIP-relative, and data-pointer references to function RVAs.

Uses read_candidates.py's cached disassembly. This includes address-taking
instructions that its direct-call listing intentionally omits.
"""
import os
import pickle
import re
import struct
import sys

import pefile
from gamedir import GAME

CACHE = os.path.join(os.path.dirname(__file__), ".disasm_cache", "read_candidates.pkl")
RIP = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
BASE = 0x180000000


def main():
    targets = {int(a, 16) for a in sys.argv[1:]}
    data = pickle.load(open(CACHE, "rb"))
    for at, mnemonic, operands, size in data["insns"]:
        target = None
        if mnemonic in ("call", "jmp") and operands.startswith("0x"):
            target = int(operands, 16) - BASE
        else:
            match = RIP.search(operands)
            if match:
                displacement = int(match.group(2), 16)
                target = at + size + (displacement if match.group(1) == "+" else -displacement)
        if target in targets:
            print(f"{at:06X}  {mnemonic} {operands}  -> {target:06X}")
    pe = pefile.PE(os.path.join(GAME, "main.dll"), fast_load=True)
    image = pe.get_memory_mapped_image()
    for target in sorted(targets):
        needle = struct.pack("<Q", BASE + target)
        for section in pe.sections:
            if section.Characteristics & 0x20000000:
                continue
            name = section.Name.rstrip(b"\0").decode("ascii", "replace")
            lo = section.VirtualAddress
            hi = min(len(image), lo + section.Misc_VirtualSize)
            at = image.find(needle, lo, hi)
            while at >= 0:
                print(f"{at:06X}  {name} pointer -> {target:06X}")
                at = image.find(needle, at + 1, hi)


if __name__ == "__main__":
    main()
