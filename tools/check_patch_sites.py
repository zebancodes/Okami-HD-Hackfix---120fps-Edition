#!/usr/bin/env python3
"""Verify every generated patch table against the shipped main.dll.

The patch rewrites 1435 sites: 1425 in the eight generated tables plus the ten
input windows that live in the patch source. Each generator checks what
it can see, but three things can only be checked once all the tables exist
together, and all three would be a crash rather than a wrong number:

  1. every `orig` byte string is still exactly what the game ships, so a
     mismatched build is refused rather than corrupted;
  2. no two patched ranges overlap, so one family's 5-byte detour cannot land
     inside another family's instruction;
  3. no computed branch destination lands *inside* a detour. Direct branches
     the generators can see for themselves, but this build dispatches its state
     machines through image-base-relative tables:

         lea    r14, [rip - 0x3af10d]                   ; r14 = image base
         movzx  eax, byte ptr [r14 + rax + 0x3AF840]    ; byte index table
         mov    ecx, dword ptr [r14 + rax*4 + 0x3AF79C] ; dword table of RVAs
         add    rcx, r14
         jmp    rcx

     and those tables live in .text, holding absolute RVAs. A destination that
     is exactly a patched site is fine -- the jump enters the stub at its first
     byte -- but one that lands part-way through a relocated instruction would
     jump into the middle of a `jmp rel32`.

A fourth is not a crash but a watch that never starts: the enemy and brush
watches check stock bytes before they start, so one whose evidence lies on
patched bytes must install before the patches (in watcherThread's order).

Exits non-zero if anything fails.

    python tools/check_patch_sites.py
"""
import os
import re
import struct
import sys

try:
    import pefile
    import capstone
except ImportError:
    sys.exit("needs pefile and capstone: pip install pefile capstone")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402

BASE_IMAGE = 0x180000000
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "src"))

# families whose patch rewrites code (so a branch must not land inside them),
# against families that only rewrite a displacement or one immediate byte
DETOUR = {"action_timers.h", "memory_timers.h", "lea_timers.h",
          "launch_velocities.h"}
INPLACE = {"phase_steps.h", "decay_factors.h", "frame_gates.h", "frame_phases.h"}
TABLES = sorted(DETOUR | INPLACE)

ENTRY = re.compile(
    r"\{0x([0-9A-F]+),\s*(?:0x[0-9A-F]+|\d+)(?:,\s*(?:0x[0-9A-F]+|\d+))*,\s*\{([^}]*)\}\}")

# The two mode-byte families do not fit ENTRY: ModeSelect carries nothing but an
# rva and its bytes, and ModeMult carries a resume address and a shape after the
# rva and a description string after the bytes. They matter here for the same
# reason as everything else -- ModeMult displaces real instructions, so nothing
# may branch into one.
MODE_SELECT = re.compile(r"\{0x([0-9A-F]+), \{([^}]*)\}\}")
MODE_MULT = re.compile(
    r"\{0x([0-9A-F]+), 0x[0-9A-F]+, 0x[0-9A-F]+, (\d+), \d+, \{([^}]*)\}")


def read_mode_tables(img, out):
    """mode_constants.h selects (in place) and mode_multipliers.h (detours)."""
    for fn, rx, detour in (("mode_constants.h", MODE_SELECT, False),
                           ("mode_multipliers.h", MODE_MULT, True)):
        path = os.path.join(SRC, fn)
        if not os.path.exists(path):
            print("  missing %s (run its generator first)" % fn)
            continue
        n = 0
        for ln in open(path):
            g = rx.search(ln)
            if not g:
                continue
            rva = int(g.group(1), 16)
            if detour:
                length = int(g.group(2))
                raw = bytes(int(b, 16) for b in g.group(3).split(","))[:length]
            else:
                raw = bytes(int(b, 16) for b in g.group(2).split(","))
                length = len(raw)
            out[rva] = (fn, length, raw)
            n += 1
            if detour:
                DETOUR.add(fn)
            else:
                INPLACE.add(fn)
        print("  %-22s %4d entries" % (fn, n))
    return out
