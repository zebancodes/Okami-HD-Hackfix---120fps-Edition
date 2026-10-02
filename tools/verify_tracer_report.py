#!/usr/bin/env python3
"""Check which tracer file tracer_report.py reads for each route step.

Builds tracer sessions in temp directories, file by file as tracerDump writes
them, and runs the real report on each (tracer_report.main with --out, so
nothing under docs/ is touched). Two sites: an early one every file saw, and a
late one only some did; the late site must reach the classification (as a
clock, in that step) exactly when the right file holds it.

  finalized            final + a stale autosave of the same run: the final
  finalized, session   the same with session lines, the autosave's file
                       newer: the final, no warning (one run)
  partial only         the autosave
  exit only            the exit snapshot
  partial + exit       the exit snapshot, which saw the late site after the
                       last autosave did not
  same run, session    the same with session lines, and the files' times the
                       wrong way round: the exit (one run: its counts decide)
  exit cut short       a crash mid-dump: the autosave, with a warning
  newer run            an exit from an earlier run and a newer run's autosave
                       (the frame counter restarted): the newer autosave
  newer run, same      the same, both counts from frame counter 0, the newer
    start              run shorter and the only one to see the late site:
                       the newer autosave (the counters say nothing)
  newer run, same      the same with session lines, and the files' times the
    start, session     wrong way round: the newer session's autosave
  final, newer run     a finished step and a later run's unfinished snapshot:
                       the final, with a warning
  final, newer run,    the same from frame counter 0 in both: the final, with
    same start         a warning

Every case runs twice, with the directory listed in either order. Then, if
the real session is in the game folder, re-runs the report on it and requires
the committed docs/animation/classification.csv and trace_summary.md back byte
for byte.

    .venv/Scripts/python tools/verify_tracer_report.py
Exits non-zero on any mismatch.
"""
import contextlib
import csv
import glob
import io
import os
import sys
import tempfile
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tracer_report  # noqa: E402
from gamedir import GAME  # noqa: E402

COLS = ("site,subsystem,sample,kind,exec,changed,ticks,max_run,chg_ticks,max_chg_run,"
        "ctx,ticks_m1,last_old,last_new,window_state")


def two_sites():
    """two real, traced candidates: one to run in every file, one late"""
    traced = {r["site"]: r for r in csv.DictReader(open(
        os.path.join(tracer_report.DOCS, "tracer_sites.csv"), encoding="utf-8"))}
    out = []
    for r in csv.DictReader(open(os.path.join(tracer_report.DOCS, "sites.csv"),
                                 encoding="utf-8")):
        t = traced.get(r["site"], {})
        if r["subsystem"] != "library" and r["site"] in traced and not t.get("refused"):
            out.append((r["site"], r["subsystem"]))
            if len(out) == 2:
                return out
    sys.exit("no traced sites in docs/animation")


