// World animations, first set:
// the sky's scrolling layers, the villagers' swinging bones, their talk
// head-bob and mood particles, the effect engine's shared particle step and
// the emitters' clocks. Included once by dinput8_proxy.cpp after the menu
// transitions; like them it follows the phase key.
//
// tools/gen_world_anims.py writes world_anims.h: a stub pool, the windows that
// jump into it and the literal retargets. Code is written once at startup
// with the game's other threads suspended. After that only the pool's data
// changes, on the game thread in the per-tick hook, before the tick's updates
// run, one block per group (sky, swing, human, effect, emitter, turn, scenery,
// objects, mode, repeat, actor: the enemies' own clocks and speed-paced steps,
// menu: list scrolls, steer: the turn steps, flag: the 60 fps flag's lengths,
// skip: the skip prompt's window):
//   [g*8]     the stock-tick mask, 0/1/3, as F1: the gated functions and the
//             counters run only on ticks with (frameCounter & mask) == 0, and
//             a root takes one square root per set bit;
//   [g*8+1]   the mask shifted left once (count2: a step the port already
//             runs on ticks of one parity);
//   [g*8+2]   the stock context's mode byte, 2 or 1 (smode), 0 at N = 1;
//   [g*8+4]   s = 1/N, the share of a stock tick one tick is worth;
//   [kWorldIntNOffset + 4g]   N as a dword (imuln);
//   the literal slots   K*s for a step, K*s^2 for the wind push, 1 - (1 - K)^s
//             for an approach's factor (blend).
// N is fps / the stock context's rate (30, or 60 in the stock game's own 60 Hz
// screens), the same N as the phase steps. The mode group (F6) is the
// exception: its sites are the port's own "step x mode", which is right in
// real time at 30 and 60 and 2x at 120, where the patch keeps the mode byte at
// 1; its N is fps / 60 while that byte reads 1. The flag group's too: its
// lengths are the port's `n << flag`, and the flag is 1 exactly when the mode
// byte is. At N = 1 (30 fps, F9, the
// phase key muted, the group off in the ini, Passthrough) mask 0, s = 1 and
// the slots hold the shipped constants, so every stub is the original code.
//
// The steer group has no windows: each turn step's call (of 2DDF90, 2DA570 or
// the enemies' 23A2E0) has its rel32 pointed at its own stub, which scales the
// limit register by s (and makes 2DA570's blend k into 1 - (1 - k)^(1/N)) and
// jumps to the call's target; the return address stays the caller's.
//
// Every stub also counts its passes in a probe (kWorldProbeOffset), and each
// gate and counter counts {ticks, counted, last tick, passes} as F1 does. The
// watcher turns them into a `world anims:` log line per status interval: how
// many sky layers, swinging bones, talking heads, mood spawners, particles
// and emitters ran per tick, and whether every counter counted on exactly
// 1/N of the ticks it ran on.
#include "world_anims.h"

static constexpr int kWaWindows = (int)(sizeof(kWorldWindows) / sizeof(kWorldWindows[0]));
static constexpr int kWaLiterals = (int)(sizeof(kWorldLiterals) / sizeof(kWorldLiterals[0]));
static constexpr int kWaSites = (int)(sizeof(kWorldSites) / sizeof(kWorldSites[0]));
static constexpr int kWaCalls = (int)(sizeof(kWorldCalls) / sizeof(kWorldCalls[0]));
static_assert(sizeof(kWorldCallOps) == sizeof(kWorldCalls) / sizeof(kWorldCalls[0]),
              "world_anims.h: one opcode per call");
static constexpr int kWaWrites = kWaWindows + kWaLiterals + kWaCalls;
static uint8_t* g_waPool = nullptr;
static bool g_waReady = false;
static int g_waKept = 0;
static volatile LONG g_waN[kWorldGroups] = {};      // ticks per stock tick the pool holds now
static volatile LONG g_waSmode[kWorldGroups] = {};  // the stock mode the pool holds (smode)
static volatile LONG g_waChanges[kWorldGroups] = {};  // every change of a group's N
static constexpr int kWaGroupMode = 8, kWaGroupRepeat = 9, kWaGroupActor = 10;
static constexpr int kWaGroupMenu = 11, kWaGroupSteer = 12, kWaGroupFlag = 13;
static constexpr int kWaGroupSkip = 14, kWaGroupPlayer = 15;
static_assert(kWorldGroups == 16, "world_anims.h and this runtime disagree on the groups");

enum WaKind : uint8_t { WA_LIN, WA_SQ, WA_SRC, WA_DST, WA_PRE, WA_ROOT, WA_GATEFN, WA_COUNT,
                        WA_GATE0, WA_DSTARG, WA_ZFIRST, WA_ZLAST, WA_UFIRST, WA_ULAST,
                        WA_COUNTLAST, WA_FLOOR1, WA_SCALEDADD, WA_ARGSCALE, WA_COUNT2,
                        WA_NOTYET, WA_SMODE, WA_IMULN, WA_SRCX, WA_STEP, WA_CALLSCALE,
                        WA_CALLBLEND, WA_MULFLAG, WA_CALLGATE, WA_MULSTORE, WA_BLEND,
                        WA_BLENDR, WA_SRCBLEND, WA_IMMSTORE, WA_SRCROOT, WA_NOTYETNEG,
                        WA_NOTYETB, WA_DSTN };

