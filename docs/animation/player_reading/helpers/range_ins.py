"""Print cached main.dll instructions in an RVA range (hex arguments)."""
import pickle
import sys

cache = pickle.load(open("tools/.disasm_cache/read_candidates.pkl", "rb"))
lo, hi = (int(arg, 16) for arg in sys.argv[1:3])
for addr, mnemonic, operands, size in cache["insns"]:
    if lo <= addr < hi:
        print(f"{addr:06X}  {mnemonic:<9} {operands}")