TBL = re.compile(r"^(\w+), dword ptr \[(\w+) \+ (\w+)\*4 \+ (0x[0-9a-f]+)\]$")

# the ten doubly-compensated input windows have no generated table -- they live
# in the patch source as kInputWindowRvas, so read them from there rather than
# keeping a second copy of the list
PROXY = os.path.normpath(os.path.join(SRC, "dinput8_proxy.cpp"))
INPUT_WINDOW = re.compile(
    r"kInputWindowRvas\[\] = \{(.*?)\};", re.S)
INPUT_WINDOW_ORIG = b"\xD3\xE3"  # shl ebx, cl


# The scale detours have no generated table either -- they are single sites
# named in the patch source, each displacing 8 bytes for a 5-byte jump. They
# were outside this checker until a new pair of them was added, which is exactly
# the kind of thing it exists to catch, so read them from the source too.
SCALE_DETOURS = (
    ("kRunPatchRva", "kRunOrig"),
    ("kJumpSiteRva", "kJumpOrig"),
    ("kJumpPickRva", "kJumpPickOrig"),
    ("kHarnessHookRva", "kHarnessHookOrig"),
    ("kTurnRva", "kTurnOrig"),
)
SCALE_ARRAYS = (
    ("kAnimSites", "kAnimOrig"),
    ("kSlopeSites", "kSlopeOrig"),
)
# arrays whose sites each have their own orig row, indexed in step
SCALE_ROW_ARRAYS = (
    ("kAirGateSites", "kAirGateOrig"),
    ("kAirAccelSites", "kAirAccelOrig"),
    ("kSwimAccelSites", "kSwimAccelOrig"),
    ("kStickDriftSites", "kStickDriftOrig"),
    ("kDrawDistanceSites", "kDrawDistanceOrig"),
)


def _orig_bytes(src, name):
    g = re.search(r"%s\[\d*\] = \{([^}]*)\}" % name, src)
    if not g:
        return None
    return bytes(int(b, 16) for b in re.findall(r"0x([0-9A-Fa-f]{2})", g.group(1)))


def _orig_rows(src, name):
    """[bytes] for a `name[][N] = {{..},{..}}` table, one row per site."""
    g = re.search(r"%s\[\]\[\d+\] = \{(.*?)\};" % name, src, re.S)
    if not g:
        return []
    return [bytes(int(b, 16) for b in re.findall(r"0x([0-9A-Fa-f]{2})", row))
            for row in re.findall(r"\{([^}]*)\}", g.group(1))]


def rip_relative(raw):
    """True if this instruction addresses memory relative to rip.

    installScaleDetour copies the displaced instruction into a code cave at an
    address chosen at runtime, so a rip-relative displacement points somewhere
    else once it moves. kAirAccelOrig shipped with exactly this bug: it read an
    arbitrary float instead of the time scale, and the airborne acceleration
    fix silently did nothing but corrupt the value. copyDisplaced now rewrites
    the displacement; this check makes sure it still exists.
    """
    i = 0
    while i < len(raw) and raw[i] in (0xF2, 0xF3, 0x66):
        i += 1
    if i < len(raw) and 0x40 <= raw[i] <= 0x4F:
        i += 1
    if i < len(raw) and raw[i] == 0x0F:
        i += 1
    i += 1  # opcode
    if i >= len(raw):
        return False
    return (raw[i] >> 6) == 0 and (raw[i] & 7) == 5


