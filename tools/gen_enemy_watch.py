#!/usr/bin/env python3
"""Generate src/enemy_watch.h: the enemy classes and fields the enemy watch reads.

The watch (src/enemy_watch_runtime.h) measures what a hit does to an enemy:
how far it flies, how high, how long it stays up, how often it is hit and
which states it goes through, once per stock tick at any frame rate. It points
each enemy class's update (vtable slot 8, +0x40) at a thunk that runs the
update unchanged and then samples the object. Nothing in the game's code is
written.

The classes are every vtable in tools/rtti_classes.txt whose RTTI (read here
from main.dll: the complete object locator at vtable[-1], its class hierarchy
descriptor and base class array) lists cEm, the enemy base class, as a base.
The fields are cEm's, each shown by an instruction of cEm's own code (a
function in cEm's vtable, so rcx is the enemy):

  * +E44  hit points (int): 238AB0, slot 30, "cmp dword [rcx+E44], 0" and on
          <= 0 "mov dword [rcx+E34], 3" (state 3, dying);
  * +E34  the state byte, +E35 the action, +E36 its step: the same store, and
          238B40 (slot 25) writes the dword E34 = 2 on a hit;
  * +E72  flags (0x80 hit this tick, 0x10 dead), +E76 the hit invulnerability
          (byte, ticks): 238B40 decrements it while the hit flag is clear;
  * +E76 = 10 in 23A0F0 (slot 21), the hit handler, which also copies the
          attacker's push vector into +E10;
  * +A8   the position pointer (cModel's constructor points it at the matrix
          translation +80): 2DA3D0, the root-motion move every enemy state
          calls, "mov rcx, [rcx+A8]" before cMatrix::Apply into it;
  * +B4   the heading: 238F40 passes "[rbx+B4]" to the turn helper 2DDF90;
          +B0 and +B8, the other two angles of the same rotation vector, are
          logged beside it;
  * +E54  the vertical velocity: the fall 20EA30 reads and writes it with the
          time step.

Every instruction cited is checked byte for byte by the runtime before it
patches a slot, and each slot must hold the update this table names.

    .venv/Scripts/python tools/gen_enemy_watch.py [--check]
"""
import hashlib
import os
import struct
import sys

import capstone
from capstone import x86_const as X
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT_H = os.path.join(ROOT, "src", "enemy_watch.h")
BASE = 0x180000000
SLOT = 8  # the update, +0x40
BASE_CLASS = b".?AVcEm@@"
CEM_VTABLE = 0x67E398


