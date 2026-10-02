import csv, sys, collections
D = "docs/animation/"
grp = sys.argv[1]
fn = sys.argv[2] if len(sys.argv) > 2 else None
cov = [r for r in csv.DictReader(open(D + "coverage.csv", encoding="utf-8"))
       if r["group"] == grp and r["status"] in ("to-patch", "review", "unclassified")]
si = {r["site"]: r for r in csv.DictReader(open(D + "sites.csv", encoding="utf-8"))}
cl = {r["site"]: r for r in csv.DictReader(open(D + "classification.csv", encoding="utf-8"))}
for r in cov:
    if fn and r["function"] != fn:
        continue
    s, c = si[r["site"]], cl.get(r["site"], {})
    print("%s %s %-7s %-9s %-14s st=%-4s own=%-10s cls=%-8s ctx=%-5s exec=%-8s chg=%-8s tk=%-6s ctk=%-6s | %s | %s" % (
        r["function"], r["site"], r["status"][:7], r["shape"], s["field"][:14], s["step"][:4], s["owners"][:10],
        c.get("class", ""), c.get("context", ""), c.get("exec", ""), c.get("changed", ""), c.get("ticks", ""),
        c.get("chg_ticks", ""), c.get("static_reason", "")[:40], c.get("delta", "")[:30]))
