# jt.py TABLE_RVA COUNT: a switch table of rva dwords (base = image base)
import pickle, sys, struct
c = pickle.load(open("tools/.disasm_cache/read_candidates.pkl", "rb"))
img = c["img"]; t = int(sys.argv[1], 16); n = int(sys.argv[2])
print(" ".join("%d:%X" % (i, struct.unpack_from("<I", img, t + 4 * i)[0]) for i in range(n)))
