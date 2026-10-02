import re, os, sys, bisect, collections
REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
import xrefs, gen_integer_skips as gis
BASE = 0x180000000
pe, base, img, text = xrefs.load_bin("main.dll")
insns = [(a - BASE, m, o, s) for a, m, o, s in xrefs.cached_insns("main.dll")]
idx = {a: k for k, (a, m, o, s) in enumerate(insns)}
ranges = sorted(gis.patched_ranges())
starts = [r[0] for r in ranges]
def patched(a, size):
    k = bisect.bisect_right(starts, a + size - 1) - 1
    while k >= 0 and ranges[k][1] > a - 64:
        if ranges[k][0] < a + size and a < ranges[k][1]:
            return ranges[k][2]
        k -= 1
    return None
sites = []
for m in re.finditer(r"\{0x([0-9A-F]+), 0x[0-9A-F]+, \{[^}]*\}\},\s+// \*= ([0-9.]+)\s+(\S+) \+0x([0-9a-f]+)", open(os.path.join(REPO,"src","decay_factors.h")).read()):
    sites.append((int(m.group(1),16), m.group(2), m.group(3), int(m.group(4),16)))
out = collections.defaultdict(list)
for rva, k, owner, field in sites:
    i = idx.get(rva)
    if i is None: continue
    disp = "+ 0x%x]" % field
    for j in range(max(0, i-60), min(len(insns), i+30)):
        a, mn, op, sz = insns[j]
        if mn in ("addss", "subss") and disp in op and op.split(",")[0].startswith("xmm"):
            out[(rva, k, owner, field)].append((a, mn, op, patched(a, sz)))
        # load of the field followed within 2 insns by an addss into memory-position
        if mn == "movss" and op.startswith("xmm") and disp in op:
            reg = op.split(",")[0]
            for t in range(j+1, min(len(insns), j+4)):
                b, mn2, op2, sz2 = insns[t]
                if mn2 in ("addss","subss") and op2.startswith(reg + ",") and "[" in op2:
                    out[(rva, k, owner, field)].append((b, mn2, op2 + " (pre: xmm holds the field)", patched(b, sz2)))
for key in sorted(out):
    rva, k, owner, field = key
    rows = [r for r in out[key] if not r[3]]
    if rows:
        print("%X *= %s %s +0x%x:" % (rva, k, owner, field))
        for a, mn, op, p in rows:
            print("    %X %s %s" % (a, mn, op))

print("\n==== with the store's coverage status")
import csv
cov = {r["site"]: r for r in csv.DictReader(open(os.path.join(REPO,"docs","animation","coverage.csv"), encoding="utf-8"))}
reads = {r["site"]: r for r in csv.DictReader(open(os.path.join(REPO,"docs","animation","reads.csv"), encoding="utf-8"))}
seen=set()
for key in sorted(out):
    for a, mn, op, p in out[key]:
        if p or a in seen: continue
        seen.add(a)
        k = idx[a]
        # any patched instruction in the 4 before (a scaled multiplier)
        pre_p = [insns[t] for t in range(k-4, k) if patched(insns[t][0], insns[t][3])]
        st = None
        for t in range(k+1, min(len(insns), k+4)):
            b, mn2, op2, sz2 = insns[t]
            if mn2 == "movss" and op2.startswith("dword ptr"):
                st = "%X" % b; break
        c = cov.get(st, {})
        print("%X %-40s store %s %-8s %s %s" % (a, op[:40], st, c.get("status",""), ("prior-patched" if pre_p else ""), reads.get(st,{}).get("verdict","")))
