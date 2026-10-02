#!/usr/bin/env python3
"""Check the loading-screen field watch offline, without the game.

Loads the built DLL into this process and calls its OkamiLoadingWatchSelfTest
on the game's main.dll (mapped, never run). The export installs the watch --
the check that vtable main+6AFF88 slot 3 holds cCockLoading's update, and the
write of the wrapper into it -- then plays the watch a simulated loading screen
on a synthetic clock in four cases: stock 30, 120 without the fixes, 120 and 60
with them (the dots on the counter frame_clocks.h gives their read, through the
DLL's real frameClockStep). The watch has to read stock, stock, stock and 4x
fast, and a screen has to close half a second after its last update.

    .venv/Scripts/python tools/verify_loading_watch.py [--dll .build/bin/dinput8.dll]
"""
import argparse
import ctypes
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    args = ap.parse_args()
    work = args.out or tempfile.mkdtemp(prefix="okami_loading_selftest_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    fn = ctypes.WinDLL(dll).OkamiLoadingWatchSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    fn.restype = ctypes.c_int
    rc = fn(os.path.join(GAME, "main.dll").encode("mbcs"), work.encode("mbcs"))
    print(open(os.path.join(work, "report.txt")).read().rstrip())
    print("loading watch self-test: %s (rc %d)" % ("verified" if rc == 0 else "FAILED", rc))
    return rc


if __name__ == "__main__":
    sys.exit(main())
