#!/usr/bin/env python3
"""Turn the p-code census into an inventory of every per-tick animation clock.

    .venv/Scripts/python tools/animation_inventory.py [--census PATH] [--outdir docs/animation]

Inputs (all regenerable, none checked in):
  * ~\\tools\\pcode_census.jsonl                tools/pcode_census.py
  * ~\\tools\\main_decompiled.c                 tools/ghidra_export.py
  * tools/rtti_classes.txt                      RTTI vtables (class -> methods)
  * main.dll from the game directory            constants
  * src/*.h                                     what the patch already covers

Outputs in --outdir:
  * sites.csv        every self-updating store that is not a bit operation,
                     with owner classes, subsystem, step shape, resolved step
                     constants and whether an existing patch table covers it
  * clock_reads.csv  every function that reads the frame counter or the mode
                     byte, with the encoding of each read and its coverage
  * summary.md       counts by subsystem x shape, for the hand-written
                     docs/animation/README.md to cite

Nothing here decides what to patch. A self-update is only a *candidate*: a
state index advanced once on a transition looks exactly like a timer counted
every tick, and only reading the site tells them apart (tools/ghidra_lines.py
prints any function with instruction addresses on every line for that).
"""
import argparse
import bisect
import collections
import csv
import json
import os
import re
import struct
import sys

import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamedir import GAME  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE = 0x180000000
DECOMP = os.environ.get("OKAMI_DECOMP", os.path.expanduser(r"~\tools\main_decompiled.c"))
CENSUS = os.environ.get("OKAMI_CENSUS", os.path.expanduser(r"~\tools\pcode_census.jsonl"))

FRAME, MODE, TSCALE = 0xB6AC20, 0xB6AC45, 0xB6AC38

# Subsystem roots that are not RTTI methods: they are called straight from the
# per-frame dispatcher (main+4BA500) on a global object. See docs/animation.
UI_ROOTS = {
    0x413CC0: "pause menu manager (obj B1EBA0)",
    0x149F50: "options controller (obj B1E100)",
    0x3F3F70: "HUD manager update (obj B1C7C0)",
    0x3F3A10: "HUD manager draw (obj B1C7C0)",
    0x403D50: "brush window (obj B1CC20)",
    0x4396F0: "scene transition model (obj B4DF40)",
}
EFFECT_ROOTS = {0x18E1A0: "effect manager step", 0x1928F0: "effect instance step"}
UI_PREFIX = ("cCock", "cSubScr", "cSS", "cOption", "cTitle", "cMc", "cShop", "cItemShop",
             "cKibaShop", "cSkillShop", "cPictureBook", "cGallery", "iSSFiles",
             "cWeaponCommand", "cUchikoCommand", "cToolCommand", "cFudesetModel")
LAYOUT_RANGE = (0x1B1000, 0x1BA000)   # hx 2D layout player (every cCock/cSubScr owns one)
LIBRARY_END = 0x120000                # below: CRI middleware and CRT, no game symbols
WRAP_FN = 0x13F2E0                    # wrap angle to (-pi, pi]
MATERIAL_FN = 0x20CF90                # model material state: rgb +50..58, a +5C, uv +60/+64


# ---------------------------------------------------------------- binary
class Image:
    def __init__(self, path):
        pe = pefile.PE(path, fast_load=True)
        self.img = pe.get_memory_mapped_image()
        self.sects = [(s.Name.rstrip(b"\0").decode(), s.VirtualAddress,
                       max(s.Misc_VirtualSize, s.SizeOfRawData)) for s in pe.sections]

    def sect(self, rva):
        for n, va, sz in self.sects:
            if va <= rva < va + sz:
                return n
        return None

    def f32(self, rva):
        if rva + 4 > len(self.img):
            return None
        return struct.unpack_from("<f", self.img, rva)[0]

    def const(self, rva, size=4):
        """value of an initialised constant, or None"""
        if self.sect(rva) not in (".rdata", ".data") or rva + size > len(self.img):
            return None
        if size == 8:
            return struct.unpack_from("<d", self.img, rva)[0]
        v = struct.unpack_from("<f", self.img, rva)[0]
        raw = struct.unpack_from("<I", self.img, rva)[0]
        if raw == 0 or 1e-6 < abs(v) < 1e7:
            return v
        return raw


