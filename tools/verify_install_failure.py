#!/usr/bin/env python3
"""Prove offline that the grouped installs fail safely.

The turn rate (installTurnRate) and the frame clocks (installFrameClocks) each
patch a group of instructions that only works whole, and point it into memory
of their own: the turn stub and its private pairs in the movement fix's cave,
which later installers carve up too, and the counter page. writeGroup writes a
group in order and, when a write fails, puts back the ones already made; if a
write cannot be put back either, it stops, so a prefix of the group stays.

1. Loads the built DLL into this process and calls its OkamiInstallFailSelfTest
   export, which maps main.dll without running any of it and makes each install
   fail at every one of its writes in turn (writeProtected's fault injection),
   and then at three with the undo failing too.

2. Every rollback, write k rejected: the install says so; it made k writes, the
   failed one and k undos (2k + 1 calls, so the undo really ran); every site
   holds its original bytes; the turn cave's free space is where it started
   (nothing points into it now, so the next installer may have it); nothing
   is marked installed or stranded.

3. Every stranded install, the undo failing after write k: the first k writes
   stay, each with the bytes a full install writes, and every later site holds
   the original. The turn install:
     * reserved its stub and pairs: the free space it hands back starts past
       both, and everything from there on is what the installers after it
       wrote (the self-test fills it all);
     * never converts: the count is 0 after the watcher has run at 120 fps;
     * reads as stock, under Unicorn with main.dll where the DLL mapped it and
       the cave as the DLL left it: the approach function called through the
       stuck entry, every stuck table read in both mode-byte states, and every
       stuck bypass must give the original's result bit for bit.
   The frame clocks: the hook stays, and every counter equals the frame
   counter on every tick, at 30/60/120 fps, in both stock contexts, fix on and
   muted -- so every stuck read reads what the original does.

    .venv/Scripts/python tools/verify_install_failure.py [--dll .build/bin/dinput8.dll]
Exits non-zero on any mismatch.
"""
import argparse
import csv
import ctypes
import hashlib
import os
import shutil
import struct
import sys
import tempfile

try:
    import capstone
    import pefile
    from unicorn import UcError
except ImportError:
    sys.exit("needs pefile, capstone and unicorn: pip install pefile capstone unicorn")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import verify_frame_clocks as vfc  # noqa: E402
import verify_turn_callers as vtc  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
CAVE_SIZE = 8192
START = 80                  # the turn stub's offset in the cave (after the header)


def rel32(nxt, target):
    return struct.pack("<i", target - nxt)


