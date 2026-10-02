// The day/night clock. Included once by
// dinput8_proxy.cpp after integer_skip_runtime.h.
//
// The time of day is one dword, main+B20830, 1 800 000 to a day; the lighting
// picks and crossfades its five palettes from it, and NPCs, enemies and events
// ask it whether it is day or night. The day/night controller's update
// (main+4AF780, once per tick from the dispatcher) records the clock as it
// was, then tail-jumps to one of two workers that advance it: the normal
// advance (+100 a tick after a short delay) or a scripted transition (the
// sky change of a brush technique or an event: a fixed number of steps to a
// target time). Both count ticks, so at 120 fps the day took 2.5 minutes
// instead of 10 and every sky change ran in a quarter of its time.
//
// src/day_clock.h (tools/gen_day_clock.py) retargets the two tail jumps at a
// stub each: on a stock tick (frameCounter & mask == 0) it jumps on to the
// worker, otherwise it returns to the dispatcher as the worker would have
// with nothing to do. The update itself still runs every tick, so its record
// of the previous time stays one tick old and the event code that asks "did
// the clock cross X since the last update" sees each crossing exactly once.
// The mask is data (0 = every tick, the stock game): N - 1 for the stock
// context's N, like F1's, and it follows the timer key like the frame clocks.
// tools/verify_day_clock.py proves it offline, running the real update under
// Unicorn against the stock game's.
//
// The field watch: the per-tick hook reads the clock after each tick and
// sorts every tick that changed it into a requested time (the update applied
// one: see the time-lapses below), a normal step (exactly kDayStep), a
// transition step (while the controller's step count is non-zero) or a jump
// (anything else setting the time). Over each status interval the watcher
// turns the normal steps into minutes per in-game day, against the stock 10.0;
// each transition is timed from its start to its last step, against its steps
// (and delay) at the stock rate. Both go on the overlay's third line.
//
// Both are timed in game time: ticks over the rate the game is configured to
// tick at (the patched fps, or with the patch off the stock game's own). Real
// seconds would judge the frame rate, not the fix: when the game falls short
// of its rate, everything in it slows, stock or not. At the 30 ticks/s the game
// gets in the background at 120 fps, real time read a correctly gated clock as
// "4.0x SLOW", and at 90 ticks/s a clock stepping every third tick instead of
// every fourth read OK. The shortfall itself is reported beside the verdict.
//
// The time-lapses. A third path sets the clock and is not gated: a time the
// game requests (the controller's +0x30, the time at +0x2C), which the update
// applies itself before either tail jump. Scripted time-lapses request one on
// every pass of a loop that waits a tick per pass (the task wait, main+4567C0,
// counts real ticks), lerping from the time they started at to a target:
//   * three lerp on the event player's playhead (main+4B0010, 4B0190, 4B0550),
//     which steps by (float)mode * speed * 0.5 a tick and stops at the event's
//     end. The mode byte is pinned at 1 while patched, so at 120 fps the
//     playhead, and every lapse on it, runs at 60 a second, 2x its stock 30;
//   * one lerps on its own count of passes (main+4B0430), so it runs one pass
//     a tick: 4x at 120, 2x at 60.
// The requested jump's call is retargeted at a stub that only counts, so the
// watch knows each tick that applied a request, whatever the time was. A run
// of such ticks is a lapse. It is timed in game time, from the tick of its
// first request to that of its last, against its stock duration: for a lapse
// that began with an event and ended as it finished (on the playhead), the
// playhead's advance over its ticks at the stock 30 a second (at the event's
// speed); for any other, its requests, one per stock tick. An event that
// starts inside a lapse ends it there: the count-driven lapse at 4B0430 is
// followed, in the same function, by one on the playhead.
#include "day_clock.h"

static constexpr int kDcSites = (int)(sizeof(kDayClockSites) / sizeof(kDayClockSites[0]));
static_assert(kDayCounterOffset + 8 * kDcSites <= kDayCodeOffset, "day clock counters");
static_assert(kDayRequestSite < kDcSites, "the requested jump's site");
static uint8_t* g_dcPool = nullptr;
static bool g_dcReady = false;
static int g_dcKept = 0;
static volatile LONG g_dcMaskChanges = 0;  // every write that changed the mask

static void updateDayClock() {
    if (!g_dcPool) {
        return;
    }
    uint8_t mask = 0;
    // Without the stock context (the shadow) or the tick hook the gate stays
    // open: the stock game's rate, never a guess.
    if (g_dcReady && g_fcHooked && g_cfg.fixDayClock && !g_cfg.passthrough && g_fps60 &&
        !g_timerFixMuted && g_shadowOn && g_shadowMode) {
        uint8_t mode = *g_shadowMode;
        if (mode == 1 || mode == 2) {
            unsigned fps = g_fpsImmsFast ? 120u : 60u;
            mask = (uint8_t)(fps / (mode == 1 ? 60u : 30u) - 1u);
        }
    }
    volatile uint8_t* m = g_dcPool + kDayMaskOffset;
    if (*m != mask) {
        *m = mask;
        InterlockedIncrement(&g_dcMaskChanges);
    }
}

static const char* dayClockState() {
    if (!g_cfg.fixDayClock) return "off(ini)";
    if (!g_dcReady || !g_fcHooked) return "NOT INSTALLED";
    if (!g_fps60) return "stock";
    if (g_timerFixMuted) return "MUTED";
    if (!g_shadowOn || !g_shadowMode || (*g_shadowMode != 1 && *g_shadowMode != 2))
        return "NO CONTEXT";
    return "on";
}

// --- the field watch -------------------------------------------------------

// Kept by the game thread, one tick at a time: plain stores, no locks.
struct DayWatch {
    uint32_t prev;  // the clock after the previous tick
    uint8_t ctx;    // the stock game's mode byte on the previous tick
    uint32_t fps;   // the configured tick rate on the previous tick
    bool started;
    bool trOn;      // a transition is running
    uint32_t trCount0, trDelay0, trSteps, trHz;
    uint32_t trTicks, trFps;  // ticks since it started, and the configured rate then
    LONG trChanges0;          // mask and context changes when it started
    LONGLONG trStart;
    uint32_t tick;     // ticks seen
    uint32_t req;      // the request stub's count after the previous tick
    float p;           // the event playhead after the previous tick
    uint32_t evFlags;  // the event player's flags after the previous tick
    // the time-lapse in progress
    bool lpOn, lpFresh, lpDone;  // started with an event; that event finished
    uint32_t lpFirst, lpLast;    // the ticks of its first and last request
    uint32_t lpReqs, lpFrom, lpTo, lpPTicks, lpFps, lpHz;
    double lpPAdv;
    float lpSpeed;
    LONG lpCtx0;
    LONGLONG lpStart, lpEnd;
};
static DayWatch g_dw = {};
static volatile LONG g_dwTicks = 0;  // ticks seen
static volatile LONG g_dwSteps = 0;  // ticks on which the clock moved by exactly kDayStep
static volatile LONG g_dwJumps = 0;  // ticks on which it moved any other way outside a transition
static volatile LONG g_dwReqs = 0;   // ticks on which the update applied a requested time
static volatile LONG g_dwCtxChanges = 0;  // ticks on which the stock context or the rate changed

