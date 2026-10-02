#!/usr/bin/env python3
"""Turn a tracer session into a classification of every candidate.

Reads the okami_tracer\\phaseNN_*.csv files the tracer build writes (the final
file of each step; if the step never finished, the latest complete snapshot of
it -- from the latest run, and within that run normally the .exit file, which
holds everything the .partial autosave does and more; see pick_files) and
joins them with docs/animation/sites.csv and tracer_sites.csv.

Per candidate, over the whole session:

  class       clock        changed on 8 or more consecutive ticks
              gated-clock  changed on 8+ ticks, and on at least 1 in 5 of the
                           ticks it ran, but never 8 in a row (every 2nd or 3rd
                           tick, a frame-counter gate)
              event        changed, but on fewer than 8 ticks
              static       ran, never changed the field
              unseen       never ran on the route
              untraced     no window (see tracer_sites.csv for why)
  context     30 / 60 / both -- the mode byte on the ticks it ran (1 = the stock
              60 Hz configuration, 2 = 30 Hz)
  steps       route steps it changed in
  delta       one sampled per-execution change, decoded by the store's kind

and, joined from docs/animation/static_classification.csv (tools/site_facts.py),
the class the code alone gives, which decides what the route never reached:

  decision    patch         the session saw it clock, and the code agrees
              patch-static  unseen on the route; the code shows a clock
                            (strong or medium evidence)
              exclude       state, pointer, input -- or it ran and never
                            changed, or only changed as an event, and the code
                            does not call it a clock either
              review        the two disagree, or neither decides

Writes docs/animation/classification.csv and docs/animation/trace_summary.md.

    python tools/tracer_report.py [DIR] [--out OUTDIR]
                                  (default: <game>\\okami_tracer, docs/animation)
"""
import collections
import csv
import datetime
import glob
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamedir import GAME  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
DOCS = os.path.join(ROOT, "docs", "animation")

HDR_TICKS = re.compile(r"# ticks (\d+) .*?, ([\d.]+) s = ([\d.]+) ticks/s, slow (\d+) s,"
                       r" mode samples other/1/2 (\d+)/(\d+)/(\d+)")
HDR_RANGE = re.compile(r"# ticks \d+ \(frame counter (\d+)\.\.(\d+)\)")
HDR_PHASE = re.compile(r"# okami tracer phase (\d+): (.*)")
HDR_SESSION = re.compile(r"# session (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})Z pid (\d+)$")
FILE = re.compile(r"phase(\d+)_(.+?)(\.partial|\.exit|\.selftest)?\.csv$")
COLUMNS = 15   # site .. window_state, as tracerDump writes them


