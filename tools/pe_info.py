#!/usr/bin/env python
"""Dump PE headers/imports/exports/sections for the Okami HD binaries."""
import json
import os
import sys

import pefile

from gamedir import GAME  # auto-detected Steam install (or OKAMI_DIR)


def analyze(path):
    pe = pefile.PE(path, fast_load=False)
    d = {}
    d["machine"] = hex(pe.FILE_HEADER.Machine)
    d["characteristics"] = hex(pe.FILE_HEADER.Characteristics)
    d["entry"] = hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
    d["imagebase"] = hex(pe.OPTIONAL_HEADER.ImageBase)
    d["subsystem"] = pe.OPTIONAL_HEADER.Subsystem
    d["dll_characteristics"] = hex(pe.OPTIONAL_HEADER.DllCharacteristics)
    sections = []
    for s in pe.sections:
        sections.append(
            {
                "name": s.Name.rstrip(b"\x00").decode("latin1"),
                "va": hex(s.VirtualAddress),
                "vsize": hex(s.Misc_VirtualSize),
                "rawsize": hex(s.SizeOfRawData),
                "chars": hex(s.Characteristics),
            }
        )
    d["sections"] = sections
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        d["imports"] = []
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode()
            funcs = []
            for imp in entry.imports:
                funcs.append(imp.name.decode() if imp.name else f"ord{imp.ordinal}")
            d["imports"].append({"dll": dll, "count": len(funcs), "funcs": funcs})
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        d["exports"] = [
            (e.name.decode() if e.name else f"ord{e.ordinal}", hex(e.address))
            for e in pe.DIRECTORY_ENTRY_EXPORT.symbols
        ]
    d["tls_callbacks"] = (
        hex(pe.DIRECTORY_ENTRY_TLS.struct.AddressOfCallBacks)
        if hasattr(pe, "DIRECTORY_ENTRY_TLS")
        else None
    )
    return d


def main():
    for name in sys.argv[1:] or ["okami.exe", "main.dll", "flower_kernel.dll"]:
        path = os.path.join(GAME, name)
        try:
            d = analyze(path)
            print(f"===== {name} =====")
            print(json.dumps(d, indent=1))
        except Exception as e:  # noqa: BLE001
            print(name, "ERROR", repr(e))


if __name__ == "__main__":
    main()
