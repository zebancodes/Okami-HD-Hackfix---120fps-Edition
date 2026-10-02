// The scripted tasks' pauses at their stock length and their stepping loops
// at one pass a stock tick.
// Included once by dinput8_proxy.cpp after the world animations.
//
// Every scripted event runs in a task, a coroutine that yields with the task
// wait main+4567C0(task, n); the task manager counts n down by one a tick. At
// 120 fps a pause of n ticks is a quarter of stock's, and a loop that yields
// with wait(1) runs four passes per stock tick. tools/gen_task_waits.py writes
// task_waits.h: a stub with two entries (a pause, a loop's pass) and the calls
// of the wait it takes over (task_waits.csv has every call and why the others
// are left). Each call's rel32 is retargeted at its entry once, at startup,
// with the game's other threads suspended; after that only the pool's N
// changes, on the game thread in the per-tick hook. The stub runs on the
// task's own thread: it multiplies the length by N, caps it at the countdown's
// 0xFFFF and jumps on to the wait. N is fps over the stock context's rate, the
// phase steps' N; at N = 1 (30 fps, F9, the timer key muted, FixTaskWaits=0,
// Passthrough) the stub hands the length on untouched.
//
// The skip latch, installed with them: the event camera sequencer's loops,
// now one pass a stock tick, check the skip button on its press edge, which
// lasts a tick. flower_tick's call of the task manager (after the pad update)
// goes through a stub that keeps the last four ticks' press words, and the
// skip check's two reads of them OR in those of the previous N - 1 ticks: a
// reader once a stock tick sees every press once. At N = 1 that OR is zero
// and the reads are the originals.
#include "task_waits.h"

static constexpr int kTwSites = (int)(sizeof(kTaskWaitSites) / sizeof(kTaskWaitSites[0]));
static constexpr int kTwWindows = (int)(sizeof(kTaskWaitWindows) / sizeof(kTaskWaitWindows[0]));
// the group: every call, then the task manager's call, then the windows
static constexpr int kTwWrites = kTwSites + 1 + kTwWindows;
static uint8_t* g_twPool = nullptr;
static bool g_twReady = false;
static int g_twKept = 0;
static volatile LONG g_twN = 1;
static volatile LONG g_twChanges = 0;

// N for this tick: fps over the stock context's rate while the fix is on.
static unsigned taskWaitsN() {
    if (!g_twReady || !g_fcHooked || !g_cfg.fixTaskWaits || g_cfg.passthrough || !g_fps60 ||
        g_timerFixMuted || !g_shadowOn || !g_shadowMode) {
        return 1;
    }
    uint8_t mode = *g_shadowMode;
    if (mode != 1 && mode != 2) {
        return 1;  // no stock context: the original lengths
    }
    unsigned fps = g_fpsImmsFast ? 120u : 60u;
    return fps / (mode == 1 ? 60u : 30u);
}

// From the per-tick hook, before the tick's tasks run.
static void updateTaskWaits() {
    if (!g_twPool) return;
    unsigned n = taskWaitsN();
    if (n != (unsigned)g_twN) {
        *(volatile uint32_t*)(g_twPool + kTaskWaitNOffset) = n;
        InterlockedExchange(&g_twN, (LONG)n);
        InterlockedIncrement(&g_twChanges);
    }
}

static const char* taskWaitState() {
    if (!g_cfg.fixTaskWaits) return "off(ini)";
    if (!g_twReady || !g_fcHooked) return "NOT INSTALLED";
    if (!g_fps60) return "stock";
    if (g_timerFixMuted) return "MUTED";
    return "on";
}

