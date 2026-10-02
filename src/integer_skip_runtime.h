// F1 UI prototype. Included once by dinput8_proxy.cpp after the shared tick hook.
// The generated detours are installed once. Only the mask byte changes at run time.
#include "integer_skips.h"

static constexpr int kIsWindows = (int)(sizeof(kIntegerSkipWindows) / sizeof(kIntegerSkipWindows[0]));
static uint8_t* g_isPool = nullptr;
static bool g_isReady = false;
static int g_isKept = 0;
static volatile LONG g_integerFixMuted = 0;
static volatile LONG g_isMaskChanges = 0;  // every write that changed the mask or g_isOn
static volatile LONG g_isOn = 0;  // the mask follows the stock context (not stock, muted, unknown)

static void updateIntegerSkips() {
    if (!g_isPool) {
        return;
    }
    uint8_t mask = 0;
    LONG on = 0;
    // A pinned real mode byte cannot tell gameplay from native-60 menus.
    // Without the shadow or the tick hook, keep the original instruction active.
    if (g_isReady && g_fcHooked && g_cfg.fixIntegerSkips && !g_cfg.passthrough &&
        g_fps60 && !g_integerFixMuted && g_shadowOn && g_shadowMode) {
        uint8_t mode = *g_shadowMode;
        if (mode == 1 || mode == 2) {
            unsigned fps = g_fpsImmsFast ? 120u : 60u;
            mask = (uint8_t)(fps / (mode == 1 ? 60u : 30u) - 1u);
            on = 1;
        }
    }
    // at 60 fps in a 60 Hz menu the mask is 0 both on and muted, so the
    // switch between them is a change too
    volatile uint8_t* m = g_isPool + kIntegerSkipMaskOffset;
    if (*m != mask || g_isOn != on) {
        *m = mask;
        g_isOn = on;
        InterlockedIncrement(&g_isMaskChanges);
    }
}

static const char* integerSkipState() {
    if (!g_cfg.fixIntegerSkips) return "off(ini)";
    if (!g_isReady || !g_fcHooked) return "NOT INSTALLED";
    if (!g_fps60) return "stock";
    if (g_integerFixMuted) return "MUTED";
    if (!g_shadowOn || !g_shadowMode || (*g_shadowMode != 1 && *g_shadowMode != 2))
        return "NO CONTEXT";
    return "on";
}

// The in-game check. Every stub counts, per site, the ticks its step was
// reached on and the ticks it counted on (a slot of kIntegerSkipCounterStride
// bytes per site from kIntegerSkipCounterOffset: {ticks, counted, the frame
// counter at its last pass, passes}). Emulation proves the gate offline; only
// the game shows how often each site really runs. A site reached only on ticks
// the mask skips would never count. So over each status interval with one mask
// throughout, the ticks it counted on must be the ticks it ran on divided by
// N = mask + 1. In stock 30 fps (F9) or muted, N is 1 and the counted rate is
// the stock baseline for that site.
// Ticks, not passes: a site in a loop is passed once per element, and a loop
// that drops an element on the tick its count runs out (the bestiary grid,
// 41B7DD) is passed more often on the ticks before a count than after. A cell
// with delay D is passed 2D-1 times at /2 and counts D times, so per pass the
// share read 0.565 in game, a false WRONG, while every cell took its D stock
// ticks. Per tick the share is 1/N whatever the population does. Passes are
// still counted, for the log, where they show a loop as passes per tick.
// "Throughout" is exact: a menu can switch the stock context to 60 Hz and back
// inside one interval, which the mask at its two ends does not show, so every
// change of the mask is counted and an interval with any gets no verdict.
//
// That check alone is circular: it holds the gate to the N the patch chose from
// the shadow mode byte, so a wrong context passes it, which is the kind of error
// the 60 Hz menus once were. So each site the tracer session (Passthrough: the
// stock game) saw run at one stock rate only carries that rate in the header
// (stockHz, 30 or 60), and while the patch is on, its N must also be
// fps / stockHz. That is the context as the stock game had it, not as the
// shadow says. A site seen at both rates, or never seen, gets the gate check
// only, and the line says how many were held to the trace. A mismatch is not
// proof the patch is wrong (the route may simply never have shown that site in
// this context), so it is reported as CONTEXT, apart from a gate that is WRONG,
// and neither reads OK.
static constexpr int kIsSites = (int)(sizeof(kIntegerSkipSites) / sizeof(kIntegerSkipSites[0]));
static constexpr int kIsSlot = (int)(kIntegerSkipCounterStride / 4);  // dwords per site
static_assert(kIntegerSkipCounterOffset + kIntegerSkipCounterStride * kIsSites <=
                  kIntegerSkipCodeOffset, "integer skip counters");
