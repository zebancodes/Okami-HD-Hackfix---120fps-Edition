#!/usr/bin/env python
"""Zip the player release: the built DLL, release/README.txt, the optional
release/okami_hackfix.ini and the license, into .release/.

    .venv/Scripts/python tools/make_release.py [--build-dir DIR]

The zip is named after OKAMI_HACKFIX_VERSION and the DLL's sha1, and the
DLL's sha1 and sha256 are printed (a VirusTotal search takes either). Text
files get Windows line endings, since players open them in Notepad and the
ini goes through GetPrivateProfileString. Run it on the DLL the suite passed:
it does not build.
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def crlf(path):
    text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    return text.replace("\n", "\r\n").encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=os.path.join(ROOT, ".build", "bin"))
    args = ap.parse_args()

    dll = open(os.path.join(args.build_dir, "dinput8.dll"), "rb").read()
    src = open(os.path.join(ROOT, "src", "dinput8_proxy.cpp"), encoding="utf-8").read()
    m = re.search(r'#define OKAMI_HACKFIX_VERSION "([^"]+)"', src)
    if not m:
        sys.exit("OKAMI_HACKFIX_VERSION not found in src/dinput8_proxy.cpp")
    sha1 = hashlib.sha1(dll).hexdigest()
    sha256 = hashlib.sha256(dll).hexdigest()

    out_dir = os.path.join(ROOT, ".release")
    os.makedirs(out_dir, exist_ok=True)
    name = "okami_hd_hackfix-%s-%s.zip" % (m.group(1), sha1[:8])
    out = os.path.join(out_dir, name)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("DINPUT8.dll", dll)
        z.writestr("README.txt", crlf(os.path.join(ROOT, "release", "README.txt")))
        z.writestr("okami_hackfix.ini", crlf(os.path.join(ROOT, "release", "okami_hackfix.ini")))
        z.writestr("LICENSE.txt", crlf(os.path.join(ROOT, "LICENSE")))
    print(out)
    print("DINPUT8.dll sha1   %s" % sha1)
    print("DINPUT8.dll sha256 %s" % sha256)
    return 0


if __name__ == "__main__":
    sys.exit(main())