// From the watcher once per status interval: how many of the taken-over
// pauses began, scaled or not, the stock ticks the scaled ones asked for, and
// the loop passes made at one a stock tick.
static uint32_t g_twPrev[4] = {};
static bool g_twPrevOk = false;
static LONG g_twPrevChanges = 0;
static void measureTaskWaits(LONGLONG now) {
    (void)now;
    if (!g_twPool) return;
    const volatile uint32_t* p = (const volatile uint32_t*)g_twPool;
    uint32_t cur[4] = {p[kTaskWaitScaledOffset / 4], p[kTaskWaitPlainOffset / 4],
                       p[kTaskWaitTicksOffset / 4], p[kTaskWaitLoopsOffset / 4]};
    uint32_t ds = cur[0] - g_twPrev[0], dp = cur[1] - g_twPrev[1];
    uint32_t dt = cur[2] - g_twPrev[2], dl = cur[3] - g_twPrev[3];
    bool ok = g_twPrevOk;
    bool changed = g_twChanges != g_twPrevChanges;
    memcpy(g_twPrev, cur, sizeof(cur));
    g_twPrevOk = true;
    g_twPrevChanges = g_twChanges;
    if (!ok || (!ds && !dp && !dl)) return;  // no scripted pause or loop: nothing to say
    logf("task waits: %s /%ld | %u pauses scaled (%u stock ticks, %.2f s at stock 30), %u loop "
         "passes at one a stock tick, %u calls at their shipped length%s", taskWaitState(),
         (long)g_twN, ds, dt, dt / 30.0, dl, dp, changed ? " | N changed in the interval" : "");
}

// The group's writes, in order, into caller-owned storage.
static void taskWaitWrites(uint8_t* pool, GroupWrite* writes, uint8_t (*rels)[4],
                           uint8_t* tickRel, uint8_t (*jumps)[7], bool* ok) {
    for (int i = 0; i < kTwSites; i++) {
        const auto& s = kTaskWaitSites[i];
        uint32_t entry = s.entry ? kTaskWaitLoopEntry : kTaskWaitPauseEntry;
        *ok &= putRel32(g_eng.main + s.rva + 5, pool + entry, rels[i]);
        writes[i] = {g_eng.main + s.rva + 1, rels[i], &s.rel, 4};
    }
    *ok &= putRel32(g_eng.main + kTaskWaitTickCallRva + 5, pool + kTaskWaitTickEntry, tickRel);
    writes[kTwSites] = {g_eng.main + kTaskWaitTickCallRva + 1, tickRel, &kTaskWaitTickCallRel, 4};
    for (int i = 0; i < kTwWindows; i++) {
        const auto& w = kTaskWaitWindows[i];
        jumps[i][0] = 0xE9;
        *ok &= putRel32(g_eng.main + w.rva + 5, pool + w.code, jumps[i] + 1);
        jumps[i][5] = jumps[i][6] = 0xCC;
        writes[kTwSites + 1 + i] = {g_eng.main + w.rva, jumps[i], w.orig, 7};
    }
}