// A blend literal's slot: 1 - (1 - k)^(1/n) for 0 < k < 1, the root taken by one
// sqrtf per halving as the `root` stubs take it (n = 2, 4), so the verifier's
// float arithmetic gives the same bits; k itself at n = 1 or outside (0, 1).
static float waBlendLiteral(float k, unsigned n) {
    if (n == 1 || !(k > 0.0f && k < 1.0f)) return k;
    float v = 1.0f - k;
    if (n & (n - 1)) return 1.0f - powf(v, 1.0f / (float)n);  // not a power of two
    for (unsigned m = n; m > 1; m >>= 1) v = sqrtf(v);
    return 1.0f - v;
}
static bool waCounted(uint8_t kind) {
    return kind == WA_GATEFN || kind == WA_COUNT || kind == WA_GATE0 || kind == WA_COUNTLAST ||
           kind == WA_COUNT2 || kind == WA_NOTYET || kind == WA_NOTYETNEG || kind == WA_NOTYETB ||
           kind == WA_SMODE || kind == WA_CALLGATE;
}

static bool worldGroupEnabled(int g) {
    switch (g) {
        case 0: return g_cfg.fixSkyScroll;
        case 1: return g_cfg.fixSwingPhysics;
        case 2: return g_cfg.fixHumanAnims;
        // the old experiment FixEffects runs every esp* update on every other
        // tick: on top of this family it would halve the particles' speed
        case 3: return g_cfg.fixParticles && !g_cfg.fixEffects;
        case 4: return g_cfg.fixEmitters && !g_cfg.fixEffects;
        case 5: return g_cfg.fixTurnLimits;
        case 6: return g_cfg.fixScenerySway;
        case 7: return g_cfg.fixObjectAnims;
        case kWaGroupMode: return g_cfg.fixModeQuantities;
        case kWaGroupRepeat: return g_cfg.fixMenuRepeat;
        case kWaGroupActor: return g_cfg.fixEnemyClocks;
        case kWaGroupMenu: return g_cfg.fixMenuScroll;
        case kWaGroupSteer: return g_cfg.fixTurnSteps;
        case kWaGroupFlag: return g_cfg.fixFlagQuantities;
        case kWaGroupSkip: return g_cfg.fixSkipWindow;
        case kWaGroupPlayer: return g_cfg.fixPlayerAnims;
        default: return false;
    }
}

// smode is the stock context's mode byte (2 or 1) the repeat's counters lose
// on a stock tick at N > 1; at N = 1 the stubs read the real byte, and 0 here.
static void worldAnimsApply(int g, unsigned n, unsigned smode = 0) {
    volatile uint8_t* p = g_waPool;
    float s = 1.0f / (float)n;
    p[kWorldGroupStride * g] = (uint8_t)(n - 1);
    p[kWorldGroupStride * g + 1] = (uint8_t)((n - 1) << 1);
    p[kWorldGroupStride * g + 2] = (uint8_t)(n > 1 ? smode : 0);
    *(volatile uint32_t*)(p + kWorldIntNOffset + 4 * g) = n;
    *(volatile float*)(p + kWorldGroupStride * g + 4) = s;
    for (const auto& l : kWorldLiterals) {
        if (l.group != g) continue;
        float k = *(const float*)(g_eng.main + l.constRva);
        float v = n == 1 ? k : l.kind == WA_LIN ? k * s : l.kind == WA_BLEND ?
                  waBlendLiteral(k, n) : k * s * s;
        *(volatile float*)(p + l.slot) = v;
    }
    InterlockedExchange(&g_waN[g], (LONG)n);
    InterlockedExchange(&g_waSmode[g], (LONG)(n > 1 ? smode : 0));
    InterlockedIncrement(&g_waChanges[g]);
}

// N for this tick and group: fps over the stock context's rate while it is on.
// The mode group's is fps / 60 while the real mode byte reads 1, as the patch
// keeps it: its sites are the port's "step x mode", right at 60.
static unsigned worldAnimsN(int g) {
    if (!g_waReady || !g_fcHooked || !g_cfg.fixWorldAnims || !worldGroupEnabled(g) ||
        g_cfg.passthrough || !g_fps60 || g_phaseFixMuted) {
        return 1;
    }
    unsigned fps = g_fpsImmsFast ? 120u : 60u;
    if (g == kWaGroupMode || g == kWaGroupFlag) {
        return g_eng.modeByte && *(volatile uint8_t*)g_eng.modeByte == 1 ? fps / 60u : 1u;
    }
    if (!g_shadowOn || !g_shadowMode) {
        return 1;
    }
    uint8_t mode = *g_shadowMode;
    if (mode != 1 && mode != 2) {
        return 1;  // no stock context: leave the original code in charge
    }
    return fps / (mode == 1 ? 60u : 30u);
}

static const char* worldAnimState() {
    if (!g_cfg.fixWorldAnims) return "off(ini)";
    if (!g_waReady || !g_fcHooked) return "NOT INSTALLED";
    if (!g_fps60) return "stock";
    if (g_phaseFixMuted) return "MUTED";
    if (!g_shadowOn || !g_shadowMode || (*g_shadowMode != 1 && *g_shadowMode != 2))
        return "NO CONTEXT";
    return "on";
}

// From the per-tick hook, before the tick's updates run.
static void updateWorldAnims() {
    if (!g_waPool) return;
    for (int g = 0; g < kWorldGroups; g++) {
        unsigned n = worldAnimsN(g);
        // the stock context's mode, for the repeat's counters: it can change
        // with N unchanged (60 fps in play and 120 in a 60 Hz menu are both 2)
        unsigned smode = n > 1 && g == kWaGroupRepeat && g_shadowMode ? *g_shadowMode : 0;
        if (n != (unsigned)g_waN[g] || smode != (unsigned)g_waSmode[g]) {
            worldAnimsApply(g, n, smode);
        }
    }
}