# ---------------------------------------------------------------- decompilation index
class Decomp:
    HDR = re.compile(r"^// ==== main\+([0-9A-F]{6})  (.*?) ====$", re.M)
    CALL = re.compile(r"\b(?:FUN|thunk_FUN|LAB)_18([0-9a-f]{7})\b")

    def __init__(self, path):
        src = open(path, encoding="utf-8", errors="replace").read()
        ms = list(self.HDR.finditer(src))
        self.funcs = {}
        self.order = []
        for i, m in enumerate(ms):
            e = ms[i + 1].start() if i + 1 < len(ms) else len(src)
            rva = int(m.group(1), 16)
            self.funcs[rva] = (m.group(2), src[m.end():e])
            self.order.append(rva)
        self.order.sort()
        self.calls = {}
        self.callers = collections.defaultdict(set)
        for rva, (name, body) in self.funcs.items():
            out = {int(x, 16) for x in self.CALL.findall(body)} - {rva}
            out &= self.funcs.keys()
            mt = re.match(r"thunk_FUN_18([0-9a-f]{7})", name)
            if mt:
                out.add(int(mt.group(1), 16))
            self.calls[rva] = out
            for t in out:
                self.callers[t].add(rva)

    def owner(self, rva):
        i = bisect.bisect_right(self.order, rva) - 1
        return self.order[i] if i >= 0 else None

    def reach(self, roots, maxcallers, depth):
        seen = {}
        todo = [(r, 0) for r in roots if r in self.funcs]
        while todo:
            r, d = todo.pop()
            if r in seen and seen[r] <= d:
                continue
            seen[r] = d
            if d >= depth:
                continue
            for c in self.calls.get(r, ()):
                if len(self.callers.get(c, ())) <= maxcallers:
                    todo.append((c, d + 1))
        return seen


def load_rtti(path):
    classes = {}
    vt = collections.defaultdict(list)
    for line in open(path):
        p = line.split()
        if len(p) < 4 or p[2] != "off=0":
            continue
        cls = p[1].replace(".?AV", "").replace(".?AU", "").rstrip("@")
        fns = [int(x, 16) for x in p[4:]]
        classes.setdefault(cls, fns)
        for i, f in enumerate(fns):
            vt[f].append((cls, i))
    return classes, vt


def patched_sites(repo):
    """RVA -> table name for every code site an existing generated table patches"""
    out = {}
    for fn in sorted(os.listdir(os.path.join(repo, "src"))):
        if not fn.endswith(".h"):
            continue
        for m in re.finditer(r"^\s*\{0x([0-9A-Fa-f]{5,6}),", open(os.path.join(repo, "src", fn)).read(), re.M):
            rva = int(m.group(1), 16)
            if rva < 0x670000:          # code only; mode_constants also lists data tables
                out[rva] = fn[:-2]
    return out


# ---------------------------------------------------------------- classification
_G = re.compile(r"\[g([0-9a-f]+)/(\d)\]")
_IMM = re.compile(r"#([0-9a-f]+)/(\d)")


def phi_branches(e):
    """split PHI(a|b|c) at its own nesting level"""
    inner, depth, cur, out = e[4:-1], 0, "", []
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "|" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def shape(r):
    e, top = r["e"], r["e"].split("(", 1)[0]
    clk = set(r["clk"])
    if top == "PHI":
        # a conditional step: classify by the first branch that does arithmetic
        for b in phi_branches(e):
            s = shape(dict(r, e=b, clk=[]))
            if s not in ("copy", "other"):
                return shape(dict(r, e=b)) if clk else s
        return "copy"
    if "tscale" in clk:
        return "port:timescale"
    if clk & {"mode", "fps", "shift"}:
        return "port:mode"
    if "frame" in clk:
        return "frame-derived"
    if top in ("INT_OR", "INT_AND", "INT_XOR", "INT_NEGATE", "BOOL_NEGATE"):
        return "bits"
    if top in ("COPY", "phi") or top.startswith("["):
        return "copy"
    if top.startswith("call_%x" % WRAP_FN):
        return "phase-wrap"
    if top.startswith("call_"):
        return "call"
    if top in ("INT_ADD", "INT_SUB"):
        m = re.fullmatch(r"INT_(ADD|SUB)\(\[[^\]]*\],#([0-9a-f]+)/(\d)\)", e)
        if m:
            return "counter" if int(m.group(2), 16) in (1, 2, 3, 4) or \
                int(m.group(2), 16) >= (1 << (8 * int(m.group(3)))) - 4 else "int-step"
        return "int-expr"
    if top in ("FLOAT_ADD", "FLOAT_SUB"):
        if re.fullmatch(r"FLOAT_(ADD|SUB)\((\[[^\]]*\],\[g[0-9a-f]+/4\]|\[g[0-9a-f]+/4\],\[[^\]]*\])\)", e):
            return "float-step"
        if re.search(r"FLOAT_MULT\(FLOAT_SUB\(", e):
            return "lerp"
        return "float-expr"
    if top == "FLOAT_MULT":
        return "multiplier"
    if top in ("INT_MULT", "INT_LEFT"):
        return "int-mult"
    return "other"


