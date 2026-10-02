// M2, the menu transitions.
// Included once by dinput8_proxy.cpp after the phase-step pools: the family
// follows the phase key, which also holds the transition's fade (439B48) and
// one of its decays (43987C).
//
// tools/gen_menu_transitions.py writes menu_transitions.h: a stub pool, the
// windows that jump into it and five literal retargets. Code is written once
// at startup with the game's other threads suspended. After that only the
// pool's data changes, on the game thread in the per-tick hook, before the
// tick's updates run:
//   [kMenuMaskOffset]   the stock-tick mask, 0/1/3, as F1: a counter counts
//                       and the drop's update runs only on ticks with
//                       (frameCounter & mask) == 0;
//   [kMenuScaleOffset]  s = 1/N, the share of a stock tick one tick is worth,
//                       which the scaled steps multiply by;
//   the literal slots   K*s for a step, K**s for a factor.
// N is fps / the stock context's rate (30, or 60 in the stock game's own 60 Hz
// menus), the same N as the phase steps. At N = 1 (30 fps, F9, the phase key
// muted, Passthrough) mask 0, s = 1 and the slots hold the shipped constants,
// so every stub is the original code.
#include "menu_transitions.h"

static constexpr int kMtWindows = (int)(sizeof(kMenuWindows) / sizeof(kMenuWindows[0]));
static constexpr int kMtLiterals = (int)(sizeof(kMenuLiterals) / sizeof(kMenuLiterals[0]));
static constexpr int kMtSites = (int)(sizeof(kMenuSites) / sizeof(kMenuSites[0]));
static constexpr int kMtWrites = kMtWindows + kMtLiterals;
static uint8_t* g_mtPool = nullptr;
static bool g_mtReady = false;
static int g_mtKept = 0;
static volatile LONG g_mtN = 1;          // ticks per stock tick the pool holds now

static void menuTransitionsApply(unsigned n) {
    volatile uint8_t* p = g_mtPool;
    float s = 1.0f / (float)n;
    p[kMenuMaskOffset] = (uint8_t)(n - 1);
    *(volatile float*)(p + kMenuScaleOffset) = s;
    for (const auto& l : kMenuLiterals) {
        float k = *(const float*)(g_eng.main + l.constRva);
        float v = n == 1 ? k : l.kind == 0 ? k * s : powf(k, s);
        *(volatile float*)(p + l.slot) = v;
    }
    InterlockedExchange(&g_mtN, (LONG)n);
}

// N for this tick: fps over the stock context's rate while the family is on.
static unsigned menuTransitionsN() {
    if (!g_mtReady || !g_fcHooked || !g_cfg.fixMenuTransitions || g_cfg.passthrough ||
        !g_fps60 || g_phaseFixMuted || !g_shadowOn || !g_shadowMode) {
        return 1;
    }
    uint8_t mode = *g_shadowMode;
    if (mode != 1 && mode != 2) {
        return 1;  // no stock context: leave the original code in charge
    }
    unsigned fps = g_fpsImmsFast ? 120u : 60u;
    return fps / (mode == 1 ? 60u : 30u);
}

static const char* menuTransitionState() {
    if (!g_cfg.fixMenuTransitions) return "off(ini)";
    if (!g_mtReady || !g_fcHooked) return "NOT INSTALLED";
    if (!g_fps60) return "stock";
    if (g_phaseFixMuted) return "MUTED";
    if (!g_shadowOn || !g_shadowMode || (*g_shadowMode != 1 && *g_shadowMode != 2))
        return "NO CONTEXT";
    return "on";
}

// ---------------------------------------------------------------------------
// The field watch. Per tick, on the game thread, before the tick's updates:
// the scene transition (the struct main+7A9C20 points at) and the pause menu
// (main+7A90B8). Each phase that ends leaves one record: its ticks, the tick
// rate they ran at, and the phase's stock length in stock ticks, simulated
// from the state it started in with the game's own float arithmetic. Game
// time, as the day clock does: ticks over the configured rate, so a frame-rate
// dip does not read as the fix being wrong.
// ---------------------------------------------------------------------------
static const uint32_t kMtTransitionPtrRva = 0x7A9C20;  // -> B4DF40, 4396F0's this
static const uint32_t kMtPausePtrRva = 0x7A90B8;       // -> B1EBA0, 413CC0's this