// The last transition, published by the game thread under a sequence number
// (odd while it writes) so the watcher never reads half of one.
struct DayTransition {
    uint32_t count, delay, steps, hz;
    uint32_t ticks, fps;  // how many ticks it took, at what configured rate
    bool mixed;           // the gate or the context changed while it ran
    double secs;          // real seconds
};
static DayTransition g_dwTr = {};
static volatile LONG g_dwTrSeq = 0;

static bool readDayTransition(DayTransition& out, LONG& seq) {
    for (int tries = 0; tries < 8; tries++) {
        LONG a = g_dwTrSeq;
        MemoryBarrier();
        if (a & 1) {
            continue;
        }
        DayTransition t = g_dwTr;
        MemoryBarrier();
        if (g_dwTrSeq == a) {
            out = t;
            seq = a;
            return true;
        }
    }
    return false;
}

// Finished time-lapses, the last few, so two in one status interval (a lapse
// on its own count, then one on the playhead) are both seen. Each slot's seq
// is 0 while the game thread writes it and n + 1 for the n-th lapse after.
static constexpr uint32_t kDayLapseGap = 8;  // ticks without a request that end a lapse
static constexpr uint32_t kDayLapseMin = 4;  // requests: fewer is a time set, not a lapse
struct DayLapse {
    uint32_t from, to;      // the clock before its first request and after its last
    uint32_t reqs, ticks;   // requests applied, and the ticks from the first to the last
    uint32_t pTicks;        // of those, ticks on which the event playhead advanced
    double pAdv;            // by how much in all
    float speed;            // the event's playback speed when it started
    uint32_t fps, hz;       // the configured tick rate, and the stock context's
    bool onPlayhead;        // began with an event and ended as it finished
    bool mixed;             // the rate or the context changed while it ran
    double secs;            // real seconds
    volatile LONG seq;
};
static DayLapse g_dwLapse[4] = {};
static volatile LONG g_dwLapseN = 0;  // lapses published

static void closeDayLapse(DayWatch& w) {
    w.lpOn = false;
    if (w.lpReqs < kDayLapseMin) {
        return;  // a time set once or twice (sleep, an event), not a lapse
    }
    LONG n = g_dwLapseN;
    DayLapse& l = g_dwLapse[n % 4];
    l.seq = 0;
    MemoryBarrier();
    l.from = w.lpFrom;
    l.to = w.lpTo;
    l.reqs = w.lpReqs;
    l.ticks = w.lpLast - w.lpFirst + 1;
    l.pTicks = w.lpPTicks;
    l.pAdv = w.lpPAdv;
    l.speed = w.lpSpeed;
    l.fps = w.lpFps;
    l.hz = w.lpHz;
    l.onPlayhead = w.lpFresh && w.lpDone && w.lpPTicks && w.lpSpeed > 0.0f;
    l.mixed = g_dwCtxChanges != w.lpCtx0;
    l.secs = (double)(w.lpEnd - w.lpStart) / (double)g_qpcFreq;
    MemoryBarrier();
    l.seq = n + 1;
    MemoryBarrier();
    g_dwLapseN = n + 1;
}

// From the per-tick hook, after the frame counter went up. The clock as the
// previous tick's update left it, so every tick's change is seen once.
static void dayClockOnTick(LONGLONG now) {
    if (!g_dcPool) {
        return;
    }
    const uint8_t* main = g_eng.main;
    uint32_t v = *(const volatile uint32_t*)(main + kDayClockRva);
    const uint8_t* ctl = main + kDayControllerRva;
    uint32_t count = *(const volatile uint16_t*)(ctl + kDayCountOff);
    const uint8_t* ev = main + kDayEventRva;
    float p = *(const volatile float*)(ev + kDayEventPlayheadOff);
    uint32_t fl = *(const volatile uint32_t*)(ev + kDayEventFlagsOff);
    uint32_t req = *(const volatile uint32_t*)(g_dcPool + kDayCounterOffset + 8 * kDayRequestSite);
    DayWatch& w = g_dw;
    uint32_t d = w.started ? v - w.prev : 0;
    uint32_t dr = w.started ? req - w.req : 0;  // requests the last tick's update applied
    uint32_t before = w.prev;
    uint8_t ctx = stockModeByte();
    uint32_t fps = frameClockUHz(0);  // the configured tick rate: patched fps, or stock's own
    if (w.started && (ctx != w.ctx || fps != w.fps)) {
        g_dwCtxChanges = g_dwCtxChanges + 1;
    }
    // the event player over the last tick: an event started (its playhead back
    // to 0, or its done bit cleared), or the one playing finished
    bool evStart = w.started && (p < w.p || ((w.evFlags & kDayEventDone) && !(fl & kDayEventDone)));
    bool evDone = w.started && !(w.evFlags & kDayEventDone) && (fl & kDayEventDone);
    double dp = w.started && !evStart && p > w.p ? (double)p - (double)w.p : 0.0;
    w.ctx = ctx;
    w.fps = fps;
    w.prev = v;
    w.req = req;
    w.p = p;
    w.evFlags = fl;
    w.started = true;
    w.tick++;
    g_dwTicks = g_dwTicks + 1;
    if (dr) {
        // the update applied a time and did nothing else that tick
        g_dwReqs = g_dwReqs + 1;
    } else if (d) {
        if (w.trOn) {
            w.trSteps++;
        } else if (d == kDayStep) {
            g_dwSteps = g_dwSteps + 1;
        } else {
            g_dwJumps = g_dwJumps + 1;
        }
    }
    if (w.trOn) {
        w.trTicks++;  // the ticks after its first, up to and including its last
    }
    if (count && !w.trOn) {
        w.trOn = true;
        w.trCount0 = count;
        w.trDelay0 = *(const volatile uint32_t*)(ctl + kDayDelayOff);
        w.trSteps = 0;
        w.trTicks = 0;
        w.trFps = fps;
        w.trChanges0 = g_dcMaskChanges + g_dwCtxChanges;
        w.trStart = now;
        w.trHz = ctx == 1 ? 60u : 30u;
    } else if (!count && w.trOn) {
        w.trOn = false;
        InterlockedIncrement(&g_dwTrSeq);  // odd: writing
        g_dwTr.count = w.trCount0;
        g_dwTr.delay = w.trDelay0;
        g_dwTr.steps = w.trSteps;
        g_dwTr.hz = w.trHz;
        g_dwTr.ticks = w.trTicks;
        g_dwTr.fps = w.trFps;
        g_dwTr.mixed = g_dcMaskChanges + g_dwCtxChanges != w.trChanges0;
        g_dwTr.secs = (double)(now - w.trStart) / (double)g_qpcFreq;
        InterlockedIncrement(&g_dwTrSeq);  // even: done
    }
    // The time-lapse. The ticks are numbered as the hook sees them: the tick
    // that applied a request is the one before this.
    uint32_t last = w.tick - 1;
    if (w.lpOn && evStart) {
        closeDayLapse(w);  // what ran before an event began is its own lapse
    }
    if (dr) {
        if (!w.lpOn) {
            float speed = *(const volatile float*)(ev + kDayEventSpeedOff);
            w.lpOn = true;
            w.lpFirst = last;
            w.lpReqs = 0;
            w.lpFrom = before;
            w.lpPTicks = 0;
            w.lpPAdv = 0.0;
            w.lpSpeed = speed;
            // an event started with it: playing, and at most a couple of its
            // steps along (the loops start one, then ask for their first time)
            w.lpFresh = !(fl & kDayEventDone) && p < 3.0f * (speed > 1.0f ? speed : 1.0f);
            w.lpDone = false;
            w.lpFps = fps;
            w.lpHz = ctx == 1 ? 60u : 30u;
            w.lpCtx0 = g_dwCtxChanges;
            w.lpStart = now;
        }
        w.lpReqs += dr;
        w.lpLast = last;
        w.lpTo = v;
        w.lpEnd = now;
        // the playhead's advance on the ticks the lapse asked for a time
        if (dp > 0.0) {
            w.lpPTicks++;
            w.lpPAdv += dp;
        }
    }
    if (w.lpOn) {
        w.lpDone = w.lpDone || evDone;
        if (!dr && last - w.lpLast > kDayLapseGap) {
            closeDayLapse(w);
        }
    }
}