def scale_detours():
    """[(rva, orig_bytes, label)] for the hand-coded single-site detours."""
    try:
        src = open(PROXY, encoding="utf-8").read()
    except OSError:
        return []
    out = []
    for rva_name, orig_name in SCALE_DETOURS:
        raw = _orig_bytes(src, orig_name)
        g = re.search(r"%s\s*=\s*0x([0-9A-Fa-f]+)" % rva_name, src)
        if raw and g:
            out.append((int(g.group(1), 16), raw, rva_name))
    for arr_name, orig_name in SCALE_ARRAYS:
        raw = _orig_bytes(src, orig_name)
        g = re.search(r"%s\[\]\[2\] = \{(.*?)\};" % arr_name, src, re.S)
        if raw and g:
            for a, _b in re.findall(r"\{0x([0-9A-Fa-f]+), 0x([0-9A-Fa-f]+)\}", g.group(1)):
                out.append((int(a, 16), raw, arr_name))
    for arr_name, orig_name in SCALE_ROW_ARRAYS:
        rows = _orig_rows(src, orig_name)
        g = re.search(r"%s\[\]\[2\] = \{(.*?)\};" % arr_name, src, re.S)
        if rows and g:
            pairs = re.findall(r"\{0x([0-9A-Fa-f]+), 0x([0-9A-Fa-f]+)\}", g.group(1))
            for i, (a, _b) in enumerate(pairs):
                if i < len(rows):
                    out.append((int(a, 16), rows[i], arr_name))
    return out


# src/hoisted_decay.h has a shape of its own: the load is verified and never
# written, and what gets replaced is the multiply plus the store after it, as
# one range. Both halves are checked -- the load because the whole argument
# that the register holds k rests on it.
HOIST_H = os.path.normpath(os.path.join(SRC, "hoisted_decay.h"))
HOIST_ENTRY = re.compile(
    r"\{0x([0-9A-Fa-f]+),\s*\{([^}]*)\},\s*(\d+),\s*"
    r"0x([0-9A-Fa-f]+),\s*\{([^}]*)\},\s*(\d+),\s*"
    r"\{([^}]*)\},\s*(\d+),", re.S)


def _bytes_of(text, n):
    return bytes(int(b, 16) for b in re.findall(r"0x([0-9A-Fa-f]{2})", text))[:n]


def hoisted_decay():
    """(patched ranges, load sites to verify)"""
    try:
        h = open(HOIST_H, encoding="utf-8").read()
    except OSError:
        return [], []
    patched, loads = [], []
    for m in HOIST_ENTRY.finditer(h):
        load_rva = int(m.group(1), 16)
        load_raw = _bytes_of(m.group(2), int(m.group(3)))
        mul_rva = int(m.group(4), 16)
        mul_raw = _bytes_of(m.group(5), int(m.group(6)))
        store_raw = _bytes_of(m.group(7), int(m.group(8)))
        patched.append((mul_rva, mul_raw + store_raw, "hoisted_decay.h"))
        loads.append((load_rva, load_raw))
    return patched, loads


# src/shadow_mode.h: the retargeted mode-byte instructions change only their
# displacement, but the whole instruction is claimed here, since its immediate
# byte sits after the displacement; the memset return windows are detours.
SHADOW_H = "shadow_mode.h"
SHADOW_WINDOW = "shadow_mode.h window"


def shadow_mode():
    """[(rva, orig bytes, label)] for the shadow mode sites and windows."""
    if not os.path.exists(os.path.join(SRC, SHADOW_H)):
        print("  missing %s (run tools/gen_shadow_mode.py)" % SHADOW_H)
        return []
    import verify_shadow_mode
    hdr = verify_shadow_mode.parse_header()
    return ([(s["rva"], s["orig"], SHADOW_H) for s in hdr["sites"]]
            + [(w["rva"], w["orig"], SHADOW_WINDOW) for w in hdr["windows"]])


# src/frame_clocks.h: the reads change only their displacement; the gates only
# their mask byte (the last byte, as frame_gates.h); the hook on flower_tick's
# increment is a detour, so nothing may branch into it.
CLOCKS_H = "frame_clocks.h"
CLOCKS_GATE = "frame_clocks.h gate"
CLOCKS_TICK = "frame_clocks.h tick"


