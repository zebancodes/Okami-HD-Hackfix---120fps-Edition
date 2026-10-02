#!/usr/bin/env python3
"""Which `near` candidates sit in a task loop task_waits.h converts to one
pass a stock tick (its wait(1) made wait(N)): every cycle through the
candidate's block must pass the converted wait's block."""
import collections
import contextlib
import csv
import io
import os
import re
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
import task_wait_loops as twl  # noqa: E402

DOCS = os.path.join(REPO, "docs", "animation")


def converted_loops():
    out = {}
    pat = re.compile(r"\{0x([0-9A-F]+), -?\d+, (\d+), 0x(E8|E9), (\d)\},\s+// in ([0-9A-F]+), (\w+)")
    for m in pat.finditer(open(os.path.join(REPO, "src", "task_waits.h")).read()):
        if m.group(4) == "1":
            out[int(m.group(1), 16)] = int(m.group(5), 16)
    return out


# --nested: also take a site in an inner loop of the paced loop (a walk over a
# table runs once a pass: 4BBE10, 5B5BF0, which the cycle test first missed)
NESTED = "--nested" in sys.argv


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        prog = twl.Program()
    loops = converted_loops()
    by_fn = collections.defaultdict(list)
    for call, fn in loops.items():
        by_fn[fn].append(call)
    # the near sites of 2026-10-02 (coverage.csv calls them `read` once they
    # have verdicts): the reading list and the first run's task-loop sites
    here = os.path.dirname(os.path.abspath(__file__))
    listed = set(open(os.path.join(here, "near_taskloop_sites.txt")).read().split())
    for line in open(os.path.join(here, "near_by_fn.txt")):
        listed.update(x.split(":")[0] for x in line.split()[2:])
    rows = [r for r in csv.DictReader(open(os.path.join(DOCS, "coverage.csv"), encoding="utf-8"))
            if r["status"] == "near" or r["site"] in listed]
    found, other = [], collections.Counter()
    for r in rows:
        site = int(r["site"], 16)
        fn = prog.func_of(site)
        calls = [c for c in loops if prog.func_of(c).root == fn.root]
        if not calls:
            other[r["family"]] += 1
            continue
        bl, bof, heads = prog.loops(fn)
        if site not in bof:
            other["not decoded"] += 1
            continue
        sb = bof[site]
        hit = None
        for c in calls:
            if c not in bof:
                continue
            head, nodes = prog.innermost(fn, c)
            if head is None:
                continue
            hb = bof[head]
            body = heads[head] if head in heads else None
            if body is None:
                # innermost() keys heads by block
                body = next(b for h, b in heads.items() if h == bof[head])
            if sb not in body:
                continue
            # no cycle through the site's block that avoids the wait's block
            wb = bof[c]
            succ = collections.defaultdict(set)
            for b in body:
                last = bl[b][-1]
                for s in fn_succs(fn, last):
                    if s in bof and bof[s] in body:
                        succ[b].add(bof[s])
            # can sb reach sb (through head) without wb?
            seen, work = set(), [x for x in succ[sb] if x != wb]
            cyc = False
            while work:
                n = work.pop()
                if n == sb:
                    cyc = True
                    break
                if n in seen or n == wb:
                    continue
                seen.add(n)
                work.extend(succ[n])
            if sb == wb:
                cyc = False
            if not cyc or NESTED:
                hit = (c, head)
                break
        if hit:
            found.append((r, hit))
        else:
            other["in fn, not in a converted loop: " + r["family"]] += 1
    for r, (c, head) in found:
        print("%s %s %s %s %s wait %X head %X" % (r["site"], r["function"], r["family"], r["group"],
                                                 r["shape"], c, head))
    print(len(found), "in converted loops")
    for k, v in other.most_common():
        print(" ", v, k)


def fn_succs(fn, a):
    i = fn.ins[a]
    out = []
    m = i.mnemonic
    if m in ("ret", "int3", "ud2", "hlt"):
        return out
    if m.startswith("j"):
        op = i.operands[0]
        if op.type == twl.X.X86_OP_IMM:
            out.append(op.imm)
        if m == "jmp":
            return out
    out.append(a + i.size)
    return out


if __name__ == "__main__":
    main()