def resolve(e, img):
    def sub(m):
        v = img.const(int(m.group(1), 16), int(m.group(2)))
        if v is None:
            return m.group(0)
        return "%.6g" % v if isinstance(v, float) else "0x%x" % v
    e = _G.sub(sub, e)
    return e


def step_values(e, img):
    vals = []
    for m in _G.finditer(e):
        rva = int(m.group(1), 16)
        if img.sect(rva) == ".rdata" or (img.sect(rva) == ".data" and rva < 0x7E5000):
            v = img.const(rva, int(m.group(2)))
            if isinstance(v, float):
                vals.append("%.6g" % v)
    for m in _IMM.finditer(e):
        v, sz = int(m.group(1), 16), int(m.group(2))
        if v >= 1 << (8 * sz - 1):
            v -= 1 << (8 * sz)
        vals.append(str(v))
    return " ".join(vals[:4])


def field_of(loc):
    m = re.fullmatch(r"(?:INT_ADD|PTRSUB)\(in:(\w+),c([0-9a-f]+)\)", loc)
    if m:
        return "%s+0x%X" % (m.group(1), int(m.group(2), 16))
    m = re.fullmatch(r"PTRADD\(in:(\w+),c([0-9a-f]+),c([0-9a-f]+)\)", loc)
    if m:
        return "%s+0x%X" % (m.group(1), int(m.group(2), 16) * int(m.group(3), 16))
    m = re.fullmatch(r"g([0-9a-f]+)", loc)
    if m:
        return "main+%X" % int(m.group(1), 16)
    m = re.search(r"CALL\(g%x,[^,]*,c(\d+)\),c([0-9a-f]+)\)" % MATERIAL_FN, loc)
    if m:
        return "material[%s]+0x%X" % (m.group(1), int(m.group(2), 16))
    return loc if len(loc) <= 70 else loc[:67] + "..."


def class_family(cls):
    """em2c -> em, uta4 -> ut, cHumanShop -> cHuman, cKiType007 -> cKiType,
    objScroll -> obj; templates and namespaced classes -> None"""
    m = re.fullmatch(r"([a-z]{2})[0-9a-f]{2}", cls)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(c[A-Z][A-Za-z]*?)\d+", cls)
    if m:
        return m.group(1)
    m = re.match(r"(c[A-Z][a-z]+)", cls)
    if m:
        return m.group(1)
    m = re.match(r"([a-z]+)(?=[A-Z_0-9]|$)", cls)
    return m.group(1) if m and "@" not in cls else None


# ---------------------------------------------------------------- clock-read encodings
FC = "DAT_180b6ac20"
MB = "DAT_180b6ac45"


def fc_encoding(s):
    if re.search(FC + r" = " + FC + r" [+-]|memset\(&" + FC, s):
        return "writer"
    if re.search(r"& (1|3|7|0xf|0x1f|0x3f)\) [!=]= 0", s) and FC in s:
        return "mask-gate"
    if re.search(r"& 1\) == \*", s):
        return "parity-gate"
    if re.search(r"% 10\b|/ 0x[0-9a-f]+\) \* 0x|% \(ulonglong\)DAT_18097|% \(uint\)\(DAT_180b6ac44 >> 1\)", s) or \
            re.search(FC + r" == \(", s):
        return "modulo-gate"
    if re.search(r"% 0x168|% 0xe10|% \(0x168|%$", s):
        return "phase-360"
    if re.search(FC + r" \* [24]\)|\(float\)" + FC + r" \*|\(float\)\(ushort\)" + FC + r"|& 0x3f\) \+", s):
        return "phase-raw"
    if ">> 2 & 3" in s:
        return "cycle"
    if re.search(r"0x1e0 /", s):
        return "elapsed/mode"
    if FC + " - " in s:
        return "elapsed"
    return "snapshot"


