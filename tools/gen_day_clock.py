#!/usr/bin/env python3
"""Generate src/day_clock.h: the day/night clock at the stock tick rate.

The world's time of day is one dword, main+B20830, in units of which a day is
1 800 000 (the lighting keys its five palettes and their 90 000-unit
crossfades off `clock % 1800000`, main+4AC680). Nothing reads wall-clock time:
the day/night controller (a global object, main+B6A9B0) is updated once per
tick from the dispatcher (main+4BA500 -> thunk 4AF770 -> 4AF780), and that
update ends in one of two tail jumps:

  * the advance (4AF800): after its gates, `delay ? delay-- : clock += 100`.
    100 a tick is 18 000 ticks a day, 10 minutes at the stock 30 Hz -- and
    2.5 minutes at 120, 5 at 60: nothing in it depends on the mode byte;
  * the transition (4AF910), the scripted fast-forward (the sky change of a
    brush technique or an event): `delay ? delay-- :
    clock += (target - clock) / steps; steps--` -- a per-tick count as well.

Everything else the update does is kept every tick: it first records the
clock as it was (+8, and +4 = that % day), and the event code downstream
(4AF610 and friends: "did the clock cross X since the last update") compares
against that record. So the two workers are gated, not the update: on a tick
that is not a stock tick (frameCounter & mask != 0) the stub returns straight
to the dispatcher, exactly as if the worker had found nothing to do, and the
next update's record makes the crossing visible on exactly one tick. The
delay counts in stock ticks, the transition in stock steps, and the advance
is 100 per stock tick: the stock game, in wall-clock time.

A third path is left ungated: a time the game requests (+0x30, applied by
the update itself before either tail jump). Scripted time-lapses request one
on every pass of a loop, lerping on the event player's playhead or on their
own count. The update's call to the setter is retargeted at a stub that only
counts the requests applied and jumps on, so the field watch can time each
lapse; the generator also proves the lapse loops and the event player's
playhead, speed and done bit that the watch reads (find_request, find_lapses,
find_event_player).

Only the three rel32s change. The generator proves from the binary that:

  * the adder (`clock += edx`, with the day length and the day counter) is
    unique, and its only two callers are the two workers, identified by
    shape (`mov edx, 100` / `idiv` over the step count);
  * each worker is referenced exactly once in the whole image: by its tail
    jump in the update, whose frame is already torn down (`add rsp, 0x20;
    pop rbx`), so rsp points at the dispatcher's return address and a bare
    `ret` is the worker returning at once;
  * no flag is read before it is written, on both sides of the stub: in the
    worker's entry and after the dispatcher's call;
  * the update is reached only through the thunk, and the thunk only from the
    dispatcher, with rcx = the controller.

    .venv/Scripts/python tools/gen_day_clock.py
"""
import csv
import hashlib
import os
import re
import struct
import sys

import capstone
from capstone import x86_const as X
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402
import xrefs  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT_H = os.path.join(ROOT, "src", "day_clock.h")
OUT_CSV = os.path.join(ROOT, "docs", "animation", "day_clock.csv")
CLOCKS_H = os.path.join(ROOT, "src", "frame_clocks.h")
SHADOW_H = os.path.join(ROOT, "src", "shadow_mode.h")
BASE = 0x180000000
DAY_UNITS = 1800000

# The pool: [0] the mask byte (0 / 1 / 3), [COUNTER_OFFSET + 8*i] two dwords
# per site -- how often its stub was entered and how often it let the worker
# run; for the requested jump, how many requests the update applied -- for
# the in-game check; one stub per site from CODE_OFFSET.
MASK_OFFSET, COUNTER_OFFSET, CODE_OFFSET, STUB_SIZE, POOL_SIZE = 0, 0x10, 0x40, 0x40, 0x100