static void installTaskWaits() {
    if (!g_cfg.fixTaskWaits || g_cfg.passthrough || !g_eng.main || g_twPool) return;
    if (!g_fcHooked || g_fcStranded || !g_shadowOk) {
        logf("task waits: shared tick hook or stock context unavailable, not patched");
        return;
    }
    for (const auto& s : kTaskWaitSites) {
        const uint8_t* at = g_eng.main + s.rva;
        int32_t rel;
        memcpy(&rel, at + 1, 4);
        if (at[0] != s.op || (s.op != 0xE8 && s.op != 0xE9) || rel != s.rel ||
            at + 5 + rel != g_eng.main + kTaskWaitRva) {
            logf("task waits: main+%X differs from main.dll sha1 %s, not patched", s.rva,
                 TASK_WAITS_MAIN_SHA1);
            return;
        }
    }
    {
        const uint8_t* at = g_eng.main + kTaskWaitTickCallRva;
        int32_t rel;
        memcpy(&rel, at + 1, 4);
        bool bad = at[0] != 0xE8 || rel != kTaskWaitTickCallRel ||
                   at + 5 + rel != g_eng.main + kTaskManagerRva;
        for (const auto& w : kTaskWaitWindows) bad |= memcmp(g_eng.main + w.rva, w.orig, 7) != 0;
        if (bad) {
            logf("task waits: the task manager's call or the skip check differs from main.dll "
                 "sha1 %s, not patched", TASK_WAITS_MAIN_SHA1);
            return;
        }
    }
    uint8_t* pool = allocNear(g_eng.main, kTaskWaitPoolSize);
    if (!pool) {
        logf("task waits: no reachable stub pool, not patched");
        return;
    }
    memcpy(pool + kTaskWaitCodeOffset, kTaskWaitCode, sizeof(kTaskWaitCode));
    *(uint32_t*)(pool + kTaskWaitNOffset) = 1;  // N = 1 before any call reaches it
    bool ok = true;
    for (const auto& f : kTaskWaitFixups) {
        ok &= putRel32(pool + f.next, g_eng.main + f.target, pool + f.field);
    }
    static uint8_t rels[kTwSites][4];
    static uint8_t tickRel[4];
    static uint8_t jumps[kTwWindows][7];
    static GroupWrite writes[kTwWrites];
    taskWaitWrites(pool, writes, rels, tickRel, jumps, &ok);
    if (!ok) {
        freeNear(pool);
        logf("task waits: stub pool out of reach, not patched");
        return;
    }
    FlushInstructionCache(GetCurrentProcess(), pool, kTaskWaitPoolSize);
    bool installed = false;
    for (int attempt = 0; attempt < 32; attempt++) {
        bool safe = suspendOthers();
        // a thread stopped inside a write's bytes would resume on a torn
        // instruction: none may be
        for (int t = 0; t < g_susCount && safe; t++) {
            for (int i = 0; i < kTwWrites && safe; i++) {
                DWORD64 start = (DWORD64)writes[i].dst - (i < kTwSites + 1 ? 1 : 0);
                DWORD64 len = i < kTwSites + 1 ? 5 : 7;
                if (g_susRip[t] > start && g_susRip[t] < start + len) safe = false;
            }
        }
        if (!safe) {
            resumeOthers();
            Sleep(1);
            continue;
        }
        for (int i = 0; i < kTwWrites; i++) {
            safe &= memcmp(writes[i].dst, writes[i].orig, writes[i].len) == 0;
        }
        if (safe) {
            g_twPool = pool;
            g_twKept = writeGroup(writes, kTwWrites);
            g_twReady = g_twKept == kTwWrites;
            installed = true;
        }
        resumeOthers();
        break;
    }
    if (!g_twKept) {
        g_twPool = nullptr;
        freeNear(pool);
    }
    // A partial rollback keeps its pool at N = 1: every call left retargeted
    // reaches the wait with its shipped length, and the skip check's history
    // stays zero.
    int loops = 0;
    for (const auto& s : kTaskWaitSites) loops += s.entry;
    logf("task waits: %d/%d writes (%d pauses, %d loop waits, the skip latch), %s; follows the "
         "timer key %s", g_twKept, kTwWrites, kTwSites - loops, loops,
         g_twReady ? "ready" : installed ? "inactive after write failure" : "not patched",
         g_cfg.timerToggleName);
}