def mode_encoding(s):
    if MB + " = " in s:
        return "writer"
    if re.search(r"= \(uint\)" + MB + ";|= " + MB + ";", s):
        return "save"
    if re.search(MB + r" - 1\) \* 4\)", s):
        return "table[mode-1]"
    if re.search(r"\(float\)\(byte\)\(\(" + MB, s):
        return "float*((mode!=2)+1)"
    if re.search(r"\(float\)\(uint\)" + MB + r"|\(float\)" + MB, s):
        return "float*mode"
    if re.search(r"[+-] \(uint\)" + MB + r"|- " + MB + r"\)|- \(int\)" + MB, s):
        return "step=mode"
    if re.search(r"/ \(ulonglong\)" + MB, s):
        return "n/mode"
    if re.search(r"% \(ulonglong\)" + MB, s):
        return "x%mode"
    if re.search(r"\(" + MB + r" [!=]= '.x0[12]'\) \+ 1", s):
        return "(mode==1)+1"
    if re.search(MB + r" [!=]= '.x0[12]'.*DAT_180b6ac20", s):
        return "parity-gate"
    if re.search(MB + r" - 1\)", s):
        return "index=mode-1"
    return "test"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=CENSUS)
    ap.add_argument("--decomp", default=DECOMP)
    ap.add_argument("--binary", default=os.path.join(GAME, "main.dll"))
    ap.add_argument("--outdir", default=os.path.join(REPO, "docs", "animation"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    img = Image(args.binary)
    dc = Decomp(args.decomp)
    classes, vt = load_rtti(os.path.join(HERE, "rtti_classes.txt"))
    patched = patched_sites(REPO)
    patched_rvas = sorted(patched)

    # owner classes: private helpers (<=2 callers) up to depth 4 from own methods
    # a method is always owned by every class whose vtable holds it; private
    # helpers are only followed from methods shared by at most three classes,
    # or a base-class method would drag half the game into every subsystem
    owners = collections.defaultdict(set)
    for cls, fns in classes.items():
        for f in fns:
            owners[f].add(cls)
        roots = [f for f in fns if f in dc.funcs and len(vt.get(f, [])) <= 3]
        for f in dc.reach(roots, maxcallers=2, depth=4):
            owners[f].add(cls)
    ui_fns = {}
    for root, label in UI_ROOTS.items():
        for f in dc.reach([root], maxcallers=3, depth=5):
            ui_fns.setdefault(f, label)
    fx_fns = {}
    for root, label in EFFECT_ROOTS.items():
        for f in dc.reach([root], maxcallers=6, depth=3):
            fx_fns.setdefault(f, label)

    def subsystem(frva, loc):
        own = owners.get(frva, set())
        if frva < LIBRARY_END:
            return "library"
        if "CALL(g%x" % MATERIAL_FN in loc:
            return "model-material"
        if LAYOUT_RANGE[0] <= frva < LAYOUT_RANGE[1]:
            return "ui-layout-player"
        if any(c.startswith("esp") for c in own) or frva in fx_fns:
            return "effect"
        if frva in ui_fns or (own and 2 * sum(c.startswith(UI_PREFIX) for c in own) >= len(own)):
            return "ui"
        pref = sorted({class_family(c) for c in own} - {None})
        if pref:
            return "object:" + "/".join(pref[:3])
        return "unattributed"

    def covered(frva, lo, hi):
        i = bisect.bisect_left(patched_rvas, lo - 8)
        hits = set()
        while i < len(patched_rvas) and patched_rvas[i] <= hi + 8:
            if dc.owner(patched_rvas[i]) == frva:
                hits.add(patched[patched_rvas[i]])
            i += 1
        return ",".join(sorted(hits))

    recs = [json.loads(l) for l in open(args.census, encoding="utf-8")]
    rows = []
    for r in recs:
        if r["t"] != "self":
            continue
        sh = shape(r)
        if sh in ("bits", "copy"):
            continue
        f = r["f"]
        own = sorted(owners.get(f, ()))
        slots = ",".join("%s[%d]" % c for c in vt.get(f, [])[:3])
        lo = min(x for x in (r["at"], r["ld"]) if x is not None)
        rows.append({
            "site": "%06X" % r["at"],
            "load": "%06X" % r["ld"] if r["ld"] is not None else "",
            "function": "%06X" % f,
            "subsystem": subsystem(f, r["loc"]),
            "owners": " ".join(own[:4]) + (" +%d" % (len(own) - 4) if len(own) > 4 else ""),
            "vtable": slots,
            "root": ui_fns.get(f) or fx_fns.get(f) or "",
            "shape": sh,
            "size": r["sz"],
            "field": field_of(r["loc"]),
            "step": step_values(r["e"], img),
            "clocks": " ".join(sorted(set(r["clk"]))),
            "covered_by": covered(f, lo, r["at"]),
            "expr": resolve(r["e"], img)[:200],
        })
    rows.sort(key=lambda x: (x["subsystem"], x["function"], x["site"]))
    cols = list(rows[0].keys())
    with open(os.path.join(args.outdir, "sites.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)

    # clock reads, by function, from the decompiled text
    crow = []
    for f in sorted({r["f"] for r in recs if r["t"] == "clock" and r["clk"] in ("frame", "mode")}):
        body = dc.funcs[f][1]
        for ln in body.split("\n"):
            s = ln.strip()
            for clk, token, enc in (("frame", FC, fc_encoding), ("mode", MB, mode_encoding)):
                if re.search(token + r"\b", s):
                    own = sorted(owners.get(f, ()))
                    crow.append({
                        "function": "%06X" % f,
                        "clock": clk,
                        "encoding": enc(s),
                        "subsystem": subsystem(f, ""),
                        "owners": " ".join(own[:3]),
                        "covered_by": covered(f, f, f + 0x4000) if clk == "frame" else "",
                        "code": s[:180],
                    })
    with open(os.path.join(args.outdir, "clock_reads.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, list(crow[0].keys()))
        w.writeheader()
        w.writerows(crow)

    # summary
    subs = collections.Counter(r["subsystem"].split(":")[0] if not r["subsystem"].startswith("object")
                               else "object" for r in rows)
    shapes = ["counter", "int-step", "int-expr", "float-step", "float-expr", "phase-wrap",
              "multiplier", "lerp", "call", "int-mult", "frame-derived", "port:mode",
              "port:timescale", "other"]
    tab = collections.defaultdict(collections.Counter)
    cov = collections.Counter()
    for r in rows:
        s = r["subsystem"] if not r["subsystem"].startswith("object") else "object"
        tab[s][r["shape"]] += 1
        if r["covered_by"]:
            cov[s] += 1
    with open(os.path.join(args.outdir, "summary.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("<!-- generated by tools/animation_inventory.py -- do not edit -->\n\n")
        fh.write("Self-updating stores by subsystem and step shape (bit operations and plain copies excluded).\n\n")
        fh.write("| subsystem | total | covered | " + " | ".join(shapes) + " |\n")
        fh.write("|---|---|---|" + "---|" * len(shapes) + "\n")
        for s, n in subs.most_common():
            fh.write("| %s | %d | %d | %s |\n" % (s, n, cov[s], " | ".join(str(tab[s][k] or "") for k in shapes)))
        fh.write("\nClock reads by encoding:\n\n| clock | encoding | reads | functions |\n|---|---|---|---|\n")
        cc = collections.Counter((c["clock"], c["encoding"]) for c in crow)
        cf = collections.defaultdict(set)
        for c in crow:
            cf[(c["clock"], c["encoding"])].add(c["function"])
        for (clk, enc), n in sorted(cc.items()):
            fh.write("| %s | %s | %d | %d |\n" % (clk, enc, n, len(cf[(clk, enc)])))
    print("%d sites, %d clock reads -> %s" % (len(rows), len(crow), args.outdir))
    for s, n in subs.most_common():
        print("  %-18s %6d  covered %d" % (s, n, cov[s]))


if __name__ == "__main__":
    main()