// ---------------------------------------------------------------------------
// The measurement, from the watcher once per status interval: passes per tick
// for each site, from its probe, over the frame counter's advance. Every gate
// and counter is held to 1/N, as F1's are: over an interval with one N
// throughout, the ticks it counted on must be the ticks it ran on over N.
// ---------------------------------------------------------------------------
struct WaGroupVerdict {
    int live, wrong, intermittent;
    bool changed;
    uint32_t badSite, ran, counted;
};
struct WaSummary {
    bool valid;
    double perTick[kWorldGroups][2];  // group: {headline, second headline} passes per tick
    unsigned n[kWorldGroups];
    WaGroupVerdict v[kWorldGroups];
};
static WaSummary g_waLast = {};
static SRWLOCK g_waLastLock = SRWLOCK_INIT;
static uint32_t g_waPrevProbe[(kWorldCodeOffset - kWorldProbeOffset) / 4] = {};
static uint32_t g_waPrevGate[(kWorldProbeOffset - kWorldCounterOffset) / 16][2] = {};
static uint32_t g_waPrevFc = 0;
static LONG g_waPrevChanges[kWorldGroups] = {};
static bool g_waPrevOk = false;

static void waVerdict(const WaGroupVerdict& v, unsigned n, char* out, size_t cap) {
    if (!v.live) {
        snprintf(out, cap, "no counter ran");
    } else if (v.changed) {
        snprintf(out, cap, "%d counters, N changed, no verdict", v.live);
    } else if (v.wrong) {
        snprintf(out, cap, "%d of %d counters WRONG, first %X", v.wrong, v.live, v.badSite);
    } else if (v.intermittent == v.live) {
        snprintf(out, cap, "%d counters, all intermittent, no verdict", v.live);
    } else {
        snprintf(out, cap, "%d counters /%u OK, %d intermittent", v.live - v.intermittent, n,
                 v.intermittent);
    }
}

static void measureWorldAnims(LONGLONG now) {
    (void)now;
    if (!g_waPool || !g_eng.frameCounter) return;
    const volatile uint32_t* probe = (const volatile uint32_t*)(g_waPool + kWorldProbeOffset);
    const volatile uint32_t* gate = (const volatile uint32_t*)(g_waPool + kWorldCounterOffset);
    uint32_t fc = *g_eng.frameCounter;
    uint32_t ticks = fc - g_waPrevFc;
    bool ok = g_waPrevOk && ticks > 0 && ticks < 100000;
    WaSummary sum = {};
    sum.valid = ok;
    for (int g = 0; g < kWorldGroups; g++) {
        sum.n[g] = (unsigned)g_waN[g];
        sum.v[g].changed = g_waChanges[g] != g_waPrevChanges[g];
    }
    char sites[900] = "";
    size_t su = 0;
    for (int i = 0; i < kWaSites; i++) {
        const WorldSite& s = kWorldSites[i];
        uint32_t v = probe[s.probe], d = v - g_waPrevProbe[s.probe];
        g_waPrevProbe[s.probe] = v;
        if (waCounted(s.kind)) {
            const volatile uint32_t* c = gate + kWorldCounterStride / 4 * s.counter;
            uint32_t t = c[0], k = c[1];
            uint32_t dt = t - g_waPrevGate[s.counter][0], dk = k - g_waPrevGate[s.counter][1];
            g_waPrevGate[s.counter][0] = t;
            g_waPrevGate[s.counter][1] = k;
            WaGroupVerdict& gv = sum.v[s.group];
            if (ok && dt) {
                unsigned n = sum.n[s.group];
                double want = (double)dt / n, slack = want * 0.05 > 2.0 ? want * 0.05 : 2.0;
                gv.live++;
                gv.ran += dt;
                gv.counted += dk;
                // Only a site reached on (nearly) every tick can be held to 1/N.
                // One reached on some ticks only can be reached on stock ticks
                // more or less often than 1 in N without anything being wrong:
                // a particle killed on a stock tick never reaches its later
                // slots on that tick, at any frame rate.
                if (dt < ticks - ticks / 50) {
                    gv.intermittent++;
                } else if (fabs((double)dk - want) > slack && !gv.wrong++) {
                    gv.badSite = s.site;
                }
            }
        }
        if (!ok) continue;
        double pt = (double)d / ticks;
        if (s.role < 2) sum.perTick[s.group][s.role] += pt;
        if (d && su < sizeof(sites) - 24) {
            su += (size_t)snprintf(sites + su, sizeof(sites) - su, " %X %.1f", s.site, pt);
        }
    }
    for (int g = 0; g < kWorldGroups; g++) g_waPrevChanges[g] = g_waChanges[g];
    g_waPrevFc = fc;
    g_waPrevOk = true;
    if (!ok) return;
    char human[96], effect[96], scenery[96], modeq[96], repeat[96], menu[96], flag[96];
    char skip[96], player[96];
    waVerdict(sum.v[2], sum.n[2], human, sizeof(human));
    waVerdict(sum.v[3], sum.n[3], effect, sizeof(effect));
    waVerdict(sum.v[6], sum.n[6], scenery, sizeof(scenery));
    waVerdict(sum.v[kWaGroupMode], sum.n[kWaGroupMode], modeq, sizeof(modeq));
    waVerdict(sum.v[kWaGroupRepeat], sum.n[kWaGroupRepeat], repeat, sizeof(repeat));
    waVerdict(sum.v[kWaGroupMenu], sum.n[kWaGroupMenu], menu, sizeof(menu));
    waVerdict(sum.v[kWaGroupFlag], sum.n[kWaGroupFlag], flag, sizeof(flag));
    waVerdict(sum.v[kWaGroupSkip], sum.n[kWaGroupSkip], skip, sizeof(skip));
    waVerdict(sum.v[kWaGroupPlayer], sum.n[kWaGroupPlayer], player, sizeof(player));
    logf("world anims: %s | sky /%u %.1f layer steps/tick | swing /%u %.1f bones/tick | "
         "human /%u talk %.1f heads/tick, mood %.1f/tick, %s | effect /%u %.1f particles/tick, "
         "%s | emitter /%u %.1f emitters/tick | turn /%u %.1f turns/tick | scenery /%u %.1f "
         "swaying objects/tick, %s | objects /%u %.1f items/tick | enemy clocks /%u %.1f "
         "steps/tick | mode /%u camera %.1f paths/tick, timer %.1f/tick, %s | repeat /%u %.1f "
         "checks/tick, %s | menu /%u %.1f scrolls/tick, %s | steer /%u %.1f turns/tick | "
         "flag /%u rumble %.1f/tick, fade %.2f/tick, %s | skip /%u %.1f checks/tick, %s | "
         "player /%u %.1f steps/tick, %s |%s",
         worldAnimState(), sum.n[0], sum.perTick[0][0], sum.n[1], sum.perTick[1][0], sum.n[2],
         sum.perTick[2][0], sum.perTick[2][1], human, sum.n[3], sum.perTick[3][0], effect,
         sum.n[4], sum.perTick[4][0], sum.n[5], sum.perTick[5][0], sum.n[6], sum.perTick[6][0],
         scenery, sum.n[7], sum.perTick[7][0], sum.n[kWaGroupActor],
         sum.perTick[kWaGroupActor][0], sum.n[kWaGroupMode],
         sum.perTick[kWaGroupMode][0], sum.perTick[kWaGroupMode][1], modeq,
         sum.n[kWaGroupRepeat], sum.perTick[kWaGroupRepeat][0], repeat, sum.n[kWaGroupMenu],
         sum.perTick[kWaGroupMenu][0], menu, sum.n[kWaGroupSteer], sum.perTick[kWaGroupSteer][0],
         sum.n[kWaGroupFlag], sum.perTick[kWaGroupFlag][0], sum.perTick[kWaGroupFlag][1], flag,
         sum.n[kWaGroupSkip], sum.perTick[kWaGroupSkip][0], skip, sum.n[kWaGroupPlayer],
         sum.perTick[kWaGroupPlayer][0], player, sites);
    AcquireSRWLockExclusive(&g_waLastLock);
    g_waLast = sum;
    ReleaseSRWLockExclusive(&g_waLastLock);
}