def split_sites(blob, lens):
    """a site dump, one record per case: [[bytes of each site], ...]"""
    per = sum(lens)
    assert len(blob) % per == 0, "site dump of %d bytes, %d per case" % (len(blob), per)
    out = []
    for c in range(len(blob) // per):
        pos, rec = c * per, []
        for n in lens:
            rec.append(blob[pos:pos + n])
            pos += n
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=os.path.join(ROOT, ".build", "bin", "dinput8.dll"))
    ap.add_argument("--out", default=None, help="work directory (default: a temp dir)")
    args = ap.parse_args()

    entries, reads, bypass, tsha = vtc.parse_header()
    fch = vfc.parse_header()
    path = os.path.join(GAME, "main.dll")
    sha = hashlib.sha1(open(path, "rb").read()).hexdigest()
    if sha != tsha or sha != fch["sha"]:
        sys.exit("main.dll sha1 %s is not the build the headers were generated from" % sha)
    fails = 0

    # 1. the DLL's own installs, failing
    work = args.out or tempfile.mkdtemp(prefix="okami_install_fail_")
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, "dinput8.dll")
    shutil.copy2(args.dll, dll)
    lib = ctypes.WinDLL(dll)
    fn = lib.OkamiInstallFailSelfTest
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    fn.restype = ctypes.c_int
    rc = fn(path.encode("mbcs"), work.encode("mbcs"))
    report = open(os.path.join(work, "report.txt")).read()
    print("DLL self-test (rc %d): %s" % (rc, report.strip().splitlines()[-1]))
    if rc != 0:
        print(report)
        return 1
    v = {p[0]: int(p[1], 16) for p in (ln.split() for ln in report.splitlines())
         if len(p) == 2 and p[0] in ("main", "cave", "count", "one", "zero", "slots", "fcstub")}
    base, cave = v["main"], v["cave"]

    # ---------------------------------------------------------------- turn
    turn_orig = [vtc.TURN_ORIG] + [r["orig"] for r in reads] + [b["orig"] for b in bypass]
    turn_lens = [len(x) for x in turn_orig]
    nw = len(turn_orig)
    rows = list(csv.DictReader(open(os.path.join(work, "turn.csv"))))
    sites = split_sites(open(os.path.join(work, "turn_sites.bin"), "rb").read(), turn_lens)
    if len(rows) != len(sites) or sum(r["case"] == "rollback" for r in rows) != nw:
        print("  FAIL turn: %d rows, %d site records, want %d rollbacks" % (len(rows), len(sites),
                                                                          nw))
        return 1

    def turn_installed(plain, pairs):
        """the bytes a full install writes at each site, given where its stub went"""
        stub = cave + START
        out = [b"\xE9" + rel32(base + vtc.TURN + 5, stub) + b"\x90" * (len(vtc.TURN_ORIG) - 5)]
        for r in reads:
            pair = pairs + 8 * r["pair"]
            d = pair - (base + r["rva"] + r["len"]) if r["rip"] else pair - base
            b = bytearray(r["orig"])
            b[r["disp_off"]:r["disp_off"] + 4] = struct.pack("<i", d)
            out.append(bytes(b))
        for b in bypass:
            out.append(b["orig"][:1] + rel32(base + b["rva"] + 5, plain))
        return out

    bad = []
    for row, rec in zip(rows, sites):
        if row["case"] != "rollback":
            continue
        k = int(row["k"])
        why = []
        if row["ok"] != "0":
            why.append("reported success")
        if int(row["writes"]) != 2 * k + 1:
            why.append("%s writes, want %d (%d, the failure, %d undone)"
                       % (row["writes"], 2 * k + 1, k, k))
        if int(row["cur"]) != START:
            why.append("free space at +%s, want +%d" % (row["cur"], START))
        if row["installed"] != "0" or row["stranded"] != "0":
            why.append("installed=%s stranded=%s" % (row["installed"], row["stranded"]))
        changed = [i for i, (got, want) in enumerate(zip(rec, turn_orig)) if got != want]
        if changed:
            why.append("%d site(s) not original, first #%d" % (len(changed), changed[0]))
        if why:
            bad.append("write %d rejected: %s" % (k, "; ".join(why)))
    print("turn rate, every write rejected in turn (%d): the install fails, undoes every write it"
          " made and leaves the cave free: %d wrong" % (nw, len(bad)))
    for b in bad[:8]:
        print("  FAIL " + b)
    fails += len(bad)

    pe = pefile.PE(path, fast_load=True)
    pe.relocate_image(base)
    img0 = bytes(pe.get_memory_mapped_image())
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    sbad = []
    for row, rec in zip(rows, sites):
        if row["case"] != "stranded":
            continue
        k = int(row["k"])
        plain, pairs = cave + int(row["plain"]), cave + int(row["pairs"])
        want = turn_installed(plain, pairs)
        why = []
        if row["ok"] != "0":
            why.append("reported success")
        if int(row["writes"]) != k + 2:
            why.append("%s writes, want %d (%d, the failure, one failed undo)"
                       % (row["writes"], k + 2, k))
        if row["installed"] != "0" or row["stranded"] != "1":
            why.append("installed=%s stranded=%s" % (row["installed"], row["stranded"]))
        if row["count"] != "0":
            why.append("the square-root count is %s at 120 fps" % row["count"])
        if int(row["plain"]) < 0 or int(row["pairs"]) < 0:
            why.append("no stub recorded")
            sbad.append("stranded at %d: %s" % (k, "; ".join(why)))
            continue
        for i, got in enumerate(rec):
            exp = want[i] if i < k else turn_orig[i]
            if got != exp:
                why.append("site #%d is %s, want %s" % (i, got.hex(), "the installed bytes"
                                                        if i < k else "the original"))
                break
        cave_bytes = open(os.path.join(work, "turn_cave_%d.bin" % k), "rb").read()
        pairs_end = pairs + 8 * len(entries)
        cur = cave + int(row["cur"])
        if cur < pairs_end:
            why.append("free space at +%X, inside the stub or pairs (they end at +%X)"
                       % (cur - cave, pairs_end - cave))
        tail = cave_bytes[cur - cave:]
        if len(cave_bytes) != CAVE_SIZE or tail != b"\xCC" * len(tail):
            why.append("the later installers' fill is not all there past +%X" % (cur - cave))
        plain_code = cave_bytes[plain - cave:plain - cave + len(vtc.TURN_ORIG) + 5]
        if plain_code != vtc.TURN_ORIG + b"\xE9" + rel32(plain + len(vtc.TURN_ORIG) + 5,
                                                          base + vtc.TURN + len(vtc.TURN_ORIG)):
            why.append("the relocated prologue is not intact")

        # the stuck bytes and the cave as the DLL left them, against the original
        img = bytearray(img0)
        a = [base + vtc.TURN] + [base + r["rva"] for r in reads] + [base + b["rva"] for b in bypass]
        for i, got in enumerate(rec):
            img[a[i] - base:a[i] - base + len(got)] = got
        m = vtc.Machine(img, base, cave, cave_bytes)
        for i, e in enumerate(entries):
            m.w32(base + e, int(row["table%d" % i], 16))
            m.w32(base + e + 4, int(row["stock%d" % i], 16))

        def approach(kk, entry_bytes):
            m.code(base + vtc.TURN, entry_bytes)
            m.run(base + vtc.TURN, None, xmm={0: vtc.TARGET, 1: vtc.FACING, 2: kk},
                  push_ret=True)
            return vtc.fbits(m.xmmf(0))
        checked = 0
        for kk in (0.05, 0.25, 0.6, 0.95, 1.0, 1.5, -0.2, 0.0):
            kk = vtc.f32(kk)
            got, orig = approach(kk, rec[0]), approach(kk, vtc.TURN_ORIG)
            checked += 1
            if got != orig:
                why.append("through the stuck entry, k %.2f gives %08X, the original %08X"
                           % (kk, got, orig))
                break
        m.code(base + vtc.TURN, rec[0])

        def read_value(r, code):
            m.code(base + r["rva"], code)
            at = base + r["rva"]
            ins = list(md.disasm(bytes(m.mu.mem_read(at, 32)), at, count=2))
            load = ins[1] if r["rip"] else ins[0]
            mem = [o for o in load.operands if o.type == capstone.x86_const.X86_OP_MEM][0]
            mode = bytes(m.mu.mem_read(base + vtc.MODE, 1))[0]
            regs = {load.reg_name(mem.mem.index): mode - 1}
            if not r["rip"]:
                regs[load.reg_name(mem.mem.base)] = base
            m.run(at, load.address + load.size, regs=regs)
            return vtc.fbits(m.xmmf(int(load.reg_name(load.operands[0].reg)[3:])))
        for mode in (1, 2):
            m.mu.mem_write(base + vtc.MODE, bytes([mode]))
            for j, r in enumerate(reads):
                if 1 + j >= k:
                    break
                got, orig = read_value(r, rec[1 + j]), read_value(r, r["orig"])
                m.code(base + r["rva"], rec[1 + j])
                checked += 1
                if got != orig:
                    why.append("stuck table read %X (mode %d) reads %08X, the original %08X"
                               % (r["rva"], mode, got, orig))
                    break
        for j, b in enumerate(bypass):
            i = 1 + len(reads) + j
            if i >= k:
                break
            at = base + b["rva"]
            res = []
            for code in (rec[i], b["orig"]):
                m.code(at, code)
                if b["orig"][0] == 0xE8:
                    m.run(at, at + 5, xmm={0: vtc.TARGET, 1: vtc.FACING, 2: vtc.f32(0.5)})
                else:
                    m.run(at, None, xmm={0: vtc.TARGET, 1: vtc.FACING, 2: vtc.f32(0.5)},
                          push_ret=True)
                res.append(vtc.fbits(m.xmmf(0)))
            m.code(at, rec[i])
            checked += 1
            if res[0] != res[1]:
                why.append("stuck bypass %X gives %08X, the original %08X" % (b["rva"], *res))
        print("  stranded after write %d (%d stay: entry%s%s): stub and pairs kept below +%X,"
              " count 0 at 120 fps, %d emulated checks against the original%s"
              % (k, k, ", %d table reads" % min(k - 1, len(reads)) if k > 1 else "",
                 ", %d bypasses" % (k - 1 - len(reads)) if k > 1 + len(reads) else "",
                 cur - cave, checked, ": " + "; ".join(why) if why else ""))
        if why:
            sbad.append("stranded at %d: %s" % (k, "; ".join(why)))
    print("turn rate, 3 stranded: %d wrong" % len(sbad))
    for b in sbad:
        print("  FAIL " + b)
    fails += len(sbad)

    # ---------------------------------------------------------------- frame clocks
    tl = len(fch["tick_orig"])
    clock_orig = [fch["tick_orig"]] + [r["orig"] for r in fch["reads"]]
    clock_lens = [len(x) for x in clock_orig]
    ncw = len(clock_orig)
    stub, slots = v["fcstub"], v["slots"]
    clock_want = [b"\xE9" + rel32(base + fch["tick"] + 5, stub) + b"\x90" * (tl - 5)]
    for r in fch["reads"]:
        b = bytearray(r["orig"])
        b[r["disp_off"]:r["disp_off"] + 4] = rel32(base + r["rva"] + r["len"],
                                                   slots + 4 * r["slot"])
        clock_want.append(bytes(b))
    crow = list(csv.DictReader(open(os.path.join(work, "clocks.csv"))))
    csites = split_sites(open(os.path.join(work, "clocks_sites.bin"), "rb").read(), clock_lens)
    ticks = list(csv.DictReader(open(os.path.join(work, "clocks_ticks.csv"))))
    cbad = []
    if len(crow) != len(csites) or sum(r["case"] == "rollback" for r in crow) != ncw:
        print("  FAIL frame clocks: %d rows, %d site records, want %d rollbacks"
              % (len(crow), len(csites), ncw))
        return 1
    for row, rec in zip(crow, csites):
        k = int(row["k"])
        why = []
        if row["case"] == "rollback":
            if row["hooked"] != "0" or row["stranded"] != "0":
                why.append("hooked=%s stranded=%s" % (row["hooked"], row["stranded"]))
            if int(row["writes"]) != 2 * k + 1:
                why.append("%s writes, want %d" % (row["writes"], 2 * k + 1))
            want = clock_orig
        else:
            if row["hooked"] != "1" or row["stranded"] != "1":
                why.append("hooked=%s stranded=%s" % (row["hooked"], row["stranded"]))
            if int(row["writes"]) != k + 2:
                why.append("%s writes, want %d" % (row["writes"], k + 2))
            want = clock_want[:k] + clock_orig[k:]
            mine = [t for t in ticks if t["k"] == str(k)]
            off = [t for t in mine
                   if any(int(t["slot%d" % j]) != int(t["counter"])
                          for j in range(2 + len(fch["holds"])))]
            modes = {(t["fps"], t["mode"], t["muted"]) for t in mine}
            if not mine or off:
                why.append("%d of %d ticks have a counter that is not the frame counter%s"
                           % (len(off), len(mine),
                              " (first: tick %s, %s fps)" % (off[0]["tick"], off[0]["fps"])
                              if off else ""))
            else:
                print("  stranded after write %d (the hook and %d reads stay): %d ticks in %d"
                      " fps/context/A-B states, every counter the frame counter"
                      % (k, k - 1, len(mine), len(modes)))
        if row["reads"] != "0" or row["gates"] != "0":
            why.append("reads=%s gates=%s marked patched" % (row["reads"], row["gates"]))
        diff = [i for i, (got, exp) in enumerate(zip(rec, want)) if got != exp]
        if diff:
            why.append("%d site(s) wrong, first #%d" % (len(diff), diff[0]))
        if why:
            cbad.append("%s at %d: %s" % (row["case"], k, "; ".join(why)))
    print("frame clocks, every write rejected in turn (%d) and 3 stranded: %d wrong"
          % (ncw, len(cbad)))
    for b in cbad[:8]:
        print("  FAIL " + b)
    fails += len(cbad)

    print("\nwork dir %s\n%s" % (work, "FAILED (%d)" % fails if fails else
                                  "grouped installs fail safely"))
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UcError as e:
        sys.exit("emulation fault: %s" % e)