enum MtPhase : uint8_t { MT_SLIDE, MT_GLIDE, MT_FADE, MT_FADE_TAIL, MT_DROP, MT_PHASES };
static const char* const kMtPhaseName[MT_PHASES] = {"slide", "glide", "fade", "fade tail",
                                                     "pause drop"};

struct MtRecord {
    uint8_t phase;
    uint8_t mixed;       // the tick rate or context changed during it
    uint16_t stockTicks; // its stock length, simulated from its start
    uint32_t ticks;      // ticks it took here
    uint32_t hz;         // ticks per second it ran at (game time)
    uint32_t stockHz;    // the stock context's rate at its start
};
struct MtTrack {
    bool on;
    uint32_t ticks, hz, stockHz, n;
    uint16_t stockTicks;
    bool mixed;
};
static MtTrack g_mtTrack[MT_PHASES] = {};
static MtRecord g_mtRing[16] = {};
static volatile LONG g_mtRingHead = 0;  // records written, ever (game thread)
static LONG g_mtRingRead = 0;           // records logged (watcher)
static MtRecord g_mtLast[MT_PHASES] = {};
static LONGLONG g_mtLastAt[MT_PHASES] = {};
static SRWLOCK g_mtLastLock = SRWLOCK_INIT;

static uint16_t mtStockSlide(float x, float v) {
    // 439A50: x += v, until 25 >= x
    for (uint16_t k = 1; k < 2000; k++) {
        x = x + v;
        if (!(25.0f < x)) return k;
    }
    return 0;
}
static uint16_t mtStockFade(float a) {
    // 439AD0 state 1: alpha -= 0.056, until 0 > alpha
    const float step = *(const float*)(g_eng.main + 0x6B23E8);
    for (uint16_t k = 1; k < 2000; k++) {
        a = a - step;
        if (0.0f > a) return k;
    }
    return 0;
}
static uint16_t mtStockFadeTail(float c) {
    // 439AD0 state 3: c += 14, until c > 64
    for (uint16_t k = 1; k < 2000; k++) {
        c = c + 14.0f;
        if (c > 64.0f) return k;
    }
    return 0;
}
static uint16_t mtStockDrop(float p, float v) {
    // 415B30: v += 6; p = (v + p) + v; at p > 0 bounce: v *= -0.43, p = 0,
    // and |v| < 3 settles
    const float bounce = *(const float*)(g_eng.main + 0x6B08C8);
    for (uint16_t k = 1; k < 2000; k++) {
        v = v + 6.0f;
        p = (v + p) + v;
        if (p > 0.0f) {
            v = v * bounce;
            p = 0.0f;
            if (fabsf(v) < 3.0f) return k;
        }
    }
    return 0;
}

static void mtBegin(MtTrack& t, uint16_t stockTicks, uint32_t hz, uint32_t stockHz, uint32_t n) {
    t.on = true;
    t.ticks = 0;
    t.hz = hz;
    t.stockHz = stockHz;
    t.n = n;
    t.stockTicks = stockTicks;
    t.mixed = false;
}
static void mtEnd(MtTrack& t, MtPhase phase) {
    t.on = false;
    if (!t.ticks) return;
    MtRecord& r = g_mtRing[g_mtRingHead % 16];
    r.phase = (uint8_t)phase;
    r.mixed = t.mixed;
    r.stockTicks = t.stockTicks;
    r.ticks = t.ticks;
    r.hz = t.hz;
    r.stockHz = t.stockHz;
    MemoryBarrier();
    InterlockedIncrement(&g_mtRingHead);
}
// One phase: `in` says whether the object is in it this tick (the state the
// last tick's update left), `start` computes its stock length on entry. A
// phase is mixed only if the rate, the stock context or N changed on a tick
// that belongs to it. The tick that sees it over does not: the pause drop's
// last update switches the menu to its 60 Hz context, and that change is the
// drop finishing, not something that happened during it.
template <typename F>
static void mtStep(MtPhase phase, bool in, uint32_t hz, uint32_t stockHz, uint32_t n, F start) {
    MtTrack& t = g_mtTrack[phase];
    if (in && !t.on) {
        mtBegin(t, start(), hz, stockHz, n);
    } else if (!in && t.on) {
        mtEnd(t, phase);
    }
    if (t.on) {
        t.ticks++;
        if (t.hz != hz || t.stockHz != stockHz || t.n != n) t.mixed = true;
    }
}

