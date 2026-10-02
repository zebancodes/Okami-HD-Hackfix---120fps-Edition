#!/usr/bin/env python3
"""Check the enemy watch offline, without the game.

1. src/enemy_watch.h is what tools/gen_enemy_watch.py writes from the
   installed main.dll (the classes deriving from cEm, and the instructions
   that show the fields the watch reads).
2. The built DLL's OkamiEnemyWatchSelfTest, on main.dll mapped and never run:
   * the install: the evidence, then every class's update slot at a thunk that
     calls the sampler and jumps to that class's own update, each thunk with
     unwind data RtlLookupFunctionEntry finds;
   * the thunk itself, around two stand-in updates: integer and float
     arguments reach them though the sampler clobbers every argument
     register, and their return values reach the caller;
   * a synthetic enemy hit twice and flown through the watch at 30, at a fixed
     120 and at 120 with only its fall fixed: the fixed 120 must read as stock
     at every stock tick, the half-fixed one four times the ground;
   * the watcher's poll ends an episode whose enemy stopped updating.
   `--break sample` samples every update instead of every stock tick: the
   fixed 120 must then fail to read as stock.

    .venv/Scripts/python tools/verify_enemy_watch.py [--dll .build/bin/dinput8.dll]
"""
import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    ap.add_argument("--break", dest="brk", choices=["sample"], default=None)
    args = ap.parse_args()
    gen = subprocess.run([sys.executable, os.path.join(HERE, "gen_enemy_watch.py"), "--check"],
                         capture_output=True, text=True)
    print(gen.stdout.rstrip())
    if gen.returncode:
        print("enemy watch: FAILED (the header)")
        return 1
    work = args.out or tempfile.mkdtemp(prefix="okami_enemy_selftest_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    fn = ctypes.WinDLL(dll).OkamiEnemyWatchSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    fn.restype = ctypes.c_int
    rc = fn(os.path.join(GAME, "main.dll").encode("mbcs"), work.encode("mbcs"),
            1 if args.brk == "sample" else 0)
    print(open(os.path.join(work, "report.txt")).read().rstrip())
    print("enemy watch: %s (rc %d)" % ("verified" if rc == 0 else "FAILED", rc))
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
