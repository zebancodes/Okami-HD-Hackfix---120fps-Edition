#!/usr/bin/env python3
"""Export Ghidra's decompilation of main.dll as one greppable C file.

    .venv/Scripts/python tools/ghidra_export.py [--binary main.dll] [--out PATH]

Why this exists
---------------
Every generator in this directory searches for one *encoding* of a bug shape,
and this project's recurring failure is finding one encoding and missing the
others. It has happened four times: the action countdown in its register, memory
and `lea` forms; the per-mode damping table addressed image-base-relative with
the table RVA hidden in a displacement; and the integer half of the mode-byte
family, where there is no constant to search for at all because the table is the
instruction (`add eax, eax`).

A decompiler collapses all of that. `add eax,eax`, `shl eax,1`,
`lea eax,[rdx+rdx]` and `imul eax,2` become one expression, and a grep for the
mode byte returns every reader with its meaning attached. The capstone
generators stay authoritative -- they emit the exact bytes the patch verifies at
runtime -- but this file is how you find the sites worth writing a generator for.

Each function is preceded by `// ==== main+XXXXXX name ====`, so a hit maps
straight onto the patch tables, the log, and `ok2.Mod.show()`.

Setup (already done on this machine, recorded here so it can be repeated):
  * Temurin JDK 21            winget install EclipseAdoptium.Temurin.21.JDK
  * Ghidra 12.1.3             extracted to GHIDRA_INSTALL_DIR below
  * pyghidra + jpype1         from Ghidra/Features/PyGhidra/pypkg/dist
Note that analyzeHeadless.bat cannot cope with the parentheses in
"Program Files (x86)", which is why the binaries are analysed from a copy.
"""
import argparse
import os
import sys

GHIDRA = os.environ.get("GHIDRA_INSTALL_DIR",
                        os.path.expanduser(r"~\tools\ghidra_12.1.3_PUBLIC"))
PROJECT_DIR = os.environ.get("OKAMI_GHIDRA_PROJECT",
                             os.path.expanduser(r"~\tools\ghidra_proj"))
PROJECT_NAME = "okami"
DEFAULT_OUT = os.path.expanduser(r"~\tools\main_decompiled.c")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", default="main.dll",
                    help="program name inside the Ghidra project")
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=int, default=30,
                    help="per-function decompiler timeout in seconds")
    # main.dll has 27k functions and takes the best part of an hour, which is
    # longer than any single automated run here survives, so the export is
    # resumable: run it in chunks and concatenate.
    ap.add_argument("--start", type=int, default=0, help="first function index")
    ap.add_argument("--limit", type=int, default=0, help="0 = to the end")
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()
    out = args.out or (DEFAULT_OUT if args.binary == "main.dll"
                       else os.path.join(os.path.dirname(DEFAULT_OUT),
                                         args.binary + "_decompiled.c"))

    os.environ.setdefault("GHIDRA_INSTALL_DIR", GHIDRA)
    import pyghidra
    pyghidra.start(verbose=False)

    from ghidra.app.decompiler import DecompInterface
    from ghidra.base.project import GhidraProject
    from ghidra.util.task import ConsoleTaskMonitor

    project = GhidraProject.openProject(PROJECT_DIR, PROJECT_NAME, True)
    try:
        program = project.openProgram("/", args.binary, True)
    except Exception as exc:
        sys.exit("could not open %s in %s/%s: %s\n"
                 "run the headless import first (see the module docstring)"
                 % (args.binary, PROJECT_DIR, PROJECT_NAME, exc))

    try:
        base = program.getImageBase().getOffset()
        monitor = ConsoleTaskMonitor()
        iface = DecompInterface()
        iface.openProgram(program)

        funcs = list(program.getFunctionManager().getFunctions(True))
        total = len(funcs)
        end = total if args.limit <= 0 else min(total, args.start + args.limit)
        chunk = funcs[args.start:end]
        failed = 0
        mode = "a" if args.append else "w"
        with open(out, mode, encoding="utf-8", errors="replace", newline="\n") as fh:
            if not args.append:
                fh.write("// Ghidra decompilation of %s, by tools/ghidra_export.py\n"
                         % args.binary)
                fh.write("// Headers carry RVAs: main+XXXXXX, exactly as the patch "
                         "tables and the log use them.\n")
                fh.write("// %d functions\n\n" % total)
            for n, f in enumerate(chunk, args.start + 1):
                rva = f.getEntryPoint().getOffset() - base
                fh.write("// ==== main+%06X  %s ====\n" % (rva, f.getName()))
                res = iface.decompileFunction(f, args.timeout, monitor)
                if res is not None and res.decompileCompleted():
                    fh.write(res.getDecompiledFunction().getC())
                else:
                    failed += 1
                    fh.write("// DECOMPILATION FAILED: %s\n"
                             % (res.getErrorMessage() if res is not None else "no result"))
                fh.write("\n")
                if n % 1000 == 0:
                    print("  %d/%d" % (n, total), flush=True)
        iface.dispose()
        print("wrote %s -- functions [%d,%d) of %d, %d failed; next --start %d"
              % (out, args.start, end, total, failed, end))
    finally:
        project.close()


if __name__ == "__main__":
    main()