// Both objects are statics of main.dll, reached through pointers in its .data.
// A pointer outside the image (not relocated, or not set yet) is not followed.
static uint32_t mtImageSize() {
    static uint32_t size = 0;
    if (!size) {
        auto dos = (const IMAGE_DOS_HEADER*)g_eng.main;
        auto nt = (const IMAGE_NT_HEADERS64*)(g_eng.main + dos->e_lfanew);
        size = nt->OptionalHeader.SizeOfImage;
    }
    return size;
}
static const uint8_t* mtImagePointer(uint32_t rva, uint32_t size) {
    const uint8_t* p = *(const uint8_t* const*)(g_eng.main + rva);
    const uint8_t* end = g_eng.main + mtImageSize();
    return p >= g_eng.main && p + size <= end ? p : nullptr;
}

static void menuTransitionWatchOnTick() {
    if (!g_eng.main) return;
    uint32_t hz = g_fps60 ? (g_fpsImmsFast ? 120u : 60u) : (stockModeByte() == 1 ? 60u : 30u);
    uint32_t stockHz = stockModeByte() == 1 ? 60u : 30u;
    uint32_t n = (uint32_t)g_mtN;
    const uint8_t* tr = mtImagePointer(kMtTransitionPtrRva, 0x40);
    if (tr) {
        uint8_t pathA = tr[0x22], pathB = tr[0x23], st = tr[0x29];
        mtStep(MT_SLIDE, pathA && st == 1, hz, stockHz, n, [&]() -> uint16_t {
            const uint8_t* model = *(uint8_t* const*)tr;
            if (!model || !readableRange(model + 0xA8, 8)) return 0;
            const float* pos = *(float* const*)(model + 0xA8);
            if (!pos || !readableRange(pos, 4)) return 0;
            return mtStockSlide(*pos, *(const float*)(tr + 0x18));
        });
        mtStep(MT_GLIDE, pathA && st == 2, hz, stockHz, n, []() -> uint16_t { return 28; });
        mtStep(MT_FADE, pathB && st == 1, hz, stockHz, n,
               [&]() -> uint16_t { return mtStockFade(*(const float*)(tr + 0x10)); });
        mtStep(MT_FADE_TAIL, pathB && st == 3, hz, stockHz, n,
               [&]() -> uint16_t { return mtStockFadeTail(*(const float*)(tr + 0xC)); });
    }
    const uint8_t* pm = mtImagePointer(kMtPausePtrRva, 0x100);
    if (pm) {
        bool drop = pm[0x98] <= 1 && pm[0x99] == 1;
        mtStep(MT_DROP, drop, hz, stockHz, n, [&]() -> uint16_t {
            return mtStockDrop(*(const float*)(pm + 0x8C), *(const float*)(pm + 0x90));
        });
    }
}

// From the per-tick hook: the pool's data, then the watch.
static void updateMenuTransitions() {
    if (g_mtPool) {
        unsigned n = menuTransitionsN();
        if (n != (unsigned)g_mtN) {
            menuTransitionsApply(n);
        }
    }
    menuTransitionWatchOnTick();
}

static void mtVerdict(const MtRecord& r, char* out, size_t n) {
    double got = (double)r.ticks / r.hz, want = r.stockHz ? (double)r.stockTicks / r.stockHz : 0;
    if (!r.stockTicks || want <= 0) {
        snprintf(out, n, "%s %.2f s", kMtPhaseName[r.phase], got);
        return;
    }
    // one stock tick of slack: a phase starts on any tick, its first stock
    // tick may be up to N-1 ticks away
    double slack = 1.0 / r.stockHz + 0.5 / r.hz;
    const char* verdict = r.mixed ? "rate or context changed during it" : nullptr;
    char buf[48];
    if (!verdict) {
        if (fabs(got - want) <= slack) {
            verdict = "OK";
        } else {
            snprintf(buf, sizeof(buf), "%.1fx %s", got < want ? want / got : got / want,
                     got < want ? "FAST" : "SLOW");
            verdict = buf;
        }
    }
    snprintf(out, n, "%s %.2f s (stock %.2f) %s", kMtPhaseName[r.phase], got, want, verdict);
}

// From the watcher: log what ended, keep the last of each for the overlay.
static void pollMenuTransitions(LONGLONG now) {
    LONG head = g_mtRingHead;
    if (head - g_mtRingRead > 16) g_mtRingRead = head - 16;  // overrun: skip the oldest
    while (g_mtRingRead < head) {
        MtRecord r = g_mtRing[g_mtRingRead % 16];
        g_mtRingRead++;
        char v[120];
        mtVerdict(r, v, sizeof(v));
        logf("menu transition: %s | %u ticks at %u/s, stock %u ticks at %u Hz | menus=%s /%ld",
             v, r.ticks, r.hz, r.stockTicks, r.stockHz, menuTransitionState(), (long)g_mtN);
        AcquireSRWLockExclusive(&g_mtLastLock);
        g_mtLast[r.phase] = r;
        g_mtLastAt[r.phase] = now;
        ReleaseSRWLockExclusive(&g_mtLastLock);
    }
}

