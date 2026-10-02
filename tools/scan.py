#!/usr/bin/env python
"""Scan PE exports and ASCII/UTF-16 strings in a binary."""
import os
import re
import sys

import pefile

from gamedir import GAME  # auto-detected Steam install (or OKAMI_DIR)


def exports(path, pat):
    pe = pefile.PE(path, fast_load=False)
    if not hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        return
    print(f"--- exports of {os.path.basename(path)} ---")
    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        name = e.name.decode() if e.name else f"ord{e.ordinal}"
        if pat.search(name):
            print(f"  {hex(e.address)} {name}")


def strings(path, pat, min_len=4):
    data = open(path, "rb").read()
    print(f"--- strings of {os.path.basename(path)} ---")
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        s = m.group().decode("ascii", "replace")
        if pat.search(s):
            print(f"  {hex(m.start())} {s}")


def main():
    what, pat = sys.argv[1], sys.argv[2]
    pat = re.compile(pat, re.I)
    for name in ["okami.exe", "main.dll", "flower_kernel.dll"]:
        path = os.path.join(GAME, name)
        if what == "exports":
            exports(path, pat)
        else:
            strings(path, pat)


if __name__ == "__main__":
    main()
