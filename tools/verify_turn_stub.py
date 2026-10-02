#!/usr/bin/env python
"""Decode the turn-rate stub before it ever runs.

installTurnRate() emits its bytes one at a time with hand-computed rip
displacements and four rel8 branch fixups. A wrong fixup does not fail to
build and does not fail to install -- it crashes inside the angular approach,
which runs for every actor every tick, so the game dies instantly and the log
says the patch installed fine.

This mirrors the emitter, lays the result out at a plausible address and
disassembles it, then checks:

  * every instruction decodes and the sequence is the intended one,
  * each rip operand lands on the constant it was meant to,
  * each branch lands on an instruction boundary inside the stub,
  * the three "leave k alone" exits converge on the displaced prologue,
  * the tail is the relocated prologue followed by a jump back to the resume.

    python tools/verify_turn_stub.py
"""
import struct
import sys

try:
    import capstone
except ImportError:
    sys.exit("needs capstone: pip install capstone")

MAIN = 0x00007FFEF7050000
CAVE = MAIN + 0x00A00000    # a cave allocNear would plausibly hand back
TURN_RVA = 0x2DA510
TURN_RESUME = 0x2DA519
TURN_ORIG = bytes([0x48, 0x83, 0xEC, 0x58, 0x0F, 0x29, 0x74, 0x24, 0x40])

ONE = CAVE - 0x40      # stand-ins for the cave data slots
ZERO = CAVE - 0x3C
COUNT = CAVE - 0x38


def emit():
    code = bytearray()

    def rip(target, trailing=0):
        d = target - (CAVE + len(code) + 4 + trailing)
        code.extend(struct.pack("<i", d))

    code.extend([0xF3, 0x0F, 0x10, 0x1D]); rip(ONE)          # movss xmm3,[one]
    code.extend([0xF3, 0x0F, 0x5C, 0xDA])                    # subss xmm3,xmm2
    code.extend([0x0F, 0x2F, 0x1D]); rip(ZERO)               # comiss xmm3,[zero]
    code.append(0x76); fix1 = len(code); code.append(0)      # jbe done
    code.extend([0xF3, 0x0F, 0x10, 0x25]); rip(ONE)          # movss xmm4,[one]
    code.extend([0x0F, 0x2F, 0xE3])                          # comiss xmm4,xmm3
    code.append(0x76); fix2 = len(code); code.append(0)      # jbe done
    code.extend([0x80, 0x3D]); rip(COUNT, 1); code.append(0x00)  # cmp byte [cnt],0
    code.append(0x74); fix3 = len(code); code.append(0)      # je done
    code.extend([0xF3, 0x0F, 0x51, 0xDB])                    # sqrtss xmm3,xmm3
    code.extend([0x80, 0x3D]); rip(COUNT, 1); code.append(0x01)  # cmp byte [cnt],1
    code.append(0x74); fix4 = len(code); code.append(0)      # je store
    code.extend([0xF3, 0x0F, 0x51, 0xDB])                    # sqrtss xmm3,xmm3
    code[fix4] = len(code) - fix4 - 1                        # store:
    code.extend([0xF3, 0x0F, 0x10, 0x15]); rip(ONE)          # movss xmm2,[one]
    code.extend([0xF3, 0x0F, 0x5C, 0xD3])                    # subss xmm2,xmm3
    done = len(code)
    code[fix1] = done - fix1 - 1
    code[fix2] = done - fix2 - 1
    code[fix3] = done - fix3 - 1
    code.extend(TURN_ORIG)
    code.append(0xE9)
    back = (MAIN + TURN_RESUME) - (CAVE + len(code) + 4)
    code.extend(struct.pack("<i", back))
    return bytes(code), done


WANT = [
    ("movss", "xmm3", ONE), ("subss", None, None), ("comiss", "xmm3", ZERO),
    ("jbe", None, None), ("movss", "xmm4", ONE), ("comiss", None, None),
    ("jbe", None, None), ("cmp", None, COUNT), ("je", None, None),
    ("sqrtss", None, None), ("cmp", None, COUNT), ("je", None, None),
    ("sqrtss", None, None), ("movss", "xmm2", ONE), ("subss", None, None),
    ("sub", None, None), ("movaps", None, None), ("jmp", None, None),
]


def main():
    code, done_off = emit()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    ins = list(md.disasm(code, CAVE))
    consumed = sum(i.size for i in ins)
    if consumed != len(code):
        sys.exit("FAIL: %d of %d bytes decoded -- a malformed instruction"
                 % (consumed, len(code)))
    if len(ins) != len(WANT):
        for i in ins:
            print("  %s %s" % (i.mnemonic, i.op_str))
        sys.exit("FAIL: %d instructions, expected %d" % (len(ins), len(WANT)))

    bounds = {i.address for i in ins}
    done_addr = CAVE + done_off
    problems = []
    for n, (i, (mn, reg, target)) in enumerate(zip(ins, WANT)):
        if i.mnemonic != mn:
            problems.append("%d: %s, expected %s" % (n, i.mnemonic, mn))
            continue
        if reg and not i.op_str.startswith(reg):
            problems.append("%d: %s writes %s, expected %s" % (n, mn, i.op_str, reg))
        if target is not None:
            got = None
            if "rip" in i.op_str:
                tail = i.op_str.split("rip")[1].split("]")[0].replace(" ", "")
                got = i.address + i.size + int(tail, 16)
            if got != target:
                problems.append("%d: %s reads %s, expected %X"
                                % (n, mn, hex(got) if got else "nothing", target))
        if mn in ("jbe", "je"):
            dst = int(i.op_str, 16)
            if dst not in bounds and dst != CAVE + len(code):
                problems.append("%d: %s lands at %X, not an instruction boundary"
                                % (n, mn, dst))

    # the three bail-outs must all reach the relocated prologue
    exits = [ins[3], ins[6], ins[8]]
    for e in exits:
        dst = int(e.op_str, 16)
        if dst != done_addr:
            problems.append("bail at %X goes to %X, expected the prologue at %X"
                            % (e.address, dst, done_addr))
    # and the inner one must skip exactly one sqrtss
    inner = int(ins[11].op_str, 16)
    if inner != ins[13].address:
        problems.append("the 60 fps path lands at %X, expected the store at %X"
                        % (inner, ins[13].address))
    # tail: prologue bytes verbatim, then a jump to the resume
    if code[done_off:done_off + len(TURN_ORIG)] != TURN_ORIG:
        problems.append("the relocated prologue does not match the original bytes")
    if int(ins[-1].op_str, 16) != MAIN + TURN_RESUME:
        problems.append("the jump back goes to %s, expected %X"
                        % (ins[-1].op_str, MAIN + TURN_RESUME))

    for n, i in enumerate(ins):
        mark = "  <- done" if i.address == done_addr else ""
        print("  %2d  %-24s %s %s%s"
              % (n, i.bytes.hex(), i.mnemonic, i.op_str, mark))
    if problems:
        print()
        for x in problems:
            print("FAIL: %s" % x)
        sys.exit(1)
    print("\nturn stub verified: %d bytes, decode clean, rip operands and all four"
          " branch fixups land where intended" % len(code))


if __name__ == "__main__":
    main()
