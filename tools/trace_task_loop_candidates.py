#!/usr/bin/env python3
"""List unresolved inventory sites in loops paced by installed task waits."""
import collections
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs", "animation")
patched = {
    int(s, 16) for s in re.findall(
        r"^    \{0x([0-9A-F]+), [-0-9]+, \d+, 0xE[89], 1\}",
        open(os.path.join(ROOT, "src", "task_waits.h"), encoding="utf-8").read(), re.M
    )
}
left = {
    int(row["site"], 16): row for row in csv.DictReader(
        open(os.path.join(DOCS, "coverage.csv"), encoding="utf-8")
    ) if row["status"] in ("to-patch", "review")
}
found = collections.defaultdict(list)
for row in csv.DictReader(open(os.path.join(DOCS, "task_waits.csv"), encoding="utf-8")):
    wait = int(row["site"], 16)
    if wait not in patched or row["cls"] != "pass" or row["loop"] != "loop":
        continue
    for site in (int(s, 16) for s in re.findall(r"\b([0-9A-F]{6})\b", row["steps"])):
        if site in left and left[site]["function"] == row["function"]:
            found[site].append(wait)
for site, waits in sorted(found.items()):
    row = left[site]
    print(f"{site:06X} {row['group']:13} {row['function']:6} {row['shape']:12} waits: "
          + " ".join(f"{w:06X}" for w in waits))
print(f"{len(found)} unresolved sites in installed stock-paced task loops")
if len(sys.argv) == 3 and sys.argv[1] == "--spec":
    groups = collections.defaultdict(list)
    for site, waits in sorted(found.items()):
        groups[left[site]["function"]].append((site, waits))
    with open(sys.argv[2], "w", encoding="utf-8") as spec:
        spec.write("# Each site is a read-modify-write in the named function's loop body.\n")
        spec.write("# The cited wait(1) is installed as a loop call in task_waits.h.\n")
        for function, sites in sorted(groups.items(), key=lambda pair: int(pair[0], 16)):
            waits = sorted({wait for _, pair in sites for wait in pair})
            spec.write("follows | %s loop body resumes after task_waits.h stock-paced wait(1) at %s; "
                       "the first pass runs once before that wait | %s\n" %
                       (function, ",".join(f"{w:X}" for w in waits),
                        " ".join(f"{site:X}" for site, _ in sites)))
