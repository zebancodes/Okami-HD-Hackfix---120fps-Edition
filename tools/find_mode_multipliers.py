#!/usr/bin/env python3
"""Find the INTEGER half of the mode-byte family and emit the C table.

src/mode_constants.py covers the float side: the `{k**0.5, k}` damping pairs and
the `movss xmm,[0.5]` per-tick time steps that the engine selects by testing the
mode byte at main+0xB6AC45. There is an integer side as well, and it was missed
entirely, because it holds no constant a float scan could recognise -- the
"table" is the instruction itself:

    cmp   byte ptr [B6AC45], 1
    ...
    jne   skip
    add   eax, eax          <- the whole per-mode table, as one instruction
  skip:

and, where the compiler preferred branchless code,

    cmp   byte ptr [B6AC45], 1
    sete  al
    inc   eax               <- eax = 1 or 2
    imul  eax, <n>

Both compute `n * (mode == 1 ? 2 : 1)`, and every one of them is a duration in
ticks: an animation keyframe length, the span of an interpolation. The mode byte
is 1 at 120 fps too, so all of them still double where they now need to
quadruple, and everything they drive runs exactly twice as fast as it should.

The patch replaces the hard-coded 2 with a dword it holds at 2 in 60 fps mode
and 4 in 120 fps mode, so the 60 fps behaviour is reproduced bit for bit.

    python tools/find_mode_multipliers.py
"""
import os
import re
import sys

try:
    import pefile
    import capstone
except ImportError:
    sys.exit("needs pefile and capstone: pip install pefile capstone")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402

BASE_IMAGE = 0x180000000
MODE_BYTE = 0xB6AC45
RIP = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")

# shape ids, mirrored in dinput8_proxy.cpp
S_IMUL_EAX = 0     # copy; jne L; imul eax,[mult]; L: jmp resume
S_MOVSX_EDX = 1    # copy movsx; jne L; mov eax,edx; imul eax,[mult]; jmp resume; L: jmp alt
S_SETE_R9 = 2      # jne L; mov r9d,[mult]; jmp M; L: mov r9d,1; M: jmp resume
S_SETE_EBX = 3     # jne L; mov ebx,[mult]; jmp M; L: mov ebx,1; M: copy lea; jmp resume
S_CMP2_EAX = 4     # copy; cmp eax,2; jne L; mov eax,[mult]; L: jmp resume

# Each site was read out of the disassembly by hand (there are six, and every
# one needed its own argument about which bytes are safe to displace and which
# flags are still live). The generator's job is to prove they are still there
# and to emit the bytes, not to rediscover them.
SITES = [
    (0x1B8C36, 8, S_IMUL_EAX,  0x1B8C42, 0, "UI layout colour track length"),
    (0x1B8C68, 6, S_MOVSX_EDX, 0x1B8C71, 0x1B8C72, "UI layout position track length"),
    (0x1B8C96, 8, S_IMUL_EAX,  0x1B8CA2, 0, "UI layout rotation track length"),
    # (D) was very nearly missed. A capstone scan for calls put this function's
    # entry at 1B8CB8 -- eight bytes past the real one at 1B8CB0 -- found no
    # callers, and wrote it off as dead. Ghidra's decompilation shows it with
    # three callers, exactly like the other three, and byte-identical code to
    # (B). Prefer real function boundaries over a guess at where one starts.
    (0x1B8CCB, 6, S_MOVSX_EDX, 0x1B8CD4, 0x1B8CD5, "UI layout scale track length"),
    (0x1B4768, 7, S_SETE_R9,   0x1B476F, 0, "UI layout keyframe search compare"),
    (0x1B47D6, 9, S_SETE_EBX,  0x1B47DF, 0, "UI layout keyframe interpolation span"),
    (0x4BA141, 7, S_CMP2_EAX,  0x4BA148, 0, "motion blend length (cKamikiFree +0xF50)"),
]


