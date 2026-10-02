#!/usr/bin/env python3
"""How far along the patch is: every candidate in docs/animation/sites.csv
against what the tables patch today and what the classification decided.

The plan's goal: every candidate patched or excluded with a
reason. A candidate is a self-updating store the census found; this sorts
each one into

  library     linked middleware (CRI, CRT), excluded wholesale
  covered     a patched range of any family lies in the same function within
              8 bytes of the update's load .. store (the rule
              animation_inventory.py used for `covered_by` in 2026-09)
  excluded    classification.csv decided `exclude` (its static reason says why)
  port        the port already scales it by the time scale (audit only)
  read        read by hand (docs/animation/reads.csv, a verdict per site): a row
              further away fixes it, or it needs nothing (it follows something
              already at stock pace, runs once per event, ...), and why
  near        none of those, but a patched range in the same function within
              64 bytes: a scaled step computed a little before the load, as
              many world rows are. Counted apart: probably covered, unproven
  to-patch    classified to patch (`patch`, `patch-static`), nothing near it
  review      classified `review`: not yet read
  unclassified  not in classification.csv

Patched ranges come from check_patch_sites.all_sites (every family's
tables, parsed exactly); function starts from the decompile's headers.

    .venv/Scripts/python tools/coverage_report.py [--decomp PATH] [--out docs/animation]

Writes OUT/coverage.csv (a row per candidate: status, the covering family and
its distance) and OUT/coverage.md (the counts); prints the counts.
"""
import argparse
import bisect
import collections
import contextlib
import csv
import datetime
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_patch_sites as cps  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
DOCS = os.path.join(ROOT, "docs", "animation")
DECOMP = os.path.expanduser(r"~\tools\main_decompiled.c")
FUNC_HDR = re.compile(r"^// ==== main\+([0-9A-F]{6})  ", re.M)
TIGHT, NEAR = 8, 64
PLANNED = ("patch", "patch-static")

# subsystem -> the group a player would name
GROUPS = [
    ("enemies", ("em", "cEnemy", "cEm", "cMonster")),
    ("player and weapons", ("pl", "plwp", "plwpsub", "wp")),
    ("animals", ("an", "cAnimal", "cDog", "cFish")),
    ("people", ("hm", "cHuman")),
    ("objects", ("ut", "et", "obj", "gt", "vt", "cItem", "cKiType", "cKihon", "cBall", "cCarry",
                 "cGear", "cDig", "cBamboo", "cObj", "cTubomi", "cKakejiku", "cSave", "cScr", "sg",
                 "db")),
    ("effects", ("es",)),
]


def group_of(subsystem):
    if subsystem == "library":
        return "library"
    if subsystem in ("effect",):
        return "effects"
    if subsystem.startswith("ui"):
        return "ui"
    if subsystem == "model-material":
        return "materials"
    if subsystem.startswith("object:"):
        fams = subsystem[7:].split("/")
        for name, prefixes in GROUPS:
            if any(f in prefixes for f in fams):
                return name
        return "objects"
    return "unattributed"


