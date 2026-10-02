# fref.py DISP [DISP..] [--in LO HI]: every instruction touching [reg + DISP]
import pickle, sys, bisect, re
c = pickle.load(open("tools/.disasm_cache/read_candidates.pkl", "rb"))
ins = c["insns"]
args = sys.argv[1:]
lo, hi = 0, 1 << 40
if "--in" in args:
    i = args.index("--in"); lo, hi = int(args[i+1], 16), int(args[i+2], 16); del args[i:i+3]
pats = [re.compile(r"\[r\w+ \+ (?:r\w+\*\d \+ )?%s\]" % ("0x%x" % int(a, 16))) for a in args]
for a, m, o, s in ins:
    if lo <= a < hi and any(p.search(o) for p in pats):
        print("%X  %-8s %s" % (a, m, o))