static uint32_t g_isPrev[kIsSites][3];  // ticks, counted, passes at the last interval
static LONGLONG g_isPrevT = 0;
static uint8_t g_isPrevMask = 0xFF;
static LONG g_isPrevChanges = -1;
static char g_isLine[200] = "";  // the overlay's second line, from the last interval
static SRWLOCK g_isLineLock = SRWLOCK_INIT;

// From the watcher, once per status interval.
static void measureIntegerSkips(LONGLONG now) {
    if (!g_isPool) {
        return;
    }
    const volatile uint32_t* c = (const volatile uint32_t*)(g_isPool + kIntegerSkipCounterOffset);
    uint8_t mask = *(volatile uint8_t*)(g_isPool + kIntegerSkipMaskOffset);
    bool on = g_isOn != 0;
    LONG changes = g_isMaskChanges;
    double secs = g_isPrevT ? (double)(now - g_isPrevT) / (double)g_qpcFreq : 0.0;
    bool steady = g_isPrevT && mask == g_isPrevMask && changes == g_isPrevChanges && secs > 0.5;
    unsigned n = (unsigned)mask + 1u;
    unsigned fps = g_fpsImmsFast ? 120u : 60u;
    int live = 0, wrong = 0, traced = 0, strange = 0;
    double loE = 1e9, hiE = 0.0, loA = 1e9, hiA = 0.0;
    uint32_t badSite = 0, oddSite = 0;
    unsigned oddHz = 0;
    double badGot = 0.0, badWant = 0.0;
    char sites[640] = "";
    size_t su = 0;
    for (int i = 0; i < kIsSites; i++) {
        int k = kIntegerSkipSites[i].counter;
        const volatile uint32_t* s = c + kIsSlot * k;
        uint32_t ticks = s[0], counted = s[1], passes = s[3];
        uint32_t e = ticks - g_isPrev[k][0], a = counted - g_isPrev[k][1],
                 p = passes - g_isPrev[k][2];
        g_isPrev[k][0] = ticks;
        g_isPrev[k][1] = counted;
        g_isPrev[k][2] = passes;
        if (!steady || e == 0) {
            continue;
        }
        live++;
        double es = e / secs, as = a / secs, want = (double)e / n;
        loE = es < loE ? es : loE;
        hiE = es > hiE ? es : hiE;
        loA = as < loA ? as : loA;
        hiA = as > hiA ? as : hiA;
        // the gate counts on the ticks that are a multiple of N: within one
        // of e/N for a site run on every tick, and within one per burst for
        // a site run in bursts
        double slack = want * 0.05 > 2.0 ? want * 0.05 : 2.0;
        if (fabs((double)a - want) > slack && !wrong++) {
            badSite = kIntegerSkipSites[i].site;
            badGot = as;
            badWant = want / secs;
        }
        // the context, against the stock game's own record of this site
        unsigned hz = kIntegerSkipSites[i].stockHz;
        if (on && hz) {
            traced++;
            if (fps / hz != n && !strange++) {
                oddSite = kIntegerSkipSites[i].site;
                oddHz = hz;
            }
        }
        if (su < sizeof(sites) - 40) {
            su += (size_t)snprintf(sites + su, sizeof(sites) - su, " %X %.1f>%.1f",
                                   kIntegerSkipSites[i].site, es, as);
            if (p > e + e / 20 && su < sizeof(sites)) {  // a loop: passes per tick
                su += (size_t)snprintf(sites + su, sizeof(sites) - su, " x%.1f", (double)p / e);
            }
        }
    }
    char bad[160] = "";
    size_t bu = 0;
    if (wrong) {
        bu += (size_t)snprintf(bad, sizeof(bad), " | %d WRONG: %X %.1f/s, want %.1f", wrong,
                               badSite, badGot, badWant);
    }
    if (strange && bu < sizeof(bad)) {
        bu += (size_t)snprintf(bad + bu, sizeof(bad) - bu,
                               " | %d CONTEXT: %X ran /%u, stock trace %u Hz = /%u", strange,
                               oddSite, n, oddHz, fps / oddHz);
    }
    if (on && !wrong && !strange && bu < sizeof(bad)) {
        snprintf(bad + bu, sizeof(bad) - bu, " OK, %d of %d vs stock trace", traced, live);
    }
    g_isPrevT = now;
    g_isPrevMask = mask;
    g_isPrevChanges = changes;
    if (!steady) {
        return;  // the mask changed inside the interval: mixed rates, no verdict
    }
    const char* state = integerSkipState();
    char line[sizeof(g_isLine)];
    if (!live) {
        snprintf(line, sizeof(line), "INTEGERS %s /%u | no counter ran in the last %.0f s", state,
                 n, secs);
    } else {
        auto range = [](char* out, size_t sz, double lo, double hi) {
            if (hi - lo < 0.5) {
                snprintf(out, sz, "%.1f/s", hi);
            } else {
                snprintf(out, sz, "%.1f-%.1f/s", lo, hi);
            }
        };
        char es[40], as[40];
        range(es, sizeof(es), loE, hiE);
        range(as, sizeof(as), loA, hiA);
        snprintf(line, sizeof(line), "INTEGERS %s /%u | %d live: ran %s, counted %s%s", state, n,
                 live, es, as, bad);
        logf("integer skips: %.1f s, %s /%u, %d live, %d wrong, %d against the stock trace with"
             " %d context mismatch%s (site ticks ran>counted on per s, xK passes a tick in a"
             " loop):%s",
             secs, state, n, live, wrong, traced, strange, strange == 1 ? "" : "es", sites);
    }
    AcquireSRWLockExclusive(&g_isLineLock);
    memcpy(g_isLine, line, sizeof(line));
    ReleaseSRWLockExclusive(&g_isLineLock);
}