// The overlay line while a transition was seen in the last 8 s.
static bool menuOverlayLine(char* out, size_t n) {
    if (!g_cfg.fixMenuTransitions || g_cfg.passthrough) return false;
    LONGLONG now = qpc();
    size_t u = (size_t)snprintf(out, n, "MENUS %s /%ld |", menuTransitionState(), (long)g_mtN);
    bool any = false;
    AcquireSRWLockShared(&g_mtLastLock);
    for (int p = 0; p < MT_PHASES && u < n; p++) {
        if (!g_mtLastAt[p] || now - g_mtLastAt[p] > 8 * g_qpcFreq) continue;
        char v[96];
        mtVerdict(g_mtLast[p], v, sizeof(v));
        u += (size_t)snprintf(out + u, n - u, " %s;", v);
        any = true;
    }
    ReleaseSRWLockShared(&g_mtLastLock);
    return any;
}

static void installMenuTransitions() {
    if (!g_cfg.fixMenuTransitions || g_cfg.passthrough || !g_eng.main || g_mtPool) return;
    if (!g_fcHooked || g_fcStranded || !g_shadowOk ||
        (uint8_t*)g_eng.frameCounter != g_eng.main + kMenuFrameCounterRva) {
        logf("menu transitions: shared tick hook or stock context unavailable, not patched");
        return;
    }
    for (const auto& w : kMenuWindows) {
        if (w.len < 5 || w.len > 32 || memcmp(g_eng.main + w.rva, kMenuOrig + w.orig, w.len)) {
            logf("menu transitions: main+%X differs from main.dll sha1 %s, not patched", w.rva,
                 MENU_TRANSITIONS_MAIN_SHA1);
            return;
        }
    }
    for (int i = 0; i < kMtLiterals; i++) {
        if (memcmp(g_eng.main + kMenuLiterals[i].rva, kMenuLiteralOrig[i].b, 8)) {
            logf("menu transitions: main+%X differs from main.dll sha1 %s, not patched",
                 kMenuLiterals[i].rva, MENU_TRANSITIONS_MAIN_SHA1);
            return;
        }
    }
    uint8_t* pool = allocNear(g_eng.main, kMenuPoolSize);
    if (!pool) {
        logf("menu transitions: no reachable stub pool, not patched");
        return;
    }
    memcpy(pool + kMenuCodeOffset, kMenuCode, sizeof(kMenuCode));
    bool ok = true;
    for (const auto& f : kMenuFixups) {
        if (f.next) {
            ok &= putRel32(pool + f.next, g_eng.main + f.target, pool + f.field);
        } else {
            uint64_t target = (uint64_t)(g_eng.main + f.target);
            memcpy(pool + f.field, &target, sizeof(target));
        }
    }
    // N = 1 before any jump exists: every stub is the original code
    g_mtPool = pool;
    menuTransitionsApply(1);
    g_mtPool = nullptr;
    uint8_t jumps[kMtWindows][32];
    uint8_t disps[kMtLiterals][4];
    GroupWrite writes[kMtWrites];
    for (int i = 0; i < kMtWindows; i++) {
        const auto& w = kMenuWindows[i];
        memset(jumps[i], 0x90, w.len);
        jumps[i][0] = 0xE9;
        ok &= putRel32(g_eng.main + w.rva + 5, pool + w.stub, jumps[i] + 1);
        writes[i] = {g_eng.main + w.rva, jumps[i], kMenuOrig + w.orig, w.len};
    }
    for (int i = 0; i < kMtLiterals; i++) {
        const auto& l = kMenuLiterals[i];
        ok &= putRel32(g_eng.main + l.rva + 8, pool + l.slot, disps[i]);
        writes[kMtWindows + i] = {g_eng.main + l.rva + 4, disps[i], kMenuLiteralOrig[i].b + 4, 4};
    }
    if (!ok) {
        freeNear(pool);
        logf("menu transitions: relocation out of reach, not patched");
        return;
    }
    FlushInstructionCache(GetCurrentProcess(), pool, kMenuPoolSize);
    bool installed = false;
    for (int attempt = 0; attempt < 32; attempt++) {
        bool safe = suspendOthers();
        for (int t = 0; t < g_susCount && safe; t++) {
            for (const auto& w : kMenuWindows) {
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
        for (const auto& w : kMenuWindows) {
            safe &= memcmp(g_eng.main + w.rva, kMenuOrig + w.orig, w.len) == 0;
        }
        for (int i = 0; i < kMtLiterals; i++) {
            safe &= memcmp(g_eng.main + kMenuLiterals[i].rva, kMenuLiteralOrig[i].b, 8) == 0;
        }
        if (safe) {
            g_mtPool = pool;
            g_mtKept = writeGroup(writes, kMtWrites);
            g_mtReady = g_mtKept == kMtWrites;
            installed = true;
        }
        resumeOthers();
        break;
    }
    if (!g_mtKept) {
        g_mtPool = nullptr;
        freeNear(pool);
    }
    // A partial rollback keeps its pool at N = 1: every remaining jump runs the
    // original instructions and every remaining literal reads its constant.
    logf("menu transitions: %d/%d writes (%d windows, %d literals), %s; follows the phase key %s",
         g_mtKept, kMtWrites, kMtWindows, kMtLiterals,
         g_mtReady ? "ready" : installed ? "inactive after write failure" : "not patched",
         g_cfg.phaseToggleName);
}

// Offline, for tools/verify_menu_transitions.py: map main.dll without running
// it, use the real installer, dump the pool and every patched byte, then drive
// the per-tick update through fps, context, key and config, and fail each
// write in turn.
extern "C" __declspec(dllexport) int OkamiMenuTransitionSelfTest(const char* mainPath,
                                                                 const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) return 2;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixMenuTransitions = true;
    g_cfg.fixFrameClocks = true;
    g_cfg.passthrough = false;
    if (!tick || !resolveFrameConfig(tick)) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    installFrameClocks();
    installShadowMode();
    installMenuTransitions();
    if (!g_mtReady) {
        fprintf(rep, "FAIL install\n");
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\npool %p\n", (void*)m, (void*)g_mtPool);
    int fails = 0;
    uint8_t installedCode[kMenuPoolSize - kMenuCodeOffset];
    memcpy(installedCode, g_mtPool + kMenuCodeOffset, sizeof(installedCode));
    snprintf(path, sizeof(path), "%s\\pool.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fails += fwrite(g_mtPool, 1, kMenuPoolSize, f) != kMenuPoolSize;
        fclose(f);
    } else fails++;
    snprintf(path, sizeof(path), "%s\\patched.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& w : kMenuWindows) fails += fwrite(g_eng.main + w.rva, 1, w.len, f) != w.len;
        for (const auto& l : kMenuLiterals) fails += fwrite(g_eng.main + l.rva, 1, 8, f) != 8;
        fclose(f);
    } else fails++;
    // every combination through the per-tick hook: mask, s and the slots
    snprintf(path, sizeof(path), "%s\\modes.csv", outDir);
    if (FILE* f = fopen(path, "w")) {
        fprintf(f, "fps,mode,enabled,muted,shadow,hook,complete,mask,scale");
        for (const auto& l : kMenuLiterals) fprintf(f, ",slot%X", l.rva);
        fprintf(f, "\n");
        for (int fps : {30, 60, 120}) for (int mode : {0, 1, 2, 3})
        for (int enabled : {0, 1}) for (int muted : {0, 1})
        for (int shadow : {0, 1}) for (int hook : {0, 1}) for (int complete : {0, 1}) {
            g_fps60 = fps != 30;
            g_fpsImmsFast = fps == 120;
            *g_shadowMode = (uint8_t)mode;
            g_shadowOn = shadow != 0;
            g_cfg.fixMenuTransitions = enabled != 0;
            g_phaseFixMuted = muted;
            g_fcHooked = hook != 0;
            g_mtReady = complete != 0;
            frameClockOnTick();
            fprintf(f, "%d,%d,%d,%d,%d,%d,%d,%u,%.9g", fps, mode, enabled, muted, shadow, hook,
                    complete, (unsigned)g_mtPool[kMenuMaskOffset],
                    (double)*(float*)(g_mtPool + kMenuScaleOffset));
            for (const auto& l : kMenuLiterals) fprintf(f, ",%.9g", (double)*(float*)(g_mtPool + l.slot));
            fprintf(f, "\n");
        }
        fclose(f);
    } else fails++;
    fails += memcmp(installedCode, g_mtPool + kMenuCodeOffset, sizeof(installedCode)) != 0;
    // The watch's stock simulations, against the game's own recurrences.
    {
        uint16_t slide = mtStockSlide(680.0f, -4.25f), drop = mtStockDrop(-514.0f, 0.0f),
                 fade = mtStockFade(1.0f), tail = mtStockFadeTail(0.0f);
        bool simOk = slide == 155 && drop == 18 && fade == 18 && tail == 5;
        fprintf(rep, "stock sims: slide(680) %u, drop(-514) %u, fade %u, tail %u: %s\n", slide, drop,
                fade, tail, simOk ? "ok" : "FAIL");
        fails += !simOk;
        MtRecord r = {MT_GLIDE, 0, 28, 112, 120, 30};
        char v[120];
        mtVerdict(r, v, sizeof(v));
        bool okOk = strcmp(v, "glide 0.93 s (stock 0.93) OK") == 0;
        r.ticks = 28;
        mtVerdict(r, v, sizeof(v));
        bool fastOk = strcmp(v, "glide 0.23 s (stock 0.93) 4.0x FAST") == 0;
        r.ticks = 112;
        r.mixed = 1;
        mtVerdict(r, v, sizeof(v));
        bool mixedOk = strstr(v, "rate or context changed") != nullptr;
        fprintf(rep, "verdict ok: %s\nverdict fast: %s\nverdict mixed: %s\n", okOk ? "ok" : "FAIL",
                fastOk ? "ok" : "FAIL", mixedOk ? "ok" : "FAIL");
        fails += !okOk + !fastOk + !mixedOk;
    }
    g_cfg.fixMenuTransitions = true;
    g_fcHooked = true;
    g_mtReady = true;
    g_shadowOn = true;
    *g_shadowMode = 2;
    g_phaseFixMuted = 0;
    g_fps60 = 1;
    g_fpsImmsFast = true;
    // Every failed write, including a failed undo, leaves what remains at N = 1.
    g_faultLoop = true;  // no protection change a write, no thread snapshot an install
    for (int rest = 0; rest <= 1; rest++) for (int k = 0; k < kMtWrites; k++) {
        for (const auto& w : kMenuWindows)
            fails += !writeProtected(g_eng.main + w.rva, kMenuOrig + w.orig, w.len);
        for (int i = 0; i < kMtLiterals; i++)
            fails += !writeProtected(g_eng.main + kMenuLiterals[i].rva, kMenuLiteralOrig[i].b, 8);
        freeNear(g_mtPool);
        g_mtPool = nullptr;
        g_mtReady = false;
        g_mtKept = 0;
        g_mtN = 1;
        g_writeCount = 0;
        g_writeFailAt = k;
        g_writeFailRest = rest != 0;
        installMenuTransitions();
        g_writeFailAt = -1;
        g_writeFailRest = false;
        frameClockOnTick();
        fails += g_mtReady || g_mtKept != (rest ? k : 0);
        fails += g_mtKept ? (!g_mtPool || g_mtPool[kMenuMaskOffset] != 0 ||
                             *(float*)(g_mtPool + kMenuScaleOffset) != 1.0f)
                          : g_mtPool != nullptr;
        for (int i = 0; i < kMtWindows; i++) {
            const auto& w = kMenuWindows[i];
            uint8_t want[32];
            memcpy(want, kMenuOrig + w.orig, w.len);
            if (i < g_mtKept) {
                memset(want, 0x90, w.len);
                want[0] = 0xE9;
                fails += !putRel32(g_eng.main + w.rva + 5, g_mtPool + w.stub, want + 1);
            }
            fails += memcmp(want, g_eng.main + w.rva, w.len) != 0;
        }
        for (int i = 0; i < kMtLiterals; i++) {
            const auto& l = kMenuLiterals[i];
            uint8_t want[8];
            memcpy(want, kMenuLiteralOrig[i].b, 8);
            if (kMtWindows + i < g_mtKept) {
                fails += !putRel32(g_eng.main + l.rva + 8, g_mtPool + l.slot, want + 4);
            }
            fails += memcmp(want, g_eng.main + l.rva, 8) != 0;
        }
    }
    g_faultLoop = false;
    fprintf(rep, "failed-write cases %d\n%s (%d failures)\n", 2 * kMtWrites, fails ? "FAIL" : "PASS",
            fails);
    fclose(rep);
    return fails ? 1 : 0;
}
