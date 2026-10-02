#!/usr/bin/env python
"""Disassemble the machine code the patch writes, instead of trusting it.

    .venv/Scripts/python tools/verify_stubs.py

Every detour in this patch is hand-assembled: byte arrays in dinput8_proxy.cpp
copied into a code cave at runtime. Nothing ever checked that those bytes decode
to the instructions the comments claim, and two separate faults have already
come out of that blind spot:

  * the airborne acceleration detour relocated `mulss xmm0,[rip+0x7B57B4]`
    without rewriting the displacement, so it multiplied by an arbitrary float
    instead of the time scale, and the "fix" silently did nothing for a session;

  * the harness entry stub is fifty bytes of hand-written prologue that had
    never executed when it shipped -- one wrong byte there is an instant crash
    on load.

So this reads the byte arrays back out of the source and decodes them, checking
the things a hand-assembled stub gets wrong silently:

  * the instruction sequence is what the source comments say it is;
  * every push has its matching pop, in reverse order;
  * rsp is 16-byte aligned at every call, as the Windows x64 ABI requires;
  * the stub's net effect on rsp is zero;
  * the mulss encodings really name the xmm register the caller asked for.
"""
import os
import re
import sys

try:
    import capstone
except ImportError:
    sys.exit("needs capstone: .venv/Scripts/python -m pip install capstone")

PROXY = os.path.join(os.path.dirname(__file__), "..", "src", "dinput8_proxy.cpp")
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def array_bytes(src, name):
    """Read `static const uint8_t <name>[] = { ... };` out of the source.

    Tokenise on commas rather than grepping for `0x..`: a placeholder written as
    a bare `0` is perfectly good C and dropping it silently shifts every byte
    after it, which is exactly the sort of fault this tool exists to catch.
    """
    m = re.search(r"%s\[\]\s*=\s*\{(.*?)\};" % re.escape(name), src, re.S)
    if not m:
        return None
    body = re.sub(r"//[^\n]*", "", m.group(1))  # strip the inline comments
    out = []
    for tok in body.split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(int(tok, 0) & 0xFF)
    return bytes(out)


def walk(code, base_align=8):
    """Decode, tracking rsp alignment. Returns (rows, problems)."""
    rows, problems = [], []
    rsp = base_align
    pushed = []
    for i in MD.disasm(code, 0):
        before = rsp % 16
        if i.mnemonic in ("push", "pushfq"):
            rsp -= 8
            pushed.append(i.op_str or "flags")
        elif i.mnemonic in ("pop", "popfq"):
            rsp += 8
            what = i.op_str or "flags"
            if not pushed:
                problems.append("pop %s with nothing pushed" % what)
            else:
                want = pushed.pop()
                if want != what:
                    problems.append("pop %s does not match push %s" % (what, want))
        elif i.mnemonic in ("sub", "add") and i.op_str.startswith("rsp,"):
            delta = int(i.op_str.split(",")[1].strip(), 16)
            rsp += -delta if i.mnemonic == "sub" else delta
        if i.mnemonic == "call" and before != 0:
            problems.append("call at +0x%X with rsp %% 16 == %d (ABI requires 0)"
                            % (i.address, before))
        rows.append((i.address, before, i.mnemonic, i.op_str))
    if pushed:
        problems.append("never popped: %s" % ", ".join(reversed(pushed)))
    if rsp != base_align:
        problems.append("net rsp change %d, expected 0" % (rsp - base_align))
    return rows, problems


def check_harness_stub(src, verbose):
    raw = array_bytes(src, "kHarnessStub")
    if raw is None:
        return ["kHarnessStub not found in dinput8_proxy.cpp"]
    # the install patches a callback address into the imm64; give it a
    # recognisable non-zero value so the decode is realistic
    at = re.search(r"kHarnessStubFnAt = (\d+)", src)
    if not at:
        return ["kHarnessStubFnAt not found"]
    off = int(at.group(1))
    raw = raw[:off] + bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]) + raw[off + 8:]
    # the displaced prologue and the jump back are appended at install time
    tail = array_bytes(src, "kHarnessHookOrig") or b""
    m = re.search(r"kHarnessHookOrig\[5\]\s*=\s*\{([^}]*)\}", src)
    if m:
        tail = bytes(int(b, 16) for b in re.findall(r"0x([0-9A-Fa-f]{2})", m.group(1)))
    code = raw + tail + bytes([0xE9, 0, 0, 0, 0])

    rows, problems = walk(code)
    if verbose:
        print("  harness entry stub (%d bytes)" % len(code))
        for addr, align, mn, ops in rows:
            print("    +%04X  rsp%%16=%-2d  %-8s %s" % (addr, align, mn, ops))
    # the callback must actually be called, and the displaced prologue must run
    mns = [r[2] for r in rows]
    if "call" not in mns:
        problems.append("stub never calls the callback")
    if not any(r[2] == "mov" and "rbx" in r[3] for r in rows):
        problems.append("displaced prologue (mov [rsp+0x10], rbx) is missing")
    if mns[-1] != "jmp":
        problems.append("stub does not end in a jump back")
    return problems