def function_starts(path):
    if not os.path.exists(path):
        sys.exit("no decompile at %s (tools/ghidra_export.py writes it)" % path)
    src = open(path, encoding="utf-8", errors="replace").read()
    return sorted(int(m.group(1), 16) for m in FUNC_HDR.finditer(src))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--decomp", default=DECOMP)
    ap.add_argument("--out", default=DOCS)
    args = ap.parse_args()

    starts = function_starts(args.decomp)

    def owner(rva):
        i = bisect.bisect_right(starts, rva) - 1
        return starts[i] if i >= 0 else None

    img, _lo, _hi = cps.load_image()
    with contextlib.redirect_stdout(io.StringIO()):
        sites, _detours, loads = cps.all_sites(img)
    ranges = sorted([(rva, rva + max(ln, 1), fam) for rva, (fam, ln, _raw) in sites.items()] +
                    # a hoisted decay patches the multiply; the load of k it is proven
                    # from sits by the update itself
                    [(rva, rva + len(raw), "hoisted_decay.h") for rva, raw in loads])
    by_fn = collections.defaultdict(list)
    for a, b, fam in ranges:
        by_fn[owner(a)].append((a, b, fam))

    cands = list(csv.DictReader(open(os.path.join(DOCS, "sites.csv"), encoding="utf-8")))
    cls = {r["site"]: r for r in csv.DictReader(open(os.path.join(DOCS, "classification.csv"),
                                                      encoding="utf-8"))}
    reads_path = os.path.join(DOCS, "reads.csv")
    reads = {r["site"]: r for r in csv.DictReader(open(reads_path, encoding="utf-8"))}         if os.path.exists(reads_path) else {}
    unknown = sorted(set(reads) - {c["site"] for c in cands})
    if unknown:
        sys.exit("reads.csv names %d sites that are not candidates: %s"
                 % (len(unknown), ", ".join(unknown[:8])))
    rows = []
    for c in cands:
        site = int(c["site"], 16)
        load = int(c["load"], 16) if c["load"] else site
        lo, hi = min(site, load), max(site, load)
        fn = int(c["function"], 16) if c["function"] else owner(site)
        best = None
        for a, b, fam in by_fn.get(fn, ()):
            # distance from the update's instructions to the patched range
            d = 0 if (a <= hi and b > lo) else (lo - b if b <= lo else a - hi)
            if best is None or d < best[0]:
                best = (d, fam)
        k = cls.get(c["site"])
        decision = k["decision"] if k else ""
        if c["subsystem"] == "library":
            status = "library"
        elif best and best[0] <= TIGHT:
            status = "covered"
        elif decision == "exclude":
            status = "excluded"
        elif c["shape"] == "port:timescale":
            status = "port"
        elif c["site"] in reads and reads[c["site"]]["verdict"] != "left":
            status = "read"
        elif best and best[0] <= NEAR:
            status = "near"
        elif decision in PLANNED:
            status = "to-patch"
        elif decision == "review":
            status = "review"
        else:
            status = "unclassified"
        rows.append({"site": c["site"], "function": "%X" % fn if fn is not None else "",
                     "subsystem": c["subsystem"], "group": group_of(c["subsystem"]),
                     "shape": c["shape"], "status": status,
                     "family": best[1] if best else "", "distance": best[0] if best else "",
                     "decision": decision,
                     "reason": ("read: %s, %s" % (reads[c["site"]]["verdict"],
                                                  reads[c["site"]]["note"])
                                if status == "read" else
                                k.get("static_reason", "") if k else "")})

    # A historical patch may be replaced by a documented fix outside the
    # eight-byte coverage radius, such as a gate for the complete physics step.
    old = [r for r, c in zip(rows, cands) if c["covered_by"] and r["status"] != "library"]
    lost = [r for r in old if r["status"] != "covered" and not
            (r["status"] == "read" and reads[r["site"]]["verdict"] == "fixed")]

    statuses = ["covered", "excluded", "port", "library", "read", "near", "to-patch", "review",
                "unclassified"]
    total = collections.Counter(r["status"] for r in rows)
    groups = collections.defaultdict(collections.Counter)
    for r in rows:
        groups[r["group"]][r["status"]] += 1
    fams = collections.Counter(r["family"] for r in rows if r["status"] == "covered")
    reasons = collections.Counter(r["reason"] for r in rows if r["status"] == "excluded")
    verdicts = collections.Counter(reads[r["site"]]["verdict"] for r in rows
                                   if r["status"] == "read")

    n = len(rows)
    settled = total["covered"] + total["excluded"] + total["port"] + total["library"] +         total["read"]
    left = total["to-patch"] + total["review"] + total["unclassified"]
    lines = []
    say = lines.append
    say("# Coverage: the candidates against the patch")
    say("")
    say("Written by `tools/coverage_report.py` on %s from `sites.csv` (%d candidates), "
        "`classification.csv` and the tables in `src/` (%d patched ranges)."
        % (datetime.date.today().isoformat(), n, len(ranges)))
    say("")
    say("**Settled: %d of %d (%.0f%%)**: covered %d, excluded %d (library %d, classified %d, "
        "port-scaled %d), read by hand %d. **Near a patch, unproven: %d.** **Left: %d** "
        "(classified to patch %d, to review %d, never classified %d)."
        % (settled, n, 100.0 * settled / n, total["covered"],
           total["library"] + total["excluded"] + total["port"], total["library"],
           total["excluded"], total["port"], total["read"], total["near"], left,
           total["to-patch"], total["review"], total["unclassified"]))
    say("")
    say("Without the library: settled %d of %d (%.0f%%), %.0f%% with the near ones."
        % (settled - total["library"], n - total["library"],
           100.0 * (settled - total["library"]) / (n - total["library"]),
           100.0 * (settled - total["library"] + total["near"]) / (n - total["library"])))
    say("")
    say("| group | " + " | ".join(statuses) + " | total |")
    say("|---|" + "---|" * (len(statuses) + 1))
    for g in sorted(groups, key=lambda g: -sum(groups[g].values())):
        cnt = groups[g]
        say("| %s | " % g + " | ".join(str(cnt[s]) if cnt[s] else "--" for s in statuses)
            + " | %d |" % sum(cnt.values()))
    say("| **all** | " + " | ".join(str(total[s]) for s in statuses) + " | %d |" % n)
    say("")
    say("Covered, by family: " + ", ".join("%s %d" % (f, c) for f, c in fams.most_common()) + ".")
    say("")
    say("Excluded, the classification's reasons (top 8): " +
        "; ".join("%s (%d)" % (r or "none given", c) for r, c in reasons.most_common(8)) + ".")
    say("")
    if verdicts:
        say("Read by hand (`reads.csv`), by verdict: " +
            ", ".join("%s %d" % v for v in verdicts.most_common()) + ".")
        say("")
    say("Check: of the %d candidates `animation_inventory.py` found covered in 2026-09, %d "
        "remain covered or have documented replacement fixes%s." % (len(old), len(old) - len(lost),
                                      "" if not lost else " (%d NOT: %s)" % (
                                          len(lost), ", ".join(r["site"] for r in lost[:8]))))
    say("")
    say("The classification is from 2026-09-18: `review` and `to-patch` shrink only as "
        "candidates are read or patched, and a candidate the patch covers some other way "
        "(a hook, a skipped call, a retargeted table the rule does not see) still counts "
        "as left.")

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "coverage.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    open(os.path.join(args.out, "coverage.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
