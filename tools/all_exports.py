#!/usr/bin/env python
"""Dump all exports of the given binary as RVA:name."""
import os
import sys

import pefile

from gamedir import GAME  # auto-detected Steam install (or OKAMI_DIR)


def main():
    for name in sys.argv[1:] or ["main.dll"]:
        path = os.path.join(GAME, name)
        pe = pefile.PE(path, fast_load=False)
        print(f"===== exports of {name} =====")
        if not hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            print("  (none)")
            continue
        for e in sorted(pe.DIRECTORY_ENTRY_EXPORT.symbols, key=lambda s: s.address):
            nm = e.name.decode() if e.name else f"ord{e.ordinal}"
            print(f"{hex(e.address)} {nm}")


if __name__ == "__main__":
    main()
