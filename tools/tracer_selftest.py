#!/usr/bin/env python3
"""Run the tracer build's install code outside the game, and check what it did.

tools/verify_tracer.py proves the stub pool described by the header is
neutral. This proves the DLL installs *that* pool: it loads the built tracer
DLL into this Python process, calls its OkamiTracerSelfTest export -- which maps
main.dll without running any of it (DONT_RESOLVE_DLL_REFERENCES) and runs the
real tracerInstall -- and then compares

  * the pool the DLL built, byte for byte, with the header's code after the
    header's fixups are applied for the addresses the DLL actually used, and
    with freshly initialised records;
  * every window as it now reads in the mapped main.dll with `jmp stub` plus
    int3 fill;

and reads the DLL's own checks of the int3-net lookup, shedding and the dump.
Nothing of the game executes: main.dll is only mapped, and no stub is run.

    python tools/tracer_selftest.py [--dll .build-tracer/bin/dinput8.dll]
"""
import argparse
import ctypes
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import verify_tracer  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build-tracer", "bin", "dinput8.dll"))
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    args = ap.parse_args()

    hdr = verify_tracer.parse_header()
    work = args.out or tempfile.mkdtemp(prefix="okami_tracer_selftest_")
    os.makedirs(work, exist_ok=True)
    # a private copy, so the DLL's log and dumps land in the work directory
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiTracerSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    fn.restype = ctypes.c_int
    rc = fn(os.path.join(GAME, "main.dll").encode("mbcs"), work.encode("mbcs"))

    report = open(os.path.join(work, "report.txt")).read()
    print(report.rstrip())
    fails = 0 if rc == 0 else 1
    vals = dict(ln.split(" ", 1) for ln in report.splitlines() if " " in ln)
    if "pool" not in vals:
        print("no install to compare (rc %d); see %s" % (rc, work))
        return 1
    main_base = int(vals["main"], 16)
    pool = int(vals["pool"], 16)

    # 1. the pool, against the header laid out at the DLL's addresses
    got = open(os.path.join(work, "pool.bin"), "rb").read()
    want = bytearray(hdr["pool_size"])
    co = hdr["code_off"]
    want[co:co + len(hdr["code"])] = hdr["code"]
    for field, nxt, target in hdr["fixups"]:
        if nxt == 0:
            struct.pack_into("<Q", want, field, main_base + target)
        else:
            struct.pack_into("<i", want, field, (main_base + target) - (pool + nxt))
    rs = hdr["rec_size"]
    for i in range(len(hdr["sites"])):
        struct.pack_into("<I", want, i * rs + 0x20, 0xFFFFFFFE)   # lastTick
        struct.pack_into("<I", want, i * rs + 0x34, 0xFFFFFFFE)   # lastChg
    diff = [i for i in range(len(want)) if got[i] != want[i]]
    print("pool: %d bytes compared, %d differ" % (len(want), len(diff)))
    if diff:
        print("  first difference at pool+%X" % diff[0])
        fails += 1

    # 2. every window: jmp to its stub, then int3
    wb = open(os.path.join(work, "windows.bin"), "rb").read()
    pos, bad = 0, 0
    for rva, stub, ooff, ln in hdr["windows"]:
        cur = wb[pos:pos + ln]
        pos += ln
        rel = (pool + stub) - (main_base + rva + 5)
        exp = b"\xE9" + struct.pack("<i", rel) + b"\xCC" * (ln - 5)
        if cur != exp:
            bad += 1
            if bad <= 5:
                print("  window main+%X reads %s" % (rva, cur.hex()))
    print("windows: %d checked, %d wrong" % (len(hdr["windows"]), bad))
    fails += 1 if bad else 0

    dumps = [f for f in os.listdir(os.path.join(work, "okami_tracer"))] \
        if os.path.isdir(os.path.join(work, "okami_tracer")) else []
    print("dump files: %s" % ", ".join(sorted(dumps)))
    print("\nwork dir %s\n%s" % (work, "FAILED" if fails else "self-test passed"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