def frame_clocks():
    """[(rva, orig bytes, label)] for the frame-counter clock reads, gates and hook."""
    if not os.path.exists(os.path.join(SRC, CLOCKS_H)):
        print("  missing %s (run tools/gen_frame_clocks.py)" % CLOCKS_H)
        return []
    import verify_frame_clocks
    hdr = verify_frame_clocks.parse_header()
    return ([(r["rva"], r["orig"], CLOCKS_H) for r in hdr["reads"]]
            + [(g["rva"], g["orig"], CLOCKS_GATE) for g in hdr["gates"]]
            + [(hdr["tick"], hdr["tick_orig"], CLOCKS_TICK)])


# src/turn_callers.h: the table reads change only their displacement, the
# bypassed calls only their rel32 -- both the last four bytes, as the default
# span below assumes.
TURN_H = "turn_callers.h"


def turn_callers():
    """[(rva, orig bytes, label)] for the turn callers' table reads and bypasses."""
    if not os.path.exists(os.path.join(SRC, TURN_H)):
        print("  missing %s (run tools/gen_turn_callers.py)" % TURN_H)
        return []
    import verify_turn_callers
    _entries, reads, bypass, _sha = verify_turn_callers.parse_header()
    return ([(r["rva"], r["orig"], TURN_H) for r in reads]
            + [(b["rva"], b["orig"], TURN_H) for b in bypass])


def input_windows():
    try:
        g = INPUT_WINDOW.search(open(PROXY, encoding="utf-8").read())
    except OSError:
        return []
    if not g:
        return []
    return [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)", g.group(1))]


def load_image():
    pe = pefile.PE(os.path.join(GAME, "main.dll"), fast_load=True)
    img = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    return img, text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize


def disassemble(img, lo, hi):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = bytes(img[lo:hi])
    insns, off = [], 0
    while off < len(code):
        found = False
        for i in md.disasm(code[off:off + 65536], BASE_IMAGE + lo + off):
            insns.append((i.address - BASE_IMAGE, i.mnemonic, i.op_str, i.size))
            off = i.address - BASE_IMAGE - lo + i.size
            found = True
        if not found:
            off += 1
    return insns


def integer_skips():
    """Whole F1 relocation windows, including their padding instructions."""
    if not os.path.exists(os.path.join(SRC, "integer_skips.h")):
        return []
    import verify_integer_skips
    hdr = verify_integer_skips.parse_header()
    return [(rva, hdr["orig"][orig:orig + n], "integer_skips.h")
            for rva, _stub, orig, n in hdr["windows"]]


def day_clock():
    """The day/night clock's two tail jumps and its requested jump's call, each
    retargeted whole (5 bytes)."""
    if not os.path.exists(os.path.join(SRC, "day_clock.h")):
        print("  missing day_clock.h (run tools/gen_day_clock.py)")
        return []
    import verify_day_clock
    hdr = verify_day_clock.parse_header()
    return [(rva, hdr["orig"][5 * i:5 * i + 5], "day_clock.h")
            for i, (rva, _t, _s, _r) in enumerate(hdr["sites"])]


def menu_transitions():
    """M2's menu transitions: whole relocation windows, and the literal sites
    whose 4-byte displacement is pointed at the family's pool."""
    if not os.path.exists(os.path.join(SRC, "menu_transitions.h")):
        print("  missing menu_transitions.h (run tools/gen_menu_transitions.py)")
        return [], []
    import verify_menu_transitions
    hdr = verify_menu_transitions.parse_header()
    windows = [(rva, hdr["orig"][orig:orig + n], "menu_transitions.h")
               for rva, _stub, orig, n in hdr["windows"]]
    literals = [(rva, raw, MENU_LITERAL)
                for (rva, _c, _s, _k), raw in zip(hdr["literals"], hdr["lit_orig"])]
    return windows, literals


MENU_LITERAL = "menu_transitions.h literal"


