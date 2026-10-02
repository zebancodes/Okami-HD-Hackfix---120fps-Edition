#!/usr/bin/env python3
"""Read the coverage report's candidates by hand.

    .venv/Scripts/python tools/read_candidates.py --left enemies     # the left functions, most sites first
    .venv/Scripts/python tools/read_candidates.py 280CB0 [...]       # a function's disassembly
    .venv/Scripts/python tools/read_candidates.py 280CB0 --ctx 20 6  # only around its left sites
    .venv/Scripts/python tools/read_candidates.py 280CB0 -d          # with the decompile

Each line is annotated: a rip operand's value (its float, `DATA` in .data),
known call targets, `P family` where a patched range covers the
instruction, `<< status shape field` at a candidate's store and `(load of X)`
at its load. After the listing: the direct callers and the data words that
point at the function, with the vtable and slot they sit in (slot 8 is an
enemy's update, 25 its per-tick handler, 29 its damage handler).

The disassembly, call graph and data pointers are cached in
tools/.disasm_cache/read_candidates.pkl (`--rebuild`); the patched ranges and
coverage.csv are read fresh every run, so rerun coverage_report.py after a
build. Verdicts go to docs/animation/reads.csv (tools/add_reads.py) and rows
to gen_world_anims.MANIFEST (tools/manifest_rows.py).
"""
import bisect
import collections
import contextlib
import csv
import io
import os
import pickle
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.normpath(os.path.join(HERE, ".."))
DOCS = os.path.join(ROOT, "docs", "animation")
CACHE = os.path.join(HERE, ".disasm_cache", "read_candidates.pkl")
DECOMP = os.path.expanduser(r"~\tools\main_decompiled.c")
BASE = 0x180000000
RIP_RE = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
FUNC_HDR = re.compile(r"^// ==== main\+([0-9A-F]{6})  ", re.M)
NAMES = {
    0x13F2E0: "wrap angle", 0x20E210: "turn toward point", 0x20E290: "turn toward angle",
    0x2DA410: "forward step", 0x2DA3F0: "move by matrix", 0x2DA510: "FixTurnRate blend",
    0x2DA570: "clamped approach", 0x2DDF90: "clamped angle to point", 0x23A2E0: "turn to Ama",
    0x20EA30: "fall", 0x20ED50: "fall2", 0x4B9C80: "motion advance", 0x239AA0: "death fade",
    0x239010: "hit shake", 0x20CFD0: "submodel", 0x20CF90: "material",
    0x239420: "advance; animation ended?", 0x4BA080: "play motion", 0x1989F0: "effect",
    0x44EA00: "sound", 0x1DA050: "spawn",
}


def build():
    import xrefs
    pe, base, img, text = xrefs.load_bin("main.dll")
    insns = [(a - BASE, m, o, s) for a, m, o, s in xrefs.cached_insns("main.dll")]
    callers = collections.defaultdict(list)
    for a, m, o, s in insns:
        if m in ("call", "jmp") and o.startswith("0x"):
            try:
                callers[int(o, 16) - BASE].append(a)
            except ValueError:
                pass
    ptrs = collections.defaultdict(list)
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00") in (b".rdata", b".data"):
            lo, hi = sec.VirtualAddress, sec.VirtualAddress + sec.Misc_VirtualSize
            for off in range(lo, hi - 7, 8):
                v = struct.unpack_from("<Q", img, off)[0]
                if BASE + text[0] <= v < BASE + text[0] + text[1]:
                    ptrs[v - BASE].append(off)
    secs = [(s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize,
             s.Name.rstrip(b"\x00").decode()) for s in pe.sections]
    imps = {a - BASE: n.split("!")[-1] for a, n in xrefs.import_names(pe).items()}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump(dict(insns=insns, callers=dict(callers), ptrs=dict(ptrs), img=img, secs=secs,
                     imps=imps), open(CACHE, "wb"), protocol=4)


def patched_ranges():
    import check_patch_sites as cps
    cimg, _l, _h = cps.load_image()
    with contextlib.redirect_stdout(io.StringIO()):
        sites, _det, loads = cps.all_sites(cimg)
    return sorted([(r, r + max(ln, 1), fam) for r, (fam, ln, _raw) in sites.items()] +
                  [(r, r + len(raw), "hoisted_decay.h") for r, raw in loads])