// "10.0 min/day (stock 10.0) OK", or how far off. Both measures are
// durations, so smaller than stock is faster. Returns the length written.
static size_t dayVerdict(char* out, size_t n, double got, double stock, double tol,
                         const char* fmt, const char* unit) {
    char a[32], b[32];
    snprintf(a, sizeof(a), fmt, got);
    snprintf(b, sizeof(b), fmt, stock);
    double r = got > 0.0 ? stock / got : 0.0;  // > 1: faster than stock
    int u;
    if (fabs(got - stock) <= tol) {
        u = snprintf(out, n, "%s%s (stock %s) OK", a, unit, b);
    } else if (r > 1.0) {
        u = snprintf(out, n, "%s%s (stock %s) %.1fx FAST", a, unit, b, r);
    } else {
        u = snprintf(out, n, "%s%s (stock %s) %.1fx SLOW", a, unit, b, r > 0.0 ? 1.0 / r : 0.0);
    }
    return u > 0 ? (size_t)u : 0;
}

static LONGLONG g_dcPrevT = 0;
static LONG g_dcPrev[4] = {};  // ticks, steps, jumps, requested at the last interval
static uint32_t g_dcPrevStub[2 * kDcSites] = {};
static uint8_t g_dcPrevMask = 0xFF;
static LONG g_dcPrevChanges = -1;
static LONG g_dcTrSeen = 0;
static LONG g_dcLapseSeen = 0;
static char g_dcRate[128] = "";  // the rate verdict of the last interval that had one
static char g_dcEvent[112] = "";  // the last sky change's or time-lapse's
static SRWLOCK g_dcLock = SRWLOCK_INIT;

static void dayHM(uint32_t v, char* out, size_t n) {
    uint32_t tod = v % kDayUnits;
    snprintf(out, n, "%02u:%02u", tod * 24u / kDayUnits, tod * 24u % kDayUnits * 60u / kDayUnits);
}

// A finished time-lapse against its stock duration, both in game time. On the
// playhead, the stock duration is how long the playhead's advance over its
// ticks takes at the stock 30 a second (at the event's speed): the playhead's
// rate against its stock rate. On its own count, one request per stock tick.
// Returns the stock duration in seconds (0 when the rate or context changed).
static double dayLapseVerdict(char* out, size_t n, const DayLapse& l) {
    char from[8], to[8];
    dayHM(l.from, from, sizeof(from));
    dayHM(l.to, to, sizeof(to));
    double game = l.fps ? (double)l.ticks / l.fps : 0.0;
    double stock = (double)l.reqs / l.hz;
    if (l.onPlayhead) {
        double rate = l.pAdv / l.pTicks * l.fps;  // playhead units per game second
        stock = game * rate / (kDayPlayheadStockRate * l.speed);
    }
    int u = snprintf(out, n, "time-lapse %s>%s ", from, to);
    size_t at = u > 0 && (size_t)u < n ? (size_t)u : n;
    if (l.mixed) {
        snprintf(out + at, n - at, "%.2f s, rate or context changed during it", game);
        return 0.0;
    }
    // its first and last requests are seen on a tick each: 2.5 stock ticks of slack
    dayVerdict(out + at, n - at, game, stock, 2.5 / l.hz, "%.2f", " s");
    return stock;
}

