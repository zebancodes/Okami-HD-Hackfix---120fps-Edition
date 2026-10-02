#!/usr/bin/env python3
"""Name the instruction that writes Amaterasu's horizontal speed, at runtime.

    .venv/Scripts/python tools/frida_watch_speed.py            # +0xE48, the speed
    .venv/Scripts/python tools/frida_watch_speed.py --off 0xE54 # vertical velocity
    .venv/Scripts/python tools/frida_watch_speed.py --airborne  # only while in the air

Start the game first, get in-game, then run this and play. It prints every
distinct instruction that writes the field, as `main+RVA`, with a hit count and
the range of values it wrote.

Why this exists
---------------
Static analysis found the wrong subsystem three times running: the ground speed
target was patched twice with no measurable effect, while the jump trace showed
the airborne speed frozen at a value nothing in the patched path produces. The
decompiler answers "what does this code do"; it does not answer "which of the
2000 places that touch this field actually wrote it just now". A hardware
watchpoint does, with no guessing at all.

x86-64 has four debug registers, so this uses one slot on every thread and
reports whichever one fires. The handler does no I/O -- it accumulates into a
map that is drained once a second -- so the game keeps running at speed.

Safety: this only reads. It sets no breakpoints on code, patches nothing, and
writes nothing into the process. Detaching or killing this script leaves the
game untouched.
"""
import argparse
import sys
import time

try:
    import frida
except ImportError:
    sys.exit("needs frida: .venv/Scripts/python -m pip install frida")

