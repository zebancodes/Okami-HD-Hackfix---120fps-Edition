#!/usr/bin/env python3
"""Check the fault guard (guardedCall in dinput8_proxy.cpp) in a built DLL.

Calls the DLL's OkamiFaultGuardSelfTest export, which faults inside the guard,
runs clean inside it, faults again and runs clean again, and checks the code
each call returns. It runs here on the main thread, then on four worker threads
at once (the GCC build keeps its guard state per thread), then on the main
thread again. A build whose guard does not catch the fault takes this process
down instead of printing a result.

The MSVC-ABI builds use __try/__except. The GCC build's vectored-handler path
can be built and checked with clang too, where there is no GCC:

    cmake -S . -B <dir> -G Ninja -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_C_COMPILER=clang
          -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS=-DOKAMI_VEH_GUARD
    .venv/Scripts/python tools/verify_fault_guard.py --dll <dir>/bin/dinput8.dll

Exits non-zero on any failure.
"""
import argparse
import ctypes
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    args = ap.parse_args()
    work = tempfile.mkdtemp(prefix="okami_fault_guard_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    fn = ctypes.WinDLL(dll).OkamiFaultGuardSelfTest
    fn.restype = ctypes.c_int
    results = {"main thread": fn()}
    out = {}

    def worker(k):
        out[k] = [fn() for _ in range(3)]
    threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for k in sorted(out):
        results["worker %d (3 runs)" % k] = max(out[k])
    results["main thread again"] = fn()
    fails = 0
    for name, rc in results.items():
        fails += rc != 0
        print("%s %s" % ("ok  " if rc == 0 else "FAIL", name))
    print("\n%s" % ("FAILED (%d)" % fails if fails else "fault guard verified"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