class Fail(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Fail(msg)


def load():
    path = os.path.join(GAME, "main.dll")
    raw = open(path, "rb").read()
    pe = pefile.PE(data=raw, fast_load=False)
    need(pe.OPTIONAL_HEADER.ImageBase == BASE, "unexpected image base")
    img = bytes(pe.get_memory_mapped_image())
    text = [s for s in pe.sections if s.Name.rstrip(b"\x00") == b".text"][0]
    funcs = sorted((e.struct.BeginAddress, e.struct.EndAddress)
                   for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    return hashlib.sha1(raw).hexdigest(), pe, img, (text.VirtualAddress,
                                                    text.VirtualAddress + text.Misc_VirtualSize), funcs


def function_of(funcs, rva):
    for lo, hi in funcs:
        if lo <= rva < hi:
            return lo, hi
    return None


def decode(md, img, lo, hi):
    return list(md.disasm(img[lo:hi], BASE + lo))


def rip_target(ins, op):
    return ins.address + ins.size + op.mem.disp - BASE


def find_adder(md, img, text):
    """`mov r8d, [rip+clock]; add r8d, edx` ... `mov [rip+clock], r8d`, with
    the day length and a word counter bumped on a day boundary."""
    lo, hi = text
    pat = re.compile(re.escape(b"\x44\x8B\x05") + b"....", re.S)
    hits = []
    for m in pat.finditer(img, lo, hi):
        at = m.start()
        if img[at + 7:at + 10] != b"\x44\x03\xC2":  # add r8d, edx
            continue
        insns = []
        for ins in md.disasm(img[at:at + 0x100], BASE + at):
            insns.append(ins)
            if ins.mnemonic == "ret":
                break
        if not insns or insns[-1].mnemonic != "ret":
            continue
        clock = rip_target(insns[0], insns[0].operands[1])
        stores = [i for i in insns if i.mnemonic == "mov" and i.operands[0].type == X.X86_OP_MEM
                  and i.operands[0].mem.base == X.X86_REG_RIP
                  and rip_target(i, i.operands[0]) == clock
                  and i.operands[1].type == X.X86_OP_REG and i.reg_name(i.operands[1].reg) == "r8d"]
        day = [i for i in insns if i.mnemonic == "imul" and len(i.operands) == 3
               and i.operands[2].type == X.X86_OP_IMM and i.operands[2].imm == DAY_UNITS]
        count = [i for i in insns if i.mnemonic == "inc" and i.operands[0].type == X.X86_OP_MEM
                 and i.operands[0].mem.base == X.X86_REG_RIP and i.operands[0].size == 2]
        if stores and day and len(count) == 1:
            hits.append((at, clock, rip_target(count[0], count[0].operands[0]), insns))
    need(len(hits) == 1, "expected one clock adder, found %d" % len(hits))
    return hits[0]


def all_references(insns_all, img, targets):
    """Every direct branch, call or rip-relative lea at one of `targets` (or into
    its first 5 bytes), and every absolute pointer to one."""
    refs = {t: [] for t in targets}
    for a, m, o, s in insns_all:
        r = a - BASE
        t = None
        if (m.startswith("j") or m == "call") and o.startswith("0x"):
            t = int(o, 16) - BASE
        elif m == "lea" and "rip" in o:
            g = xrefs.RIP_RE.search(o)
            if g:
                t = a + s + int(g.group(2), 16) * (1 if g.group(1) == "+" else -1) - BASE
        if t is None:
            continue
        for T in targets:
            if T <= t < T + 5:
                refs[T].append((r, m, t - T))
    for T in targets:
        va = struct.pack("<Q", BASE + T)
        i = img.find(va)
        while i != -1:
            refs[T].append((i, "abs64", 0))
            i = img.find(va, i + 1)
    return refs


def flags_dead_from(md, img, rva, limit=24):
    """True when, walking forward from rva, every flag is written (or the path
    leaves through a call/ret, after which the ABI treats flags as clobbered)
    before any is read."""
    md.detail = True
    for ins in md.disasm(img[rva:rva + 0x80], BASE + rva):
        if limit == 0:
            return False
        limit -= 1
        ef = ins.eflags
        reads = ef & (X.X86_EFLAGS_TEST_OF | X.X86_EFLAGS_TEST_SF | X.X86_EFLAGS_TEST_ZF |
                      X.X86_EFLAGS_TEST_PF | X.X86_EFLAGS_TEST_CF | X.X86_EFLAGS_TEST_AF |
                      X.X86_EFLAGS_TEST_DF)
        if reads or ins.mnemonic in ("pushfq", "pushf", "lahf"):
            return False
        if ins.mnemonic in ("call", "ret"):
            return True
        writes_all = all(ef & w for w in (
            X.X86_EFLAGS_MODIFY_OF | X.X86_EFLAGS_RESET_OF,
            X.X86_EFLAGS_MODIFY_SF, X.X86_EFLAGS_MODIFY_ZF, X.X86_EFLAGS_MODIFY_PF,
            X.X86_EFLAGS_MODIFY_CF | X.X86_EFLAGS_RESET_CF))
        if writes_all:
            return True
        if ins.mnemonic.startswith("j") and ins.mnemonic != "jmp":
            return False
    return False


def classify_worker(md, img, funcs, call_rva, adder):
    fn = function_of(funcs, call_rva)
    need(fn is not None, "adder caller main+%X has no .pdata entry" % call_rva)
    body = decode(md, img, *fn)
    k = [i.address - BASE for i in body].index(call_rva)
    pre, post = body[max(0, k - 8):k], body[k + 1:k + 4]
    facts = {"fn": fn, "call": call_rva}
    # the delay: mov eax, [rbx+D]; test eax, eax; je; dec eax; mov [rbx+D], eax
    for j in range(len(body) - 4):
        a, b, c, d, e = body[j:j + 5]
        if (a.mnemonic == "mov" and a.op_str.startswith("eax, dword ptr [rbx + ")
                and b.mnemonic == "test" and b.op_str == "eax, eax" and c.mnemonic == "je"
                and d.mnemonic == "dec" and d.op_str == "eax" and e.mnemonic == "mov"
                and e.op_str == a.op_str.split(", ", 1)[1] + ", eax"):
            facts["delay"] = a.operands[1].mem.disp
            facts["delay_dec"] = d.address - BASE
    if (len(pre) >= 2 and pre[-1].mnemonic == "mov" and pre[-1].op_str == "rcx, rbx"
            and pre[-2].mnemonic == "mov" and pre[-2].op_str.startswith("edx, 0x")):
        facts["role"] = "advance"
        facts["step"] = pre[-2].operands[1].imm
        facts["step_at"] = pre[-2].address - BASE
    elif (any(i.mnemonic == "idiv" and i.op_str == "ecx" for i in pre)
          and any(i.mnemonic == "movzx" and i.op_str.startswith("ecx, word ptr [rbx + ")
                  for i in pre)):
        cnt = [i for i in pre if i.mnemonic == "movzx"][0].operands[1].mem.disp
        tgt = [i for i in pre if i.mnemonic == "mov" and i.op_str.startswith("eax, dword ptr [rbx + ")]
        dec = [i for i in post if i.mnemonic == "add"
               and i.op_str == "word ptr [rbx + 0x%x], ax" % cnt]
        need(tgt and dec and post[0].mnemonic == "mov" and post[0].op_str == "eax, 0xffff",
             "transition at main+%X lacks target/step-count shape" % call_rva)
        facts.update(role="transition", count=cnt, target=tgt[0].operands[1].mem.disp,
                     count_dec=dec[0].address - BASE)
    else:
        raise Fail("adder caller main+%X is neither shape" % call_rva)
    need("delay" in facts, "%s at main+%X has no delay countdown" % (facts["role"], fn[0]))
    return facts


def find_request(md, img, funcs, ub, clock):
    """The update's requested-jump path, before either tail jump: a time the
    game asked for (+R set, the time at +V) is applied and the update returns.

        cmp byte ptr [rcx + R], 0; je; mov edx, [rcx + V]; call SET; mov byte ptr [rbx + R], 0

    SET stores edx to the clock. Its call is the one call in the update, and
    the only change is its rel32, at a stub that counts and jumps on to SET."""
    calls = [k for k, i in enumerate(ub) if i.mnemonic == "call"]
    need(len(calls) == 1, "the update makes %d calls, want only the requested jump's" % len(calls))
    k = calls[0]
    need(3 <= k < len(ub) - 1, "the update's call has no requested-jump shape around it")
    cmp, je, load, call, clear = ub[k - 3:k + 2]
    mr = re.fullmatch(r"byte ptr \[rcx \+ (0x[0-9a-f]+)\], 0", cmp.op_str)
    mv = re.fullmatch(r"edx, dword ptr \[rcx \+ (0x[0-9a-f]+)\]", load.op_str)
    need(cmp.mnemonic == "cmp" and mr and je.mnemonic == "je" and load.mnemonic == "mov" and mv,
         "the update's call main+%X is not preceded by the request test and load"
         % (call.address - BASE))
    req, value = int(mr.group(1), 16), int(mv.group(1), 16)
    need(clear.mnemonic == "mov" and clear.op_str == "byte ptr [rbx + 0x%x], 0" % req,
         "the request is not cleared after the call")
    at = call.address - BASE
    need(img[at] == 0xE8, "the requested jump's call main+%X is not call rel32" % at)
    setter = call.operands[0].imm - BASE
    # a leaf (no .pdata entry): straight from its entry to its ret
    fn = function_of(funcs, setter)
    need(fn is None or fn[0] == setter, "the setter main+%X is inside a function" % setter)
    body = []
    for i in md.disasm(img[setter:setter + 0x200], BASE + setter):
        body.append(i)
        if i.mnemonic == "ret":
            break
    need(body and body[-1].mnemonic == "ret", "the setter main+%X has no ret" % setter)
    need(any(i.mnemonic == "mov" and i.op_str.endswith(", edx")
             and i.operands[0].type == X.X86_OP_MEM and i.operands[0].mem.base == X.X86_REG_RIP
             and rip_target(i, i.operands[0]) == clock for i in body),
         "the setter main+%X does not store edx to the clock" % setter)
    need(flags_dead_from(md, img, setter), "the setter main+%X reads a flag before writing it" % setter)
    return dict(rva=at, target=setter, role="request", orig=bytes(img[at:at + 5]),
                request=req, value=value)


def find_lapses(insns_all, req, value):
    """Every loop that asks for a new time on each pass (+req = 1, +value =
    eax) and waits in the same body: a scripted time-lapse. Each lerps either
    on a global playhead (`subss xmm, [rip + P]`), leaving when bit 1 of a
    global flags dword is set, or on its own count (`inc r; ...; cmp r, n; jl`).
    Returns the loops and the one playhead and flags globals they share."""
    at = {a: k for k, (a, _m, _o, _s) in enumerate(insns_all)}
    loops = []
    for k, (a, m, o, _s) in enumerate(insns_all):
        if m != "mov" or o != "byte ptr [rbx + 0x%x], 1" % req:
            continue
        back = None
        for j in range(k + 1, min(k + 48, len(insns_all))):
            m2, o2 = insns_all[j][1], insns_all[j][2]
            if m2.startswith("j") and m2 != "jmp" and o2.startswith("0x") and \
                    a - 0x80 <= int(o2, 16) <= a:
                back = j
                break
        if back is None or int(insns_all[back][2], 16) not in at:
            continue
        body = insns_all[at[int(insns_all[back][2], 16)]:back + 1]
        # the wait: the loop's last call, just before its exit test
        calls = [o2 for _a, m2, o2, _s2 in body if m2 == "call"]
        if not any(m2 == "mov" and o2 == "dword ptr [rbx + 0x%x], eax" % value
                   for _a, m2, o2, _s2 in body) or not calls:
            continue
        waits = {calls[-1]}
        head = body[0][0] - BASE
        reads = [xrefs.rip_target(i) for i in body if i[1] == "subss" and "rip" in i[2]]
        tail = body[-4:]
        if reads:
            need(len(reads) == 1, "lapse loop main+%X reads %d rip globals" % (head, len(reads)))
            need([i[1] for i in tail] == ["mov", "shr", "test", "je"] and tail[1][2] == "eax, 1"
                 and tail[2][2] == "al, 1" and tail[0][2].startswith("eax, dword ptr [rip"),
                 "lapse loop main+%X does not leave on bit 1 of a flags global" % head)
            loops.append(dict(head=head, kind="playhead", playhead=reads[0] - BASE,
                              flags=xrefs.rip_target(tail[0]) - BASE, wait=waits.pop()))
        else:
            cmp = body[-2]
            regs = cmp[2].split(", ")
            need(body[-1][1] == "jl" and cmp[1] == "cmp" and len(regs) == 2 and
                 any(m2 == "inc" and o2 == regs[0] for _a, m2, o2, _s2 in body),
                 "lapse loop main+%X lerps on neither a playhead nor its own count" % head)
            loops.append(dict(head=head, kind="count", wait=waits.pop()))
    heads = [lp for lp in loops if lp["kind"] == "playhead"]
    need(heads, "no time-lapse loop lerps on a playhead")
    need(len({lp["playhead"] for lp in heads}) == 1 and len({lp["flags"] for lp in heads}) == 1,
         "the time-lapse loops read different playheads")
    need(len({lp["wait"] for lp in loops}) == 1, "the time-lapse loops wait in different ways")
    return loops, heads[0]["playhead"], heads[0]["flags"]


def find_event_player(insns_all, img, funcs, playhead, flags, mode_rva):
    """The object that owns the playhead and the flags: its integrator
    `P += (float)mode * speed * 0.5`, which sets the done bit (2) once P reaches
    the event's length, and its start, which sets P = 0, speed = 1.0 and the
    flags to 0. Proves the object and every offset the watch reads."""
    hits = []
    for k in range(10, len(insns_all) - 12):
        a, m, o, _s = insns_all[k]
        ma = re.fullmatch(r"(xmm\d+), dword ptr \[rbx \+ (0x[0-9a-f]+)\]", o)
        if m != "addss" or not ma or insns_all[k + 1][1] != "movss" or \
                insns_all[k + 1][2] != "dword ptr [rbx + %s], %s" % (ma.group(2), ma.group(1)):
            continue
        off = int(ma.group(2), 16)
        obj = playhead - off
        before, after = insns_all[k - 10:k], insns_all[k + 2:k + 12]
        mode = [i for i in before if i[1] == "movzx" and i[2].startswith("eax, byte ptr [rip")
                and xrefs.rip_target(i) - BASE == mode_rva]
        half = [i for i in before if i[1] == "movss" and "[rip" in i[2] and
                struct.unpack_from("<f", img, xrefs.rip_target(i) - BASE)[0] == 0.5]
        speed = [re.search(r"\[rbx \+ (0x[0-9a-f]+)\]", i[2]) for i in before
                 if i[1] == "movss" and i[2].startswith("xmm") and "[rbx + " in i[2]]
        done = [n for n, i in enumerate(after) if i[1] == "or" and i[2] == "edx, 2"]
        store = done and after[done[0] + 1][1] == "mov" and \
            after[done[0] + 1][2] == "dword ptr [rbx + 0x%x], edx" % (flags - obj)
        if mode and half and len(speed) == 1 and store:
            hits.append(dict(integrator=a - BASE, obj=obj, playhead_off=off,
                             speed_off=int(speed[0].group(1), 16), flags_off=flags - obj))
    need(len(hits) == 1, "expected one integrator of the lapses' playhead, found %d" % len(hits))
    ev = hits[0]
    # the start: P = 0, speed = 1.0, flags = 0, called with rcx = the object
    starts = set()
    for k, (a, m, o, _s) in enumerate(insns_all):
        if m != "mov" or o != "dword ptr [rcx + 0x%x], 0" % ev["playhead_off"]:
            continue
        near = insns_all[k:k + 48]
        fn = function_of(funcs, a - BASE)
        if fn and any(i[2] == "dword ptr [rcx + 0x%x], 0x3f800000" % ev["speed_off"]
                      for i in near) and \
                any(re.fullmatch(r"dword ptr \[r[cb]x \+ 0x%x\], 0" % ev["flags_off"], i[2])
                    for i in near):
            starts.add(fn[0])
    need(len(starts) == 1, "expected one event start, found %d" % len(starts))
    start = starts.pop()
    tied = [insns_all[k][0] - BASE for k in range(len(insns_all) - 12)
            if insns_all[k][1] == "lea" and insns_all[k][2].startswith("rcx, [rip")
            and xrefs.rip_target(insns_all[k]) == BASE + ev["obj"]
            and any(i[1] == "call" and i[2] == hex(BASE + start) for i in insns_all[k:k + 12])]
    need(tied, "nothing starts an event on main+%X" % ev["obj"])
    ev.update(start=start, started_at=tied[0])
    return ev


def main():
    sha, pe, img, text, funcs = load()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    adder, clock, day_count, adder_insns = find_adder(md, img, text)
    insns_all = xrefs.cached_insns("main.dll")

    # the adder's callers are the two workers
    callers = [a - BASE for a, m, o, s in insns_all
               if m == "call" and o == hex(BASE + adder)]
    need(len(callers) == 2, "expected 2 callers of the adder, found %d" % len(callers))
    workers = [classify_worker(md, img, funcs, c, adder) for c in callers]
    need(sorted(w["role"] for w in workers) == ["advance", "transition"],
         "the two callers are not one advance and one transition")
    workers.sort(key=lambda w: w["role"])  # advance first
    need(workers[0]["delay"] == workers[1]["delay"], "the workers count different delays")

    # every reference to each worker's entry
    entries = [w["fn"][0] for w in workers]
    refs = all_references(insns_all, img, entries)
    update = None
    sites = []
    for w in workers:
        r = refs[w["fn"][0]]
        need(len(r) == 1 and r[0][1] == "jmp" and r[0][2] == 0,
             "%s main+%X is referenced %r, want one tail jump" % (w["role"], w["fn"][0], r))
        jrva = r[0][0]
        need(img[jrva] == 0xE9, "tail jump at main+%X is not jmp rel32" % jrva)
        fn = function_of(funcs, jrva)
        need(fn is not None, "tail jump main+%X outside any function" % jrva)
        need(update in (None, fn), "the tail jumps are in different functions")
        update = fn
        body = decode(md, img, *fn)
        k = [i.address - BASE for i in body].index(jrva)
        need(k >= 2 and body[k - 2].mnemonic == "add" and body[k - 2].op_str == "rsp, 0x20"
             and body[k - 1].mnemonic == "pop" and body[k - 1].op_str == "rbx",
             "tail jump main+%X is not preceded by the frame teardown" % jrva)
        need(body[0].mnemonic == "push" and body[0].op_str == "rbx" and body[1].mnemonic == "sub"
             and body[1].op_str == "rsp, 0x20", "the update's prologue is not push rbx; sub rsp, 0x20")
        need(flags_dead_from(md, img, w["fn"][0]),
             "%s main+%X reads a flag before writing it" % (w["role"], w["fn"][0]))
        sites.append(dict(rva=jrva, target=w["fn"][0], role=w["role"], orig=bytes(img[jrva:jrva + 5])))

    # the update: reached only through a thunk, the thunk only from the dispatcher
    urefs = all_references(insns_all, img, [update[0]])[update[0]]
    need(len(urefs) == 1 and urefs[0][1] == "jmp", "update main+%X refs %r" % (update[0], urefs))
    thunk = urefs[0][0]
    need(function_of(funcs, thunk) is None and img[thunk] == 0xE9,
         "main+%X is not a bare jmp thunk" % thunk)
    trefs = all_references(insns_all, img, [thunk])[thunk]
    need(len(trefs) == 1 and trefs[0][1] == "call", "thunk main+%X refs %r" % (thunk, trefs))
    call = trefs[0][0]
    fn = function_of(funcs, call)
    body = decode(md, img, *fn)
    k = [i.address - BASE for i in body].index(call)
    lea = body[k - 1]
    need(lea.mnemonic == "lea" and lea.op_str.startswith("rcx, [rip "),
         "the dispatcher's call main+%X does not load rcx with a global" % call)
    controller = rip_target(lea, lea.operands[1])
    need(flags_dead_from(md, img, call + 5), "the dispatcher reads flags after main+%X" % call)
    # the update records the clock in the controller before anything else
    ub = decode(md, img, *update)
    need(any(i.mnemonic == "mov" and i.operands[1].type == X.X86_OP_MEM
             and i.operands[1].mem.base == X.X86_REG_RIP and rip_target(i, i.operands[1]) == clock
             for i in ub[:4]), "the update does not read the clock first")

    counter = int(re.search(r"kFrameClockCounterRva = 0x([0-9A-Fa-f]+)",
                            open(CLOCKS_H).read()).group(1), 16)
    mode_rva = int(re.search(r"kShadowModeByteRva = 0x([0-9A-Fa-f]+)",
                             open(SHADOW_H).read()).group(1), 16)
    adv, trn = workers
    step = adv["step"]
    need(DAY_UNITS % step == 0, "step %d does not divide the day" % step)

    # the requested-jump path, the time-lapses that drive it, and the event
    # player whose playhead most of them follow: counted, never changed
    reqs = find_request(md, img, funcs, ub, clock)
    need(reqs["rva"] not in [s["rva"] for s in sites], "the request call is a tail jump")
    sites.append(reqs)
    lapses, playhead, evflags = find_lapses(insns_all, reqs["request"], reqs["value"])
    ev = find_event_player(insns_all, img, funcs, playhead, evflags, mode_rva)

    # the stubs
    code = bytearray(b"\xCC" * (POOL_SIZE - CODE_OFFSET))
    fixups = []
    for i, s in enumerate(sites):
        S = CODE_OFFSET + i * STUB_SIZE
        entered, ran = COUNTER_OFFSET + 8 * i, COUNTER_OFFSET + 8 * i + 4
        b = bytearray()
        if s["role"] == "request":
            # a count of the requests the update applies, then the setter as
            # called: the call's return address is still on the stack
            b += b"\xFF\x05" + struct.pack("<i", entered - (S + 6))        # inc [applied]
            b += b"\xE9\0\0\0\0"                                          # jmp setter
            fixups.append((S + 7, S + 11, s["target"]))
            need(len(b) == 11, "request stub size")
            code[S - CODE_OFFSET:S - CODE_OFFSET + len(b)] = b
            s["stub"] = S
            continue
        b += b"\xFF\x05" + struct.pack("<i", entered - (S + 6))            # inc [entered]
        b += b"\x50"                                                       # push rax
        b += b"\x8A\x05\0\0\0\0"                                          # mov al, [fc]
        fixups.append((S + 9, S + 13, counter))
        b += b"\x22\x05" + struct.pack("<i", MASK_OFFSET - (S + 19))       # and al, [mask]
        b += b"\x58"                                                       # pop rax
        b += b"\x75\x0B"                                                   # jne skip
        b += b"\xFF\x05" + struct.pack("<i", ran - (S + 28))               # inc [ran]
        b += b"\xE9\0\0\0\0"                                              # jmp worker
        fixups.append((S + 29, S + 33, s["target"]))
        b += b"\xC3"                                                       # skip: ret
        need(len(b) == 34 and len(b) <= STUB_SIZE, "stub size")
        code[S - CODE_OFFSET:S - CODE_OFFSET + len(b)] = b
        s["stub"] = S
    code = bytes(code).rstrip(b"\xCC")

    def hexbytes(bs, per=24, indent="    "):
        rows = [indent + ",".join("0x%02X" % x for x in bs[k:k + per]) + ","
                for k in range(0, len(bs), per)]
        return "\n".join(rows)

    # informational only: the lighting's palette boundaries (4AC680 reads them)
    thresholds = struct.unpack_from("<5I", img, 0x7AD6B0)
    out = []
    out.append("// Generated by tools/gen_day_clock.py -- do not edit.")
    out.append("// The day/night clock's two per-tick workers, run on stock ticks only.")
    out.append("#pragma once")
    out.append("#include <cstdint>")
    out.append("")
    out.append('#define DAY_CLOCK_MAIN_SHA1 "%s"' % sha)
    out.append("static const uint32_t kDayClockRva = 0x%X;       // the world clock, %d a day"
               % (clock, DAY_UNITS))
    out.append("static const uint32_t kDayCountRva = 0x%X;       // days elapsed, a word" % day_count)
    out.append("static const uint32_t kDayControllerRva = 0x%X;  // the day/night controller"
               % controller)
    out.append("static const uint32_t kDayCountOff = 0x%X;        // transition steps left, a word"
               % trn["count"])
    out.append("static const uint32_t kDayTargetOff = 0x%X;       // the transition's target time"
               % trn["target"])
    out.append("static const uint32_t kDayDelayOff = 0x%X;        // ticks to wait first, a dword"
               % adv["delay"])
    out.append("static const uint32_t kDayUnits = %d;" % DAY_UNITS)
    out.append("static const uint32_t kDayStep = %d;              // per stock tick (main+%X)"
               % (step, adv["step_at"]))
    out.append("static const uint32_t kDayFrameCounterRva = 0x%X;" % counter)
    out.append("static const uint32_t kDayMaskOffset = 0x%X;" % MASK_OFFSET)
    out.append("static const uint32_t kDayCounterOffset = 0x%X;  // {entered, ran} per site;"
               " the request site's first counts requests applied" % COUNTER_OFFSET)
    out.append("static const uint32_t kDayCodeOffset = 0x%X;" % CODE_OFFSET)
    out.append("static const uint32_t kDayPoolSize = 0x%X;" % POOL_SIZE)
    out.append("")
    out.append("// The requested jump (main+%X -> main+%X): the controller's +0x%X set asks the"
               % (reqs["rva"], reqs["target"], reqs["request"]))
    out.append("// update to set the clock to +0x%X. %d time-lapse loops ask on every pass:"
               % (reqs["value"], len(lapses)))
    for lp in lapses:
        out.append("//   main+%X, lerping on %s" % (lp["head"], "the event playhead"
                                                     if lp["kind"] == "playhead" else "its own count"))
    out.append("static const int kDayRequestSite = %d;" % sites.index(reqs))
    out.append("static const uint32_t kDayRequestOff = 0x%X;      // a byte" % reqs["request"])
    out.append("static const uint32_t kDayRequestValueOff = 0x%X;" % reqs["value"])
    out.append("// The event player they lerp on: its integrator (main+%X) steps the playhead by"
               % ev["integrator"])
    out.append("// (float)mode * speed * 0.5 a tick and sets the done bit once it reaches the event's")
    out.append("// length; its start (main+%X) sets playhead 0, speed 1.0, flags 0." % ev["start"])
    out.append("static const uint32_t kDayEventRva = 0x%X;" % ev["obj"])
    out.append("static const uint32_t kDayEventPlayheadOff = 0x%X;  // a float" % ev["playhead_off"])
    out.append("static const uint32_t kDayEventSpeedOff = 0x%X;     // a float" % ev["speed_off"])
    out.append("static const uint32_t kDayEventFlagsOff = 0x%X;" % ev["flags_off"])
    out.append("static const uint32_t kDayEventDone = 2;")
    out.append("// the playhead's stock rate at speed 1: mode 2 x 0.5 at 30 Hz, mode 1 x 0.5 at 60")
    out.append("static const float kDayPlayheadStockRate = %.1ff;  // per second" % (2 * 0.5 * 30))
    out.append("")
    out.append("static const uint8_t kDayClockCode[] = {")
    out.append(hexbytes(code))
    out.append("};")
    out.append("")
    out.append("struct DayClockFixup { uint32_t field, next, target; };  // rel32 at field -> main+target")
    out.append("static const DayClockFixup kDayClockFixups[] = {")
    for f in fixups:
        out.append("    {0x%X, 0x%X, 0x%X}," % f)
    out.append("};")
    out.append("")
    out.append("// Each tail jump in the update (main+%X), retargeted at its stub, and its" % update[0])
    out.append("// requested jump's call, retargeted at a stub that only counts.")
    out.append("struct DayClockSite { uint32_t rva, target, stub; const char* role; };")
    out.append("static const DayClockSite kDayClockSites[] = {")
    for s in sites:
        out.append('    {0x%X, 0x%X, 0x%X, "%s"},' % (s["rva"], s["target"], s["stub"], s["role"]))
    out.append("};")
    out.append("static const uint8_t kDayClockOrig[] = {")
    out.append(hexbytes(b"".join(s["orig"] for s in sites)))
    out.append("};")
    text_h = "\n".join(out) + "\n"
    with open(OUT_H, "w", encoding="utf-8", newline="\n") as f:
        f.write(text_h)

    facts = [
        ("clock", "main+%X" % clock, "adder main+%X: mov r8d,[clock]; add r8d,edx; store; imul %d"
         % (adder, DAY_UNITS)),
        ("day counter", "main+%X" % day_count, "inc word in the adder on a day boundary"),
        ("controller", "main+%X" % controller, "lea rcx before the dispatcher's call main+%X" % call),
        ("dispatcher call", "main+%X" % call, "only reference to the thunk main+%X" % thunk),
        ("update", "main+%X" % update[0], "only reference: the thunk's jmp"),
    ]
    for w, s in zip(workers, sites):
        facts.append((w["role"], "main+%X" % w["fn"][0],
                      "only reference: tail jump main+%X; adder call main+%X; delay +0x%X at main+%X%s"
                      % (s["rva"], w["call"], w["delay"], w["delay_dec"],
                         "; step %d at main+%X" % (w["step"], w["step_at"]) if w["role"] == "advance"
                         else "; count +0x%X (dec main+%X), target +0x%X"
                         % (w["count"], w["count_dec"], w["target"]))))
    facts.append(("requested jump", "main+%X" % reqs["rva"],
                  "the update's one call, to the setter main+%X (stores edx to the clock) when "
                  "+0x%X is set, time +0x%X; flags dead at the setter"
                  % (reqs["target"], reqs["request"], reqs["value"])))
    for lp in lapses:
        facts.append(("time-lapse", "main+%X" % lp["head"],
                      "loop setting +0x%X and +0x%X each pass, waiting through main+%X; %s"
                      % (reqs["request"], reqs["value"], int(lp["wait"], 16) - BASE,
                         "lerps on the playhead main+%X, leaves on bit 1 of main+%X"
                         % (lp["playhead"], lp["flags"]) if lp["kind"] == "playhead"
                         else "lerps on its own count (inc; cmp; jl)")))
    facts.append(("event player", "main+%X" % ev["obj"],
                  "integrator main+%X: +0x%X += mode * [+0x%X] * 0.5, done bit 2 in +0x%X; "
                  "start main+%X (called after lea rcx at main+%X)"
                  % (ev["integrator"], ev["playhead_off"], ev["speed_off"], ev["flags_off"],
                     ev["start"], ev["started_at"])))
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["what", "where", "evidence"])
        wr.writerows(facts)
    for row in facts:
        print("%-16s %-12s %s" % row)
    print("day: %d units, %d per stock tick = %.1f min at 30 Hz; palettes at %s"
          % (DAY_UNITS, step, DAY_UNITS / step / 30 / 60, ", ".join(
              "%02d:%02d" % (t * 24 // DAY_UNITS, t * 24 % DAY_UNITS * 60 // DAY_UNITS)
              for t in thresholds)))
    print("wrote %s (%d sites, %d code bytes, %d fixups); sha1 %s"
          % (os.path.relpath(OUT_H, ROOT), len(sites), len(code), len(fixups), sha))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as e:
        sys.exit("gen_day_clock: %s" % e)