def world_anims():
    """The world animations: whole relocation windows, the turn steps' calls
    retargeted at their stubs, and the literals whose 4-byte displacement is
    pointed at the family's pool."""
    if not os.path.exists(os.path.join(SRC, "world_anims.h")):
        print("  missing world_anims.h (run tools/gen_world_anims.py)")
        return [], []
    import verify_world_anims
    hdr = verify_world_anims.parse_header()
    windows = [(rva, hdr["orig"][orig:orig + n], "world_anims.h")
               for rva, _stub, orig, n in hdr["windows"]]
    # a turn step's call, whose rel32 is retargeted at its stub: the whole call
    windows += [(rva, bytes([op]) + struct.pack("<i", target - (rva + 5)), WORLD_CALL)
                for (rva, _stub, target), op in zip(hdr["calls"],
                                                     verify_world_anims.call_ops(hdr))]
    literals = [(rva, raw, WORLD_LITERAL)
                for (rva, _c, _s, _k, _g), raw in zip(hdr["literals"], hdr["lit_orig"])]
    return windows, literals


WORLD_LITERAL = "world_anims.h literal"
WORLD_CALL = "world_anims.h call"


TASK_WINDOW = "task_waits.h window"


def task_waits():
    """The task waits' calls (and tail jumps) of main+4567C0, whose rel32 is
    retargeted at the family's stub: the whole 5-byte instruction; flower_tick's
    call of the task manager, retargeted the same way; and the skip check's two
    7-byte reads, each replaced by a jmp (TASK_WINDOW, a detour)."""
    path = os.path.join(SRC, "task_waits.h")
    if not os.path.exists(path):
        print("  missing task_waits.h (run tools/gen_task_waits.py)")
        return []
    text = open(path, encoding="utf-8").read()
    body = re.search(r"kTaskWaitSites\[\]\s*=\s*\{(.*?)\n\};", text, re.S).group(1)
    out = []
    for rva, rel, _ticks, op, _entry in re.findall(
            r"\{0x([0-9A-F]+), (-?\d+), (\d+), 0x([0-9A-F]{2}), (\d)\}", body):
        out.append((int(rva, 16), bytes([int(op, 16)]) + struct.pack("<i", int(rel)),
                    "task_waits.h"))
    if not out:
        raise ValueError("task_waits.h: no calls parsed; the table's layout changed")
    call = int(re.search(r"kTaskWaitTickCallRva\s*=\s*0x([0-9A-F]+)", text).group(1), 16)
    rel = int(re.search(r"kTaskWaitTickCallRel\s*=\s*(-?\d+)", text).group(1))
    out.append((call, b"\xE8" + struct.pack("<i", rel), "task_waits.h"))
    body = re.search(r"kTaskWaitWindows\[\]\s*=\s*\{(.*?)\n\};", text, re.S).group(1)
    for rva, orig in re.findall(r"\{0x([0-9A-F]+), \{([0-9A-Fx, ]+)\}, 0x[0-9A-F]+\}", body):
        out.append((int(rva, 16), bytes(int(x, 16) for x in orig.split(",")), TASK_WINDOW))
    return out


def read_tables(img):
    """{rva: (file, patched length)} -- trailing zero padding trimmed."""
    out = {}
    read_mode_tables(img, out)
    for fn in TABLES:
        path = os.path.join(SRC, fn)
        if not os.path.exists(path):
            print("  missing %s (run its generator first)" % fn)
            continue
        n = 0
        for ln in open(path):
            g = ENTRY.search(ln)
            if not g:
                continue
            rva = int(g.group(1), 16)
            raw = bytes(int(b, 16) for b in g.group(2).split(","))
            L = len(raw)
            while L > 0 and raw[L - 1] == 0 and bytes(img[rva:rva + L]) != raw[:L]:
                L -= 1
            out[rva] = (fn, L, raw[:L])
            n += 1
        print("  %-22s %4d entries" % (fn, n))
    return out


