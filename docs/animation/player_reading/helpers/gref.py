# gref.py ADDR [LEN]: every instruction whose rip operand points into [ADDR, ADDR+LEN)
import pickle, sys, re
c = pickle.load(open("tools/.disasm_cache/read_candidates.pkl", "rb"))
R = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
lo = int(sys.argv[1], 16); n = int(sys.argv[2], 16) if len(sys.argv) > 2 else 4
for a, m, o, s in c["insns"]:
    mo = R.search(o)
    if mo:
        d = int(mo.group(2), 16)
        t = a + s + d if mo.group(1) == "+" else a + s - d
        if lo <= t < lo + n:
            print("%X  %-8s %s   ; ->%X" % (a, m, o, t))