JS = r"""
const PLAYER_SLOT = %(slot)d;      // main+B6B2D0 holds the pl00 pointer
const FIELD = %(field)d;           // offset of the watched field
const AIRBORNE_ONLY = %(airborne)d;
const STATE = 0xE35;               // pl00+0xE35: 03 while airborne

const main = Process.getModuleByName('main.dll');
send({kind: 'info', text: 'main.dll at ' + main.base});

let player = NULL;
let watched = NULL;
const hits = {};       // pc -> [count, min, max, lastState]

const armedThreads = {};

// Debug registers are per thread, so every thread needs its own slot and any
// thread created after the first pass would be missed. Re-arming on a timer is
// cheaper than tracking thread creation and covers the same ground.
function arm(addr, announce) {
    let fresh = 0, err = null;
    Process.enumerateThreads().forEach(function (t) {
        if (armedThreads[t.id] === addr.toString()) {
            return;
        }
        try {
            t.setHardwareWatchpoint(0, addr, 4, 'w');
            armedThreads[t.id] = addr.toString();
            fresh++;
        } catch (e) {
            err = e.message;
        }
    });
    if (fresh && announce) {
        send({kind: 'info', text: 'watchpoint on ' + addr + ' armed on ' + fresh +
                                  ' new thread(s)' + (err ? ' (some failed: ' + err + ')' : '')});
    }
    return fresh;
}

Process.setExceptionHandler(function (details) {
    if (details.type !== 'single-step' && details.type !== 'breakpoint') {
        return false;
    }
    if (watched.isNull()) {
        return false;
    }
    const pc = details.context.pc;
    // only claim exceptions from the module we are watching
    const rva = pc.sub(main.base);
    const r = rva.toUInt32();
    if (r > main.size) {
        return false;
    }
    let v = 0.0, st = 0;
    try {
        v = watched.readFloat();
        st = player.add(STATE).readU8();
    } catch (e) {}
    if (AIRBORNE_ONLY && st !== 3) {
        return true;
    }
    const key = '0x' + r.toString(16).toUpperCase();
    const e = hits[key];
    if (e === undefined) {
        hits[key] = [1, v, v, st];
    } else {
        e[0]++;
        if (v < e[1]) e[1] = v;
        if (v > e[2]) e[2] = v;
        e[3] = st;
    }
    return true;
});

// the player object comes and goes with the level, so re-arm when it moves
setInterval(function () {
    let p;
    try {
        p = main.base.add(PLAYER_SLOT).readPointer();
    } catch (e) {
        return;
    }
    if (p.isNull()) {
        return;
    }
    if (!p.equals(player)) {
        player = p;
        watched = p.add(FIELD);
        for (const k in armedThreads) { delete armedThreads[k]; }
        send({kind: 'info', text: 'player object at ' + p});
    }
    arm(watched, true);
}, 500);

// Disarming is not optional. The exception handler dies with the script, but
// the debug registers do not -- they live in the threads. Detaching while a
// watchpoint is still armed means the next write raises a debug exception with
// nothing left to handle it, and the game hangs. That is exactly what happened
// the first time this was run.
rpc.exports = {
    disarm: function () {
        let n = 0;
        Process.enumerateThreads().forEach(function (t) {
            try {
                t.unsetHardwareWatchpoint(0);
                n++;
            } catch (e) {}
        });
        for (const k in armedThreads) { delete armedThreads[k]; }
        watched = NULL;
        player = NULL;
        return n;
    }
};

setInterval(function () {
    const keys = Object.keys(hits);
    if (keys.length === 0) {
        return;
    }
    const rows = keys.map(function (k) {
        return {pc: k, n: hits[k][0], lo: hits[k][1], hi: hits[k][2], st: hits[k][3]};
    });
    keys.forEach(function (k) { delete hits[k]; });
    send({kind: 'hits', rows: rows});
}, 1000);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", default="okami.exe")
    ap.add_argument("--off", default="0xE48", help="player field offset to watch")
    ap.add_argument("--slot", default="0xB6B2D0", help="main.dll RVA of the player pointer")
    ap.add_argument("--airborne", action="store_true",
                    help="only record writes taken while pl00+0xE35 == 3")
    ap.add_argument("--seconds", type=int, default=0, help="0 = until interrupted")
    args = ap.parse_args()

    try:
        session = frida.attach(args.process)
    except frida.ProcessNotFoundError:
        sys.exit("%s is not running -- start the game and get in-game first" % args.process)

    totals = {}

    def on_message(msg, _data):
        if msg["type"] == "error":
            print("  script error: %s" % msg.get("description"), flush=True)
            return
        p = msg["payload"]
        if p["kind"] == "info":
            print("  %s" % p["text"], flush=True)
            return
        for r in p["rows"]:
            t = totals.setdefault(r["pc"], [0, r["lo"], r["hi"], r["st"]])
            t[0] += r["n"]
            t[1] = min(t[1], r["lo"])
            t[2] = max(t[2], r["hi"])
            t[3] = r["st"]
            print("  main+%-8s n=%-6d value %8.4f .. %8.4f   state %02X"
                  % (r["pc"][2:], t[0], t[1], t[2], t[3]), flush=True)

    script = session.create_script(JS % {
        "slot": int(args.slot, 16),
        "field": int(args.off, 16),
        "airborne": 1 if args.airborne else 0,
    })
    script.on("message", on_message)
    script.load()
    print("watching pl00+%s -- play, then Ctrl-C" % args.off, flush=True)
    try:
        if args.seconds:
            time.sleep(args.seconds)
        else:
            sys.stdin.read()
    except KeyboardInterrupt:
        pass
    finally:
        # disarm BEFORE detaching, or the game hangs on its next write
        try:
            exports = getattr(script, "exports_sync", None) or script.exports
            n = exports.disarm()
            print("\n  disarmed watchpoint on %d thread(s)" % n, flush=True)
        except Exception as exc:
            print("\n  WARNING: could not disarm (%s) -- the game may hang; "
                  "restart it before playing" % exc, flush=True)
        print("\n==== distinct writers of pl00+%s ====" % args.off)
        for pc, (n, lo, hi, st) in sorted(totals.items(), key=lambda kv: -kv[1][0]):
            print("  main+%-8s n=%-7d value %9.4f .. %9.4f" % (pc[2:], n, lo, hi))
        session.detach()


if __name__ == "__main__":
    main()