// From the watcher, once per status interval.
static void measureDayClock(LONGLONG now) {
    if (!g_dcPool) {
        return;
    }
    LONG cur[4] = {g_dwTicks, g_dwSteps, g_dwJumps, g_dwReqs};
    uint8_t mask = *(volatile uint8_t*)(g_dcPool + kDayMaskOffset);
    // with the patch off the mask stays 0, so the stock game's own context
    // changes are counted too: one interval must be one context
    LONG changes = g_dcMaskChanges + g_dwCtxChanges;
    const volatile uint32_t* stub = (const volatile uint32_t*)(g_dcPool + kDayCounterOffset);
    uint32_t sd[2 * kDcSites];
    for (int i = 0; i < 2 * kDcSites; i++) {
        uint32_t s = stub[i];
        sd[i] = s - g_dcPrevStub[i];
        g_dcPrevStub[i] = s;
    }
    double secs = g_dcPrevT ? (double)(now - g_dcPrevT) / (double)g_qpcFreq : 0.0;
    bool steady = g_dcPrevT && mask == g_dcPrevMask && changes == g_dcPrevChanges && secs > 0.5;
    uint32_t dt = (uint32_t)(cur[0] - g_dcPrev[0]), ds = (uint32_t)(cur[1] - g_dcPrev[1]),
             dj = (uint32_t)(cur[2] - g_dcPrev[2]), dq = (uint32_t)(cur[3] - g_dcPrev[3]);
    memcpy(g_dcPrev, cur, sizeof(cur));
    g_dcPrevT = now;
    g_dcPrevMask = mask;
    g_dcPrevChanges = changes;
    unsigned n = (unsigned)mask + 1u;
    unsigned hz = stockModeByte() == 1 ? 60u : 30u;
    unsigned fps = frameClockUHz(0);  // the configured tick rate: patched fps, or stock's own
    double stockMin = (double)kDayUnits / kDayStep / hz / 60.0;
    uint32_t v = *(const volatile uint32_t*)(g_eng.main + kDayClockRva);
    char hm[8];
    dayHM(v, hm, sizeof(hm));
    char rate[128] = "";
    if (!steady) {
        // the mask or the context changed inside the interval: rates mixed, no verdict
    } else if (!ds && !dj && !dq) {
        snprintf(rate, sizeof(rate), "clock stopped here");
    } else if (dj || dq) {
        // someone set the time: this interval's rate means nothing
    } else if ((uint64_t)ds * n + 2u * n < dt) {
        snprintf(rate, sizeof(rate), "clock ran %u of %u ticks", ds * n, dt);
    } else {
        // steps per second of game time: dt ticks are dt / fps game seconds
        double minPerDay = (double)kDayUnits / ((double)ds * kDayStep * fps / dt) / 60.0;
        size_t u = dayVerdict(rate, sizeof(rate), minPerDay, stockMin, stockMin * 0.05, "%.1f",
                              " min/day");
        double tps = dt / secs;
        if (tps < fps * 0.92 && u < sizeof(rate)) {
            snprintf(rate + u, sizeof(rate) - u, "; game at %.0f%% speed (%.0f of %u ticks/s)",
                     100.0 * tps / fps, tps, fps);
        }
    }
    if (steady && (ds || dj || dq)) {
        const int r = 2 * kDayRequestSite;
        logf("day clock: %.1f s, %s /%u, %s (clock %u, day %u), %u ticks (%.1f/s of %u):"
             " %u steps, %u requested, %u other; advance stub %.1f>%.1f/s, transition stub"
             " %.1f>%.1f/s, requests %.1f/s%s%s",
             secs, dayClockState(), n, hm, v,
             (unsigned)*(const volatile uint16_t*)(g_eng.main + kDayCountRva), dt, dt / secs, fps,
             ds, dq, dj, sd[0] / secs, sd[1] / secs, sd[2] / secs, sd[3] / secs, sd[r] / secs,
             rate[0] ? ": " : "", rate);
    }
    char event[sizeof(g_dcEvent)] = "";
    DayTransition t;
    LONG seq;
    if (readDayTransition(t, seq) && seq != g_dcTrSeen && seq) {
        g_dcTrSeen = seq;
        double stock = (double)(t.count + t.delay) / (double)t.hz;
        double game = t.fps ? (double)t.ticks / (double)t.fps : 0.0;
        int u = snprintf(event, sizeof(event), "sky change ");
        size_t at = u > 0 && (size_t)u < sizeof(event) ? (size_t)u : sizeof(event);
        if (t.steps != t.count) {
            snprintf(event + at, sizeof(event) - at, "cut short, %u of %u steps in %.2f s", t.steps,
                     t.count, game);
        } else if (t.mixed) {
            snprintf(event + at, sizeof(event) - at, "%.2f s, gate or context changed during it",
                     game);
        } else {
            // the start is seen on a tick, the end on a tick: 2.5 stock ticks of slack
            dayVerdict(event + at, sizeof(event) - at, game, stock, 2.5 / t.hz, "%.2f", " s");
        }
        logf("day clock: sky change of %u steps (+%u delay) at %u Hz stock, %u ticks at %u fps"
             " (%.2f s real): %s", t.count, t.delay, t.hz, t.ticks, t.fps, t.secs, event + at);
    }
    // every time-lapse since the last interval, oldest first; one the game
    // thread has already overwritten (more than four in an interval) is lost
    LONG ln = g_dwLapseN;
    if (ln - g_dcLapseSeen > 4) {
        logf("day clock: %d time-lapses since the last interval were not read",
             (int)(ln - g_dcLapseSeen - 4));
        g_dcLapseSeen = ln - 4;
    }
    for (; g_dcLapseSeen < ln; g_dcLapseSeen++) {
        const DayLapse& slot = g_dwLapse[g_dcLapseSeen % 4];
        LONG want = g_dcLapseSeen + 1;
        if (slot.seq != want) {
            continue;
        }
        MemoryBarrier();
        DayLapse l = slot;
        MemoryBarrier();
        if (slot.seq != want) {
            continue;  // overwritten while it was read
        }
        double stock = dayLapseVerdict(event, sizeof(event), l);
        if (l.onPlayhead) {
            logf("day clock: %s on the playhead: %u requests over %u ticks at %u fps (%.2f s real);"
                 " the playhead +%.1f on %u of them at speed %.2f, %.1f/s against the stock"
                 " %.1f/s; stock %.2f s", event, l.reqs, l.ticks, l.fps, l.secs, l.pAdv,
                 l.pTicks, l.speed, l.pAdv / l.pTicks * l.fps, kDayPlayheadStockRate * l.speed,
                 stock);
        } else {
            logf("day clock: %s on its own count: %u requests over %u ticks at %u fps (%.2f s real),"
                 " one a stock tick at %u Hz; stock %.2f s (the playhead +%.1f on %u of them)",
                 event, l.reqs, l.ticks, l.fps, l.secs, l.hz, stock, l.pAdv, l.pTicks);
        }
    }
    AcquireSRWLockExclusive(&g_dcLock);
    if (rate[0]) {
        memcpy(g_dcRate, rate, sizeof(rate));
    }
    if (event[0]) {
        memcpy(g_dcEvent, event, sizeof(event));
    }
    ReleaseSRWLockExclusive(&g_dcLock);
}

// The overlay's day line; false when the family is not installed.
static bool dayOverlayLine(char* out, size_t n) {
    if (!g_dcPool) {
        return false;
    }
    char hm[8];
    dayHM(*(const volatile uint32_t*)(g_eng.main + kDayClockRva), hm, sizeof(hm));
    AcquireSRWLockShared(&g_dcLock);
    size_t u = (size_t)snprintf(out, n, "DAY %s /%u | %s | %s", dayClockState(),
                                (unsigned)g_dcPool[kDayMaskOffset] + 1u, hm,
                                g_dcRate[0] ? g_dcRate : "measuring...");
    if (g_dcEvent[0] && u < n) {
        snprintf(out + u, n - u, " | %s", g_dcEvent);
    }
    ReleaseSRWLockShared(&g_dcLock);
    return true;
}