// A short tail for the overlay's status line.
static void worldStatusTail(char* out, size_t n) {
    AcquireSRWLockShared(&g_waLastLock);
    WaSummary s = g_waLast;
    ReleaseSRWLockShared(&g_waLastLock);
    if (!s.valid) {
        snprintf(out, n, " | world %s /%ld", worldAnimState(), (long)g_waN[0]);
        return;
    }
    int wrong = 0;
    for (int g = 0; g < kWorldGroups; g++) wrong += s.v[g].wrong;
    snprintf(out, n,
             " | world %s /%u sky %.0f swing %.0f talk %.0f mood %.0f fx %.0f em %.0f turn %.0f "
             "sway %.0f obj %.0f clk %.0f str %.0f | mode /%u cam %.0f | rep /%u%s",
             worldAnimState(), s.n[3], s.perTick[0][0], s.perTick[1][0], s.perTick[2][0],
             s.perTick[2][1], s.perTick[3][0], s.perTick[4][0], s.perTick[5][0], s.perTick[6][0],
             s.perTick[7][0], s.perTick[kWaGroupActor][0], s.perTick[kWaGroupSteer][0],
             s.n[kWaGroupMode],
             s.perTick[kWaGroupMode][0],
             s.n[kWaGroupRepeat], wrong ? " COUNTER WRONG" : "");
}

