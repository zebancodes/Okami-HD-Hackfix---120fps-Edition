#!/usr/bin/env python
"""Take a harness run apart offline.

    .venv/Scripts/python tools/harness_report.py            # all rates found
    .venv/Scripts/python tools/harness_report.py 30 120     # compare two
    .venv/Scripts/python tools/harness_report.py --dir .    # traces elsewhere

The patch writes two kinds of file into the game directory:

    okami_harness.csv           one summary line per rate, the baseline store
    okami_harness_<N>fps.csv    the full per-tick trace of the last run at <N>

The in-game report compares summaries, which is enough to answer "do these two
rates move her the same distance". This reads the *traces*, which is what you
need to answer why they do not: where in the run the two curves separate, what
the per-tick velocity was doing at that moment, and whether the run is even
trustworthy.

It deliberately says nothing about whether a fix is correct. It reports what
happened, including the reasons a run should be thrown away -- a stall, a rate
that missed its target, a jump that never occurred, a slope term that stayed at
zero the whole time.
"""
import argparse
import csv
import math
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from gamedir import GAME
except Exception:
    GAME = "."


def load_trace(path):
    rows = []
    meta = ""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                meta = line[1:].strip()
                continue
            if line.startswith("tick,"):
                hdr = line.strip().split(",")
                break
        else:
            return None
        for rec in csv.DictReader(f, fieldnames=hdr):
            try:
                rows.append({
                    "ms": float(rec["ms"]),
                    "x": float(rec["x"]), "y": float(rec["y"]), "z": float(rec["z"]),
                    "hs": float(rec["hspeed"]), "vy": float(rec["vy"]),
                    "b0": float(rec["b0"]), "launch": float(rec["launch"]),
                    "facing": float(rec.get("facing") or 0.0),
                    "ofsx": float(rec.get("ofsx") or 0.0),
                    "ofsz": float(rec.get("ofsz") or 0.0),
                    "animrate": float(rec.get("animrate") or 0.0),
                    "st": int(rec["state"], 16), "sub": int(rec["sub"], 16),
                })
            except (ValueError, TypeError, KeyError):
                continue
    return {"meta": meta, "rows": rows, "path": path}


def derive(tr):
    rows = tr["rows"]
    if len(rows) < 2:
        return None
    d = 0.0
    cum, spd = [], []
    for i, r in enumerate(rows):
        if i:
            dx = r["x"] - rows[i - 1]["x"]
            dz = r["z"] - rows[i - 1]["z"]
            step = (dx * dx + dz * dz) ** 0.5
            dt = (r["ms"] - rows[i - 1]["ms"]) / 1000.0
            if step < 300.0:
                d += step
            spd.append(step / dt if dt > 1e-6 else 0.0)
        else:
            spd.append(0.0)
        cum.append(d)
    # pl00+0xE48 is the displacement the movement code asked for on that tick,
    # so travelled/requested is 1.0 while she is free and collapses the moment
    # she is against geometry. Nothing else in a run reveals that: the speed
    # field, the states and the tick rate all look perfectly healthy.
    want_sum = got_sum = 0.0
    blocked_from = None
    low = 0
    for i in range(1, len(rows)):
        want = rows[i - 1]["hs"]
        if want <= 0.02:
            low = 0
            continue
        dx = rows[i]["x"] - rows[i - 1]["x"]
        dz = rows[i]["z"] - rows[i - 1]["z"]
        step = (dx * dx + dz * dz) ** 0.5
        if step > 300.0:
            continue
        want_sum += want
        got_sum += step
        if step < want * 0.5:
            low += 1
            if low >= 5 and blocked_from is None:
                blocked_from = rows[i - 4]["ms"]
        else:
            low = 0
    dts = [rows[i]["ms"] - rows[i - 1]["ms"] for i in range(1, len(rows))]
    dts = [d for d in dts if d > 0.0] or [0.0]  # a clock that went backwards is not an interval
    mean = sum(dts) / len(dts)
    air = [r for r in rows if r["st"] == 3]
    return {
        "n": len(rows), "span": rows[-1]["ms"] - rows[0]["ms"],
        "rate": (len(rows) - 1) * 1000.0 / max(1e-6, rows[-1]["ms"] - rows[0]["ms"]),
        "cum": cum, "spd": spd, "total": d,
        "dt_mean": mean, "dt_min": min(dts), "dt_max": max(dts),
        "peak": max(spd), "peak_ground": max([s for s, r in zip(spd, rows) if r["st"] != 3] or [0]),
        "air_ticks": len(air),
        "air_ms": (air[-1]["ms"] - air[0]["ms"]) if air else 0.0,
        "rise": (max(r["y"] for r in air) - air[0]["y"]) if air else 0.0,
        "b0_max": max(abs(r["b0"]) for r in rows),
        "launch_max": max(r["launch"] for r in rows),
        "hs_max": max(r["hs"] for r in rows),
        "subs": sorted({r["sub"] for r in rows}),
        # which way she actually went. The script drives the stick, but the
        # direction she turns towards comes from main+B6B134, which the pad task
        # may compute before the injected stick is written -- so this is
        # measured, not assumed.
        "travel": math.atan2(rows[-1]["z"] - rows[0]["z"], rows[-1]["x"] - rows[0]["x"]),
        "facing0": rows[0]["facing"], "facing1": rows[-1]["facing"],
        # main+3A77B9 adds these onto the transform once per tick, so their sum
        # is the distance they contributed over the run. If that differs between
        # rates, the offsets are a per-tick displacement that was never scaled.
        "ofs_sum": sum((r["ofsx"] ** 2 + r["ofsz"] ** 2) ** 0.5 for r in rows),
        "ofs_peak": max([(r["ofsx"] ** 2 + r["ofsz"] ** 2) ** 0.5 for r in rows] or [0.0]),
        "anim_mean": (sum(r["animrate"] for r in rows) / len(rows)) if rows else 0.0,
        "anim_peak": max([r["animrate"] for r in rows] or [0.0]),
        "move_eff": (got_sum / want_sum) if want_sum > 1e-6 else 1.0,
        "want_sum": want_sum, "got_sum": got_sum, "blocked_from": blocked_from,
    }