static void installDayClock() {
    if (!g_cfg.fixDayClock || g_cfg.passthrough || !g_eng.main || g_dcPool) return;
    if (!g_fcHooked || g_fcStranded || !g_shadowOk ||
        (uint8_t*)g_eng.frameCounter != g_eng.main + kDayFrameCounterRva) {
        logf("day clock: shared tick hook or stock context unavailable, not patched");
        return;
    }
    for (int i = 0; i < kDcSites; i++) {
        if (memcmp(g_eng.main + kDayClockSites[i].rva, kDayClockOrig + 5 * i, 5)) {
            logf("day clock: main+%X differs from main.dll sha1 %s, not patched",
                 kDayClockSites[i].rva, DAY_CLOCK_MAIN_SHA1);
            return;
        }
    }
    uint8_t* pool = allocNear(g_eng.main, kDayPoolSize);
    if (!pool) {
        logf("day clock: no reachable stub pool, not patched");
        return;
    }
    memcpy(pool + kDayCodeOffset, kDayClockCode, sizeof(kDayClockCode));
    bool ok = true;
    for (const auto& f : kDayClockFixups) {
        ok &= putRel32(pool + f.next, g_eng.main + f.target, pool + f.field);
    }
    uint8_t jumps[kDcSites][5];
    GroupWrite writes[kDcSites];
    for (int i = 0; i < kDcSites; i++) {
        const auto& s = kDayClockSites[i];
        jumps[i][0] = kDayClockOrig[5 * i];  // jmp for a tail jump, call for the request
        ok &= putRel32(g_eng.main + s.rva + 5, pool + s.stub, jumps[i] + 1);
        writes[i] = {g_eng.main + s.rva, jumps[i], kDayClockOrig + 5 * i, 5};
    }
    if (!ok) {
        freeNear(pool);
        logf("day clock: stub pool out of reach, not patched");
        return;
    }
    pool[kDayMaskOffset] = 0;
    FlushInstructionCache(GetCurrentProcess(), pool, kDayPoolSize);
    bool installed = false;
    for (int attempt = 0; attempt < 32; attempt++) {
        bool safe = suspendOthers();
        for (int t = 0; t < g_susCount && safe; t++) {
            for (const auto& s : kDayClockSites) {
                DWORD64 start = (DWORD64)(g_eng.main + s.rva);
                if (g_susRip[t] > start && g_susRip[t] < start + 5) {
                    safe = false;
                    break;
                }
            }
        }
        if (!safe) {
            resumeOthers();
            Sleep(1);
            continue;
        }
        for (int i = 0; i < kDcSites; i++) {
            safe &= memcmp(g_eng.main + kDayClockSites[i].rva, kDayClockOrig + 5 * i, 5) == 0;
        }
        if (safe) {
            g_dcPool = pool;
            g_dcKept = writeGroup(writes, kDcSites);
            g_dcReady = g_dcKept == kDcSites;
            installed = true;
        }
        resumeOthers();
        break;
    }
    if (!g_dcKept) {
        g_dcPool = nullptr;
        freeNear(pool);
    }
    // A partial rollback keeps its pool forever with the mask at zero: every
    // jump left in goes through a stub that runs its worker on every tick, and
    // the request's stub always runs the setter.
    logf("day clock: %d/%d sites retargeted (the tail jumps, the requested jump's call), %s;"
         " stock: %u a tick = %.1f min a day at 30 Hz; follows the timer key %s",
         g_dcKept, kDcSites, g_dcReady ? "ready" : installed ? "inactive after write failure"
                                                             : "not patched",
         kDayStep, (double)kDayUnits / kDayStep / 30.0 / 60.0, g_cfg.timerToggleName);
}