// The overlay's second line when no loading screen has it; false when the
// family is not installed.
static bool integerOverlayLine(char* out, size_t n) {
    if (!g_isPool) {
        return false;
    }
    AcquireSRWLockShared(&g_isLineLock);
    if (g_isLine[0]) {
        snprintf(out, n, "%s", g_isLine);
    } else {
        snprintf(out, n, "INTEGERS %s | measuring...", integerSkipState());
    }
    ReleaseSRWLockShared(&g_isLineLock);
    return true;
}

static void installIntegerSkips() {
    if (!g_cfg.fixIntegerSkips || g_cfg.passthrough || !g_eng.main || g_isPool) return;
    if (!g_fcHooked || g_fcStranded || !g_shadowOk ||
        (uint8_t*)g_eng.frameCounter != g_eng.main + kIntegerSkipFrameCounterRva) {
        logf("integer skips: shared tick hook or stock context unavailable, not patched");
        return;
    }
    for (const auto& w : kIntegerSkipWindows) {
        if (w.len < 5 || w.len > 32 ||
            memcmp(g_eng.main + w.rva, kIntegerSkipOrig + w.orig, w.len)) {
            logf("integer skips: main+%X differs from main.dll sha1 %s, not patched",
                 w.rva, INTEGER_SKIPS_MAIN_SHA1);
            return;
        }
    }
    uint8_t* pool = allocNear(g_eng.main, kIntegerSkipPoolSize);
    if (!pool) {
        logf("integer skips: no reachable stub pool, not patched");
        return;
    }
    memcpy(pool + kIntegerSkipCodeOffset, kIntegerSkipCode, sizeof(kIntegerSkipCode));
    bool ok = true;
    for (const auto& f : kIntegerSkipFixups) {
        if (f.next) {
            ok &= putRel32(pool + f.next, g_eng.main + f.target, pool + f.field);
        } else {
            uint64_t target = (uint64_t)(g_eng.main + f.target);
            memcpy(pool + f.field, &target, sizeof(target));
        }
    }
    uint8_t jumps[kIsWindows][32];
    GroupWrite writes[kIsWindows];
    for (int i = 0; i < kIsWindows; i++) {
        const auto& w = kIntegerSkipWindows[i];
        memset(jumps[i], 0x90, w.len);
        jumps[i][0] = 0xE9;
        ok &= putRel32(g_eng.main + w.rva + 5, pool + w.stub, jumps[i] + 1);
        writes[i] = {g_eng.main + w.rva, jumps[i], kIntegerSkipOrig + w.orig, w.len};
    }
    if (!ok) {
        freeNear(pool);
        logf("integer skips: relocation out of reach, not patched");
        return;
    }
    pool[kIntegerSkipMaskOffset] = 0;
    FlushInstructionCache(GetCurrentProcess(), pool, kIntegerSkipPoolSize);
    // Retry if a thread stopped in a displaced window. No code is changed until
    // every suspended instruction pointer is outside the overwritten interiors.
    bool installed = false;
    for (int attempt = 0; attempt < 32; attempt++) {
        bool safe = suspendOthers();
        for (int t = 0; t < g_susCount && safe; t++) {
            for (const auto& w : kIntegerSkipWindows) {
                DWORD64 start = (DWORD64)(g_eng.main + w.rva);
                if (g_susRip[t] > start && g_susRip[t] < start + w.len) {
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
        // Recheck while stopped, before the first write (other patch families
        // may have changed a site since the initial validation).
        for (const auto& w : kIntegerSkipWindows) {
            safe &= memcmp(g_eng.main + w.rva, kIntegerSkipOrig + w.orig, w.len) == 0;
        }
        if (safe) {
            g_isPool = pool;
            g_isKept = writeGroup(writes, kIsWindows);
            g_isReady = g_isKept == kIsWindows;
            installed = true;
        }
        resumeOthers();
        break;
    }
    if (!g_isKept) {
        g_isPool = nullptr;
        freeNear(pool);
    }
    // A partial rollback keeps its pool forever and mask zero, so every
    // remaining jump executes the full original window, without decimation.
    logf("integer skips: %d/%d windows installed, %s; A/B key %s",
         g_isKept, kIsWindows, g_isReady ? "ready" : installed ? "inactive after write failure"
                                                                     : "not patched",
         g_cfg.integerToggleName);
}

// Offline: map main.dll without executing game code, use the real installer,
// export its bytes for Unicorn, and exercise mode and failed-write transitions.
extern "C" __declspec(dllexport) int OkamiIntegerSkipSelfTest(const char* mainPath,
                                                              const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) return 2;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixIntegerSkips = true;
    g_cfg.fixFrameClocks = false;  // F1 must work independently of F5.
    g_cfg.fixFramePhases = false;
    g_cfg.passthrough = false;
    if (!tick || !resolveFrameConfig(tick)) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    installFrameClocks();
    installShadowMode();
    installIntegerSkips();
    if (!g_isReady) {
        fprintf(rep, "FAIL install\n");
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\npool %p\n", (void*)m, (void*)g_isPool);
    int fails = 0;
    uint8_t installedCode[kIntegerSkipPoolSize - kIntegerSkipCodeOffset];
    memcpy(installedCode, g_isPool + kIntegerSkipCodeOffset, sizeof(installedCode));
    snprintf(path, sizeof(path), "%s\\pool.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fails += fwrite(g_isPool, 1, kIntegerSkipPoolSize, f) != kIntegerSkipPoolSize;
        fclose(f);
    } else fails++;
    snprintf(path, sizeof(path), "%s\\windows.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& w : kIntegerSkipWindows)
            fails += fwrite(g_eng.main + w.rva, 1, w.len, f) != w.len;
        fclose(f);
    } else fails++;
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
            g_cfg.fixIntegerSkips = enabled != 0;
            g_integerFixMuted = muted;
            g_fcHooked = hook != 0;
            g_isReady = complete != 0;
            frameClockOnTick();
            fprintf(f, "%d,%d,%d,%d,%d,%d,%d,%u\n", fps, mode, enabled, muted,
                    shadow, hook, complete, (unsigned)g_isPool[kIntegerSkipMaskOffset]);
        }
        fclose(f);
    } else fails++;
    // Toggles changed data only, including every relocated displacement.
    fails += memcmp(installedCode, g_isPool + kIntegerSkipCodeOffset, sizeof(installedCode)) != 0;
    // The measurement's arithmetic, on counters set by hand over 5 s at /4:
    // one site run on every tick and counting on every 4th (right), one run
    // on every tick and never counting (a site on the skipped residues), and
    // one that did not run. Then a mask that changes and comes back inside an
    // interval (a menu's 60 Hz context), which must give no verdict, and a
    // steady interval after it, which must give one again.
    {
        if (!g_qpcFreq) g_qpcFreq = 10000000;
        uint32_t* cnt = (uint32_t*)(g_isPool + kIntegerSkipCounterOffset);
        memset(cnt, 0, kIntegerSkipCounterStride * kIsSites);
        // ticks run on, ticks counted on, and passes (one a tick unless given)
        auto add = [&](int k, uint32_t ticks, uint32_t counted, uint32_t passes = 0) {
            cnt[kIsSlot * k] += ticks;
            cnt[kIsSlot * k + 1] += counted;
            cnt[kIsSlot * k + 3] += passes ? passes : ticks;
        };
        g_isPrevT = 0;
        g_isLine[0] = 0;
        g_fps60 = 1;
        g_fpsImmsFast = true;
        g_cfg.fixIntegerSkips = true;
        g_isReady = g_fcHooked = g_shadowOn = true;
        *g_shadowMode = 2;
        g_integerFixMuted = 0;
        updateIntegerSkips();  // 120 fps, stock 30 Hz: /4
        bool maskOk = g_isPool[kIntegerSkipMaskOffset] == 3;
        LONGLONG t = 1000;
        measureIntegerSkips(t);
        int k0 = kIntegerSkipSites[0].counter, k1 = kIntegerSkipSites[1].counter;
        add(k0, 600, 150);
        add(k1, 600, 0);
        t += 5 * g_qpcFreq;
        measureIntegerSkips(t);
        char want[96];
        snprintf(want, sizeof(want), "1 WRONG: %X 0.0/s, want 30.0", kIntegerSkipSites[1].site);
        bool wrongOk = strstr(g_isLine, "INTEGERS on /4 | 2 live: ran 120.0/s") &&
                       strstr(g_isLine, want);
        // the second site counting too, now: both right
        add(k0, 600, 150);
        add(k1, 600, 150);
        t += 5 * g_qpcFreq;
        measureIntegerSkips(t);
        bool okOk = strstr(g_isLine, "2 live: ran 120.0/s, counted 30.0/s OK") != nullptr;
        char kept[sizeof(g_isLine)];
        memcpy(kept, g_isLine, sizeof(kept));
        // a 60 Hz menu opened and closed inside the interval: /2 and back to
        // /4, so the mask at the two ends agrees, and counts above ticks/4
        *g_shadowMode = 1;
        updateIntegerSkips();
        maskOk = maskOk && g_isPool[kIntegerSkipMaskOffset] == 1;
        *g_shadowMode = 2;
        updateIntegerSkips();
        maskOk = maskOk && g_isPool[kIntegerSkipMaskOffset] == 3;
        add(k0, 600, 158);
        t += 5 * g_qpcFreq;
        measureIntegerSkips(t);
        bool mixedOk = strcmp(kept, g_isLine) == 0;
        add(k0, 600, 150);  // then steady again: a verdict again
        t += 5 * g_qpcFreq;
        measureIntegerSkips(t);
        bool againOk = strstr(g_isLine, "1 live: ran 120.0/s, counted 30.0/s OK") != nullptr;
        // A loop whose population shrinks, the bestiary grid: passed 1.77
        // times a tick, and the cells a count empties are gone from the next
        // tick. It counts on one tick in N: OK. Held to its passes instead
        // (1062 / 4 = 265 against 150) it would read WRONG.
        add(k0, 600, 150, 1062);
        t += 5 * g_qpcFreq;
        measureIntegerSkips(t);
        bool loopOk = strstr(g_isLine, "1 live: ran 120.0/s, counted 30.0/s OK") &&
                      !strstr(g_isLine, "WRONG");
        // Against the stock trace. A site the trace saw only at 60 Hz, gated
        // /4 because the shadow says 30: the gate itself is right (ticks/4),
        // so only the trace can say the context is not.
        int j60 = -1;
        for (int i = 0; i < kIsSites && j60 < 0; i++) {
            if (kIntegerSkipSites[i].stockHz == 60) j60 = i;
        }
        uint32_t s0 = kIntegerSkipSites[0].site, s60 = j60 >= 0 ? kIntegerSkipSites[j60].site : 0;
        int k60 = j60 >= 0 ? kIntegerSkipSites[j60].counter : 0;
        auto interval = [&](int k, uint32_t ticks, uint32_t counted) {
            add(k, ticks, counted);
            t += 5 * g_qpcFreq;
            measureIntegerSkips(t);
        };
        char want2[160];
        interval(k60, 600, 150);
        snprintf(want2, sizeof(want2), "1 live: ran 120.0/s, counted 30.0/s | 1 CONTEXT: %X"
                 " ran /4, stock trace 60 Hz = /2", s60);
        bool ctxOk = j60 >= 0 && kIntegerSkipSites[0].stockHz == 30 && strstr(g_isLine, want2) &&
                     !strstr(g_isLine, "OK");
        // the shadow says 60: /2, an interval for the change, then that site
        // in its own context reads OK, held to the trace
        *g_shadowMode = 1;
        updateIntegerSkips();
        interval(k60, 600, 300);
        interval(k60, 600, 300);
        bool ctx60Ok = strstr(g_isLine, "INTEGERS on /2 | 1 live: ran 120.0/s, counted 60.0/s"
                                        " OK, 1 of 1 vs stock trace") != nullptr;
        // and a site the trace saw only at 30 Hz, gated /2 in that same menu
        interval(k0, 600, 300);
        snprintf(want2, sizeof(want2), "1 CONTEXT: %X ran /2, stock trace 30 Hz = /4", s0);
        bool ctx30Ok = strstr(g_isLine, want2) != nullptr;
        // At 60 fps in the 60 Hz menu the mask is 0 whether the family is on
        // or muted. On: /1 is still held to the trace (60 / 60 Hz = 1).
        g_fpsImmsFast = false;
        updateIntegerSkips();
        interval(k60, 300, 300);
        interval(k60, 300, 300);
        bool on1Ok = strstr(g_isLine, "INTEGERS on /1 | 1 live: ran 60.0/s, counted 60.0/s OK,"
                                      " 1 of 1 vs stock trace") != nullptr;
        // muting there changes no mask, but it is a change: that interval gets
        // no verdict, and muted ones after it none either
        memcpy(kept, g_isLine, sizeof(kept));
        g_integerFixMuted = 1;
        updateIntegerSkips();
        bool maskStill = g_isPool[kIntegerSkipMaskOffset] == 0;
        interval(k60, 300, 300);
        bool muteKept = strcmp(kept, g_isLine) == 0;
        interval(k60, 300, 300);
        bool mutedOk = maskStill && muteKept &&
                       strstr(g_isLine, "INTEGERS MUTED /1 | 1 live: ran 60.0/s, counted 60.0/s") &&
                       !strstr(g_isLine, "OK") && !strstr(g_isLine, "CONTEXT");
        g_integerFixMuted = 0;
        g_fpsImmsFast = true;
        *g_shadowMode = 2;
        updateIntegerSkips();
        fprintf(rep, "measure wrong: %s\nmeasure ok: %s\nmeasure dip kept: %s\n"
                     "measure again: %s\nmeasure a shrinking loop, per tick: %s\nmask: %s\n"
                     "measure context vs trace, 60 Hz site at /4: %s\n"
                     "measure context vs trace, 60 Hz site at /2: %s\n"
                     "measure context vs trace, 30 Hz site at /2: %s\n"
                     "measure context vs trace, /1 at 60 fps: %s\n"
                     "measure muted at an unchanged mask: %s\n",
                wrongOk ? "ok" : "FAIL", okOk ? "ok" : "FAIL", mixedOk ? "ok" : "FAIL",
                againOk ? "ok" : "FAIL", loopOk ? "ok" : "FAIL", maskOk ? "ok" : "FAIL",
                ctxOk ? "ok" : "FAIL", ctx60Ok ? "ok" : "FAIL", ctx30Ok ? "ok" : "FAIL",
                on1Ok ? "ok" : "FAIL", mutedOk ? "ok" : "FAIL");
        fails += !wrongOk + !okOk + !mixedOk + !againOk + !loopOk + !maskOk + !ctxOk + !ctx60Ok +
                 !ctx30Ok + !on1Ok + !mutedOk;
        g_isPool[kIntegerSkipMaskOffset] = 0;
    }
    for (const auto& w : kIntegerSkipWindows) {
        uint8_t want[32];
        memset(want, 0x90, w.len);
        want[0] = 0xE9;
        fails += !putRel32(g_eng.main + w.rva + 5, g_isPool + w.stub, want + 1);
        fails += memcmp(want, g_eng.main + w.rva, w.len) != 0;
    }
    g_cfg.fixIntegerSkips = true;
    g_fcHooked = true;
    g_isReady = true;
    g_shadowOn = true;
    *g_shadowMode = 2;
    g_integerFixMuted = 0;
    g_fps60 = 1;
    g_fpsImmsFast = true;
    // Every failed write, including a failed undo, must leave all remaining
    // detours neutral and their referenced pool allocated.
    g_faultLoop = true;  // no protection change a write, no thread snapshot an install
    for (int rest = 0; rest <= 1; rest++) for (int k = 0; k < kIsWindows; k++) {
        for (const auto& w : kIntegerSkipWindows)
            fails += !writeProtected(g_eng.main + w.rva, kIntegerSkipOrig + w.orig, w.len);
        freeNear(g_isPool);
        g_isPool = nullptr;
        g_isReady = false;
        g_isKept = 0;
        g_writeCount = 0;
        g_writeFailAt = k;
        g_writeFailRest = rest != 0;
        installIntegerSkips();
        g_writeFailAt = -1;
        g_writeFailRest = false;
        frameClockOnTick();
        fails += g_isReady || g_isKept != (rest ? k : 0);
        fails += g_writeCount != (rest && k ? k + 2 : 2 * k + 1);
        fails += g_isKept ? (!g_isPool || g_isPool[kIntegerSkipMaskOffset] != 0)
                          : g_isPool != nullptr;
        for (int i = 0; i < kIsWindows; i++) {
            const auto& w = kIntegerSkipWindows[i];
            uint8_t want[32];
            memcpy(want, kIntegerSkipOrig + w.orig, w.len);
            if (i < g_isKept) {
                memset(want, 0x90, w.len);
                want[0] = 0xE9;
                fails += !putRel32(g_eng.main + w.rva + 5, g_isPool + w.stub, want + 1);
            }
            fails += memcmp(want, g_eng.main + w.rva, w.len) != 0;
        }
    }
    g_faultLoop = false;
    fprintf(rep, "failed-write cases %d\n%s (%d failures)\n", 2 * kIsWindows,
            fails ? "FAIL" : "PASS", fails);
    fclose(rep);
    return fails ? 1 : 0;
}