def main():
    pe = pefile.PE(os.path.join(GAME, "main.dll"), fast_load=True)
    img = pe.get_memory_mapped_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    # Every site must be preceded by a `cmp [modebyte], 1`. The branch shapes
    # additionally need that compare's flags to still be live at the detour,
    # because their stub re-tests ZF; kMultCmp2Eax does not, since the compiler
    # already folded the answer into eax with `sete`/`inc` and the stub reads it
    # back from there.
    def guarded(rva, carries_in_eax=False):
        keep = ("mov", "movsx", "movzx", "movsxd", "lea", "cdqe", "nop")
        if carries_in_eax:
            keep += ("sete", "setne", "inc", "xor")
        for back in range(8, 48):
            start = rva - back
            insns = list(md.disasm(bytes(img[start:rva + 16]), BASE_IMAGE + start))
            if not insns or insns[0].address != BASE_IMAGE + start:
                continue
            addrs = [i.address - BASE_IMAGE for i in insns]
            if rva not in addrs:
                continue
            for i in insns:
                a = i.address - BASE_IMAGE
                if a >= rva:
                    break
                if i.mnemonic != "cmp":
                    continue
                mm = RIP.search(i.op_str)
                if not mm:
                    continue
                d = int(mm.group(2), 16)
                t = a + i.size + (d if mm.group(1) == "+" else -d)
                if t == MODE_BYTE and i.op_str.rstrip().endswith(", 1"):
                    # nothing between may write flags
                    for j in insns:
                        ja = j.address - BASE_IMAGE
                        if ja <= a or ja >= rva:
                            continue
                        if j.mnemonic not in keep:
                            return None
                        if j.mnemonic == "xor" and not carries_in_eax:
                            return None
                    return a
        return None

    out = [
        "// Generated by tools/find_mode_multipliers.py -- do not edit by hand.",
        "// See the README section \"120 fps and the mode byte\".",
        "//",
        "// The integer half of the mode-byte family: `n * (mode == 1 ? 2 : 1)`,",
        "// where n is a duration in ticks. The mode byte is 1 at 120 fps as well, so",
        "// each of these doubles where it needs to quadruple and whatever it times",
        "// runs at exactly twice the speed it should.",
        "//",
        "// The hard-coded 2 becomes a dword the patch holds at 2 in 60 fps mode and 4",
        "// in 120 fps mode, so 60 fps is reproduced exactly.",
        "",
        "// how the stub rebuilds each site",
        "enum ModeMultShape {",
        "    kMultImulEax = 0,   // copy; jne L; imul eax,[mult]; L: jmp resume",
        "    kMultMovsxEdx = 1,  // copy movsx; jne L; mov eax,edx; imul; jmp resume; L: jmp alt",
        "    kMultSeteR9 = 2,    // jne L; mov r9d,[mult]; jmp M; L: mov r9d,1; M: jmp resume",
        "    kMultSeteEbx = 3,   // as above in ebx, then the displaced lea",
        "    kMultCmp2Eax = 4,   // copy; cmp eax,2; jne L; mov eax,[mult]; L: jmp resume",
        "};",
        "",
        "struct ModeMult {",
        "    uint32_t rva;        // where the detour goes",
        "    uint32_t resume;     // where the stub rejoins",
        "    uint32_t altResume;  // the second exit, for kMultMovsxEdx",
        "    uint8_t len;         // bytes displaced",
        "    uint8_t shape;",
        "    uint8_t orig[10];    // exactly what must be there",
        "    const char* what;",
        "};",
        "",
        "static const ModeMult kModeMults[] = {",
    ]
    for rva, ln, shape, resume, alt, what in SITES:
        g = guarded(rva, shape == S_CMP2_EAX)
        if g is None:
            sys.exit("no live `cmp [mode],1` reaches main+%06X" % rva)
        raw = bytes(img[rva:rva + ln])
        out.append("    {0x%06X, 0x%06X, 0x%06X, %d, %d, {%s}, \"%s\"},  // guard at %06X"
                   % (rva, resume, alt, ln, shape,
                      ", ".join("0x%02X" % b for b in raw) +
                      ", 0x00" * (10 - ln), what, g))
        print("  main+%06X  %-42s guard main+%06X" % (rva, what, g))
    out.append("};")

    dest = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "src", "mode_multipliers.h"))
    with open(dest, "w", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n%d sites -> src/mode_multipliers.h" % len(SITES))


if __name__ == "__main__":
    main()
