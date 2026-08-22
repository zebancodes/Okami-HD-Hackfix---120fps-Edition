#!/usr/bin/env python
"""Copy the built proxy DLL and ini into the Okami HD game directory."""
import os
import shutil
import sys

GAME_DIR = r"D:\SteamLibrary\steamapps\common\Okami"
HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(os.path.dirname(HERE), ".build", "bin")


def main():
    src_dll = os.path.join(BIN, "dinput8.dll")
    src_ini = os.path.join(BIN, "okami.ini")
    if not os.path.exists(src_dll):
        print(f"build output missing: {src_dll}")
        return 1
    if not os.path.exists(GAME_DIR):
        print(f"game dir missing: {GAME_DIR}")
        return 1
    dst_dll = os.path.join(GAME_DIR, "DINPUT8.dll")
    dst_ini = os.path.join(GAME_DIR, "okami.ini")
    shutil.copy2(src_dll, dst_dll)
    print(f"deployed {dst_dll}")
    if os.path.exists(src_ini):
        shutil.copy2(src_ini, dst_ini)
        print(f"deployed {dst_ini}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