def switch_destinations(img, insns, lo, hi):
    tables = set()
    for k, (a, mn, o, s) in enumerate(insns):
        if mn != "mov":
            continue
        g = TBL.match(o)
        if not g:
            continue
        tbl = int(g.group(4), 16)
        if not (lo <= tbl < hi):
            continue
        for j in range(k + 1, min(k + 6, len(insns))):
            m2, o2 = insns[j][1], insns[j][2]
            if m2 == "jmp" and "ptr" not in o2 and not o2.startswith("0x"):
                tables.add(tbl)
                break
    dests = set()
    for tbl in tables:
        for i in range(4096):
            off = tbl + i * 4
            if off + 4 > len(img):
                break
            t = struct.unpack_from("<I", img, off)[0]
            if not (lo <= t < hi):
                break
            dests.add(t)
    return tables, dests


def all_sites(img):
    """Every family's patched sites: rva -> (family, length, original bytes),
    the scale detours and the hoisted decays' loads (tools/coverage_report.py
    reads the same)."""
    print("tables:")
    sites = read_tables(img)
    if not sites:
        sys.exit("no tables found under src/")
    windows = input_windows()
    print("  %-22s %4d entries (from dinput8_proxy.cpp)"
          % ("kInputWindowRvas", len(windows)))
    for rva in windows:
        sites[rva] = ("input windows", 2, INPUT_WINDOW_ORIG)
    detours = scale_detours()
    print("  %-22s %4d entries (from dinput8_proxy.cpp)"
          % ("scale detours", len(detours)))
    for rva, raw, label in detours:
        sites[rva] = (label, len(raw), raw)
        DETOUR.add(label)
    hoist, hoist_loads = hoisted_decay()
    print("  %-22s %4d entries (from hoisted_decay.h)"
          % ("hoisted decays", len(hoist)))
    for rva, raw, label in hoist:
        sites[rva] = (label, len(raw), raw)
        DETOUR.add(label)
    shadow = shadow_mode()
    print("  %-22s %4d entries (%d memset window(s))"
          % (SHADOW_H, len(shadow), sum(1 for s in shadow if s[2] == SHADOW_WINDOW)))
    for rva, raw, label in shadow:
        sites[rva] = (label, len(raw), raw)
    DETOUR.add(SHADOW_WINDOW)
    clocks = frame_clocks()
    print("  %-22s %4d entries (%d reads, %d gates, the tick hook)"
          % (CLOCKS_H, len(clocks), sum(1 for c in clocks if c[2] == CLOCKS_H),
             sum(1 for c in clocks if c[2] == CLOCKS_GATE)))
    for rva, raw, label in clocks:
        sites[rva] = (label, len(raw), raw)
    DETOUR.add(CLOCKS_TICK)
    turns = turn_callers()
    print("  %-22s %4d entries (table reads and bypassed calls)" % (TURN_H, len(turns)))
    for rva, raw, label in turns:
        sites[rva] = (label, len(raw), raw)
    integers = integer_skips()
    print("  %-22s %4d entries (whole relocation windows)" % ("integer_skips.h", len(integers)))
    for rva, raw, label in integers:
        if rva in sites:
            raise ValueError("integer window duplicates another family at main+%X" % rva)
        sites[rva] = (label, len(raw), raw)
    DETOUR.add("integer_skips.h")
    days = day_clock()
    print("  %-22s %4d entries (the workers' tail jumps, the requested jump's call)"
          % ("day_clock.h", len(days)))
    for rva, raw, label in days:
        if rva in sites:
            raise ValueError("day clock jump duplicates another family at main+%X" % rva)
        sites[rva] = (label, len(raw), raw)
    DETOUR.add("day_clock.h")
    menus, menu_literals = menu_transitions()
    print("  %-22s %4d entries (%d relocation windows, %d literal retargets)"
          % ("menu_transitions.h", len(menus) + len(menu_literals), len(menus),
             len(menu_literals)))
    for rva, raw, label in menus + menu_literals:
        if rva in sites:
            raise ValueError("menu transition site duplicates another family at main+%X" % rva)
        sites[rva] = (label, len(raw), raw)
    DETOUR.add("menu_transitions.h")
    worlds, world_literals = world_anims()
    ncalls = sum(1 for w in worlds if w[2] == WORLD_CALL)
    print("  %-22s %4d entries (%d relocation windows, %d calls retargeted, %d literal "
          "retargets)" % ("world_anims.h", len(worlds) + len(world_literals),
                          len(worlds) - ncalls, ncalls, len(world_literals)))
    for rva, raw, label in worlds + world_literals:
        if rva in sites:
            raise ValueError("world animation site duplicates another family at main+%X" % rva)
        sites[rva] = (label, len(raw), raw)
    DETOUR.add("world_anims.h")
    waits = task_waits()
    print("  %-22s %4d entries (calls of the task wait, their rel32 retargeted)"
          % ("task_waits.h", len(waits)))
    for rva, raw, label in waits:
        if rva in sites:
            raise ValueError("task wait call duplicates another family at main+%X" % rva)
        sites[rva] = (label, len(raw), raw)
    DETOUR.add(TASK_WINDOW)
    detours = detours + [c for c in clocks if c[2] == CLOCKS_TICK]
    return sites, detours, hoist_loads


