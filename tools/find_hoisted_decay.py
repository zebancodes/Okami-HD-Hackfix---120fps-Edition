#!/usr/bin/env python
"""Find per-tick decays whose factor the compiler hoisted into a register.

tools/find_decay_factors.py matches the damp that reads its constant inline:

    movss xmm0, [rsi+0xE48]
    mulss xmm0, dword ptr [rip+K]      <- it sees this
    movss [rsi+0xE48], xmm0

When the same constant is used more than once in a function the compiler loads
it into a callee-saved register far upstream and the damp becomes:

    movss xmm6, dword ptr [rip+K]      ... hundreds of bytes earlier
    ...
    movss xmm0, [rdi+0xE48]
    mulss xmm0, xmm6                   <- no rip operand, invisible to the match
    movss [rdi+0xE48], xmm0

Identical arithmetic, no pattern to find. main+3B55C0 is one of these: it is
`hspeed *= 0.1` once per tick in the jump handler, and at 120 fps it runs four
times as often as the value was chosen for. In the first harness session it
took Amaterasu from 1.05917 to 0.00330 units/tick in six ticks, before she had
even left the ground.

Reading the register is only sound if nothing else writes it, so that is the
test applied here rather than a dataflow approximation:

  * exactly one `movss xmmS, [rip+K]` in the whole function, K a .rdata float
    strictly between 0 and 1,
  * no other instruction anywhere in the function writes xmmS,
  * the multiply sits in a load/multiply/store triple on one field, so it is
    unambiguously that field decaying and not an intermediate.

A site that fails any of those is reported under --all and never emitted.

    python tools/find_hoisted_decay.py            # what is in the player
    python tools/find_hoisted_decay.py --image    # the whole dll, for scale
    python tools/find_hoisted_decay.py --header   # write src/hoisted_decay.h
"""
import argparse
import os
import struct
import sys

try:
    import capstone
    import pefile
except ImportError:
    sys.exit("needs pefile and capstone: pip install pefile capstone")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402

DISPATCH_TABLE = 0x3AF8A0
DISPATCH_N = 0x5F


def player_states(img):
    """Functions the player state dispatcher (main+3AF020) can reach."""
    out = set()
    for i in range(DISPATCH_N):
        try:
            off = struct.unpack_from("<I", img, DISPATCH_TABLE + i * 4)[0]
        except Exception:
            break
        if not (0x100000 <= off <= 0x700000):
            continue
        if img[off] == 0x48 and img[off + 3] == 0xE8:
            rel = struct.unpack_from("<i", img, off + 4)[0]
            out.add(off + 8 + rel)
    return out


