#!/usr/bin/env python3
"""Check which script F3 runs for every shape of [Harness] Step<n> in okami.ini.

Loads the built DLL into this process and calls its OkamiHarnessScriptSelfTest
export -- the real harnessLoadScript(), reading a real okami.ini through
GetPrivateProfileString -- once per case, all in one process so that a custom
script left over from an earlier case would show:

  no Step keys           the built-in script, its normal length
  a valid custom script  exactly its steps, its length
  a malformed first step, a malformed step after valid ones, an unknown
  action (first or later), a zero length
                         the complete built-in script, identical to the
                         first case: nothing of the custom steps survives

The built-in script is also checked against kHarnessDefault in the source.

    .venv/Scripts/python tools/verify_harness_script.py [--dll .build/bin/dinput8.dll]
Exits non-zero on any mismatch.
"""
import argparse
import ctypes
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "src", "dinput8_proxy.cpp")

VALID = ["500,0,1,none,run", "300,0,1,jump,0.50,hop", "450,-1,0,none,-0.35,sidestep"]
CASES = [
    ("no Step keys", [], "builtin"),
    ("valid custom script", VALID, "custom"),
    ("malformed first step (the review's example)", ["600,2,0,none,invalid direction"],
     "builtin"),
    ("malformed step after two valid ones", VALID[:2] + ["abc"], "builtin"),
    ("unknown action after valid steps", VALID[:2] + ["300,0,1,fly,oops"], "builtin"),
    ("unknown action on the first step", ["300,0,1,fly,oops"], "builtin"),
    ("zero-length step after a valid one", VALID[:1] + ["0,0,1,none,nothing"], "builtin"),
    ("valid custom script again, after the failures", VALID, "custom"),
]


def builtin_from_source():
    src = open(SRC, encoding="utf-8").read()
    body = re.search(r"kHarnessDefault\[\] = \{(.*?)\n\};", src, re.S).group(1)
    steps = re.findall(r"\{(\d+), (-?\d), (-?\d), (\w+), ([-+0-9.]+)f, \"([^\"]*)\"\}", body)
    return [(int(ms), int(dx), int(dy), "none" if act == "0" else "jump", float(dh), lab)
            for ms, dx, dy, act, dh, lab in steps]


def parse(text):
    lines = text.strip().splitlines()
    kind, n, total = lines[0].split()
    steps = []
    for ln in lines[1:]:
        ms, dx, dy, act, dh, lab = ln.split(",", 5)
        steps.append((int(ms), int(dx), int(dy), act, float(dh), lab))
    return kind, int(n), int(total), steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    args = ap.parse_args()
    work = tempfile.mkdtemp(prefix="okami_harness_script_")
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    fn = ctypes.WinDLL(dll).OkamiHarnessScriptSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    fn.restype = ctypes.c_int

    builtin = builtin_from_source()
    results, fails = {}, 0
    for k, (name, steps, want) in enumerate(CASES):
        d = os.path.join(work, "case%d" % k)
        os.makedirs(d)
        with open(os.path.join(d, "okami.ini"), "w") as f:
            f.write("[Harness]\nHarness=1\n")
            for i, s in enumerate(steps):
                f.write("Step%d=%s\n" % (i + 1, s))
        rc = fn(d.encode("mbcs"), d.encode("mbcs"))
        if rc != 0:
            print("FAIL %s: self-test returned %d" % (name, rc))
            fails += 1
            continue
        text = open(os.path.join(d, "script.txt")).read()
        kind, n, total, got = parse(text)
        results[name] = text
        if want == "builtin":
            expect = builtin
        else:
            expect = []
            for s in steps:
                p = s.split(",")
                dh = float(p[4]) if len(p) == 6 else 0.0
                expect.append((int(p[0]), int(p[1]), int(p[2]), p[3], dh, p[-1]))
        problems = []
        if kind != want:
            problems.append("ran the %s script" % kind)
        if got != expect:
            problems.append("steps %s, want %s" % (got, expect))
        if n != len(expect) or total != sum(s[0] for s in expect):
            problems.append("%d steps / %d ms, want %d / %d"
                            % (n, total, len(expect), sum(s[0] for s in expect)))
        if want == "builtin" and name != CASES[0][0] and text != results.get(CASES[0][0]):
            problems.append("differs from the no-Step-keys run")
        fails += bool(problems)
        print("%s %-48s -> %s, %d steps, %d ms%s" % ("FAIL" if problems else "ok  ", name, kind,
                                                     n, total,
                                                     (": " + "; ".join(problems)) if problems
                                                     else ""))
    print("\n%s" % ("FAILED (%d)" % fails if fails else "harness script selection verified"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
