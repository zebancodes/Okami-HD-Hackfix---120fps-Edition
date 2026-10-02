#!/usr/bin/env python3
"""Merge hand-read verdicts into docs/animation/reads.csv, which
tools/coverage_report.py counts as settled (`read`).

    .venv/Scripts/python tools/add_reads.py SPEC [SPEC...]

Spec lines: `verdict | why | SITE SITE ...` (# comments). Verdicts:
  fixed    a row fixes it (far enough from the site that the report's
           8-byte rule does not see it)
  once     it runs once per event (a hit, an action's start, an animation's
           end), not every tick
  follows  it follows something already at stock pace (a wrap of a scaled
           phase, the animation's root turn, an actor clock's crossing)
  stock    already right at any rate (an animation rate the motion advance
           scales, an offset after a copy)
  left     read and left on purpose (say why)
A later verdict for a site replaces the earlier one. Every site must be a
candidate in sites.csv.
"""
import csv
import os
import sys

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "animation")
P = os.path.join(DOCS, "reads.csv")
VERDICTS = ("fixed", "once", "follows", "stock", "left")


def main():
    rows = {r["site"]: r for r in csv.DictReader(open(P, encoding="utf-8"))} \
        if os.path.exists(P) else {}
    cands = {r["site"] for r in csv.DictReader(open(os.path.join(DOCS, "sites.csv"),
                                                    encoding="utf-8"))}
    n = 0
    for spec in sys.argv[1:]:
        for line in open(spec, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            verdict, note, sites = [x.strip() for x in line.split("|")]
            if verdict not in VERDICTS:
                sys.exit("unknown verdict %r in: %s" % (verdict, line))
            for s in sites.split():
                if s not in cands:
                    sys.exit("%s is not a candidate" % s)
                rows[s] = dict(site=s, verdict=verdict, note=note)
                n += 1
    with open(P, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["site", "verdict", "note"])
        w.writeheader()
        for s in sorted(rows, key=lambda x: int(x, 16)):
            w.writerow(rows[s])
    print("%d verdicts; %d in reads.csv" % (n, len(rows)))


if __name__ == "__main__":
    main()
