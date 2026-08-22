#!/usr/bin/env python
"""Compact import summary: which DLLs each binary imports and which functions."""
import os
import sys

import pefile

GAME = r"D:\SteamLibrary\steamapps\common\Okami"


def main():
    for name in sys.argv[1:] or ["okami.exe", "main.dll", "flower_kernel.dll"]:
        path = os.path.join(GAME, name)
        pe = pefile.PE(path, fast_load=False)
        print(f"===== {name} =====")
        if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            print("  (no imports)")
            continue
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode()
            funcs = [
                imp.name.decode() if imp.name else f"ord{imp.ordinal}"
                for imp in entry.imports
            ]
            print(f"[{dll}] {len(funcs)}")
            for fn in funcs:
                print(f"   {fn}")


if __name__ == "__main__":
    main()