static void installWorldAnims() {
    if (!g_cfg.fixWorldAnims || g_cfg.passthrough || !g_eng.main || g_waPool) return;
    if (!g_fcHooked || g_fcStranded || !g_shadowOk ||
        (uint8_t*)g_eng.frameCounter != g_eng.main + kWorldFrameCounterRva) {
        logf("world anims: shared tick hook or stock context unavailable, not patched");
        return;
    }
    for (const auto& w : kWorldWindows) {
        if (w.len < 5 || w.len > 32 || memcmp(g_eng.main + w.rva, kWorldOrig + w.orig, w.len)) {
            logf("world anims: main+%X differs from main.dll sha1 %s, not patched", w.rva,
                 WORLD_ANIMS_MAIN_SHA1);
            return;
        }
    }
    for (int i = 0; i < kWaLiterals; i++) {
        if (memcmp(g_eng.main + kWorldLiterals[i].rva, kWorldLiteralOrig[i].b, 8)) {
            logf("world anims: main+%X differs from main.dll sha1 %s, not patched",
                 kWorldLiterals[i].rva, WORLD_ANIMS_MAIN_SHA1);
            return;
        }
    }
    // each turn step's call: `call rel32` (or a tail `jmp rel32`) to its target,
    // as shipped
    static uint8_t callOrig[kWaCalls][5];
    for (int i = 0; i < kWaCalls; i++) {
        const auto& c = kWorldCalls[i];
        int32_t rel = (int32_t)(c.target - (c.rva + 5));
        callOrig[i][0] = kWorldCallOps[i];
        memcpy(callOrig[i] + 1, &rel, 4);
        if (memcmp(g_eng.main + c.rva, callOrig[i], 5)) {
            logf("world anims: main+%X differs from main.dll sha1 %s, not patched", c.rva,
                 WORLD_ANIMS_MAIN_SHA1);
            return;
        }
    }
    uint8_t* pool = allocNear(g_eng.main, kWorldPoolSize);
    if (!pool) {
        logf("world anims: no reachable stub pool, not patched");
        return;
    }
    memcpy(pool + kWorldCodeOffset, kWorldCode, sizeof(kWorldCode));
    *(float*)(pool + kWorldZeroOffset) = 0.0f;
    *(float*)(pool + kWorldZeroOffset + 4) = 1.0f;
    bool ok = true;
    for (const auto& f : kWorldFixups) {
        if (f.next) {
            ok &= putRel32(pool + f.next, g_eng.main + f.target, pool + f.field);
        } else {
            uint64_t target = (uint64_t)(g_eng.main + f.target);
            memcpy(pool + f.field, &target, sizeof(target));
        }
    }
    // N = 1 before any jump exists: every stub is the original code
    g_waPool = pool;
    for (int g = 0; g < kWorldGroups; g++) worldAnimsApply(g, 1);
    g_waPool = nullptr;
    uint8_t jumps[kWaWindows][32];
    uint8_t disps[kWaLiterals][4];
    static uint8_t rels[kWaCalls][4];
    static GroupWrite writes[kWaWrites];
    for (int i = 0; i < kWaWindows; i++) {
        const auto& w = kWorldWindows[i];
        memset(jumps[i], 0x90, w.len);
        jumps[i][0] = 0xE9;
        ok &= putRel32(g_eng.main + w.rva + 5, pool + w.stub, jumps[i] + 1);
        writes[i] = {g_eng.main + w.rva, jumps[i], kWorldOrig + w.orig, w.len};
    }
    for (int i = 0; i < kWaLiterals; i++) {
        const auto& l = kWorldLiterals[i];
        ok &= putRel32(g_eng.main + l.rva + 8, pool + l.slot, disps[i]);
        writes[kWaWindows + i] = {g_eng.main + l.rva + 4, disps[i], kWorldLiteralOrig[i].b + 4, 4};
    }
    for (int i = 0; i < kWaCalls; i++) {
        const auto& c = kWorldCalls[i];
        ok &= putRel32(g_eng.main + c.rva + 5, pool + c.stub, rels[i]);
        writes[kWaWindows + kWaLiterals + i] = {g_eng.main + c.rva + 1, rels[i], callOrig[i] + 1, 4};
    }
    if (!ok) {
        freeNear(pool);
        logf("world anims: relocation out of reach, not patched");
        return;
    }
    FlushInstructionCache(GetCurrentProcess(), pool, kWorldPoolSize);
    bool installed = false;
    for (int attempt = 0; attempt < 32; attempt++) {
        bool safe = suspendOthers();
        for (int t = 0; t < g_susCount && safe; t++) {
            for (const auto& w : kWorldWindows) {
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
        for (const auto& w : kWorldWindows) {
            safe &= memcmp(g_eng.main + w.rva, kWorldOrig + w.orig, w.len) == 0;
        }
        for (int i = 0; i < kWaLiterals; i++) {
            safe &= memcmp(g_eng.main + kWorldLiterals[i].rva, kWorldLiteralOrig[i].b, 8) == 0;
        }
        for (int i = 0; i < kWaCalls; i++) {
            safe &= memcmp(g_eng.main + kWorldCalls[i].rva, callOrig[i], 5) == 0;
        }
        if (safe) {
            g_waPool = pool;
            g_waKept = writeGroup(writes, kWaWrites);
            g_waReady = g_waKept == kWaWrites;
            installed = true;
        }
        resumeOthers();
        break;
    }
    if (!g_waKept) {
        g_waPool = nullptr;
        freeNear(pool);
    }
    // A partial rollback keeps its pool at N = 1: every remaining jump runs the
    // original instructions and every remaining literal reads its constant.
    if (g_cfg.fixEffects && (g_cfg.fixParticles || g_cfg.fixEmitters)) {
        logf("world anims: FixEffects=1 (the old every-other-tick experiment) is on, so the "
             "particle and emitter groups stay at N = 1");
    }
    logf("world anims: %d/%d writes (%d windows, %d literals, %d calls), %s; sky=%d swing=%d "
         "human=%d particles=%d emitters=%d turn=%d scenery=%d objects=%d mode=%d repeat=%d "
         "actor=%d menu=%d steer=%d flag=%d skip=%d player=%d; follows the phase key %s",
         g_waKept, kWaWrites, kWaWindows, kWaLiterals, kWaCalls,
         g_waReady ? "ready" : installed ? "inactive after write failure" : "not patched",
         (int)g_cfg.fixSkyScroll, (int)g_cfg.fixSwingPhysics, (int)g_cfg.fixHumanAnims,
         (int)g_cfg.fixParticles, (int)g_cfg.fixEmitters, (int)g_cfg.fixTurnLimits,
         (int)g_cfg.fixScenerySway, (int)g_cfg.fixObjectAnims, (int)g_cfg.fixModeQuantities,
         (int)g_cfg.fixMenuRepeat, (int)g_cfg.fixEnemyClocks, (int)g_cfg.fixMenuScroll,
         (int)g_cfg.fixTurnSteps, (int)g_cfg.fixFlagQuantities, (int)g_cfg.fixSkipWindow,
         (int)g_cfg.fixPlayerAnims, g_cfg.phaseToggleName);
}

// Offline, for tools/verify_world_anims.py: map main.dll without running it,
// use the real installer, dump the pool and every patched byte, drive the
// per-tick update through fps, context, key, master and group switches, check
// the measurement's verdicts, then fail each write in turn.
extern "C" __declspec(dllexport) int OkamiWorldAnimSelfTest(const char* mainPath,
                                                            const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) return 2;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixWorldAnims = true;
    g_cfg.fixSkyScroll = g_cfg.fixSwingPhysics = g_cfg.fixHumanAnims = true;
    g_cfg.fixParticles = g_cfg.fixEmitters = g_cfg.fixTurnLimits = g_cfg.fixScenerySway =
        g_cfg.fixObjectAnims = g_cfg.fixModeQuantities = g_cfg.fixMenuRepeat = true;
    g_cfg.fixEnemyClocks = g_cfg.fixMenuScroll = g_cfg.fixTurnSteps = true;
    g_cfg.fixFlagQuantities = g_cfg.fixSkipWindow = g_cfg.fixPlayerAnims = true;
    g_cfg.fixFrameClocks = true;
    g_cfg.passthrough = false;
    if (!tick || !resolveFrameConfig(tick)) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    installFrameClocks();
    installShadowMode();
    installWorldAnims();
    if (!g_waReady) {
        fprintf(rep, "FAIL install\n");
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\npool %p\n", (void*)m, (void*)g_waPool);
    int fails = 0;
    uint8_t installedCode[kWorldPoolSize - kWorldCodeOffset];
    memcpy(installedCode, g_waPool + kWorldCodeOffset, sizeof(installedCode));
    snprintf(path, sizeof(path), "%s\\pool.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fails += fwrite(g_waPool, 1, kWorldPoolSize, f) != kWorldPoolSize;
        fclose(f);
    } else fails++;
    snprintf(path, sizeof(path), "%s\\patched.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& w : kWorldWindows) fails += fwrite(g_eng.main + w.rva, 1, w.len, f) != w.len;
        for (const auto& l : kWorldLiterals) fails += fwrite(g_eng.main + l.rva, 1, 8, f) != 8;
        for (const auto& c : kWorldCalls) fails += fwrite(g_eng.main + c.rva, 1, 5, f) != 5;
        fclose(f);
    } else fails++;
    // every combination through the per-tick hook: each group's mask, s and slots.
    // Each group's N depends on its own switch only, so the group switches take
    // the patterns that show that: all off, all on, each alone, each missing.
    snprintf(path, sizeof(path), "%s\\modes.csv", outDir);
    if (FILE* f = fopen(path, "w")) {
        fprintf(f, "fps,mode,real,master,groups,muted,shadow,hook,complete");
        for (int g = 0; g < kWorldGroups; g++) {
            fprintf(f, ",mask%d,scale%d,mask2_%d,smode%d,intn%d", g, g, g, g, g);
        }
        for (const auto& l : kWorldLiterals) fprintf(f, ",slot%X", l.rva);
        fprintf(f, "\n");
        const int all = (1 << kWorldGroups) - 1;
        int patterns[2 + 2 * kWorldGroups];
        int np = 0;
        patterns[np++] = 0;
        patterns[np++] = all;
        for (int g = 0; g < kWorldGroups; g++) {
            patterns[np++] = 1 << g;
            patterns[np++] = all & ~(1 << g);
        }
        for (int fps : {30, 60, 120}) for (int mode : {0, 1, 2, 3}) for (int real : {1, 2})
        for (int master : {0, 1}) for (int pi = 0; pi < np; pi++)
        for (int muted : {0, 1}) for (int shadow : {0, 1}) for (int hook : {0, 1})
        for (int complete : {0, 1}) {
            int groups = patterns[pi];
            g_fps60 = fps != 30;
            g_fpsImmsFast = fps == 120;
            *g_shadowMode = (uint8_t)mode;
            *(volatile uint8_t*)g_eng.modeByte = (uint8_t)real;
            g_shadowOn = shadow != 0;
            g_cfg.fixWorldAnims = master != 0;
            g_cfg.fixSkyScroll = (groups & 1) != 0;
            g_cfg.fixSwingPhysics = (groups & 2) != 0;
            g_cfg.fixHumanAnims = (groups & 4) != 0;
            g_cfg.fixParticles = (groups & 8) != 0;
            g_cfg.fixEmitters = (groups & 16) != 0;
            g_cfg.fixTurnLimits = (groups & 32) != 0;
            g_cfg.fixScenerySway = (groups & 64) != 0;
            g_cfg.fixObjectAnims = (groups & 128) != 0;
            g_cfg.fixModeQuantities = (groups & 256) != 0;
            g_cfg.fixMenuRepeat = (groups & 512) != 0;
            g_cfg.fixEnemyClocks = (groups & 1024) != 0;
            g_cfg.fixMenuScroll = (groups & 2048) != 0;
            g_cfg.fixTurnSteps = (groups & 4096) != 0;
            g_cfg.fixFlagQuantities = (groups & 8192) != 0;
            g_cfg.fixSkipWindow = (groups & 16384) != 0;
            g_cfg.fixPlayerAnims = (groups & 32768) != 0;
            g_phaseFixMuted = muted;
            g_fcHooked = hook != 0;
            g_waReady = complete != 0;
            frameClockOnTick();
            fprintf(f, "%d,%d,%d,%d,%d,%d,%d,%d,%d", fps, mode, real, master, groups, muted,
                    shadow, hook, complete);
            for (int g = 0; g < kWorldGroups; g++) {
                fprintf(f, ",%u,%.9g,%u,%u,%u", (unsigned)g_waPool[kWorldGroupStride * g],
                        (double)*(float*)(g_waPool + kWorldGroupStride * g + 4),
                        (unsigned)g_waPool[kWorldGroupStride * g + 1],
                        (unsigned)g_waPool[kWorldGroupStride * g + 2],
                        *(uint32_t*)(g_waPool + kWorldIntNOffset + 4 * g));
            }
            for (const auto& l : kWorldLiterals) fprintf(f, ",%.9g", (double)*(float*)(g_waPool + l.slot));
            fprintf(f, "\n");
        }
        fclose(f);
    } else fails++;
    fails += memcmp(installedCode, g_waPool + kWorldCodeOffset, sizeof(installedCode)) != 0;
    fails += *(float*)(g_waPool + kWorldZeroOffset) != 0.0f ||
             *(float*)(g_waPool + kWorldZeroOffset + 4) != 1.0f;
    // The measurement: a simulated interval through the real probes and counters.
    {
        g_cfg.fixWorldAnims = g_cfg.fixSkyScroll = g_cfg.fixSwingPhysics = g_cfg.fixHumanAnims = true;
        g_cfg.fixParticles = g_cfg.fixEmitters = g_cfg.fixTurnLimits = g_cfg.fixScenerySway =
        g_cfg.fixObjectAnims = g_cfg.fixModeQuantities = g_cfg.fixMenuRepeat = true;
        g_cfg.fixEnemyClocks = g_cfg.fixMenuScroll = g_cfg.fixTurnSteps = true;
        g_cfg.fixFlagQuantities = g_cfg.fixSkipWindow = g_cfg.fixPlayerAnims = true;
        g_fcHooked = g_waReady = true;
        g_shadowOn = true;
        *g_shadowMode = 2;
        *(volatile uint8_t*)g_eng.modeByte = 1;
        g_phaseFixMuted = 0;
        g_fps60 = 1;
        g_fpsImmsFast = true;
        frameClockOnTick();
        uint32_t* fcp = (uint32_t*)g_eng.frameCounter;
        uint32_t fc0 = *fcp;
        g_waPrevOk = false;
        measureWorldAnims(0);  // the baseline
        volatile uint32_t* probe = (volatile uint32_t*)(g_waPool + kWorldProbeOffset);
        volatile uint32_t* gate = (volatile uint32_t*)(g_waPool + kWorldCounterOffset);
        uint32_t firstClock = 0;
        for (const auto& st : kWorldSites) {
            if (st.group == kWaGroupActor && st.role == 0 && !firstClock) firstClock = st.site;
        }
        // 600 ticks: 3 bones a tick at each of the two roots, one talking head,
        // 20 particles, one enemy clock; every counter reached every tick and counting on every
        // Nth of its group (4th, 2nd for the mode group at 120), except `bad`,
        // which counts on every tick
        auto run = [&](uint32_t bad) {
            for (uint32_t t = 0; t < 600; t++) {
                (*fcp)++;
                for (const auto& st : kWorldSites) {
                    if (st.kind == WA_ROOT && st.group == 1) probe[st.probe] += 3;
                    if (st.role == 0 && st.group == 2) probe[st.probe] += 1;
                    if (st.role == 0 && st.group == 3) probe[st.probe] += 20;
                    if (st.site == firstClock) probe[st.probe] += 1;  // one enemy clock a tick
                    if (!waCounted(st.kind)) continue;
                    volatile uint32_t* c = gate + kWorldCounterStride / 4 * st.counter;
                    c[0]++;
                    if ((*fcp & (uint32_t)(g_waN[st.group] - 1)) == 0 || st.site == bad) c[1]++;
                }
            }
            measureWorldAnims(0);
        };
        run(0);
        int counted[kWorldGroups] = {};
        for (const auto& st : kWorldSites) {
            if (waCounted(st.kind)) counted[st.group]++;
        }
        WaSummary s = g_waLast;
        char v[96];
        waVerdict(s.v[3], s.n[3], v, sizeof(v));
        bool okSum = s.valid && s.n[0] == 4 && fabs(s.perTick[1][0] - 6.0) < 1e-9 &&
                     fabs(s.perTick[2][0] - 1.0) < 1e-9 && fabs(s.perTick[3][0] - 20.0) < 1e-9 &&
                     s.v[2].live == counted[2] && !s.v[2].wrong && s.v[3].live == counted[3] &&
                     !s.v[3].wrong && firstClock && s.n[kWaGroupActor] == 4 &&
                     fabs(s.perTick[kWaGroupActor][0] - 1.0) < 1e-9 &&
                     strstr(v, "/4 OK");
        fprintf(rep, "measurement at /4: swing %.2f bones/tick, talk %.2f, particles %.2f, "
                "enemy clocks %.2f /%u, effect %s: %s\n", s.perTick[1][0], s.perTick[2][0],
                s.perTick[3][0], s.perTick[kWaGroupActor][0], s.n[kWaGroupActor], v,
                okSum ? "ok" : "FAIL");
        fails += !okSum;
        // the mode group runs at /2 at 120 while the others run at /4, and the
        // repeat group at the stock context's /4
        char vm[96], vr[96];
        waVerdict(s.v[kWaGroupMode], s.n[kWaGroupMode], vm, sizeof(vm));
        waVerdict(s.v[kWaGroupRepeat], s.n[kWaGroupRepeat], vr, sizeof(vr));
        bool okF6 = s.n[kWaGroupMode] == 2 && s.n[kWaGroupRepeat] == 4 &&
                    s.v[kWaGroupMode].live == counted[kWaGroupMode] &&
                    s.v[kWaGroupRepeat].live == counted[kWaGroupRepeat] &&
                    !s.v[kWaGroupMode].wrong && !s.v[kWaGroupRepeat].wrong &&
                    strstr(vm, "/2 OK") && strstr(vr, "/4 OK");
        fprintf(rep, "measurement, mode group %s, repeat group %s: %s\n", vm, vr,
                okF6 ? "ok" : "FAIL");
        fails += !okF6;
        // one counter that counts on every tick must read WRONG, and name itself
        uint32_t bad = 0;
        for (const auto& st : kWorldSites) {
            if (st.kind == WA_COUNT && st.group == 3) bad = st.site;
        }
        run(bad);
        waVerdict(g_waLast.v[3], g_waLast.n[3], v, sizeof(v));
        char want[32];
        snprintf(want, sizeof(want), "WRONG, first %X", bad);
        bool wrongOk = strstr(v, want) != nullptr && g_waLast.v[3].wrong == 1;
        fprintf(rep, "measurement, one ungated counter: %s: %s\n", v, wrongOk ? "ok" : "FAIL");
        fails += !wrongOk;
        // a counter reached only on the ticks between stock ticks (its particle
        // dies on each stock tick) counts on none of them: intermittent, not WRONG
        for (uint32_t t = 0; t < 600; t++) {
            (*fcp)++;
            for (const auto& st : kWorldSites) {
                if (!waCounted(st.kind)) continue;
                if (st.site == bad && (*fcp & 3) == 0) continue;
                volatile uint32_t* c = gate + kWorldCounterStride / 4 * st.counter;
                c[0]++;
                if ((*fcp & 3) == 0) c[1]++;
            }
        }
        measureWorldAnims(0);
        waVerdict(g_waLast.v[3], g_waLast.n[3], v, sizeof(v));
        bool interOk = !g_waLast.v[3].wrong && g_waLast.v[3].intermittent == 1 &&
                       strstr(v, "/4 OK, 1 intermittent") != nullptr;
        fprintf(rep, "measurement, one intermittent counter: %s: %s\n", v,
                interOk ? "ok" : "FAIL");
        fails += !interOk;
        *fcp = fc0;
        g_waPrevOk = false;
    }
    g_cfg.fixWorldAnims = g_cfg.fixSkyScroll = g_cfg.fixSwingPhysics = g_cfg.fixHumanAnims = true;
    g_cfg.fixParticles = g_cfg.fixEmitters = g_cfg.fixTurnLimits = g_cfg.fixScenerySway =
        g_cfg.fixObjectAnims = g_cfg.fixModeQuantities = g_cfg.fixMenuRepeat = true;
    *(volatile uint8_t*)g_eng.modeByte = 1;
    g_fcHooked = true;
    g_waReady = true;
    g_shadowOn = true;
    *g_shadowMode = 2;
    g_phaseFixMuted = 0;
    g_fps60 = 1;
    g_fpsImmsFast = true;
    // Every failed write, including a failed undo, leaves what remains at N = 1.
    g_faultLoop = true;  // no protection change a write, no thread snapshot an install
    for (int rest = 0; rest <= 1; rest++) for (int k = 0; k < kWaWrites; k++) {
        for (const auto& w : kWorldWindows)
            fails += !writeProtected(g_eng.main + w.rva, kWorldOrig + w.orig, w.len);
        for (int i = 0; i < kWaLiterals; i++)
            fails += !writeProtected(g_eng.main + kWorldLiterals[i].rva, kWorldLiteralOrig[i].b, 8);
        for (int i = 0; i < kWaCalls; i++) {
            const auto& c = kWorldCalls[i];
            uint8_t orig[5] = {kWorldCallOps[i]};
            int32_t rel = (int32_t)(c.target - (c.rva + 5));
            memcpy(orig + 1, &rel, 4);
            fails += !writeProtected(g_eng.main + c.rva, orig, 5);
        }
        freeNear(g_waPool);
        g_waPool = nullptr;
        g_waReady = false;
        g_waKept = 0;
        for (int g = 0; g < kWorldGroups; g++) g_waN[g] = 1, g_waSmode[g] = 0;
        g_writeCount = 0;
        g_writeFailAt = k;
        g_writeFailRest = rest != 0;
        installWorldAnims();
        g_writeFailAt = -1;
        g_writeFailRest = false;
        frameClockOnTick();
        fails += g_waReady || g_waKept != (rest ? k : 0);
        if (g_waKept) {
            fails += !g_waPool;
            for (int g = 0; g < kWorldGroups && g_waPool; g++) {
                fails += g_waPool[kWorldGroupStride * g] != 0 ||
                         g_waPool[kWorldGroupStride * g + 1] != 0 ||
                         g_waPool[kWorldGroupStride * g + 2] != 0 ||
                         *(uint32_t*)(g_waPool + kWorldIntNOffset + 4 * g) != 1 ||
                         *(float*)(g_waPool + kWorldGroupStride * g + 4) != 1.0f;
            }
        } else {
            fails += g_waPool != nullptr;
        }
        for (int i = 0; i < kWaWindows; i++) {
            const auto& w = kWorldWindows[i];
            uint8_t want[32];
            memcpy(want, kWorldOrig + w.orig, w.len);
            if (i < g_waKept) {
                memset(want, 0x90, w.len);
                want[0] = 0xE9;
                fails += !putRel32(g_eng.main + w.rva + 5, g_waPool + w.stub, want + 1);
            }
            fails += memcmp(want, g_eng.main + w.rva, w.len) != 0;
        }
        for (int i = 0; i < kWaLiterals; i++) {
            const auto& l = kWorldLiterals[i];
            uint8_t want[8];
            memcpy(want, kWorldLiteralOrig[i].b, 8);
            if (kWaWindows + i < g_waKept) {
                fails += !putRel32(g_eng.main + l.rva + 8, g_waPool + l.slot, want + 4);
            }
            fails += memcmp(want, g_eng.main + l.rva, 8) != 0;
        }
        for (int i = 0; i < kWaCalls; i++) {
            const auto& c = kWorldCalls[i];
            uint8_t want[5] = {kWorldCallOps[i]};
            int32_t rel = (int32_t)(c.target - (c.rva + 5));
            memcpy(want + 1, &rel, 4);
            if (kWaWindows + kWaLiterals + i < g_waKept) {
                fails += !putRel32(g_eng.main + c.rva + 5, g_waPool + c.stub, want + 1);
            }
            fails += memcmp(want, g_eng.main + c.rva, 5) != 0;
        }
    }
    g_faultLoop = false;
    fprintf(rep, "failed-write cases %d\n%s (%d failures)\n", 2 * kWaWrites, fails ? "FAIL" : "PASS",
            fails);
    fclose(rep);
    return fails ? 1 : 0;
}