class Fail(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Fail(msg)


def build():
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    sha = hashlib.sha1(raw).hexdigest()
    pe = pefile.PE(data=raw, fast_load=True)
    need(pe.OPTIONAL_HEADER.ImageBase == BASE, "unexpected image base")
    img = pe.get_memory_mapped_image()
    secs = {s.Name.rstrip(b"\0").decode(): (s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize)
            for s in pe.sections}
    text = secs[".text"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def u32(a):
        return struct.unpack_from("<I", img, a)[0]

    def i32(a):
        return struct.unpack_from("<i", img, a)[0]

    def u64(a):
        return struct.unpack_from("<Q", img, a)[0]

    def type_name(td):
        s = img[td + 0x10:td + 0x10 + 256]
        return bytes(s[:s.index(b"\0")])

    def bases(vt):
        """The class's own name and its base names, from vtable[-1]'s RTTI."""
        col = u64(vt - 8) - BASE
        need(u32(col) == 1, "vtable %X: COL %X has signature %d" % (vt, col, u32(col)))
        need(u32(col + 4) == 0, "vtable %X is not the primary vtable" % vt)
        need(i32(col + 20) == col, "vtable %X: COL %X does not point at itself" % (vt, col))
        name = type_name(i32(col + 12))
        chd = i32(col + 16)
        n = u32(chd + 8)
        arr = i32(chd + 12)
        names = [type_name(i32(i32(arr + 4 * k))) for k in range(n)]
        need(names and names[0] == name, "vtable %X: base array does not start with the class" % vt)
        return name, names[1:]

    def ins_at(a):
        return next(md.disasm(img[a:a + 16], BASE + a))

    def slot(vt, k):
        return u64(vt + 8 * k) - BASE

    cited = {}

    def cite(a, mnemonic, want):
        i = ins_at(a)
        need(i.mnemonic == mnemonic and i.op_str == want,
             "%X is %s %s, not %s %s" % (a, i.mnemonic, i.op_str, mnemonic, want))
        cited[a] = bytes(i.bytes)
        return i

    # -- cEm itself, and the fields' evidence in its own code
    name, _b = bases(CEM_VTABLE)
    need(name == BASE_CLASS, "vtable %X is %r, not cEm" % (CEM_VTABLE, name))
    need(slot(CEM_VTABLE, 30) == 0x238AB0, "cEm slot 30 is not 238AB0")
    cite(0x238AB0, "cmp", "dword ptr [rcx + 0xe44], 0")
    cite(0x238AC6, "mov", "dword ptr [rcx + 0xe34], 3")
    need(slot(CEM_VTABLE, 25) == 0x238B40, "cEm slot 25 is not 238B40")
    cite(0x238B40, "movzx", "edx, word ptr [rcx + 0xe72]")
    cite(0x238B4C, "movzx", "eax, byte ptr [rcx + 0xe76]")
    cite(0x238B5B, "dec", "al")
    cite(0x238B5D, "mov", "byte ptr [rcx + 0xe76], al")
    cite(0x238B8B, "mov", "dword ptr [rcx + 0xe34], 2")
    need(slot(CEM_VTABLE, 21) == 0x23A0F0, "cEm slot 21 is not 23A0F0")
    cite(0x23A10D, "mov", "byte ptr [rcx + 0xe76], 0xa")
    cite(0x23A114, "add", "rcx, 0xe10")
    cite(0x2DA3D0, "lea", "r8, [rcx + 0xec0]")
    cite(0x2DA3DB, "mov", "rcx, qword ptr [rcx + 0xa8]")
    cite(0x238F56, "movss", "xmm1, dword ptr [rbx + 0xb4]")
    cite(0x238F6F, "call", hex(BASE + 0x2DDF90))
    # the fall reads and writes vy at +E54 of the enemy it is given (rcx)
    fall = [i for i in md.disasm(img[0x20EA30:0x20EA30 + 0x400], BASE + 0x20EA30)]
    e54 = [i for i in fall if any(op.type == X.X86_OP_MEM and op.mem.disp == 0xE54 for op in i.operands)]
    need(len(e54) >= 2, "the fall 20EA30 does not use +E54")
    for i in e54[:2]:
        cited[i.address - BASE] = bytes(i.bytes)

    # -- every class deriving from cEm, from rtti_classes.txt's vtables
    classes = []
    seen = set()
    for line in open(os.path.join(HERE, "rtti_classes.txt")):
        p = line.split()
        if len(p) < 4 or p[2] != "off=0":
            continue
        vt = int(p[0], 16)
        if vt in seen:
            continue
        seen.add(vt)
        name, bs = bases(vt)
        if BASE_CLASS not in bs:
            continue
        n = int(p[3].split("=")[1])
        need(n > SLOT, "%s: only %d slots" % (name, n))
        upd = slot(vt, SLOT)
        need(text[0] <= upd < text[1], "%s: slot %d is %X, outside .text" % (name, SLOT, upd))
        short = name[4:-2].decode()
        need(len(short) < 12, "class name %s too long" % short)
        classes.append((vt, upd, short))
    need(len(classes) >= 60, "only %d classes derive from cEm" % len(classes))
    # the thunk forwards every argument register, so any signature is safe;
    # a class whose slot is shared with a non-cEm vtable would be sampled
    # as an enemy, so no update of the table may sit in a non-cEm vtable
    updates = {u for _v, u, _n in classes}
    for line in open(os.path.join(HERE, "rtti_classes.txt")):
        p = line.split()
        if len(p) < 5 or p[2] != "off=0":
            continue
        vt = int(p[0], 16)
        if any(vt == v for v, _u, _n in classes):
            continue
        n = int(p[3].split("=")[1])
        if n > SLOT and slot(vt, SLOT) in updates:
            nm, bs = bases(vt)
            need(nm == BASE_CLASS, "update %X is also in %s's vtable %X" % (slot(vt, SLOT), nm, vt))
    return sha, classes, cited


def render(sha, classes, cited):
    out = []
    w = out.append
    w("// Generated by tools/gen_enemy_watch.py -- do not edit by hand.")
    w("// The enemy watch (enemy_watch_runtime.h): every class whose RTTI lists cEm as a")
    w("// base, and the instructions that show the cEm fields the watch reads.")
    w("#pragma once")
    w("#include <stdint.h>")
    w("")
    w('#define ENEMY_WATCH_MAIN_SHA1 "%s"' % sha)
    w("static const uint32_t kEwSlotOff = 0x%X;  // vtable slot %d, the update" % (SLOT * 8, SLOT))
    w("static const uint32_t kEwHp = 0xE44, kEwState = 0xE34, kEwFlags = 0xE72, kEwInvuln = 0xE76;")
    w("static const uint32_t kEwPosPtr = 0xA8, kEwRot = 0xB0, kEwVy = 0xE54;")
    w("")
    w("// Checked byte for byte before any slot is written.")
    w("struct EwEvidence { uint32_t rva; uint8_t len; uint8_t bytes[15]; };")
    w("static const EwEvidence kEwEvidence[] = {")
    for a in sorted(cited):
        b = cited[a]
        w("    {0x%X, %d, {%s}}," % (a, len(b), ", ".join("0x%02X" % x for x in b)))
    w("};")
    w("")
    w("struct EwClass { uint32_t vtable; uint32_t update; char name[12]; };")
    w("static const EwClass kEwClasses[] = {")
    for vt, upd, nm in classes:
        w('    {0x%X, 0x%X, "%s"},' % (vt, upd, nm))
    w("};")
    w("static const int kEwClassCount = %d;" % len(classes))
    w("static const int kEwUpdateCount = %d;  // distinct update functions" % len({u for _v, u, _n in classes}))
    return "\n".join(out) + "\n"


def main():
    try:
        sha, classes, cited = build()
    except Fail as e:
        print("FAILED: %s" % e)
        return 1
    text = render(sha, classes, cited)
    if "--check" in sys.argv:
        cur = open(OUT_H).read() if os.path.exists(OUT_H) else ""
        if cur != text:
            print("FAILED: src/enemy_watch.h is not what the generator writes")
            return 1
        print("enemy_watch.h up to date: %d classes, %d updates, %d instructions cited" % (
            len(classes), len({u for _v, u, _n in classes}), len(cited)))
        return 0
    open(OUT_H, "w", newline="\n").write(text)
    print("wrote %s: %d classes, %d updates, %d instructions cited" % (
        OUT_H, len(classes), len({u for _v, u, _n in classes}), len(cited)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