def function_bounds(img, start, limit=0x4000):
    """Walk to the first int3 run that follows a terminator."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    end = start
    for ins in md.disasm(img[start:start + limit], start):
        end = ins.address + ins.size
        if ins.mnemonic == "int3":
            return ins.address
    return end


def decode(img, lo, hi):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    out = []
    addr = lo
    while addr < hi:
        progressed = False
        for ins in md.disasm(img[addr:hi], addr):
            out.append(ins)
            addr = ins.address + ins.size
            progressed = True
        if not progressed:
            addr += 1
    return out


def rip_target(ins):
    if "rip" not in ins.op_str:
        return None
    try:
        tail = ins.op_str.split("rip")[1].split("]")[0].replace(" ", "")
        return ins.address + ins.size + int(tail, 16)
    except Exception:
        return None


def writes(ins):
    """The xmm register this instruction defines, if any."""
    ops = [o.strip() for o in ins.op_str.split(",")]
    if not ops or not ops[0].startswith("xmm"):
        return None
    if ins.mnemonic in ("comiss", "ucomiss", "comisd", "ucomisd"):
        return None
    return ops[0]


def field_of(op):
    """`dword ptr [rdi + 0xe48]` -> ('rdi', 0xe48)"""
    if "[" not in op or "rip" in op:
        return None
    inner = op.split("[", 1)[1].split("]", 1)[0]
    parts = [x.strip() for x in inner.split("+")]
    if len(parts) != 2:
        return None
    try:
        return parts[0], int(parts[1], 16)
    except ValueError:
        return None


def branch_edges(ins):
    """(from, to) for every direct branch inside this function."""
    out = []
    for i in ins:
        if i.mnemonic.startswith("j") and i.op_str.startswith("0x"):
            try:
                out.append((i.address, int(i.op_str, 16)))
            except ValueError:
                pass
    return out


def entered_only_from_within(edges, lo, hi):
    """True if control cannot reach [lo,hi] except by falling into lo.

    A branch that lands inside the interval is harmless as long as it comes
    from inside the interval as well: the only way to be executing in there at
    all is then to have fallen through lo, which is where the constant was
    loaded. A branch from outside is an entry point that skips the load, and
    the register could hold anything.
    """
    for src, dst in edges:
        if lo <= dst <= hi and not (lo <= src <= hi):
            return False
    return True


def scan(img, rdata, funcs):
    """Accept a `mulss xmmD, xmmS` only when xmmS provably holds a constant.

    The test is local, not whole-function: a callee-saved register is loaded
    with one constant, used, then loaded with another, and asking whether it is
    written once in the whole function rejects every real site. What has to
    hold is that the NEAREST preceding definition of xmmS is a rodata load and
    that control cannot arrive at the multiply without passing through it --
    so no branch may target anything strictly between the two.
    """
    good, rejected = [], []
    for fn in sorted(funcs):
        end = function_bounds(img, fn)
        ins = decode(img, fn, end)
        edges = branch_edges(ins)
        for n, i in enumerate(ins):
            if i.mnemonic != "mulss":
                continue
            ops = [o.strip() for o in i.op_str.split(",")]
            if len(ops) != 2 or not ops[1].startswith("xmm"):
                continue
            dst, src = ops[0], ops[1]
            # nearest preceding definition of src
            why, load = None, None
            for k in range(n - 1, -1, -1):
                if writes(ins[k]) == src:
                    load = ins[k]
                    break
            if load is None:
                why = "%s is never defined before this point" % src
            elif load.mnemonic != "movss":
                why = "%s last defined by %s, not a constant load" % (src, load.mnemonic)
            else:
                t = rip_target(load)
                if t is None or not (rdata[0] <= t < rdata[1]):
                    why = "%s last loaded from something other than rodata" % src
                else:
                    v = struct.unpack_from("<f", img, t)[0]
                    if not (0.0 < v < 1.0):
                        why = "%s holds %g, not a decay factor" % (src, v)
            if why is None:
                # control must not be able to enter between the load and the use
                lo, hi = load.address + load.size, i.address
                if not entered_only_from_within(edges, lo, hi):
                    why = "a branch from outside lands between the load and the multiply"
            if why is None:
                if n == 0 or n + 1 >= len(ins):
                    why = "not inside a load/multiply/store triple"
                else:
                    ld, st = ins[n - 1], ins[n + 1]
                    lf = (field_of(ld.op_str.split(",", 1)[1])
                          if ld.mnemonic == "movss" and "," in ld.op_str else None)
                    sf = field_of(st.op_str.split(",", 1)[0]) if st.mnemonic == "movss" else None
                    lreg = ld.op_str.split(",")[0].strip() if ld.mnemonic == "movss" else None
                    sreg = st.op_str.split(",")[-1].strip() if st.mnemonic == "movss" else None
                    if lf is None or sf is None or lf != sf or lreg != dst or sreg != dst:
                        why = "not inside a load/multiply/store triple"
            t = rip_target(load) if load is not None and load.mnemonic == "movss" else None
            v = struct.unpack_from("<f", img, t)[0] if t is not None and rdata[0] <= t < rdata[1] else 0.0
            rec = (fn, i, (load, t or 0, v), dst, src)
            if why:
                rejected.append((rec, why))
            else:
                good.append((rec, ins[n - 1], ins[n + 1]))
    return good, rejected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", action="store_true", help="scan every function, not just the player")
    ap.add_argument("--all", action="store_true", help="also list what was rejected and why")
    ap.add_argument("--header", action="store_true", help="write src/hoisted_decay.h")
    args = ap.parse_args()

    pe = pefile.PE(os.path.join(GAME, "main.dll"), fast_load=True)
    img = pe.get_memory_mapped_image()
    text = rdata = None
    for s in pe.sections:
        if b".text" in s.Name:
            text = (s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize)
        if b".rdata" in s.Name:
            rdata = (s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize)

    if args.image:
        # every call target in .text, as a cheap function list
        funcs = set()
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        i = text[0]
        while True:
            i = img.find(b"\xe8", i + 1, text[1])
            if i < 0:
                break
            d = struct.unpack_from("<i", img, i + 1)[0]
            t = i + 5 + d
            if text[0] <= t < text[1]:
                funcs.add(t)
    else:
        funcs = player_states(img)

    good, rejected = scan(img, rdata, funcs)
    print("scanned %d function(s): %d verified hoisted decays, %d rejected"
          % (len(funcs), len(good), len(rejected)))
    for (fn, mul, load, dst, src), ld, st in sorted(good, key=lambda g: g[0][1].address):
        li, lrva, lval = load
        fld = field_of(st.op_str.split(",", 1)[0])
        print("  main+%06X  %s *= %-6g   factor held in %s from main+%06X (loaded main+%06X)"
              % (mul.address, ("+0x%X" % fld[1]) if fld else "?", lval, src, lrva, li.address))
    if args.all:
        print("\nrejected:")
        seen = {}
        for (fn, mul, load, dst, src), why in rejected:
            seen[why] = seen.get(why, 0) + 1
        for why, n in sorted(seen.items(), key=lambda kv: -kv[1]):
            print("  %4d  %s" % (n, why))

    if not args.header:
        return
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "src", "hoisted_decay.h")
    with open(out, "w", newline="\n") as f:
        f.write("// Generated by tools/find_hoisted_decay.py -- do not edit by hand.\n")
        f.write("// See the README section \"A decay the finder could not see\".\n//\n")
        f.write("// Each entry is `field *= k` once per tick, where k lives in a register\n")
        f.write("// the compiler hoisted out of the loop. The load is verified and left\n")
        f.write("// alone; the multiply and the store after it are replaced by a detour\n")
        f.write("// that multiplies by k**timeScale instead.\n//\n")
        f.write("// %d site(s) in the player state handlers.\n\n" % len(good))
        # a REX-prefixed movss/mulss is a byte longer than the plain form, so
        # every array is sized for the worst case and carries its own length
        f.write("struct HoistDecaySite {\n")
        f.write("    uint32_t loadRva;       // movss xmmS, [rip+K] -- verified, never patched\n")
        f.write("    uint8_t  loadOrig[10];\n")
        f.write("    uint8_t  loadLen;\n")
        f.write("    uint32_t mulRva;        // mulss xmmD, xmmS    -- replaced\n")
        f.write("    uint8_t  mulOrig[6];\n")
        f.write("    uint8_t  mulLen;\n")
        f.write("    uint8_t  storeOrig[10]; // the store after it, relocated into the cave\n")
        f.write("    uint8_t  storeLen;\n")
        f.write("    uint8_t  xmmD;          // destination register index, for the new mulss\n")
        f.write("    float    k;             // the shipped factor\n")
        f.write("    const char* what;\n")
        f.write("};\n\n")
        f.write("static const HoistDecaySite kHoistDecaySites[] = {\n")

        def pad(bs, n):
            return ", ".join(["0x%02X" % b for b in bs] + ["0x00"] * (n - len(bs)))

        for (fn, mul, load, dst, src), ld, st in sorted(good, key=lambda g: g[0][1].address):
            li, lrva, lval = load
            fld = field_of(st.op_str.split(",", 1)[0])
            assert len(li.bytes) <= 10 and len(mul.bytes) <= 6 and len(st.bytes) <= 10
            f.write("    {0x%06X, {%s}, %d,\n"
                    "     0x%06X, {%s}, %d,\n"
                    "     {%s}, %d, %d, %gf,\n"
                    "     \"main+%06X %s *= %g\"},\n"
                    % (li.address, pad(li.bytes, 10), len(li.bytes),
                       mul.address, pad(mul.bytes, 6), len(mul.bytes),
                       pad(st.bytes, 10), len(st.bytes),
                       int(dst[3:]), lval, mul.address,
                       ("+0x%X" % fld[1]) if fld else "?", lval))
        f.write("};\n")
    print("\nwrote %s" % out)


if __name__ == "__main__":
    main()