def left_functions(group):
    cov = [r for r in csv.DictReader(open(os.path.join(DOCS, "coverage.csv"), encoding="utf-8"))
           if r["group"] == group and r["status"] in ("to-patch", "review", "unclassified")]
    byf = collections.defaultdict(list)
    for r in cov:
        byf[r["function"]].append(r)
    print("%d left in %d functions" % (len(cov), len(byf)))
    for f, rs in sorted(byf.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print("%s %2d  %s" % (f, len(rs), " ".join("%s:%s" % (r["site"], r["shape"][:5])
                                                   for r in rs)))


def main():
    argv = sys.argv[1:]
    if "--left" in argv:
        left_functions(argv[argv.index("--left") + 1])
        return
    ctx = None
    if "--ctx" in argv:
        i = argv.index("--ctx")
        ctx = (int(argv[i + 1]), int(argv[i + 2]))
        del argv[i:i + 3]
    if "--rebuild" in argv or not os.path.exists(CACHE):
        build()
    c = pickle.load(open(CACHE, "rb"))
    insns, img = c["insns"], c["img"]
    addrs = [i[0] for i in insns]
    ranges = patched_ranges()
    src = open(DECOMP, encoding="utf-8", errors="replace").read()
    fstarts = [(int(m.group(1), 16), m.start()) for m in FUNC_HDR.finditer(src)]
    starts = [f for f, _ in fstarts]
    cov = list(csv.DictReader(open(os.path.join(DOCS, "coverage.csv"), encoding="utf-8")))
    sinfo = {r["site"]: r for r in csv.DictReader(open(os.path.join(DOCS, "sites.csv"),
                                                       encoding="utf-8"))}
    by_site, by_load = {}, {}
    for r in cov:
        by_site[int(r["site"], 16)] = r
        ld = sinfo[r["site"]]["load"]
        if ld and ld != r["site"]:
            by_load[int(ld, 16)] = r
    text_lo = min(lo for lo, hi, n in c["secs"] if n == ".text")
    text_hi = max(hi for lo, hi, n in c["secs"] if n == ".text")

    def sec(rva):
        return next((n for lo, hi, n in c["secs"] if lo <= rva < hi), "?")

    def slot(r):
        k = r
        while k >= 8 and text_lo <= struct.unpack_from("<Q", img, k - 8)[0] - BASE < text_hi:
            k -= 8
        return "%X=vt%X[%d]" % (r, k, (r - k) // 8)

    for a in (x for x in argv if not x.startswith("-")):
        i = bisect.bisect_right(starts, int(a, 16)) - 1
        fn = starts[i]
        end = starts[i + 1] if i + 1 < len(starts) else fn + 0x1000
        if "-d" in argv:
            print(src[fstarts[i][1]:fstarts[i + 1][1] if i + 1 < len(fstarts) else len(src)])
        own = collections.Counter(sinfo[r["site"]]["owners"] for r in cov
                                  if r["function"] == "%X" % fn)
        lines = []
        j = bisect.bisect_left(addrs, fn)
        while j < len(insns) and insns[j][0] < end:
            ad, m, o, s = insns[j]
            j += 1
            if m == "int3":
                continue
            notes = []
            mo = RIP_RE.search(o)
            if mo:
                disp = int(mo.group(2), 16)
                t = ad + s + disp if mo.group(1) == "+" else ad + s - disp
                if t in c["imps"]:
                    notes.append(c["imps"][t])
                elif 0 <= t and t + 4 <= len(img):
                    notes.append("[%X%s]=%.7g" % (t, " DATA" if sec(t) == ".data" else "",
                                                  struct.unpack_from("<f", img, t)[0]))
            if m == "call" and o.startswith("0x"):
                try:
                    notes.append(NAMES.get(int(o, 16) - BASE, ""))
                except ValueError:
                    pass
            notes += ["P " + fam for lo, hi, fam in ranges if lo <= ad < hi or ad <= lo < ad + s]
            left = False
            if ad in by_site:
                r = by_site[ad]
                notes.append("<< %s %s %s" % (r["status"], r["shape"], sinfo[r["site"]]["field"]))
                left = r["status"] in ("to-patch", "review", "unclassified")
            if ad in by_load:
                notes.append("(load of %s)" % by_load[ad]["site"])
            line = "  %6X  %-8s %s" % (ad, m, o)
            notes = [n for n in notes if n]
            if notes:
                line = "%-62s ; %s" % (line, "  ".join(notes))
            lines.append((line, left))
        print("==== %X .. %X  owners %s" % (fn, end, dict(own)))
        if ctx is None:
            print("\n".join(ln for ln, _ in lines))
        else:
            want = set()
            for k, (_ln, left) in enumerate(lines):
                if left:
                    want.update(range(max(0, k - ctx[0]), min(len(lines), k + ctx[1] + 1)))
            prev = None
            for k in sorted(want):
                if prev is not None and k != prev + 1:
                    print("----")
                print(lines[k][0])
                prev = k
        cf = collections.Counter(starts[bisect.bisect_right(starts, x) - 1]
                                 for x in c["callers"].get(fn, []))
        print("  callers: %s" % ", ".join("%X(%d)" % kv for kv in cf.most_common(12)))
        refs = c["ptrs"].get(fn, [])
        print("  data refs: %s" % ", ".join(slot(x) for x in refs[:8]) +
              (" +%d" % (len(refs) - 8) if len(refs) > 8 else ""))


if __name__ == "__main__":
    main()