// Offline, for tools/verify_task_waits.py: map main.dll without running it,
// use the real installer, dump the pool and every patched call, drive the
// per-tick update through fps, context, key, switch and hook states, then
// fail each write in turn.
extern "C" __declspec(dllexport) int OkamiTaskWaitSelfTest(const char* mainPath,
                                                           const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) return 2;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixTaskWaits = true;
    g_cfg.fixFrameClocks = true;
    g_cfg.passthrough = false;
    if (!tick || !resolveFrameConfig(tick)) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    installFrameClocks();
    installShadowMode();
    installTaskWaits();
    if (!g_twReady) {
        fprintf(rep, "FAIL install\n");
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\npool %p\n", (void*)m, (void*)g_twPool);
    int fails = 0;
    snprintf(path, sizeof(path), "%s\\pool.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fails += fwrite(g_twPool, 1, kTaskWaitPoolSize, f) != kTaskWaitPoolSize;
        fclose(f);
    } else fails++;
    // every call's 5 bytes, the task manager's call's 5, each window's 7
    snprintf(path, sizeof(path), "%s\\patched.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& s : kTaskWaitSites) fails += fwrite(g_eng.main + s.rva, 1, 5, f) != 5;
        fails += fwrite(g_eng.main + kTaskWaitTickCallRva, 1, 5, f) != 5;
        for (const auto& w : kTaskWaitWindows) fails += fwrite(g_eng.main + w.rva, 1, 7, f) != 7;
        fclose(f);
    } else fails++;
    snprintf(path, sizeof(path), "%s\\modes.csv", outDir);
    if (FILE* f = fopen(path, "w")) {
        fprintf(f, "fps,mode,fix,muted,shadow,hook,complete,n\n");
        for (int fps : {30, 60, 120}) for (int mode : {0, 1, 2, 3}) for (int fix : {0, 1})
        for (int muted : {0, 1}) for (int shadow : {0, 1}) for (int hook : {0, 1})
        for (int complete : {0, 1}) {
            g_fps60 = fps != 30;
            g_fpsImmsFast = fps == 120;
            *g_shadowMode = (uint8_t)mode;
            g_shadowOn = shadow != 0;
            g_cfg.fixTaskWaits = fix != 0;
            g_timerFixMuted = muted;
            g_fcHooked = hook != 0;
            g_twReady = complete != 0;
            frameClockOnTick();
            fprintf(f, "%d,%d,%d,%d,%d,%d,%d,%u\n", fps, mode, fix, muted, shadow, hook,
                    complete, *(uint32_t*)(g_twPool + kTaskWaitNOffset));
        }
        fclose(f);
    } else fails++;
    // Every failed write, including a failed undo, leaves what remains at N = 1.
    g_cfg.fixTaskWaits = true;
    g_fcHooked = true;
    g_shadowOn = true;
    *g_shadowMode = 2;
    g_timerFixMuted = 0;
    g_fps60 = 1;
    g_fpsImmsFast = true;
    // a representative sample of the write positions (every one would take
    // kTwWrites squared writes): the ends, the middle, the last call, the task
    // manager's call and each window
    const int picks[] = {0, 1, 2, kTwSites / 3, kTwSites / 2, kTwSites - 1, kTwSites,
                         kTwSites + 1, kTwWrites - 1};
    static uint8_t rels[kTwSites][4];
    static uint8_t tickRel[4];
    static uint8_t jumps[kTwWindows][7];
    static GroupWrite want[kTwWrites];
    int cases = 0;
    g_faultLoop = true;  // no protection change a write, no thread snapshot an install
    for (int rest = 0; rest <= 1; rest++) for (int k : picks) {
        bool reach = true;   // put everything back as shipped before the next case
        taskWaitWrites(g_twPool, want, rels, tickRel, jumps, &reach);
        for (int i = kTwWrites - 1; i >= 0; i--) {
            fails += !writeProtected(want[i].dst, want[i].orig, want[i].len);
        }
        freeNear(g_twPool);
        g_twPool = nullptr;
        g_twReady = false;
        g_twKept = 0;
        g_twN = 1;
        g_writeCount = 0;
        g_writeFailAt = k;
        g_writeFailRest = rest != 0;
        installTaskWaits();
        g_writeFailAt = -1;
        g_writeFailRest = false;
        frameClockOnTick();
        cases++;
        fails += g_twReady || g_twKept != (rest ? k : 0);
        if (g_twKept) {
            fails += !g_twPool || *(uint32_t*)(g_twPool + kTaskWaitNOffset) != 1;
            bool ok = true;
            taskWaitWrites(g_twPool, want, rels, tickRel, jumps, &ok);
            fails += !ok;
        } else {
            fails += g_twPool != nullptr;
        }
        for (int i = 0; i < kTwWrites; i++) {
            const void* expect = i < g_twKept ? want[i].bytes : want[i].orig;
            fails += memcmp(expect, want[i].dst, want[i].len) != 0;
        }
    }
    g_faultLoop = false;
    fprintf(rep, "failed-write cases %d\n%s (%d failures)\n", cases, fails ? "FAIL" : "PASS",
            fails);
    fclose(rep);
    return fails ? 1 : 0;
}