def dump(path, phase, first, last, rows, cut=False, mtime=None, session=None):
    lines = ["# okami tracer phase %d: test step" % phase,
             "# ticks %d (frame counter %d..%d), %.1f s = 30.00 ticks/s, slow 0 s,"
             " mode samples other/1/2 0/0/%d" % (last - first, first, last,
                                                  (last - first) / 30.0, last - first),
             "# sites 2, windows installed 2, shed 0, int3-net hits 0, main.dll sha1 test"]
    if session:
        lines.append("# session %s" % session)
    lines.append(COLS)
    for site, sub, chg in rows:
        run = 40 if chg else 0
        lines.append("%s,%s,4,1,%d,%d,%d,%d,%d,%d,2,0,0,3F800000,1"
                     % (site, sub, 60, run, 60, 60, run, run))
    text = "\n".join(lines) + "\n"
    if cut:
        text = text[:-12]                       # the dump stopped mid-row
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def main():
    (early, esub), (late, lsub) = two_sites()
    before = [(early, esub, True)]              # the early site alone
    after = [(early, esub, True), (late, lsub, True)]   # and the late one
    now = time.time()
    old_run = "2026-09-18T20:00:00.000Z pid 4100"   # two runs of the game, an hour apart
    new_run = "2026-09-18T21:00:00.000Z pid 5200"
    F = dict                                    # one file of a case
    cases = [
        # name, files, the file to read, late site seen, a warning expected
        ("finalized", [F(sfx="", first=1000, last=5000, rows=after, mtime=now),
                       F(sfx=".partial", first=1000, last=3000, rows=before, mtime=now - 100)],
         "", True, False),
        ("finalized, session",
         [F(sfx="", first=1000, last=5000, rows=after, mtime=now - 100, session=new_run),
          F(sfx=".partial", first=1000, last=3000, rows=before, mtime=now, session=new_run)],
         "", True, False),
        ("partial only", [F(sfx=".partial", first=1000, last=3000, rows=before, mtime=now)],
         ".partial", False, False),
        ("exit only", [F(sfx=".exit", first=1000, last=5000, rows=after, mtime=now)],
         ".exit", True, False),
        ("partial + exit",
         [F(sfx=".partial", first=1000, last=3000, rows=before, mtime=now - 100),
          F(sfx=".exit", first=1000, last=5000, rows=after, mtime=now)],
         ".exit", True, False),
        ("same run, session",
         [F(sfx=".partial", first=1000, last=3000, rows=before, mtime=now, session=new_run),
          F(sfx=".exit", first=1000, last=5000, rows=after, mtime=now - 100, session=new_run)],
         ".exit", True, False),
        ("exit cut short",
         [F(sfx=".partial", first=1000, last=3000, rows=before, mtime=now - 100),
          F(sfx=".exit", first=1000, last=5000, rows=after, mtime=now, cut=True)],
         ".partial", False, True),
        ("newer run",
         [F(sfx=".exit", first=1000, last=5000, rows=after, mtime=now - 3600),
          F(sfx=".partial", first=200, last=900, rows=before, mtime=now)],
         ".partial", False, False),
        ("newer run, same start",
         [F(sfx=".exit", first=0, last=5000, rows=before, mtime=now - 3600),
          F(sfx=".partial", first=0, last=900, rows=after, mtime=now)],
         ".partial", True, False),
        ("newer run, same start, session",
         [F(sfx=".exit", first=0, last=5000, rows=before, mtime=now, session=old_run),
          F(sfx=".partial", first=0, last=900, rows=after, mtime=now - 100, session=new_run)],
         ".partial", True, False),
        ("final, newer run",
         [F(sfx="", first=1000, last=5000, rows=after, mtime=now - 3600),
          F(sfx=".partial", first=200, last=900, rows=before, mtime=now)],
         "", True, True),
        ("final, newer run, same start",
         [F(sfx="", first=0, last=5000, rows=after, mtime=now - 3600),
          F(sfx=".partial", first=0, last=900, rows=before, mtime=now)],
         "", True, True),
    ]
    real_glob = glob.glob
    fails = 0
    for name, files, want, late_seen, want_warning in cases:
        d = tempfile.mkdtemp(prefix="okami_tracer_report_")
        for f in files:
            dump(os.path.join(d, "phase03_test_step%s.csv" % f["sfx"]), 3, f["first"], f["last"],
                 f["rows"], f.get("cut", False), f["mtime"], f.get("session"))
        listing = sorted(real_glob(os.path.join(d, "phase*.csv")))
        for order, names in (("listed", listing), ("reversed", listing[::-1])):
            with mock.patch.object(tracer_report.glob, "glob", return_value=names):
                warnings = []
                picked = tracer_report.pick_files(d, warn=warnings.append)
                got = picked.get(3, (None, None))
                kind = {"final": ""}.get(got[1], got[1])
                problems = []
                if kind != want:
                    problems.append("read %s, want %s" % (got[1], want or "final"))
                # the whole report, to see the late site's evidence arrive or not
                out = os.path.join(d, "out_" + order)
                os.makedirs(out)
                with contextlib.redirect_stdout(io.StringIO()):
                    tracer_report.main([d, "--out", out])
            cls = {r["site"]: r for r in csv.DictReader(
                open(os.path.join(out, "classification.csv"), encoding="utf-8"))}
            want_cls = "clock" if late_seen else "unseen"
            if cls[late]["class"] != want_cls or (late_seen and cls[late]["steps"] != "3"):
                problems.append("the late site %s is %s in steps '%s', want %s"
                                % (late, cls[late]["class"], cls[late]["steps"], want_cls))
            if cls[early]["class"] != "clock":
                problems.append("the early site %s is %s" % (early, cls[early]["class"]))
            if bool(warnings) != want_warning:
                problems.append("warnings %s" % (warnings or "none"))
            fails += bool(problems)
            print("%s %-32s %-8s -> %-9s late site %-7s%s%s" % (
                "FAIL" if problems else "ok  ", name, order, got[1], cls[late]["class"],
                "" if not warnings else " | " + warnings[0].split(": ", 1)[1],
                (" | " + "; ".join(problems)) if problems else ""))

    # the real session, if there is one: the committed outputs must come back
    real = os.path.join(GAME, "okami_tracer")
    if os.path.isdir(real):
        out = tempfile.mkdtemp(prefix="okami_tracer_real_")
        with contextlib.redirect_stdout(io.StringIO()):
            tracer_report.main([real, "--out", out])
        same = []
        for fn in ("classification.csv", "trace_summary.md"):
            # the summary names the directory it was given, spelled as given
            a, b = [[ln for ln in open(os.path.join(p, fn), encoding="utf-8").read().splitlines()
                     if not ln.startswith("Generated by")]
                    for p in (out, tracer_report.DOCS)]
            same.append(a == b)
        ok = all(same)
        fails += not ok
        print("%s the real session in %s: classification.csv %s, trace_summary.md %s"
              % ("ok  " if ok else "FAIL", real, "identical" if same[0] else "DIFFERS",
                 "identical" if same[1] else "DIFFERS"))
    print("\n%s" % ("FAILED (%d)" % fails if fails else "tracer file selection verified"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
