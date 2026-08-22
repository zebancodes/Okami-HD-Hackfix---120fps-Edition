#!/usr/bin/env python
"""Cache full .text disassembly (error-tolerant) and find rip-relative refs into an RVA window."""
import os
import pickle
import re
import sys

import capstone
import pefile

GAME = r"D:\SteamLibrary\steamapps\common\Okami"
CACHE = os.path.join(os.path.dirname(__file__), ".disasm_cache")
RIP_RE = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")


def load_bin(name):
    path = os.path.join(GAME, name)
    pe = pefile.PE(path, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()
    img = bytearray(pe.OPTIONAL_HEADER.SizeOfImage)
    for s in pe.sections:
        if s.PointerToRawData and s.SizeOfRawData:
            off = s.PointerToRawData + s.SizeOfRawData
            end = s.VirtualAddress + min(s.SizeOfRawData, off - s.PointerToRawData)
            img[s.VirtualAddress : end] = data[s.PointerToRawData : off]
    text = None
    for s in pe.sections:
        if s.Name.rstrip(b"\x00") == b".text":
            text = (s.VirtualAddress, s.Misc_VirtualSize)
    return pe, base, bytes(img), text


def cached_insns(name):
    cache_file = os.path.join(CACHE, name + ".pkl")
    os.makedirs(CACHE, exist_ok=True)
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            return pickle.load(f)
    pe, base, img, text = load_bin(name)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    rva0, size = text
    insns = []
    pos = 0
    chunk = 0x4000
    overlap = 16
    seen = set()
    while pos < size:
        piece = img[rva0 + pos : rva0 + min(pos + chunk, size)]
        base_addr = base + rva0 + pos
        consumed = 0
        for insn in md.disasm(piece, base_addr):
            if insn.address in seen:
                continue
            seen.add(insn.address)
            insns.append((insn.address, insn.mnemonic, insn.op_str, insn.size))
            consumed = insn.address - base_addr + insn.size
        if consumed <= 0:
            pos += 1  # invalid byte, skip
        else:
            pos += max(consumed, 1)
    insns.sort()
    with open(cache_file, "wb") as f:
        pickle.dump(insns, f, protocol=4)
    return insns


def import_names(pe):
    d = {}
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode()
            for imp in entry.imports:
                nm = imp.name.decode() if imp.name else f"ord{imp.ordinal}"
                d[imp.address] = f"{dll}!{nm}"
    return d


def rip_target(insn):
    a, m, o, s = insn
    mo = RIP_RE.search(o)
    if not mo:
        return None
    disp = int(mo.group(2), 16)
    return a + s + disp if mo.group(1) == "+" else a + s - disp


def main():
    name = sys.argv[1]
    lo = int(sys.argv[2], 0)
    hi = int(sys.argv[3], 0)
    pe, base, img, text = load_bin(name)
    insns = cached_insns(name)
    print(f"rip-relative refs in {name} into [{hex(lo)}, {hex(hi)})")
    for insn in insns:
        t = rip_target(insn)
        if t is not None and lo <= t - base < hi:
            print(f"{hex(insn[0])} {insn[1]} {insn[2]}   ; -> {hex(t)}")
    print("total insns:", len(insns))


if __name__ == "__main__":
    main()