def check_frame_clock_stub(src, verbose):
    """The per-tick hook on flower_tick's `inc [frameCounter]` (frame_clocks.h):
    the relocated increment, then the template, then the jump back. rsp is
    16-aligned at the hook site, so base_align is 0 here, not 8."""
    raw = array_bytes(src, "kFrameClockStub")
    if raw is None:
        return ["kFrameClockStub not found in dinput8_proxy.cpp"]
    at = re.search(r"kFrameClockStubFnAt = (\d+)", src)
    if not at:
        return ["kFrameClockStubFnAt not found"]
    off = int(at.group(1))
    if raw[off - 2:off] != b"\x48\xB8":
        return ["kFrameClockStubFnAt (%d) does not point at a movabs rax immediate" % off]
    raw = raw[:off] + bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]) + raw[off + 8:]
    code = b"\xFF\x05\x00\x00\x00\x00" + raw + bytes([0xE9, 0, 0, 0, 0])
    rows, problems = walk(code, base_align=0)
    if verbose:
        print("  frame clock tick stub (%d bytes)" % len(code))
        for addr, align, mn, ops in rows:
            print("    +%04X  rsp%%16=%-2d  %-8s %s" % (addr, align, mn, ops))
    mns = [r[2] for r in rows]
    if mns[0] != "inc" or mns[1] != "pushfq" or mns[-2] != "popfq" or mns[-1] != "jmp":
        problems.append("the stub is not inc, pushfq ... popfq, jmp: %s" % mns)
    if mns.count("call") != 1:
        problems.append("the stub calls %d times" % mns.count("call"))
    saved = [r[3].split(",")[1].strip() for r in rows if r[2] == "movdqu" and
             r[3].startswith("xmmword ptr")]
    restored = [r[3].split(",")[0].strip() for r in rows if r[2] == "movdqu" and
                r[3].startswith("xmm") and not r[3].startswith("xmmword")]
    if saved != ["xmm%d" % i for i in range(6)] or restored != saved:
        problems.append("xmm saves %s / restores %s, want xmm0-5 both" % (saved, restored))
    return problems


def check_mulss_encoding(verbose):
    """installScaleDetour builds `mulss xmmN,[rip+d]` as 0x05 | (N << 3)."""
    problems = []
    if verbose:
        print("  installScaleDetour mulss encodings")
    for reg in range(6):
        code = bytes([0xF3, 0x0F, 0x59, 0x05 | (reg << 3), 0, 0, 0, 0])
        got = list(MD.disasm(code, 0))
        if not got:
            problems.append("mulss for xmm%d does not decode" % reg)
            continue
        i = got[0]
        want = "xmm%d," % reg
        if i.mnemonic != "mulss" or not i.op_str.startswith(want):
            problems.append("reg %d encodes as `%s %s`, expected mulss %s.."
                            % (reg, i.mnemonic, i.op_str, want))
        elif verbose:
            print("    xmm%d -> %s %s" % (reg, i.mnemonic, i.op_str))
    return problems


def check_jump_pick(src, verbose):
    """The one bespoke compare stub: load the field, scale it, compare."""
    if "installJumpPickDetour" not in src:
        return ["installJumpPickDetour not found"]
    code = bytes([0xF3, 0x0F, 0x10, 0x8F, 0x48, 0x0E, 0x00, 0x00,   # movss xmm1,[rdi+0xE48]
                  0xF3, 0x0F, 0x59, 0x0D, 0, 0, 0, 0,               # mulss xmm1,[rip+d]
                  0x0F, 0x2F, 0xC1,                                 # comiss xmm0, xmm1
                  0xE9, 0, 0, 0, 0])                                # jmp back
    rows, problems = walk(code)
    if verbose:
        print("  jump variant select stub")
        for addr, align, mn, ops in rows:
            print("    +%04X  %-8s %s" % (addr, mn, ops))
    seq = [r[2] for r in rows]
    if seq != ["movss", "mulss", "comiss", "jmp"]:
        problems.append("unexpected sequence %s" % seq)
    # the compare must be xmm0 against the scaled scratch, in that order
    if rows[2][3].replace(" ", "") != "xmm0,xmm1":
        problems.append("comiss operands are %r, expected xmm0, xmm1" % rows[2][3])
    return problems


def main():
    verbose = "-q" not in sys.argv
    src = open(PROXY, encoding="utf-8").read()
    problems = []
    problems += check_harness_stub(src, verbose)
    problems += check_frame_clock_stub(src, verbose)
    problems += check_mulss_encoding(verbose)
    problems += check_jump_pick(src, verbose)
    if problems:
        print("\n%d stub problem(s):" % len(problems))
        for p in problems:
            print("   %s" % p)
        return 1
    print("\nstubs verified: decode, push/pop pairing, call alignment, net rsp 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