def at(tr, dv, ms):
    """cumulative distance and height at a wall-clock time"""
    rows = tr["rows"]
    best = 0
    for i, r in enumerate(rows):
        if r["ms"] <= ms:
            best = i
        else:
            break
    return dv["cum"][best], rows[best]["y"] - rows[0]["y"]


def name(rate):
    if rate < 0:
        r = -rate - 1
        return "stock, previous run" if r == 0 else "%d fps, previous run" % r
    return "stock (unpatched)" if rate == 0 else "%d fps" % rate


def warn(tr, dv, want):
    out = []
    if dv["total"] < 5.0:
        out.append("she did not move (%.1f units) -- run is INVALID, do not compare"
                   % dv["total"])
    if dv["move_eff"] < 0.70:
        out.append("BLOCKED: travelled %.0f%% of what the movement code asked for"
                   " (%.1f of %.1f units)%s. Every distance in this run is wrong."
                   " The per-tick speed field is still good -- a wall does not change"
                   " what the controller requests."
                   % (dv["move_eff"] * 100.0, dv["got_sum"], dv["want_sum"],
                      "" if dv["blocked_from"] is None
                      else ", first pinned at %.0f ms" % dv["blocked_from"]))
    elif dv["move_eff"] < 0.92:
        out.append("travelled %.0f%% of the requested distance -- she brushed something"
                   % (dv["move_eff"] * 100.0))
    if dv["dt_max"] > dv["dt_mean"] * 3 and dv["dt_max"] > 20:
        out.append("stall: longest tick %.1f ms against %.1f mean" % (dv["dt_max"], dv["dt_mean"]))
    if want and want > 0 and abs(dv["rate"] - want) > want * 0.10:
        out.append("achieved %.1f ticks/s against a nominal %d" % (dv["rate"], want))
    if not dv["air_ticks"]:
        out.append("never airborne -- the jump half of this run means nothing")
    elif dv["launch_max"] <= 5.0:
        out.append("launch velocity peaked at %.2f: the STANDING jump variant."
                   " Above 30 fps that is the main+3B41E6 bug, unless she really was"
                   " standing still" % dv["launch_max"])
    if dv["b0_max"] < 0.01:
        out.append("pl00+0xB0 stayed at 0: flat ground only, so the slope terms"
                   " (FixSlopeTerm, the takeoff term) were NOT exercised")
    return out


