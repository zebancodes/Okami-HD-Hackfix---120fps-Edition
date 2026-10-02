#!/usr/bin/env python3
"""Check offline that the installs find their caves when main.dll is crowded.

Every stub and every retargeted value must sit within a rel32 of main.dll.
On 2026-09-25, after a reboot, main.dll loaded at 0x1B96C400000 in among the
heaps instead of high at 0x7FFF..., and the old allocNear (a 64 KB region of
its own for each install, probed outward up to 1 GB) found room for nine
installs: from the decay factors on, nothing went in, among them the shadow
mode byte and the five families that need it (the world animations first).
allocNear now carves page-aligned blocks out of shared chunks, the first one
reserved when the loader maps main.dll.

The built DLL's OkamiCaveSelfTest, in a fresh process that loads the DLL
first (as the game does: flower_kernel.dll, which imports it, is up well
before main.dll):
  * the loader's notification: a DLL named main.dll loaded normally (a copy of
    the system's version.dll; a DONT_RESOLVE_DLL_REFERENCES mapping gets no
    notification) has the first chunk, 1 MB, reserved within its reach;
then main.dll mapped without running it:
  * roomy: the watcher's 18 requests in order, all in one 1 MB chunk;
  * crowded: the address space within reach filled but for --leave single
    64 KB granules spread through it (9, what the reboot left), and the same
    requests: every one handed out;
  * each time: in reach of every byte of the image both ways, page-aligned,
    zeroed, apart, within a rel32 of each other, each chunk a granule clear of
    the image; a block given back (a rollback) and asked for again comes back
    zeroed.
`--break old` hands each request a region of its own, as before: the crowded
run must then fail (it runs out of granules long before the world anims).

    .venv/Scripts/python tools/verify_cave_pressure.py [--dll .build/bin/dinput8.dll]
"""
import argparse
import ctypes
import os
import shutil
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
    ap.add_argument("--leave", type=int, default=9,
                    help="free granules left within reach in the crowded run")
    ap.add_argument("--break", dest="brk", choices=["old"], default=None)
    args = ap.parse_args()
    work = args.out or tempfile.mkdtemp(prefix="okami_cave_selftest_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    fn = ctypes.WinDLL(dll).OkamiCaveSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    fn.restype = ctypes.c_int
    rc = fn(os.path.join(GAME, "main.dll").encode("mbcs"), work.encode("mbcs"), args.leave,
            1 if args.brk == "old" else 0)
    print(open(os.path.join(work, "report.txt")).read().rstrip())
    print("cave pressure: %s (rc %d)" % ("verified" if rc == 0 else "FAILED", rc))
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