// Offline: map main.dll without executing game code, use the real installer,
// export its bytes for Unicorn (tools/verify_day_clock.py), check the mask for
// every combination of mode and switch, run the field watch through a
// simulated clock, and fail every write in turn.
extern "C" __declspec(dllexport) int OkamiDayClockSelfTest(const char* mainPath,
                                                           const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) return 2;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixDayClock = true;
    g_cfg.fixIntegerSkips = false;
    g_cfg.fixFrameClocks = false;  // the day clock needs only the shared tick hook
    g_cfg.fixFramePhases = false;
    g_cfg.passthrough = false;
    if (!tick || !resolveFrameConfig(tick)) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    installFrameClocks();
    installShadowMode();
    installDayClock();
    if (!g_dcReady) {
        fprintf(rep, "FAIL install\n");
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\npool %p\n", (void*)m, (void*)g_dcPool);
    int fails = 0;
    uint8_t installedCode[kDayPoolSize - kDayCodeOffset];
    memcpy(installedCode, g_dcPool + kDayCodeOffset, sizeof(installedCode));
    snprintf(path, sizeof(path), "%s\\pool.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fails += fwrite(g_dcPool, 1, kDayPoolSize, f) != kDayPoolSize;
        fclose(f);
    } else fails++;
    snprintf(path, sizeof(path), "%s\\sites.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& s : kDayClockSites) fails += fwrite(g_eng.main + s.rva, 1, 5, f) != 5;
        fclose(f);
    } else fails++;
    // the mask, for every combination of the switches it follows
    snprintf(path, sizeof(path), "%s\\modes.csv", outDir);
    if (FILE* f = fopen(path, "w")) {
        fprintf(f, "fps,mode,enabled,muted,shadow,hook,complete,mask\n");
        for (int fps : {30, 60, 120}) for (int mode : {0, 1, 2, 3})
        for (int enabled : {0, 1}) for (int muted : {0, 1})
        for (int shadow : {0, 1}) for (int hook : {0, 1}) for (int complete : {0, 1}) {
            g_fps60 = fps != 30;
            g_fpsImmsFast = fps == 120;
            *g_shadowMode = (uint8_t)mode;
            g_shadowOn = shadow != 0;
            g_cfg.fixDayClock = enabled != 0;
            g_timerFixMuted = muted;
            g_fcHooked = hook != 0;
            g_dcReady = complete != 0;
            frameClockOnTick();
            fprintf(f, "%d,%d,%d,%d,%d,%d,%d,%u\n", fps, mode, enabled, muted, shadow, hook,
                    complete, (unsigned)g_dcPool[kDayMaskOffset]);
        }
        fclose(f);
    } else fails++;
    fails += memcmp(installedCode, g_dcPool + kDayCodeOffset, sizeof(installedCode)) != 0;
    // The field watch, on a clock driven the way the gated game drives it:
    // 120 ticks a second, +100 on every Nth. The overlay's verdicts must read
    // stock at /4, 4x fast with the gate open, "stopped" with the clock held,
    // and a 90-step transition must take its stock 3 s.
    {
        if (!g_qpcFreq) g_qpcFreq = 10000000;
        g_cfg.fixDayClock = true;
        g_fcHooked = g_dcReady = g_shadowOn = true;
        g_fps60 = 1;
        g_fpsImmsFast = true;
        *g_shadowMode = 2;
        g_timerFixMuted = 0;
        volatile uint32_t* clock = (volatile uint32_t*)(g_eng.main + kDayClockRva);
        volatile uint16_t* count = (volatile uint16_t*)(g_eng.main + kDayControllerRva + kDayCountOff);
        volatile uint32_t* target = (volatile uint32_t*)(g_eng.main + kDayControllerRva + kDayTargetOff);
        volatile uint32_t* delay = (volatile uint32_t*)(g_eng.main + kDayControllerRva + kDayDelayOff);
        *clock = 900000;
        *count = 0;
        *delay = 0;
        g_dw = DayWatch{};
        g_dcRate[0] = g_dcEvent[0] = 0;
        g_dcPrevT = 0;
        LONGLONG t = 1000;
        LONGLONG dtick = g_qpcFreq / 120;  // real time per tick: the game keeping up
        unsigned stride = 0;               // nonzero: a broken gate, stepping every stride-th tick
        uint32_t fc = 0;
        // The requested jump, the event player and a scripted time-lapse, as
        // the game has them: a lapse is a task that makes one pass, then waits
        // `every` ticks (1: the task wait counts real ticks, as it does now).
        const uint8_t* ctlBase = g_eng.main + kDayControllerRva;
        volatile uint8_t* reqFlag = (volatile uint8_t*)(ctlBase + kDayRequestOff);
        volatile uint32_t* reqValue = (volatile uint32_t*)(ctlBase + kDayRequestValueOff);
        volatile uint32_t* applied =
            (volatile uint32_t*)(g_dcPool + kDayCounterOffset + 8 * kDayRequestSite);
        uint8_t* ev = g_eng.main + kDayEventRva;
        volatile float* playhead = (volatile float*)(ev + kDayEventPlayheadOff);
        volatile float* evSpeed = (volatile float*)(ev + kDayEventSpeedOff);
        volatile uint32_t* evFlags = (volatile uint32_t*)(ev + kDayEventFlagsOff);
        volatile uint8_t* real = (volatile uint8_t*)g_eng.modeByte;
        uint8_t realWas = *real;
        *reqFlag = 0;
        *playhead = 0.0f;
        *evSpeed = 1.0f;
        *evFlags = kDayEventDone;
        float evLen = 0.0f;
        float fixedStep = 0.0f;  // nonzero: a playhead fixed to step this much a tick
        bool taskFirst = false;  // the lapse's task before the dispatcher in the tick, or after
        struct {
            int kind;    // 0 none, 1 on the playhead, 2 on its own count
            bool then;   // a count, then one on the playhead (main+4B0310)
            uint32_t from, to;
            int passes, n, every, wait;
            float len;
        } lp = {};
        auto request = [&](uint32_t v) {
            *reqValue = v;
            *reqFlag = 1;
        };
        auto startEvent = [&](float len) {  // main+481A10
            *playhead = 0.0f;
            *evSpeed = 1.0f;
            *evFlags = 0;
            evLen = len;
        };
        auto lerp = [&](double f) { return lp.from + (uint32_t)((double)(lp.to - lp.from) * f); };
        auto lapseTask = [&]() {
            if (!lp.kind || lp.wait-- > 0) {
                return;
            }
            lp.wait = lp.every - 1;
            if (lp.kind == 2) {
                if (lp.passes < lp.n) {
                    request(lerp((double)++lp.passes / lp.n));
                    return;
                }
                if (!lp.then) {
                    request(lp.to);  // the time it lapsed to
                    lp.kind = 0;
                    return;
                }
                lp.kind = 1;  // the same function goes on to one on the playhead
                lp.passes = 0;
                lp.from = *clock;
                lp.to += 90000;
            }
            if (!lp.passes) {
                startEvent(lp.len);
            } else if (*evFlags & kDayEventDone) {
                request(lp.to);  // main+4AF030
                lp.kind = 0;
                return;
            }
            lp.passes++;
            request(lerp(*playhead / lp.len));
        };
        auto eventStep = [&]() {  // main+476A16: P += mode * speed * 0.5, stopping at the end
            if (*evFlags & kDayEventDone) {
                return;
            }
            float step = fixedStep ? fixedStep : (float)*real * *evSpeed * 0.5f;
            if (*playhead + step >= evLen) {
                *evFlags = *evFlags | kDayEventDone;
            } else {
                *playhead = *playhead + step;
            }
        };
        // one tick of the game, in its order: flower_tick's increment (the
        // hook: the mask, then the watch's look at the clock), then the
        // dispatcher's update, which applies a requested time (through the
        // request stub: its count) or on a stock tick runs the worker, then
        // the event player and the lapse's task
        auto run = [&](int ticks, bool advance) {
            for (int i = 0; i < ticks; i++) {
                fc++;
                t += dtick;
                updateDayClock();
                dayClockOnTick(t);
                if (taskFirst) {
                    lapseTask();
                }
                uint8_t msk = g_dcPool[kDayMaskOffset];
                if (*reqFlag) {
                    *applied = *applied + 1;
                    *clock = *reqValue;
                    *reqFlag = 0;
                } else if (stride ? fc % stride == 0 : (fc & msk) == 0) {
                    if (*count) {
                        if (*delay) {
                            *delay = *delay - 1;
                        } else {
                            *clock = *clock + (uint32_t)((int32_t)(*target - *clock) / (int32_t)*count);
                            *count = (uint16_t)(*count - 1);
                        }
                    } else if (advance) {
                        *clock = *clock + kDayStep;
                    }
                }
                eventStep();
                if (!taskFirst) {
                    lapseTask();
                }
            }
        };
        // a lapse from hh:mm, run to its end and the gap after it
        auto lapse = [&](int kind, int hh, int mm, int n, float len, int every) {
            *clock = *clock - *clock % kDayUnits + (uint32_t)(hh * 60 + mm) * kDayUnits / 1440u;
            lp = {};
            lp.kind = kind;
            lp.from = *clock;
            lp.to = *clock - *clock % kDayUnits + kDayUnits;  // to midnight
            lp.n = n;
            lp.len = len;
            lp.every = every;
            for (int i = 0; i < 4000 && lp.kind; i++) {
                run(1, false);
            }
            run(2 * kDayLapseGap, false);
        };
        auto lastLapse = [&](int back, char* out, size_t sz) {
            const DayLapse& l = g_dwLapse[(g_dwLapseN - 1 - back) % 4];
            out[0] = 0;
            if (g_dwLapseN > back) {
                dayLapseVerdict(out, sz, l);
            }
            return l.onPlayhead;
        };
        updateDayClock();
        bool maskOk = g_dcPool[kDayMaskOffset] == 3;
        measureDayClock(t);
        run(600, true);
        measureDayClock(t);
        char line[200];
        dayOverlayLine(line, sizeof(line));
        // 150 steps from 12:00; the last is seen by the next interval's first tick
        bool okStock = strstr(line, "DAY on /4 | 12:12 | 10.1 min/day (stock 10.0) OK") != nullptr;
        fprintf(rep, "%s watch at /4: %s\n", okStock ? "ok  " : "FAIL", line);
        // the timer key: gate open at 120, a mask change inside the interval
        // (no verdict), then a steady one
        g_timerFixMuted = 1;
        run(600, true);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okMixed = strstr(line, "10.1 min/day (stock 10.0) OK") != nullptr;
        run(600, true);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okFast = strstr(line, "DAY MUTED /1") && strstr(line, "2.5 min/day (stock 10.0) 4.0x FAST");
        fprintf(rep, "%s watch muted: %s (mixed interval kept the last verdict: %d)\n",
                okFast && okMixed ? "ok  " : "FAIL", line, (int)okMixed);
        g_timerFixMuted = 0;
        run(600, false);
        measureDayClock(t);
        run(600, false);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okStopped = strstr(line, "clock stopped here") != nullptr;
        fprintf(rep, "%s watch held: %s\n", okStopped ? "ok  " : "FAIL", line);
        // a sky change: 90 steps to 18:00 after a 2-tick delay, at /4
        *target = *clock - *clock % kDayUnits + 1350000;
        *delay = 2;
        *count = 90;
        run(4 * 92 + 8, false);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okTr = strstr(line, "sky change 3.07 s (stock 3.07) OK") && *clock % kDayUnits == 1350000;
        fprintf(rep, "%s watch transition: %s\n", okTr ? "ok  " : "FAIL", line);
        // and one cut short: the count cleared half-way
        *target = *clock + 90000;
        *count = 60;
        run(4 * 30, false);
        *count = 0;
        run(8, false);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okCut = strstr(line, "sky change cut short, 30 of 60 steps") != nullptr;
        fprintf(rep, "%s watch cut short: %s\n", okCut ? "ok  " : "FAIL", line);
        // The game short of its rate. In the background it gets 30 ticks a
        // second at the 120 configuration: the gate is right (a step every
        // 4th tick), so the verdict must be OK, with the shortfall beside it.
        // In real time this read 40 min/day, "4.0x SLOW".
        dtick = g_qpcFreq / 30;
        run(150, true);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okBack = strstr(line, "DAY on /4") &&
                      strstr(line, "min/day (stock 10.0) OK; game at 25% speed (30 of 120 ticks/s)");
        fprintf(rep, "%s watch at 30 ticks/s: %s\n", okBack ? "ok  " : "FAIL", line);
        // A gate stepping every 3rd tick where it should every 4th, while the
        // game makes 90 ticks a second: 30 steps a real second, which in real
        // time read as the stock 10.0 min/day, OK. In game time it is 1.3x fast.
        dtick = g_qpcFreq / 90;
        stride = 3;
        run(450, true);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        // (7.6: the watch sees each step on the tick after, so 149 of the 150)
        bool okHidden = strstr(line, "min/day (stock 10.0) 1.3x FAST; game at 75% speed"
                                     " (90 of 120 ticks/s)") != nullptr;
        fprintf(rep, "%s watch, wrong gate at 90 ticks/s: %s\n", okHidden ? "ok  " : "FAIL", line);
        stride = 0;
        // a whole sky change at 30 ticks a second: 3.07 s of game time (12.3 s real)
        g_dcEvent[0] = 0;
        *target = *clock - *clock % kDayUnits + 450000;
        *delay = 2;
        *count = 90;
        dtick = g_qpcFreq / 30;
        run(4 * 92 + 8, false);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okTrSlow = strstr(line, "sky change 3.07 s (stock 3.07) OK") != nullptr;
        fprintf(rep, "%s watch transition at 30 ticks/s: %s\n", okTrSlow ? "ok  " : "FAIL", line);
        // and one with the timer key pressed half-way (the gate opens): no verdict
        dtick = g_qpcFreq / 120;
        *target = *clock + 90000;
        *count = 60;
        run(4 * 30, false);
        g_timerFixMuted = 1;
        run(40, false);
        g_timerFixMuted = 0;
        run(8, false);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okTrMixed = strstr(line, "gate or context changed during it") != nullptr;
        fprintf(rep, "%s watch transition across the timer key: %s\n", okTrMixed ? "ok  " : "FAIL",
                line);
        // Time-lapses at 120 fps, the real mode byte pinned at 1 as the patch
        // pins it. One on the playhead over an 81-tick event (2.7 s stock):
        // the playhead steps 0.5 a tick, so it ends in half its stock time.
        *real = 1;
        char lap[sizeof(g_dcEvent)], lap2[sizeof(g_dcEvent)];
        LONG lapsesWere = g_dwLapseN;
        lapse(1, 22, 45, 0, 81.0f, 1);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okLpHead = strstr(line, "| time-lapse 22:45>00:00 1.36 s (stock 2.72) 2.0x FAST") &&
                        g_dwLapseN == lapsesWere + 1 && lastLapse(0, lap, sizeof(lap));
        fprintf(rep, "%s watch time-lapse on the playhead: %s\n", okLpHead ? "ok  " : "FAIL", line);
        // the same with its task before the dispatcher in the tick
        taskFirst = true;
        lapse(1, 22, 45, 0, 81.0f, 1);
        taskFirst = false;
        bool okLpOrder = lastLapse(0, lap, sizeof(lap)) && strstr(lap, "2.0x FAST");
        fprintf(rep, "%s watch time-lapse, task first in the tick: %s\n", okLpOrder ? "ok  " : "FAIL",
                lap);
        // a playhead that steps at its stock rate (0.25 a tick at 120): OK
        fixedStep = 0.25f;
        lapse(1, 22, 45, 0, 81.0f, 1);
        fixedStep = 0.0f;
        bool okLpFixed = lastLapse(0, lap, sizeof(lap)) && strstr(lap, "22:45>00:00 2.71 s") &&
                         strstr(lap, ") OK");
        fprintf(rep, "%s watch time-lapse, playhead at its stock rate: %s\n",
                okLpFixed ? "ok  " : "FAIL", lap);
        // one on its own count, 60 passes and the time it lapsed to: one a
        // tick, 4x; with a wait of 4 ticks a pass (a stock-tick wait), OK
        lapse(2, 20, 0, 60, 0.0f, 1);
        bool okLpCount = !lastLapse(0, lap, sizeof(lap)) &&
                         strstr(lap, "time-lapse 20:00>00:00 0.51 s (stock 2.03) 4.0x FAST");
        lapse(2, 20, 0, 60, 0.0f, 4);
        bool okLpCountFixed = !lastLapse(0, lap2, sizeof(lap2)) && strstr(lap2, "(stock 2.03) OK");
        fprintf(rep, "%s watch time-lapse on its own count: %s; waiting 4 ticks a pass: %s\n",
                okLpCount && okLpCountFixed ? "ok  " : "FAIL", lap, lap2);
        // a count with an unrelated event playing all through: its count decides
        startEvent(1e6f);
        run(40, false);
        lapse(2, 20, 0, 60, 0.0f, 1);
        bool okLpBusy = !lastLapse(0, lap, sizeof(lap)) && strstr(lap, "4.0x FAST");
        fprintf(rep, "%s watch time-lapse on its own count during an event: %s\n",
                okLpBusy ? "ok  " : "FAIL", lap);
        *evFlags = kDayEventDone;
        // main+4B0310: 30 passes on its own count, then an event and a lapse on
        // its playhead. Two lapses, split where the event starts, both logged.
        lapsesWere = g_dwLapseN;
        *clock = *clock - *clock % kDayUnits + 1080u * kDayUnits / 1440u;
        lp = {};
        lp.kind = 2;
        lp.then = true;
        lp.from = *clock;
        lp.to = *clock + 90000;
        lp.n = 30;
        lp.len = 45.0f;
        lp.every = 1;
        for (int i = 0; i < 4000 && lp.kind; i++) {
            run(1, false);
        }
        run(2 * kDayLapseGap, false);
        bool countPart = !lastLapse(1, lap, sizeof(lap)), headPart = lastLapse(0, lap2, sizeof(lap2));
        bool okLpSplit = g_dwLapseN == lapsesWere + 2 && countPart && headPart &&
                         strstr(lap, "4.0x FAST") && strstr(lap2, "2.0x FAST");
        measureDayClock(t);  // both logged
        fprintf(rep, "%s watch count then playhead (4B0310): %s, then %s\n",
                okLpSplit ? "ok  " : "FAIL", lap, lap2);
        // a time set once (sleep): no lapse, and the interval has no rate verdict
        run(600, true);
        measureDayClock(t);
        lapsesWere = g_dwLapseN;
        char rateWas[sizeof(g_dcRate)];
        memcpy(rateWas, g_dcRate, sizeof(rateWas));
        request(*clock + 300000);
        run(600, true);
        measureDayClock(t);
        bool okLpOnce = g_dwLapseN == lapsesWere && strcmp(rateWas, g_dcRate) == 0 && rateWas[0];
        fprintf(rep, "%s watch, a time set once: no lapse, the rate verdict kept (%s)\n",
                okLpOnce ? "ok  " : "FAIL", g_dcRate);
        // With the patch off (F9) the gate is open and the rate is the stock
        // game's own: 30 a second in mode 2, 60 in mode 1, where a stock day
        // takes 5 minutes. An interval in which the stock game changes its own
        // mode mixes the two and gets no verdict.
        g_fps60 = 0;
        g_shadowOn = false;
        *real = 2;
        dtick = g_qpcFreq / 30;
        run(150, true);  // the switch
        measureDayClock(t);
        run(150, true);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okStock30 = strstr(line, "DAY stock /1") && strstr(line, "min/day (stock 10.0) OK") &&
                         !strstr(line, "speed");
        fprintf(rep, "%s watch stock 30 Hz: %s\n", okStock30 ? "ok  " : "FAIL", line);
        char before[sizeof(g_dcRate)];  // the verdict, not the line: the time of day moves on
        memcpy(before, g_dcRate, sizeof(before));
        run(75, true);
        *real = 1;
        dtick = g_qpcFreq / 60;
        run(150, true);
        measureDayClock(t);
        bool okStockMixed = strcmp(before, g_dcRate) == 0;
        run(300, true);
        measureDayClock(t);
        dayOverlayLine(line, sizeof(line));
        bool okStock60 = strstr(line, "min/day (stock 5.0) OK") && !strstr(line, "speed");
        fprintf(rep, "%s watch stock 60 Hz: %s (the mixed interval kept the last verdict: %d)\n",
                okStock60 && okStockMixed ? "ok  " : "FAIL", line, (int)okStockMixed);
        // and time-lapses in the stock game (mode 2, 30 ticks a second): the
        // playhead steps 1 a tick and the count makes one pass a tick, stock
        *real = 2;
        dtick = g_qpcFreq / 30;
        run(60, false);
        lapse(1, 22, 45, 0, 81.0f, 1);
        bool okLpStockHead = lastLapse(0, lap, sizeof(lap)) && strstr(lap, "22:45>00:00") &&
                             strstr(lap, ") OK");
        lapse(2, 20, 0, 60, 0.0f, 1);
        bool okLpStockCount = !lastLapse(0, lap2, sizeof(lap2)) && strstr(lap2, ") OK");
        fprintf(rep, "%s watch time-lapses in the stock game: %s; %s\n",
                okLpStockHead && okLpStockCount ? "ok  " : "FAIL", lap, lap2);
        *real = realWas;
        g_fps60 = 1;
        g_shadowOn = true;
        fprintf(rep, "%s mask\n", maskOk ? "ok  " : "FAIL");
        fails += !okStock + !okMixed + !okFast + !okStopped + !okTr + !okCut + !maskOk + !okBack +
                 !okHidden + !okTrSlow + !okTrMixed + !okStock30 + !okStockMixed + !okStock60 +
                 !okLpHead + !okLpOrder + !okLpFixed + !okLpCount + !okLpCountFixed + !okLpBusy +
                 !okLpSplit + !okLpOnce + !okLpStockHead + !okLpStockCount;
        g_dcPool[kDayMaskOffset] = 0;
    }
    for (int i = 0; i < kDcSites; i++) {
        const auto& s = kDayClockSites[i];
        uint8_t want[5] = {kDayClockOrig[5 * i]};
        fails += !putRel32(g_eng.main + s.rva + 5, g_dcPool + s.stub, want + 1);
        fails += memcmp(want, g_eng.main + s.rva, 5) != 0;
    }
    // Every failed write, including a failed undo, must leave the jumps that
    // stay in going through a neutral stub, and the pool allocated for them.
    g_cfg.fixDayClock = true;
    g_fcHooked = true;
    g_shadowOn = true;
    *g_shadowMode = 2;
    g_timerFixMuted = 0;
    g_fps60 = 1;
    g_fpsImmsFast = true;
    int cases = 0;
    g_faultLoop = true;  // no protection change a write, no thread snapshot an install
    for (int rest = 0; rest <= 1; rest++) for (int k = 0; k < kDcSites; k++) {
        for (int i = 0; i < kDcSites; i++)
            fails += !writeProtected(g_eng.main + kDayClockSites[i].rva, kDayClockOrig + 5 * i, 5);
        freeNear(g_dcPool);
        g_dcPool = nullptr;
        g_dcReady = false;
        g_dcKept = 0;
        g_writeCount = 0;
        g_writeFailAt = k;
        g_writeFailRest = rest != 0;
        installDayClock();
        g_writeFailAt = -1;
        g_writeFailRest = false;
        frameClockOnTick();
        cases++;
        fails += g_dcReady || g_dcKept != (rest ? k : 0);
        fails += g_writeCount != (rest && k ? k + 2 : 2 * k + 1);
        fails += g_dcKept ? (!g_dcPool || g_dcPool[kDayMaskOffset] != 0) : g_dcPool != nullptr;
        for (int i = 0; i < kDcSites; i++) {
            const auto& s = kDayClockSites[i];
            uint8_t want[5];
            memcpy(want, kDayClockOrig + 5 * i, 5);
            if (i < g_dcKept) {
                want[0] = kDayClockOrig[5 * i];
                fails += !putRel32(g_eng.main + s.rva + 5, g_dcPool + s.stub, want + 1);
            }
            fails += memcmp(want, g_eng.main + s.rva, 5) != 0;
        }
    }
    g_faultLoop = false;
    fprintf(rep, "failed-write cases %d\n%s (%d failures)\n", cases, fails ? "FAIL" : "PASS",
            fails);
    fclose(rep);
    return fails ? 1 : 0;
}