def snapshot_info(path):
    """(first tick, last tick, session) of the counts in a complete tracer
    file, or a reason it is not one. Complete: both header lines, the column
    row, every row with all its columns, and the final newline -- a write the
    game did not finish (it crashed, or was killed, mid-dump) fails at least
    the last. session: (the run's start as a Unix time, its pid) from the
    `# session` line, or None for a file written before there was one."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        return None, "unreadable (%s)" % e
    if not text.endswith("\n"):
        return None, "cut short (no final newline)"
    lines = text.splitlines()
    rng = next((HDR_RANGE.match(ln) for ln in lines if HDR_RANGE.match(ln)), None)
    if not any(HDR_PHASE.match(ln) for ln in lines) or not rng or \
            not any(HDR_TICKS.match(ln) for ln in lines):
        return None, "no header"
    body = [ln for ln in lines if not ln.startswith("#")]
    if not body or not body[0].startswith("site,"):
        return None, "no column row"
    bad = [k for k, ln in enumerate(body[1:], 2) if ln.count(",") != COLUMNS - 1]
    if bad:
        return None, "row %d has the wrong number of columns" % bad[0]
    ses = next((HDR_SESSION.match(ln) for ln in lines if HDR_SESSION.match(ln)), None)
    session = None
    if ses:
        start = datetime.datetime.strptime(ses.group(1), "%Y-%m-%dT%H:%M:%S.%f")
        session = (start.replace(tzinfo=datetime.timezone.utc).timestamp(), int(ses.group(2)))
    return (int(rng.group(1)), int(rng.group(2)), session), None


def run_order(f):
    """Where a file's run falls among runs: its start, from the session line,
    or for a file without one (from before the tracer wrote it) the file's own
    modification time. Runs of the game do not overlap, so a run that started
    after another's file was written is the later run, and so is the run of a
    file written after another run started."""
    return f["session"][0] if f["session"] else f["mtime"]


def same_run(a, b):
    """Only a session line can say two files are from one run. The frame
    counter cannot: it restarts with every launch, from the same value."""
    return a["session"] is not None and a["session"] == b["session"]


def pick_files(d, warn=print):
    """One file per route step.

    F4 ends a step by writing its final file and deleting its autosave. A step
    that never ended leaves its autosave (.partial, rewritten every
    AutosaveSeconds) and, if the game quit normally, an .exit file written at
    exit from the same running counts -- everything the autosave has, and
    whatever ran after it. So, per step:

      the final file, if it is complete;
      else the latest complete snapshot: from the latest run (run_order), and
      within that run the one whose counts reach the later tick, .exit on a
      tie;
      else a self-test file.

    A later run wins over an earlier one however far each got: the frame
    counter restarts with the game, so how far a run's counts reach says
    nothing about when it ran. A file cut short is skipped with a warning, and
    so is a final file overtaken by a later run's snapshot (the final still
    wins: it is the whole step, the snapshot only part of one)."""
    found = {}
    for p in glob.glob(os.path.join(d, "phase*.csv")):
        g = FILE.search(os.path.basename(p))
        if not g:
            continue
        info, why = snapshot_info(p)
        if info is None:
            warn("tracer report: skipping %s: %s" % (os.path.basename(p), why))
            continue
        kind = g.group(3) or "final"
        found.setdefault(int(g.group(1)), []).append(
            dict(path=p, kind=kind, first=info[0], last=info[1], session=info[2],
                 mtime=os.path.getmtime(p)))
    out = {}
    for n in sorted(found):
        files = found[n]
        finals = [f for f in files if f["kind"] == "final"]
        snaps = [f for f in files if f["kind"] in (".partial", ".exit")]
        tests = [f for f in files if f["kind"] == ".selftest"]
        # within a run the key's first term is shared (the session's start),
        # or for files without a session line differs as they were written:
        # an .exit is always written after its run's autosave
        best = max(snaps, key=lambda f: (run_order(f), f["last"], f["kind"] == ".exit"),
                   default=None)
        if finals:
            final = max(finals, key=lambda f: (run_order(f), f["last"]))
            if best is not None and not same_run(best, final) and \
                    run_order(best) > run_order(final):
                warn("tracer report: step %d: using the finished %s over the newer, unfinished"
                     " %s from a later run" % (n, os.path.basename(final["path"]),
                                               os.path.basename(best["path"])))
            best = final
        elif best is None and tests:
            best = tests[0]
        if best is not None:
            out[n] = (best["path"], best["kind"])
    return out


def read_phase(path):
    meta = {}
    rows = []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    body = []
    for ln in lines:
        if ln.startswith("#"):
            g = HDR_PHASE.match(ln)
            if g:
                meta["label"] = g.group(2)
            g = HDR_TICKS.match(ln)
            if g:
                meta.update(ticks=int(g.group(1)), secs=float(g.group(2)),
                            tps=float(g.group(3)), slow=int(g.group(4)),
                            modes=(int(g.group(5)), int(g.group(6)), int(g.group(7))))
        else:
            body.append(ln)
    for r in csv.DictReader(body):
        rows.append(r)
    return meta, rows


def decode(kind, size, old, new):
    """A readable per-execution change from the raw samples."""
    o, n = int(old, 16), int(new, 16)
    if kind == "1" and size == 4:
        a = struct.unpack("<f", struct.pack("<I", o & 0xFFFFFFFF))[0]
        b = struct.unpack("<f", struct.pack("<I", n & 0xFFFFFFFF))[0]
        return "%.6g -> %.6g (%+.6g)" % (a, b, b - a)
    if kind == "1" and size == 8:
        a = struct.unpack("<d", struct.pack("<Q", o))[0]
        b = struct.unpack("<d", struct.pack("<Q", n))[0]
        return "%.6g -> %.6g (%+.6g)" % (a, b, b - a)
    if size in (1, 2, 4, 8):
        bits = size * 8
        sa = o - (1 << bits) if o >> (bits - 1) else o
        sb = n - (1 << bits) if n >> (bits - 1) else n
        return "%d -> %d (%+d)" % (sa, sb, sb - sa)
    return "%s -> %s" % (old, new)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="classify a tracer session")
    ap.add_argument("dir", nargs="?", default=None,
                    help="the phase files (default: <game>\\okami_tracer)")
    ap.add_argument("--out", default=DOCS,
                    help="where classification.csv and trace_summary.md go"
                         " (default: docs/animation)")
    args = ap.parse_args(argv)
    d = args.dir or os.path.join(GAME, "okami_tracer")
    files = pick_files(d)
    if not files:
        sys.exit("no phase files in %s" % d)
    sites = {r["site"]: r for r in csv.DictReader(open(os.path.join(DOCS, "sites.csv"),
                                                       encoding="utf-8"))
             if r["subsystem"] != "library"}
    traced = {r["site"]: r for r in csv.DictReader(open(os.path.join(DOCS, "tracer_sites.csv"),
                                                        encoding="utf-8"))}
    static_path = os.path.join(DOCS, "static_classification.csv")
    static = {}
    if os.path.exists(static_path):
        static = {r["site"]: r for r in csv.DictReader(open(static_path, encoding="utf-8"))}

    agg = collections.defaultdict(lambda: dict(exec=0, changed=0, ticks=0, chg_ticks=0,
                                               max_run=0, max_chg_run=0, ticks_m1=0,
                                               steps=[], shed=False, best=None))
    phases = []
    for n, (path, kind) in files.items():
        meta, rows = read_phase(path)
        phases.append((n, kind, meta, len(rows)))
        for r in rows:
            a = agg[r["site"]]
            for k in ("exec", "changed", "ticks", "chg_ticks", "ticks_m1"):
                a[k] += int(r[k])
            a["max_run"] = max(a["max_run"], int(r["max_run"]))
            mcr = int(r["max_chg_run"])
            if mcr > a["max_chg_run"] or (a["best"] is None and int(r["changed"])):
                a["best"] = (r["kind"], int(r["sample"]), r["last_old"], r["last_new"])
            a["max_chg_run"] = max(a["max_chg_run"], mcr)
            if int(r["changed"]):
                a["steps"].append(n)
            if r["window_state"] == "2":
                a["shed"] = True

    out = []
    counts = collections.Counter()
    decisions = collections.Counter()
    by_sub = collections.defaultdict(collections.Counter)
    for site, s in sites.items():
        t = traced.get(site, {})
        a = agg.get(site)
        if t.get("refused"):
            cls = "untraced"
        elif not a or not a["exec"]:
            cls = "unseen"
        elif not a["changed"]:
            cls = "static"
        elif a["max_chg_run"] >= 8:
            cls = "clock"
        elif a["chg_ticks"] >= 8 and a["chg_ticks"] * 5 >= a["ticks"]:
            cls = "gated-clock"
        else:
            cls = "event"
        ctx = ""
        delta = ""
        if a and a["ticks"]:
            ctx = "60" if a["ticks_m1"] == a["ticks"] else ("30" if a["ticks_m1"] == 0 else "both")
        if a and a["best"]:
            kind, size, old, new = a["best"]
            delta = decode(kind, size, old, new)
        st = static.get(site, {})
        scls, sconf = st.get("static_class", ""), st.get("confidence", "")
        static_clock = scls == "clock" and sconf in ("strong", "medium")
        static_no = scls in ("state", "pointer", "input")
        if cls in ("clock", "gated-clock"):
            decision = "review" if static_no else "patch"
        elif cls in ("event", "static"):
            decision = "review" if static_clock else "exclude"
        elif static_clock:
            decision = "patch-static"
        elif static_no:
            decision = "exclude"
        else:
            decision = "review"
        decisions[decision] += 1
        sub = s["subsystem"].split(":")[0]
        counts[cls] += 1
        by_sub[sub][cls] += 1
        out.append({
            "site": site, "subsystem": s["subsystem"], "shape": s["shape"],
            "function": s["function"], "class": cls, "context": ctx,
            "steps": " ".join(str(x) for x in sorted(set(a["steps"]))) if a else "",
            "exec": a["exec"] if a else 0, "changed": a["changed"] if a else 0,
            "ticks": a["ticks"] if a else 0, "chg_ticks": a["chg_ticks"] if a else 0,
            "max_chg_run": a["max_chg_run"] if a else 0,
            "shed": "yes" if a and a["shed"] else "",
            "delta": delta, "covered_by": s["covered_by"],
            "refused": t.get("refused", ""),
            "static_class": scls, "static_confidence": sconf,
            "static_reason": st.get("reason", ""), "step_at": st.get("step_at", ""),
            "step_op": st.get("step_op", ""), "decision": decision,
        })
    cols = list(out[0].keys())
    with open(os.path.join(args.out, "classification.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)

    classes = ["clock", "gated-clock", "event", "static", "unseen", "untraced"]
    md = ["# Tracer session summary", "",
          "Generated by `tools/tracer_report.py` from `%s`." % d, "",
          "## Route steps", "",
          "| step | file | ticks | seconds | ticks/s | slow s | mode samples other/1/2 | sites ran |",
          "|---|---|---|---|---|---|---|---|"]
    for n, kind, meta, nrows in phases:
        md.append("| %d %s | %s | %s | %.1f | %.2f | %s | %s | %d |" % (
            n, meta.get("label", ""), kind, meta.get("ticks", "?"), meta.get("secs", 0.0),
            meta.get("tps", 0.0), meta.get("slow", "?"),
            "/".join(str(x) for x in meta.get("modes", ())), nrows))
    md += ["", "## Classes", "", "| subsystem | " + " | ".join(classes) + " |",
           "|---|" + "---|" * len(classes)]
    for sub in sorted(by_sub):
        md.append("| %s | %s |" % (sub, " | ".join(str(by_sub[sub][c]) for c in classes)))
    md.append("| **all** | %s |" % " | ".join("**%d**" % counts[c] for c in classes))
    ctxc = collections.Counter(r["context"] for r in out if r["class"] in ("clock", "gated-clock"))
    md += ["", "Clocks by stock context: 30 Hz %d, 60 Hz %d, both %d." % (
        ctxc["30"], ctxc["60"], ctxc["both"]), "",
           "## Decisions", "",
           "patch %d, patch-static %d, exclude %d, review %d." % (
               decisions["patch"], decisions["patch-static"], decisions["exclude"],
               decisions["review"]), ""]
    open(os.path.join(args.out, "trace_summary.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md))
    print("\nwrote classification.csv and trace_summary.md in %s" % args.out)


if __name__ == "__main__":
    main()
