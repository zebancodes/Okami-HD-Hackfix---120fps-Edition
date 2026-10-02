"""near sites not yet given a verdict in near_reads*.spec nor set aside in pending.txt"""
import glob, os, re
D = os.path.dirname(os.path.abspath(__file__))
done = set()
for p in glob.glob(os.path.join(D, "near_reads*.spec")):
    for line in open(p, encoding="utf-8"):
        if line.startswith("#") or "|" not in line:
            continue
        done.update(line.rsplit("|", 1)[1].split())
for line in open(os.path.join(D, "pending.txt"), encoding="utf-8"):
    done.update(re.findall(r"\b[0-9A-F]{6}\b", line.split("(", 1)[1] if "(" in line else ""))
left = []
for line in open(os.path.join(D, "near_by_fn.txt")):
    p = line.split()
    sites = [s.split(":")[0] for s in p[2:]]
    rest = [s for s in sites if s not in done]
    if rest:
        left.append((p[0], p[1], rest))
print(sum(len(r) for _f, _g, r in left), "sites in", len(left), "functions")
import sys
n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
for f, g, r in left[:n]:
    print(f, g, " ".join(r))
