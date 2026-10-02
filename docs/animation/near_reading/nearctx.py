#!/usr/bin/env python3
"""Print read_candidates' annotated listing around each near site of the
functions given (lines from near_by_fn.txt), B lines before and A after."""
import contextlib
import io
import os
import re
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
import read_candidates as rc  # noqa: E402

SP = os.path.dirname(os.path.abspath(__file__))


def main():
    fns = [a.upper() for a in sys.argv[1:] if not a.startswith("-")]
    before = int(next((a[3:] for a in sys.argv if a.startswith("-b=")), 14))
    after = int(next((a[3:] for a in sys.argv if a.startswith("-a=")), 8))
    table = {}
    for line in open(os.path.join(SP, "near_by_fn.txt")):
        p = line.split()
        table[p[0]] = (p[1], [s.split(":")[0] for s in p[2:]])
    for fn in fns:
        group, sites = table[fn]
        buf = io.StringIO()
        old = sys.argv
        sys.argv = ["read_candidates.py", fn]
        with contextlib.redirect_stdout(buf):
            try:
                rc.main()
            except SystemExit:
                pass
        sys.argv = old
        lines = buf.getvalue().splitlines()
        start = next((k for k, l in enumerate(lines) if l.startswith("==== ")), 0)
        body = lines[start:]
        idx = {}
        for k, l in enumerate(body):
            m = re.match(r"\s+([0-9A-F]{6})\s", l)
            if m:
                idx[m.group(1)] = k
        keep = set()
        for s in sites:
            if s in idx:
                keep.update(range(max(1, idx[s] - before), min(len(body), idx[s] + after + 1)))
        print("######## %s (%s) near: %s" % (fn, group, " ".join(sites)))
        print(body[0])
        prev = None
        for k in sorted(keep):
            if prev is not None and k != prev + 1:
                print("  ...")
            print(body[k])
            prev = k
        tail = [l for l in body if l.startswith("  callers") or l.startswith("  data refs")]
        print("\n".join(tail))


if __name__ == "__main__":
    main()