def main():
    img, lo, hi = load_image()
    sites, detours, hoist_loads = all_sites(img)
    fails = 0

    # ---- 0a. the loads the hoisted decays reason from --------------------
    # These are never written, but if one has moved then the register no longer
    # provably holds k and the multiply must not be rewritten either.
    img0, _lo0, _hi0 = img, 0, 0
    bad_loads = [rva for rva, raw in hoist_loads
                 if bytes(img0[rva:rva + len(raw)]) != raw]
    print("   hoisted-decay loads: %d verified%s"
          % (len(hoist_loads) - len(bad_loads),
             "" if not bad_loads else ", %d NO LONGER MATCH" % len(bad_loads)))
    for rva in bad_loads:
        print("     main+%06X" % rva)
    fails += len(bad_loads)

    # ---- 0. relocatability of every displaced instruction -----------------
    src = open(PROXY, encoding="utf-8").read()
    riprel = [(rva, label) for rva, raw, label in detours if rip_relative(raw)]
    has_fixup = "copyDisplaced" in src
    print("\n0. %d of %d displaced instructions are rip-relative; "
          "displacement fixup %s"
          % (len(riprel), len(detours), "present" if has_fixup else "MISSING"))
    for rva, label in sorted(riprel):
        print("   %06X in %s" % (rva, label))
    if riprel and not has_fixup:
        print("   these would read from the wrong address once moved into the cave")
        fails += len(riprel)

    # the hand-assembled stubs themselves: do they decode to what was meant?
    try:
        import verify_stubs
        stub_problems = (verify_stubs.check_harness_stub(src, False)
                         + verify_stubs.check_frame_clock_stub(src, False)
                         + verify_stubs.check_mulss_encoding(False)
                         + verify_stubs.check_jump_pick(src, False))
        # the turn-rate stub is emitted byte by byte with four branch fixups
        # and two rip displacements, one of which was wrong the first time
        import subprocess
        turn = subprocess.run([sys.executable,
                               os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "verify_turn_stub.py")],
                              capture_output=True, text=True)
        if turn.returncode != 0:
            stub_problems.append("turn stub: " + (turn.stdout or turn.stderr).strip()
                                 .splitlines()[-1])
    except Exception as exc:  # the checker must not die on a tooling problem
        stub_problems = ["verify_stubs failed: %s" % exc]
    print("   emitted stubs: %s"
          % ("decode clean (push/pop pairing, call alignment, net rsp 0)"
             if not stub_problems else "%d PROBLEM(S)" % len(stub_problems)))
    for sp in stub_problems:
        print("     %s" % sp)
    fails += len(stub_problems)

    # ---- 1. orig bytes ----------------------------------------------------
    bad = [rva for rva, (fn, L, raw) in sites.items()
           if bytes(img[rva:rva + L]) != raw]
    print("\n1. %d sites, %d whose bytes no longer match this build"
          % (len(sites), len(bad)))
    for rva in sorted(bad)[:10]:
        print("   %06X in %s" % (rva, sites[rva][0]))
    fails += len(bad)

    # ---- 2. overlap -------------------------------------------------------
    spans = []
    for rva, (fn, L, raw) in sites.items():
        if fn in DETOUR:
            spans.append((rva, rva + max(L, 5), fn))
        elif fn in ("input windows", SHADOW_H):
            spans.append((rva, rva + L, fn))               # nops; a whole instruction
        elif fn in ("frame_gates.h", CLOCKS_GATE):
            spans.append((rva + L - 1, rva + L, fn))       # the mask byte
        else:
            spans.append((rva + L - 4, rva + L, fn))       # the displacement
    spans.sort()
    clashes = [(spans[i], spans[i + 1]) for i in range(len(spans) - 1)
               if spans[i + 1][0] < spans[i][1]]
    print("2. %d overlapping patch ranges" % len(clashes))
    for a, b in clashes[:10]:
        print("   %s %06X-%06X vs %s %06X-%06X"
              % (a[2], a[0], a[1], b[2], b[0], b[1]))
    fails += len(clashes)

    # ---- 3. computed branch destinations ----------------------------------
    insns = disassemble(img, lo, hi)
    tables, dests = switch_destinations(img, insns, lo, hi)
    interior = {}
    for rva, (fn, L, raw) in sites.items():
        if fn not in DETOUR:
            continue
        for off in range(1, max(L, 5)):
            interior[rva + off] = (fn, rva)
    landed = sorted(t for t in dests if t in interior)
    exact = sorted(t for t in dests if t in sites)
    print("3. %d switch tables, %d destinations; %d land inside a detour, "
          "%d land exactly on one (harmless)"
          % (len(tables), len(dests), len(landed), len(exact)))
    for t in landed[:10]:
        fn, rva = interior[t]
        print("   %06X is inside %s site %06X" % (t, fn, rva))
    fails += len(landed)

    # ---- 4. the watches' evidence ------------------------------------------
    # A watch checks stock bytes byte for byte before it starts. Where those
    # bytes are ones a family rewrites, the watch must install before any
    # family does: the enemy watch's main+238B5B is an action timer site, and
    # installed last it never started in the game (2026-09-25).
    watcher = src[src.index("static DWORD WINAPI watcherThread"):]
    first_patch = watcher.index("installTaskGate();")
    evidence_rx = re.compile(r"\{0x([0-9A-F]+),\s*(\d+),\s*\{([^}]*)\}\}")
    watch_fails = 0
    print("4. the watches' evidence against the patched ranges:")
    for header, table, install in (("enemy_watch.h", "kEwEvidence", "installEnemyWatch();"),
                                   ("brush_watch.h", "kBrushEvidence", "installBrushWatch();")):
        text = open(os.path.join(SRC, header)).read()
        body = text[text.index(table + "[] = {"):]
        body = body[:body.index("\n};")]
        entries = [(int(g.group(1), 16), int(g.group(2))) for g in evidence_rx.finditer(body)]
        clash = [(rva, n, s) for rva, n in entries for s in spans if rva < s[1] and s[0] < rva + n]
        at = watcher.index(install)
        early = at < first_patch
        bad = bool(clash) and not early
        print("   %s %-14s %3d entries, %d on patched bytes; installs %s the patches"
              % ("FAIL" if bad else "ok  ", header, len(entries), len(clash),
                 "before" if early else "after"))
        for rva, n, s in clash[:5]:
            print("        main+%06X+%d on %s %06X-%06X" % (rva, n, s[2], s[0], s[1]))
        watch_fails += bad
    fails += watch_fails

    print("\n%s" % ("FAILED: %d problems" % fails if fails else "all checks passed"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
