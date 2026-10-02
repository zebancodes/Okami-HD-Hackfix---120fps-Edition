#!/usr/bin/env python
"""Copy the built proxy DLL and ini into the Okami HD game directory.

Usage: deploy.py [--game-dir DIR] [--build-dir DIR] [--uninstall]

The game directory is auto-detected from the Steam library list (or taken
from the OKAMI_DIR environment variable / --game-dir). An existing okami.ini
in the game folder is left untouched so user settings survive redeploys.
"""
import argparse
import os
import shutil
import sys

from gamedir import find_game_dir

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEPLOYED = ("DINPUT8.dll", "okami.ini", "okami_hackfix.log")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--build-dir", default=os.path.join(ROOT, ".build", "bin"))
    ap.add_argument("--uninstall", action="store_true",
                    help="remove the deployed files from the game folder")
    args = ap.parse_args()

    game = args.game_dir or find_game_dir()
    if not game or not os.path.isfile(os.path.join(game, "okami.exe")):
        print("game dir not found; pass --game-dir or set OKAMI_DIR")
        return 1

    if args.uninstall:
        for name in DEPLOYED:
            p = os.path.join(game, name)
            if os.path.exists(p):
                os.remove(p)
                print(f"removed {p}")
        return 0

    src_dll = os.path.join(args.build_dir, "dinput8.dll")
    if not os.path.exists(src_dll):
        print(f"build output missing: {src_dll}")
        return 1
    dst_dll = os.path.join(game, "DINPUT8.dll")
    shutil.copy2(src_dll, dst_dll)
    print(f"deployed {dst_dll}")

    src_ini = os.path.join(ROOT, "okami.ini")
    dst_ini = os.path.join(game, "okami.ini")
    if os.path.exists(dst_ini):
        print(f"kept existing {dst_ini}")
    elif os.path.exists(src_ini):
        shutil.copy2(src_ini, dst_ini)
        print(f"deployed {dst_ini}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
