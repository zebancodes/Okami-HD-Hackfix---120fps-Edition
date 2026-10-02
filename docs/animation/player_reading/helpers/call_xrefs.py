"""Print direct call and jump references to one cached main.dll RVA."""
import pickle
import sys

target = int(sys.argv[1], 16) + 0x180000000
cache = pickle.load(open("tools/.disasm_cache/read_candidates.pkl", "rb"))
for address, mnemonic, operands, _size in cache["insns"]:
    if mnemonic in ("call", "jmp") and operands == f"0x{target:x}":
        print(f"{address:06X} {mnemonic}")