def sparkline(vals, width=60, height=9):
    if not vals:
        return []
    hi = max(vals) or 1.0
    buckets = [[] for _ in range(width)]
    for i, v in enumerate(vals):
        buckets[min(width - 1, i * width // len(vals))].append(v)
    col = [(sum(b) / len(b) if b else 0.0) for b in buckets]
    rows = []
    for r in range(height, 0, -1):
        line = "".join("#" if c >= hi * (r - 0.5) / height else " " for c in col)
        rows.append("  %7.1f |%s" % (hi * r / height, line))
    rows.append("          +" + "-" * width)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rates", nargs="*", type=int, help="e.g. 30 120 (default: all found)")
    ap.add_argument("--dir", default=GAME)
    args = ap.parse_args()

    found = {}
    # <rate>fps.csv is the newest run at that rate and <rate>fps.prev.csv the one
    # before it, which the patch keeps now rather than overwriting. The previous
    # one is listed as its own entry so the two can be compared directly -- that
    # pair IS the noise floor.
    for path in sorted(glob.glob(os.path.join(args.dir, "okami_harness_*.csv"))):
        base = os.path.basename(path)
        prev = base.endswith(".prev.csv")
        tail = base[:-9].split("_")[-1] + ".csv" if prev else base.split("_")[-1]
        if tail == "stock.csv":
            # the Passthrough=1 control: nominally 30 fps, but NOT the same
            # measurement as a patched 30 fps run, so it gets its own key
            rate = 0
        elif tail.endswith("fps.csv"):
            try:
                rate = int(tail.replace("fps.csv", ""))
            except ValueError:
                continue
        else:
            continue
        tr = load_trace(path)
        if tr and tr["rows"]:
            found[-rate - 1 if prev else rate] = tr
    if not found:
        sys.exit("no okami_harness_*fps.csv in %s -- run the harness (F3) in game first"
                 % args.dir)

    rates = args.rates or sorted(found)
    rates = [r for r in rates if r in found]

    derived = {}
    for r in rates:
        dv = derive(found[r])
        if not dv:
            continue
        derived[r] = dv
        print("==== %s ====  %s" % (name(r), found[r]["meta"]))
        print("  %d ticks over %.0f ms -> %.1f ticks/s%s"
              % (dv["n"], dv["span"], dv["rate"],
                 "" if r == 0 else " (nominal %d)" % r))
        print("  tick interval %.2f ms mean, %.2f-%.2f" % (dv["dt_mean"], dv["dt_min"], dv["dt_max"]))
        print("  distance %.1f, peak %.1f/s (ground %.1f/s), peak per-tick %.3f"
              % (dv["total"], dv["peak"], dv["peak_ground"], dv["hs_max"]))
        print("  airborne %d ticks / %.0f ms, rise %.1f, launch peak %.2f"
              % (dv["air_ticks"], dv["air_ms"], dv["rise"], dv["launch_max"]))
        print("  sub-states %s, |b0| max %.3f"
              % (",".join("%02X" % x for x in dv["subs"]), dv["b0_max"]))
        print("  travelled %.3f rad from start, facing %.3f -> %.3f"
              % (dv["travel"], dv["facing0"], dv["facing1"]))
        print("  travelled %.0f%% of the distance the movement code asked for"
              % (dv["move_eff"] * 100.0))
        print("  pl+0x10A0/A8 offsets added to the transform: %.1f units total,"
              " peak %.4f/tick" % (dv["ofs_sum"], dv["ofs_peak"]))
        print("  anim rate (pl+0xF54): mean %.4f, peak %.4f"
              % (dv["anim_mean"], dv["anim_peak"]))
        for w in warn(found[r], dv, r if r >= 0 else -r - 1):
            print("  !! %s" % w)
        print("  world speed over the run (units/s):")
        for ln in sparkline(dv["spd"]):
            print("  " + ln)
        print()

    if len(rates) >= 2:
        a, b = rates[0], rates[-1]
        da, db = derived.get(a), derived.get(b)
        if da and db:
            print("==== %s vs %s ====" % (name(a), name(b)))
            if (a == 0) != (b == 0):
                print("  (one side is the unpatched game -- this is the control comparison)")
            print("  %-8s %10s %10s %9s   %8s %8s" % ("t(ms)", "dist:%s" % name(a),
                                                      "dist:%s" % name(b), "delta",
                                                      "h:%s" % name(a), "h:%s" % name(b)))
            end = int(min(da["span"], db["span"]))
            for ms in range(200, end + 1, 400):
                ca, ha = at(found[a], da, ms)
                cb, hb = at(found[b], db, ms)
                d = (cb - ca) * 100.0 / ca if ca > 0.5 else 0.0
                print("  %-8d %10.1f %10.1f %+8.1f%%   %8.1f %8.1f" % (ms, ca, cb, d, ha, hb))
            d = (db["total"] - da["total"]) * 100.0 / da["total"] if da["total"] > 0.5 else 0.0
            print("  %-8s %10.1f %10.1f %+8.1f%%" % ("TOTAL", da["total"], db["total"], d))
            dt = abs(da["travel"] - db["travel"])
            if dt > math.pi:
                dt = 2 * math.pi - dt
            if dt > 0.25:
                print("  !! these runs travelled %.2f rad APART -- same distance in a"
                      " different direction is not the same experiment" % dt)
            print("  rise     %10.1f %10.1f %+8.1f%%"
                  % (da["rise"], db["rise"],
                     (db["rise"] - da["rise"]) * 100.0 / da["rise"] if da["rise"] > 0.1 else 0.0))
            print("  launch   %10.2f %10.2f   <- 5.4 is the running jump, 4.2 the standing one"
                  % (da["launch_max"], db["launch_max"]))
            print("  ofs sum  %10.1f %10.1f   <- per-tick position offsets; equal means scaled"
                  % (da["ofs_sum"], db["ofs_sum"]))
            print("  animrate %10.4f %10.4f   <- mean pl+0xF54" % (da["anim_mean"], db["anim_mean"]))
            print("\n  0% on TOTAL means the two rates move her the same distance in the same")
            print("  real time. Compare it against the spread between two runs at the SAME")
            print("  rate before reading anything into it.")


if __name__ == "__main__":
    main()
