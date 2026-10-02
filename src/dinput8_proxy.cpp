// DINPUT8 proxy for Okami HD -- 60 FPS unlock
//
// Loaded as `DINPUT8.dll` next to okami.exe because flower_kernel.dll imports
// DirectInput8Create by name. Forwards that call to the real system
// dinput8.dll (or another proxy, see okami.ini) and applies a runtime patch
// set to the game:
//
//   1. Disable the PS2 display mode (SetPs2DispMode(false)). The PC port
//      boots in PS2 presentation mode, which is what locks the engine at
//      30 Hz with its native step configuration.
//   2. Force the engine's 60 fps configuration byte to 1. Every flower_tick
//      then writes fps=60 and timeScale=0.5, which keeps game-time running at
//      real speed at double the tick rate. The game's own writes to that
//      byte are pointed at a private shadow byte (src/shadow_mode.h), which
//      keeps the stock game's 30/60 Hz context; if the table does not match
//      the build, the `mov byte ptr [mode], 2` immediates are rewritten to 1.
//   3. Hook the swap chain's Present (IDXGISwapChain vtable slot 8): present
//      without a vblank wait and enforce a 16.667 ms game-step grid with a
//      high-resolution timer. The stock present path is what paces the game
//      at 30 steps/s; the game's host loop only drains flower_tick().
//   4. Set the config refresh rate to 60 through SystemConfig::SetRefleshRate.
//
// Every engine symbol is resolved by export name at runtime and every code
// site is verified before it is written, so a mismatched game build leaves
// the game untouched (stock 30 fps) instead of corrupting it. The patch is
// applied in memory only; no game files are modified.

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <objbase.h>  // REFIID, LPUNKNOWN
#include <dxgi.h>
#include <mmsystem.h>  // timeBeginPeriod
#include <tlhelp32.h>  // thread snapshots, for suspendOthers

#include <cctype>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

#define OKAMI_HACKFIX_VERSION "1.0.1"

static bool readableRange(const void* p, size_t n);  // defined with the probes
static uint8_t* allocNear(uint8_t* nearTo, size_t size);  // defined with the patch helpers
static void freeNear(void* p);                            // gives an allocNear block back
static void updateSlowFrame();  // defined with the frame-counter oscillators
static void logFixState(const char* why);  // defined with the A/B mute flags
static bool applyShadowMode(bool on);  // defined with the shadow mode byte
static void updateTurnPairs();  // defined with the turn rate
static void updateIntegerSkips();  // data-only F1 gate, also refreshed on flower_tick
static void updateMenuTransitions();  // M2 menu transitions: pool data and field watch, per tick
static const char* menuTransitionState();
static void updateWorldAnims();  // world animations: each group's pool data, per tick
static void updateTaskWaits();  // task waits: the stub's N, per tick
static const char* worldAnimState();
static void updateDayClock();  // data-only day/night gate (day_clock_runtime.h), the same way
static void dayClockOnTick(LONGLONG now);  // its field watch, from the per-tick hook
static void constPoolsOnTick();  // phase steps and decays at the stock context's rate
#ifdef OKAMI_TRACER
static void tracerLoadConfig(const char* ini);  // src/tracer_runtime.h
static bool tracerOverlay(char* line, size_t n, double tickHz);
#endif

#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif

// ---------------------------------------------------------------------------
// Logging (okami_hackfix.log next to the DLL)
// ---------------------------------------------------------------------------

static FILE* g_log = nullptr;
static SRWLOCK g_logLock = SRWLOCK_INIT;
static LONGLONG g_startTicks = 0;
static LONGLONG g_qpcFreq = 1;

static LONGLONG qpc() {
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    return now.QuadPart;
}

static thread_local int t_inLog = 0;

static void logf(const char* fmt, ...) {
    if (t_inLog) {
        return;  // re-entered on the same thread (fault inside a log call)
    }
    t_inLog = 1;
    AcquireSRWLockExclusive(&g_logLock);
    if (g_log) {
        double t = (double)(qpc() - g_startTicks) / (double)g_qpcFreq;
        fprintf(g_log, "[%9.3f] ", t);
        va_list ap;
        va_start(ap, fmt);
        vfprintf(g_log, fmt, ap);
        va_end(ap);
        fputc('\n', g_log);
        fflush(g_log);
    }
    ReleaseSRWLockExclusive(&g_logLock);
    t_inLog = 0;
}

// ---------------------------------------------------------------------------
// Fault guard
//
// A few callbacks run on the game's own threads and read game memory that can
// be freed under them (the harness's player, the task and gate tracers, the
// diagnostics). A fault in one must end that callback, not the game:
// guardedCall(fn, arg) runs fn(arg) and returns 0, or the exception code of a
// hardware fault that ended it early.
//
// Compilers that target the MSVC ABI (cl, clang-cl, clang with an -msvc
// triple) have __try/__except for this. GCC has no structured exception
// handling syntax at all, so there a vectored handler does the same job:
// guardedCall captures its own context on entry, and a fault on the same
// thread while fn runs resumes at that capture with the fault's code set --
// what __except does, minus the unwind, which nothing guarded here needs (no
// destructors, no __finally). Only hardware faults are taken: a software
// exception (a C++ throw, OutputDebugString's) goes on to whatever handles it,
// as it would with __try around it. Defining OKAMI_VEH_GUARD builds the GCC
// path with any compiler, so it can be tested where there is no GCC.
// ---------------------------------------------------------------------------

typedef void (*GuardedFn)(void* arg);

#if defined(_MSC_VER) && !defined(OKAMI_VEH_GUARD)
static DWORD guardedCall(GuardedFn fn, void* arg) {
    DWORD code = 0;
    __try {
        fn(arg);
    } __except (code = GetExceptionCode(), EXCEPTION_EXECUTE_HANDLER) {
    }
    return code;
}
#else
struct FaultGuard {
    CONTEXT resume;       // captured on entry to guardedCall
    FaultGuard* outer;    // the guard this one is nested in, if any
    volatile DWORD code;  // set by the handler just before it resumes
};
static DWORD g_guardTls = TLS_OUT_OF_INDEXES;
static INIT_ONCE g_guardOnce = INIT_ONCE_STATIC_INIT;

static LONG CALLBACK guardHandler(EXCEPTION_POINTERS* ep) {
    // every exception on every thread comes here first: be quick, and leave
    // the thread's last error as it found it
    DWORD err = GetLastError();
    FaultGuard* g = (FaultGuard*)TlsGetValue(g_guardTls);
    SetLastError(err);
    if (!g) {
        return EXCEPTION_CONTINUE_SEARCH;
    }
    DWORD code = ep->ExceptionRecord->ExceptionCode;
    switch (code) {
    case EXCEPTION_ACCESS_VIOLATION:
    case EXCEPTION_IN_PAGE_ERROR:
    case EXCEPTION_ILLEGAL_INSTRUCTION:
    case EXCEPTION_PRIV_INSTRUCTION:
    case EXCEPTION_INT_DIVIDE_BY_ZERO:
    case EXCEPTION_INT_OVERFLOW:
    case EXCEPTION_DATATYPE_MISALIGNMENT:
    case EXCEPTION_ARRAY_BOUNDS_EXCEEDED:
        break;
    default:
        return EXCEPTION_CONTINUE_SEARCH;
    }
    TlsSetValue(g_guardTls, g->outer);
    SetLastError(err);
    g->code = code;
    *ep->ContextRecord = g->resume;
    return EXCEPTION_CONTINUE_EXECUTION;
}

static BOOL CALLBACK guardInit(PINIT_ONCE, PVOID, PVOID*) {
    g_guardTls = TlsAlloc();
    if (g_guardTls != TLS_OUT_OF_INDEXES && !AddVectoredExceptionHandler(1, guardHandler)) {
        TlsFree(g_guardTls);
        g_guardTls = TLS_OUT_OF_INDEXES;
    }
    return TRUE;
}

// noinline: the capture has to be taken in a frame that is still live when
// the handler resumes it, and that is this one only while fn runs
static __attribute__((noinline)) DWORD guardedCall(GuardedFn fn, void* arg) {
    InitOnceExecuteOnce(&g_guardOnce, guardInit, nullptr, nullptr);
    if (g_guardTls == TLS_OUT_OF_INDEXES) {
        fn(arg);  // no handler could be installed: run it unguarded
        return 0;
    }
    FaultGuard g;
    g.outer = (FaultGuard*)TlsGetValue(g_guardTls);
    g.code = 0;
    // Returns here twice: now, and after a fault, when the handler puts this
    // context back. Between the two only memory differs, and the one thing
    // read afterwards, g.code, is volatile.
    RtlCaptureContext(&g.resume);
    if (g.code) {
        return g.code;
    }
    TlsSetValue(g_guardTls, &g);
    fn(arg);
    TlsSetValue(g_guardTls, g.outer);
    return 0;
}
#endif

// Offline self-test, driven by tools/verify_fault_guard.py: a fault inside the
// guard comes back as its code, a clean call as 0, the thread carries on, and
// a second fault after the first is caught too (the guard re-arms).
static void guardTestFault(void* p) {
    *(volatile int*)p = 1;
}
static void guardTestClean(void* p) {
    *(int*)p += 1;
}
extern "C" __declspec(dllexport) int OkamiFaultGuardSelfTest() {
    int x = 0;
    DWORD a = guardedCall(guardTestFault, (void*)16);
    DWORD b = guardedCall(guardTestClean, &x);
    DWORD c = guardedCall(guardTestFault, nullptr);
    DWORD d = guardedCall(guardTestClean, &x);
    bool ok = a == EXCEPTION_ACCESS_VIOLATION && b == 0 && c == EXCEPTION_ACCESS_VIOLATION &&
              d == 0 && x == 2;
    return ok ? 0 : 1;
}

// ---------------------------------------------------------------------------
// Configuration (okami.ini, [Main])
// ---------------------------------------------------------------------------

struct Config {
    // The player's settings live in okami_hackfix.ini; the development-era
    // okami.ini is read when that is absent, and then Developer defaults to 1
    // so a test setup keeps its keys, logs and watches without editing it.
    char iniPath[MAX_PATH] = "";
    bool iniFound = false;
    bool iniLegacy = false;     // the config came from okami.ini
    bool developer = false;     // A/B keys, harness, watches, status lines
    int defaultFps = 120;       // 30, 60 or 120 (the rate the game starts at)
    UINT toggleVk = VK_F9;      // 0 = disabled
    char toggleName[32] = "F9";
    bool requireFocus = true;
    bool beep = true;
    UINT syncInterval = 0;      // Present sync interval in 60 fps mode
    int statusInterval = 5;     // seconds, 0 = off
    bool fixes = true;          // experimental game-logic fixes in 60 fps mode
    char halfRateTasks[512] = "";  // comma-separated task class name prefixes
    bool fixMenus = false;      // half-rate the sub-screen (pause menu, brush) update slot
    bool fixHud = false;        // half-rate the HUD element update slot
    bool fixEffects = false;    // half-rate the effect (esp*) step slot
    char extraGates[512] = "";  // extra "<class prefix|vtable RVA>:<slot>" gates
    char probes[1024] = "";     // count-only function probes "fn:<rva>:<len>[:<fix>/..]"
    char watchBytes[256] = "";  // hex RVAs of bytes shown in the status line
    char gateSets[1024] = "";   // '|'-separated sets of probe names to half-rate, cycled by the set key
    char gateSetNames[512] = "";  // '|'-separated labels for those sets, shown on the overlay
    bool overlay = false;       // on-screen status line (mode, fixes, active gate set)
    bool speedLog = false;      // log every 100 ms player sample (speed + state)
    bool fixRunSpeed = true;    // real-time jog/run speed in 60 fps mode
    bool fixAnimRate = true;    // keep the run/dash animation rate at its 30 fps value
    UINT speedToggleVk = VK_F8; // hotkey that A/Bs the movement fixes (0 = none)
    char speedToggleName[32] = "F8";
    bool fixInputWindows = true;  // undo the doubly-compensated cPad::ActSet windows
    bool fixFrameGates = true;  // real-time rate for effects gated off the frame counter
    bool fixFramePhases = true;  // real-time rate for the UI oscillators
    bool fixFrameClocks = true;  // every other frame-counter clock (frame_clocks.h)
    bool fixIntegerSkips = false;  // experimental UI integer clocks (F1)
    bool fixDayClock = true;  // the day/night clock at the stock tick rate (day_clock.h)
    bool brushWatch = true;   // log each use of the brush's Rejuvenation stages (brush_watch.h)
    bool enemyWatch = true;   // log what each hit does to an enemy (enemy_watch.h)
    bool fixMenuTransitions = true;  // M2: scene transition, pause drop, HUD fade (menu_transitions.h)
    bool fixWorldAnims = true;    // world animations, first set (world_anims.h); the groups:
    bool fixSkyScroll = true;     //   objScroll's UV scroll: sky, clouds, water layers
    bool fixSwingPhysics = true;  //   swinging bones: sleeves, hair, sashes
    bool fixHumanAnims = true;    //   villagers' talk head-bob and mood particles
    bool fixParticles = true;     //   the effect engine's shared particle step
    bool fixEmitters = true;      //   the effect emitters' ages
    bool fixTurnLimits = true;    //   how fast walkers and enemies turn toward a target
    bool fixScenerySway = true;   //   trees', bushes' and other scenery's sway
    bool fixObjectAnims = true;   //   objects' own animation: the reflector, item fades
    bool fixModeQuantities = true;  // the port's "x mode" steps (F6): event camera, HUD timer
    bool fixMenuRepeat = true;    //   the menus' held-direction repeat at the stock rate
    bool fixEnemyClocks = true;   //   enemies' state timers, counted in their own time
    bool fixMenuScroll = true;    //   the sub-screens' list scroll, open and close
    bool fixTurnSteps = true;     //   turns through 2DDF90 / 2DA570, enemies' 23A2E0
    bool fixFlagQuantities = true;  // the port's `n << 60 fps flag` lengths: rumble, fade
    bool fixSkipWindow = true;    //   the skip prompt's second-press window at 5 s
    bool fixPlayerAnims = true;   //   Amaterasu's own timers and motions, her weapons' pieces
    bool fixTaskWaits = true;     // scripted pauses and stepping loops at their stock length
    UINT integerToggleVk = VK_F4;
    char integerToggleName[32] = "F4";
    bool fixModeConstants = true;  // per-mode damping/advance constants beyond 60 fps
    bool fixModeMultipliers = true;  // the integer x2 half of the same family
    bool fixSlopeTerm = true;  // the unscaled half of the movement speed target
    bool fixAirAccel = true;   // airborne acceleration needs ts^2, not ts
    bool fixStickDrift = true; // the stick's steering in the wall recoil (+0x10E8), k^ts gain
    int drawDistance = 1;      // placed objects' draw limit +D72 times this (1 = stock, max 6)
    bool fixAirGates = true;   // per-tick speed thresholds in the jump path
    bool fixHoistDecay = true; // speed damps whose factor sits in a register
    bool fixTurnRate = true;   // the angular approach every actor turns with
    bool fps120 = false;        // experimental: run the fast mode at 120 instead of 60
    bool fixDecay = true;       // real-time damping/smoothing in 60 fps mode
    bool fixLaunchVelocity = true;  // undo the double-scaled launch velocities
    bool fixPhaseSteps = true;  // real-time effect/fade/scroll phases in 60 fps mode
    UINT phaseToggleVk = VK_F5; // hotkey that A/Bs the phase step fix (0 = none)
    char phaseToggleName[32] = "F5";
    bool fixActionTimers = true;  // real-time action durations in 60 fps mode
    UINT timerToggleVk = VK_F6; // hotkey that A/Bs the action timer fix (0 = none)
    char timerToggleName[32] = "F6";
    bool jumpTrace = false;     // log every sample of a jump's climb (diagnostic)
    bool fixJumpHeight = true;  // real-time jump/wall-jump height in 60 fps mode
    UINT jumpToggleVk = VK_F7;  // hotkey that A/Bs the jump fix (0 = none)
    char jumpToggleName[32] = "F7";
    UINT setVk = 0;             // hotkey cycling the active gate set (0 = none)
    char setName[32] = "None";
    int gateTrace = 0;          // log the callers of the first N calls of each gate
    UINT fixToggleVk = VK_F10;  // hotkey toggling those fixes (0 = none)
    char fixToggleName[32] = "F10";
    UINT markVk = 0;            // hotkey writing a labelled probe snapshot (0 = none)
    char markName[32] = "None";
    char harnessName[32] = "F3";  // hotkey that runs the scripted input test
    UINT harnessVk = 0;
    bool harness = true;        // install the player-update hook for the test harness
    // Passthrough: forward DirectInput8Create, install the harness and the
    // overlay, and change nothing else about the game.
    //
    // Every measurement in this project has been taken against "30 fps mode",
    // which is not the stock game: it is the patched DLL with its fixes
    // restored and its mode-byte writers still rewritten. If that restore is
    // incomplete in any way then the baseline itself is wrong and every delta
    // measured against it inherits the error. Passthrough is the control that
    // has been missing -- the real game, measured with the same instrument.
    bool passthrough = false;
    int harnessStick = -127;    // stick value the script's "forward" means
    char proxyDll[MAX_PATH] = "";
};

static Config g_cfg;
static char g_baseDir[MAX_PATH] = "";  // directory of this DLL, with trailing '\'
static HINSTANCE g_ourInstance = nullptr;

static UINT parseVk(const char* s) {
    char buf[32];
    size_t n = 0;
    for (const char* p = s; *p && n + 1 < sizeof(buf); p++) {
        if (!isspace((unsigned char)*p)) {
            buf[n++] = (char)toupper((unsigned char)*p);
        }
    }
    buf[n] = 0;
    if (n == 0 || !strcmp(buf, "NONE") || !strcmp(buf, "OFF") ||
        !strcmp(buf, "0")) {
        return 0;
    }
    if (n > 2 && buf[0] == '0' && buf[1] == 'X') {
        return (UINT)strtoul(buf + 2, nullptr, 16);
    }
    if (buf[0] == 'F' && n >= 2 && n <= 3 && isdigit((unsigned char)buf[1])) {
        int f = atoi(buf + 1);
        if (f >= 1 && f <= 24) {
            return VK_F1 + (UINT)(f - 1);
        }
    }
    if (!strncmp(buf, "NUMPAD", 6) && n == 7 && isdigit((unsigned char)buf[6])) {
        return VK_NUMPAD0 + (UINT)(buf[6] - '0');
    }
    if (n == 1 && isalnum((unsigned char)buf[0])) {
        return (UINT)buf[0];
    }
    struct {
        const char* name;
        UINT vk;
    } named[] = {
        {"HOME", VK_HOME},     {"END", VK_END},         {"INSERT", VK_INSERT},
        {"DELETE", VK_DELETE}, {"PAUSE", VK_PAUSE},     {"SCROLLLOCK", VK_SCROLL},
        {"SCROLL", VK_SCROLL}, {"PAGEUP", VK_PRIOR},    {"PAGEDOWN", VK_NEXT},
        {"TAB", VK_TAB},       {"BACKSPACE", VK_BACK},  {"SPACE", VK_SPACE},
        {"MULTIPLY", VK_MULTIPLY}, {"ADD", VK_ADD},      {"SUBTRACT", VK_SUBTRACT},
        {"DIVIDE", VK_DIVIDE}, {"DECIMAL", VK_DECIMAL},
    };
    for (auto& e : named) {
        if (!strcmp(buf, e.name)) {
            return e.vk;
        }
    }
    return VK_F9;
}

// The release defaults leave the development features off; Developer=1 (or a
// development-era okami.ini) restores them. Each still yields to its own key.
static void applyReleaseDefaults() {
    if (g_cfg.developer) {
        return;
    }
    g_cfg.statusInterval = 0;
    g_cfg.brushWatch = false;
    g_cfg.enemyWatch = false;
    g_cfg.harness = false;
    g_cfg.harnessVk = 0;
    snprintf(g_cfg.harnessName, sizeof(g_cfg.harnessName), "None");
    g_cfg.speedToggleVk = g_cfg.jumpToggleVk = g_cfg.timerToggleVk = 0;
    g_cfg.phaseToggleVk = g_cfg.integerToggleVk = g_cfg.fixToggleVk = 0;
    snprintf(g_cfg.speedToggleName, sizeof(g_cfg.speedToggleName), "None");
    snprintf(g_cfg.jumpToggleName, sizeof(g_cfg.jumpToggleName), "None");
    snprintf(g_cfg.timerToggleName, sizeof(g_cfg.timerToggleName), "None");
    snprintf(g_cfg.phaseToggleName, sizeof(g_cfg.phaseToggleName), "None");
    snprintf(g_cfg.integerToggleName, sizeof(g_cfg.integerToggleName), "None");
    snprintf(g_cfg.fixToggleName, sizeof(g_cfg.fixToggleName), "None");
}

static void loadConfig() {
    char ini[MAX_PATH];
    snprintf(ini, sizeof(ini), "%sokami_hackfix.ini", g_baseDir);
    if (GetFileAttributesA(ini) == INVALID_FILE_ATTRIBUTES) {
        char legacy[MAX_PATH];
        snprintf(legacy, sizeof(legacy), "%sokami.ini", g_baseDir);
        if (GetFileAttributesA(legacy) != INVALID_FILE_ATTRIBUTES) {
            snprintf(ini, sizeof(ini), "%s", legacy);
            g_cfg.iniLegacy = true;
        }
    }
    snprintf(g_cfg.iniPath, sizeof(g_cfg.iniPath), "%s", ini);
    const char* sec = "Main";
    if (GetFileAttributesA(ini) == INVALID_FILE_ATTRIBUTES) {
        logf("config: %s not found, using defaults", ini);
        applyReleaseDefaults();
        return;
    }
    g_cfg.iniFound = true;
    g_cfg.developer = GetPrivateProfileIntA(sec, "Developer", g_cfg.iniLegacy ? 1 : 0, ini) != 0;
    logf("config: %s%s, Developer=%d", ini, g_cfg.iniLegacy ? " (the development-era name)" : "",
         (int)g_cfg.developer);
    {
        int fps = GetPrivateProfileIntA(sec, "DefaultFps", 120, ini);
        g_cfg.defaultFps = fps == 30 ? 30 : fps == 60 ? 60 : 120;
    }
    GetPrivateProfileStringA(sec, "ToggleKey", "F9", g_cfg.toggleName,
                             sizeof(g_cfg.toggleName), ini);
    g_cfg.toggleVk = parseVk(g_cfg.toggleName);
    g_cfg.requireFocus = GetPrivateProfileIntA(sec, "RequireFocus", 1, ini) != 0;
    g_cfg.beep = GetPrivateProfileIntA(sec, "Beep", 1, ini) != 0;
    g_cfg.syncInterval = (UINT)GetPrivateProfileIntA(sec, "SyncInterval", 0, ini);
    if (g_cfg.syncInterval > 4) {
        g_cfg.syncInterval = 4;
    }
    g_cfg.statusInterval = GetPrivateProfileIntA(sec, "StatusInterval", g_cfg.developer ? 5 : 0, ini);
    if (g_cfg.statusInterval < 0) {
        g_cfg.statusInterval = 0;
    }
    g_cfg.fixes = GetPrivateProfileIntA(sec, "Fixes", 1, ini) != 0;
    GetPrivateProfileStringA(sec, "HalfRateTasks", "", g_cfg.halfRateTasks,
                             sizeof(g_cfg.halfRateTasks), ini);
    g_cfg.fixMenus = GetPrivateProfileIntA(sec, "FixMenus", 0, ini) != 0;
    g_cfg.fixHud = GetPrivateProfileIntA(sec, "FixHud", 0, ini) != 0;
    g_cfg.fixEffects = GetPrivateProfileIntA(sec, "FixEffects", 0, ini) != 0;
    GetPrivateProfileStringA(sec, "ExtraGates", "", g_cfg.extraGates,
                             sizeof(g_cfg.extraGates), ini);
    GetPrivateProfileStringA(sec, "Probes", "", g_cfg.probes, sizeof(g_cfg.probes), ini);
    GetPrivateProfileStringA(sec, "WatchBytes", "", g_cfg.watchBytes,
                             sizeof(g_cfg.watchBytes), ini);
    GetPrivateProfileStringA(sec, "GateSets", "", g_cfg.gateSets, sizeof(g_cfg.gateSets), ini);
    GetPrivateProfileStringA(sec, "GateSetNames", "", g_cfg.gateSetNames,
                             sizeof(g_cfg.gateSetNames), ini);
    g_cfg.overlay = GetPrivateProfileIntA(sec, "Overlay", 0, ini) != 0;
    g_cfg.speedLog = GetPrivateProfileIntA(sec, "SpeedLog", 0, ini) != 0;
    g_cfg.fixRunSpeed = GetPrivateProfileIntA(sec, "FixRunSpeed", 1, ini) != 0;
    g_cfg.fixAnimRate = GetPrivateProfileIntA(sec, "FixAnimRate", 1, ini) != 0;
    g_cfg.fixJumpHeight = GetPrivateProfileIntA(sec, "FixJumpHeight", 1, ini) != 0;
    g_cfg.jumpTrace = GetPrivateProfileIntA(sec, "JumpTrace", 0, ini) != 0;
    g_cfg.fixActionTimers = GetPrivateProfileIntA(sec, "FixActionTimers", 1, ini) != 0;
    g_cfg.fixPhaseSteps = GetPrivateProfileIntA(sec, "FixPhaseSteps", 1, ini) != 0;
    g_cfg.fixLaunchVelocity = GetPrivateProfileIntA(sec, "FixLaunchVelocity", 1, ini) != 0;
    g_cfg.fixDecay = GetPrivateProfileIntA(sec, "FixDecay", 1, ini) != 0;
    g_cfg.fps120 = GetPrivateProfileIntA(sec, "Fps120", 0, ini) != 0;
    g_cfg.fixInputWindows = GetPrivateProfileIntA(sec, "FixInputWindows", 1, ini) != 0;
    g_cfg.fixFrameGates = GetPrivateProfileIntA(sec, "FixFrameGates", 1, ini) != 0;
    g_cfg.fixFramePhases = GetPrivateProfileIntA(sec, "FixFramePhases", 1, ini) != 0;
    g_cfg.fixFrameClocks = GetPrivateProfileIntA(sec, "FixFrameClocks", 1, ini) != 0;
    g_cfg.fixIntegerSkips = GetPrivateProfileIntA(sec, "FixIntegerSkips", 0, ini) != 0;
    g_cfg.fixDayClock = GetPrivateProfileIntA(sec, "FixDayClock", 1, ini) != 0;
    g_cfg.brushWatch = GetPrivateProfileIntA(sec, "BrushWatch", g_cfg.developer ? 1 : 0, ini) != 0;
    g_cfg.enemyWatch = GetPrivateProfileIntA(sec, "EnemyWatch", g_cfg.developer ? 1 : 0, ini) != 0;
    g_cfg.fixMenuTransitions = GetPrivateProfileIntA(sec, "FixMenuTransitions", 1, ini) != 0;
    g_cfg.fixWorldAnims = GetPrivateProfileIntA(sec, "FixWorldAnims", 1, ini) != 0;
    g_cfg.fixSkyScroll = GetPrivateProfileIntA(sec, "FixSkyScroll", 1, ini) != 0;
    g_cfg.fixSwingPhysics = GetPrivateProfileIntA(sec, "FixSwingPhysics", 1, ini) != 0;
    g_cfg.fixHumanAnims = GetPrivateProfileIntA(sec, "FixHumanAnims", 1, ini) != 0;
    g_cfg.fixParticles = GetPrivateProfileIntA(sec, "FixParticles", 1, ini) != 0;
    g_cfg.fixEmitters = GetPrivateProfileIntA(sec, "FixEmitters", 1, ini) != 0;
    g_cfg.fixTurnLimits = GetPrivateProfileIntA(sec, "FixTurnLimits", 1, ini) != 0;
    g_cfg.fixScenerySway = GetPrivateProfileIntA(sec, "FixScenerySway", 1, ini) != 0;
    g_cfg.fixObjectAnims = GetPrivateProfileIntA(sec, "FixObjectAnims", 1, ini) != 0;
    g_cfg.fixModeQuantities = GetPrivateProfileIntA(sec, "FixModeQuantities", 1, ini) != 0;
    g_cfg.fixMenuRepeat = GetPrivateProfileIntA(sec, "FixMenuRepeat", 1, ini) != 0;
    g_cfg.fixEnemyClocks = GetPrivateProfileIntA(sec, "FixEnemyClocks", 1, ini) != 0;
    g_cfg.fixMenuScroll = GetPrivateProfileIntA(sec, "FixMenuScroll", 1, ini) != 0;
    g_cfg.fixTurnSteps = GetPrivateProfileIntA(sec, "FixTurnSteps", 1, ini) != 0;
    g_cfg.fixFlagQuantities = GetPrivateProfileIntA(sec, "FixFlagQuantities", 1, ini) != 0;
    g_cfg.fixSkipWindow = GetPrivateProfileIntA(sec, "FixSkipWindow", 1, ini) != 0;
    g_cfg.fixPlayerAnims = GetPrivateProfileIntA(sec, "FixPlayerAnims", 1, ini) != 0;
    g_cfg.fixTaskWaits = GetPrivateProfileIntA(sec, "FixTaskWaits", 1, ini) != 0;
    GetPrivateProfileStringA(sec, "IntegerToggleKey", g_cfg.developer ? "F4" : "None", g_cfg.integerToggleName,
                             sizeof(g_cfg.integerToggleName), ini);
    g_cfg.integerToggleVk = parseVk(g_cfg.integerToggleName);
    g_cfg.fixModeConstants = GetPrivateProfileIntA(sec, "FixModeConstants", 1, ini) != 0;
    g_cfg.fixModeMultipliers =
        GetPrivateProfileIntA(sec, "FixModeMultipliers", 1, ini) != 0;
    g_cfg.fixSlopeTerm = GetPrivateProfileIntA(sec, "FixSlopeTerm", 1, ini) != 0;
    g_cfg.fixAirAccel = GetPrivateProfileIntA(sec, "FixAirAccel", 1, ini) != 0;
    g_cfg.fixStickDrift = GetPrivateProfileIntA(sec, "FixStickDrift", 1, ini) != 0;
    g_cfg.drawDistance = (int)GetPrivateProfileIntA(sec, "DrawDistance", 1, ini);
    if (g_cfg.drawDistance < 1) {
        g_cfg.drawDistance = 1;
    } else if (g_cfg.drawDistance > 6) {
        g_cfg.drawDistance = 6;  // 5000 x 6 still fits the 16-bit compares
    }
    g_cfg.fixAirGates = GetPrivateProfileIntA(sec, "FixAirGates", 1, ini) != 0;
    g_cfg.fixHoistDecay = GetPrivateProfileIntA(sec, "FixHoistDecay", 1, ini) != 0;
    g_cfg.fixTurnRate = GetPrivateProfileIntA(sec, "FixTurnRate", 1, ini) != 0;
    GetPrivateProfileStringA(sec, "PhaseToggleKey", g_cfg.developer ? "F5" : "None", g_cfg.phaseToggleName,
                             sizeof(g_cfg.phaseToggleName), ini);
    g_cfg.phaseToggleVk = parseVk(g_cfg.phaseToggleName);
    if (!g_cfg.phaseToggleVk) {
        snprintf(g_cfg.phaseToggleName, sizeof(g_cfg.phaseToggleName), "None");
    }
    GetPrivateProfileStringA(sec, "TimerToggleKey", g_cfg.developer ? "F6" : "None", g_cfg.timerToggleName,
                             sizeof(g_cfg.timerToggleName), ini);
    g_cfg.timerToggleVk = parseVk(g_cfg.timerToggleName);
    if (!g_cfg.timerToggleVk) {
        snprintf(g_cfg.timerToggleName, sizeof(g_cfg.timerToggleName), "None");
    }
    GetPrivateProfileStringA(sec, "JumpToggleKey", g_cfg.developer ? "F7" : "None", g_cfg.jumpToggleName,
                             sizeof(g_cfg.jumpToggleName), ini);
    g_cfg.jumpToggleVk = parseVk(g_cfg.jumpToggleName);
    if (!g_cfg.jumpToggleVk) {
        snprintf(g_cfg.jumpToggleName, sizeof(g_cfg.jumpToggleName), "None");
    }
    GetPrivateProfileStringA(sec, "SpeedToggleKey", g_cfg.developer ? "F8" : "None", g_cfg.speedToggleName,
                             sizeof(g_cfg.speedToggleName), ini);
    g_cfg.speedToggleVk = parseVk(g_cfg.speedToggleName);
    if (!_stricmp(g_cfg.speedToggleName, "None")) {
        g_cfg.speedToggleVk = 0;
    }
    GetPrivateProfileStringA(sec, "SetKey", "None", g_cfg.setName, sizeof(g_cfg.setName), ini);
    g_cfg.setVk = parseVk(g_cfg.setName);
    if (!_stricmp(g_cfg.setName, "None")) {
        g_cfg.setVk = 0;
    }
    g_cfg.gateTrace = GetPrivateProfileIntA(sec, "GateTrace", 0, ini);
    if (g_cfg.gateTrace < 0) {
        g_cfg.gateTrace = 0;
    }
    GetPrivateProfileStringA(sec, "FixToggleKey", g_cfg.developer ? "F10" : "None", g_cfg.fixToggleName,
                             sizeof(g_cfg.fixToggleName), ini);
    g_cfg.fixToggleVk = parseVk(g_cfg.fixToggleName);
    GetPrivateProfileStringA(sec, "MarkKey", "None", g_cfg.markName,
                             sizeof(g_cfg.markName), ini);
    g_cfg.markVk = parseVk(g_cfg.markName);
    if (!_stricmp(g_cfg.markName, "None")) {
        g_cfg.markVk = 0;
    }
    // These live in [Harness], not [Main]. Reading them from the wrong section
    // is silent: every default here equals the value the ini documents, so the
    // keys appear to work and simply ignore anything you set them to.
    const char* hsec = "Harness";
    g_cfg.passthrough = GetPrivateProfileIntA(hsec, "Passthrough", 0, ini) != 0;
    g_cfg.harness = GetPrivateProfileIntA(hsec, "Harness", g_cfg.developer ? 1 : 0, ini) != 0;
    GetPrivateProfileStringA(hsec, "HarnessKey", g_cfg.developer ? "F3" : "None", g_cfg.harnessName,
                             sizeof(g_cfg.harnessName), ini);
    g_cfg.harnessVk = parseVk(g_cfg.harnessName);
    if (!_stricmp(g_cfg.harnessName, "None")) {
        g_cfg.harnessVk = 0;
    }
    g_cfg.harnessStick = GetPrivateProfileIntA(hsec, "HarnessStick", -127, ini);
    if (g_cfg.harnessStick > 127) {
        g_cfg.harnessStick = 127;
    }
    if (g_cfg.harnessStick < -127) {
        g_cfg.harnessStick = -127;
    }
    GetPrivateProfileStringA(sec, "ProxyDll", "", g_cfg.proxyDll,
                             sizeof(g_cfg.proxyDll), ini);
    logf("config: DefaultFps=%d ToggleKey=%s (vk 0x%02X) RequireFocus=%d Beep=%d "
         "SyncInterval=%u StatusInterval=%d Fixes=%d FixToggleKey=%s FixMenus=%d "
         "FixHud=%d FixEffects=%d ExtraGates=%s Probes=%s WatchBytes=%s GateTrace=%d "
         "HalfRateTasks=%s ProxyDll=%s",
         g_cfg.defaultFps, g_cfg.toggleName, g_cfg.toggleVk, (int)g_cfg.requireFocus,
         (int)g_cfg.beep, g_cfg.syncInterval, g_cfg.statusInterval,
         (int)g_cfg.fixes, g_cfg.fixToggleName, (int)g_cfg.fixMenus, (int)g_cfg.fixHud,
         (int)g_cfg.fixEffects, g_cfg.extraGates, g_cfg.probes, g_cfg.watchBytes,
         g_cfg.gateTrace, g_cfg.halfRateTasks,
         g_cfg.proxyDll[0] ? g_cfg.proxyDll : "(system)");
    // The line above predates the patch families and names none of them, so a
    // log could not say which fixes were even enabled -- and the ini in the game
    // folder is deliberately left alone on deploy, so it drifts from the one in
    // the repo. Record every key that selects a family.
    logf("fixes: Fps120=%d RunSpeed=%d AnimRate=%d JumpHeight=%d LaunchVelocity=%d"
         " ActionTimers=%d InputWindows=%d FrameGates=%d FramePhases=%d"
         " PhaseSteps=%d ModeConstants=%d ModeMultipliers=%d SlopeTerm=%d AirAccel=%d AirGates=%d",
         (int)g_cfg.fps120, (int)g_cfg.fixRunSpeed, (int)g_cfg.fixAnimRate,
         (int)g_cfg.fixJumpHeight, (int)g_cfg.fixLaunchVelocity,
         (int)g_cfg.fixActionTimers, (int)g_cfg.fixInputWindows,
         (int)g_cfg.fixFrameGates, (int)g_cfg.fixFramePhases,
         (int)g_cfg.fixPhaseSteps, (int)g_cfg.fixModeConstants,
         (int)g_cfg.fixModeMultipliers, (int)g_cfg.fixSlopeTerm,
         (int)g_cfg.fixAirAccel, (int)g_cfg.fixAirGates);
    logf("fixes: HoistDecay=%d TurnRate=%d FrameClocks=%d DayClock=%d BrushWatch=%d"
         " EnemyWatch=%d MenuTransitions=%d StickDrift=%d WorldAnims=%d (SkyScroll=%d SwingPhysics=%d"
         " HumanAnims=%d Particles=%d Emitters=%d TurnLimits=%d ScenerySway=%d"
         " ObjectAnims=%d ModeQuantities=%d MenuRepeat=%d EnemyClocks=%d MenuScroll=%d"
         " TurnSteps=%d FlagQuantities=%d SkipWindow=%d PlayerAnims=%d)"
         " TaskWaits=%d",
         (int)g_cfg.fixHoistDecay, (int)g_cfg.fixTurnRate, (int)g_cfg.fixFrameClocks,
         (int)g_cfg.fixDayClock, (int)g_cfg.brushWatch, (int)g_cfg.enemyWatch,
         (int)g_cfg.fixMenuTransitions,
         (int)g_cfg.fixStickDrift, (int)g_cfg.fixWorldAnims, (int)g_cfg.fixSkyScroll,
         (int)g_cfg.fixSwingPhysics, (int)g_cfg.fixHumanAnims, (int)g_cfg.fixParticles,
         (int)g_cfg.fixEmitters, (int)g_cfg.fixTurnLimits, (int)g_cfg.fixScenerySway,
         (int)g_cfg.fixObjectAnims, (int)g_cfg.fixModeQuantities, (int)g_cfg.fixMenuRepeat,
         (int)g_cfg.fixEnemyClocks, (int)g_cfg.fixMenuScroll, (int)g_cfg.fixTurnSteps,
         (int)g_cfg.fixFlagQuantities, (int)g_cfg.fixSkipWindow, (int)g_cfg.fixPlayerAnims,
         (int)g_cfg.fixTaskWaits);
    // echoed because they come from a different ini section, and a key read
    // from the wrong section fails silently by falling back to its default
    logf("harness config: Passthrough=%d Harness=%d HarnessKey=%s (vk 0x%X) HarnessStick=%d",
         (int)g_cfg.passthrough, (int)g_cfg.harness, g_cfg.harnessName, g_cfg.harnessVk,
         g_cfg.harnessStick);
    if (g_cfg.passthrough) {
        logf("harness config: PASSTHROUGH IS ON -- this run installs no patches and is the"
             " unpatched control, not a 30 fps measurement");
    }
}

// ---------------------------------------------------------------------------
// Engine symbol resolution + verification
// ---------------------------------------------------------------------------

typedef void(__fastcall* SetPs2DispFn)(uint8_t);
typedef uint8_t(__fastcall* IsPs2DispFn)();
typedef void* (*GetSingletonFn)();
typedef void(__fastcall* SetFloatFn)(void*, float);
typedef float(__fastcall* GetFloatFn)(void*);

struct Engine {
    uint8_t* main = nullptr;
    uint8_t* fk = nullptr;
    // main.dll frame configuration written by flower_tick every frame
    uint8_t* modeByte = nullptr;      // 1 -> fps=60/timeScale=0.5, 2 -> 30/1.0
    uint8_t* fpsByte = nullptr;       // 30 / 60 (status only)
    float* timeScale = nullptr;       // 1.0 / 0.5 (status only)
    uint32_t* frameCounter = nullptr; // per-tick counter (status only)
    // `mov byte ptr [modeByte], 2` sites in main.dll .text (imm8 at +6)
    uint8_t* writerSites[16] = {};
    int writerCount = 0;
    // engine functions
    SetPs2DispFn setPs2Disp = nullptr;
    IsPs2DispFn isPs2Disp = nullptr;
    GetSingletonFn getSysCfg = nullptr;
    SetFloatFn setRefleshRate = nullptr;
    GetFloatFn getRefleshRate = nullptr;
    // flower_kernel global holding the IDXGISwapChain* the engine presents on
    IDXGISwapChain** swapChainSlot = nullptr;
    // main.dll global holding the player object (class pl00), resolved from
    // the store in pl00's setup method; status/diagnostics only
    uint8_t** playerSlot = nullptr;
    void* playerVtable = nullptr;
    // cTaskManager::step(entry): wakes one task thread for one frame. Each
    // 0x70-byte entry holds the task object at +0x18 (its vtable slot 1 is
    // the task body). Detoured to classify and optionally half-rate tasks.
    uint8_t* taskStep = nullptr;
};

static Engine g_eng;
static uint8_t* g_main = nullptr;  // kept for the trace build
static uint8_t* g_fk = nullptr;

static bool inImage(uint8_t* mod, const void* p) {
    auto dos = (IMAGE_DOS_HEADER*)mod;
    auto nt = (IMAGE_NT_HEADERS*)(mod + dos->e_lfanew);
    return (uint8_t*)p >= mod && (uint8_t*)p < mod + nt->OptionalHeader.SizeOfImage;
}

static bool textSection(uint8_t* mod, uint8_t** beg, uint8_t** end) {
    auto dos = (IMAGE_DOS_HEADER*)mod;
    auto nt = (IMAGE_NT_HEADERS*)(mod + dos->e_lfanew);
    auto sec = IMAGE_FIRST_SECTION(nt);
    for (int i = 0; i < nt->FileHeader.NumberOfSections; i++) {
        if (!memcmp(sec[i].Name, ".text", 6)) {
            *beg = mod + sec[i].VirtualAddress;
            *end = *beg + sec[i].Misc.VirtualSize;
            return true;
        }
    }
    return false;
}

static uint32_t peTimestamp(uint8_t* mod) {
    auto dos = (IMAGE_DOS_HEADER*)mod;
    auto nt = (IMAGE_NT_HEADERS*)(mod + dos->e_lfanew);
    return nt->FileHeader.TimeDateStamp;
}

// rip-relative target of an instruction whose disp32 sits at insn+dispOff
// and whose total length is len
static uint8_t* ripTarget(const uint8_t* insn, int dispOff, int len) {
    int32_t disp;
    memcpy(&disp, insn + dispOff, 4);
    return (uint8_t*)insn + len + disp;
}

// Locate the frame configuration variables from flower_tick's own code:
//   C7 05 d32 00 00 80 3F   mov dword [timeScale], 1.0f
//   C6 05 d32 1E            mov byte  [fps], 30
//   80 3D d32 01            cmp byte  [mode], 1
//   FF 05 d32               inc dword [frameCounter]
static bool resolveFrameConfig(uint8_t* tick) {
    const size_t window = 0x300;
    for (size_t i = 0; i + 7 <= window; i++) {
        const uint8_t* p = tick + i;
        if (p[0] == 0x80 && p[1] == 0x3D && p[6] == 0x01 && !g_eng.modeByte) {
            uint8_t* t = ripTarget(p, 2, 7);
            if (inImage(g_eng.main, t)) {
                g_eng.modeByte = t;
            }
        } else if (p[0] == 0xC6 && p[1] == 0x05 && p[6] == 0x1E && !g_eng.fpsByte) {
            uint8_t* t = ripTarget(p, 2, 7);
            if (inImage(g_eng.main, t)) {
                g_eng.fpsByte = t;
            }
        } else if (p[0] == 0xC7 && p[1] == 0x05 && i + 10 <= window && p[6] == 0x00 &&
                   p[7] == 0x00 && p[8] == 0x80 && p[9] == 0x3F && !g_eng.timeScale) {
            uint8_t* t = ripTarget(p, 2, 10);
            if (inImage(g_eng.main, t)) {
                g_eng.timeScale = (float*)t;
            }
        } else if (p[0] == 0xFF && p[1] == 0x05 && !g_eng.frameCounter) {
            uint8_t* t = ripTarget(p, 2, 6);
            if (inImage(g_eng.main, t)) {
                g_eng.frameCounter = (uint32_t*)t;
            }
        }
    }
    if (!g_eng.modeByte || !g_eng.fpsByte) {
        return false;
    }
    // the two bytes are adjacent in the retail build; anything else means the
    // pattern matched something unexpected
    if (g_eng.fpsByte + 1 != g_eng.modeByte) {
        logf("verify: fps byte %p / mode byte %p are not adjacent",
             (void*)g_eng.fpsByte, (void*)g_eng.modeByte);
        return false;
    }
    return true;
}

// Find every `C6 05 d32 02` (mov byte ptr [rip+d32], 2) in main.dll .text
// whose target is the mode byte.
static int resolveWriterSites() {
    uint8_t *beg, *end;
    if (!textSection(g_eng.main, &beg, &end)) {
        return 0;
    }
    g_eng.writerCount = 0;
    for (uint8_t* p = beg; p + 7 <= end; p++) {
        if (p[0] == 0xC6 && p[1] == 0x05 && p[6] == 0x02 &&
            ripTarget(p, 2, 7) == g_eng.modeByte) {
            if (g_eng.writerCount < (int)(sizeof(g_eng.writerSites) /
                                          sizeof(g_eng.writerSites[0]))) {
                g_eng.writerSites[g_eng.writerCount++] = p;
            }
        }
    }
    return g_eng.writerCount;
}

// SwapChain::swap(unsigned) in flower_kernel loads the engine's swap chain
// pointer from a global right before calling Present:
//   48 8B 0D d32   mov rcx, [rip+d32]     <- the global
//   45 33 C0       xor r8d, r8d
static bool resolveSwapChainSlot() {
    auto swap = (uint8_t*)GetProcAddress((HMODULE)g_eng.fk,
                                         "?swap@SwapChain@render@m2@@QEAAXI@Z");
    if (!swap) {
        return false;
    }
    if (swap[0] == 0xE9) {  // export stub: jmp rel32 -> real body
        swap = ripTarget(swap, 1, 5);
    }
    for (int i = 0; i + 10 <= 0x100; i++) {
        const uint8_t* p = swap + i;
        if (p[0] == 0x48 && p[1] == 0x8B && p[2] == 0x0D && p[7] == 0x45 &&
            p[8] == 0x33 && p[9] == 0xC0) {
            uint8_t* t = ripTarget(p, 3, 7);
            if (inImage(g_eng.fk, t)) {
                g_eng.swapChainSlot = (IDXGISwapChain**)t;
                return true;
            }
        }
    }
    return false;
}

static bool resolveEngine() {
    HMODULE mm = GetModuleHandleA("main.dll");
    HMODULE fm = GetModuleHandleA("flower_kernel.dll");
    if (!mm || !fm) {
        return false;
    }
    g_eng.main = g_main = (uint8_t*)mm;
    g_eng.fk = g_fk = (uint8_t*)fm;
    logf("main.dll=%p (timestamp %08X) flower_kernel.dll=%p (timestamp %08X)",
         (void*)g_eng.main, peTimestamp(g_eng.main), (void*)g_eng.fk,
         peTimestamp(g_eng.fk));

    bool ok = true;
    auto tick = (uint8_t*)GetProcAddress(mm, "?flower_tick@@YA_NXZ");
    if (!tick) {
        logf("verify: flower_tick export missing");
        ok = false;
    } else if (!resolveFrameConfig(tick)) {
        logf("verify: frame configuration not found in flower_tick");
        ok = false;
    } else {
        logf("resolved: mode byte main+%llX fps byte main+%llX timeScale main+%llX "
             "counter main+%llX",
             (unsigned long long)(g_eng.modeByte - g_eng.main),
             (unsigned long long)(g_eng.fpsByte - g_eng.main),
             (unsigned long long)(g_eng.timeScale ? (uint8_t*)g_eng.timeScale - g_eng.main : 0),
             (unsigned long long)(g_eng.frameCounter ? (uint8_t*)g_eng.frameCounter - g_eng.main : 0));
        int n = resolveWriterSites();
        if (n == 0) {
            logf("verify: no `mov byte [mode], 2` sites found");
            ok = false;
        } else {
            logf("resolved: %d mode writer site(s)", n);
            for (int i = 0; i < n; i++) {
                logf("  writer main+%llX",
                     (unsigned long long)(g_eng.writerSites[i] - g_eng.main));
            }
        }
    }

    g_eng.setPs2Disp = (SetPs2DispFn)GetProcAddress(fm, "?SetPs2DispMode@m2@@YAX_N@Z");
    g_eng.isPs2Disp = (IsPs2DispFn)GetProcAddress(fm, "?IsPs2DispMode@m2@@YA_NXZ");
    if (!g_eng.setPs2Disp || !g_eng.isPs2Disp) {
        logf("verify: Set/IsPs2DispMode exports missing");
        ok = false;
    }
    g_eng.getSysCfg = (GetSingletonFn)GetProcAddress(
        mm, "?getSingletonInstance@?$SingletonObject@VSystemConfig@m2@@@hx@@SAPEAVSystemConfig@m2@@XZ");
    g_eng.setRefleshRate =
        (SetFloatFn)GetProcAddress(mm, "?SetRefleshRate@SystemConfig@m2@@QEAAXM@Z");
    g_eng.getRefleshRate =
        (GetFloatFn)GetProcAddress(mm, "?GetRefleshRate@SystemConfig@m2@@QEBAMXZ");
    if (!g_eng.getSysCfg || !g_eng.setRefleshRate) {
        logf("verify: SystemConfig exports missing (refresh rate config will be skipped)");
    }
    // player object global: pl00's setup method (vtable slot 6) stores `this`
    // with `48 89 2D d32` (mov [rip+d32], rbp) right after loading the state
    // callback table. Build 6990973: setup at main+0x3A8EA0, vtable main+0x68B280.
    {
        uint8_t* setup = g_eng.main + 0x3A8EA0;
        for (int i = 0; i < 0x80; i++) {
            if (setup[i] == 0x48 && setup[i + 1] == 0x89 && setup[i + 2] == 0x2D) {
                uint8_t* t = ripTarget(setup + i, 3, 7);
                if (inImage(g_eng.main, t)) {
                    g_eng.playerSlot = (uint8_t**)t;
                    g_eng.playerVtable = g_eng.main + 0x68B280;
                    logf("resolved: player slot main+%llX",
                         (unsigned long long)(t - g_eng.main));
                }
                break;
            }
        }
    }
    // task step (build 6990973: main+0x456600), verified by prologue
    {
        static const uint8_t pro[15] = {0x40, 0x53, 0x48, 0x83, 0xEC, 0x20, 0x0F, 0xB7,
                                        0x51, 0x10, 0x48, 0x8B, 0xD9, 0x8B, 0xCA};
        uint8_t* f = g_eng.main + 0x456600;
        if (!memcmp(f, pro, 15)) {
            g_eng.taskStep = f;
        } else {
            logf("verify: task step prologue mismatch (task gating unavailable)");
        }
    }
    if (!resolveSwapChainSlot()) {
        logf("verify: swap chain global not found in SwapChain::swap");
        ok = false;
    } else {
        logf("resolved: swap chain slot flower_kernel+%llX",
             (unsigned long long)((uint8_t*)g_eng.swapChainSlot - g_eng.fk));
    }
    return ok;
}

// ---------------------------------------------------------------------------
// Frame pacing
// ---------------------------------------------------------------------------

static HANDLE g_timer = nullptr;
static bool g_timerHighRes = false;
static bool g_timePeriodSet = false;

static void initTiming() {
    g_timer = CreateWaitableTimerExW(nullptr, nullptr,
                                     CREATE_WAITABLE_TIMER_HIGH_RESOLUTION,
                                     TIMER_ALL_ACCESS);
    g_timerHighRes = g_timer != nullptr;
    if (!g_timer) {
        g_timer = CreateWaitableTimerExW(nullptr, nullptr, 0, TIMER_ALL_ACCESS);
    }
    // 1 ms scheduler granularity as a fallback for the non-high-res path
    g_timePeriodSet = timeBeginPeriod(1) == TIMERR_NOERROR;
    logf("timing: qpc %lld Hz, waitable timer %s, timeBeginPeriod(1) %s",
         (long long)g_qpcFreq,
         g_timer ? (g_timerHighRes ? "high-resolution" : "standard") : "unavailable",
         g_timePeriodSet ? "ok" : "failed");
}

// Sleep until the QPC timestamp `target`, spinning only for the last ~0.5 ms.
static void waitUntil(LONGLONG target) {
    const LONGLONG reserve = g_qpcFreq / 2000;  // 0.5 ms
    LONGLONG remain = target - qpc();
    if (remain > reserve) {
        LONGLONG sleepTicks = remain - reserve;
        if (g_timer) {
            LARGE_INTEGER due;
            due.QuadPart = -(sleepTicks * 10000000LL / g_qpcFreq);  // 100 ns, relative
            if (SetWaitableTimerEx(g_timer, &due, 0, nullptr, nullptr, nullptr, 0)) {
                WaitForSingleObject(g_timer, 100);
            }
        } else {
            Sleep((DWORD)(sleepTicks * 1000 / g_qpcFreq));
        }
    }
    while (qpc() < target) {
        YieldProcessor();
    }
}

// Fixed step grid anchored at an epoch, so rounding never accumulates. The
// grid re-anchors after a stall longer than one frame (loading screens,
// alt-tab) instead of trying to catch up. The rate follows the engine config
// the patch asked for: 60 Hz normally, 120 in the experimental mode.
static LONGLONG g_gridEpoch = 0;
static LONGLONG g_gridIndex = 0;
static volatile LONG g_targetHz = 60;

static void paceFrame() {
    LONGLONG hz = g_targetHz > 0 ? g_targetHz : 60;
    const LONGLONG step = g_qpcFreq / hz;
    LONGLONG now = qpc();
    LONGLONG prevTarget = g_gridEpoch + (g_gridIndex * g_qpcFreq) / hz;
    if (g_gridEpoch == 0 || now - prevTarget > step) {
        g_gridEpoch = now;
        g_gridIndex = 0;
    }
    g_gridIndex++;
    waitUntil(g_gridEpoch + (g_gridIndex * g_qpcFreq) / hz);
}

// ---------------------------------------------------------------------------
// Present shim + swap chain vtable patch
// ---------------------------------------------------------------------------

typedef HRESULT(STDMETHODCALLTYPE* PresentFn)(IDXGISwapChain*, UINT, UINT);

// Every vtable we have patched, with the Present it originally held. The
// engine's swap chain pointer can change class over its lifetime (the game
// recreates it, and overlays such as ReShade or frame limiters wrap it in
// proxies), so the shim looks up the original by the calling object's vtable
// instead of trusting a single saved pointer.
struct PresentHook {
    void** slot;      // &vtable[8]
    PresentFn orig;   // what the slot held before we patched it
};
static PresentHook g_hooks[8];
static int g_hookCount = 0;
static volatile LONG g_presentPatched = 0;  // 1 while the live vtable is ours
static volatile LONG g_presentCount = 0;
static volatile LONG g_lastGameSync = -1;

static const char* moduleNameOf(const void* addr, char* buf, size_t n) {
    HMODULE m = nullptr;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                               GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)addr, &m) &&
        m) {
        char path[MAX_PATH];
        if (GetModuleFileNameA(m, path, MAX_PATH)) {
            const char* s = strrchr(path, '\\');
            snprintf(buf, n, "%s+%llX", s ? s + 1 : path,
                     (unsigned long long)((const uint8_t*)addr - (const uint8_t*)m));
            return buf;
        }
    }
    snprintf(buf, n, "%p", addr);
    return buf;
}

static PresentFn origPresentFor(IDXGISwapChain* sc) {
    void** vt = *(void***)sc;
    for (int i = 0; i < g_hookCount; i++) {
        if (g_hooks[i].slot == &vt[8]) {
            return g_hooks[i].orig;
        }
    }
    return nullptr;
}

static void logSwapChainInfo(IDXGISwapChain* sc) {
    DXGI_SWAP_CHAIN_DESC d;
    if (SUCCEEDED(sc->GetDesc(&d))) {
        logf("swapchain: %ux%u refresh=%u/%u windowed=%d swapeffect=%d buffers=%u "
             "flags=0x%X format=%d",
             d.BufferDesc.Width, d.BufferDesc.Height, d.BufferDesc.RefreshRate.Numerator,
             d.BufferDesc.RefreshRate.Denominator, (int)d.Windowed, (int)d.SwapEffect,
             d.BufferCount, d.Flags, (int)d.BufferDesc.Format);
    }
    BOOL fs = FALSE;
    IDXGIOutput* out = nullptr;
    if (SUCCEEDED(sc->GetFullscreenState(&fs, &out))) {
        char name[64] = "?";
        if (out) {
            DXGI_OUTPUT_DESC od;
            if (SUCCEEDED(out->GetDesc(&od))) {
                WideCharToMultiByte(CP_UTF8, 0, od.DeviceName, -1, name, sizeof(name),
                                    nullptr, nullptr);
            }
            out->Release();
        }
        logf("swapchain: fullscreen=%d output=%s", (int)fs, name);
    }
}

// Overlays and drivers (ReShade, NVIDIA's NvPresent64 layer, ...) wrap the
// swap chain in proxies that forward Present to the next layer. If more than
// one of those vtables ends up patched, the shim is re-entered on the same
// thread for a single game frame; only the outermost call may pace and count.
static thread_local int t_presentDepth = 0;

static HRESULT STDMETHODCALLTYPE presentShim(IDXGISwapChain* sc, UINT sync, UINT flags) {
    PresentFn orig = origPresentFor(sc);
    if (t_presentDepth > 0) {
        // nested layer: forward untouched, the outer call already handled it
        return orig ? orig(sc, sync, flags) : DXGI_ERROR_INVALID_CALL;
    }
    if ((LONG)sync != g_lastGameSync) {
        g_lastGameSync = (LONG)sync;
        logf("present: game requested sync interval %u (using %u)", sync, g_cfg.syncInterval);
    }
    static bool infoLogged = false;
    if (!infoLogged) {
        infoLogged = true;
        logSwapChainInfo(sc);
    }
    if (!orig) {
        // an object whose vtable we never patched reached the shim: only
        // possible if the vtable was copied elsewhere; there is no safe
        // original to call, so fail the present instead of jumping blindly
        static bool warned = false;
        if (!warned) {
            warned = true;
            logf("warn: present on unknown vtable %p", (void*)*(void***)sc);
        }
        return DXGI_ERROR_INVALID_CALL;
    }
    // present with the configured interval (0 = no vblank wait): the stock
    // synchronous present is what paces the game at 30 steps/s
    t_presentDepth++;
    HRESULT hr = orig(sc, g_cfg.syncInterval, flags);
    t_presentDepth--;
    InterlockedIncrement(&g_presentCount);
    // the UI oscillators read a halved copy of the engine's frame counter
    updateSlowFrame();
    // enforce the 60 Hz game-step clock on the frame thread
    paceFrame();
    return hr;
}

static void** presentSlot() {
    if (!g_eng.swapChainSlot) {
        return nullptr;
    }
    IDXGISwapChain* sc = *g_eng.swapChainSlot;
    if (!sc) {
        return nullptr;
    }
    void** vt = *(void***)sc;
    return vt ? &vt[8] : nullptr;
}

// Patch the Present slot of the DXGI swap chain vtable. All swap chains of
// the same class share the vtable, so resolution changes / swap chain
// recreates keep the patch active.
static void installPresentHook() {
    void** slot = presentSlot();
    if (!slot) {
        return;  // swap chain not created yet; caller retries
    }
    PresentFn cur = (PresentFn)*slot;
    if (!cur) {
        return;
    }
    if (cur == &presentShim) {
        InterlockedExchange(&g_presentPatched, 1);
        return;
    }
    // a vtable we patched before and later restored (30 fps mode): re-arm it
    for (int i = 0; i < g_hookCount; i++) {
        if (g_hooks[i].slot == slot) {
            InterlockedExchangePointer(slot, (void*)&presentShim);
            InterlockedExchange(&g_presentPatched, 1);
            g_gridEpoch = 0;
            return;
        }
    }
    if (g_hookCount >= (int)(sizeof(g_hooks) / sizeof(g_hooks[0]))) {
        logf("warn: too many distinct swap chain vtables; not hooking %p", (void*)slot);
        return;
    }
    DWORD old;
    if (!VirtualProtect(slot, sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
        logf("warn: present vtable VirtualProtect failed err=%lu",
             (unsigned long)GetLastError());
        return;
    }
    g_hooks[g_hookCount].slot = slot;
    g_hooks[g_hookCount].orig = cur;
    g_hookCount++;  // publish the entry before the slot starts routing here
    InterlockedExchangePointer(slot, (void*)&presentShim);
    InterlockedExchange(&g_presentPatched, 1);
    g_gridEpoch = 0;
    char a[96], b[96];
    logf("present hooked: vtable %s orig %s", moduleNameOf(slot, a, sizeof(a)),
         moduleNameOf((void*)cur, b, sizeof(b)));
}

// Restore every vtable we patched (30 fps mode).
static void removePresentHook() {
    for (int i = 0; i < g_hookCount; i++) {
        void** slot = g_hooks[i].slot;
        if (*slot == (void*)&presentShim) {
            DWORD old;
            if (VirtualProtect(slot, sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
                InterlockedExchangePointer(slot, (void*)g_hooks[i].orig);
            }
        }
    }
    InterlockedExchange(&g_presentPatched, 0);
}

// Keep the hook alive across swap chain recreation.
static void checkPresentHookAlive() {
    if (!g_presentPatched) {
        return;
    }
    void** slot = presentSlot();
    if (slot && *slot != (void*)&presentShim) {
        InterlockedExchange(&g_presentPatched, 0);
        logf("swap chain vtable changed; re-hooking");
        installPresentHook();
    }
}

// ---------------------------------------------------------------------------
// Crash diagnostics: log the first few hard exceptions (module+offset) so
// user reports can tell a patch fault from a game/overlay fault.
// ---------------------------------------------------------------------------

static volatile LONG g_exceptionsLogged = 0;

static LONG CALLBACK exceptionLogger(EXCEPTION_POINTERS* ep) {
    DWORD code = ep->ExceptionRecord->ExceptionCode;
    if (code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_ILLEGAL_INSTRUCTION ||
        code == EXCEPTION_STACK_OVERFLOW || code == EXCEPTION_PRIV_INSTRUCTION ||
        code == EXCEPTION_IN_PAGE_ERROR) {
        if (InterlockedIncrement(&g_exceptionsLogged) <= 3) {
            char a[96];
            const void* addr = ep->ExceptionRecord->ExceptionAddress;
            logf("EXCEPTION 0x%08lX at %s (thread %lu)%s", (unsigned long)code,
                 moduleNameOf(addr, a, sizeof(a)), (unsigned long)GetCurrentThreadId(),
                 code == EXCEPTION_ACCESS_VIOLATION
                     ? (ep->ExceptionRecord->ExceptionInformation[0] ? " [write]" : " [read]")
                     : "");
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

// ---------------------------------------------------------------------------
// Engine-side fixes
// ---------------------------------------------------------------------------

// The engine pairs its frame-window compensation with the framerate mode
// byte: <=1 keeps the 60 Hz semantics of every compensated timer at 60
// ticks/s (key timers decay 1/tick, keyframe durations double, movement
// speeds switch). The game's own system-state machine rewrites it to 2 (30 Hz
// semantics) throughout gameplay, which at our 60 Hz tick rate would make
// every frame-counted window run twice as fast in real time. Rewriting the
// `mov byte ptr [mode], 2` immediates makes the game's own writers emit 1.
static void setWriterImm(uint8_t imm) {
    for (int i = 0; i < g_eng.writerCount; i++) {
        uint8_t* p = g_eng.writerSites[i] + 6;  // C6 05 disp32 imm8 -> imm8
        DWORD old;
        if (!VirtualProtect(p, 1, PAGE_EXECUTE_READWRITE, &old)) {
            logf("warn: mode writer VirtualProtect failed at %p", (void*)p);
            continue;
        }
        *p = imm;
    }
}

static void setConfigRefleshRate(float rate) {
    if (!g_eng.getSysCfg || !g_eng.setRefleshRate) {
        return;
    }
    void* sysCfg = g_eng.getSysCfg();
    if (sysCfg) {
        float before = g_eng.getRefleshRate ? g_eng.getRefleshRate(sysCfg) : -1.0f;
        g_eng.setRefleshRate(sysCfg, rate);
        logf("config refresh rate %.0f -> %.0f", (double)before, (double)rate);
    }
}

// ---------------------------------------------------------------------------
// Per-frame tracing (OKAMI_TRACE builds only; gcc/clang, build 6990973 RVAs)
// ---------------------------------------------------------------------------

#ifdef OKAMI_TRACE
#if !defined(__GNUC__) && !defined(__clang__)
#error "OKAMI_TRACE needs gcc or clang (GNU inline asm + naked functions)"
#endif
static constexpr uintptr_t kTickRva = 0x4B63B0;       // flower_tick
static constexpr uintptr_t kKeyTableRva = 0x0B6AD00;  // cKs key object
static constexpr uintptr_t kFrameCounterRva2 = 0x0B6AC20;
static constexpr uintptr_t kFpsByteRva2 = 0x0B6AC44;
static constexpr uintptr_t kModeByteRva2 = 0x0B6AC45;
static constexpr uintptr_t kTimeScaleRva2 = 0x0B6AC38;
static constexpr size_t kKeyDump = 0x1D0;

extern "C" {
__attribute__((used)) uint8_t* g_tickTramp = nullptr;
__attribute__((used)) uint8_t* g_moveTramp = nullptr;
__attribute__((used)) uint8_t* g_chan3Tramp = nullptr;
__attribute__((used)) uint8_t* g_chan4Tramp = nullptr;
__attribute__((used)) uint8_t* g_bstTramp = nullptr;
__attribute__((used)) uint8_t* g_motTramp = nullptr;
__attribute__((used)) uint8_t* g_gcbTramp = nullptr;
}
static uint8_t g_tickSaved[15];  // push7(2+1+1+1+2+2+2)+sub(4)=15, next at 0x4b63bf
static volatile LONG g_tickHookOk = 0;
static uint32_t g_lastKeySum = 0;
static uint32_t g_dumpCounter = 0;

static volatile uint32_t g_keyActiveUntilTick = 0;
static volatile uint32_t g_lastTickFC = 0;

// called on the main thread inside flower_tick
extern "C" void traceOnTick() {
#ifdef OKAMI_TRACE_BARE
    static volatile LONG n = 0;
    InterlockedIncrement(&n);
    return;
#else
    uint32_t fc =
        *(volatile uint32_t*)(g_main + kFrameCounterRva2);
    const uint8_t* keys = (const uint8_t*)(g_main + kKeyTableRva);

    // dump when any key activity is present, otherwise every 30 ticks
    uint32_t sum = 0;
    for (size_t i = 0; i < 0x40; i++) {
        sum += keys[i];
    }
    g_lastTickFC = fc;
    if (sum != 0) {
        g_keyActiveUntilTick = fc + 60;  // keep channel logging during presses
    }
    g_dumpCounter++;
    bool active = (g_lastKeySum == 0 && sum != 0) || sum != 0;
    if (!active && (g_dumpCounter % 30) != 0) {
        g_lastKeySum = sum;
        return;
    }
    g_lastKeySum = sum;
    g_dumpCounter = 0;
    (void)keys;
    // the game-system object IS at main+0x5CF230 (the callback's argument)
    uint8_t* sys = g_main + 0x5CF230;
    {
        float px = *(float*)(sys + 0xa8), py = *(float*)(sys + 0xac),
              pz = *(float*)(sys + 0xb0);
        uint32_t st = *(uint32_t*)(sys + 0xe30);
        float t0 = *(float*)(sys + 0x5490);
        logf("G2 t=%u st=%08x pos=(%8.1f %8.1f %8.1f) tm=%.2f", fc, st,
             (double)px, (double)py, (double)pz, (double)t0);
    }
#endif  // OKAMI_TRACE_BARE
}

// movement update hook: capture velocities/flags/anim frame counters
static constexpr uintptr_t kMoveUpdateRva = 0x19E040;
static uint8_t g_moveSaved[15];  // push rdi(2)+sub(7)+mov rax,[rcx](3)+mov rdi,rcx(3)
static uint32_t g_moveLastSig = 0;

extern "C" void traceMove(void* obj) {
    uint8_t* p = (uint8_t*)obj;
    float vx = *(float*)(p + 0x160), vy = *(float*)(p + 0x164),
          vz = *(float*)(p + 0x168);
    uint8_t f1 = p[0x18d], f2 = p[0x18e];
    uint16_t a1 = *(uint16_t*)(p + 0x1b0), a2 = *(uint16_t*)(p + 0x214),
             a3 = *(uint16_t*)(p + 0x278);
    float s1 = *(float*)(p + 0x2d4), s2 = *(float*)(p + 0x2d8);
    uint32_t sig = (uint32_t)((uint64_t)obj >> 4) ^ (uint32_t)(vx * 10) ^
                   (uint32_t)(vy * 10) ^ ((uint32_t)a3 << 16) ^ ((uint32_t)a1 << 8);
    // log on change, or every 90 ticks as baseline
    static uint32_t ctr = 0;
    ctr++;
    if (sig == g_moveLastSig && (ctr % 90) != 0) {
        return;
    }
    g_moveLastSig = sig;
    logf("M %p v=(%6.1f %6.1f %6.1f) f=%02x%02x a=[%u %u %u] s=(%.2f %.2f)",
         obj, (double)vx, (double)vy, (double)vz, f1, f2, a1, a2, a3,
         (double)s1, (double)s2);
}

static __attribute__((naked)) void moveHookNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"
        "movq 0x60(%rsp), %rcx\n\t"  // original rcx (this) from the saved stack
        "call traceMove\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_moveTramp(%rip)\n\t");
}

static void installMoveTrace() {
    uint8_t* target = g_main + kMoveUpdateRva;
    memcpy(g_moveSaved, target, sizeof(g_moveSaved));
    g_moveTramp = (uint8_t*)VirtualAlloc(nullptr, sizeof(g_moveSaved) + 16,
                                         MEM_COMMIT | MEM_RESERVE,
                                         PAGE_EXECUTE_READWRITE);
    if (!g_moveTramp) {
        logf("trace: move trampoline alloc failed");
        return;
    }
    memcpy(g_moveTramp, target, sizeof(g_moveSaved));
    uint8_t* back = g_moveTramp + sizeof(g_moveSaved);
    back[0] = 0x48;
    back[1] = 0xB8;
    uint64_t retAddr = (uint64_t)(target + sizeof(g_moveSaved));
    memcpy(back + 2, &retAddr, 8);
    back[10] = 0xFF;
    back[11] = 0xE0;

    uint8_t patch[15];
    patch[0] = 0xFF;
    patch[1] = 0x25;
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)&moveHookNaked;
    memcpy(patch + 6, &hookAddr, 8);
    patch[14] = 0x90;
    DWORD old;
    if (!VirtualProtect(target, sizeof(patch), PAGE_EXECUTE_READWRITE, &old)) {
        logf("trace: move VirtualProtect failed");
        return;
    }
    memcpy(target, patch, sizeof(patch));
    logf("trace: move update hooked at %p", (void*)target);
}


// 3D anim channel advance hooks (0x1b26e0, 0x1b2840): rdx = channel object
static uint8_t g_chan3Saved[15];
static uint8_t g_chan4Saved[15];

extern "C" void traceChan3D(uint8_t* chan) {
    static uint32_t ctr = 0;
    ctr++;
    uint32_t act = g_keyActiveUntilTick;
    uint32_t ft = g_lastTickFC;
    if ((ft >= act) && (ctr % 6000) != 0) {
        return;
    }
    float px = *(float*)(chan + 0x20), py = *(float*)(chan + 0x24);
    uint16_t f1 = *(uint16_t*)(chan + 0x88), f2 = *(uint16_t*)(chan + 0x8c);
    uint32_t flags = *(uint32_t*)(chan + 0xa8);
    uint8_t* mot = *(uint8_t**)(chan + 0x18);
    uint16_t ai = mot ? *(uint16_t*)(mot + 0x278) : 0;
    logf("D3 %p f=[%u %u] o=(%7.1f %7.1f) fl=%08x ai=%u", (void*)chan, f1, f2,
         (double)px, (double)py, flags, ai);
}

static void makeChan3D(uint8_t* target, uint8_t* saved, uint8_t** tramp,
                       void* hook) {
    memcpy(saved, target, 15);
    *tramp = (uint8_t*)VirtualAlloc(nullptr, 15 + 16, MEM_COMMIT | MEM_RESERVE,
                                    PAGE_EXECUTE_READWRITE);
    if (!*tramp) {
        return;
    }
    memcpy(*tramp, target, 15);
    uint8_t* back = *tramp + 15;
    back[0] = 0xFF;
    back[1] = 0x25;  // jmp qword ptr [rip+0] (rax-free: prologues may use rax)
    memset(back + 2, 0, 4);
    uint64_t retAddr = (uint64_t)(target + 15);
    memcpy(back + 6, &retAddr, 8);

    uint8_t patch[15];
    patch[0] = 0xFF;
    patch[1] = 0x25;
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)hook;
    memcpy(patch + 6, &hookAddr, 8);
    patch[14] = 0x90;
    DWORD old;
    if (VirtualProtect(target, 15, PAGE_EXECUTE_READWRITE, &old)) {
        memcpy(target, patch, 15);
    }
}

static __attribute__((naked)) void chan3HookNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"
        "movq 0x48(%rsp), %rcx\n\t"  // original rdx = channel object
        "call traceChan3D\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_chan3Tramp(%rip)\n\t");
}

static __attribute__((naked)) void chan4HookNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"
        "movq 0x48(%rsp), %rcx\n\t"  // original rdx = channel object
        "call traceChan3D\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_chan4Tramp(%rip)\n\t");
}

static void installChan3DTrace() {
    makeChan3D(g_main + 0x1B26E0, g_chan3Saved, &g_chan3Tramp,
               (void*)chan3HookNaked);
    makeChan3D(g_main + 0x1B2840, g_chan4Saved, &g_chan4Tramp,
               (void*)chan4HookNaked);
    logf("trace: 3D chan hooks installed");
}

// body state dispatcher hook (0x1c2880): logs state transitions and dumps
// each state's motion table
static constexpr uintptr_t kBStateRva = 0x1C2880;
static uint8_t g_bstSaved[15];  // 2+4+6+3 = 15
static uint32_t g_bstLastState = 0xFFFFFFFF;
static uint64_t g_bstDumped[8] = {0};

// is this pointer inside committed memory? (crash-safe table reads)
static bool ptrIsCommit(uint8_t* p) {
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0) {
        return false;
    }
    return mbi.State == MEM_COMMIT &&
           mbi.Protect != PAGE_NOACCESS &&
           mbi.Protect != 0;
}

extern "C" void traceBState(uint8_t* obj) {
    uint32_t sid = *(uint32_t*)(obj + 0x1f8);
    uint32_t s94 = *(uint32_t*)(obj + 0x94);
    uint32_t s6c = *(uint32_t*)(obj + 0x6c);
    uint8_t s18 = obj[0x18];
    uint64_t mot = *(uint64_t*)(obj + 0x98);
    uint32_t fc = g_lastTickFC;
    uint32_t act = g_keyActiveUntilTick;
    // log + dump only while a button is being pressed (in game). The loading
    // sequence also runs this state machine; logging there stalls the load.
    if (fc < act) {
        if (sid != g_bstLastState) {
            g_bstLastState = sid;
            logf("B t=%u sid=%u s94=%x s6c=%u s18=%u mot=%p", fc, sid, s94,
                 s6c, s18, (void*)mot);
        }
        uint8_t* p = (uint8_t*)mot;
        if (p && ptrIsCommit(p) && (sid == 0x13 || sid == 0x14 || sid == 0x12 ||
                                    sid == 0x15)) {
            for (int b = 0; b < 8; b++) {
                if (g_bstDumped[b] == 0) {
                    g_bstDumped[b] = 0x100000000ULL | sid;
                    logf("BDUMP sid=%u mot=%p", sid, (void*)mot);
                    char line[80];
                    for (uint32_t row = 0; row < 0x800; row += 16) {
                        size_t n = 0;
                        n += (size_t)snprintf(line + n, sizeof(line) - n,
                                              "  %04x: ", row);
                        for (int i = 0; i < 16; i++) {
                            n += (size_t)snprintf(line + n, sizeof(line) - n,
                                                  "%02x ", p[row + i]);
                        }
                        logf("%s", line);
                    }
                    break;
                }
            }
        }
    }
}

static __attribute__((naked)) void bstHookNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"
        "movq 0x50(%rsp), %rcx\n\t"  // original rcx (body obj)
        "call traceBState\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_bstTramp(%rip)\n\t");
}

static void installBStateTrace() {
    uint8_t* target = g_main + kBStateRva;
    memcpy(g_bstSaved, target, 15);
    g_bstTramp = (uint8_t*)VirtualAlloc(nullptr, 15 + 16, MEM_COMMIT | MEM_RESERVE,
                                        PAGE_EXECUTE_READWRITE);
    if (!g_bstTramp) {
        logf("trace: bst trampoline alloc failed");
        return;
    }
    memcpy(g_bstTramp, target, 15);
    uint8_t* back = g_bstTramp + 15;
    back[0] = 0xFF;
    back[1] = 0x25;  // jmp qword ptr [rip+0] (rax-free: prologues may use rax)
    memset(back + 2, 0, 4);
    uint64_t retAddr = (uint64_t)(target + 15);
    memcpy(back + 6, &retAddr, 8);

    uint8_t patch[15];
    patch[0] = 0xFF;
    patch[1] = 0x25;
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)&bstHookNaked;
    memcpy(patch + 6, &hookAddr, 8);
    patch[14] = 0x90;
    DWORD old;
    if (!VirtualProtect(target, 15, PAGE_EXECUTE_READWRITE, &old)) {
        logf("trace: bst VirtualProtect failed");
        return;
    }
    memcpy(target, patch, 15);
    logf("trace: body state hooked at %p", (void*)target);
}

// motion channel-data setup hook (0x1c79f0): dumps the parsed motion tables
static constexpr uintptr_t kMotionRva = 0x1C79F0;
static uint8_t g_motSaved[19];  // 5+1+1+2+4+6 = 19
static uint64_t g_dumpedMots = 0;

extern "C" void traceMotion(uint8_t* obj, uint32_t edx, uint32_t r8) {
    uint64_t* mot = (uint64_t*)(obj + 0x98);
    uint64_t mp = *mot;
    if (!mp || (mp < 0x10000) || (mp > 0x7fffffffffffULL)) {
        return;
    }
    static uint32_t cnt = 0;
    cnt++;
    if (cnt <= 200 || (cnt % 2000) == 0) {
        logf("K %p edx=%u r8=%u mot=%p", (void*)obj, edx, r8, (void*)mp);
    }
    uint32_t act = g_keyActiveUntilTick;
    uint32_t fc = g_lastTickFC;
    // dump motion tables only while a button is being pressed (in game) and
    // the pointer is valid; up to 8 distinct tables
    if (fc < act && mp && ptrIsCommit((uint8_t*)mp)) {
        static uint64_t dumped[8] = {0};
        for (int b = 0; b < 8; b++) {
            if (dumped[b] == mp) {
                return;
            }
            if (dumped[b] == 0) {
                dumped[b] = mp;
                logf("MOTDUMP %p", (void*)mp);
                uint8_t* p = (uint8_t*)mp;
                char line[80];
                for (uint32_t row = 0; row < 0x2000; row += 16) {
                    size_t n = 0;
                    n += (size_t)snprintf(line + n, sizeof(line) - n,
                                          "  %04x: ", row);
                    for (int i = 0; i < 16; i++) {
                        n += (size_t)snprintf(line + n, sizeof(line) - n,
                                              "%02x ", p[row + i]);
                    }
                    logf("%s", line);
                }
                return;
            }
        }
    }
}

static __attribute__((naked)) void motHookNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"
        "movq 0x50(%rsp), %rcx\n\t"  // original rcx (obj)
        "movl 0x48(%rsp), %edx\n\t"  // original edx
        "movl 0x40(%rsp), %r8d\n\t"  // original r8d
        "call traceMotion\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_motTramp(%rip)\n\t");
}

static void installMotionTrace() {
    uint8_t* target = g_main + kMotionRva;
    memcpy(g_motSaved, target, 19);
    g_motTramp = (uint8_t*)VirtualAlloc(nullptr, 19 + 16, MEM_COMMIT | MEM_RESERVE,
                                        PAGE_EXECUTE_READWRITE);
    if (!g_motTramp) {
        logf("trace: mot trampoline alloc failed");
        return;
    }
    memcpy(g_motTramp, target, 19);
    uint8_t* back = g_motTramp + 19;
    back[0] = 0xFF;
    back[1] = 0x25;  // jmp qword ptr [rip+0] (rax-free: prologues may use rax)
    memset(back + 2, 0, 4);
    uint64_t retAddr = (uint64_t)(target + 19);
    memcpy(back + 6, &retAddr, 8);

    uint8_t patch[19];
    patch[0] = 0xFF;
    patch[1] = 0x25;
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)&motHookNaked;
    memcpy(patch + 6, &hookAddr, 8);
    memset(patch + 14, 0x90, 5);
    DWORD old;
    if (!VirtualProtect(target, 19, PAGE_EXECUTE_READWRITE, &old)) {
        logf("trace: mot VirtualProtect failed");
        return;
    }
    memcpy(target, patch, 19);
    logf("trace: motion hook at %p", (void*)target);
}

// game-logic callback hook (main.dll 0x5CE810, the flower update-message fn)
static constexpr uintptr_t kGameCbRva = 0x5CE810;
static uint8_t g_gcbSaved[19];  // 3+1+1+1+1+5+7 = 19, next at 0x5ce823
static uint32_t g_gcbLastSig = 0;

extern "C" void traceGameSys(uint8_t* sys) {
    // sys = the main-system object: +0xa8 pos, +0xe34/0xe35 state,
    // +0x5490/+0x54a0 soft timers
    float px = *(float*)(sys + 0xa8), py = *(float*)(sys + 0xac),
          pz = *(float*)(sys + 0xb0);
    uint32_t st = *(uint32_t*)(sys + 0xe34);
    float t0 = *(float*)(sys + 0x5490), t1 = *(float*)(sys + 0x5494);
    uint32_t fc = g_lastTickFC;
    static uint32_t ctr = 0;
    ctr++;
    uint32_t act = g_keyActiveUntilTick;
    if ((fc < act) && (ctr % 600) != 0) {
        return;  // only baseline when idle
    }
    logf("G t=%u st=%08x pos=(%8.1f %8.1f %8.1f) tm=(%.2f %.2f)", fc, st,
         (double)px, (double)py, (double)pz, (double)t0, (double)t1);
}

static __attribute__((naked)) void gcbHookNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"
        "movq 0x50(%rsp), %rcx\n\t"  // original rcx = main system object
        "call traceGameSys\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_gcbTramp(%rip)\n\t");
}

static void installGameCbTrace() {
    uint8_t* target = g_main + kGameCbRva;
    memcpy(g_gcbSaved, target, sizeof(g_gcbSaved));
    g_gcbTramp = (uint8_t*)VirtualAlloc(nullptr, sizeof(g_gcbSaved) + 16,
                                        MEM_COMMIT | MEM_RESERVE,
                                        PAGE_EXECUTE_READWRITE);
    if (!g_gcbTramp) {
        logf("trace: gcb trampoline alloc failed");
        return;
    }
    memcpy(g_gcbTramp, target, sizeof(g_gcbSaved));
    uint8_t* back = g_gcbTramp + sizeof(g_gcbSaved);
    back[0] = 0x48;
    back[1] = 0xB8;
    uint64_t retAddr = (uint64_t)(target + sizeof(g_gcbSaved));
    memcpy(back + 2, &retAddr, 8);
    back[10] = 0xFF;
    back[11] = 0xE0;

    uint8_t patch[19];
    patch[0] = 0xFF;
    patch[1] = 0x25;
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)&gcbHookNaked;
    memcpy(patch + 6, &hookAddr, 8);
    memset(patch + 14, 0x90, 5);
    DWORD old;
    if (!VirtualProtect(target, sizeof(patch), PAGE_EXECUTE_READWRITE, &old)) {
        logf("trace: gcb VirtualProtect failed");
        return;
    }
    memcpy(target, patch, sizeof(patch));
    logf("trace: game callback hooked at %p", (void*)target);
}

static __attribute__((naked)) void tickHookNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"
        "call traceOnTick\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_tickTramp(%rip)\n\t");
}

static void installTickTrace() {
    uint8_t* target = g_main + kTickRva;
    memcpy(g_tickSaved, target, sizeof(g_tickSaved));
    g_tickTramp = (uint8_t*)VirtualAlloc(nullptr, sizeof(g_tickSaved) + 16,
                                         MEM_COMMIT | MEM_RESERVE,
                                         PAGE_EXECUTE_READWRITE);
    if (!g_tickTramp) {
        logf("trace: trampoline alloc failed");
        return;
    }
    memcpy(g_tickTramp, target, sizeof(g_tickSaved));
    uint8_t* back = g_tickTramp + sizeof(g_tickSaved);
    back[0] = 0x48;
    back[1] = 0xB8;  // mov rax, imm64
    uint64_t retAddr = (uint64_t)(target + sizeof(g_tickSaved));
    memcpy(back + 2, &retAddr, 8);
    back[10] = 0xFF;
    back[11] = 0xE0;  // jmp rax

    uint8_t patch[14];
    patch[0] = 0xFF;
    patch[1] = 0x25;  // jmp qword ptr [rip+0]
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)&tickHookNaked;
    memcpy(patch + 6, &hookAddr, 8);
    DWORD old;
    if (!VirtualProtect(target, sizeof(patch), PAGE_EXECUTE_READWRITE, &old)) {
        logf("trace: VirtualProtect failed");
        return;
    }
    memcpy(target, patch, sizeof(patch));
    InterlockedExchange(&g_tickHookOk, 1);
    logf("trace: flower_tick hooked at %p", (void*)target);
}
#endif  // OKAMI_TRACE

// ---------------------------------------------------------------------------
// Game-speed diagnostics (OKAMI_DIAG builds only; gcc/clang, build 6990973)
//
// Hooks the character body update and the animation channel advance and
// logs, per tick, what moves and by how much. Used to find which game
// systems ignore the engine's 60 fps configuration.
// ---------------------------------------------------------------------------

#ifdef OKAMI_DIAG
#if !defined(__GNUC__) && !defined(__clang__)
#error "OKAMI_DIAG needs gcc or clang (GNU inline asm + naked functions)"
#endif
static constexpr uintptr_t kDiagBodyRva = 0x19E040;     // Body::update, this = rcx
static constexpr uintptr_t kDiagChanRva = 0x1B26E0;     // anim channel advance, chan = rdx
static constexpr uintptr_t kDiagChanDurRva = 0x1B8C50;  // int16 frameCount(motion)

extern "C" {
__attribute__((used)) uint8_t* g_diagBodyTramp = nullptr;
__attribute__((used)) uint8_t* g_diagChanTramp = nullptr;
}

struct DiagSlot {
    void* obj;
    uint32_t lastLog;
    uint32_t lastDump;
    uint32_t calls;
};
static DiagSlot g_diagBodies[64];
static DiagSlot g_diagChans[128];

static DiagSlot* diagSlot(DiagSlot* tab, size_t n, void* obj) {
    for (size_t i = 0; i < n; i++) {
        if (tab[i].obj == obj) {
            return &tab[i];
        }
    }
    for (size_t i = 0; i < n; i++) {
        if (!tab[i].obj) {
            tab[i].obj = obj;
            return &tab[i];
        }
    }
    return nullptr;
}

static uint32_t diagTick() {
    return g_eng.frameCounter ? *(volatile uint32_t*)g_eng.frameCounter : 0;
}

static void diagFault(DWORD code) {
    static volatile LONG faults = 0;
    if (InterlockedIncrement(&faults) <= 3) {
        logf("diag: hook fault 0x%08lX (suppressed)", (unsigned long)code);
    }
}

static void diagBodyImpl(uint8_t* obj, void* caller) {
    float vx = *(float*)(obj + 0x160), vy = *(float*)(obj + 0x164),
          vz = *(float*)(obj + 0x168);
    if (fabsf(vx) + fabsf(vy) + fabsf(vz) < 0.001f) {
        return;  // idle characters
    }
    DiagSlot* s = diagSlot(g_diagBodies, 64, obj);
    if (!s) {
        return;
    }
    uint32_t tick = diagTick();
    s->calls++;
    if (s->lastLog == 0 || tick - s->lastLog >= 6) {
        s->lastLog = tick;
        char c[96];
        logf("B t=%u m=%u obj=%p v=(%.3f %.3f %.3f) from %s", tick,
             (unsigned)*(volatile uint8_t*)g_eng.modeByte, (void*)obj, (double)vx,
             (double)vy, (double)vz, moduleNameOf(caller, c, sizeof(c)));
    }
    if (s->lastDump == 0 || tick - s->lastDump >= 60) {
        s->lastDump = tick;
        // raw float view of the object so the position vector can be located
        char line[1400];
        size_t n = (size_t)snprintf(line, sizeof(line), "BD t=%u obj=%p vt=%p |", tick,
                                    (void*)obj, *(void**)obj);
        for (int off = 0x10; off < 0x1a0 && n + 16 < sizeof(line); off += 4) {
            float f = *(float*)(obj + off);
            if (f != f || fabsf(f) > 1e7f || (f != 0.0f && fabsf(f) < 1e-6f)) {
                n += (size_t)snprintf(line + n, sizeof(line) - n, " .");
            } else {
                n += (size_t)snprintf(line + n, sizeof(line) - n, " %.1f", (double)f);
            }
        }
        logf("%s", line);
    }
}

static void diagChanImpl(uint8_t* chan, void* caller) {
    uint8_t* mot = *(uint8_t**)chan;
    // same validity checks the game makes before touching the motion data
    if (!mot || *(int16_t*)(mot + 0x6c) <= 1 || *(int16_t*)(mot + 0x6e) <= 1) {
        return;
    }
    uint32_t flags = *(uint32_t*)(chan + 0xa8);
    if (!(flags & (1u << 24)) || (flags & (1u << 13))) {
        return;
    }
    DiagSlot* s = diagSlot(g_diagChans, 128, chan);
    if (!s) {
        return;
    }
    s->calls++;
    if ((s->calls % 60) != 1) {
        return;
    }
    typedef int16_t(__fastcall * DurFn)(void*);
    int dur = ((DurFn)(g_main + kDiagChanDurRva))(mot);
    char c[96];
    logf("C t=%u m=%u chan=%p f=%u dur=%d calls=%u from %s", diagTick(),
         (unsigned)*(volatile uint8_t*)g_eng.modeByte, (void*)chan,
         (unsigned)*(uint16_t*)(chan + 0x88), dur, s->calls,
         moduleNameOf(caller, c, sizeof(c)));
}

struct DiagArgs {
    uint8_t* p;
    void* caller;
};

extern "C" void diagBody(uint8_t* obj, void* caller) {
    DiagArgs a = {obj, caller};
    DWORD code = guardedCall(
        [](void* v) { diagBodyImpl(((DiagArgs*)v)->p, ((DiagArgs*)v)->caller); }, &a);
    if (code) {
        diagFault(code);
    }
}

extern "C" void diagChan(uint8_t* chan, void* caller) {
    DiagArgs a = {chan, caller};
    DWORD code = guardedCall(
        [](void* v) { diagChanImpl(((DiagArgs*)v)->p, ((DiagArgs*)v)->caller); }, &a);
    if (code) {
        diagFault(code);
    }
}

static __attribute__((naked)) void diagBodyNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x30, %rsp\n\t"  // 7 pushes + 0x30 keeps rsp 16-aligned at the call
        "movq 0x58(%rsp), %rcx\n\t"  // original rcx (this)
        "movq 0x68(%rsp), %rdx\n\t"  // return address = caller
        "call diagBody\n\t"
        "addq $0x30, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_diagBodyTramp(%rip)\n\t");
}

static __attribute__((naked)) void diagChanNaked() {
    __asm__ volatile(
        "pushq %rax\n\t"
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x30, %rsp\n\t"  // 7 pushes + 0x30 keeps rsp 16-aligned at the call
        "movq 0x50(%rsp), %rcx\n\t"  // original rdx (channel)
        "movq 0x68(%rsp), %rdx\n\t"  // return address = caller
        "call diagChan\n\t"
        "addq $0x30, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "popq %rax\n\t"
        "jmp *g_diagChanTramp(%rip)\n\t");
}

// Detour a function whose first 15 bytes are whole instructions with no
// rip-relative operands: copy them to a trampoline, jump back after them.
static bool installDetour15(uint8_t* target, uint8_t** tramp, void* hook,
                            const char* what) {
    *tramp = (uint8_t*)VirtualAlloc(nullptr, 15 + 16, MEM_COMMIT | MEM_RESERVE,
                                    PAGE_EXECUTE_READWRITE);
    if (!*tramp) {
        logf("diag: %s trampoline alloc failed", what);
        return false;
    }
    memcpy(*tramp, target, 15);
    uint8_t* back = *tramp + 15;
    back[0] = 0xFF;
    back[1] = 0x25;  // jmp qword ptr [rip+0] (rax-free: prologues may use rax)
    memset(back + 2, 0, 4);
    uint64_t retAddr = (uint64_t)(target + 15);
    memcpy(back + 6, &retAddr, 8);
    uint8_t patch[15];
    patch[0] = 0xFF;
    patch[1] = 0x25;  // jmp qword ptr [rip+0]
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)hook;
    memcpy(patch + 6, &hookAddr, 8);
    patch[14] = 0x90;
    DWORD old;
    if (!VirtualProtect(target, 15, PAGE_EXECUTE_READWRITE, &old)) {
        logf("diag: %s VirtualProtect failed", what);
        return false;
    }
    memcpy(target, patch, 15);
    logf("diag: %s hooked at main+%llX", what, (unsigned long long)(target - g_main));
    return true;
}

static void installDiag() {
    // expected prologues on build 6990973
    static const uint8_t bodyPro[15] = {0x40, 0x57, 0x48, 0x81, 0xEC, 0x90, 0x00, 0x00,
                                        0x00, 0x48, 0x8B, 0x01, 0x48, 0x8B, 0xF9};
    static const uint8_t chanPro[15] = {0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x74,
                                        0x24, 0x20, 0x57, 0x48, 0x83, 0xEC, 0x30};
    if (!memcmp(g_main + kDiagBodyRva, bodyPro, 15)) {
        installDetour15(g_main + kDiagBodyRva, &g_diagBodyTramp, (void*)diagBodyNaked, "body");
    } else {
        logf("diag: body prologue mismatch, not hooked");
    }
    if (!memcmp(g_main + kDiagChanRva, chanPro, 15)) {
        installDetour15(g_main + kDiagChanRva, &g_diagChanTramp, (void*)diagChanNaked, "chan");
    } else {
        logf("diag: chan prologue mismatch, not hooked");
    }
}
#endif  // OKAMI_DIAG

// ---------------------------------------------------------------------------
// Experimental 60 fps game-logic fixes
//
// Measured on build 6990973: the player's own movement (class pl00) is fully
// time-scaled by the engine (81 timeScale sites), so it needs no fix; an
// earlier attempt to halve its displacement made it run at ~0.8x. What runs
// at double speed in 60 fps mode is the UI layer (menus, HUD, the brush
// screen) and effects, which advance per tick.
// ---------------------------------------------------------------------------

static volatile LONG g_fixesActive = 0;  // 1 while 60 fps mode is on and fixes enabled

// ---- task classification + half-rate gate ----
// Every game subsystem is a task object stepped once per tick. The MSVC RTTI
// on its vtable gives the class name (vtable[-1] -> COL, +0xc TypeDescriptor
// RVA, +0x10 name ".?AV<class>@@"). Classes listed in HalfRateTasks are
// stepped only on even ticks while fixes are active in 60 fps mode, which
// returns their per-frame logic to the stock 30 Hz.

struct TaskClass {
    void* key;        // task entry function (hdlr::Handler wraps a function pointer at +0x10)
    char name[64];
    bool halfRate;
    uint32_t steps;
    uint32_t skipped;
};
static TaskClass g_taskClasses[96];
static int g_taskClassCount = 0;

static bool vtableClassName(void** vt, char* out, size_t n) {
    if (!vt || !inImage(g_eng.main, vt)) {
        return false;
    }
    uint8_t* col = (uint8_t*)vt[-1];
    if (!col || !inImage(g_eng.main, col)) {
        return false;
    }
    uint32_t tdRva = *(uint32_t*)(col + 0xc);
    const char* nm = (const char*)(g_eng.main + tdRva + 0x10);
    if (!inImage(g_eng.main, nm) || nm[0] != '.' || nm[1] != '?') {
        return false;
    }
    // ".?AVcFoo@@" -> "cFoo"
    const char* b = nm + 4;
    size_t len = 0;
    while (b[len] && !(b[len] == '@' && b[len + 1] == '@') && len + 1 < n) {
        len++;
    }
    memcpy(out, b, len);
    out[len] = 0;
    return len > 0;
}

static bool rttiClassName(void* obj, char* out, size_t n) {
    return vtableClassName(*(void***)obj, out, n);
}

// HalfRateTasks entries are matched as a prefix of the task name, which is
// "<class> fn=main+<RVA>" for handler-wrapped tasks, so both class-name
// prefixes ("cSubScr") and function RVAs ("fn=main+41F2A0") work.
static bool listedHalfRate(const char* name) {
    const char* p = g_cfg.halfRateTasks;
    while (*p) {
        while (*p == ' ' || *p == ',') {
            p++;
        }
        const char* e = p;
        while (*e && *e != ',') {
            e++;
        }
        size_t len = (size_t)(e - p);
        while (len && p[len - 1] == ' ') {
            len--;
        }
        if (len && (!_strnicmp(name, p, len) || strstr(name, p) == name + 0 ||
                    (strstr(name, "fn=") && !_strnicmp(strstr(name, "fn="), p, len)))) {
            return true;
        }
        p = e;
    }
    return false;
}

static TaskClass* taskClassFor(void* obj) {
    char cls[48];
    if (!rttiClassName(obj, cls, sizeof(cls))) {
        snprintf(cls, sizeof(cls), "vt+%llX", (unsigned long long)(*(uint8_t**)obj - g_eng.main));
    }
    // hdlr::Handler<...> tasks: the real identity is the wrapped function
    void* key = *(void**)obj;
    void* fn = nullptr;
    if (!strncmp(cls, "?$Handler@", 10) && readableRange((uint8_t*)obj + 0x10, 8)) {
        fn = *(void**)((uint8_t*)obj + 0x10);
        if (fn) {
            key = fn;
        }
    }
    for (int i = 0; i < g_taskClassCount; i++) {
        if (g_taskClasses[i].key == key) {
            return &g_taskClasses[i];
        }
    }
    if (g_taskClassCount >= (int)(sizeof(g_taskClasses) / sizeof(g_taskClasses[0]))) {
        return nullptr;
    }
    TaskClass* c = &g_taskClasses[g_taskClassCount];
    c->key = key;
    if (fn) {
        char m[96];
        snprintf(c->name, sizeof(c->name), "%s fn=%s", cls, moduleNameOf(fn, m, sizeof(m)));
    } else {
        snprintf(c->name, sizeof(c->name), "%s", cls);
    }
    c->halfRate = listedHalfRate(c->name);
    c->steps = 0;
    c->skipped = 0;
    g_taskClassCount++;
    logf("task: %s%s", c->name, c->halfRate ? " [half-rate]" : "");
    return c;
}

#if defined(__GNUC__) || defined(__clang__)
extern "C" {
__attribute__((used)) uint8_t* g_taskStepTramp = nullptr;
__attribute__((used)) volatile uint8_t g_taskSkip = 0;
}

static void taskStepDecideImpl(uint8_t* entry) {
    g_taskSkip = 0;
    if (!entry || !readableRange(entry, 0x70)) {
        return;
    }
    uint8_t* obj = *(uint8_t**)(entry + 0x18);
    if (!obj || !readableRange(obj, 16)) {
        return;
    }
    TaskClass* c = taskClassFor(obj);
    if (!c) {
        return;
    }
    c->steps++;
    if (c->halfRate && g_fixesActive && g_eng.frameCounter &&
        (*(volatile uint32_t*)g_eng.frameCounter & 1)) {
        c->skipped++;
        g_taskSkip = 1;
    }
}

extern "C" void taskStepDecide(uint8_t* entry) {
    if (guardedCall([](void* e) { taskStepDecideImpl((uint8_t*)e); }, entry)) {
        g_taskSkip = 0;
    }
}

// entry = rcx. Decide, then either skip (plain return; the task thread just
// stays asleep this tick) or continue into the original via the trampoline.
static __attribute__((naked)) void taskStepHook() {
    __asm__ volatile(
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x28, %rsp\n\t"  // 6 pushes + 0x28 keeps rsp 16-aligned at the call
        "call taskStepDecide\n\t"
        "addq $0x28, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "cmpb $0, g_taskSkip(%rip)\n\t"
        "jne 1f\n\t"
        "jmp *g_taskStepTramp(%rip)\n\t"
        "1:\n\t"
        "ret\n\t");
}

static void installTaskGate() {
    if (!g_eng.taskStep || (!g_cfg.halfRateTasks[0] && !g_cfg.statusInterval)) {
        return;  // nothing to gate and nothing to report
    }
    uint8_t* target = g_eng.taskStep;
    g_taskStepTramp = (uint8_t*)VirtualAlloc(nullptr, 15 + 16, MEM_COMMIT | MEM_RESERVE,
                                             PAGE_EXECUTE_READWRITE);
    if (!g_taskStepTramp) {
        logf("task gate: trampoline alloc failed");
        return;
    }
    memcpy(g_taskStepTramp, target, 15);
    uint8_t* back = g_taskStepTramp + 15;
    back[0] = 0xFF;
    back[1] = 0x25;  // jmp qword ptr [rip+0] (rax-free: prologues may use rax)
    memset(back + 2, 0, 4);
    uint64_t retAddr = (uint64_t)(target + 15);
    memcpy(back + 6, &retAddr, 8);
    uint8_t patch[15];
    patch[0] = 0xFF;
    patch[1] = 0x25;
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)&taskStepHook;
    memcpy(patch + 6, &hookAddr, 8);
    patch[14] = 0x90;
    DWORD old;
    if (!VirtualProtect(target, 15, PAGE_EXECUTE_READWRITE, &old)) {
        logf("task gate: VirtualProtect failed");
        return;
    }
    memcpy(target, patch, 15);
    logf("task gate: task step hooked at main+%llX", (unsigned long long)(target - g_eng.main));
}
#else
static void installTaskGate() {
    logf("task gate: not available in MSVC builds (needs gcc/clang)");
}
#endif

// ---- virtual-slot half-rate gate ----
// The UI layer is not time-scaled by the engine: sub-screens (cSubScr*: the
// pause menu, brush screen, map and files) and HUD elements (cCock*) are
// stepped once per tick through a virtual "update" slot, separate from their
// draw slot. Every class with a matching RTTI name has that slot redirected
// to a stub which runs the original only on even ticks while fixes are
// active in 60 fps mode, so the UI keeps its stock 30 Hz logic while the
// game keeps drawing it at 60.

struct GateGroup {
    const char* key;                 // ini key / log name
    const char* label;               // what the class set is, for the log
    bool (*match)(const char* cls);  // RTTI class-name filter
    int slot;                        // vtable index of the per-tick update
    bool* enabled;
};

static bool matchSubScr(const char* c) {
    return !strncmp(c, "cSubScr", 7);
}
static bool matchCock(const char* c) {
    return !strncmp(c, "cCock", 5);
}
// effect objects: esp01..esp80, espStrip and the two bases share slot 3
// (the step wrapper that dispatches to each type's own update); the
// emitter classes and espSys have a different layout and are left alone
static bool matchEsp(const char* c) {
    return !strncmp(c, "esp", 3) &&
           (isdigit((unsigned char)c[3]) || !strcmp(c, "espBase") || !strcmp(c, "espWork") ||
            !strcmp(c, "espStrip"));
}

struct SlotGate {
    void** slot;   // vtable entry patched (nullptr for a function detour)
    void* orig;    // original function, or the detour's trampoline
    char name[40];
    int index;
    int group;     // index into g_gateGroups, -1 = ExtraGates / Probes
    bool gateIt;   // false = count and trace only (Probes)
    bool setGated; // true while the active gate set names this probe
    uint32_t calls;
    uint32_t skipped;
    int traced;
};

static GateGroup g_gateGroups[] = {
    {"FixMenus", "cSubScr*", matchSubScr, 4, &g_cfg.fixMenus},
    {"FixHud", "cCock*", matchCock, 3, &g_cfg.fixHud},
    {"FixEffects", "esp*", matchEsp, 3, &g_cfg.fixEffects},
};
static SlotGate g_gates[320];
static int g_gateCount = 0;

// Gate sets: each set names probes (by any substring of the probe name, e.g.
// the call-site RVA "4BA74A" or a class prefix "cSubScr") that should run at
// half rate while that set is selected. The set key cycles 0 (none), 1, 2 ...
// so several hypotheses can be compared in one play session.
static int g_activeSet = 0;
static int g_setCount = 0;

static const char* gateSetSpec(int n, size_t* lenOut) {
    const char* p = g_cfg.gateSets;
    for (int i = 1; i < n && *p; i++) {
        const char* bar = strchr(p, '|');
        if (!bar) {
            return nullptr;
        }
        p = bar + 1;
    }
    if (!*p) {
        return nullptr;
    }
    const char* bar = strchr(p, '|');
    *lenOut = bar ? (size_t)(bar - p) : strlen(p);
    return p;
}

static bool nameInSpec(const char* name, const char* spec, size_t specLen) {
    const char* p = spec;
    const char* end = spec + specLen;
    while (p < end) {
        while (p < end && (*p == ' ' || *p == ',')) {
            p++;
        }
        const char* e = p;
        while (e < end && *e != ',') {
            e++;
        }
        size_t len = (size_t)(e - p);
        while (len && p[len - 1] == ' ') {
            len--;
        }
        if (len) {
            char tok[64];
            if (len >= sizeof(tok)) {
                len = sizeof(tok) - 1;
            }
            memcpy(tok, p, len);
            tok[len] = 0;
            // case-insensitive substring match against the probe name
            for (const char* q = name; *q; q++) {
                if (!_strnicmp(q, tok, len)) {
                    return true;
                }
            }
        }
        p = e + 1;
    }
    return false;
}

static bool sectionRange(uint8_t* mod, const char* name, uint8_t** beg, uint8_t** end) {
    auto dos = (IMAGE_DOS_HEADER*)mod;
    auto nt = (IMAGE_NT_HEADERS*)(mod + dos->e_lfanew);
    auto sec = IMAGE_FIRST_SECTION(nt);
    size_t len = strlen(name);
    for (int i = 0; i < nt->FileHeader.NumberOfSections; i++) {
        if (!strncmp((const char*)sec[i].Name, name, len) && (len == 8 || sec[i].Name[len] == 0)) {
            *beg = mod + sec[i].VirtualAddress;
            *end = *beg + sec[i].Misc.VirtualSize;
            return true;
        }
    }
    return false;
}

static void logGateStats(double secs) {
    char line[512];
    size_t n = 0;
    for (int i = 0; i < g_gateCount; i++) {
        SlotGate* g = &g_gates[i];
        if (!g->calls) {
            continue;
        }
        if (n + 48 >= sizeof(line)) {
            logf("gates:%s", line);
            n = 0;
        }
        n += (size_t)snprintf(line + n, sizeof(line) - n, " %s[%d]:%.0f/s", g->name, g->index,
                              (double)g->calls / secs);
        if (g->skipped) {
            n += (size_t)snprintf(line + n, sizeof(line) - n, "(%u skipped)", g->skipped);
        }
        g->calls = 0;
        g->skipped = 0;
    }
    if (n) {
        logf("gates:%s", line);
    }
}

#if defined(__GNUC__) || defined(__clang__)
static uint8_t* g_gateStubs = nullptr;  // one kGateStubSize stub per gate
static const int kGateStubSize = 20;

// Heuristic return-address scan from the gated call's stack: values inside
// main.dll .text that follow a call instruction. Enough to find the
// per-frame dispatcher of a slot without unwind information.
static void logGateCallersImpl(SlotGate* g, void** entryRsp) {
    uint8_t *tb, *te;
    if (!textSection(g_eng.main, &tb, &te)) {
        return;
    }
    void* self = entryRsp[-1];  // rcx, pushed first by gateCommon
    char cls[40] = "?";
    if (self && readableRange(self, 8)) {
        rttiClassName(self, cls, sizeof(cls));
    }
    char buf[320] = "";
    size_t n = 0;
    int found = 0;
    for (int i = 0; i < 1024 && found < 12 && n + 16 < sizeof(buf); i++) {
        if (!readableRange(entryRsp + i, 8)) {
            break;
        }
        uint8_t* v = (uint8_t*)entryRsp[i];
        if (v < tb + 8 || v >= te) {
            continue;
        }
        bool isCall = v[-5] == 0xE8 || (v[-6] == 0xFF && v[-5] == 0x15) ||
                      (v[-2] == 0xFF && (v[-1] & 0xF8) == 0xD0) ||
                      (v[-3] == 0xFF && (v[-2] & 0xF8) == 0x50) ||
                      (v[-6] == 0xFF && (v[-5] & 0xF8) == 0x90) ||
                      (v[-4] == 0xFF && v[-3] == 0x54 && v[-2] == 0x24) ||
                      (v[-7] == 0x41 && v[-6] == 0xFF && (v[-5] & 0xF8) == 0x90);
        if (!isCall) {
            continue;
        }
        n += (size_t)snprintf(buf + n, sizeof(buf) - n, " %llX", (unsigned long long)(v - g_eng.main));
        found++;
    }
    logf("gate trace: %s[%d] this=%s tick=%u callers:%s", g->name, g->index, cls,
         g_eng.frameCounter ? *(volatile uint32_t*)g_eng.frameCounter : 0, buf);
}

static void logGateCallers(SlotGate* g, void** entryRsp) {
    struct Args {
        SlotGate* g;
        void** entryRsp;
    } a = {g, entryRsp};
    guardedCall([](void* v) { logGateCallersImpl(((Args*)v)->g, ((Args*)v)->entryRsp); }, &a);
}

// Called by gateCommon with the gate index and the stack pointer at entry
// (-> return address). Returns the original function to run, or nullptr to
// skip this tick (the stub then returns 0).
extern "C" void* gateDecide(int idx, void** entryRsp) {
    if (idx < 0 || idx >= g_gateCount) {
        return nullptr;
    }
    SlotGate* g = &g_gates[idx];
    g->calls++;
    if (g_cfg.gateTrace > 0 && g->traced < g_cfg.gateTrace) {
        g->traced++;
        logGateCallers(g, entryRsp);
    }
    bool on = (g->gateIt || g->setGated) && (g->group < 0 || *g_gateGroups[g->group].enabled);
    if (on && g_fixesActive && g_eng.frameCounter &&
        (*(volatile uint32_t*)g_eng.frameCounter & 1)) {
        g->skipped++;
        return nullptr;
    }
    return g->orig;
}

// Each stub does "mov r11d, idx; jmp gateCommon". Here: save the argument
// registers, ask gateDecide, then tail-jump into the original or return 0.
static __attribute__((naked)) void gateCommon() {
    __asm__ volatile(
        "pushq %rcx\n\t"
        "pushq %rdx\n\t"
        "pushq %r8\n\t"
        "pushq %r9\n\t"
        "pushq %r10\n\t"
        "pushq %r11\n\t"
        "subq $0x68, %rsp\n\t"  // 6 pushes + 0x68 keeps rsp 16-aligned at the call
        "movdqu %xmm0, 0x20(%rsp)\n\t"
        "movdqu %xmm1, 0x30(%rsp)\n\t"
        "movdqu %xmm2, 0x40(%rsp)\n\t"
        "movdqu %xmm3, 0x50(%rsp)\n\t"
        "movl %r11d, %ecx\n\t"
        "leaq 0x98(%rsp), %rdx\n\t"  // entry rsp (return address slot)
        "call gateDecide\n\t"
        "movdqu 0x20(%rsp), %xmm0\n\t"
        "movdqu 0x30(%rsp), %xmm1\n\t"
        "movdqu 0x40(%rsp), %xmm2\n\t"
        "movdqu 0x50(%rsp), %xmm3\n\t"
        "addq $0x68, %rsp\n\t"
        "popq %r11\n\t"
        "popq %r10\n\t"
        "popq %r9\n\t"
        "popq %r8\n\t"
        "popq %rdx\n\t"
        "popq %rcx\n\t"
        "testq %rax, %rax\n\t"
        "jz 1f\n\t"
        "jmp *%rax\n\t"
        "1:\n\t"
        "xorl %eax, %eax\n\t"
        "ret\n\t");
}

// "mov r11d, idx; jmp [rip+0] -> gateCommon"
static uint8_t* writeGateStub(int idx) {
    uint8_t* st = g_gateStubs + idx * kGateStubSize;
    st[0] = 0x41;
    st[1] = 0xBB;  // mov r11d, idx
    memcpy(st + 2, &idx, 4);
    st[6] = 0xFF;
    st[7] = 0x25;  // jmp qword ptr [rip+0]
    memset(st + 8, 0, 4);
    uint64_t common = (uint64_t)&gateCommon;
    memcpy(st + 12, &common, 8);
    return st;
}

static void addGate(void** vt, int slot, const char* cls, int group) {
    if (g_gateCount >= (int)(sizeof(g_gates) / sizeof(g_gates[0]))) {
        return;
    }
    void** slotp = vt + slot;
    for (int i = 0; i < g_gateCount; i++) {
        if (g_gates[i].slot == slotp) {
            return;
        }
    }
    SlotGate* g = &g_gates[g_gateCount];
    memset(g, 0, sizeof(*g));
    g->slot = slotp;
    g->orig = *slotp;
    snprintf(g->name, sizeof(g->name), "%s", cls);
    g->index = slot;
    g->group = group;
    g->gateIt = true;
    uint8_t* st = writeGateStub(g_gateCount);
    DWORD old;
    if (!VirtualProtect(slotp, 8, PAGE_READWRITE, &old)) {
        logf("gate: VirtualProtect failed for %s[%d]", cls, slot);
        return;
    }
    *(void* volatile*)slotp = st;
    VirtualProtect(slotp, 8, old, &old);
    g_gateCount++;
}


// ---- function detours ("fn:<rva>:<len>[:<fix>/<fix>..]") ----
// The first `len` bytes (whole instructions) move to a trampoline allocated
// within +-2 GB of main.dll; each `fix` is the byte offset of a disp32/rel32
// field in that prefix (rip-relative operand or call/jmp rel32) which is
// rebased by the move. tools: prolog2.py in the scratchpad writes the spec.
static uint8_t* g_trampPage = nullptr;
static size_t g_trampUsed = 0;

static void addFnGate(const char* spec, bool gateIt) {
    // spec = "<rva>:<len>[:<fix>/<fix>..]" (the "fn:" prefix already stripped)
    char buf[96];
    snprintf(buf, sizeof(buf), "%s", spec);
    char* lenStr = strchr(buf, ':');
    if (!lenStr) {
        logf("gate: bad function spec %s", spec);
        return;
    }
    *lenStr++ = 0;
    char* fixStr = strchr(lenStr, ':');
    if (fixStr) {
        *fixStr++ = 0;
    }
    unsigned long rva = strtoul(buf, nullptr, 16);
    int len = atoi(lenStr);
    uint8_t *tb, *te;
    if (!textSection(g_eng.main, &tb, &te) || len < 14 || len > 40 ||
        g_eng.main + rva < tb || g_eng.main + rva + len > te) {
        logf("gate: function spec %s rejected (not in .text or bad length)", spec);
        return;
    }
    if (g_gateCount >= (int)(sizeof(g_gates) / sizeof(g_gates[0]))) {
        return;
    }
    uint8_t* target = g_eng.main + rva;
    if (target[0] == 0xFF && target[1] == 0x25) {
        logf("gate: main+%lX already hooked", rva);
        return;
    }
    if (!g_trampPage) {
        g_trampPage = allocNear(g_eng.main, 4096);
        if (!g_trampPage) {
            logf("gate: no trampoline page near main.dll");
            return;
        }
        logf("gate: trampolines at %p (main.dll %p)", g_trampPage, g_eng.main);
    }
    size_t need = (size_t)len + 14;
    need = (need + 15) & ~(size_t)15;
    if (g_trampUsed + need > 4096) {
        logf("gate: trampoline page full");
        return;
    }
    uint8_t* tramp = g_trampPage + g_trampUsed;
    memcpy(tramp, target, (size_t)len);
    int64_t delta = (int64_t)target - (int64_t)tramp;
    while (fixStr && *fixStr) {
        int off = atoi(fixStr);
        if (off < 0 || off + 4 > len) {
            logf("gate: bad fix offset %d in %s", off, spec);
            return;
        }
        int32_t d;
        memcpy(&d, tramp + off, 4);
        int64_t nd = (int64_t)d + delta;
        if (nd != (int32_t)nd) {
            logf("gate: trampoline too far for %s", spec);
            return;
        }
        d = (int32_t)nd;
        memcpy(tramp + off, &d, 4);
        fixStr = strchr(fixStr, '/');
        if (fixStr) {
            fixStr++;
        }
    }
    uint8_t* back = tramp + len;
    back[0] = 0xFF;
    back[1] = 0x25;  // jmp qword ptr [rip+0] (rax-free: prologues may use rax)
    memset(back + 2, 0, 4);
    uint64_t retAddr = (uint64_t)(target + len);
    memcpy(back + 6, &retAddr, 8);
    g_trampUsed += need;

    SlotGate* g = &g_gates[g_gateCount];
    memset(g, 0, sizeof(*g));
    g->slot = nullptr;
    g->orig = tramp;
    snprintf(g->name, sizeof(g->name), "fn+%lX", rva);
    g->index = 0;
    g->group = -1;
    g->gateIt = gateIt;
    uint8_t* st = writeGateStub(g_gateCount);
    uint8_t patch[40];
    memset(patch, 0x90, sizeof(patch));
    patch[0] = 0xFF;
    patch[1] = 0x25;  // jmp qword ptr [rip+0]
    memset(patch + 2, 0, 4);
    uint64_t hookAddr = (uint64_t)st;
    memcpy(patch + 6, &hookAddr, 8);
    DWORD old;
    if (!VirtualProtect(target, (size_t)len, PAGE_EXECUTE_READWRITE, &old)) {
        logf("gate: VirtualProtect failed for main+%lX", rva);
        return;
    }
    memcpy(target, patch, (size_t)len);
    VirtualProtect(target, (size_t)len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), target, (size_t)len);
    g_gateCount++;
    logf("gate: %s main+%lX (%d bytes moved)", gateIt ? "extra fn" : "probe", rva, len);
}

// ---- call-site gates ("cs:<rva of the E8 call>") ----
// Patching the 5-byte relative call means no prologue analysis and gates one
// specific call, e.g. a single subsystem update inside the frame dispatcher.
static void addCsGate(const char* spec, bool gateIt) {
    unsigned long rva = strtoul(spec, nullptr, 16);
    uint8_t *tb, *te;
    if (!textSection(g_eng.main, &tb, &te) || g_eng.main + rva < tb ||
        g_eng.main + rva + 5 > te) {
        logf("gate: call site main+%lX not in .text", rva);
        return;
    }
    uint8_t* site = g_eng.main + rva;
    if (site[0] != 0xE8) {
        logf("gate: main+%lX is not a direct call (%02X)", rva, site[0]);
        return;
    }
    if (g_gateCount >= (int)(sizeof(g_gates) / sizeof(g_gates[0]))) {
        return;
    }
    int32_t rel;
    memcpy(&rel, site + 1, 4);
    uint8_t* callee = site + 5 + rel;
    if (!g_trampPage) {
        g_trampPage = allocNear(g_eng.main, 4096);
        if (!g_trampPage) {
            logf("gate: no trampoline page near main.dll");
            return;
        }
    }
    SlotGate* g = &g_gates[g_gateCount];
    memset(g, 0, sizeof(*g));
    g->slot = nullptr;
    g->orig = callee;
    snprintf(g->name, sizeof(g->name), "cs+%lX>%llX", rva,
             (unsigned long long)(callee - g_eng.main));
    g->index = 0;
    g->group = -1;
    g->gateIt = gateIt;
    uint8_t* st = writeGateStub(g_gateCount);
    int64_t newRel = (int64_t)st - (int64_t)(site + 5);
    if (newRel != (int32_t)newRel) {
        logf("gate: stub out of reach for call site main+%lX", rva);
        return;
    }
    int32_t nr = (int32_t)newRel;
    DWORD old;
    if (!VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &old)) {
        logf("gate: VirtualProtect failed for call site main+%lX", rva);
        return;
    }
    memcpy(site + 1, &nr, 4);
    VirtualProtect(site, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), site, 5);
    g_gateCount++;
}

// comma-separated "fn:..." / "cs:..." specs
static void addFnList(const char* list, bool gateIt) {
    const char* p = list;
    while (*p) {
        while (*p == ' ' || *p == ',') {
            p++;
        }
        const char* e = p;
        while (*e && *e != ',') {
            e++;
        }
        char tok[96];
        size_t len = (size_t)(e - p);
        if (len >= sizeof(tok)) {
            len = sizeof(tok) - 1;
        }
        memcpy(tok, p, len);
        tok[len] = 0;
        p = e;
        if (!len) {
            continue;
        }
        if (!strncmp(tok, "fn:", 3)) {
            addFnGate(tok + 3, gateIt);
        } else if (!strncmp(tok, "cs:", 3)) {
            addCsGate(tok + 3, gateIt);
        } else if (gateIt) {
            // handled by the vtable parser
        } else {
            logf("gate: Probes entry %s ignored (needs fn:<rva>:<len> or cs:<rva>)", tok);
        }
    }
}

// Walk main.dll's .rdata for MSVC RTTI complete-object locators (primary
// vtables only) whose class name passes match() (or starts with prefix);
// gate `slot` of each.
static int collectGates(const char* prefix, bool (*match)(const char*), int slot, int group) {
    uint8_t *rb, *re, *tb, *te;
    if (!sectionRange(g_eng.main, ".rdata", &rb, &re) || !textSection(g_eng.main, &tb, &te)) {
        return 0;
    }
    auto dos = (IMAGE_DOS_HEADER*)g_eng.main;
    auto nt = (IMAGE_NT_HEADERS*)(g_eng.main + dos->e_lfanew);
    uint64_t lo = (uint64_t)g_eng.main + 0x1000;
    uint64_t hi = (uint64_t)g_eng.main + nt->OptionalHeader.SizeOfImage - 0x20;
    size_t plen = prefix ? strlen(prefix) : 0;
    int before = g_gateCount;
    for (uint8_t* p = rb; p + 16 <= re; p += 8) {
        uint64_t v = *(uint64_t*)p;
        if (v < lo || v >= hi) {
            continue;
        }
        uint8_t* col = (uint8_t*)v;
        if (*(uint32_t*)col != 1 || *(uint32_t*)(col + 4) != 0 ||
            *(uint32_t*)(col + 0x14) != (uint32_t)(col - g_eng.main)) {
            continue;
        }
        uint32_t tdRva = *(uint32_t*)(col + 0xc);
        if (tdRva >= nt->OptionalHeader.SizeOfImage - 0x40) {
            continue;
        }
        const char* nm = (const char*)(g_eng.main + tdRva + 0x10);
        if (nm[0] != '.' || nm[1] != '?' || nm[2] != 'A' || (nm[3] != 'V' && nm[3] != 'U')) {
            continue;
        }
        if (match ? !match(nm + 4) : strncmp(nm + 4, prefix, plen) != 0) {
            continue;
        }
        void** vt = (void**)(p + 8);
        int n = 0;
        while (n < 64 && (uint8_t*)vt[n] >= tb && (uint8_t*)vt[n] < te) {
            n++;
        }
        char cls[40];
        if (!vtableClassName(vt, cls, sizeof(cls))) {
            continue;
        }
        if (slot >= n) {
            logf("gate: %s has only %d slots, slot %d not gated", cls, n, slot);
            continue;
        }
        addGate(vt, slot, cls, group);
    }
    return g_gateCount - before;
}

static void installSlotGates() {
    if (!g_eng.main) {
        return;
    }
    // near main.dll so a patched call site can reach a stub with its rel32
    g_gateStubs = allocNear(g_eng.main, 8192);
    if (!g_gateStubs) {
        g_gateStubs = (uint8_t*)VirtualAlloc(nullptr, 8192, MEM_COMMIT | MEM_RESERVE,
                                             PAGE_EXECUTE_READWRITE);
    }
    if (!g_gateStubs) {
        logf("gate: stub alloc failed");
        return;
    }
    for (int i = 0; i < (int)(sizeof(g_gateGroups) / sizeof(g_gateGroups[0])); i++) {
        GateGroup* gg = &g_gateGroups[i];
        if (!*gg->enabled) {
            // nothing to gate: leave those vtables untouched entirely
            continue;
        }
        int n = collectGates(nullptr, gg->match, gg->slot, i);
        logf("gate: %s -> %d classes (%s, slot %d)", gg->key, n, gg->label, gg->slot);
    }
    // ExtraGates: "<class prefix>:<slot>" or "<vtable RVA hex>:<slot>", comma-separated
    const char* p = g_cfg.extraGates;
    while (*p) {
        while (*p == ' ' || *p == ',') {
            p++;
        }
        const char* e = p;
        while (*e && *e != ',') {
            e++;
        }
        char tok[96];
        size_t len = (size_t)(e - p);
        if (len >= sizeof(tok)) {
            len = sizeof(tok) - 1;
        }
        memcpy(tok, p, len);
        tok[len] = 0;
        p = e;
        char* colon = strchr(tok, ':');
        if (!colon || !len || !strncmp(tok, "fn:", 3) || !strncmp(tok, "cs:", 3)) {
            continue;
        }
        *colon = 0;
        int slot = atoi(colon + 1);
        char* endp = nullptr;
        unsigned long rva = strtoul(tok, &endp, 16);
        if (endp && *endp == 0 && strlen(tok) >= 4) {
            void** vt = (void**)(g_eng.main + rva);
            uint8_t *tb, *te;
            char cls[40];
            if (slot < 0 || slot > 64 || !readableRange(vt, (size_t)(slot + 1) * 8) ||
                !textSection(g_eng.main, &tb, &te) || (uint8_t*)vt[slot] < tb ||
                (uint8_t*)vt[slot] >= te) {
                logf("gate: ExtraGates %s:%d is not a code slot, ignored", tok, slot);
                continue;
            }
            if (!vtableClassName(vt, cls, sizeof(cls))) {
                snprintf(cls, sizeof(cls), "vt+%lX", rva);
            }
            addGate(vt, slot, cls, -1);
            logf("gate: extra %s[%d] (main+%lX)", cls, slot, rva);
        } else {
            int n = collectGates(tok, nullptr, slot, -1);
            logf("gate: extra %s*:%d -> %d classes", tok, slot, n);
        }
    }
    int vslots = g_gateCount;
    addFnList(g_cfg.extraGates, true);
    addFnList(g_cfg.probes, false);
    if (g_gateCount) {
        logf("gate: %d virtual slots redirected, %d functions detoured", vslots,
             g_gateCount - vslots);
    }
    for (const char* p = g_cfg.gateSets; *p; p++) {
        if (p == g_cfg.gateSets || *p == '|') {
            g_setCount++;
        }
    }
    if (g_setCount) {
        logf("gate: %d gate set(s) available, %s cycles them", g_setCount, g_cfg.setName);
    }
}

// n = 0 turns every set-driven gate off; otherwise selects set n (1-based).
static void selectGateSet(int n) {
    size_t len = 0;
    const char* spec = n > 0 ? gateSetSpec(n, &len) : nullptr;
    int hits = 0;
    for (int i = 0; i < g_gateCount; i++) {
        bool in = spec && nameInSpec(g_gates[i].name, spec, len);
        g_gates[i].setGated = in;
        hits += in ? 1 : 0;
    }
    g_activeSet = n;
    if (spec) {
        logf("gate set %d active: %d probe(s) at half rate [%.*s]", n, hits, (int)len, spec);
    } else {
        logf("gate set 0: no set-driven half-rating");
    }
}
#else
static void installSlotGates() {
    logf("gate: not available in MSVC builds (needs gcc/clang)");
}
static void selectGateSet(int) {}
#endif

// ---------------------------------------------------------------------------
// 30/60 fps mode switching
// ---------------------------------------------------------------------------

static volatile LONG g_fps60 = 1;  // 1 = patched 60 fps, 0 = stock 30 fps
// the fast mode's rung: 1 = 120 (where checkFpsImms allows it), 0 = 60; F9
// cycles 30 -> 60 -> 120 -> 30
static volatile LONG g_fast120 = 0;

// With the shadow mode byte installed, the game's writers go to the shadow and
// the real byte is pinned; switching hands the stock context over (see
// applyShadowMode). Without it, the writers' immediates are rewritten.
static void applyFpsMode(bool announce) {
    updateIntegerSkips();
    updateDayClock();
    if (g_fps60) {
        if (!applyShadowMode(true)) {
            setWriterImm(1);
        }
        *(volatile uint8_t*)g_eng.modeByte = 1;
        g_eng.setPs2Disp(0);
        installPresentHook();
        InterlockedExchange(&g_fixesActive, g_cfg.fixes ? 1 : 0);
        if (announce) {
            logf("toggle -> 60 fps mode (patched)");
        }
    } else {
        InterlockedExchange(&g_fixesActive, 0);
        bool shadow = applyShadowMode(false);
        if (!shadow) {
            setWriterImm(2);
        }
        g_eng.setPs2Disp(1);
        if (!shadow) {
            *(volatile uint8_t*)g_eng.modeByte = 2;
        }
        removePresentHook();
        if (announce) {
            logf("toggle -> 30 fps mode (stock semantics)");
        }
    }
    updateIntegerSkips();
    updateDayClock();
}

// is [p, p+n) committed, readable memory? (for probing game objects)
static bool readableRange(const void* p, size_t n) {
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0 || mbi.State != MEM_COMMIT ||
        (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) || mbi.Protect == 0) {
        return false;
    }
    return (const uint8_t*)p + n <= (const uint8_t*)mbi.BaseAddress + mbi.RegionSize;
}

// Player position: pl00 object -> [+0xa8] transform -> x,y,z at +0,+4,+8
static float g_plVel[6] = {0, 0, 0, 0, 0, 0};  // pl00 +0xE48,+0xE4C,+0xE50,+0xE54,+0xE58,+0xE5C
static uint8_t g_plSub = 0;       // pl00 +0xE36: movement sub-state (jog / run / dash handler)
static uint16_t g_plWindup = 0;   // pl00 +0xE3C: wind-up / action timer, in ticks
static uint32_t g_plFlags = 0;    // pl00 +0xE30: bit 1 suppresses gravity for the tick
static float g_plB0 = 0.0f;      // pl00 +0xB0: the dimensionless term in the speed target
static float g_plPos[3] = {0, 0, 0};  // last sampled world position, for the jump trace
static float g_plLaunch = 0;      // pl00 +0xE14: jump launch accumulator (base + charge)
static uint16_t g_plCharge = 0;   // pl00 +0x1174: dash charge counter
static float g_plAnimRate = 0;    // pl00 +0xF54: animation playback rate

static bool playerPos(float out[3], uint8_t* extra) {
    if (!g_eng.playerSlot || !readableRange(g_eng.playerSlot, 8)) {
        return false;
    }
    uint8_t* pl = *g_eng.playerSlot;
    if (!pl || !readableRange(pl, 0xe60) || *(void**)pl != g_eng.playerVtable) {
        return false;
    }
    uint8_t* xf = *(uint8_t**)(pl + 0xa8);
    if (!xf || !readableRange(xf, 16)) {
        return false;
    }
    out[0] = *(volatile float*)(xf + 0);
    out[1] = *(volatile float*)(xf + 4);
    out[2] = *(volatile float*)(xf + 8);
    g_plPos[0] = out[0];
    g_plPos[1] = out[1];
    g_plPos[2] = out[2];
    extra[0] = pl[0xe34];
    extra[1] = pl[0xe35];
    for (int i = 0; i < 6; i++) {
        g_plVel[i] = *(volatile float*)(pl + 0xe48 + 4 * i);
    }
    g_plSub = pl[0xe36];
    g_plWindup = *(volatile uint16_t*)(pl + 0xe3c);
    g_plFlags = *(volatile uint32_t*)(pl + 0xe30);
    g_plLaunch = *(volatile float*)(pl + 0xe14);
    g_plCharge = *(volatile uint16_t*)(pl + 0x1174);
    g_plAnimRate = *(volatile float*)(pl + 0xf54);
    g_plB0 = *(volatile float*)(pl + 0xb0);
    return true;
}

static bool gameHasFocus() {
    HWND fg = GetForegroundWindow();
    if (!fg) {
        return false;
    }
    DWORD pid = 0;
    GetWindowThreadProcessId(fg, &pid);
    return pid == GetCurrentProcessId();
}

static void logDisplayInfo() {
    DEVMODEW dm;
    memset(&dm, 0, sizeof(dm));
    dm.dmSize = sizeof(dm);
    if (EnumDisplaySettingsW(nullptr, ENUM_CURRENT_SETTINGS, &dm)) {
        logf("display: primary %ux%u @ %u Hz", (unsigned)dm.dmPelsWidth,
             (unsigned)dm.dmPelsHeight, (unsigned)dm.dmDisplayFrequency);
    }
}

// ---------------------------------------------------------------------------
// Player run speed (build 6990973)
//
// Amaterasu's speed lives in pl00+0xE48 in units per tick, so a per-tick value
// that is not scaled for 60 fps covers twice the ground per second. The port
// did scale the top dash: at main+3B3826 it loads the engine time scale
// (main+B6AC38, 0.5 at 60 fps) and multiplies the 6.9 dash constant by it.
// The jog and run states were missed, which is why the measured speeds were
//
//     stage      30 fps      60 fps (stock patch)
//     jog        127/s       245/s
//     run        162/s       322/s
//     dash       207/s       207/s     <- the one that was scaled
//
// and why the flower dash felt slower than a plain run. Two fixes, both
// mirroring what the dash already does:
//
//   run  (main+3B34C8): the target speed is the raw 5.4 (or 2.7) constant.
//        A detour multiplies that target by the time scale just before it is
//        used. The 5.4 in xmm6 is left alone because it is also the divisor
//        for the animation rate, which must stay in per-tick units.
//   jog  (main+3B3183): its parameters are a private block in .data, so the
//        target (4.2), the dash-charge threshold (2.7) and the charge frame
//        count (200) are scaled in place while 60 fps mode is on.
// ---------------------------------------------------------------------------

static const uint32_t kRunPatchRva = 0x3B351C;   // movss xmm0, [rdi+0xE48]
static const uint32_t kRunResumeRva = 0x3B3524;  // addss xmm1, xmm2
static const uint8_t kRunOrig[8] = {0xF3, 0x0F, 0x10, 0x87, 0x48, 0x0E, 0x00, 0x00};

// Each jog parameter scales as a different power of the time scale, because
// they are quantities of different order. `tsPower` is that exponent.
// tsPower is the exponent of timeScale the parameter carries, except for
// JOG_BLEND, which is not a power law at all: see kJogParams below.
#define JOG_BLEND (-1)

struct JogParam {
    uint32_t rva;
    float stock;
    int tsPower;  // timeScale^tsPower, or JOG_BLEND
    const char* what;
};

// Why the exponents are what they are.
//
// Horizontal speed `pl00+0xE48` is in units per *tick*: nothing multiplies it
// by the time scale on its way to the transform, which is exactly why the
// patch has to scale the speed itself. Vertical motion is the opposite -- the
// time scale appears in both the gravity step and the integration, so the
// vertical velocity is already rate-independent and is left alone.
//
// The jog speed is the equilibrium of a per-tick acceleration against
// quadratic damping. Reading the two sites in pl01:
//
//     v += a                      ; main+3B2FBC, a = 0.2 (+ a slope term)
//     v  = v * (1.0 - c*v)        ; main+3B3183, c = 0.01
//
// Write V for real speed in units per second, so v = V*ts/30 and there are
// 30/ts ticks a second. Converting the per-tick update to continuous time:
//
//     dV/dt = a*900/ts^2 - c*V^2
//
// For that to be the same at every frame rate, `a` must carry ts^2 and `c`
// must not scale at all. Scaling `a` by ts and `c` by 1/ts -- which is what
// this patch did until now -- multiplies the whole right-hand side by 1/ts
// instead. The equilibrium is where the bracket is zero, so it comes out
// right at every rate (and measured right: 126/162/207 units/s at 60 fps
// against 123/158/206 at 30), but *the approach to it runs 1/ts too fast*.
// Amaterasu reached full speed twice as quickly at 60 fps and four times as
// quickly at 120, which is the acceleration having no weight to it.
//
// A velocity keeps ts^1, an acceleration takes ts^2, and the damping
// coefficient on v^2 takes ts^0. All of these are referenced only by the
// player movement code.
static const JogParam kJogParams[] = {
    {0x7A8358, 4.2f, 1, "jog target speed"},
    {0x7A8350, 2.7f, 1, "dash charge threshold"},
    // main+3B31D3, the charge's second step: +1174 += 1 + (int)((v - 2.7) / 1.5)
    // a tick (3B31C1..3B31DF), then the dash is ready past the charge frames.
    // (v - 2.7) / 1.5 is a ratio of two per-tick speeds, so the 1.5 takes ts
    // like the threshold. Unscaled, the ratio fell from about 1 to about 0.3 at
    // 120, the truncation made the step +1 instead of +2, and the charge took
    // 6.7 s instead of stock's 3.3 (twice as long at 60 and at 120). Read only
    // here (one reference to 7A8360).
    {0x7A8360, 1.5f, 1, "dash charge divisor"},
    {0x7A8148, 0.2f, 2, "jog acceleration"},
    {0x7A814C, 0.2f, 2, "jog slope acceleration (up)"},
    {0x7A8338, 0.4f, 2, "jog slope acceleration (down)"},
    {0x7A8340, 0.01f, 0, "jog damping coefficient"},
    // main+3B2DF2, a speed FLOOR: `if (v < 2.5) v = 2.5 - slope*k`, so entering
    // the run state snaps her to 2.5 per tick. A per-tick velocity, so ts^1.
    //
    // Unscaled this is the single largest error left in ground movement, and it
    // inverts the whole shape of a run rather than just scaling it. 2.5/tick is
    // 75 units/s at 30 fps and 300 at 120, while the target speed is correctly
    // scaled to 4.2/tick and 1.05/tick. So at 30 fps the floor is well BELOW
    // the target and she accelerates up to it; at 120 fps it is nearly three
    // times ABOVE it and she decays down. Measured, first tick of the run:
    //
    //      30 fps   2.60015/tick =  78 units/s, climbing to 126
    //     120 fps   2.40168/tick = 288 units/s, falling to 129
    //
    // Same steady state, opposite approach, and the burst is what reads as
    // twitchy at 120. The two rates agreed with themselves to 0.7% and 3.7%
    // across repeat runs, so this is not terrain.
    {0x7A8344, 2.5f, 1, "run speed floor"},
    // main+3B3235, the approach rate, and the reason 60 and 120 fps reached top
    // speed too quickly even with every term above scaled correctly:
    //
    //     v += (target - v) * 0.1      once per tick
    //
    // Nothing here is a velocity or an acceleration, so no power of ts is the
    // right answer. What has to hold is that the same FRACTION of the gap
    // survives each real second, and the gap is multiplied by (1 - k) per tick,
    // so (1 - k) is the quantity that takes the exponent:
    //
    //     k' = 1 - (1 - k)^ts          0.1 -> 0.0513 at 60, 0.0260 at 120
    //
    // It sits four bytes after the jog target speed, in the same struct, and
    // was missed because the finder was looking for velocities.
    //
    // Measured before the fix, against a 30 fps run of the same script: 95% of
    // top speed reached in 634 ms at 30 fps against under 200 ms at 120, with
    // the ramp overshooting to 1.47x mid-climb. Top speed itself and the stop
    // were already correct (-1.2% and -8%), which is why this hid for so long:
    // two of the three stages of a run were right.
    {0x7A835C, 0.1f, JOG_BLEND, "jog acceleration blend"},
};
static const uint32_t kChargeFramesRva = 0x7A8354;  // int: frames of charge before the dash
static const int32_t kChargeFramesStock = 200;

// The other half of the speed target, which the run fix alone did not cover.
//
// Both movement targets are a sum of two terms, and only one of them has ever
// carried the time scale:
//
//   run   main+3B34FC   movss xmm1, [pl+0xB0]     <- the term
//                       mulss xmm1, 1.3 or 1.1     (1.1 when [0xB0] is negative)
//                       movss xmm0, [pl+0xE48]     <- the run fix detours here,
//                       addss xmm1, xmm2              scaling xmm2 (5.4 or 2.7)
//
//   dash  main+3B381A   movss xmm1, [pl+0xB0]     <- the same term
//                       movss xmm0, [timeScale]    <- the engine scales its own
//                       mulss xmm0, 6.9               base, correctly
//                       mulss xmm1, 1.3 or 1.1
//                       addss xmm1, xmm0
//
// `pl+0xB0` is dimensionless -- it holds 1.0, or 0x3F32B8C2 (0.698 rad, 40
// degrees) -- so `[0xB0] * 1.3` is a speed contribution in per-tick units and
// has to scale with the time scale exactly like the base does. Nothing scales
// it, at either site.
//
// That error is invisible at 60 fps and obvious at 120, which is why it
// survived: the dash target is `[0xB0]*1.3 + timeScale*6.9`, so with [0xB0] = 1
// it reads 8.2 per tick at 30 fps (246 units/s) and should read 2.05 at 120.
// It actually reads 1.3 + 0.25*6.9 = 3.025, and the log measured 3.030 -- a
// 48% overspeed, and the last unexplained part of "she moves faster than her
// animation". At 60 fps the same arithmetic gives 4.75 against a correct 4.1,
// and the flat-ground case (where [0xB0] contributes nothing) measured exactly
// right, which is why every earlier speed test passed.
//
// The fix scales xmm1 where it is loaded, before the 1.3/1.1 multiply. The
// branch that picks 1.3 or 1.1 tests the sign of [0xB0] and the time scale is
// positive, so it is unaffected. g_playerScale is 1.0 at 30 fps and while the
// movement fixes are muted, so these detours are exact no-ops there.
static const uint32_t kSlopeSites[][2] = {
    {0x3B34FC, 0x3B3504},  // run target
    {0x3B381A, 0x3B3822},  // dash target
};
static const uint8_t kSlopeOrig[8] = {0xF3, 0x0F, 0x10, 0x8F, 0xB0, 0x00, 0x00, 0x00};

// Airborne horizontal acceleration
//
// Found with a hardware watchpoint on pl00+0xE48 rather than by reading code,
// after three rounds of static analysis fixed the wrong subsystem. Watching the
// field while playing named two instructions as the source of essentially all
// airborne writes -- main+3B5490 and main+3B54AE, 2072 hits each in 45 seconds
// -- and the pair reads:
//
//     main+3B547C   mulss xmm0, [timeScale]        ; a *= ts
//     main+3B5484   mulss xmm0, [pl+0xE10]
//     main+3B5490   movss [pl+0xE48], xmm0         ; v += ts * a
//     main+3B54AE   movss [pl+0xE48], xmm0         ; v *= k**ts  (mode table 7A81B8)
//
// Both halves carry the time scale, so this is not the missing-scale bug the
// earlier fixes chased. It is worse: an increment of `ts*a` against a decay of
// `k**ts` has a *rate-dependent equilibrium*. Solving `v = (v + ts*a) * k**ts`
// gives `v* = ts*a*k**ts / (1 - k**ts)`, and since `1 - k**ts` is about
// `-ts*ln k` for small ts the ts cancels, leaving the per-tick speed nearly
// constant -- so the real speed goes as 1/ts.
//
// The watchpoint measured exactly that. Peak per-tick value at this site:
//
//     30 fps   -0.3961 .. 3.4955
//     120 fps   0.0038 .. 3.1571
//
// the same number per tick at four times the tick rate. With the engine's own
// k = 0.86 the equilibrium real speed comes out 184 / 383 / 781 (arbitrary
// units) at 30 / 60 / 120 fps -- note that 60 fps is already twice too fast,
// which earlier testing missed because it only ever measured ground speed and
// jump height.
//
// An acceleration takes ts^2, exactly as the jog acceleration does. One more
// factor of the time scale here gives 184 / 191 / 195 instead.
// The same block exists four times over, once per player state that steers in
// the air, and the watchpoint only ever sat in one of them. Searching for the
// shape instead of the address -- a multiply by the time scale whose result is
// added into +0xE48 within ten instructions -- finds fourteen copies in the
// binary, four of them in the player:
//
//   main+3B547C  cKamikiFree jump  v += ts*a; v *= k^ts   (table 7A81B8)
//   main+3C32F9  state main+3C2E80 identical, same 3.0 gate, same table
//   main+3C9BE0  state main+3C9940 v += ts*a; v *= k^ts   (table 7A8160)
//   main+3BE265  state main+3BDCB0 v = v*k^ts + ts*a      (table 7A8218)
//
// The last applies its decay before the increment rather than after, which
// changes nothing that matters: the equilibrium is ts*a/(1 - k^ts) either way,
// and 1 - k^ts is about -ts*ln k, so the ts cancels and the real speed goes as
// 1/ts exactly as it does in the measured copy.
//
// The other ten copies are in main+246E60, main+2488B0 and main+249A90, which
// are not player code. They are the same bug and almost certainly make those
// actors four times too fast at 120 fps, but there is no test for them yet, so
// they are listed by tools/find_tick_thresholds.py and left alone.
static const uint32_t kAirAccelSites[][2] = {
    {0x3B547C, 0x3B5484},  // jump handler -- the copy the watchpoint measured
    {0x3BE265, 0x3BE26D},  // state main+3BDCB0
    {0x3C32F9, 0x3C3301},  // state main+3C2E80
    {0x3C9BE0, 0x3C9BE8},  // state main+3C9940
};
// each site's own rip displacement, so the bytes are checked per site
static const uint8_t kAirAccelOrig[][8] = {
    {0xF3, 0x0F, 0x59, 0x05, 0xB4, 0x57, 0x7B, 0x00},
    {0xF3, 0x0F, 0x59, 0x05, 0xCB, 0xC9, 0x7A, 0x00},
    {0xF3, 0x0F, 0x59, 0x05, 0x37, 0x79, 0x7A, 0x00},
    {0xF3, 0x0F, 0x59, 0x05, 0x50, 0x10, 0x7A, 0x00},
};

// Swimming acceleration: the same `v += ts*a; v *= k^ts` block in the water
// states 0x3B (main+3C3C70) and 0x3C (main+3C43C0), with k = 0.97 from the mode
// table at 7A8160. The shape search above missed them because they load the
// time scale (`movss xmmN, [timeScale]`) and multiply by the constant after,
// instead of multiplying by it. Swimming settled at 309 units/s at 120 fps
// against 98 at 30 (a play log, 2026-10-02).
//
// Scaling the increments to ts^2 keeps +0xE48 in per-tick units, as the
// ground, the jumps and state 0x54 (the water stroke, main+3C9BE0 above) keep
// it. The water states hand the speed to and from those: the ground enters
// 0x3B (main+3ADBA0), a jump or fall enters 0x3D (main+3AE07E, main+3AE857),
// 0x3C and 0x3B enter 0x54 on a button and 0x54 returns to 0x3B, and 0x3C
// jumps out as 0x03. 0x3D has no acceleration, only decays, so it needs
// nothing. Scaling the moves instead (a build before the release) settled at the
// same speed but cut her speed to a quarter on entering the water, and made
// every switch to or from 0x54 jump by 4x.
//
// The swimming states' land probe (`3 * v + 25` ahead, main+3C4C06 and
// main+3CA012) reads v per tick here, so at 120 it reaches 27.5 units at
// swimming speed instead of 35. That is left as it is.
static const uint32_t kSwimAccelSites[][2] = {
    {0x3C401A, 0x3C4022},  // state 0x3B: + ts * 0.002
    {0x3C4048, 0x3C4050},  // state 0x3B: + ts * 0.01 (while B6B128/B6B129)
    {0x3C467D, 0x3C4685},  // state 0x3C: + ts * 0.07 (the stroke, +0xE3E)
    {0x3C47D6, 0x3C47DE},  // state 0x3C: + ts * 0.02
};
static const uint8_t kSwimAccelOrig[][8] = {
    {0xF3, 0x0F, 0x10, 0x15, 0x16, 0x6C, 0x7A, 0x00},
    {0xF3, 0x0F, 0x10, 0x05, 0xE8, 0x6B, 0x7A, 0x00},
    {0xF3, 0x0F, 0x10, 0x05, 0xB3, 0x65, 0x7A, 0x00},
    {0xF3, 0x0F, 0x10, 0x05, 0x5A, 0x64, 0x7A, 0x00},
};
// the register each site loads the time scale into
static const int kSwimAccelReg[] = {2, 0, 0, 0};

// The stick drift: the wall-bounce "pinball" (found in play, 2026-09-23, the
// sake house). When an attack hits a wall she recoils (player state 0x2B,
// main+3C20E0, then 0x2C, main+3C2430). While she recoils the stick steers
// her, and state 0x48 (main+3C70C0) does the same. Each tick:
//
//     v(+0x10E8) = v * table7A81B8[mode - 1] + |stick| * 1.7 / 1024
//     position  += RotateY(heading) * (0, 0, v)
//
// The decay reads the port's per-mode table, so the mode constants already
// make it k^ts (k = 0.86). The stick term carries no time scale at all, not
// even the one factor the airborne copies above have. v settles at
// a / (1 - k^ts) a tick, applied fps times a second: 64/s at 30 fps, 247/s at
// the port's own 60 and 973/s at 120, fifteen times stock. With the stick
// held, a recoil throws her across a small room into the opposite wall.
//
// v is a displacement per tick at the current rate, as the port stores the
// player's other velocities. The gain that keeps both its settled value and
// its rise, per second, the same at every rate is
//
//     f(ts) = ts * (1 - k^ts) / (1 - k)
//
// v settles at a*ts/(1-k) a tick, 30/ts ticks a second: 30a/(1-k), stock's.
// It rises as 1 - k^(30t), stock's curve. f(1) = 1 exactly. ts^2, as the
// airborne sites use, would settle 5% low here.
//
// Found by shape, not address (tools/find_tick_thresholds.py): a multiply by
// the 1/1024 stick constant (main+6AEFD0) stored to +0x10E8 within four
// instructions with no time-scale multiply between. There are three copies,
// all here. The fourth use of that constant (main+3BE25D) is an airborne
// copy that already has its time scale.
static const uint32_t kStickDriftSites[][2] = {
    {0x3C2358, 0x3C2360},  // state 0x2B, the wall recoil (main+3C20E0)
    {0x3C2913, 0x3C291B},  // state 0x2C, after it (main+3C2430)
    {0x3C7255, 0x3C725D},  // state 0x48 (main+3C70C0)
};
static const uint8_t kStickDriftOrig[][8] = {
    {0xF3, 0x0F, 0x59, 0x05, 0x70, 0xCC, 0x2E, 0x00},
    {0xF3, 0x0F, 0x59, 0x05, 0xB5, 0xC6, 0x2E, 0x00},
    {0xF3, 0x0F, 0x59, 0x05, 0x73, 0x7D, 0x2E, 0x00},
};
static const uint32_t kStickDriftKRva = 0x7A81BC;  // the stock k all three decay by
static float g_stickDriftK = 0.0f;                 // read and checked at install

// Per-tick speed thresholds in the jump path
//
// pl00+0xE48 is a displacement per tick, so a threshold compared against it is
// also per tick and means a different real speed at every tick rate. The
// engine's own constants are all written for 30 fps, where a full run is about
// 3.05 per tick; at 120 fps the same run is 0.76 per tick and every one of
// these comparisons lands on the other side.
//
// main+3B4149  `if (v < 3.5 && slope < 0) v += slope * 8.0`
//     An uphill penalty applied once, at takeoff. The increment is a per-tick
//     velocity and carries no time scale, so at 120 fps it is four times too
//     large: a slope of -0.1 takes 0.8 off a speed of 0.76 and the clamp just
//     below drives it to zero. She stops dead on any incline. Both the gate
//     (ts) and the increment (ts) are scaled here.
//
// main+3B41E6  `if (2.0 <= v) jump = 5.4 else jump = 4.2`
//     Picks the running jump over the standing one, with a different animation
//     and a different launch velocity into pl00+0xE14. A 30 fps run clears 2.0
//     and a 120 fps run never does, so the fast variant is unreachable above
//     30 fps. Visible in the test log as the `want` figure: 42.6 at 30 fps
//     against 34.4 at 120, a ratio of 1.24 against the 5.4/4.2 = 1.29 the two
//     branches predict.
//
// main+3B5466  `if (v < 3.0) { v += ts*a; v *= k^ts; }`
//     The airborne steering block, and the reason a jump keeps its momentum.
//     At 30 fps a run launches at 3.05, the gate is false and the block never
//     runs, so the launch speed is preserved for the whole jump. At 120 fps a
//     run launches at 0.76, the gate is true, and the block -- a leaky
//     integrator whose equilibrium is the *steering* speed, not the run speed
//     -- drags the launch speed down to it with a 0.22 s time constant. A jump
//     out of a dash loses most of its speed before the apex.
//
// The constant is scaled rather than the field, so the comparison keeps its
// exact form. 3B41E6 is the exception: its constant is also passed on to
// FUN_1804ba080 as an animation blend length, so scaling it there would change
// the animation too. That one scales the field into a scratch register instead.
static const uint32_t kAirGateSites[][2] = {
    {0x3B4141, 0x3B4149},  // movss xmm0, [3.5]  -- takeoff uphill gate
    {0x3B4178, 0x3B4180},  // mulss xmm0, [8.0]  -- takeoff uphill increment
    {0x3B5452, 0x3B545A},  // movss xmm0, [3.0]  -- airborne steering gate
    {0x3C32D1, 0x3C32D9},  // movss xmm0, [3.0]  -- the same gate in main+3C2E80
};
static const uint8_t kAirGateOrig[][8] = {
    {0xF3, 0x0F, 0x10, 0x05, 0x3F, 0x5B, 0x2C, 0x00},
    {0xF3, 0x0F, 0x59, 0x05, 0xE0, 0x0D, 0x2C, 0x00},
    {0xF3, 0x0F, 0x10, 0x05, 0xFE, 0xFA, 0x2B, 0x00},
    {0xF3, 0x0F, 0x10, 0x05, 0x7F, 0x1C, 0x2B, 0x00},
};

// `comiss xmm0, [rdi+0xE48]` -- 7 bytes, so the detour fits with two NOPs.
// xmm1 is free here: nothing reads it between this compare and the call that
// both branches reach four instructions later, and it is volatile across that
// call anyway.
static const uint32_t kJumpPickRva = 0x3B41E6;
static const uint32_t kJumpPickResume = 0x3B41ED;
static const uint8_t kJumpPickOrig[7] = {0x0F, 0x2F, 0x87, 0x48, 0x0E, 0x00, 0x00};

// The animation rate is speed / 5.4 with a 0.7 floor, so halving the speed
// also halves the leg cycle. These two sites load the speed just before that
// divide; the detour scales the numerator back up so the rate matches 30 fps.
static const uint32_t kAnimSites[][2] = {
    {0x3B3275, 0x3B327D},  // jog handler  (rate = speed / 3.9)
    {0x3B35A2, 0x3B35AA},  // run handler  (rate = speed / 5.4)
    {0x3B38F7, 0x3B38FF},  // dash handler (rate = speed / 5.4)
};
static const uint8_t kAnimOrig[8] = {0xF3, 0x0F, 0x10, 0x8F, 0x48, 0x0E, 0x00, 0x00};

// ---------------------------------------------------------------------------
// Jump and wall-jump height at 60 fps
//
// Vertical motion is already integrated in real time by the player's update
// (pl00 vtable slot 8, main+3A9630):
//
//     pl00+0xE54 -= timeScale * 0.7          gravity   (main+3AB636)
//     transform.y += timeScale * pl00+0xE54  position  (main+3AB66B)
//
// Both the velocity and the acceleration carry the time scale, which makes
// that a plain Euler step with dt = timeScale: a jump reaches the same height
// at either frame rate, provided the launch velocity is left alone. The port
// does not leave it alone. The jump state (E35 = 03, handler main+3B3FF0)
// seeds its launch/charge accumulator with
//
//     pl00+0xE14 = timeScale * 5.0           main+3B4447
//
// which is the conversion the horizontal speed field +0xE48 needs -- that one
// really is a per-tick displacement -- but is wrong for a velocity the
// integrator will scale a second time. Apex height goes as v0^2, so halving
// the launch velocity leaves a quarter of the height at 60 fps. The per-tick
// charge growth just below it (main+3B4614) is a genuine per-tick increment,
// is correctly scaled, and is left alone.
//
// This is felt worst on the wall jump, which adds the impulse to the velocity
// already present (main+3B47C7, when the sub-action byte +0x1145 is 0x1E)
// rather than replacing it: applied at half strength part-way through a fall
// it barely lifts her at all, which is the long-standing "spins in place and
// gains no height" behaviour.
//
// The detour multiplies the stored value by 1/timeScale, undoing exactly the
// one multiply that should not be there.
//
// The jump's other two frame-rate faults -- the window in which holding the
// button charges that accumulator, and the window in which the jump floats by
// adding timeScale * 0.5 back to the velocity each tick -- are both the action
// timer pl00+0xE3C counted in raw ticks. They are not fixed here: they are two
// instances of a fault the whole character state machine has, and the action
// timer fix below covers them along with the other 163 sites.
//
// The same mistake -- an absolute vertical velocity assigned as
// timeScale * constant -- appears at 23 further sites in the player state
// handlers (knockback and various special moves; E35 = 09, 13, 29, 2A, 3F, 41
// and 56, plus three shared helpers). Those are not patched here: same bug
// class, but a different action each and none of them tested. See the README.
// ---------------------------------------------------------------------------

static const uint32_t kJumpSiteRva = 0x3B4447;    // movss [rdi+0xE14], xmm0
static const uint32_t kJumpResumeRva = 0x3B444F;  // movss xmm0, [timeScale]
static const uint8_t kJumpOrig[8] = {0xF3, 0x0F, 0x11, 0x87, 0x14, 0x0E, 0x00, 0x00};

// The same mistake, everywhere else it occurs. These 23 sites assign an
// absolute vertical velocity built as `timeScale * constant` -- knockback
// launches, pounces and special moves -- and the integrator scales it a second
// time, so each of them launches at half strength and a quarter of the height
// at 60 fps. The gravity steps look similar (`v = v - timeScale * 0.7`) but
// read the field first, and the generator excludes them on exactly that basis.
#include "launch_velocities.h"

// The gravity the integrator applies per time-scaled tick, used to turn a
// measured rise back into the launch velocity that produced it.
static const float kGravityPerTick = 0.7f;

static float* g_playerScale = nullptr;  // the detour multiplies the target by this
static float* g_animScale = nullptr;    // 1/timeScale while the animation fix is on
static float* g_jumpScale = nullptr;    // 1/timeScale while the jump fix is on
static float* g_gateScale = nullptr;    // timeScale for the per-tick thresholds
static float* g_gateInvScale = nullptr;  // 1/timeScale, for the one that scales the field
static float* g_driftScale = nullptr;    // f(ts) = ts(1-k^ts)/(1-k), the stick drift's gain
static volatile LONG g_jumpFixMuted = 0;  // set by the jump toggle key, for A/B testing
static bool g_speedFixInstalled = false;
static volatile LONG g_speedFixMuted = 0;  // set by the speed toggle key, for A/B testing
static bool g_jogParamsScaled = false;

// ---------------------------------------------------------------------------
// Memory within reach of main.dll
// ---------------------------------------------------------------------------
// Every stub, and every value a retargeted instruction reads, is reached from
// main.dll with a rel32, and some stubs reach another install's data the same
// way (the movement scales, the timer mask), so all of it has to sit within
// 2 GB of every byte of the image and of itself.
//
// Until 2026-09-25 each install reserved a region of its own. Windows hands
// out address space in 64 KB granules, so each took a granule, 16 bytes or
// 45 KB alike, found by probing outward from main.dll up to 1 GB. main.dll
// had always loaded high (0x7FFF...) with empty space around it. After a
// reboot on 2026-09-25 it loaded at 0x1B96C400000, relocated in among the
// heaps, where the game's own allocations were filling the free granules
// while the installs ran: after the phase steps none was left, and the decay
// factors, the shadow mode byte and the five families that need it (the world
// animations, the menus, the day clock, the integer clocks, the task waits)
// and the draw distance all stayed out.
//
// So the installs now share chunks, carved into page-aligned blocks: the
// first chunk of kNearChunk is reserved as soon as main.dll is known (from
// the loader's notification when it maps, before any of its code has run),
// others only if that fills, each within kNearReach of the whole image and of
// the chunks before it. A chunk keeps a granule clear of the image, so no
// block's first 64 KB overlaps main.dll (the offline verifiers map a pool's
// 64 KB in Unicorn next to the image).
static const size_t kNearPage = 4096;
static const size_t kNearChunk = 1u << 20;         // the first chunk; the installs take ~250 KB
static const size_t kNearChunkMax = 4u << 20;      // the tracer's 1.8 MB pool fits in one
static const uint64_t kNearReach = 0x7C000000ull;  // 2 GB less 64 MB of slack

struct NearChunk {
    uint8_t* base;
    size_t pages;
    uint64_t used[kNearChunkMax / kNearPage / 64];  // one bit per page
};
struct NearBlock {
    uint8_t* p;
    size_t pages;
};

static SRWLOCK g_nearLock = SRWLOCK_INIT;
static NearChunk g_nearChunks[32];
static int g_nearChunkCount = 0;
static NearBlock g_nearBlocks[128];
static int g_nearBlockCount = 0;
static const char* g_nearFirstWhen = nullptr;  // how the first chunk was found
static const uint8_t* g_nearFirstFor = nullptr;  // and the image it was reserved for
static volatile LONG g_nearFailLogged = 0;
static bool g_nearTestOld = false;  // OkamiCaveSelfTest's break: the old one-region-per-call

static uint64_t nearGranule() {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    return si.dwAllocationGranularity ? si.dwAllocationGranularity : 0x10000;
}

// The image's SizeOfImage from its PE header, 64 MB when it has none.
static size_t nearImageSpan(const uint8_t* base) {
    auto dos = (const IMAGE_DOS_HEADER*)base;
    if (dos->e_magic == IMAGE_DOS_SIGNATURE && dos->e_lfanew > 0 && dos->e_lfanew < 0x1000) {
        auto nt = (const IMAGE_NT_HEADERS64*)(base + dos->e_lfanew);
        if (nt->Signature == IMAGE_NT_SIGNATURE && nt->OptionalHeader.SizeOfImage) {
            return nt->OptionalHeader.SizeOfImage;
        }
    }
    return 64u << 20;
}

// Where a chunk may start and end so that a rel32 from any byte of the image
// reaches all of it and it reaches any byte of the image.
static void nearWindow(const uint8_t* base, size_t span, uint64_t* lo, uint64_t* hi) {
    uint64_t b = (uint64_t)base;
    *lo = b + span > kNearReach + 0x10000 ? b + span - kNearReach : 0x10000;
    *hi = b + kNearReach < 0x7FFFFFFE0000ull ? b + kNearReach : 0x7FFFFFFE0000ull;
}

// [c, c + size) against the window and against every chunk already held for
// this image (a self-test that maps main.dll again elsewhere leaves chunks no
// stub of the new mapping uses).
static bool nearFits(uint64_t c, uint64_t size, uint64_t lo, uint64_t hi) {
    if (c < lo || c + size > hi) {
        return false;
    }
    for (int i = 0; i < g_nearChunkCount; i++) {
        uint64_t b = (uint64_t)g_nearChunks[i].base;
        uint64_t e = b + g_nearChunks[i].pages * kNearPage;
        if (b < lo || e > hi) {
            continue;
        }
        uint64_t top = c + size > e ? c + size : e;
        uint64_t bottom = c < b ? c : b;
        if (top - bottom > kNearReach) {
            return false;
        }
    }
    return true;
}

// Reserves a chunk of `want` bytes (or the largest free run down to `least`)
// as near the image as the free space allows. Called with g_nearLock held;
// uses nothing but VirtualQuery and VirtualAlloc, so the loader's notification
// may call it.
static NearChunk* nearAddChunk(const uint8_t* base, size_t span, size_t want, size_t least) {
    if (g_nearChunkCount >= (int)(sizeof(g_nearChunks) / sizeof(g_nearChunks[0]))) {
        return nullptr;
    }
    uint64_t gran = nearGranule();
    want = (want + gran - 1) & ~(gran - 1);
    least = (least + gran - 1) & ~(gran - 1);
    if (want > kNearChunkMax) {
        want = kNearChunkMax;
    }
    if (least > want) {
        return nullptr;
    }
    uint64_t b = (uint64_t)base, e = b + span;
    uint64_t lo, hi;
    nearWindow(base, span, &lo, &hi);
    for (int attempt = 0; attempt < 4; attempt++) {
        uint64_t bestAt = 0, bestDist = ~0ull, bestSize = 0;
        MEMORY_BASIC_INFORMATION mbi;
        for (uint64_t a = lo & ~(gran - 1); a < hi && VirtualQuery((void*)a, &mbi, sizeof(mbi));
             a = (uint64_t)mbi.BaseAddress + mbi.RegionSize) {
            if (mbi.State != MEM_FREE) {
                continue;
            }
            uint64_t rb = (uint64_t)mbi.BaseAddress, re = rb + mbi.RegionSize;
            // the part within reach, a granule clear of the image on either side
            rb = rb > lo ? rb : lo;
            re = re < hi ? re : hi;
            if (re > b - gran && re <= b) re = b - gran;
            if (rb < e + gran && rb >= e) rb = e + gran;
            rb = (rb + gran - 1) & ~(gran - 1);
            re &= ~(gran - 1);
            if (re <= rb || re - rb < least) {
                continue;
            }
            uint64_t size = re - rb < want ? re - rb : want;
            // the end nearest the image
            uint64_t c = re <= b ? re - size : rb;
            uint64_t dist = c < b ? b - c : c - e;
            if (!nearFits(c, size, lo, hi)) {
                continue;
            }
            // a full-size chunk anywhere beats a short one; then the nearest
            if (size > bestSize || (size == bestSize && dist < bestDist)) {
                bestAt = c, bestDist = dist, bestSize = size;
            }
        }
        if (!bestSize) {
            return nullptr;
        }
        void* p = VirtualAlloc((void*)bestAt, (size_t)bestSize, MEM_COMMIT | MEM_RESERVE,
                               PAGE_EXECUTE_READWRITE);
        if (p) {
            NearChunk* ch = &g_nearChunks[g_nearChunkCount++];
            ch->base = (uint8_t*)p;
            ch->pages = (size_t)bestSize / kNearPage;
            memset(ch->used, 0, sizeof(ch->used));
            return ch;
        }
        // taken between the query and the reservation: look again
    }
    return nullptr;
}

// A run of `pages` free pages in a chunk the image reaches; marks and zeroes
// it. Called with g_nearLock held.
static uint8_t* nearTake(const uint8_t* base, size_t span, size_t pages) {
    if (g_nearBlockCount >= (int)(sizeof(g_nearBlocks) / sizeof(g_nearBlocks[0]))) {
        return nullptr;
    }
    uint64_t lo, hi;
    nearWindow(base, span, &lo, &hi);
    for (int k = 0; k < g_nearChunkCount; k++) {
        NearChunk& ch = g_nearChunks[k];
        uint64_t c = (uint64_t)ch.base;
        if (c < lo || c + ch.pages * kNearPage > hi) {
            continue;
        }
        size_t run = 0;
        for (size_t i = 0; i < ch.pages; i++) {
            bool used = (ch.used[i / 64] >> (i % 64)) & 1;
            run = used ? 0 : run + 1;
            if (run == pages) {
                size_t first = i + 1 - pages;
                for (size_t j = first; j <= i; j++) ch.used[j / 64] |= 1ull << (j % 64);
                uint8_t* p = ch.base + first * kNearPage;
                memset(p, 0, pages * kNearPage);  // as VirtualAlloc would hand it out
                g_nearBlocks[g_nearBlockCount++] = {p, pages};
                return p;
            }
        }
    }
    return nullptr;
}

// Reserves the first chunk for the image at `base`, once; `when` says how it
// was found, for the log. Safe from DllMain and from the loader's notification.
static void nearPrime(const uint8_t* base, size_t span, const char* when) {
    AcquireSRWLockExclusive(&g_nearLock);
    if (!g_nearChunkCount && nearAddChunk(base, span, kNearChunk, kNearPage)) {
        g_nearFirstWhen = when;
        g_nearFirstFor = base;
    }
    ReleaseSRWLockExclusive(&g_nearLock);
}

// Once, when a block could not be found: what the free space within reach
// looked like, for the next session's reading.
static void nearLogFailure(const uint8_t* base, size_t span, size_t size) {
    if (InterlockedExchange(&g_nearFailLogged, 1)) {
        return;
    }
    uint64_t gran = nearGranule(), lo, hi;
    nearWindow(base, span, &lo, &hi);
    uint64_t b = (uint64_t)base, freeGran = 0, regions = 0, bigSize = 0, bigAt = 0;
    MEMORY_BASIC_INFORMATION mbi;
    for (uint64_t a = lo & ~(gran - 1); a < hi && VirtualQuery((void*)a, &mbi, sizeof(mbi));
         a = (uint64_t)mbi.BaseAddress + mbi.RegionSize) {
        if (mbi.State != MEM_FREE) {
            continue;
        }
        uint64_t rb = (uint64_t)mbi.BaseAddress > lo ? (uint64_t)mbi.BaseAddress : lo;
        uint64_t re = (uint64_t)mbi.BaseAddress + mbi.RegionSize;
        re = re < hi ? re : hi;
        rb = (rb + gran - 1) & ~(gran - 1);
        re &= ~(gran - 1);
        if (re > rb) {
            regions++;
            freeGran += (re - rb) / gran;
            if (re - rb > bigSize) bigSize = re - rb, bigAt = rb;
        }
    }
    size_t usedPages = 0, pages = 0;
    for (int k = 0; k < g_nearChunkCount; k++) pages += g_nearChunks[k].pages;
    for (int i = 0; i < g_nearBlockCount; i++) usedPages += g_nearBlocks[i].pages;
    logf("caves: no room for %zu bytes within reach of main.dll (main%+lld MB .. main%+lld MB): "
         "%llu free granules in %llu regions, the largest %llu KB at main%+lld MB; "
         "held %d chunk(s), %zu of %zu KB used",
         size, ((long long)lo - (long long)b) >> 20, ((long long)hi - (long long)b) >> 20,
         (unsigned long long)freeGran, (unsigned long long)regions,
         (unsigned long long)(bigSize >> 10), ((long long)bigAt - (long long)b) >> 20,
         g_nearChunkCount, usedPages * kNearPage / 1024, pages * kNearPage / 1024);
}

// Page-aligned, zeroed, executable memory that a rel32 from anywhere in the
// image at `nearTo` reaches, and that reaches every other block.
static uint8_t* allocNear(uint8_t* nearTo, size_t size) {
    size_t pages = size ? (size + kNearPage - 1) / kNearPage : 1;
    if (pages * kNearPage > kNearChunkMax) {
        logf("caves: %zu bytes asked, more than a chunk holds", size);
        return nullptr;
    }
    size_t span = nearImageSpan(nearTo);
    AcquireSRWLockExclusive(&g_nearLock);
    uint8_t* p = nullptr;
    if (g_nearTestOld) {
        // verify_cave_pressure --break old: a region of its own per call, as
        // before 2026-09-25
        if (NearChunk* ch = nearAddChunk(nearTo, span, pages * kNearPage, pages * kNearPage)) {
            p = ch->base;
            for (size_t j = 0; j < pages; j++) ch->used[j / 64] |= 1ull << (j % 64);
            g_nearBlocks[g_nearBlockCount++] = {p, pages};
        }
    } else {
        p = nearTake(nearTo, span, pages);
    }
    if (!p && !g_nearTestOld) {
        size_t want = g_nearChunkCount ? kNearChunk / 4 : kNearChunk;
        if (want < pages * kNearPage) {
            want = pages * kNearPage;
        }
        if (nearAddChunk(nearTo, span, want, pages * kNearPage)) {
            if (!g_nearFirstWhen) {
                g_nearFirstWhen = "at the first install";
                g_nearFirstFor = nearTo;
            }
            p = nearTake(nearTo, span, pages);
        }
    }
    ReleaseSRWLockExclusive(&g_nearLock);
    if (!p) {
        nearLogFailure(nearTo, span, size);
    }
    return p;
}

// Returns a block to its chunk (its pages are zeroed when next handed out);
// anything allocNear did not hand out is released as a region of its own.
static void freeNear(void* p) {
    if (!p) {
        return;
    }
    bool mine = false;
    AcquireSRWLockExclusive(&g_nearLock);
    for (int i = 0; i < g_nearBlockCount && !mine; i++) {
        if (g_nearBlocks[i].p != p) {
            continue;
        }
        for (int k = 0; k < g_nearChunkCount; k++) {
            NearChunk& ch = g_nearChunks[k];
            if ((uint8_t*)p >= ch.base && (uint8_t*)p < ch.base + ch.pages * kNearPage) {
                size_t first = (size_t)((uint8_t*)p - ch.base) / kNearPage;
                for (size_t j = first; j < first + g_nearBlocks[i].pages; j++) {
                    ch.used[j / 64] &= ~(1ull << (j % 64));
                }
            }
        }
        g_nearBlocks[i] = g_nearBlocks[--g_nearBlockCount];
        mine = true;
    }
    ReleaseSRWLockExclusive(&g_nearLock);
    if (!mine) {
        VirtualFree(p, 0, MEM_RELEASE);
    }
}

// For the log: where the chunks are and how much of them the installs took.
static void nearLogPool(const char* when) {
    AcquireSRWLockShared(&g_nearLock);
    const uint8_t* main = g_nearFirstFor;
    size_t usedPages = 0, pages = 0;
    for (int k = 0; k < g_nearChunkCount; k++) pages += g_nearChunks[k].pages;
    for (int i = 0; i < g_nearBlockCount; i++) usedPages += g_nearBlocks[i].pages;
    char where[160] = "";
    size_t u = 0;
    for (int k = 0; k < g_nearChunkCount && u < sizeof(where); k++) {
        long long d = (long long)(uint64_t)g_nearChunks[k].base - (long long)(uint64_t)main;
        u += (size_t)snprintf(where + u, sizeof(where) - u, "%s%zu KB at main%s0x%llX",
                              k ? ", " : "", g_nearChunks[k].pages * kNearPage / 1024,
                              d < 0 ? "-" : "+", (unsigned long long)(d < 0 ? -d : d));
    }
    int chunks = g_nearChunkCount, blocks = g_nearBlockCount;
    const char* first = g_nearFirstWhen;
    ReleaseSRWLockShared(&g_nearLock);
    if (!chunks) {
        logf("caves (%s): none reserved yet", when);
        return;
    }
    logf("caves (%s): %s (the first reserved %s); %zu of %zu KB used in %d block(s)", when, where,
         first ? first : "?", usedPages * kNearPage / 1024, pages * kNearPage / 1024, blocks);
}

// The loader's DLL notifications (LdrRegisterDllNotification in ntdll,
// documented with LdrDllNotification), declared here rather than through
// winternl.h. The loader calls back when a DLL has been mapped, before its
// initializers run.
struct LdrName {
    USHORT len, max;
    PWSTR buf;
};
struct LdrDllData {
    ULONG flags;
    const LdrName* fullName;
    const LdrName* baseName;
    void* base;
    ULONG size;
};
typedef VOID(CALLBACK* LdrDllNotifyFn)(ULONG reason, const LdrDllData* data, void* ctx);
typedef LONG(NTAPI* LdrRegisterDllNotificationFn)(ULONG, LdrDllNotifyFn, void*, void**);
typedef LONG(NTAPI* LdrUnregisterDllNotificationFn)(void*);
static void* g_ldrCookie = nullptr;
static const char kNearWhenMapped[] = "when main.dll mapped, before its code ran";

static volatile LONG g_ldrCalls = 0;  // for the self-test: notifications seen
static wchar_t g_ldrLast[32];         // and the last one's name

static VOID CALLBACK onDllNotification(ULONG reason, const LdrDllData* d, void*) {
    static const wchar_t kName[] = L"main.dll";
    InterlockedIncrement(&g_ldrCalls);
    if (d && d->baseName && d->baseName->buf) {
        size_t n = d->baseName->len / 2 < 31 ? d->baseName->len / 2 : 31;
        memcpy(g_ldrLast, d->baseName->buf, n * 2);
        g_ldrLast[n] = 0;
    }
    if (reason != 1 || !d || !d->baseName || !d->baseName->buf || d->baseName->len != 16) {
        return;  // 1: loaded; 16 bytes: 8 wide characters
    }
    for (int i = 0; i < 8; i++) {
        wchar_t c = d->baseName->buf[i];
        if ((c >= L'A' && c <= L'Z' ? c + 32 : c) != kName[i]) {
            return;
        }
    }
    nearPrime((const uint8_t*)d->base, d->size, kNearWhenMapped);
}

// From DllMain: the caves' first chunk now if main.dll is already mapped (we
// are loaded while its imports are), else when the loader maps it. Only
// VirtualQuery, VirtualAlloc and ntdll here, all safe under the loader lock.
static void primeNearPool() {
    if (HMODULE m = GetModuleHandleA("main.dll")) {
        nearPrime((const uint8_t*)m, nearImageSpan((const uint8_t*)m),
                  "in DllMain, main.dll already mapped");
        return;
    }
    HMODULE nt = GetModuleHandleA("ntdll.dll");
    auto reg = nt ? (LdrRegisterDllNotificationFn)(void*)GetProcAddress(
                        nt, "LdrRegisterDllNotification")
                  : nullptr;
    if (!reg || reg(0, onDllNotification, nullptr, &g_ldrCookie) != 0) {
        g_ldrCookie = nullptr;
    }
}

static void unprimeNearPool() {
    HMODULE nt = GetModuleHandleA("ntdll.dll");
    auto unreg = nt ? (LdrUnregisterDllNotificationFn)(void*)GetProcAddress(
                          nt, "LdrUnregisterDllNotification")
                    : nullptr;
    if (g_ldrCookie && unreg) {
        unreg(g_ldrCookie);
    }
    g_ldrCookie = nullptr;
}

// ---------------------------------------------------------------------------
// Offline self-test of the above, driven by tools/verify_cave_pressure.py.
// ---------------------------------------------------------------------------
static void nearResetForTest() {
    AcquireSRWLockExclusive(&g_nearLock);
    for (int k = 0; k < g_nearChunkCount; k++) VirtualFree(g_nearChunks[k].base, 0, MEM_RELEASE);
    g_nearChunkCount = 0;
    g_nearBlockCount = 0;
    g_nearFirstWhen = nullptr;
    g_nearFirstFor = nullptr;
    g_nearFailLogged = 0;
    ReleaseSRWLockExclusive(&g_nearLock);
}

// What the watcher's installs ask for, in order, with the default ini and
// IntegerSkips on (as in the development okami.ini).
struct NearRequest {
    const char* what;
    size_t size;
};
static const NearRequest kNearRequests[] = {
    {"slot gates", 8192},        {"movement", 8192},         {"action timers", 64 + 48 * 262},
    {"memory timers", 48 * 422}, {"lea timers", 48 * 106},   {"frame clocks", 4096},
    {"mode constants", 16},      {"mode multipliers", 4096}, {"phase steps", 512},
    {"decay factors", 512},      {"shadow mode", 4096},      {"integer skips", 0x11B0},
    {"day clock", 0x100},        {"menus", 0x2D0},           {"world anims", 0xB2D0},
    {"task waits", 0x240},       {"draw distance", 4096},    {"harness", 4096},
};
static const int kNearRequestCount = (int)(sizeof(kNearRequests) / sizeof(kNearRequests[0]));

// Every request handed out, in reach of every byte of the image both ways,
// page-aligned, zeroed, apart from each other and within reach of each other,
// and each chunk a granule clear of the image; then a block given back and
// asked for again. Returns the failures.
static int nearCheckRequests(FILE* rep, const char* label, const uint8_t* main, size_t span,
                             uint8_t** got) {
    int fails = 0, handed = 0;
    for (int i = 0; i < kNearRequestCount; i++) {
        got[i] = allocNear((uint8_t*)main, kNearRequests[i].size);
        bool zero = true;
        if (got[i]) {
            handed++;
            for (size_t j = 0; j < kNearRequests[i].size && zero; j++) zero = !got[i][j];
            memset(got[i], 0xA0 + i, kNearRequests[i].size);
        }
        char at[48] = "NONE";
        if (got[i]) {
            long long d = (long long)(uint64_t)got[i] - (long long)(uint64_t)main;
            snprintf(at, sizeof(at), "at main%s0x%llX%s", d < 0 ? "-" : "+",
                     (unsigned long long)(d < 0 ? -d : d), zero ? "" : " NOT ZEROED");
        }
        fprintf(rep, "%s %s: %-16s %6zu bytes %s\n", got[i] && zero ? "ok  " : "FAIL", label,
                kNearRequests[i].what, kNearRequests[i].size, at);
        fails += !got[i] || !zero;
    }
    const int64_t kMax = 0x7FFFFFFFll, kMin = -0x80000000ll;
    int64_t b = (int64_t)(uint64_t)main, e = b + (int64_t)span;
    int64_t lowest = INT64_MAX, highest = INT64_MIN;
    int reach = 0, align = 0, overlap = 0;
    for (int i = 0; i < kNearRequestCount; i++) {
        if (!got[i]) continue;
        int64_t p = (int64_t)(uint64_t)got[i], q = p + (int64_t)kNearRequests[i].size;
        // a rel32 from anywhere in the image to anywhere in the block, and back
        reach += !(q - b <= kMax && p - e >= kMin && e - p <= kMax && b - q >= kMin);
        align += (p & (int64_t)(kNearPage - 1)) != 0;
        lowest = p < lowest ? p : lowest;
        highest = q > highest ? q : highest;
        for (int j = 0; j < i; j++) {
            if (!got[j]) continue;
            int64_t pj = (int64_t)(uint64_t)got[j], qj = pj + (int64_t)kNearRequests[j].size;
            overlap += p < qj && pj < q;
        }
    }
    bool mutual = !handed || highest - lowest <= kMax;
    uint64_t gran = nearGranule();
    int clear = 0;
    for (int k = 0; k < g_nearChunkCount; k++) {
        int64_t cb = (int64_t)(uint64_t)g_nearChunks[k].base;
        int64_t ce = cb + (int64_t)(g_nearChunks[k].pages * kNearPage);
        if (ce > b - (int64_t)gran && cb < e + (int64_t)gran) clear++;
    }
    fprintf(rep, "%s %s: %d of %d handed out; %d out of reach, %d not page-aligned, %d overlapping; "
                 "all within one rel32 of each other %d; %d chunk(s), %d within a granule of the "
                 "image\n",
            handed == kNearRequestCount && !reach && !align && !overlap && mutual && !clear
                ? "ok  "
                : "FAIL",
            label, handed, kNearRequestCount, reach, align, overlap, (int)mutual, g_nearChunkCount,
            clear);
    fails += (handed != kNearRequestCount) + reach + align + overlap + !mutual + clear;
    // the world animations' pool given back (as a rollback does) and asked for again
    int w = kNearRequestCount - 4;
    if (got[w]) {
        freeNear(got[w]);
        uint8_t* again = allocNear((uint8_t*)main, kNearRequests[w].size);
        bool zero = again != nullptr;
        for (size_t j = 0; again && j < kNearRequests[w].size && zero; j++) zero = !again[j];
        bool apart = again != nullptr;
        for (int i = 0; again && i < kNearRequestCount; i++) {
            if (i == w || !got[i]) continue;
            apart &= again + kNearRequests[w].size <= got[i] ||
                     got[i] + kNearRequests[i].size <= again;
        }
        fprintf(rep, "%s %s: %s given back and asked for again: %s, zeroed %d, apart from the "
                     "rest %d\n",
                again && zero && apart ? "ok  " : "FAIL", label, kNearRequests[w].what,
                again ? (again == got[w] ? "the same block" : "another block") : "NONE", (int)zero,
                (int)apart);
        fails += !(again && zero && apart);
        got[w] = again;
    }
    return fails;
}

// The loader's notification for a DLL named main.dll loaded after this one;
// then main.dll mapped without running it, the requests with the space around
// it free, and again with the space within reach filled but for `leave` single
// granules spread through it (9 is what the reboot of 2026-09-25 left: the
// tenth install failed). mode 1 (--break old) hands each request a region of
// its own, as allocNear did before: the crowded run must then fail.
extern "C" __declspec(dllexport) int OkamiCaveSelfTest(const char* mainPath, const char* outDir,
                                                       int leave, int mode) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    int fails = 0;
    // The loader's notification. It is not sent for a DONT_RESOLVE_DLL_REFERENCES
    // mapping, so this loads a DLL named main.dll the way the game loads the
    // real one: a copy of the system's version.dll, whose DllMain does nothing.
    {
        bool registered = g_ldrCookie != nullptr;
        char sys[MAX_PATH], stand[MAX_PATH];
        GetSystemDirectoryA(sys, MAX_PATH);
        strncat(sys, "\\version.dll", sizeof(sys) - strlen(sys) - 1);
        snprintf(stand, sizeof(stand), "%s\\main.dll", outDir);
        HMODULE s = CopyFileA(sys, stand, FALSE) ? LoadLibraryA(stand) : nullptr;
        const uint8_t* sb = (const uint8_t*)s;
        bool primed = s && g_nearChunkCount == 1 && g_nearFirstFor == sb &&
                      g_nearFirstWhen == kNearWhenMapped &&
                      g_nearChunks[0].pages * kNearPage == kNearChunk;
        if (primed) {
            uint64_t lo, hi, c = (uint64_t)g_nearChunks[0].base;
            nearWindow(sb, nearImageSpan(sb), &lo, &hi);
            primed = c >= lo && c + kNearChunk <= hi;
        }
        fprintf(rep, "%s notification: registered at load %d, %ld call(s), the last for %ls; a "
                     "DLL named main.dll loaded: the first chunk %s, %zu KB, within reach\n",
                registered && primed ? "ok  " : "FAIL", (int)registered, (long)g_ldrCalls,
                g_ldrLast[0] ? g_ldrLast : L"-",
                g_nearFirstWhen ? g_nearFirstWhen : "never reserved",
                g_nearChunkCount ? g_nearChunks[0].pages * kNearPage / 1024 : 0);
        fails += !(registered && primed);
        if (s) FreeLibrary(s);
        nearResetForTest();
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    if (!m) {
        fprintf(rep, "FAIL load %s (%lu)\n", mainPath, GetLastError());
        fclose(rep);
        return 1;
    }
    const uint8_t* main = (const uint8_t*)m;
    size_t span = nearImageSpan(main);

    static uint8_t* got[kNearRequestCount];
    // 1. room enough: everything in the first chunk
    nearResetForTest();
    g_nearTestOld = mode == 1;
    fails += nearCheckRequests(rep, "roomy", main, span, got);
    bool one = mode == 1 || (g_nearChunkCount == 1 && g_nearChunks[0].pages * kNearPage == kNearChunk);
    fprintf(rep, "%s roomy: %d chunk(s)%s\n", one ? "ok  " : "FAIL", g_nearChunkCount,
            mode == 1 ? " (old: one per request)" : ", expected one of 1024 KB");
    fails += !one;

    // 2. crowded: the window filled but for `leave` single granules
    nearResetForTest();
    uint64_t gran = nearGranule(), lo, hi;
    nearWindow(main, span, &lo, &hi);
    static uint64_t regions[8192][2];
    int nr = 0;
    uint64_t total = 0;
    MEMORY_BASIC_INFORMATION mbi;
    for (uint64_t a = lo & ~(gran - 1); a < hi && VirtualQuery((void*)a, &mbi, sizeof(mbi));
         a = (uint64_t)mbi.BaseAddress + mbi.RegionSize) {
        if (mbi.State != MEM_FREE) continue;
        uint64_t rb = (uint64_t)mbi.BaseAddress > lo ? (uint64_t)mbi.BaseAddress : lo;
        uint64_t re = (uint64_t)mbi.BaseAddress + mbi.RegionSize;
        re = re < hi ? re : hi;
        rb = (rb + gran - 1) & ~(gran - 1);
        re &= ~(gran - 1);
        if (re > rb && nr < 8192) {
            regions[nr][0] = rb, regions[nr][1] = re, nr++;
            total += (re - rb) / gran;
        }
    }
    static void* holds[16384];
    int nh = 0, holdFails = 0, kept = 0;
    uint64_t idx = 0;
    auto hold = [&](uint64_t from, uint64_t to) {
        if (to <= from) return;
        void* p = nh < 16384 ? VirtualAlloc((void*)from, (size_t)(to - from), MEM_RESERVE,
                                            PAGE_NOACCESS)
                             : nullptr;
        if (p) holds[nh++] = p;
        else holdFails++;
    };
    for (int r = 0; r < nr; r++) {
        uint64_t rb = regions[r][0], re = regions[r][1], n = (re - rb) / gran, cur = rb;
        while (kept < leave) {
            uint64_t keep = ((2 * (uint64_t)kept + 1) * total) / (2 * (uint64_t)leave);
            if (keep >= idx + n) break;
            uint64_t at = rb + (keep - idx) * gran;
            hold(cur, at);
            cur = at + gran;
            kept++;
        }
        hold(cur, re);
        idx += n;
    }
    uint64_t left = 0;
    for (uint64_t a = lo & ~(gran - 1); a < hi && VirtualQuery((void*)a, &mbi, sizeof(mbi));
         a = (uint64_t)mbi.BaseAddress + mbi.RegionSize) {
        if (mbi.State != MEM_FREE) continue;
        uint64_t rb = ((uint64_t)mbi.BaseAddress + gran - 1) & ~(gran - 1);
        uint64_t re = ((uint64_t)mbi.BaseAddress + mbi.RegionSize) & ~(gran - 1);
        rb = rb > lo ? rb : lo;
        re = re < hi ? re : hi;
        if (re > rb) left += (re - rb) / gran;
    }
    bool filled = !holdFails && left <= (uint64_t)leave;
    fprintf(rep, "%s crowded: %llu free granules within reach before, %llu after (asked %d), "
                 "%d reservations, %d failed\n",
            filled ? "ok  " : "FAIL", (unsigned long long)total, (unsigned long long)left, leave,
            nh, holdFails);
    fails += !filled;
    fails += nearCheckRequests(rep, "crowded", main, span, got);
    for (int i = 0; i < nh; i++) VirtualFree(holds[i], 0, MEM_RELEASE);
    g_nearTestOld = false;
    nearResetForTest();
    fprintf(rep, "%s\n", fails ? "FAIL" : "PASS");
    fclose(rep);
    return fails ? 1 : 0;
}

// Fault injection for the offline self-tests of the grouped installs
// (OkamiInstallFailSelfTest): writeProtected call number g_writeFailAt,
// counted from 0 since g_writeCount was last reset, fails, and with
// g_writeFailRest so does every call after it -- a rollback that cannot put
// the bytes back. -1 in the game, where this costs one compare.
static int g_writeFailAt = -1;
static bool g_writeFailRest = false;
static int g_writeCount = 0;
static bool g_faultLoop = false;  // inside an offline self-test's fault-injection loop

static bool writeProtected(void* dst, const void* src, size_t n) {
    DWORD old;
    if (g_writeFailAt >= 0) {
        int k = g_writeCount++;
        if (k == g_writeFailAt || (g_writeFailRest && k > g_writeFailAt)) {
            return false;
        }
    }
    if (g_writeFailAt >= 0 || g_faultLoop) {
        // Offline only: the fault-injection loops fail an install at each of its
        // writes in turn and put every site back before the next, so they write
        // the same sites of a main.dll nothing runs (DONT_RESOLVE_DLL_REFERENCES)
        // over and over: ~2.7 million writes to the world self-test's 948
        // sites, two protection changes each, 20 s of every world verifier run
        // (2026-09-25). A region is made writable once and left so.
        static uint8_t* rwLo[16];
        static uint8_t* rwHi[16];
        static int rwN = 0;
        uint8_t* d = (uint8_t*)dst;
        bool known = false;
        for (int i = 0; i < rwN && !known; i++) known = d >= rwLo[i] && d + n <= rwHi[i];
        MEMORY_BASIC_INFORMATION mbi;
        if (!known && rwN < 16 && VirtualQuery(dst, &mbi, sizeof(mbi)) &&
            d + n <= (uint8_t*)mbi.BaseAddress + mbi.RegionSize &&
            VirtualProtect(mbi.BaseAddress, mbi.RegionSize, PAGE_EXECUTE_READWRITE, &old)) {
            rwLo[rwN] = (uint8_t*)mbi.BaseAddress;
            rwHi[rwN] = rwLo[rwN] + mbi.RegionSize;
            rwN++;
            known = true;
        }
        if (known) {
            memcpy(dst, src, n);
            FlushInstructionCache(GetCurrentProcess(), dst, n);
            return true;
        }
    }
    if (!VirtualProtect(dst, n, PAGE_EXECUTE_READWRITE, &old)) {
        return false;
    }
    memcpy(dst, src, n);
    VirtualProtect(dst, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), dst, n);
    return true;
}

// One write of a group that has to go in whole (writeGroup).
struct GroupWrite {
    uint8_t* dst;
    const void* bytes;  // what goes in
    const void* orig;   // what was there
    size_t len;
};

// Write a group in order, or leave the code as it was: after a failed write,
// put back the ones already made, newest first. Returns how many stay in:
// n when every write went in, 0 when one failed and the rest were all put
// back. Anything between means a write could not be undone either. The undo
// stops there, so what stays is always a prefix, the first `ret` writes; each
// installer orders its group so that any prefix of it can be made harmless,
// and says how. Called with the other threads suspended: no allocation,
// locking or logging.
static int writeGroup(const GroupWrite* w, int n) {
    for (int i = 0; i < n; i++) {
        if (writeProtected(w[i].dst, w[i].bytes, w[i].len)) {
            continue;
        }
        while (i > 0 && writeProtected(w[i - 1].dst, w[i - 1].orig, w[i - 1].len)) {
            i--;
        }
        return i;
    }
    return n;
}

// The process's other threads, suspended while code they may be running is
// rewritten. Nothing between suspendOthers and resumeOthers may allocate, lock
// or log: a suspended thread can hold the heap lock or the log lock.
// SuspendThread only asks; GetThreadContext waits for the suspension to take
// effect, so every thread's stopping point is read here, into g_susRip.
static HANDLE g_susThreads[2048];
static DWORD64 g_susRip[2048];
static int g_susCount = 0;

static bool suspendOthers() {
    g_susCount = 0;
    if (g_faultLoop) {
        // Offline: nothing in a self-test's process runs main.dll, and a
        // snapshot of every thread on the machine for each of the ~1 900
        // installs of the world fault loop was 70 s a run (2026-09-25). The
        // install before the loop still suspends for real.
        return true;
    }
    bool all = true;
    DWORD pid = GetCurrentProcessId(), me = GetCurrentThreadId();
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snap == INVALID_HANDLE_VALUE) {
        return false;
    }
    THREADENTRY32 te;
    te.dwSize = sizeof(te);
    BOOL first = Thread32First(snap, &te);
    all &= first != FALSE;
    for (BOOL ok = first; ok; ok = Thread32Next(snap, &te)) {
        if (te.th32OwnerProcessID != pid || te.th32ThreadID == me) {
            continue;
        }
        if (g_susCount >= (int)(sizeof(g_susThreads) / sizeof(g_susThreads[0]))) {
            all = false;
            break;
        }
        HANDLE h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT, FALSE, te.th32ThreadID);
        if (!h) {
            all = false;
            continue;
        }
        if (SuspendThread(h) == (DWORD)-1) {
            all = false;
            CloseHandle(h);
            continue;
        }
        g_susThreads[g_susCount++] = h;
    }
    CloseHandle(snap);
    for (int i = 0; i < g_susCount; i++) {
        CONTEXT c;
        memset(&c, 0, sizeof(c));
        c.ContextFlags = CONTEXT_CONTROL;
        g_susRip[i] = GetThreadContext(g_susThreads[i], &c) ? c.Rip : 0;
        all &= g_susRip[i] != 0;
    }
    return all;
}

static void resumeOthers() {
    for (int i = 0; i < g_susCount; i++) {
        ResumeThread(g_susThreads[i]);
        CloseHandle(g_susThreads[i]);
    }
    g_susCount = 0;
}

// ---------------------------------------------------------------------------
// Shadow mode byte
//
// The mode byte is the stock game's own record of its tick rate: 2 in gameplay
// (30 Hz), 1 inside the options pages, the memory-card screens, the pause menu
// and the title (60 Hz). The fast modes pin it to 1, because every consumer
// reads it as "the engine ticks at 60 or more", and that throws the record
// away. The animation work needs it back: at 120 fps the right slowdown is 4x
// in gameplay but 2x in those menus.
//
// So the instructions that *maintain* the byte are pointed at a private shadow
// byte instead: the writes of a constant, the restores of a saved value, and
// the reads that save it for those restores. Each one changes in its rip
// displacement alone. The instructions that *consume* the byte keep reading the
// real, pinned one. The shadow then holds what the stock game's byte would hold,
// and in the game only the saves read it.
//
// One writer names no address: flower_startup's memset of the frame block
// zeroes the real byte. The instructions at its return point are moved into a
// stub that writes the same 0 to the shadow and puts the pinned 1 back in the
// real byte. The retargeted writer that follows used to be what restored it,
// and some consumers divide by the mode. The memset only runs at engine start
// (flower_startup(false); flower_tick's reset path passes true and skips it),
// which normally comes before this install, so the stub is for an install
// that wins that race. The log says if it ever runs.
//
// This replaces rewriting the `mov byte [mode], 2` immediates to 1, which stays
// as the fallback when the table does not match this main.dll. In 30 fps mode
// the original bytes go back and the real byte takes the shadow's value, so the
// stock game is exact. Both directions switch with the game's other threads
// suspended.
//
// src/shadow_mode.h is generated by tools/gen_shadow_mode.py.
// tools/verify_shadow_mode.py runs this install through
// OkamiShadowModeSelfTest and emulates the bytes it leaves against the
// originals.
// ---------------------------------------------------------------------------

#include "shadow_mode.h"

static constexpr int kShSites = (int)(sizeof(kShadowModeSites) / sizeof(kShadowModeSites[0]));
static constexpr int kShWindows =
    (int)(sizeof(kShadowModeZeroWindows) / sizeof(kShadowModeZeroWindows[0]));
// the cave: the shadow byte at the start and a byte each stub sets when it runs
// (the watcher logs and clears it), the stubs in the other half of the page, so
// writing either byte never touches a cache line that holds code
static constexpr size_t kShCaveSize = 4096;
static constexpr size_t kShStubOff = 2048;
static constexpr size_t kShStubSize = 64;

static uint8_t* g_shCave = nullptr;
static volatile uint8_t* g_shadowMode = nullptr;  // the stock game's mode byte
static uint8_t g_shSiteBytes[kShSites][16];       // each site, retargeted
static uint8_t g_shWindowBytes[kShWindows][16];   // each window: jmp stub, int3 fill
static bool g_shadowOk = false;                   // installed, switchable
static bool g_shadowOn = false;                   // the game runs the retargeted bytes

// rel32 from `next` (the end of the instruction) to `target`, if it reaches
static bool putRel32(const uint8_t* next, const void* target, uint8_t* field) {
    int64_t rel = (int64_t)(const uint8_t*)target - (int64_t)next;
    if (rel != (int32_t)rel) {
        return false;
    }
    int32_t r = (int32_t)rel;
    memcpy(field, &r, 4);
    return true;
}

// Checks every site, builds the stubs and the retargeted bytes. Writes nothing
// in main.dll: applyShadowMode does that.
static bool installShadowMode() {
    uint8_t* main = g_eng.main;
    if (!main || g_eng.modeByte != main + kShadowModeByteRva) {
        logf("shadow mode: the mode byte is not at main+%X in this build; keeping the"
             " immediate rewrite", kShadowModeByteRva);
        return false;
    }
    int bad = 0;
    for (int i = 0; i < kShSites; i++) {
        const ShadowModeSite& s = kShadowModeSites[i];
        bad += memcmp(main + s.rva, s.orig, s.len) != 0;
    }
    for (int i = 0; i < kShWindows; i++) {
        const ShadowModeZeroWindow& w = kShadowModeZeroWindows[i];
        bad += memcmp(main + w.rva, w.orig, w.len) != 0;
    }
    if (bad) {
        logf("shadow mode: %d of %d sites do not hold the bytes of main.dll sha1 %s; nothing"
             " retargeted, keeping the immediate rewrite", bad, kShSites + kShWindows,
             SHADOW_MODE_MAIN_SHA1);
        return false;
    }
    uint8_t* cave = allocNear(main, kShCaveSize);
    if (!cave) {
        logf("shadow mode: no cave near main.dll; keeping the immediate rewrite");
        return false;
    }
    cave[0] = *(volatile uint8_t*)g_eng.modeByte;
    bool ok = true;
    for (int i = 0; i < kShSites; i++) {
        const ShadowModeSite& s = kShadowModeSites[i];
        memcpy(g_shSiteBytes[i], s.orig, s.len);
        ok &= putRel32(main + s.rva + s.len, cave, g_shSiteBytes[i] + s.dispOff);
    }
    for (int i = 0; i < kShWindows; i++) {
        const ShadowModeZeroWindow& w = kShadowModeZeroWindows[i];
        uint8_t* site = main + w.rva;
        uint8_t* stub = cave + kShStubOff + (size_t)i * kShStubSize;
        uint8_t* q = stub;
        // mov byte [rip+shadow], 0 -- what the memset just wrote to the real byte
        q[0] = 0xC6;
        q[1] = 0x05;
        ok &= putRel32(q + 7, cave, q + 2);
        q[6] = 0x00;
        q += 7;
        // mov byte [rip+mode], 1 -- the real byte stays pinned
        q[0] = 0xC6;
        q[1] = 0x05;
        ok &= putRel32(q + 7, g_eng.modeByte, q + 2);
        q[6] = 0x01;
        q += 7;
        // mov byte [rip+ran], 1 -- for the log (a mov: the flags stay the game's)
        q[0] = 0xC6;
        q[1] = 0x05;
        ok &= putRel32(q + 7, cave + 1, q + 2);
        q[6] = 0x01;
        q += 7;
        // the window's instructions, their rip operands aimed where they were
        memcpy(q, w.orig, w.len);
        for (int f = 0; f < w.nFix; f++) {
            int32_t d;
            memcpy(&d, w.orig + w.fix[f][0], 4);
            ok &= putRel32(q + w.fix[f][1], site + w.fix[f][1] + d, q + w.fix[f][0]);
        }
        q += w.len;
        // jmp back
        q[0] = 0xE9;
        ok &= putRel32(q + 5, site + w.len, q + 1);
        memset(g_shWindowBytes[i], 0xCC, sizeof(g_shWindowBytes[i]));
        g_shWindowBytes[i][0] = 0xE9;
        ok &= putRel32(site + 5, stub, g_shWindowBytes[i] + 1);
    }
    FlushInstructionCache(GetCurrentProcess(), cave, kShCaveSize);
    if (!ok) {
        logf("shadow mode: the cave at %p is out of rel32 reach of main.dll; keeping the"
             " immediate rewrite", (void*)cave);
        return false;
    }
    g_shCave = cave;
    g_shadowMode = cave;
    g_shadowOk = true;
    logf("shadow mode: %d instructions and %d memset return point(s) ready, shadow byte at %p",
         kShSites, kShWindows, (void*)cave);
    return true;
}

// Point the maintaining instructions at the shadow (on) or give them back the
// real byte (off), and hand the context over in the same instant. Going on,
// the shadow takes the real byte's value and the real byte is pinned to 1;
// going off, the real byte takes the shadow's value. The other threads are
// suspended throughout, so no instruction runs half-written and no game write
// falls between the copy and the switch. Returns false if nothing changed.
static bool applyShadowMode(bool on) {
    if (!g_shadowOk) {
        return false;
    }
    if (on == g_shadowOn) {
        return true;
    }
    uint8_t* main = g_eng.main;
    volatile uint8_t* real = g_eng.modeByte;
    for (int attempt = 0; attempt < 200; attempt++) {
        suspendOthers();
        // A thread stopped past the first instruction of a window would resume
        // in the middle of the jump. Only possible going on: once the jump is
        // in, the int3 fill after it is never reached.
        bool inside = false;
        for (int t = 0; on && t < g_susCount; t++) {
            for (int i = 0; i < kShWindows; i++) {
                const uint8_t* w = main + kShadowModeZeroWindows[i].rva;
                if (g_susRip[t] > (DWORD64)w &&
                    g_susRip[t] < (DWORD64)(w + kShadowModeZeroWindows[i].len)) {
                    inside = true;
                }
            }
        }
        if (inside) {
            resumeOthers();
            Sleep(1);
            continue;
        }
        int failed = 0;
        if (on) {
            *g_shadowMode = *real;
        }
        for (int i = 0; i < kShSites; i++) {
            const ShadowModeSite& s = kShadowModeSites[i];
            failed += !writeProtected(main + s.rva, on ? g_shSiteBytes[i] : s.orig, s.len);
        }
        for (int i = 0; i < kShWindows; i++) {
            const ShadowModeZeroWindow& w = kShadowModeZeroWindows[i];
            failed += !writeProtected(main + w.rva, on ? g_shWindowBytes[i] : w.orig, w.len);
        }
        *real = on ? (uint8_t)1 : *g_shadowMode;
        resumeOthers();
        g_shadowOn = on;
        if (failed) {
            logf("shadow mode: %d of %d sites could not be written switching %s", failed,
                 kShSites + kShWindows, on ? "on" : "off");
        }
        return true;
    }
    logf("shadow mode: a thread stayed inside a memset return window; not switched on");
    return false;
}

// Offline self-test, driven by tools/verify_shadow_mode.py without the game:
// maps main.dll into the calling process (DONT_RESOLVE_DLL_REFERENCES: no
// DllMain, no imports, nothing of the game runs), finds the mode byte the way
// the game path does, installs, and switches on, off and on again, writing the
// bytes each step leaves so the script can emulate them against the originals.
// Returns 0 on success; failures are also written to report.txt.
extern "C" __declspec(dllexport) int OkamiShadowModeSelfTest(const char* mainPath,
                                                             const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    int fails = 0;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    if (!tick || !resolveFrameConfig(tick) || !installShadowMode()) {
        fprintf(rep, "FAIL load, resolve or install (see okami_hackfix.log)\n");
        fclose(rep);
        return 1;
    }
    volatile uint8_t* real = g_eng.modeByte;
    fprintf(rep, "main %p\nmode %p\nshadow %p\n", (void*)m, (void*)real, (void*)g_shadowMode);
    for (int i = 0; i < kShWindows; i++) {
        fprintf(rep, "stub %X %p\n", kShadowModeZeroWindows[i].rva,
                (void*)(g_shCave + kShStubOff + (size_t)i * kShStubSize));
    }
    // every site's bytes, then every window's, as main.dll holds them now
    auto dump = [&](const char* name) {
        snprintf(path, sizeof(path), "%s\\%s", outDir, name);
        if (FILE* f = fopen(path, "wb")) {
            for (int i = 0; i < kShSites; i++) {
                fwrite(g_eng.main + kShadowModeSites[i].rva, 1, kShadowModeSites[i].len, f);
            }
            for (int i = 0; i < kShWindows; i++) {
                fwrite(g_eng.main + kShadowModeZeroWindows[i].rva, 1,
                       kShadowModeZeroWindows[i].len, f);
            }
            fclose(f);
        }
    };
    auto check = [&](bool ok, const char* what) {
        fprintf(rep, "%s %s\n", ok ? "ok" : "FAIL", what);
        fails += ok ? 0 : 1;
    };
    // on, from a gameplay context: the shadow takes 2, the real byte is pinned
    *real = 2;
    check(applyShadowMode(true) && g_shadowOn, "switch on");
    check(*g_shadowMode == 2 && *real == 1, "on: shadow took the real byte's 2, real pinned 1");
    dump("on.bin");
    snprintf(path, sizeof(path), "%s\\cave.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fwrite(g_shCave, 1, kShCaveSize, f);
        fclose(f);
    }
    // a menu moved the stock context to 60 Hz; going off hands that to the real byte
    *g_shadowMode = 1;
    *real = 1;
    check(applyShadowMode(false) && !g_shadowOn, "switch off");
    check(*real == 1, "off: real took the shadow's 1");
    bool orig = true;
    for (int i = 0; i < kShSites; i++) {
        orig &= memcmp(g_eng.main + kShadowModeSites[i].rva, kShadowModeSites[i].orig,
                       kShadowModeSites[i].len) == 0;
    }
    for (int i = 0; i < kShWindows; i++) {
        orig &= memcmp(g_eng.main + kShadowModeZeroWindows[i].rva, kShadowModeZeroWindows[i].orig,
                       kShadowModeZeroWindows[i].len) == 0;
    }
    check(orig, "off: every site holds its original bytes");
    dump("off.bin");
    // off again changes nothing; on again from the stock game's 2
    *real = 2;
    check(applyShadowMode(false) && *real == 2, "off twice: nothing moves");
    check(applyShadowMode(true) && *g_shadowMode == 2 && *real == 1, "on again");
    dump("on2.bin");
    fprintf(rep, "%s\n", fails ? "FAILED" : "PASS");
    fclose(rep);
    return fails ? 1 : 0;
}

// Copy a displaced instruction into the code cave, repointing it if it
// addresses memory relative to rip.
//
// The cave is wherever allocNear happened to find a free page, so a
// displacement that was correct at the original site addresses something else
// entirely once the instruction moves. Every site patched before this session
// used [reg+disp32], which relocates unchanged, so this never came up. The
// airborne acceleration site added last session is
//
//     main+3B547C   mulss xmm0, [rip+0x7B57B4]      ; the time scale
//
// and copying it verbatim pointed it at whatever lay 8 MB past the cave rather
// than at the time scale. The detour then multiplied the airborne acceleration
// by an arbitrary float instead of by ts -- near enough to zero that Amaterasu
// lost all horizontal control the instant she left the ground. The fix it was
// supposed to apply never ran at all; what the test measured was this.
//
// ModRM mod=00 rm=101 is the rip-relative form, and in 64-bit mode it is the
// only one, so finding the ModRM byte is enough to detect it.
static bool copyDisplaced(uint8_t* dst, const uint8_t* orig, size_t origLen, const uint8_t* site) {
    memcpy(dst, orig, origLen);
    size_t i = 0;
    while (i < origLen && (orig[i] == 0xF2 || orig[i] == 0xF3 || orig[i] == 0x66)) {
        i++;  // mandatory SSE prefix
    }
    if (i < origLen && (orig[i] & 0xF0) == 0x40) {
        i++;  // REX
    }
    if (i < origLen && orig[i] == 0x0F) {
        i++;  // two-byte opcode escape
    }
    i++;  // the opcode byte itself
    if (i >= origLen) {
        return true;  // no ModRM to look at
    }
    uint8_t modrm = orig[i];
    if ((modrm >> 6) != 0 || (modrm & 7) != 5) {
        return true;  // register or [reg+disp] form, safe to move as-is
    }
    size_t dispAt = i + 1;
    if (dispAt + 4 != origLen) {
        return false;  // rip-relative with a trailing immediate; not handled
    }
    int32_t disp;
    memcpy(&disp, orig + dispAt, 4);
    const uint8_t* target = site + origLen + disp;
    int64_t rel = (int64_t)target - (int64_t)(dst + origLen);
    if (rel != (int32_t)rel) {
        return false;
    }
    int32_t rel32 = (int32_t)rel;
    memcpy(dst + dispAt, &rel32, 4);
    return true;
}

// Build "mulss <xmmReg>, [scale]; <displaced bytes>; jmp back" in the cave and
// patch `patchLen` bytes at the site with a jump to it.
static bool installScaleDetour(uint8_t*& caveCur, uint8_t* caveEnd, uint32_t siteRva,
                               uint32_t resumeRva, const uint8_t* orig, size_t origLen,
                               int xmmReg, float* scale, const char* what,
                               bool scaleAfter = false) {
    uint8_t* site = g_eng.main + siteRva;
    if (memcmp(site, orig, origLen) != 0) {
        if (what) {
            logf("%s: main+%X does not hold the expected instruction, not patched", what, siteRva);
        }
        return false;
    }
    if ((size_t)(caveEnd - caveCur) < origLen + 32) {
        if (what) {
            logf("%s: code cave full", what);
        }
        return false;
    }
    uint8_t* code = caveCur;
    size_t n = 0;
    // the displaced instruction runs first when it loads the register we scale
    if (scaleAfter) {
        if (!copyDisplaced(code + n, orig, origLen, site)) {
            if (what) {
                logf("%s: main+%X cannot be relocated into the cave, not patched", what, siteRva);
            }
            return false;
        }
        n += origLen;
    }
    code[n++] = 0xF3;
    code[n++] = 0x0F;
    code[n++] = 0x59;                        // mulss xmmReg, [rip+disp32]
    code[n++] = (uint8_t)(0x05 | (xmmReg << 3));
    int32_t dataDisp = (int32_t)((uint8_t*)scale - (code + n + 4));
    memcpy(code + n, &dataDisp, 4);
    n += 4;
    if (!scaleAfter) {
        if (!copyDisplaced(code + n, orig, origLen, site)) {
            if (what) {
                logf("%s: main+%X cannot be relocated into the cave, not patched", what, siteRva);
            }
            return false;
        }
        n += origLen;
    }
    code[n++] = 0xE9;
    int32_t backDisp = (int32_t)((int64_t)(g_eng.main + resumeRva) - (int64_t)(code + n + 4));
    memcpy(code + n, &backDisp, 4);
    n += 4;
    caveCur = code + ((n + 15) & ~(size_t)15);

    uint8_t patch[16];
    memset(patch, 0x90, sizeof(patch));
    patch[0] = 0xE9;
    int64_t rel = (int64_t)code - (int64_t)(site + 5);
    if (rel != (int32_t)rel) {
        if (what) {
            logf("%s: cave out of reach", what);
        }
        return false;
    }
    int32_t rel32 = (int32_t)rel;
    memcpy(patch + 1, &rel32, 4);
    if (!writeProtected(site, patch, origLen)) {
        if (what) {
            logf("%s: could not write the detour at main+%X", what, siteRva);
        }
        return false;
    }
    if (what) {
        logf("%s: installed at main+%X", what, siteRva);
    }
    return true;
}

// The stick drift's detours (see kStickDriftSites): the multiply by the
// 1/1024 stick constant is relocated, then scaled by the gain in *scale.
static int g_stickDriftDone = 0;
static void installStickDrift(uint8_t*& cur, uint8_t* end, float* scale) {
    // the exact gain needs the k the three copies decay by
    float k = *(const float*)(g_eng.main + kStickDriftKRva);
    const int drifts = (int)(sizeof(kStickDriftSites) / sizeof(kStickDriftSites[0]));
    if (k != 0.86f) {
        logf("stick drift: main+%X holds %g, not the audited 0.86, not patched", kStickDriftKRva,
             (double)k);
        return;
    }
    g_stickDriftK = k;
    g_stickDriftDone = 0;
    for (int i = 0; i < drifts; i++) {
        // xmm0 holds |stick| * 1.7 once the displaced multiply has run
        if (installScaleDetour(cur, end, kStickDriftSites[i][0], kStickDriftSites[i][1],
                               kStickDriftOrig[i], sizeof(kStickDriftOrig[i]), 0, scale, nullptr,
                               /*scaleAfter=*/true)) {
            g_stickDriftDone++;
        }
    }
    logf("stick drift: %d of %d sites scaled by ts(1-k^ts)/(1-k), k = %.2f (wall recoil 0x2B,"
         " 0x2C, 0x48)", g_stickDriftDone, drifts, (double)k);
}

// Draw distance (ini DrawDistance: 1 = stock, up to 6)
//
// A placed model (cModel and every class under it: the scenery objects, grass
// tufts, cObjBase) is drawn while its view depth (3E5F50: the camera-space z of
// its position) is at most its own limit +D72 (1000 for most, 5000 for some,
// +100 more for cObjBase), and it fades out over the last +D74 of that (20C620,
// vtable slot 1 of 780 classes). DrawDistance = k multiplies the limit where
// these read it, so objects are drawn, fade out and keep updating out to k
// times their distance. Every reader of +D72 in the game was read by hand
// (tools/verify_draw_distance.py re-scans for them): these eight scale; the
// other ten stay as shipped: copies of a parent's limit into a child (27324C,
// 3899AA, 3903F3; scaling them would square k), a floor of 2000 (5AB731), the
// fade width's setup (207F21), and sound and activity ranges (21BF18, 21C04F,
// 22C673, 22DA94, 2FE54C).
static const uint32_t kDrawDistanceSites[][2] = {
    {0x20AD54, 0x20AD5B},  // cModel's cull (vtable slot 5, 20AC70): cmp ax, word [rbx+D72]
    {0x20F245, 0x20F24C},  // cObjBase's cull (20F1D0): movsx ecx, word [rbx+D72], +100
    {0x5F69A2, 0x5F69A9},  // its copy (5F6950)
    {0x20C6CB, 0x20C6D2},  // the fade band (20C620): movsx edx, word [rbx+D72]
    {0x20C7BB, 0x20C7C3},  // 20C620's draw registration and LOD depth: movsx r9d
    {0x213D7B, 0x213D83},  // ut04's own fade band (213D50): movsx r8d
    {0x2E337D, 0x2E3384},  // et08's update, run while within the limit: movzx eax
    {0x227A45, 0x227A4C},  // a near/far state +110A (227A0C): cmp ax, word [rdi+D72]
};
static const uint8_t kDrawDistanceOrig[][8] = {
    {0x66, 0x3B, 0x83, 0x72, 0x0D, 0x00, 0x00},
    {0x0F, 0xBF, 0x8B, 0x72, 0x0D, 0x00, 0x00},
    {0x0F, 0xBF, 0x8B, 0x72, 0x0D, 0x00, 0x00},
    {0x0F, 0xBF, 0x93, 0x72, 0x0D, 0x00, 0x00},
    {0x44, 0x0F, 0xBF, 0x8B, 0x72, 0x0D, 0x00, 0x00},
    {0x44, 0x0F, 0xBF, 0x83, 0x72, 0x0D, 0x00, 0x00},
    {0x0F, 0xB7, 0x87, 0x72, 0x0D, 0x00, 0x00},
    {0x66, 0x3B, 0x87, 0x72, 0x0D, 0x00, 0x00},
};
static int32_t* g_drawFactor = nullptr;  // the k the stubs multiply by
static int g_drawDistanceDone = 0;

// One stub per site, then a jump back:
//   movsx r32, word [B+D72]   as shipped, then imul r32, dword [k]: the 32-bit
//                             compares after it see D72 * k;
//   movzx eax, word [B+D72]   as shipped, then imul eax, [k], capped at 0x7FFF
//                             for the 16-bit compare that reads ax next;
//   cmp ax, word [B+D72]      push rcx; movsx ecx, word [B+D72]; imul ecx, [k];
//                             clamped to [-0x8000, 0x7FFF]; cmp ax, cx; pop rcx:
//                             the shipped compare's flags against D72 * k.
// The flags a load stub's imul leaves are dead: at each of those sites the next
// flag writer comes before any reader (tools/verify_draw_distance.py checks it).
static size_t emitDrawStub(uint8_t* code, const uint8_t* orig, size_t len) {
    size_t n = 0;
    auto rel32 = [&](const void* target) {
        int32_t d = (int32_t)((const uint8_t*)target - (code + n + 4));
        memcpy(code + n, &d, 4);
        n += 4;
    };
    if (len == 7 && orig[0] == 0x66 && orig[1] == 0x3B) {
        uint8_t modrm = orig[2];
        if ((modrm & 0xC0) != 0x80 || (modrm & 0x38) != 0 || (modrm & 7) == 1 || (modrm & 7) == 4) {
            return 0;
        }
        code[n++] = 0x51;                                     // push rcx
        code[n++] = 0x0F;
        code[n++] = 0xBF;
        code[n++] = (uint8_t)((modrm & 0xC7) | 0x08);         // movsx ecx, word [B+disp]
        memcpy(code + n, orig + 3, 4);
        n += 4;
        code[n++] = 0x0F;
        code[n++] = 0xAF;
        code[n++] = 0x0D;                                     // imul ecx, [rip+k]
        rel32(g_drawFactor);
        static const uint8_t clamp[] = {
            0x81, 0xF9, 0xFF, 0x7F, 0x00, 0x00,  // cmp ecx, 0x7FFF
            0x7E, 0x05,                          // jle +5
            0xB9, 0xFF, 0x7F, 0x00, 0x00,        // mov ecx, 0x7FFF
            0x81, 0xF9, 0x00, 0x80, 0xFF, 0xFF,  // cmp ecx, -0x8000
            0x7D, 0x05,                          // jge +5
            0xB9, 0x00, 0x80, 0xFF, 0xFF,        // mov ecx, -0x8000
            0x66, 0x39, 0xC8,                    // cmp ax, cx
            0x59,                                // pop rcx
        };
        memcpy(code + n, clamp, sizeof(clamp));
        n += sizeof(clamp);
        return n;
    }
    size_t op = orig[0] == 0x44 ? 1 : 0;
    if (len != 7 + op || orig[op] != 0x0F || (orig[op + 1] != 0xBF && orig[op + 1] != 0xB7) ||
        (orig[op + 2] & 0xC0) != 0x80 || (orig[op + 2] & 7) == 4) {
        return 0;
    }
    bool zx = orig[op + 1] == 0xB7;
    int reg = ((orig[op + 2] >> 3) & 7) + (op ? 8 : 0);
    if (zx && reg != 0) {
        return 0;  // the cap below is written for eax
    }
    memcpy(code, orig, len);                                  // the load, as shipped
    n = len;
    if (reg >= 8) {
        code[n++] = 0x44;
    }
    code[n++] = 0x0F;
    code[n++] = 0xAF;
    code[n++] = (uint8_t)(((reg & 7) << 3) | 5);              // imul r32, [rip+k]
    rel32(g_drawFactor);
    if (zx) {
        static const uint8_t cap[] = {
            0x3D, 0xFF, 0x7F, 0x00, 0x00,  // cmp eax, 0x7FFF
            0x76, 0x05,                    // jbe +5
            0xB8, 0xFF, 0x7F, 0x00, 0x00,  // mov eax, 0x7FFF
        };
        memcpy(code + n, cap, sizeof(cap));
        n += sizeof(cap);
    }
    return n;
}

// All eight or none: a cull scaled without its fade band (or the reverse)
// would pop objects in at a distance again.
static void installDrawDistanceSites(uint8_t* cave, size_t caveSize, int k) {
    const int sites = (int)(sizeof(kDrawDistanceSites) / sizeof(kDrawDistanceSites[0]));
    g_drawDistanceDone = 0;
    g_drawFactor = (int32_t*)cave;
    *g_drawFactor = k;
    for (int i = 0; i < sites; i++) {
        size_t len = kDrawDistanceSites[i][1] - kDrawDistanceSites[i][0];
        if (memcmp(g_eng.main + kDrawDistanceSites[i][0], kDrawDistanceOrig[i], len) != 0) {
            logf("draw distance: main+%X does not hold the expected instruction, nothing patched",
                 kDrawDistanceSites[i][0]);
            return;
        }
    }
    uint8_t* cur = cave + 16;
    uint8_t* stubs[sizeof(kDrawDistanceSites) / sizeof(kDrawDistanceSites[0])];
    for (int i = 0; i < sites; i++) {
        size_t len = kDrawDistanceSites[i][1] - kDrawDistanceSites[i][0];
        if ((size_t)(cave + caveSize - cur) < 96) {
            logf("draw distance: code cave full, nothing patched");
            return;
        }
        size_t n = emitDrawStub(cur, kDrawDistanceOrig[i], len);
        if (n == 0) {
            logf("draw distance: main+%X has no stub shape, nothing patched",
                 kDrawDistanceSites[i][0]);
            return;
        }
        cur[n++] = 0xE9;
        int32_t back = (int32_t)((int64_t)(g_eng.main + kDrawDistanceSites[i][1]) -
                                 (int64_t)(cur + n + 4));
        memcpy(cur + n, &back, 4);
        n += 4;
        int64_t rel = (int64_t)cur - (int64_t)(g_eng.main + kDrawDistanceSites[i][0] + 5);
        if (rel != (int32_t)rel) {
            logf("draw distance: cave out of reach, nothing patched");
            return;
        }
        stubs[i] = cur;
        cur += (n + 15) & ~(size_t)15;
    }
    for (int i = 0; i < sites; i++) {
        uint8_t* site = g_eng.main + kDrawDistanceSites[i][0];
        size_t len = kDrawDistanceSites[i][1] - kDrawDistanceSites[i][0];
        uint8_t patch[8];
        memset(patch, 0x90, sizeof(patch));
        patch[0] = 0xE9;
        int32_t rel32 = (int32_t)((int64_t)stubs[i] - (int64_t)(site + 5));
        memcpy(patch + 1, &rel32, 4);
        if (!writeProtected(site, patch, len)) {
            logf("draw distance: could not write main+%X (%d of %d written)",
                 kDrawDistanceSites[i][0], g_drawDistanceDone, sites);
            return;
        }
        g_drawDistanceDone++;
    }
    logf("draw distance: x%d, %d of %d sites (placed objects are drawn, fade out and keep"
         " updating out to %d times their distance)", k, g_drawDistanceDone, sites, k);
}

static void installDrawDistance() {
    if (g_cfg.drawDistance <= 1) {
        logf("draw distance: stock (DrawDistance=1)");
        return;
    }
    uint8_t* cave = allocNear(g_eng.main, 4096);
    if (!cave) {
        logf("draw distance: no code cave near main.dll, not patched");
        return;
    }
    installDrawDistanceSites(cave, 4096, g_cfg.drawDistance);
}

// f(ts) = ts (1 - k^ts) / (1 - k) while on; 1, the shipped code, otherwise.
static float stickDriftGain(bool on, float ts) {
    float k = g_stickDriftK;
    if (!on || !(k > 0.0f) || !(ts > 0.05f && ts < 0.999f)) {
        return 1.0f;
    }
    return ts * (1.0f - powf(k, ts)) / (1.0f - k);
}

static void updateStickDrift(bool on, float ts) {
    if (!g_driftScale) {
        return;
    }
    float want = stickDriftGain(on, ts);
    if (*g_driftScale != want) {
        *g_driftScale = want;
    }
}


// `comiss xmm0, [rdi+0xE48]` -> load the field, divide it by the time scale,
// and compare against the untouched constant. Dividing the field rather than
// scaling the constant leaves xmm0 alone, because this constant is also handed
// to FUN_1804ba080 as an animation blend length a few instructions later.
static bool installJumpPickDetour(uint8_t*& caveCur, uint8_t* caveEnd) {
    uint8_t* site = g_eng.main + kJumpPickRva;
    if (memcmp(site, kJumpPickOrig, sizeof(kJumpPickOrig)) != 0) {
        logf("jump variant select: main+%X does not hold the expected instruction", kJumpPickRva);
        return false;
    }
    if ((size_t)(caveEnd - caveCur) < 32) {
        return false;
    }
    uint8_t* code = caveCur;
    size_t n = 0;
    const uint8_t load[8] = {0xF3, 0x0F, 0x10, 0x8F, 0x48, 0x0E, 0x00, 0x00};  // movss xmm1,[rdi+E48]
    memcpy(code + n, load, sizeof(load));
    n += sizeof(load);
    code[n++] = 0xF3;
    code[n++] = 0x0F;
    code[n++] = 0x59;
    code[n++] = 0x0D;  // mulss xmm1, [rip+disp32]
    int32_t dataDisp = (int32_t)((uint8_t*)g_gateInvScale - (code + n + 4));
    memcpy(code + n, &dataDisp, 4);
    n += 4;
    code[n++] = 0x0F;
    code[n++] = 0x2F;
    code[n++] = 0xC1;  // comiss xmm0, xmm1
    code[n++] = 0xE9;
    int32_t backDisp =
        (int32_t)((int64_t)(g_eng.main + kJumpPickResume) - (int64_t)(code + n + 4));
    memcpy(code + n, &backDisp, 4);
    n += 4;
    caveCur = code + ((n + 15) & ~(size_t)15);

    uint8_t patch[sizeof(kJumpPickOrig)];
    memset(patch, 0x90, sizeof(patch));
    patch[0] = 0xE9;
    int64_t rel = (int64_t)code - (int64_t)(site + 5);
    if (rel != (int32_t)rel) {
        return false;
    }
    int32_t rel32 = (int32_t)rel;
    memcpy(patch + 1, &rel32, 4);
    return writeProtected(site, patch, sizeof(patch));
}

// Set by the experimental 120 fps ladder further down; the action timers need
// to know how many ticks now make up one 30 fps step.
static bool g_fpsImmsOk = false;
static bool g_fpsImmsFast = false;

// The time scale the patch has configured, which is NOT the same thing as the
// time scale the engine is currently running on.
//
// main+0xB6AC38 is written every frame by flower_tick from an immediate, and
// the 120 fps ladder works by rewriting that immediate -- so the global still
// holds the previous mode's value until the game ticks once more. Anything that
// reads the global inside the toggle therefore sees a value one frame stale and
// derives its constants for the mode the game has just left. In the log:
//
//     [79.671] frame ladder -> 120 fps (timeScale 0.25, shift 2)
//     [79.671] mode constants -> k^1.00 applied to 60 damping entries
//     [79.682] mode constants -> k^0.25 applied to 60 damping entries
//
// For those 11 ms every damping constant in the game held its 30 fps value
// while the game ran at 120, and the jog block held its unscaled target -- a
// four-times-too-high speed target for a tick or two after every toggle.
//
// The ladder's own state says what the engine is about to run at, with no lag,
// so derive it from there. It is the same number, one frame earlier.
static float patchTimeScale() {
    if (!g_fps60) {
        return 1.0f;
    }
    return g_fpsImmsFast ? 0.25f : 0.5f;
}

// ---------------------------------------------------------------------------
// Action timers at 60 fps
//
// The port compensates for 60 fps in two ways: it multiplies per-tick
// quantities by the time scale, and it doubles durations by shifting them with
// the 60 fps flag. Every one of the 318 shift sites feeds cPad::ActSet, so the
// input windows are compensated and *no object state duration is*. Every
// action in the game whose length is a tick count therefore runs twice as fast
// at 60 fps: attack and recovery windows, stagger, invulnerability, the pause
// before a jump launches and the float after it.
//
// Those durations live in three adjacent fields of the shared character object
// and are always counted down the same way:
//
//     movzx eax, word ptr [rsi+0xE3C]
//     test  ax, ax
//     je    done
//     dec   ax                          <- 3 bytes
//     mov   word ptr [rsi+0xE3C], ax    <- 7 bytes
//
// Doubling every seed is not practical -- most are registers or unpacked from
// data -- but skipping the decrement on alternate ticks makes every one of
// these timers last twice as many ticks, which is the same real time at 60 fps
// as at 30. It also gets the boundaries right for free: hand-doubling the
// jump's two seeds needed 2*N for one window and 2*(N-1)+1 for the other,
// because they test the timer on opposite sides of the decrement, and getting
// that wrong was a visible 9% error in jump height.
//
// The patch goes on the decrement rather than the store, so the register and
// the field stay in step -- 72 of the sites go on to use the register. Parity
// comes from the engine's own tick counter, so the stub needs no per-frame
// upkeep, and a mask byte switches the whole thing off in one write.
//
// src/action_timers.h is generated by tools/find_action_timers.py.
// ---------------------------------------------------------------------------

#include "action_timers.h"

static uint8_t* g_timerMask = nullptr;  // 1 while the fix is active, 0 when not
static int g_timerPatched = 0;
static volatile LONG g_timerFixMuted = 0;  // set by the timer toggle key, for A/B

static void installActionTimers() {
    if (!g_cfg.fixActionTimers || !g_eng.main) {
        return;
    }
    if (!g_eng.frameCounter) {
        logf("action timers: tick counter not resolved, not patched");
        return;
    }
    const int total = (int)(sizeof(kTimerSites) / sizeof(kTimerSites[0]));
    const size_t kStub = 48;  // worst case is 40 bytes, rounded up for alignment
    size_t need = 64 + kStub * (size_t)total;
    uint8_t* cave = allocNear(g_eng.main, need);
    if (!cave) {
        logf("action timers: no code cave near main.dll, not patched");
        return;
    }
    g_timerMask = cave;
    *g_timerMask = 0;
    uint8_t* cur = cave + 64;
    uint8_t* end = cave + need;
    int mismatched = 0;
    for (int i = 0; i < total; i++) {
        const TimerSite& t = kTimerSites[i];
        uint8_t* site = g_eng.main + t.rva;
        if (memcmp(site, t.orig, t.len) != 0) {
            mismatched++;
            continue;
        }
        if ((size_t)(end - cur) < kStub) {
            mismatched++;
            continue;
        }
        uint8_t* code = cur;
        size_t n = 0;
        code[n++] = 0x9C;  // pushfq          -- the displaced store preserves flags,
        code[n++] = 0x50;  // push rax           so the test must not disturb them
        code[n++] = 0x8A;  // mov al, byte ptr [rip+tickCounter]
        code[n++] = 0x05;
        int32_t disp = (int32_t)((uint8_t*)g_eng.frameCounter - (code + n + 4));
        memcpy(code + n, &disp, 4);
        n += 4;
        code[n++] = 0x22;  // and al, byte ptr [rip+mask]  -- 0 when off, so ZF is
        code[n++] = 0x05;  //                                 set and we never skip
        disp = (int32_t)(g_timerMask - (code + n + 4));
        memcpy(code + n, &disp, 4);
        n += 4;
        code[n++] = 0x58;  // pop rax  -- does not touch the flags the `and` set
        code[n++] = 0x75;  // jnz skip
        size_t skipFixup = n;
        code[n++] = 0;
        code[n++] = 0x9D;  // popfq
        memcpy(code + n, t.orig, t.len);  // the decrement and its store
        n += t.len;
        code[n++] = 0xE9;
        int32_t back = (int32_t)((int64_t)(site + t.len) - (int64_t)(code + n + 4));
        memcpy(code + n, &back, 4);
        n += 4;
        code[skipFixup] = (uint8_t)(n - skipFixup - 1);
        code[n++] = 0x9D;  // popfq
        code[n++] = 0xE9;
        back = (int32_t)((int64_t)(site + t.len) - (int64_t)(code + n + 4));
        memcpy(code + n, &back, 4);
        n += 4;

        int64_t rel = (int64_t)code - (int64_t)(site + 5);
        if (rel != (int32_t)rel) {
            mismatched++;
            continue;
        }
        uint8_t patch[16];
        memset(patch, 0x90, sizeof(patch));
        patch[0] = 0xE9;
        int32_t rel32 = (int32_t)rel;
        memcpy(patch + 1, &rel32, 4);
        if (!writeProtected(site, patch, t.len)) {
            mismatched++;
            continue;
        }
        cur = code + ((n + 15) & ~(size_t)15);
        g_timerPatched++;
    }
    if (mismatched) {
        logf("action timers: %d of %d sites patched, %d did not match this build",
             g_timerPatched, total, mismatched);
    } else {
        logf("action timers: all %d sites patched", g_timerPatched);
    }
}

// Called from the watcher: the timers run at half rate only in 60 fps mode.
static void updateActionTimers() {
    if (!g_timerMask) {
        return;
    }
    // the stub skips the decrement whenever (tick & mask) is non-zero, so a
    // mask of 1 counts down every other tick and 3 every fourth
    uint8_t mask = 0;
    if (g_cfg.fixActionTimers && g_fps60 && !g_timerFixMuted) {
        mask = g_fpsImmsFast ? 3 : 1;
    }
    if (*g_timerMask != mask) {
        *g_timerMask = mask;
        logf("action timers -> %s", mask ? "real time" : "stock (fast at 60 fps)");
    }
}

// ---------------------------------------------------------------------------
// The memory-operand half of the same countdown
//
// The table above is only the register form. When the compiler has no further
// use for the value it counts straight against memory and there is no load and
// no store to recognise:
//
//     dec   word ptr [rsi+0xE3C]
//     cmp   word ptr [rsi+0xE3C], 0
//     jg    still_running
//     inc   byte ptr [rsi+0xE36]      ... otherwise advance the sub-state
//
// That is another 423 sites over five duration fields, a third of them
// counting up toward a limit rather than down, and it is why so much of the
// game still ran at double speed with the register form alone.
//
// The flags need more care here, because the counter *is* the flag producer:
// 159 of these are a `dec` read directly by `jne`, plus a few `jns` and `je`.
// Restoring the flags the site was entered with would be meaningless, but the
// answer every one of those consumers wants on a skipped tick is the same --
// "not finished yet" -- so the skip path publishes exactly that with
// `test rsp, rsp`, which sets ZF=0 and SF=0 (rsp is never zero, and bit 63 is
// never set in user mode) and leaves the field alone. A timer sitting at zero
// therefore survives one more tick and expires on the next real decrement,
// which is the one-tick-later behaviour the fix exists to produce.
//
// src/memory_timers.h is generated by tools/find_memory_timers.py.
// ---------------------------------------------------------------------------

#include "memory_timers.h"

static int g_memTimerPatched = 0;

static void installMemoryTimers() {
    if (!g_cfg.fixActionTimers || !g_eng.main || !g_timerMask) {
        return;  // shares the mask byte, so it needs the register form installed
    }
    const int total = (int)(sizeof(kMemTimerSites) / sizeof(kMemTimerSites[0]));
    const size_t kStub = 48;  // worst case is 37 bytes, rounded up for alignment
    size_t need = kStub * (size_t)total;
    uint8_t* cave = allocNear(g_eng.main, need);
    if (!cave) {
        logf("memory timers: no code cave near main.dll, not patched");
        return;
    }
    uint8_t* cur = cave;
    uint8_t* end = cave + need;
    int mismatched = 0;
    for (int i = 0; i < total; i++) {
        const MemTimerSite& t = kMemTimerSites[i];
        uint8_t* site = g_eng.main + t.rva;
        if (t.len < 5 || t.len > 8 || memcmp(site, t.orig, t.len) != 0) {
            mismatched++;
            continue;
        }
        if ((size_t)(end - cur) < kStub) {
            mismatched++;
            continue;
        }
        uint8_t* code = cur;
        size_t n = 0;
        code[n++] = 0x50;  // push rax
        code[n++] = 0x8A;  // mov al, byte ptr [rip+tickCounter]
        code[n++] = 0x05;
        int32_t disp = (int32_t)((uint8_t*)g_eng.frameCounter - (code + n + 4));
        memcpy(code + n, &disp, 4);
        n += 4;
        code[n++] = 0x22;  // and al, byte ptr [rip+mask]  -- 0 when off, so ZF
        code[n++] = 0x05;  //                                 is set and nothing skips
        disp = (int32_t)(g_timerMask - (code + n + 4));
        memcpy(code + n, &disp, 4);
        n += 4;
        code[n++] = 0x58;  // pop rax  -- does not touch the flags the `and` set
        code[n++] = 0x75;  // jnz skip
        size_t skipFixup = n;
        code[n++] = 0;
        memcpy(code + n, t.orig, t.len);  // the real count, and its real flags
        n += t.len;
        code[n++] = 0xE9;
        int32_t back = (int32_t)((int64_t)(site + t.len) - (int64_t)(code + n + 4));
        memcpy(code + n, &back, 4);
        n += 4;
        code[skipFixup] = (uint8_t)(n - skipFixup - 1);
        code[n++] = 0x48;  // test rsp, rsp  -- ZF=0, SF=0: "not finished yet"
        code[n++] = 0x85;
        code[n++] = 0xE4;
        code[n++] = 0xE9;
        back = (int32_t)((int64_t)(site + t.len) - (int64_t)(code + n + 4));
        memcpy(code + n, &back, 4);
        n += 4;

        int64_t rel = (int64_t)code - (int64_t)(site + 5);
        if (rel != (int32_t)rel) {
            mismatched++;
            continue;
        }
        uint8_t patch[8];
        memset(patch, 0x90, sizeof(patch));
        patch[0] = 0xE9;
        int32_t rel32 = (int32_t)rel;
        memcpy(patch + 1, &rel32, 4);
        if (!writeProtected(site, patch, t.len)) {
            mismatched++;
            continue;
        }
        cur = code + ((n + 15) & ~(size_t)15);
        g_memTimerPatched++;
    }
    if (mismatched) {
        logf("memory timers: %d of %d sites patched, %d did not match this build",
             g_memTimerPatched, total, mismatched);
    } else {
        logf("memory timers: all %d sites patched", g_memTimerPatched);
    }
}

// ---------------------------------------------------------------------------
// The ten doubly-compensated input windows
//
// The port's usual way of writing a frame-rate-independent input window is a
// raw constant shifted by the 60 fps flag:
//
//     mov ebx, 5
//     shl ebx, cl                  ; cl = main+0xB6AC40, 0 at 30 fps, 1 at 60
//     shl ebx, 0x10
//     call cPad::ActSet
//
// Ten sites in the player code compute the same window arithmetically instead,
// from the fps byte, and then shift it as well:
//
//     movzx ecx, byte ptr [fps]    ; 30 or 60
//     mov   eax, 0x88888889
//     mul   ecx
//     mov   ecx, dword ptr [shift]
//     shr   edx, 4                 ; edx = fps / 30
//     lea   ebx, [rdx + rdx*2]     ; ebx = 3 * (fps / 30)   <- already scaled
//     shl   ebx, cl                ;                        <- scaled again
//
// Three ticks at 30 fps become twelve at 60, which is twice the real time, and
// at 120 they would become forty-eight, which is four times it. The `fps / 30`
// term is the correct conversion on its own, so the fix is to drop the shift:
// two bytes per site, `shl ebx, cl` -> `nop`, with no cave and nothing to
// relocate. It shares the action timer toggle, because it is the same kind of
// mistake about the same kind of quantity.
// ---------------------------------------------------------------------------

static const uint32_t kInputWindowRvas[] = {
    0x3C1BA0, 0x3C1BD4, 0x3C1C66, 0x3C1C9A, 0x3C1CD2,
    0x3C1D06, 0x3C1D7C, 0x3C1DB0, 0x3C5F58, 0x3C5F8C,
};
static const uint8_t kInputWindowOrig[2] = {0xD3, 0xE3};  // shl ebx, cl
static const uint8_t kInputWindowNop[2] = {0x66, 0x90};   // xchg ax, ax

static int g_inputWindowOk = 0;
static bool g_inputWindowNopped = false;

static void checkInputWindows() {
    if (!g_cfg.fixInputWindows || !g_eng.main) {
        return;
    }
    for (uint32_t rva : kInputWindowRvas) {
        const uint8_t* site = g_eng.main + rva;
        if (memcmp(site, kInputWindowOrig, 2) != 0 &&
            memcmp(site, kInputWindowNop, 2) != 0) {
            logf("input windows: main+%X is not the expected shift, not patched", rva);
            g_inputWindowOk = 0;
            return;
        }
    }
    g_inputWindowOk = (int)(sizeof(kInputWindowRvas) / sizeof(kInputWindowRvas[0]));
    logf("input windows: %d doubly-compensated sites found", g_inputWindowOk);
}

// Called from the watcher alongside the action timers, and gated the same way.
static void updateInputWindows() {
    if (!g_inputWindowOk) {
        return;
    }
    bool want = g_cfg.fixInputWindows && g_fps60 && !g_timerFixMuted;
    if (want == g_inputWindowNopped) {
        return;
    }
    const uint8_t* bytes = want ? kInputWindowNop : kInputWindowOrig;
    for (uint32_t rva : kInputWindowRvas) {
        writeProtected(g_eng.main + rva, bytes, 2);
    }
    g_inputWindowNopped = want;
    logf("input windows -> %s", want ? "real time" : "stock (double-scaled at 60 fps)");
}

// ---------------------------------------------------------------------------
// The third encoding of the same countdown
//
// A handler that needs the value from *before* the count cannot use `dec`,
// because `dec` clobbers the flags it is about to branch on and overwrites the
// value it still needs. The compiler emits `lea` instead:
//
//     movzx eax, word ptr [rdx+0xE3C]
//     lea   eax, [rcx - 1]             <- new = old - 1, flags untouched
//     mov   word ptr [rdx+0xE3C], ax
//     test  cx, cx                     <- ... and the branch tests the OLD value
//     jne   still_running
//
// 106 more sites, and neither instruction touches the flags, so the stub only
// has to preserve them across its own parity test. The `test`/`cmp` that
// follows reads the untouched load register, so on a skipped tick it behaves
// exactly as though the tick had not happened.
//
// The one thing it does need is the register. The `lea` writes a different
// register from the one it reads -- at all 106 sites -- and at a few of them the
// branch tests that destination rather than the load register. Leaving it alone
// on a skipped tick would compare stale contents, so the skip path copies the
// old value into it with a synthesised `mov dst, src`. The destination then
// holds exactly what the field holds, one tick behind, which is the whole point
// of the fix, and it makes the patch safe at every site whatever reads that
// register afterwards.
//
// src/lea_timers.h is generated by tools/find_lea_timers.py.
// ---------------------------------------------------------------------------

#include "lea_timers.h"

static int g_leaTimerPatched = 0;

static void installLeaTimers() {
    if (!g_cfg.fixActionTimers || !g_eng.main || !g_timerMask) {
        return;  // shares the mask byte, so it needs the register form installed
    }
    const int total = (int)(sizeof(kLeaTimerSites) / sizeof(kLeaTimerSites[0]));
    const size_t kStub = 48;  // worst case is 43 bytes, rounded up for alignment
    size_t need = kStub * (size_t)total;
    uint8_t* cave = allocNear(g_eng.main, need);
    if (!cave) {
        logf("lea timers: no code cave near main.dll, not patched");
        return;
    }
    uint8_t* cur = cave;
    uint8_t* end = cave + need;
    int mismatched = 0;
    for (int i = 0; i < total; i++) {
        const LeaTimerSite& t = kLeaTimerSites[i];
        uint8_t* site = g_eng.main + t.rva;
        if (t.len < 5 || t.len > 11 || t.dstReg > 15 || t.srcReg > 15 ||
            memcmp(site, t.orig, t.len) != 0) {
            mismatched++;
            continue;
        }
        if ((size_t)(end - cur) < kStub) {
            mismatched++;
            continue;
        }
        uint8_t* code = cur;
        size_t n = 0;
        code[n++] = 0x9C;  // pushfq   -- the displaced pair preserves flags, so
        code[n++] = 0x50;  // push rax    the parity test must not disturb them
        code[n++] = 0x8A;  // mov al, byte ptr [rip+tickCounter]
        code[n++] = 0x05;
        int32_t disp = (int32_t)((uint8_t*)g_eng.frameCounter - (code + n + 4));
        memcpy(code + n, &disp, 4);
        n += 4;
        code[n++] = 0x22;  // and al, byte ptr [rip+mask]  -- 0 when off, so ZF
        code[n++] = 0x05;  //                                 is set and nothing skips
        disp = (int32_t)(g_timerMask - (code + n + 4));
        memcpy(code + n, &disp, 4);
        n += 4;
        code[n++] = 0x58;  // pop rax  -- does not touch the flags the `and` set
        code[n++] = 0x75;  // jnz skip
        size_t skipFixup = n;
        code[n++] = 0;
        code[n++] = 0x9D;  // popfq
        memcpy(code + n, t.orig, t.len);  // the lea and its store
        n += t.len;
        code[n++] = 0xE9;
        int32_t back = (int32_t)((int64_t)(site + t.len) - (int64_t)(code + n + 4));
        memcpy(code + n, &back, 4);
        n += 4;
        code[skipFixup] = (uint8_t)(n - skipFixup - 1);
        code[n++] = 0x9D;  // popfq
        // mov dstReg32, srcReg32 -- the old value, so the register and the
        // field stay in agreement on a skipped tick
        if (t.srcReg >= 8 || t.dstReg >= 8) {
            code[n++] = (uint8_t)(0x40 | ((t.srcReg >= 8) ? 4 : 0) |
                                  ((t.dstReg >= 8) ? 1 : 0));
        }
        code[n++] = 0x89;
        code[n++] = (uint8_t)(0xC0 | ((t.srcReg & 7) << 3) | (t.dstReg & 7));
        code[n++] = 0xE9;
        back = (int32_t)((int64_t)(site + t.len) - (int64_t)(code + n + 4));
        memcpy(code + n, &back, 4);
        n += 4;

        int64_t rel = (int64_t)code - (int64_t)(site + 5);
        if (rel != (int32_t)rel) {
            mismatched++;
            continue;
        }
        uint8_t patch[11];
        memset(patch, 0x90, sizeof(patch));
        patch[0] = 0xE9;
        int32_t rel32 = (int32_t)rel;
        memcpy(patch + 1, &rel32, 4);
        if (!writeProtected(site, patch, t.len)) {
            mismatched++;
            continue;
        }
        cur = code + ((n + 15) & ~(size_t)15);
        g_leaTimerPatched++;
    }
    if (mismatched) {
        logf("lea timers: %d of %d sites patched, %d did not match this build",
             g_leaTimerPatched, total, mismatched);
    } else {
        logf("lea timers: all %d sites patched", g_leaTimerPatched);
    }
}

// ---------------------------------------------------------------------------
// The mode byte, and why 120 fps made Amaterasu skate
//
// The engine does not always ask the time scale what frame rate it is running
// at. Often it tests the *mode byte* at main+0xB6AC45, which is 2 for the 30 fps
// configuration and 1 for the fast one -- and the patch's 120 fps mode leaves it
// at 1, because 1 is what selects the fast configuration at all. Every site
// that reads the mode byte and picks a hard-coded 60 fps constant therefore
// keeps handing out the 60 fps value at 120 fps.
//
// The one that shows is the per-tick motion advance at main+0x4B9C89:
//
//     cmp   byte ptr [rip+modeByte], 1
//     jne   thirty
//     movss xmm7, dword ptr [rip+0.5]      <- the fast path, hard-coded
//   thirty:
//     movaps xmm7, xmm8                    ; = 1.0
//
// At 120 fps the world advances a quarter step per frame while animation
// advances a half step, so Amaterasu covers ground twice as fast as her legs
// move. That is the skating.
//
// It is not one constant. The port ships a complete pre-computed damping table
// at main+0x7A8150: pairs of `{k**0.5, k}` for k = 0.99, 0.98 ... 0.05 and the
// matching growth factors up to 1.9, indexed by `(mode - 1) * 4`. It is the same
// square root this patch derives for its own decay factors, except the engine
// did it for itself, for every constant it uses -- and then only for two frame
// rates. At 120 fps all 60 entries return the 60 fps root, so everything damped
// through the table bleeds off at half the rate it should.
//
// Both are corrected the same way, by the exponent the engine's own table
// implies: `k ** timeScale`, which reproduces the shipped value exactly at
// 60 fps and gives the right one at 120. The table slots are rewritten in place;
// the 0.5 is a shared .rdata constant that hundreds of unrelated instructions
// read, so those six sites are retargeted at a private copy instead.
//
// src/mode_constants.h is generated by tools/find_mode_constants.py.
// ---------------------------------------------------------------------------

#include "mode_constants.h"

static float* g_modeHalf = nullptr;   // the private 0.5 the selects now read
static int g_modeSelectsPatched = 0;
static int g_modeTablesOk = 0;
static float g_modeTableTs = 0.0f;    // the exponent the table currently holds

static void installModeConstants() {
    if (!g_cfg.fixModeConstants || !g_eng.main) {
        return;
    }
    const int total = (int)(sizeof(kModeTables) / sizeof(kModeTables[0]));
    int matched = 0;
    for (const ModeTable& t : kModeTables) {
        if (*(const float*)(g_eng.main + t.rva) == t.fast) {
            matched++;
        }
    }
    if (matched != total) {
        logf("mode constants: %d of %d damping entries matched, not patched",
             matched, total);
        return;
    }
    g_modeTablesOk = total;

    uint8_t* cave = allocNear(g_eng.main, sizeof(float) * 4);
    if (!cave) {
        logf("mode constants: no data cave near main.dll, selects not retargeted");
    } else {
        g_modeHalf = (float*)cave;
        *g_modeHalf = 0.5f;
        for (const ModeSelect& sel : kModeSelects) {
            uint8_t* site = g_eng.main + sel.rva;
            if (memcmp(site, sel.orig, sizeof(sel.orig)) != 0) {
                continue;
            }
            int64_t rel = (int64_t)(uint8_t*)g_modeHalf - (int64_t)(site + 8);
            if (rel != (int32_t)rel) {
                continue;
            }
            int32_t disp = (int32_t)rel;
            if (writeProtected(site + 4, &disp, sizeof(disp))) {
                g_modeSelectsPatched++;
            }
        }
    }
    logf("mode constants: %d damping entries verified, %d of %d selects retargeted",
         g_modeTablesOk, g_modeSelectsPatched,
         (int)(sizeof(kModeSelects) / sizeof(kModeSelects[0])));
}

// Called from the watcher. At 60 fps every value here is exactly what the game
// shipped, so this only ever does anything at 120.
static void updateModeConstants() {
    if (!g_modeTablesOk && !g_modeHalf) {
        return;
    }
    bool on = g_cfg.fixModeConstants && g_fps60 && !g_speedFixMuted;
    // the ladder's value, not the engine's: see patchTimeScale()
    float ts = on ? patchTimeScale() : 0.5f;
    if (g_modeHalf && *g_modeHalf != ts) {
        *g_modeHalf = ts;
    }
    if (!g_modeTablesOk) {
        return;
    }
    bool stock = (ts >= 0.499f && ts <= 0.501f);
    int fixed = 0;
    for (const ModeTable& t : kModeTables) {
        float* slot = (float*)(g_eng.main + t.rva);
        // at 60 fps put the shipped bytes back rather than recomputing a value
        // that could differ from them in the last bit
        float want = stock ? t.fast : powf(t.stock, ts);
        if (*slot != want) {
            writeProtected(slot, &want, sizeof(want));
            fixed++;
        }
    }
    if (fixed && g_modeTableTs != ts) {
        logf("mode constants -> k^%.2f applied to %d damping entries",
             (double)ts, fixed);
    }
    g_modeTableTs = ts;
    // the turn callers' private copies of some of these entries follow them
    // while the turn hook is not converting
    updateTurnPairs();
}


// ---------------------------------------------------------------------------
// The integer half of the mode-byte family
//
// The damping tables above are the float side. There is an integer side, and a
// float scan could never have found it, because the per-mode "table" is the
// instruction itself:
//
//     cmp   byte ptr [B6AC45], 1
//     ...
//     jne   skip
//     add   eax, eax          <- the entire table, as one instruction
//   skip:
//     ret
//
// and, where the compiler wanted branchless code,
//
//     cmp   byte ptr [B6AC45], 1
//     sete  al
//     inc   eax               <- eax = 1 or 2
//     imul  eax, <n>
//
// Both are `n * (mode == 1 ? 2 : 1)`, and at all seven sites n is a duration in
// ticks: the four track-length getters of the UI layout player (colour,
// position, rotation, scale), the compare that finds the current keyframe,
// the span a keyframe interpolates over, and the length of a motion blend in
// the player's own animation handler. The mode byte is 1 at 120 fps too, so
// every one of them still doubles where it now needs to quadruple, and each
// runs at exactly twice the speed it should.
//
// The fix replaces the hard-coded 2 with a dword the patch holds, so the stub
// is bit-for-bit stock whenever that dword is 2. That is worth saying plainly:
// at 60 fps, at 30, and whenever the fix is muted, these detours compute
// precisely what the shipped instructions computed -- which is why they are
// safe to leave installed rather than toggled in and out of the code.
//
// src/mode_multipliers.h is generated by tools/find_mode_multipliers.py.
// ---------------------------------------------------------------------------

#include "mode_multipliers.h"

static int32_t* g_modeMult = nullptr;  // 2 in 60 fps mode, 4 in 120 fps mode
static int g_modeMultPatched = 0;

static void installModeMultipliers() {
    if (!g_cfg.fixModeMultipliers || !g_eng.main) {
        return;
    }
    const int total = (int)(sizeof(kModeMults) / sizeof(kModeMults[0]));
    uint8_t* cave = allocNear(g_eng.main, 4096);
    if (!cave) {
        logf("mode multipliers: no cave near main.dll");
        return;
    }
    g_modeMult = (int32_t*)cave;
    *g_modeMult = 2;  // stock
    uint8_t* cur = cave + 16;
    uint8_t* end = cave + 4096;

    for (const ModeMult& mm : kModeMults) {
        uint8_t* site = g_eng.main + mm.rva;
        if (memcmp(site, mm.orig, mm.len) != 0) {
            continue;
        }
        if (cur + 64 > end) {
            break;
        }
        uint8_t* stub = cur;
        uint8_t code[64];
        int n = 0;
        int jneFix = -1;
        int jmpFix = -1;

        auto relMult = [&](int at) {
            int32_t d = (int32_t)((uint8_t*)g_modeMult - (stub + at + 4));
            memcpy(code + at, &d, 4);
        };
        auto jmpTo = [&](uint32_t rva) {
            code[n++] = 0xE9;
            int32_t d = (int32_t)((g_eng.main + rva) - (stub + n + 4));
            memcpy(code + n, &d, 4);
            n += 4;
        };

        switch (mm.shape) {
            case kMultImulEax:
                memcpy(code + n, mm.orig, mm.len);
                n += mm.len;
                code[n++] = 0x75;
                jneFix = n;
                code[n++] = 0;  // jne L
                code[n++] = 0x0F;
                code[n++] = 0xAF;
                code[n++] = 0x05;
                relMult(n);
                n += 4;  // imul eax, [mult]
                code[jneFix] = (uint8_t)(n - jneFix - 1);  // L:
                jmpTo(mm.resume);
                break;
            case kMultMovsxEdx:
                memcpy(code + n, mm.orig, 4);  // movsx edx, [...]
                n += 4;
                code[n++] = 0x75;
                jneFix = n;
                code[n++] = 0;  // jne L
                code[n++] = 0x89;
                code[n++] = 0xD0;  // mov eax, edx
                code[n++] = 0x0F;
                code[n++] = 0xAF;
                code[n++] = 0x05;
                relMult(n);
                n += 4;  // imul eax, [mult]
                jmpTo(mm.resume);
                code[jneFix] = (uint8_t)(n - jneFix - 1);  // L:
                jmpTo(mm.altResume);
                break;
            case kMultSeteR9:
                code[n++] = 0x75;
                jneFix = n;
                code[n++] = 0;  // jne L
                code[n++] = 0x44;
                code[n++] = 0x8B;
                code[n++] = 0x0D;
                relMult(n);
                n += 4;  // mov r9d, [mult]
                code[n++] = 0xEB;
                jmpFix = n;
                code[n++] = 0;  // jmp M
                code[jneFix] = (uint8_t)(n - jneFix - 1);  // L:
                code[n++] = 0x41;
                code[n++] = 0xB9;  // mov r9d, 1
                {
                    int32_t one = 1;
                    memcpy(code + n, &one, 4);
                    n += 4;
                }
                code[jmpFix] = (uint8_t)(n - jmpFix - 1);  // M:
                jmpTo(mm.resume);
                break;
            case kMultSeteEbx:
                code[n++] = 0x75;
                jneFix = n;
                code[n++] = 0;  // jne L
                code[n++] = 0x8B;
                code[n++] = 0x1D;
                relMult(n);
                n += 4;  // mov ebx, [mult]
                code[n++] = 0xEB;
                jmpFix = n;
                code[n++] = 0;  // jmp M
                code[jneFix] = (uint8_t)(n - jneFix - 1);  // L:
                code[n++] = 0xBB;  // mov ebx, 1
                {
                    int32_t one = 1;
                    memcpy(code + n, &one, 4);
                    n += 4;
                }
                code[jmpFix] = (uint8_t)(n - jmpFix - 1);  // M:
                memcpy(code + n, mm.orig + 3, 4);  // the displaced lea
                n += 4;
                jmpTo(mm.resume);
                break;
            case kMultCmp2Eax:
                memcpy(code + n, mm.orig, mm.len);
                n += mm.len;
                code[n++] = 0x83;
                code[n++] = 0xF8;
                code[n++] = 0x02;  // cmp eax, 2
                code[n++] = 0x75;
                jneFix = n;
                code[n++] = 0;  // jne L
                code[n++] = 0x8B;
                code[n++] = 0x05;
                relMult(n);
                n += 4;  // mov eax, [mult]
                code[jneFix] = (uint8_t)(n - jneFix - 1);  // L:
                jmpTo(mm.resume);
                break;
            default:
                continue;
        }
        memcpy(stub, code, (size_t)n);
        cur += (n + 15) & ~15;

        uint8_t patch[16];
        memset(patch, 0x90, sizeof(patch));
        patch[0] = 0xE9;
        int32_t rel = (int32_t)(stub - (site + 5));
        memcpy(patch + 1, &rel, 4);
        if (writeProtected(site, patch, mm.len)) {
            g_modeMultPatched++;
        }
    }
    logf("mode multipliers: %d of %d integer x2 sites patched", g_modeMultPatched, total);
}

// 2 reproduces the shipped instruction exactly, so that is the value whenever
// the fix is not wanted.
static void updateModeMultipliers() {
    if (!g_modeMult) {
        return;
    }
    bool on = g_cfg.fixModeMultipliers && g_fps60 && !g_timerFixMuted;
    int32_t want = (on && g_fpsImmsFast) ? 4 : 2;
    if (*g_modeMult != want) {
        *g_modeMult = want;
        logf("mode multipliers -> x%d", want);
    }
}

// ---------------------------------------------------------------------------
// Frame-counter rate gates
//
// Repeating effects are not timed by a per-object countdown at all. They are
// throttled straight off the global frame counter:
//
//     test byte ptr [rip+frameCounter], 7
//     jne  skip
//     ...                     ; every eighth frame: spawn the dust, the spark
//   skip:
//
// The mask is a tick count like any other duration, so every footstep puff,
// trail spark, ripple and aura pulse in the game appears twice as often at
// 60 fps and would appear four times as often at 120. Two sites in pl01 write
// the same throttle as `frameCounter % (fps / 2)`, which does follow the frame
// rate -- the same story as the per-mode decay table, where the port worked out
// the right answer once and left every other instance alone.
//
// Widening the mask is the whole fix, one byte per site: 7 becomes 15 at 60 fps
// and 31 at 120. Every site is the memory form, whose only effect is on the
// flags the `jne` reads, so there is nothing else in the instruction to
// disturb. Four further sites load the counter into a register and go on to use
// that register, and those are left alone.
//
// src/frame_gates.h is generated by tools/find_frame_gates.py.
// ---------------------------------------------------------------------------

#include "frame_gates.h"

static int g_frameGateOk = 0;
static uint8_t g_frameGateShift = 0xFF;  // 0 = stock, 1 = 60 fps, 2 = 120 fps

static void checkFrameGates() {
    if (!g_cfg.fixFrameGates || !g_eng.main) {
        return;
    }
    for (const FrameGate& g : kFrameGates) {
        const uint8_t* site = g_eng.main + g.rva;
        if (memcmp(site, g.orig, g.immOff) != 0) {
            logf("frame gates: main+%X is not the expected test, not patched", g.rva);
            g_frameGateOk = 0;
            return;
        }
    }
    g_frameGateOk = (int)(sizeof(kFrameGates) / sizeof(kFrameGates[0]));
    g_frameGateShift = 0xFF;
    logf("frame gates: %d effect rate gates found", g_frameGateOk);
}

// Called from the watcher alongside the action timers, and gated the same way.
static void updateFrameGates() {
    if (!g_frameGateOk) {
        return;
    }
    uint8_t shift = 0;
    if (g_cfg.fixFrameGates && g_fps60 && !g_timerFixMuted) {
        shift = g_fpsImmsFast ? 2 : 1;
    }
    if (shift == g_frameGateShift) {
        return;
    }
    for (const FrameGate& g : kFrameGates) {
        // (mask + 1) frames becomes (mask + 1) << shift frames
        uint8_t want = (uint8_t)(((g.mask + 1u) << shift) - 1u);
        writeProtected(g_eng.main + g.rva + g.immOff, &want, 1);
    }
    g_frameGateShift = shift;
    logf("frame gates -> %s", shift ? "real time" : "stock (fast at 60 fps)");
}

// ---------------------------------------------------------------------------
// Frame-counter oscillators
//
// The other way the frame counter is read is as an angle. Menus, pickups and
// the enemy marker pulse by feeding it straight into a sine:
//
//     mov  eax, dword ptr [rip+frameCounter]
//     lea  ecx, [rax + rax*4]
//     add  ecx, ecx                       ; ecx = frame * 10
//     ...                                 ; ecx % 360
//     cvtsi2ss xmm0, rax
//     call sin
//
// Ten degrees a frame is a 36-frame cycle: 1.2 s at 30 fps, 0.6 s at 60, 0.3 s
// at 120. This is most of what was left of "the interface still looks hurried".
//
// Widening a mask does not work here, because the value is used rather than
// tested, so these 22 reads are retargeted instead -- the same displacement-only
// rewrite the phase steps and decay factors use -- to a private dword the patch
// keeps at the stock rate of the current context (see updateSlowFrame). The
// copy is *derived* from the counter rather than accumulated, so it cannot
// drift; it is
// refreshed from the present hook, once per presented frame, and again from the
// watcher in case the hook is not installed. Nothing else that reads the
// counter is touched: not the rate gates, not the `frame % (fps / 2)`
// throttles, and not the "have I already run this frame" comparisons, which
// must keep seeing the real value.
//
// objScroll was excluded here on the belief that it bumps the counter by one
// around a nested update. It does not: the bump (main+35B2C8) is in its init,
// around a loop that never reads the counter, and its second layer's offset is
// the `+ 180` in its own formula. Its reads are in frame_clocks.h instead.
//
// src/frame_phases.h is generated by tools/find_frame_phases.py.
// ---------------------------------------------------------------------------

#include "frame_phases.h"

// The page both frame-counter families read from: the counters (the first of
// which is this family's copy) at the start, the per-tick hook's stub after
// them (see "Frame-counter clocks" below). Every counter starts as the frame
// counter itself.
static const size_t kFcSlotCount = 16;
static const size_t kFcStubOff = 0x100;
static uint8_t* g_fcPage = nullptr;
static bool g_fcHooked = false;  // the per-tick hook keeps the counters

static uint32_t* frameClockSlots() {
    if (!g_fcPage && g_eng.main && g_eng.frameCounter) {
        g_fcPage = allocNear(g_eng.main, 4096);
        if (g_fcPage) {
            uint32_t now = *(volatile uint32_t*)g_eng.frameCounter;
            for (size_t i = 0; i < kFcSlotCount; i++) {
                ((uint32_t*)g_fcPage)[i] = now;
            }
        }
    }
    return (uint32_t*)g_fcPage;
}

static uint32_t* g_slowFrame = nullptr;  // what the retargeted reads see
static int g_framePhasePatched = 0;

static void installFramePhases() {
    if (!g_cfg.fixFramePhases || !g_eng.main || !g_eng.frameCounter) {
        return;
    }
    g_slowFrame = frameClockSlots();
    if (!g_slowFrame) {
        logf("frame phases: no data cave near main.dll, not patched");
        return;
    }
    const int total = (int)(sizeof(kFramePhases) / sizeof(kFramePhases[0]));
    int mismatched = 0;
    for (int i = 0; i < total; i++) {
        const FramePhase& f = kFramePhases[i];
        uint8_t* site = g_eng.main + f.rva;
        if (memcmp(site, f.orig, f.len) != 0) {
            mismatched++;
            continue;
        }
        int64_t rel = (int64_t)(uint8_t*)g_slowFrame - (int64_t)(site + f.len);
        if (rel != (int32_t)rel) {
            mismatched++;
            continue;
        }
        int32_t disp = (int32_t)rel;
        if (!writeProtected(site + f.dispOff, &disp, sizeof(disp))) {
            mismatched++;
            continue;
        }
        g_framePhasePatched++;
    }
    if (mismatched) {
        logf("frame phases: %d of %d oscillators retargeted, %d did not match this build",
             g_framePhasePatched, total, mismatched);
    } else {
        logf("frame phases: all %d oscillators retargeted", g_framePhasePatched);
    }
}

// The copy runs at the stock rate of the context the game is in. That is not
// always 30: the options pages and the memory-card screen, where 9 of the 22
// oscillators live, run at 60 in the stock game (the tracer session measured
// it, and the shadow mode byte reports it live). So at 120 fps the copy steps
// once per 4 ticks in play but once per 2 there, and at 60 fps once per 2 and
// once per tick. A single `frameCounter >> shift` pulsed those menus at half
// their stock speed.
//
// Changing the divisor of `frameCounter / N` would jump the phase, so the copy
// is `base + (frameCounter - frame0) / N`, rebased whenever N changes: derived
// from the counter between changes, so it cannot drift, and continuous across
// them. With the fix off it is the counter itself, as in the stock game.
static SRWLOCK g_slowLock = SRWLOCK_INIT;
static uint32_t g_slowBase = 0;   // the copy's value at the last rebase
static uint32_t g_slowFc0 = 0;    // the counter at the last rebase
static uint32_t g_slowN = 0;      // ticks per step; 0 while the fix is off

static void updateSlowFrame() {
    // once the per-tick hook is in (FixFrameClocks), it keeps the copy, on the
    // exact tick the counter changes; this is the fallback without it
    if (!g_slowFrame || !g_eng.frameCounter || g_fcHooked) {
        return;
    }
    // the present hook and the watcher both call this; whichever comes second
    // skips, the other one has just done it
    if (!TryAcquireSRWLockExclusive(&g_slowLock)) {
        return;
    }
    uint32_t now = *(volatile uint32_t*)g_eng.frameCounter;
    uint32_t n = 0;
    if (g_cfg.fixFramePhases && g_fps60 && !g_timerFixMuted) {
        uint32_t fps = g_fpsImmsFast ? 120u : 60u;
        bool stock60 = g_shadowOn && *g_shadowMode == 1;
        n = fps / (stock60 ? 60u : 30u);
    }
    // rebase when N changes, and if the counter ever runs backwards
    int32_t since = (int32_t)(now - g_slowFc0);
    if (n != g_slowN || since < 0) {
        g_slowBase = g_slowN ? g_slowBase + (since > 0 ? (uint32_t)since / g_slowN : 0) : now;
        g_slowFc0 = now;
        g_slowN = n;
    }
    *g_slowFrame = n ? g_slowBase + (now - g_slowFc0) / n : now;
    ReleaseSRWLockExclusive(&g_slowLock);
}

// Offline self-test, driven by tools/verify_shadow_mode.py: runs the copy
// against a counter of its own through every combination of fps mode and
// stock context, one tick at a time, and writes what it produced
// (tick,fps,shadow,active,counter,copy) for the script to check the rates,
// the continuity across switches and the identity with the fix off.
extern "C" __declspec(dllexport) int OkamiSlowFrameSelfTest(const char* outDir) {
    static uint32_t counter = 1000;
    static uint32_t copy = 0;
    static uint8_t shadow = 2;
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\slow_frame.csv", outDir);
    FILE* f = fopen(path, "w");
    if (!f) {
        return 2;
    }
    g_eng.frameCounter = &counter;
    g_slowFrame = &copy;
    g_shadowMode = &shadow;
    g_shadowOn = true;
    g_cfg.fixFramePhases = true;
    g_timerFixMuted = 0;
    // fps: 120, 60, or 30 (the fix off); shadow: the stock game's mode byte
    static const struct { int ticks, fps, shadow; } kSegs[] = {
        {400, 120, 2}, {400, 120, 1}, {401, 120, 2}, {403, 60, 2}, {400, 60, 1},
        {399, 30, 2},  {400, 120, 2}, {7, 120, 1},   {9, 120, 2},  {400, 60, 2},
        {400, 120, 1}, {400, 30, 1},  {400, 120, 1},
    };
    fprintf(f, "tick,fps,shadow,active,counter,copy\n");
    int tick = 0;
    for (const auto& s : kSegs) {
        g_fps60 = s.fps != 30;
        g_fpsImmsFast = s.fps == 120;
        shadow = (uint8_t)s.shadow;
        for (int i = 0; i < s.ticks; i++, tick++) {
            counter++;
            updateSlowFrame();
            fprintf(f, "%d,%d,%d,%d,%u,%u\n", tick, s.fps, s.shadow, g_slowN ? 1 : 0, counter,
                    copy);
        }
    }
    fclose(f);
    return 0;
}

// ---------------------------------------------------------------------------
// Frame-counter clocks (family F5)
//
// Everything else that reads the frame counter as a clock. Gates, rather than
// phases, are what make this different from the oscillators above:
//
//     mov  eax, 0x88888889
//     mul  dword ptr [rip+frameCounter]
//     shr  edx, 3
//     imul eax, edx, 15
//     cmp  dword ptr [rip+frameCounter], eax
//     jne  skip                        ; every 15th tick: the player's sparkle
//
// A copy stepping once per N ticks (S) is right for a phase but wrong for a
// gate: it sits on a multiple of 15 for N ticks in a row, so the gate fires N
// times. And unlike a `test byte [counter], 7` a modulus cannot be widened in
// place: 15 x 4 is still an imm8, but the loading screen's `% 10` is built from
// lea/add and 90 x 4 is not. So each gate's read goes to a hold counter
// H(P, e): S, except that on the ticks of a stock tick after its first, a
// value that is e mod P is held back to the one before it. The gate then fires
// once per stock tick, and every other residue reads exactly as S -- which is
// what lets the loading screen's `fc % 10` drive its dots (== 0, an event)
// and its rhythm window ({0, 1, 8, 9}, which 9 is still inside) from one read.
//
// That is only exact if the counters change on the very tick the engine's
// counter does. So they are kept by a hook on flower_tick's own
// `inc dword [frameCounter]` (main+4B651E), not from the present hook: the
// stub runs the increment, saves every volatile register, the flags and
// xmm0-5, and calls frameClockOnTick. PLAN step 0.2's per-tick hook, first
// user.
//
// Also here:
//   U   the loading screen's elapsed windows, `(counter - stamp) < 480 / mode`:
//       the mode byte is pinned at 1, so they count 60 Hz-configuration ticks
//   the mask gates frame_gates.h's search missed (a `test` in a register, or
//   with an instruction between it and its branch), widened the same way.
//
// Every read is retargeted once at install and never touched again: with the
// fix off each counter is the frame counter itself, so the read is stock.
//
// That puts U back on the frame counter's own values whenever the fix goes
// off, and the loading screen keeps stamps of U (main+B31984/B31988) across
// it: after a while at 120 fps U is hundreds of ticks behind the counter, and
// an F9 or F6 inside a loading window made its stamp that much older in one
// tick, which expired the window or finished the fade at once. U's rate
// changes too: 60 Hz-configuration ticks with the fix on; with it off the
// counter's own, which is the patched 60 or 120, or in the stock game (F9)
// the stock game's own rate, 60 in its mode-1 contexts (options, memory card,
// pause, title) and 30 elsewhere. So whenever the patch changes U's
// coordinates or rate the hook moves each stamp to keep the time since it, in
// seconds, what it was (frameClockRebaseStamps). The stock game changing its
// own mode is left alone: it counts its windows in its own ticks, and the
// patch switched off must leave it exact. Every access to those stamps is a
// member of U's family (the generator checks), and S and the holds keep no
// stamps: their readers are phases, cycles and gates, for which a jump is
// only a phase.
//
// src/frame_clocks.h is generated by tools/gen_frame_clocks.py;
// tools/verify_frame_clocks.py proves it offline.
// ---------------------------------------------------------------------------

#include "frame_clocks.h"

static const int kFcHolds = (int)(sizeof(kFrameClockHolds) / sizeof(kFrameClockHolds[0]));
static const int kFcReads = (int)(sizeof(kFrameClockReads) / sizeof(kFrameClockReads[0]));
static const int kFcGates = (int)(sizeof(kFrameClockGates) / sizeof(kFrameClockGates[0]));
static const int kFcStamps = (int)(sizeof(kFrameClockStamps) / sizeof(kFrameClockStamps[0]));
static_assert(2 + kFcHolds <= (int)kFcSlotCount, "frame clock slots");

struct FrameClockState {
    uint32_t sBase, sFc0, sN;  // S: value and counter at the last rebase, ticks per step
    uint32_t uBase, uFc0, uN;  // U: the same, in 60 Hz-configuration ticks
    uint32_t uHz;              // U's ticks per second as the previous tick counted them
    uint32_t sPrev;            // S as the previous tick left it
    bool uStock;               // the previous tick was the stock game's own (F9)
    bool started;
};
static FrameClockState g_fcs = {};
static uint32_t* g_fcStamps[sizeof(kFrameClockStamps) / sizeof(kFrameClockStamps[0])] = {};
static volatile LONG g_fcTicks = 0;      // hook calls, for the status line
static int g_fcReadsPatched = 0;
static bool g_fcGatesOk = false;
static bool g_fcStranded = false;  // a failed install left the hook in: counters held stock
static uint8_t g_fcGateShift = 0xFF;

// base + (now - fc0) / n, rebased when n changes (so it never jumps) or when
// the counter runs backwards (flower_startup's memset); the counter itself
// while n is 0. The same arithmetic as updateSlowFrame.
static uint32_t scaledCounter(uint32_t now, uint32_t n, uint32_t& base, uint32_t& fc0,
                              uint32_t& curN) {
    int32_t since = (int32_t)(now - fc0);
    if (n != curN || since < 0) {
        base = curN ? base + (since > 0 ? (uint32_t)since / curN : 0) : now;
        fc0 = now;
        curN = n;
    }
    return n ? base + (now - fc0) / n : now;
}

// The mode byte as the stock game has it: the shadow while that is on (the
// real byte is pinned at 1 then), otherwise the real byte, which in the stock
// game (F9) is the game's own again. 1 = its 60 Hz contexts, 2 = 30 Hz.
static uint8_t stockModeByte() {
    volatile uint8_t* m = g_shadowOn ? g_shadowMode : (volatile uint8_t*)g_eng.modeByte;
    return m ? *m : 2;
}

// U's ticks per second: 60 while it counts 60 Hz-configuration ticks (n60 > 0),
// otherwise the counter's own rate -- the patched fps, or with the patch off
// the stock game's, which ticks at 60 in its mode-1 contexts.
static uint32_t frameClockUHz(uint32_t n60) {
    if (n60) {
        return 60u;
    }
    if (g_fps60) {
        return g_fpsImmsFast ? 120u : 60u;
    }
    return stockModeByte() == 1 ? 60u : 30u;
}

// U has just gone from uWas (in the old coordinates, at hzWas per second) to
// uNow (at hzNow). Move each stamp so that the time since it, in seconds, is
// what it was: a window that was open stays open for as long as it had left,
// in the new mode's own terms. A stamp 2^28 ticks back (a month at 120 Hz)
// is only moved, never scaled: nothing it gates can be open.
static void frameClockRebaseStamps(uint32_t uWas, uint32_t hzWas, uint32_t uNow,
                                   uint32_t hzNow) {
    for (int i = 0; i < kFcStamps; i++) {
        uint32_t* p = g_fcStamps[i];
        if (!p) {
            continue;
        }
        uint32_t e = uWas - *p;
        if (e < 0x10000000u) {
            e = (uint32_t)((uint64_t)e * hzNow / hzWas);
        }
        *p = uNow - e;
    }
}

// One tick: n = ticks per stock tick in this context, n60 = ticks per 60 Hz
// tick; both 0 with the fix off. uHz = U's ticks per second (frameClockUHz);
// stock = the patch is off (F9) and this is the stock game's own tick.
static void frameClockStep(uint32_t now, uint32_t n, uint32_t n60, uint32_t uHz, bool stock,
                           uint32_t* slots) {
    FrameClockState& s = g_fcs;
    uint32_t sv = scaledCounter(now, n, s.sBase, s.sFc0, s.sN);
    // U as this tick would read it had nothing changed; not when the counter
    // ran backwards (flower_startup's memset), where every stamp is stale anyway
    bool forward = (int32_t)(now - s.uFc0) >= 0;
    uint32_t uWas = s.uN ? s.uBase + (now - s.uFc0) / s.uN : now;
    uint32_t uv = scaledCounter(now, n60, s.uBase, s.uFc0, s.uN);
    // from one stock tick to the next the rate is the stock game's own
    // business: it changes with the game's mode, as in the stock game
    if (s.started && forward && s.uHz && (uv != uWas || uHz != s.uHz) &&
        !(stock && s.uStock)) {
        frameClockRebaseStamps(uWas, s.uHz, uv, uHz);
    }
    s.uHz = uHz;
    s.uStock = stock;
    bool first = !s.started || sv != s.sPrev;  // the stock tick starts here
    s.started = true;
    s.sPrev = sv;
    slots[0] = sv;
    slots[1] = uv;
    for (int i = 0; i < kFcHolds; i++) {
        const FrameClockHold& h = kFrameClockHolds[i];
        uint32_t v = sv;
        if (!first && sv % h.period == h.event) {
            v = sv ? sv - 1 : h.period - 1u;  // the residue before, even at 0
        }
        slots[2 + i] = v;
    }
}

// Called by the stub on the game thread, right after the counter went up.
// Arithmetic on globals only: no locks, no logging, no allocation.
extern "C" void frameClockOnTick() {
    updateIntegerSkips();
    updateDayClock();
    dayClockOnTick(qpc());
    constPoolsOnTick();
    updateMenuTransitions();
    updateWorldAnims();
    updateTaskWaits();
    uint32_t* slots = (uint32_t*)g_fcPage;
    if (!slots) {
        return;
    }
    uint32_t n = 0, n60 = 0;
    if ((g_cfg.fixFrameClocks || g_cfg.fixFramePhases) && g_fps60 &&
        !g_timerFixMuted && !g_fcStranded) {
        uint32_t fps = g_fpsImmsFast ? 120u : 60u;
        bool stock60 = g_shadowOn && *g_shadowMode == 1;
        n = fps / (stock60 ? 60u : 30u);
        n60 = g_cfg.fixFrameClocks ? fps / 60u : 0;
    }
    frameClockStep(*(volatile uint32_t*)g_eng.frameCounter, n, n60, frameClockUHz(n60), !g_fps60,
                   slots);
    g_fcTicks++;
}

// The hook's stub, as one template so tools/verify_stubs.py can decode it and
// check the push/pop pairing and the call alignment. The relocated increment
// goes in front of it and the jump back after it. rsp is 16-aligned at the
// hook (the call at main+4B652B follows with nothing moving rsp), so the flags
// and seven pushes keep it aligned, and 0x80 holds xmm0-5 and the call's
// shadow space. Nothing is live at this point but the saves are total anyway:
// the stub leaves the game exactly the state the increment alone would.
static const uint8_t kFrameClockStub[] = {
    0x9C,                                      // pushfq
    0x50, 0x51, 0x52, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52, 0x41, 0x53,
    // push rax, rcx, rdx, r8, r9, r10, r11
    0x48, 0x81, 0xEC, 0x80, 0x00, 0x00, 0x00,  // sub rsp, 0x80
    0xF3, 0x0F, 0x7F, 0x44, 0x24, 0x20,        // movdqu [rsp+0x20], xmm0
    0xF3, 0x0F, 0x7F, 0x4C, 0x24, 0x30,        // movdqu [rsp+0x30], xmm1
    0xF3, 0x0F, 0x7F, 0x54, 0x24, 0x40,        // movdqu [rsp+0x40], xmm2
    0xF3, 0x0F, 0x7F, 0x5C, 0x24, 0x50,        // movdqu [rsp+0x50], xmm3
    0xF3, 0x0F, 0x7F, 0x64, 0x24, 0x60,        // movdqu [rsp+0x60], xmm4
    0xF3, 0x0F, 0x7F, 0x6C, 0x24, 0x70,        // movdqu [rsp+0x70], xmm5
    0x48, 0xB8, 0, 0, 0, 0, 0, 0, 0, 0,        // movabs rax, <frameClockOnTick>
    0xFF, 0xD0,                                // call rax
    0xF3, 0x0F, 0x6F, 0x44, 0x24, 0x20,        // movdqu xmm0, [rsp+0x20]
    0xF3, 0x0F, 0x6F, 0x4C, 0x24, 0x30,        // movdqu xmm1, [rsp+0x30]
    0xF3, 0x0F, 0x6F, 0x54, 0x24, 0x40,        // movdqu xmm2, [rsp+0x40]
    0xF3, 0x0F, 0x6F, 0x5C, 0x24, 0x50,        // movdqu xmm3, [rsp+0x50]
    0xF3, 0x0F, 0x6F, 0x64, 0x24, 0x60,        // movdqu xmm4, [rsp+0x60]
    0xF3, 0x0F, 0x6F, 0x6C, 0x24, 0x70,        // movdqu xmm5, [rsp+0x70]
    0x48, 0x81, 0xC4, 0x80, 0x00, 0x00, 0x00,  // add rsp, 0x80
    0x41, 0x5B, 0x41, 0x5A, 0x41, 0x59, 0x41, 0x58, 0x5A, 0x59, 0x58,
    // pop r11, r10, r9, r8, rdx, rcx, rax
    0x9D,                                      // popfq
};
static const size_t kFrameClockStubFnAt = 57;  // offset of the imm64 inside it

// Check every site, build the stub, then -- with the game's other threads
// suspended, so no displacement is ever fetched half-written -- put the hook in
// and retarget every read. The gates are widened later, by
// updateFrameClockGates, as the fps mode changes.
static void installFrameClocks() {
    if ((!g_cfg.fixFrameClocks && !g_cfg.fixIntegerSkips && !g_cfg.fixDayClock) || !g_eng.main ||
        !g_eng.frameCounter) {
        return;
    }
    uint8_t* main = g_eng.main;
    if (main + kFrameClockCounterRva != (uint8_t*)g_eng.frameCounter) {
        logf("frame clocks: the frame counter is not at main+%X in this build, not patched",
             kFrameClockCounterRva);
        return;
    }
    int bad = memcmp(main + kFrameClockTickRva, kFrameClockTickOrig,
                     sizeof(kFrameClockTickOrig)) != 0;
    const int reads = g_cfg.fixFrameClocks ? kFcReads : 0;
    const int gates = g_cfg.fixFrameClocks ? kFcGates : 0;
    for (int i = 0; i < reads; i++) {
        bad += memcmp(main + kFrameClockReads[i].rva, kFrameClockReads[i].orig,
                      kFrameClockReads[i].len) != 0;
    }
    for (int i = 0; i < gates; i++) {
        bad += memcmp(main + kFrameClockGates[i].rva, kFrameClockGates[i].orig,
                      kFrameClockGates[i].len) != 0;
    }
    if (bad) {
        logf("frame clocks: %d of %d sites do not match this build, not patched", bad,
             1 + reads + gates);
        return;
    }
    uint32_t* slots = frameClockSlots();
    if (!slots) {
        logf("frame clocks: no cave near main.dll, not patched");
        return;
    }
    // the stub: the relocated increment, the template, the jump back
    uint8_t* site = main + kFrameClockTickRva;
    uint8_t* stub = g_fcPage + kFcStubOff;
    size_t n = 0;
    if (!copyDisplaced(stub, kFrameClockTickOrig, sizeof(kFrameClockTickOrig), site)) {
        logf("frame clocks: the increment cannot be relocated, not patched");
        return;
    }
    n += sizeof(kFrameClockTickOrig);
    memcpy(stub + n, kFrameClockStub, sizeof(kFrameClockStub));
    uint64_t fn = (uint64_t)&frameClockOnTick;
    memcpy(stub + n + kFrameClockStubFnAt, &fn, 8);
    n += sizeof(kFrameClockStub);
    stub[n++] = 0xE9;
    int32_t back = (int32_t)((int64_t)(site + sizeof(kFrameClockTickOrig)) -
                             (int64_t)(stub + n + 4));
    memcpy(stub + n, &back, 4);
    n += 4;
    FlushInstructionCache(GetCurrentProcess(), stub, n);
    uint8_t hook[sizeof(kFrameClockTickOrig)];
    memset(hook, 0x90, sizeof(hook));
    hook[0] = 0xE9;
    int64_t rel = (int64_t)stub - (int64_t)(site + 5);
    if (rel != (int32_t)rel) {
        logf("frame clocks: cave out of reach, not patched");
        return;
    }
    int32_t rel32 = (int32_t)rel;
    memcpy(hook + 1, &rel32, 4);
    // every read's new displacement, worked out before anything is written
    int32_t disp[sizeof(kFrameClockReads) / sizeof(kFrameClockReads[0])];
    for (int i = 0; i < reads; i++) {
        const FrameClockRead& r = kFrameClockReads[i];
        int64_t d = (int64_t)(uint8_t*)&slots[r.slot] - (int64_t)(main + r.rva + r.len);
        if (d != (int32_t)d) {
            logf("frame clocks: counter slot out of reach of main+%X, not patched", r.rva);
            return;
        }
        disp[i] = (int32_t)d;
    }
    // all of them or none (writeGroup). The hook goes first, so a read can
    // only ever be left retargeted with the hook in to keep its counter.
    GroupWrite writes[1 + sizeof(kFrameClockReads) / sizeof(kFrameClockReads[0])];
    int nw = 0;
    writes[nw++] = {site, hook, kFrameClockTickOrig, sizeof(hook)};
    for (int i = 0; i < reads; i++) {
        const FrameClockRead& r = kFrameClockReads[i];
        writes[nw++] = {main + r.rva + r.dispOff, &disp[i], r.orig + r.dispOff, 4};
    }
    bool safe = suspendOthers();
    for (int i = 0; i < g_susCount; i++) {
        safe &= g_susRip[i] <= (DWORD64)site ||
                g_susRip[i] >= (DWORD64)(site + sizeof(kFrameClockTickOrig));
    }
    if (!safe) {
        resumeOthers();
        logf("frame clocks: could not suspend outside the tick window, not patched");
        return;
    }
    // the counters at the counter's value now, with the game stopped: exactly
    // what the reads would see, until the hook's first tick takes over
    g_fcs = FrameClockState{};
    for (int i = 0; i < kFcStamps; i++) {
        g_fcStamps[i] = g_cfg.fixFrameClocks ? (uint32_t*)(main + kFrameClockStamps[i]) : nullptr;
    }
    frameClockStep(*(volatile uint32_t*)g_eng.frameCounter, 0, 0, frameClockUHz(0), !g_fps60,
                   slots);
    int kept = writeGroup(writes, nw);
    g_fcHooked = kept > 0;
    g_fcStranded = kept > 0 && kept < nw;
    resumeOthers();
    g_fcReadsPatched = kept == nw ? reads : 0;
    g_fcGatesOk = kept == nw && g_cfg.fixFrameClocks;
    g_fcGateShift = 0xFF;
    if (kept == 0) {
        logf("frame clocks: a write failed; every write made was put back, not patched");
        return;
    }
    if (kept < nw) {
        logf("frame clocks: a write failed and one could not be put back; the first %d of %d"
             " writes stay, with every counter held at the frame counter itself, so each"
             " read is stock (frame phases too)", kept, nw);
        return;
    }
    logf("frame clocks: per-tick hook at main+%X, %d reads retargeted at %d counters,"
         " %d gates to widen", kFrameClockTickRva, reads, 2 + kFcHolds, gates);
}

// Called from the watcher alongside updateFrameGates, and gated the same way.
static void updateFrameClockGates() {
    if (!g_fcGatesOk) {
        return;
    }
    uint8_t shift = 0;
    if (g_cfg.fixFrameClocks && g_fps60 && !g_timerFixMuted) {
        shift = g_fpsImmsFast ? 2 : 1;
    }
    if (shift == g_fcGateShift) {
        return;
    }
    for (int i = 0; i < kFcGates; i++) {
        const FrameClockGate& g = kFrameClockGates[i];
        uint8_t want = (uint8_t)(((g.mask + 1u) << shift) - 1u);
        writeProtected(g_eng.main + g.rva + g.immOff, &want, 1);
    }
    g_fcGateShift = shift;
    logf("frame clock gates -> %s", shift ? "real time" : "stock (fast at 60 fps)");
}

// Offline self-test, driven by tools/verify_frame_clocks.py without the game:
// maps main.dll (DONT_RESOLVE_DLL_REFERENCES: nothing of the game runs), runs
// the real install, and writes the bytes it left (report.txt, sites.bin,
// stub.bin, slots.bin). Then it drives the counters through every combination
// of fps mode, stock context and the A/B key one tick at a time, the way the
// hook does, and writes every counter (clocks.csv) for the script to check.
extern "C" __declspec(dllexport) int OkamiFrameClockSelfTest(const char* mainPath,
                                                             const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixFrameClocks = true;
    if (!tick || !resolveFrameConfig(tick)) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    installFrameClocks();
    if (!g_fcHooked) {
        fprintf(rep, "FAIL install (see okami_hackfix.log)\n");
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\nslots %p\nstub %p\nfn %p\n", (void*)m, (void*)g_fcPage,
            (void*)(g_fcPage + kFcStubOff), (void*)&frameClockOnTick);
    snprintf(path, sizeof(path), "%s\\sites.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fwrite(g_eng.main + kFrameClockTickRva, 1, sizeof(kFrameClockTickOrig), f);
        for (int i = 0; i < kFcReads; i++) {
            fwrite(g_eng.main + kFrameClockReads[i].rva, 1, kFrameClockReads[i].len, f);
        }
        fclose(f);
    }
    snprintf(path, sizeof(path), "%s\\stub.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fwrite(g_fcPage + kFcStubOff, 1,
               sizeof(kFrameClockTickOrig) + sizeof(kFrameClockStub) + 5, f);
        fclose(f);
    }
    // the gates, widened for 120 and for 60 and put back
    static uint8_t shadow = 2;
    g_shadowMode = &shadow;
    g_shadowOn = true;
    g_timerFixMuted = 0;
    snprintf(path, sizeof(path), "%s\\gates.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        const int modes[3][2] = {{1, 1}, {1, 0}, {0, 0}};  // 120, 60, 30
        for (const auto& md : modes) {
            g_fps60 = md[0];
            g_fpsImmsFast = md[1];
            updateFrameClockGates();
            for (int i = 0; i < kFcGates; i++) {
                fwrite(g_eng.main + kFrameClockGates[i].rva, 1, kFrameClockGates[i].len, f);
            }
        }
        fclose(f);
    }
    // the counters, tick by tick
    volatile uint32_t* counter = g_eng.frameCounter;
    *counter = 5000;
    g_fcs = FrameClockState{};
    snprintf(path, sizeof(path), "%s\\clocks.csv", outDir);
    FILE* f = fopen(path, "w");
    if (!f) {
        fclose(rep);
        return 2;
    }
    // fps: the patch's mode, 30 being the patch off (F9); mode: the stock
    // game's mode byte -- the shadow while patched, with the real byte pinned
    // at 1, and the real byte itself with the patch off, where the game ticks
    // at 60 in mode 1; muted: the A/B key. Among them: 120 -> off -> 120 in
    // mode 1 throughout (the stock game at 60 Hz in between), and the stock
    // game changing its own mode with the patch off.
    static const struct { int ticks, fps, mode, muted; } kSegs[] = {
        {1200, 120, 2, 0}, {721, 120, 1, 0},  {1203, 120, 2, 0}, {600, 60, 2, 0},
        {601, 60, 1, 0},   {400, 30, 2, 0},   {300, 30, 1, 0},   {1200, 120, 2, 0},
        {7, 120, 1, 0},    {9, 120, 2, 0},    {401, 120, 2, 1},  {1080, 120, 2, 0},
        {1200, 120, 1, 0}, {500, 30, 1, 0},   {1441, 120, 1, 0}, {3, 60, 2, 0},
        {1500, 120, 2, 0}, {90, 30, 2, 0},    {1500, 120, 2, 0},
    };
    fprintf(f, "tick,fps,mode,muted,counter,S,U");
    for (int i = 0; i < kFcHolds; i++) {
        fprintf(f, ",H%d_%d", kFrameClockHolds[i].period, kFrameClockHolds[i].event);
    }
    for (int i = 0; i < kFcStamps; i++) {
        fprintf(f, ",stamp%d,set%d", i, i);
    }
    fprintf(f, "\n");
    uint32_t* slots = (uint32_t*)g_fcPage;
    int t = 0;
    volatile uint8_t* real = g_eng.modeByte;
    for (const auto& s : kSegs) {
        bool patched = s.fps != 30;
        g_fps60 = patched;
        g_fpsImmsFast = s.fps == 120;
        // as applyFpsMode leaves them
        g_shadowOn = patched;
        shadow = (uint8_t)s.mode;
        *real = patched ? (uint8_t)1 : (uint8_t)s.mode;
        g_timerFixMuted = s.muted;
        // the game's ticks per second, to place the stamps in time
        int hz = patched ? s.fps : (s.mode == 1 ? 60 : 30);
        for (int i = 0; i < s.ticks; i++, t++) {
            (*counter)++;
            frameClockOnTick();
            // the loading screen's stamps, stored as its code stores them (the
            // value of U), 2.5 s and 5 s before the end of any segment that
            // long, so that they ride through the transitions after it
            bool set[sizeof(kFrameClockStamps) / sizeof(kFrameClockStamps[0])] = {};
            for (int k = 0; k < kFcStamps; k++) {
                int before = (k + 1) * hz * 5 / 2;
                if (s.ticks - i == before) {
                    *g_fcStamps[k] = slots[1];
                    set[k] = true;
                }
            }
            fprintf(f, "%d,%d,%d,%d,%u,%u,%u", t, s.fps, s.mode, s.muted, *counter,
                    slots[0], slots[1]);
            for (int k = 0; k < kFcHolds; k++) {
                fprintf(f, ",%u", slots[2 + k]);
            }
            for (int k = 0; k < kFcStamps; k++) {
                fprintf(f, ",%u,%d", *g_fcStamps[k], (int)set[k]);
            }
            fprintf(f, "\n");
        }
    }
    fclose(f);
    fprintf(rep, "PASS\n");
    fclose(rep);
    return 0;
}

// ---------------------------------------------------------------------------
#include "integer_skip_runtime.h"
#include "day_clock_runtime.h"
#include "brush_watch_runtime.h"

// Per-tick phase steps at 60 fps
//
// Besides the integer action timers the engine runs a great many float per-tick
// counters -- effect lifetimes, fade and flash meters, scroll offsets,
// oscillator phases. They share one shape: load a field, add or subtract a
// literal, store it back, check the limit.
//
//     movss  xmm0, dword ptr [rbx+0x19C]
//     subss  xmm0, dword ptr [rip+...]      ; = 1.0
//     movss  dword ptr [rbx+0x19C], xmm0
//     comiss xmm3, xmm0                     ; espEmitter lifetime, ticking out
//
// 698 sites step a field by a literal and two of them consult the time scale,
// so at 60 fps they all run down twice as fast. Halving the *step* rather than
// skipping it on alternate ticks keeps the motion smooth: 60 half-size steps a
// second instead of 30 full ones.
//
// The fix needs no code injection at all. Every one of these is the 8-byte
// rip-relative form, so only the 4-byte displacement is rewritten, to point at
// a private copy of the literal that this patch keeps multiplied by the time
// scale. The literals are shared -- one address holds the 1.0 that hundreds of
// instructions read -- but retargeting a single instruction cannot disturb any
// other reader, and switching the fix off just writes the stock value back into
// the private copy.
//
// Only sites whose field is compared or clamped nearby are included. A one-off
// nudge in an event handler looks identical in isolation, and the limit check
// is what separates them; the split is clean, since the clamped sites step by
// 0.05 / 0.1 / 0.02 and the unclamped ones by 10 / 20 / 40 / 64 / 100.
//
// src/phase_steps.h is generated by tools/find_phase_steps.py.
// ---------------------------------------------------------------------------

#include "phase_steps.h"
#include "decay_factors.h"

// A pool of private copies of engine constants. Each pool owns a run of floats
// in a cave; an instruction is retargeted by rewriting its 4-byte displacement
// to point at the pool's copy of the constant it used to read. Constants are
// shared in .rdata -- one address holds the 1.0 that hundreds of instructions
// read -- so a pool must never write back to the original.
struct ConstPool {
    float* slot;            // the live values the retargeted code reads
    float orig[128];        // what the engine shipped
    uint32_t rva[128];      // which .rdata float each slot shadows
    int count;
    int patched;
};

static ConstPool g_phasePool = {nullptr, {0}, {0}, 0, 0};
static ConstPool g_decayPool = {nullptr, {0}, {0}, 0, 0};
static volatile LONG g_phaseFixMuted = 0;  // set by the phase toggle key, for A/B
static volatile LONG g_poolsReady = 0;      // installConstPools has finished with both pools
static float g_poolScale = 1.0f;            // the scale the slots hold now; 1 = as shipped
static volatile LONG g_poolN = 1;           // the same as ticks per stock tick, for display

// ---------------------------------------------------------------------------
// Reporting the A/B state
//
// This exists because a whole test session was silently invalid. The timer A/B
// key had no log line of its own: the only output it could produce came from
// updateActionTimers(), which prints when the mask byte *changes*. In 30 fps
// mode that mask is 0 whether the fix is muted or not, so pressing the key
// there flipped the mute and printed nothing at all. The log then showed the
// three timer families going stock on the way into 30 fps and never coming
// back, and every measurement taken after that point was of a 120 fps game
// running stock 30 fps timer semantics -- every action duration, every wind-up
// and every input window a quarter of its proper length.
//
// A toggle that can change the game without leaving a trace is worse than no
// toggle. Every one of them now reports, and the whole state is dumped on each
// fps change, so a log can always be read back with confidence.
// ---------------------------------------------------------------------------

static const char* abState(bool enabled, volatile LONG& muted) {
    return !enabled ? "off(ini)" : (muted ? "MUTED" : "on");
}

// The compact form, for lines that get read one at a time.
//
// Logging a *transition* is only useful to a reader who has seen every earlier
// transition. That assumption is what made the last session unreadable: one
// toggle went unlogged, and every measurement after it was quietly taken in a
// state the log never mentioned again. A line that carries its own state can be
// checked on its own, which is the property that actually matters -- so the two
// kinds of line that get analysed, `jump:` and `status:`, both end with this.
//
//   t = the action timer mask        (0 stock, 1 at 60 fps, 3 at 120 fps)
//   s = the movement scale           (1.000 stock, 0.500 at 60, 0.250 at 120)
//   j = the jump and launch scale    (1.000 stock, 2.000 at 60, 4.000 at 120)
//   m = the integer mode multiplier  (2 stock and at 60, 4 at 120)
static void fixFingerprint(char* out, size_t n) {
    snprintf(out, n, "fix[t%u s%.3f j%.3f m%d]",
             g_timerMask ? (unsigned)*g_timerMask : 0u,
             g_playerScale ? (double)*g_playerScale : 1.0,
             g_jumpScale ? (double)*g_jumpScale : 1.0,
             g_modeMult ? (int)*g_modeMult : 2);
}

static void logFixState(const char* why) {
    // the frame-counter clocks follow the timer key, like the frame gates
    const char* clocks = !g_cfg.fixFrameClocks ? "off(ini)"
                         : !g_fcHooked         ? "NOT INSTALLED"
                                               : abState(true, g_timerFixMuted);
    logf("fix state (%s): fps=%s | movement=%s jump=%s timers=%s phase=%s clocks=%s integers=%s"
         " day=%s menus=%s world=%s | mask=%u speed=x%.3f jump=x%.3f",
         why,
         g_fps60 ? (g_fpsImmsFast ? "120" : "60") : "30",
         abState(g_cfg.fixRunSpeed, g_speedFixMuted),
         abState(g_cfg.fixJumpHeight, g_jumpFixMuted),
         abState(g_cfg.fixActionTimers, g_timerFixMuted),
         abState(g_cfg.fixPhaseSteps, g_phaseFixMuted), clocks, integerSkipState(),
         dayClockState(), menuTransitionState(), worldAnimState(),
         g_timerMask ? (unsigned)*g_timerMask : 0u,
         g_playerScale ? (double)*g_playerScale : 1.0,
         g_jumpScale ? (double)*g_jumpScale : 1.0);
}

static int poolSlotFor(ConstPool& pool, uint32_t constRva) {
    for (int i = 0; i < pool.count; i++) {
        if (pool.rva[i] == constRva) {
            return i;
        }
    }
    if (pool.count >= (int)(sizeof(pool.rva) / sizeof(pool.rva[0]))) {
        return -1;
    }
    pool.rva[pool.count] = constRva;
    return pool.count++;
}

// Point one instruction's rip-relative operand at this pool's copy of its
// constant. Every site is the 8-byte form, so the displacement is at +4 and
// nothing about the instruction's length or flags changes.
static bool retargetConst(ConstPool& pool, uint32_t siteRva, uint32_t constRva,
                          const uint8_t* orig) {
    uint8_t* site = g_eng.main + siteRva;
    if (memcmp(site, orig, 8) != 0) {
        return false;
    }
    int slot = poolSlotFor(pool, constRva);
    if (slot < 0) {
        return false;
    }
    pool.orig[slot] = *(const float*)(g_eng.main + constRva);
    pool.slot[slot] = pool.orig[slot];
    int64_t rel = (int64_t)(uint8_t*)&pool.slot[slot] - (int64_t)(site + 8);
    if (rel != (int32_t)rel) {
        return false;
    }
    int32_t disp = (int32_t)rel;
    if (!writeProtected(site + 4, &disp, sizeof(disp))) {
        return false;
    }
    pool.patched++;
    return true;
}

static void installConstPools() {
    size_t bytes = sizeof(float) * 128;
    if (g_cfg.fixPhaseSteps && g_eng.main) {
        uint8_t* cave = allocNear(g_eng.main, bytes);
        if (!cave) {
            logf("phase steps: no data cave near main.dll, not patched");
        } else {
            g_phasePool.slot = (float*)cave;
            const int total = (int)(sizeof(kPhaseSites) / sizeof(kPhaseSites[0]));
            for (int i = 0; i < total; i++) {
                retargetConst(g_phasePool, kPhaseSites[i].rva, kPhaseSites[i].constRva,
                              kPhaseSites[i].orig);
            }
            logf("phase steps: %d of %d instructions retargeted over %d constants",
                 g_phasePool.patched, total, g_phasePool.count);
        }
    }
    if (g_cfg.fixDecay && g_eng.main) {
        uint8_t* cave = allocNear(g_eng.main, bytes);
        if (!cave) {
            logf("decay factors: no data cave near main.dll, not patched");
        } else {
            g_decayPool.slot = (float*)cave;
            const int total = (int)(sizeof(kDecaySites) / sizeof(kDecaySites[0]));
            for (int i = 0; i < total; i++) {
                retargetConst(g_decayPool, kDecaySites[i].rva, kDecaySites[i].constRva,
                              kDecaySites[i].orig);
            }
            logf("decay factors: %d of %d instructions retargeted over %d factors",
                 g_decayPool.patched, total, g_decayPool.count);
        }
    }
    // the per-tick hook may already be running: it keeps the slots from here on
    InterlockedExchange(&g_poolsReady, 1);
}

// What one tick is worth, as a fraction of a stock tick. That is the time scale
// (0.5 at 60 fps, 0.25 at 120) where the stock game ticks at 30, but not every
// context does: the options pages, the memory-card screens, the pause menu's
// interior and the title run at 60 in the stock game (mode byte 1), and every
// per-tick step there runs 60 times a second in the stock game too. The tracer
// session saw four of these sites there: the save screen's wave (1C5059), the
// pause menu's 42EEDC and 42EF08, and the scene transition's 439B48, in both
// contexts. Scaled by the time scale alone they ran at half their stock speed
// at both 60 and 120 fps. So in those contexts a tick is worth twice the time
// scale: 0.5 at 120 fps, and 1 -- the shipped value -- at 60. The context is
// the shadow mode byte, as for the frame phases; without the shadow it stays
// the time scale alone, which is right in play.
static float constPoolScale() {
    if (!g_fps60 || g_phaseFixMuted || !g_eng.timeScale) {
        return 1.0f;
    }
    float ts = *(volatile float*)g_eng.timeScale;
    if (!(ts > 0.05f && ts <= 1.0f)) {
        return 1.0f;
    }
    if (g_shadowOn && *g_shadowMode == 1) {
        ts *= 2.0f;
    }
    return ts < 1.0f ? ts : 1.0f;
}

// A linear step scales with it; an exponential decay is raised to it, so that
// the same fraction is lost per second rather than per tick.
static void applyConstPools(float scale) {
    if (g_phasePool.slot && g_cfg.fixPhaseSteps) {
        for (int i = 0; i < g_phasePool.count; i++) {
            g_phasePool.slot[i] = g_phasePool.orig[i] * scale;
        }
    }
    if (g_decayPool.slot && g_cfg.fixDecay) {
        for (int i = 0; i < g_decayPool.count; i++) {
            g_decayPool.slot[i] =
                (scale >= 0.999f) ? g_decayPool.orig[i] : powf(g_decayPool.orig[i], scale);
        }
    }
    g_poolScale = scale;
    InterlockedExchange(&g_poolN, (LONG)(1.0f / scale + 0.5f));
}

// From the per-tick hook, on the game thread, before the dispatcher runs this
// tick's updates: the slots change on the very tick the context does. A
// context change is a pause menu opening, so the few dozen multiplies and
// powf calls happen that rarely, never per tick.
static void constPoolsOnTick() {
    if (!g_poolsReady) {
        return;
    }
    float s = constPoolScale();
    if (s != g_poolScale) {
        applyConstPools(s);
    }
}

// From the watcher: the fallback without the per-tick hook, then at most one
// 10 ms pass behind a change. With the hook in, the hook alone writes the
// slots, so the two threads never race over them.
static void updateConstPools() {
    if (g_fcHooked || !g_poolsReady) {
        return;
    }
    float s = constPoolScale();
    if (s != g_poolScale) {
        applyConstPools(s);
    }
}

#include "menu_transition_runtime.h"
#include "world_anim_runtime.h"
#include "enemy_watch_runtime.h"
#include "task_wait_runtime.h"

// Offline self-test, driven by tools/verify_const_pools.py. Maps main.dll
// without running any of it and runs the real install, then drives the slots
// one tick at a time through every combination of fps, stock context, the
// phase key and the shadow's availability: through the per-tick hook, with a
// watcher pass before each tick that must not write, and through the watcher's
// fallback. Writes the installed instructions (sites.bin), each pool's layout
// (pools.csv) and every slot after every tick (ticks.csv), for the script to
// check against an independent computation and to emulate the real
// instructions with.
extern "C" __declspec(dllexport) int OkamiConstPoolSelfTest(const char* mainPath,
                                                            const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixPhaseSteps = true;
    g_cfg.fixDecay = true;
    if (!tick || !resolveFrameConfig(tick) || !g_eng.timeScale) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    installConstPools();
    const int nPhase = (int)(sizeof(kPhaseSites) / sizeof(kPhaseSites[0]));
    const int nDecay = (int)(sizeof(kDecaySites) / sizeof(kDecaySites[0]));
    fprintf(rep, "main %p\nphase %p %d %d\ndecay %p %d %d\n", (void*)m, (void*)g_phasePool.slot,
            g_phasePool.count, g_phasePool.patched, (void*)g_decayPool.slot, g_decayPool.count,
            g_decayPool.patched);
    if (!g_phasePool.slot || !g_decayPool.slot || g_phasePool.patched != nPhase ||
        g_decayPool.patched != nDecay) {
        fprintf(rep, "FAIL install\n");
        fclose(rep);
        return 1;
    }
    int fails = 0;
    snprintf(path, sizeof(path), "%s\\sites.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& s : kPhaseSites) fails += fwrite(g_eng.main + s.rva, 1, 8, f) != 8;
        for (const auto& s : kDecaySites) fails += fwrite(g_eng.main + s.rva, 1, 8, f) != 8;
        fclose(f);
    } else {
        fails++;
    }
    snprintf(path, sizeof(path), "%s\\pools.csv", outDir);
    if (FILE* f = fopen(path, "w")) {
        fprintf(f, "pool,idx,rva,orig\n");
        const ConstPool* pools[] = {&g_phasePool, &g_decayPool};
        for (int p = 0; p < 2; p++) {
            for (int i = 0; i < pools[p]->count; i++) {
                uint32_t bits;
                memcpy(&bits, &pools[p]->orig[i], 4);
                fprintf(f, "%s,%d,%X,%08X\n", p ? "decay" : "phase", i, pools[p]->rva[i], bits);
            }
        }
        fclose(f);
    } else {
        fails++;
    }
    // fps 30 is the patch off (F9); mode is the stock game's mode byte (0 before
    // the game first writes it); shadow 0 is a shadow that failed to install;
    // bad is a time scale outside anything flower_tick writes
    static uint8_t shadow = 2;
    g_shadowMode = &shadow;
    enum { kHook, kWatcher };
    static const struct { int ticks, path, fps, mode, muted, shadow, bad; } kSegs[] = {
        {12, kHook, 120, 2, 0, 1, 0}, {12, kHook, 120, 1, 0, 1, 0}, {12, kHook, 120, 2, 0, 1, 0},
        {12, kHook, 60, 2, 0, 1, 0},  {12, kHook, 60, 1, 0, 1, 0},  {12, kHook, 30, 2, 0, 0, 0},
        {12, kHook, 30, 1, 0, 0, 0},  {12, kHook, 120, 1, 1, 1, 0}, {12, kHook, 120, 1, 0, 1, 0},
        {12, kHook, 60, 1, 1, 1, 0},  {12, kHook, 60, 1, 0, 1, 0},  {12, kHook, 120, 0, 0, 1, 0},
        {12, kHook, 120, 1, 0, 0, 0}, {12, kHook, 120, 2, 0, 0, 0}, {1, kHook, 120, 1, 0, 1, 0},
        {1, kHook, 120, 2, 0, 1, 0},  {2, kHook, 120, 1, 0, 1, 0},  {1, kHook, 60, 1, 0, 1, 0},
        {1, kHook, 120, 1, 0, 1, 0},  {12, kHook, 120, 2, 0, 1, 1}, {12, kHook, 120, 1, 0, 1, 0},
        {12, kWatcher, 120, 2, 0, 1, 0}, {12, kWatcher, 120, 1, 0, 1, 0},
        {12, kWatcher, 60, 1, 0, 1, 0},  {12, kWatcher, 60, 2, 0, 1, 0},
        {12, kWatcher, 30, 1, 0, 0, 0},  {12, kWatcher, 120, 1, 1, 1, 0},
        {12, kWatcher, 120, 1, 0, 0, 0}, {12, kHook, 120, 1, 0, 1, 0},
    };
    snprintf(path, sizeof(path), "%s\\ticks.csv", outDir);
    FILE* f = fopen(path, "w");
    if (!f) {
        fclose(rep);
        return 2;
    }
    fprintf(f, "tick,path,fps,mode,muted,shadow,bad,n,watcher_wrote,phase,decay\n");
    const size_t phaseBytes = sizeof(float) * (size_t)g_phasePool.count;
    const size_t decayBytes = sizeof(float) * (size_t)g_decayPool.count;
    float before[256];
    int tickNo = 0;
    for (const auto& s : kSegs) {
        for (int i = 0; i < s.ticks; i++, tickNo++) {
            // the state as applyFpsMode and the keys leave it, and the time
            // scale as flower_tick writes it before its counter goes up: the
            // real byte pinned at 1 while patched, the stock game's own at 30
            g_fps60 = s.fps != 30;
            g_fpsImmsFast = s.fps == 120;
            g_phaseFixMuted = s.muted;
            g_shadowOn = s.shadow != 0;
            shadow = (uint8_t)s.mode;
            *(volatile float*)g_eng.timeScale = s.bad ? 0.0f
                                                : s.fps == 120 ? 0.25f
                                                : s.fps == 60  ? 0.5f
                                                : s.mode == 1  ? 0.5f
                                                               : 1.0f;
            int wrote = 0;
            if (s.path == kHook) {
                g_fcHooked = true;
                memcpy(before, g_phasePool.slot, phaseBytes);
                memcpy(before + g_phasePool.count, g_decayPool.slot, decayBytes);
                updateConstPools();  // the watcher's pass, which must leave them alone
                wrote = memcmp(before, g_phasePool.slot, phaseBytes) != 0 ||
                        memcmp(before + g_phasePool.count, g_decayPool.slot, decayBytes) != 0;
                frameClockOnTick();
            } else {
                g_fcHooked = false;
                updateConstPools();
            }
            fprintf(f, "%d,%s,%d,%d,%d,%d,%d,%ld,%d,", tickNo, s.path == kHook ? "hook" : "watcher",
                    s.fps, s.mode, s.muted, s.shadow, s.bad, (long)g_poolN, wrote);
            for (int k = 0; k < g_phasePool.count; k++) {
                uint32_t bits;
                memcpy(&bits, &g_phasePool.slot[k], 4);
                fprintf(f, "%08X", bits);
            }
            fputc(',', f);
            for (int k = 0; k < g_decayPool.count; k++) {
                uint32_t bits;
                memcpy(&bits, &g_decayPool.slot[k], 4);
                fprintf(f, "%08X", bits);
            }
            fputc('\n', f);
        }
    }
    fclose(f);
    g_fcHooked = false;
    fprintf(rep, "ticks %d\n%s\n", tickNo, fails ? "FAIL" : "PASS");
    fclose(rep);
    return fails ? 1 : 0;
}

// ---------------------------------------------------------------------------
// Experimental 120 fps
//
// The engine's frame config is a power-of-two ladder, written every frame by
// flower_tick (main+0x4B646C) and selected by the mode byte:
//
//     30 fps   timeScale 1.0    divider 4   shift 0   fps 30
//     60 fps   timeScale 0.5    divider 2   shift 1   fps 60
//
// 120 fps is the next rung: timeScale 0.25, divider 1, shift 2, fps 120. All
// four are plain immediates in the mode-1 branch, so the patch retunes them,
// and all four were checked against every reader in the image:
//
//   * the shift flag is only ever loaded into ecx and used as `shl reg, cl`
//     (322 sites), so a 2 quadruples an input window as cleanly as a 1 doubles
//     it;
//   * the fps byte is consumed as a rate, never compared against 60. Its
//     readers take fps/2, fps/30 or fps*2, all of which land on exact integers
//     at 120 and the largest of which (fps*2 into a byte field) reaches 240;
//   * the time scale is only ever multiplied, never divided by or compared;
//   * the frame divider has no reader at all. There is no rip-relative access
//     to main+0xB6AC3C outside the two writes, and its address appears nowhere
//     in the image, so nothing can be reading it indirectly either.
//
// The real gate is elsewhere: the game paces itself in sub_4B6BF0, the wait
// callback GXPacket::update runs each frame, and that starts from a hard-coded
// `mov r8d, 60` before dividing by the frame-skip setting. Left alone it would
// hold the engine to 60 frames a second while the config told every timer that
// a frame was worth a quarter of a step, and the game would run at half speed.
// It is the fifth immediate in the ladder below.
//
// Everything this patch fixes is expressed in terms of the engine's own time
// scale rather than a hard-coded half, so the movement, launch, phase and decay
// fixes all follow to 0.25 on their own. The action timers need the tick mask
// widened from 1 to 3, which makes them count down every fourth tick.
//
// This is experimental. The divider at main+0xB6AC3C is consumed by
// flower_kernel.dll and what it does with a 1 has not been established, and no
// part of this has been play-tested.
// ---------------------------------------------------------------------------

struct FpsImm {
    uint32_t rva;      // the instruction
    uint8_t len;       // its length
    uint8_t immOff;    // where the immediate starts
    uint8_t immLen;    // how wide it is
    uint32_t stock;    // the 60 fps value
    uint32_t fast;     // the 120 fps value
    const char* what;
};

static const FpsImm kFpsImms[] = {
    {0x4B6491, 7, 6, 1, 0x3C, 0x78, "fps byte"},
    {0x4B6498, 10, 6, 4, 0x3F000000, 0x3E800000, "time scale"},  // 0.5 -> 0.25
    {0x4B64A2, 10, 6, 4, 2, 1, "frame divider"},
    {0x4B64AC, 10, 6, 4, 1, 2, "duration shift"},
    {0x4B6BFD, 6, 2, 4, 0x3C, 0x78, "frame limiter cap"},  // mov r8d, 60
};

static void checkFpsImms() {
    if (!g_eng.main) {
        return;
    }
    for (auto& f : kFpsImms) {
        uint32_t cur = 0;
        memcpy(&cur, g_eng.main + f.rva + f.immOff, f.immLen);
        if (cur != f.stock && cur != f.fast) {
            logf("120 fps: main+%X does not hold the expected %s, not available", f.rva, f.what);
            return;
        }
    }
    g_fpsImmsOk = true;
}

// Retune flower_tick's mode-1 branch between the 60 and 120 fps rungs.
static void applyFpsLadder(bool fast) {
    if (!g_fpsImmsOk || fast == g_fpsImmsFast) {
        return;
    }
    for (auto& f : kFpsImms) {
        uint32_t want = fast ? f.fast : f.stock;
        if (!writeProtected(g_eng.main + f.rva + f.immOff, &want, f.immLen)) {
            logf("120 fps: could not write the %s, leaving the ladder alone", f.what);
            return;
        }
    }
    g_fpsImmsFast = fast;
    InterlockedExchange(&g_targetHz, fast ? 120 : 60);
    g_gridEpoch = 0;
    setConfigRefleshRate(fast ? 120.0f : 60.0f);
    logf("frame ladder -> %d fps (timeScale %s, shift %d)", fast ? 120 : 60,
         fast ? "0.25" : "0.5", fast ? 2 : 1);
}

static bool g_speedFixTried = false;

// ---------------------------------------------------------------------------
// A decay the finder could not see
//
// find_decay_factors.py matches the damp that reads its constant inline:
//
//     movss xmm0, [rsi+0xE48]
//     mulss xmm0, dword ptr [rip+K]
//     movss [rsi+0xE48], xmm0
//
// When a function uses the same constant more than once the compiler hoists
// the load into a callee-saved register and the damp loses its rip operand:
//
//     movss xmm6, dword ptr [rip+K]     ... hundreds of bytes earlier
//     mulss xmm0, xmm6
//
// Same arithmetic, nothing left to match on. main+3B55C0 is one of these. It
// is hspeed *= 0.1 once per tick in the jump handler, and the first harness
// run caught it taking Amaterasu from 1.05917 to 0.00330 units per tick in six
// ticks, while she was still on the ground in the jump wind-up. She then
// launched with a third of a percent of her run speed. At 30 fps the same code
// runs a quarter as often, which is the whole difference.
//
// All eight sites found this way damp the one field, pl00+0xE48. The factor is
// a surviving fraction, so it takes the exponent directly: k^ts. 0.1 becomes
// 0.562 at 120 fps.
//
// The load is verified and left alone -- it may feed other things. What gets
// replaced is the multiply and the store after it, by a detour that multiplies
// by a private k^ts slot instead of the register. The register is never
// assumed to survive; only to have held k at the moment of the multiply, which
// is the thing the tool proves.
//
// src/hoisted_decay.h is generated by tools/find_hoisted_decay.py.
// ---------------------------------------------------------------------------

#include "hoisted_decay.h"

#define HOIST_N ((int)(sizeof(kHoistDecaySites) / sizeof(kHoistDecaySites[0])))
static float* g_hoistScale = nullptr;  // one k^ts per site
static int g_hoistPatched = 0;

static void installHoistDecay(uint8_t*& cur, uint8_t* end, float* slots) {
    if (!g_cfg.fixHoistDecay) {
        return;
    }
    g_hoistScale = slots;
    int done = 0, skipped = 0;
    for (int i = 0; i < HOIST_N; i++) {
        const HoistDecaySite& h = kHoistDecaySites[i];
        uint8_t* load = g_eng.main + h.loadRva;
        uint8_t* site = g_eng.main + h.mulRva;
        size_t span = (size_t)h.mulLen + (size_t)h.storeLen;
        slots[i] = h.k;
        // the load is the proof the register holds k; if it has moved, so has
        // the reasoning, and the site is left alone rather than guessed at
        if (memcmp(load, h.loadOrig, h.loadLen) != 0 ||
            memcmp(site, h.mulOrig, h.mulLen) != 0 ||
            memcmp(site + h.mulLen, h.storeOrig, h.storeLen) != 0) {
            logf("hoisted decay: %s does not match this build, not patched", h.what);
            skipped++;
            continue;
        }
        if (h.xmmD > 7 || span < 5 || (size_t)(end - cur) < span + 32) {
            skipped++;
            continue;
        }
        uint8_t* code = cur;
        size_t n = 0;
        code[n++] = 0xF3;
        code[n++] = 0x0F;
        code[n++] = 0x59;                                  // mulss xmmD, [rip+slot]
        code[n++] = (uint8_t)(0x05 | (h.xmmD << 3));
        int32_t dataDisp = (int32_t)((uint8_t*)&slots[i] - (code + n + 4));
        memcpy(code + n, &dataDisp, 4);
        n += 4;
        if (!copyDisplaced(code + n, h.storeOrig, h.storeLen, site + h.mulLen)) {
            skipped++;
            continue;
        }
        n += h.storeLen;
        code[n++] = 0xE9;
        int32_t back = (int32_t)((int64_t)(site + span) - (int64_t)(code + n + 4));
        memcpy(code + n, &back, 4);
        n += 4;
        int64_t rel = (int64_t)code - (int64_t)(site + 5);
        if (rel != (int32_t)rel) {
            skipped++;
            continue;
        }
        uint8_t patch[16];
        memset(patch, 0x90, sizeof(patch));
        patch[0] = 0xE9;
        int32_t rel32 = (int32_t)rel;
        memcpy(patch + 1, &rel32, 4);
        if (!writeProtected(site, patch, span)) {
            skipped++;
            continue;
        }
        cur = code + ((n + 15) & ~(size_t)15);
        done++;
    }
    g_hoistPatched = done;
    logf("hoisted decays: %d of %d speed damps scaled%s", done, HOIST_N,
         skipped ? " (some skipped, see above)" : "");
}

// A surviving fraction takes the exponent directly, the same rule the mode
// damping tables follow.
static void updateHoistDecay(bool on, float ts) {
    if (!g_hoistScale || !g_hoistPatched) {
        return;
    }
    for (int i = 0; i < HOIST_N; i++) {
        float want = (on && ts < 0.999f) ? powf(kHoistDecaySites[i].k, ts)
                                         : kHoistDecaySites[i].k;
        if (g_hoistScale[i] != want) {
            g_hoistScale[i] = want;
        }
    }
}

// ---------------------------------------------------------------------------
// How everything in the game turns
//
// main+2DA510 is the angular approach, and 162 call sites use it:
//
//     facing = wrap(facing + k * wrap(wrap(target) - wrap(facing)))
//
// with main+13F2E0 as the wrap to (-PI, PI]. k arrives in xmm2 and is a
// per-tick blend, so the fraction of the gap that SURVIVES a tick is (1 - k)
// and that is the quantity carrying the exponent:
//
//     k' = 1 - (1 - k)^ts
//
// The player ground turn passes 0.6 (main+3A7390), which should be 0.205 at
// 120 fps; unpatched she reaches the target heading three to four times too
// quickly. About half the call sites pass k in a register rather than a
// constant, so there is nothing to retarget at the call sites and the fix has
// to be here, at the one function they all go through.
//
// ts is only ever 1, 1/2 or 1/4, so the exponent is a chain of square roots
// rather than a call to powf, which matters when this runs for every actor
// every tick: 0 of them at 30 fps, one at 60, two at 120.
//
// The transform is skipped unless 0 < k < 1. Outside that range (1 - k)^ts is
// either a NaN or a sign flip, and a caller passing k >= 1 means "snap to the
// target", which is already rate-independent.
//
// xmm3 and xmm4 are scratch: this function takes three float arguments, so
// xmm0-xmm2 are live and xmm3-xmm5 are volatile and dead at entry.
//
// Not every caller passes a stock per-tick blend, and converting the ones
// that do not is wrong twice over (tools/gen_turn_callers.py audits all 163,
// docs/animation/turn_callers.csv has the result):
//
//   37 build k from the engine's own per-mode table, g - 1 with g from a
//      {g^0.5, g} pair that mode_constants.h already rewrites to {g^ts, g}.
//      The jump handler's airborne steering (main+3B5530) passed
//      1.1^0.25 - 1 = 0.0241 at 120 fps and the hook made it 0.0061, a
//      quarter of the stock steering; stock wants 1 - 0.9^0.25 = 0.0260.
//      Each of those table reads is retargeted at a private {fast, stock}
//      pair whose fast slot holds the stock g while the hook converts, so the
//      hook sees the stock coefficient and converts it once, and holds the
//      real table's value while it does not, so the site reads what it did.
//   4  pass something that is not a per-tick blend at all: the keyframe
//      interpolator's fraction between two keys, and the motion blend-in's
//      1/n. Those calls are retargeted past the conversion, at the relocated
//      prologue the stub ends with.
//
// Both go in with the hook or not at all: the hook alone would double-scale
// every table caller. If a write fails the ones made are put back, and the
// stub's space in the cave goes back to the installers after this one. If one
// cannot be put back, the rest stay too (writeGroup) and pointing into the
// cave, so the cave is kept and the fix stranded: the count held at 0, so the
// stub goes straight to the relocated prologue, and the pairs kept at the real
// table's values, so a retargeted read reads what the original does.
// ---------------------------------------------------------------------------

#include "turn_callers.h"

static const uint32_t kTurnRva = 0x2DA510;
static const uint32_t kTurnResume = 0x2DA519;
// sub rsp, 0x58 ; movaps [rsp+0x40], xmm6 -- 9 bytes, neither rip-relative,
// so the pair relocates by plain copy
static const uint8_t kTurnOrig[9] = {0x48, 0x83, 0xEC, 0x58,
                                     0x0F, 0x29, 0x74, 0x24, 0x40};
static const int kTurnPairs = (int)(sizeof(kTurnPairEntries) / sizeof(kTurnPairEntries[0]));
static const int kTurnReads = (int)(sizeof(kTurnTableReads) / sizeof(kTurnTableReads[0]));
static const int kTurnBypasses = (int)(sizeof(kTurnBypass) / sizeof(kTurnBypass[0]));
static uint8_t* g_turnSqrtCount = nullptr;  // 0 at 30 fps, 1 at 60, 2 at 120
static float* g_turnPairs = nullptr;         // {fast, stock} per kTurnPairEntries
static uint8_t* g_turnPlain = nullptr;       // the relocated prologue: no conversion
static bool g_turnInstalled = false;         // all of it went in: the hook may convert
static bool g_turnStranded = false;          // part of it is stuck in: kept stock

// Keep each private pair's fast slot at the stock g while the hook converts,
// and at whatever the real table holds (mode_constants.h's g^ts, or the
// shipped g^0.5) while it does not. Called whenever either can change.
static void updateTurnPairs() {
    if (!g_turnPairs || !(g_turnInstalled || g_turnStranded)) {
        return;
    }
    bool converting = *g_turnSqrtCount != 0;
    for (int i = 0; i < kTurnPairs; i++) {
        float want = converting ? g_turnPairs[2 * i + 1]
                                : *(volatile float*)(g_eng.main + kTurnPairEntries[i]);
        if (g_turnPairs[2 * i] != want) {
            g_turnPairs[2 * i] = want;
        }
    }
}

static bool installTurnRate(uint8_t*& cur, uint8_t* end, uint8_t* countByte, float* one,
                            float* zero) {
    if (!g_cfg.fixTurnRate || !g_eng.main) {
        return false;
    }
    uint8_t* main = g_eng.main;
    uint8_t* site = main + kTurnRva;
    int bad = memcmp(site, kTurnOrig, sizeof(kTurnOrig)) != 0;
    for (int i = 0; i < kTurnReads; i++) {
        bad += memcmp(main + kTurnTableReads[i].rva, kTurnTableReads[i].orig,
                      kTurnTableReads[i].len) != 0;
    }
    for (int i = 0; i < kTurnBypasses; i++) {
        bad += memcmp(main + kTurnBypass[i].rva, kTurnBypass[i].orig, 5) != 0;
    }
    if (bad) {
        logf("turn rate: %d of %d sites do not match this build, not patched", bad,
             1 + kTurnReads + kTurnBypasses);
        return false;
    }
    if ((size_t)(end - cur) < 128 + 16 + (size_t)kTurnPairs * 8) {
        logf("turn rate: code cave full, not patched");
        return false;
    }
    *one = 1.0f;
    *zero = 0.0f;
    *countByte = 0;
    g_turnSqrtCount = countByte;

    uint8_t* code = cur;
    size_t n = 0;
    // rip is the address of the NEXT instruction, so anything that follows the
    // displacement counts. `cmp byte [rip+d], imm8` carries a trailing imm8 and
    // reads one byte past the intended target without this.
    auto ripDisp = [&](const void* target, int trailing = 0) {
        int32_t d = (int32_t)((const uint8_t*)target - (code + n + 4 + trailing));
        memcpy(code + n, &d, 4);
        n += 4;
    };
    // xmm3 = 1 - k
    code[n++] = 0xF3; code[n++] = 0x0F; code[n++] = 0x10; code[n++] = 0x1D;  // movss xmm3,[one]
    ripDisp(one);
    code[n++] = 0xF3; code[n++] = 0x0F; code[n++] = 0x5C; code[n++] = 0xDA;  // subss xmm3, xmm2
    // bail unless 0 < 1-k < 1
    code[n++] = 0x0F; code[n++] = 0x2F; code[n++] = 0x1D;                    // comiss xmm3,[zero]
    ripDisp(zero);
    code[n++] = 0x76;                                                        // jbe done
    size_t fix1 = n; code[n++] = 0;
    code[n++] = 0xF3; code[n++] = 0x0F; code[n++] = 0x10; code[n++] = 0x25;  // movss xmm4,[one]
    ripDisp(one);
    code[n++] = 0x0F; code[n++] = 0x2F; code[n++] = 0xE3;                    // comiss xmm4, xmm3
    code[n++] = 0x76;                                                        // jbe done
    size_t fix2 = n; code[n++] = 0;
    // one square root per halving of the tick
    code[n++] = 0x80; code[n++] = 0x3D;                                      // cmp byte [cnt],0
    ripDisp(countByte, 1);
    code[n++] = 0x00;
    code[n++] = 0x74;                                                        // je done
    size_t fix3 = n; code[n++] = 0;
    code[n++] = 0xF3; code[n++] = 0x0F; code[n++] = 0x51; code[n++] = 0xDB;  // sqrtss xmm3,xmm3
    code[n++] = 0x80; code[n++] = 0x3D;                                      // cmp byte [cnt],1
    ripDisp(countByte, 1);
    code[n++] = 0x01;
    code[n++] = 0x74;                                                        // je store
    size_t fix4 = n; code[n++] = 0;
    code[n++] = 0xF3; code[n++] = 0x0F; code[n++] = 0x51; code[n++] = 0xDB;  // sqrtss xmm3,xmm3
    code[fix4] = (uint8_t)(n - fix4 - 1);                                    // store:
    code[n++] = 0xF3; code[n++] = 0x0F; code[n++] = 0x10; code[n++] = 0x15;  // movss xmm2,[one]
    ripDisp(one);
    code[n++] = 0xF3; code[n++] = 0x0F; code[n++] = 0x5C; code[n++] = 0xD3;  // subss xmm2, xmm3
    code[fix1] = (uint8_t)(n - fix1 - 1);                                    // done:
    code[fix2] = (uint8_t)(n - fix2 - 1);
    code[fix3] = (uint8_t)(n - fix3 - 1);
    // the displaced prologue, then back; a call that must not be converted
    // enters here
    uint8_t* plain = code + n;
    memcpy(code + n, kTurnOrig, sizeof(kTurnOrig));
    n += sizeof(kTurnOrig);
    code[n++] = 0xE9;
    int32_t back = (int32_t)((int64_t)(main + kTurnResume) - (int64_t)(code + n + 4));
    memcpy(code + n, &back, 4);
    n += 4;
    FlushInstructionCache(GetCurrentProcess(), code, n);
    // the private pairs, after the stub: {real fast value, stock g} for now,
    // so every retargeted read is exactly the original until updateTurnPairs
    float* pairs = (float*)(code + ((n + 15) & ~(size_t)15));
    for (int i = 0; i < kTurnPairs; i++) {
        pairs[2 * i] = *(const float*)(main + kTurnPairEntries[i]);
        pairs[2 * i + 1] = *(const float*)(main + kTurnPairEntries[i] + 4);
    }

    // every write worked out before anything is written
    int64_t rel = (int64_t)code - (int64_t)(site + 5);
    bool reach = rel == (int32_t)rel;
    uint8_t patch[sizeof(kTurnOrig)];
    memset(patch, 0x90, sizeof(patch));
    patch[0] = 0xE9;
    int32_t rel32 = (int32_t)rel;
    memcpy(patch + 1, &rel32, 4);
    int32_t readDisp[sizeof(kTurnTableReads) / sizeof(kTurnTableReads[0])];
    for (int i = 0; i < kTurnReads; i++) {
        const TurnTableRead& r = kTurnTableReads[i];
        uint8_t* pair = (uint8_t*)&pairs[2 * r.pair];
        // `[imageBase + idx*4 + d]` names the pair by its offset from the image
        // base; a rip-relative `lea` by its offset from the next instruction
        int64_t d = r.ripRel ? (int64_t)pair - (int64_t)(main + r.rva + r.len)
                             : (int64_t)pair - (int64_t)main;
        reach = reach && d == (int32_t)d;
        readDisp[i] = (int32_t)d;
    }
    int32_t bypassRel[sizeof(kTurnBypass) / sizeof(kTurnBypass[0])];
    for (int i = 0; i < kTurnBypasses; i++) {
        int64_t d = (int64_t)plain - (int64_t)(main + kTurnBypass[i].rva + 5);
        reach = reach && d == (int32_t)d;
        bypassRel[i] = (int32_t)d;
    }
    if (!reach) {
        logf("turn rate: cave out of range, not patched");
        return false;
    }
    // with the game's other threads stopped, so no instruction is ever fetched
    // with half of its displacement written; all of them or none
    GroupWrite writes[1 + sizeof(kTurnTableReads) / sizeof(kTurnTableReads[0]) +
                      sizeof(kTurnBypass) / sizeof(kTurnBypass[0])];
    int nw = 0;
    writes[nw++] = {site, patch, kTurnOrig, sizeof(kTurnOrig)};
    for (int i = 0; i < kTurnReads; i++) {
        const TurnTableRead& r = kTurnTableReads[i];
        writes[nw++] = {main + r.rva + r.dispOff, &readDisp[i], r.orig + r.dispOff, 4};
    }
    for (int i = 0; i < kTurnBypasses; i++) {
        writes[nw++] = {main + kTurnBypass[i].rva + 1, &bypassRel[i], kTurnBypass[i].orig + 1, 4};
    }
    suspendOthers();
    int kept = writeGroup(writes, nw);
    resumeOthers();
    if (kept == 0) {
        logf("turn rate: a write failed; every write made was put back, not patched");
        return false;
    }
    // from here some instruction points into the stub or the pairs: they are
    // the cave's for good, whatever the later installers want
    cur = (uint8_t*)(pairs + 2 * kTurnPairs);
    cur += (16 - ((uintptr_t)cur & 15)) & 15;
    g_turnPairs = pairs;
    g_turnPlain = plain;
    if (kept < nw) {
        g_turnStranded = true;
        updateTurnPairs();
        logf("turn rate: a write failed and one could not be put back; the first %d of %d"
             " writes stay, with the stub kept and never converting, so the game reads as"
             " stock", kept, nw);
        return false;
    }
    g_turnInstalled = true;
    logf("turn rate: angular approach at main+%X scaled; %d table reads recovered at their"
         " stock coefficient (%d pairs), %d calls past the conversion",
         kTurnRva, kTurnReads, kTurnPairs, kTurnBypasses);
    return true;
}

static void updateTurnRate(bool on, float ts) {
    if (!g_turnSqrtCount || !(g_turnInstalled || g_turnStranded)) {
        return;
    }
    uint8_t want = 0;
    if (on && g_turnInstalled) {
        if (ts < 0.3f) {
            want = 2;  // 120 fps: (1-k)^(1/4)
        } else if (ts < 0.7f) {
            want = 1;  // 60 fps:  (1-k)^(1/2)
        }
    }
    if (*g_turnSqrtCount != want) {
        *g_turnSqrtCount = want;
    }
    updateTurnPairs();
}

// Offline self-test, driven by tools/verify_turn_callers.py without the game:
// maps main.dll (DONT_RESOLVE_DLL_REFERENCES: nothing of the game runs), runs
// the real installs of the mode constants and the turn rate into a cave of
// its own, and writes the cave (cave.bin), the patched bytes (sites.bin) and,
// for each fps mode with the movement fixes on and muted, what the watcher's
// updates leave in the count, the private pairs and the real table
// (states.csv). The script emulates the installed code against those.
extern "C" __declspec(dllexport) int OkamiTurnRateSelfTest(const char* mainPath,
                                                           const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    if (!m) {
        fprintf(rep, "FAIL load %s (%lu)\n", mainPath, GetLastError());
        fclose(rep);
        return 1;
    }
    g_eng.main = (uint8_t*)m;
    g_cfg.fixTurnRate = true;
    g_cfg.fixModeConstants = true;
    installModeConstants();
    const size_t caveSize = 8192;
    uint8_t* cave = allocNear(g_eng.main, caveSize);
    if (!cave || !g_modeTablesOk) {
        fprintf(rep, "FAIL %s\n", cave ? "mode constants did not verify" : "no cave");
        fclose(rep);
        return 1;
    }
    float* one = (float*)(cave + 64);
    float* zero = (float*)(cave + 68);
    uint8_t* count = cave + 72;
    uint8_t* cur = cave + 80;
    uint8_t* stub = cur;
    if (!installTurnRate(cur, cave + caveSize, count, one, zero)) {
        fprintf(rep, "FAIL install (see okami_hackfix.log)\n");
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\ncave %p\nstub %p\nplain %p\npairs %p\ncount %p\none %p\nzero %p\n",
            (void*)m, (void*)cave, (void*)stub, (void*)g_turnPlain, (void*)g_turnPairs,
            (void*)count, (void*)one, (void*)zero);
    snprintf(path, sizeof(path), "%s\\cave.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fwrite(cave, 1, caveSize, f);
        fclose(f);
    }
    snprintf(path, sizeof(path), "%s\\sites.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fwrite(g_eng.main + kTurnRva, 1, sizeof(kTurnOrig), f);
        for (int i = 0; i < kTurnReads; i++) {
            fwrite(g_eng.main + kTurnTableReads[i].rva, 1, kTurnTableReads[i].len, f);
        }
        for (int i = 0; i < kTurnBypasses; i++) {
            fwrite(g_eng.main + kTurnBypass[i].rva, 1, 5, f);
        }
        fclose(f);
    }
    snprintf(path, sizeof(path), "%s\\states.csv", outDir);
    FILE* f = fopen(path, "w");
    if (!f) {
        fclose(rep);
        return 2;
    }
    fprintf(f, "state,fps,muted,count");
    for (int i = 0; i < kTurnPairs; i++) {
        fprintf(f, ",fast%d,stock%d,table%d", i, i, i);
    }
    fprintf(f, "\n");
    // the watcher's order: updateSpeedFix (which calls updateTurnRate) first,
    // then updateModeConstants
    static const struct { const char* name; int fps, muted; } kStates[] = {
        {"30", 30, 0},        {"60", 60, 0},        {"120", 120, 0},  {"120muted", 120, 1},
        {"60muted", 60, 1},   {"120again", 120, 0}, {"30again", 30, 0},
    };
    for (const auto& s : kStates) {
        g_fps60 = s.fps != 30;
        g_fpsImmsFast = s.fps == 120;
        g_speedFixMuted = s.muted;
        updateTurnRate(g_fps60 && !g_speedFixMuted, patchTimeScale());
        updateModeConstants();
        fprintf(f, "%s,%d,%d,%u", s.name, s.fps, s.muted, (unsigned)*count);
        for (int i = 0; i < kTurnPairs; i++) {
            uint32_t a, b, t;
            memcpy(&a, &g_turnPairs[2 * i], 4);
            memcpy(&b, &g_turnPairs[2 * i + 1], 4);
            memcpy(&t, g_eng.main + kTurnPairEntries[i], 4);
            fprintf(f, ",%08X,%08X,%08X", a, b, t);
        }
        fprintf(f, "\n");
    }
    fclose(f);
    fprintf(rep, "PASS\n");
    fclose(rep);
    return 0;
}

// Offline self-test of the grouped installs' failure path, driven by
// tools/verify_install_failure.py without the game: maps main.dll (nothing of
// it runs) and makes the turn rate's and the frame clocks' installs fail at
// each of their writes in turn, through writeProtected's fault injection, and
// then at a few with the undo failing as well. Per case it writes what the
// install returned, the writes it made, where it left the cave's free space
// and the bytes it left at every site (turn.csv, turn_sites.bin, clocks.csv,
// clocks_sites.bin). A stranded turn install is then followed by what follows
// it in the game: the installers after it fill every byte they were given, and
// the watcher runs at 120 fps; the cave is written after that
// (turn_cave_<k>.bin). A stranded frame-clock install runs its hook through
// every fps mode and context (clocks_ticks.csv). The script checks all of it.
// Offline, for tools/verify_stick_drift.py: map main.dll without running it,
// run the real installs of the mode constants and the stick drift, and write
// the cave, the three patched sites, and the gain and the decay table's fast
// entry the watcher leaves at 30, 60 and 120 fps, muted and switched off.
extern "C" __declspec(dllexport) int OkamiStickDriftSelfTest(const char* mainPath,
                                                            const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    if (!m) {
        fprintf(rep, "FAIL load %s (%lu)\n", mainPath, GetLastError());
        fclose(rep);
        return 1;
    }
    g_eng.main = (uint8_t*)m;
    g_cfg.fixModeConstants = true;
    g_cfg.fixStickDrift = true;
    installModeConstants();
    const size_t caveSize = 4096;
    uint8_t* cave = allocNear(g_eng.main, caveSize);
    if (!cave || !g_modeTablesOk) {
        fprintf(rep, "FAIL %s\n", cave ? "mode constants did not verify" : "no cave");
        fclose(rep);
        return 1;
    }
    g_driftScale = (float*)cave;
    *g_driftScale = 1.0f;
    uint8_t* cur = cave + 64;
    installStickDrift(cur, cave + caveSize, g_driftScale);
    const int drifts = (int)(sizeof(kStickDriftSites) / sizeof(kStickDriftSites[0]));
    if (g_stickDriftDone != drifts) {
        fprintf(rep, "FAIL install %d of %d\n", g_stickDriftDone, drifts);
        fclose(rep);
        return 1;
    }
    fprintf(rep, "main %p\ncave %p\nk %.9g\n", (void*)m, (void*)cave, (double)g_stickDriftK);
    snprintf(path, sizeof(path), "%s\\cave.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fwrite(cave, 1, caveSize, f);
        fclose(f);
    }
    snprintf(path, sizeof(path), "%s\\sites.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& site : kStickDriftSites) {
            fwrite(g_eng.main + site[0], 1, 8, f);
        }
        fclose(f);
    }
    snprintf(path, sizeof(path), "%s\\states.csv", outDir);
    FILE* f = fopen(path, "w");
    if (!f) {
        fclose(rep);
        return 2;
    }
    fprintf(f, "state,fps,muted,enabled,ts,gain,fast\n");
    static const struct { const char* name; int fps, muted, enabled; } kStates[] = {
        {"30", 30, 0, 1},        {"60", 60, 0, 1},       {"120", 120, 0, 1},
        {"120muted", 120, 1, 1}, {"120off", 120, 0, 0},  {"60again", 60, 0, 1},
        {"30again", 30, 0, 1},
    };
    for (const auto& st : kStates) {
        g_fps60 = st.fps != 30;
        g_fpsImmsFast = st.fps == 120;
        g_speedFixMuted = st.muted;
        g_cfg.fixStickDrift = st.enabled != 0;
        // the watcher's two updates, as updateSpeedFix and the loop run them
        bool on = g_fps60 && !g_speedFixMuted;
        updateStickDrift(on && g_cfg.fixStickDrift, patchTimeScale());
        updateModeConstants();
        fprintf(f, "%s,%d,%d,%d,%.9g,%.9g,%.9g\n", st.name, st.fps, st.muted, st.enabled,
                (double)(g_fps60 ? patchTimeScale() : 1.0f), (double)*g_driftScale,
                (double)*(const float*)(g_eng.main + kStickDriftKRva - 4));
    }
    fclose(f);
    fprintf(rep, "PASS\n");
    fclose(rep);
    return 0;
}

// Offline, for tools/verify_draw_distance.py: map main.dll without running it,
// run the real install with DrawDistance = factor, and write the cave and the
// eight sites' bytes (8 each, what the site holds after the install).
extern "C" __declspec(dllexport) int OkamiDrawDistanceSelfTest(const char* mainPath,
                                                              const char* outDir, int factor) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    if (!m) {
        fprintf(rep, "FAIL load %s (%lu)\n", mainPath, GetLastError());
        fclose(rep);
        return 1;
    }
    g_eng.main = (uint8_t*)m;
    const size_t caveSize = 4096;
    uint8_t* cave = allocNear(g_eng.main, caveSize);
    if (!cave) {
        fprintf(rep, "FAIL no cave\n");
        fclose(rep);
        return 1;
    }
    installDrawDistanceSites(cave, caveSize, factor);
    const int sites = (int)(sizeof(kDrawDistanceSites) / sizeof(kDrawDistanceSites[0]));
    fprintf(rep, "main %p\ncave %p\nfactor %d\ndone %d\n", (void*)m, (void*)cave, factor,
            g_drawDistanceDone);
    snprintf(path, sizeof(path), "%s\\cave.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        fwrite(cave, 1, caveSize, f);
        fclose(f);
    }
    snprintf(path, sizeof(path), "%s\\sites.bin", outDir);
    if (FILE* f = fopen(path, "wb")) {
        for (const auto& site : kDrawDistanceSites) {
            fwrite(g_eng.main + site[0], 1, 8, f);
        }
        fclose(f);
    }
    if (g_drawDistanceDone == sites) {
        fprintf(rep, "PASS\n");
    } else {
        fprintf(rep, "FAIL install %d of %d\n", g_drawDistanceDone, sites);
    }
    fclose(rep);
    return g_drawDistanceDone == sites ? 0 : 1;
}

extern "C" __declspec(dllexport) int OkamiInstallFailSelfTest(const char* mainPath,
                                                              const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    uint8_t* tick = m ? (uint8_t*)GetProcAddress(m, "?flower_tick@@YA_NXZ") : nullptr;
    g_eng.main = (uint8_t*)m;
    g_cfg.fixTurnRate = true;
    g_cfg.fixModeConstants = true;
    g_cfg.fixFrameClocks = true;
    if (!tick || !resolveFrameConfig(tick)) {
        fprintf(rep, "FAIL load or resolve\n");
        fclose(rep);
        return 1;
    }
    uint8_t* main = g_eng.main;
    installModeConstants();
    const size_t caveSize = 8192;
    uint8_t* cave = allocNear(main, caveSize);
    uint32_t* slots = frameClockSlots();
    if (!cave || !slots || !g_modeTablesOk) {
        fprintf(rep, "FAIL %s\n", !g_modeTablesOk ? "mode constants did not verify" : "no cave");
        fclose(rep);
        return 1;
    }
    uint8_t* end = cave + caveSize;
    float* one = (float*)(cave + 64);
    float* zero = (float*)(cave + 68);
    uint8_t* count = cave + 72;
    uint8_t* start = cave + 80;
    static uint8_t shadow = 2;
    g_shadowMode = &shadow;
    volatile uint8_t* real = g_eng.modeByte;
    volatile uint32_t* counter = g_eng.frameCounter;
    fprintf(rep, "main %p\ncave %p\ncount %p\none %p\nzero %p\nslots %p\nfcstub %p\n", (void*)m,
            (void*)cave, (void*)count, (void*)one, (void*)zero, (void*)slots,
            (void*)(g_fcPage + kFcStubOff));

    auto failAt = [](int k, bool rest) {
        g_writeCount = 0;
        g_writeFailAt = k;
        g_writeFailRest = rest;
    };
    auto noFail = []() {
        g_writeFailAt = -1;
        g_writeFailRest = false;
    };
    auto turnSites = [&](FILE* f) {
        fwrite(main + kTurnRva, 1, sizeof(kTurnOrig), f);
        for (int i = 0; i < kTurnReads; i++) {
            fwrite(main + kTurnTableReads[i].rva, 1, kTurnTableReads[i].len, f);
        }
        for (int i = 0; i < kTurnBypasses; i++) {
            fwrite(main + kTurnBypass[i].rva, 1, 5, f);
        }
    };
    auto clockSites = [&](FILE* f) {
        fwrite(main + kFrameClockTickRva, 1, sizeof(kFrameClockTickOrig), f);
        for (int i = 0; i < kFcReads; i++) {
            fwrite(main + kFrameClockReads[i].rva, 1, kFrameClockReads[i].len, f);
        }
    };
    // between cases, as a test harness: the original bytes back and the state
    // from before any install. The script has already seen what the failed
    // install itself left.
    auto resetTurn = [&]() {
        writeProtected(main + kTurnRva, kTurnOrig, sizeof(kTurnOrig));
        for (int i = 0; i < kTurnReads; i++) {
            writeProtected(main + kTurnTableReads[i].rva, kTurnTableReads[i].orig,
                           kTurnTableReads[i].len);
        }
        for (int i = 0; i < kTurnBypasses; i++) {
            writeProtected(main + kTurnBypass[i].rva, kTurnBypass[i].orig, 5);
        }
        g_turnSqrtCount = nullptr;
        g_turnPairs = nullptr;
        g_turnPlain = nullptr;
        g_turnInstalled = false;
        g_turnStranded = false;
        g_fps60 = 0;
        g_fpsImmsFast = 0;
        updateModeConstants();  // the shipped table
        memset(start, 0, (size_t)(end - start));
    };
    auto resetClocks = [&]() {
        writeProtected(main + kFrameClockTickRva, kFrameClockTickOrig,
                       sizeof(kFrameClockTickOrig));
        for (int i = 0; i < kFcReads; i++) {
            writeProtected(main + kFrameClockReads[i].rva, kFrameClockReads[i].orig,
                           kFrameClockReads[i].len);
        }
        g_fcHooked = false;
        g_fcStranded = false;
        g_fcGatesOk = false;
        g_fcReadsPatched = 0;
        g_fcs = FrameClockState{};
    };

    // the turn rate: each write rejected with the undo working, then the undo
    // failing too after the entry hook alone, half the table reads, and all
    // but the last bypass
    const int turnWrites = 1 + kTurnReads + kTurnBypasses;
    const int turnStrand[] = {1, 1 + kTurnReads / 2, turnWrites - 1};
    snprintf(path, sizeof(path), "%s\\turn.csv", outDir);
    FILE* tc = fopen(path, "w");
    snprintf(path, sizeof(path), "%s\\turn_sites.bin", outDir);
    FILE* ts = fopen(path, "wb");
    if (!tc || !ts) {
        fclose(rep);
        return 2;
    }
    fprintf(tc, "case,k,ok,writes,cur,installed,stranded,count,plain,pairs");
    for (int i = 0; i < kTurnPairs; i++) {
        fprintf(tc, ",table%d,stock%d", i, i);
    }
    fprintf(tc, "\n");
    for (int pass = 0; pass < turnWrites + 3; pass++) {
        bool strand = pass >= turnWrites;
        int k = strand ? turnStrand[pass - turnWrites] : pass;
        uint8_t* cur = start;
        failAt(k, strand);
        bool ok = installTurnRate(cur, end, count, one, zero);
        int writes = g_writeCount;
        noFail();
        turnSites(ts);
        bool installed = g_turnInstalled, stranded = g_turnStranded;
        if (strand) {
            // the installers after it, writing every byte they were given
            memset(cur, 0xCC, (size_t)(end - cur));
            // and the watcher at 120 fps with the fixes on
            g_fps60 = 1;
            g_fpsImmsFast = 1;
            g_speedFixMuted = 0;
            updateTurnRate(true, patchTimeScale());
            updateModeConstants();
            snprintf(path, sizeof(path), "%s\\turn_cave_%d.bin", outDir, k);
            if (FILE* f = fopen(path, "wb")) {
                fwrite(cave, 1, caveSize, f);
                fclose(f);
            }
        }
        fprintf(tc, "%s,%d,%d,%d,%d,%d,%d,%u,%d,%d", strand ? "stranded" : "rollback", k,
                (int)ok, writes, (int)(cur - cave), (int)installed, (int)stranded,
                (unsigned)*count, g_turnPlain ? (int)(g_turnPlain - cave) : -1,
                g_turnPairs ? (int)((uint8_t*)g_turnPairs - cave) : -1);
        for (int i = 0; i < kTurnPairs; i++) {
            uint32_t t, s;
            memcpy(&t, main + kTurnPairEntries[i], 4);
            memcpy(&s, main + kTurnPairEntries[i] + 4, 4);
            fprintf(tc, ",%08X,%08X", t, s);
        }
        fprintf(tc, "\n");
        resetTurn();
    }
    fclose(tc);
    fclose(ts);

    // the frame clocks: the same, stranding after the hook alone, half the
    // reads, and all but the last
    const int clockWrites = 1 + kFcReads;
    const int clockStrand[] = {1, 1 + kFcReads / 2, clockWrites - 1};
    snprintf(path, sizeof(path), "%s\\clocks.csv", outDir);
    FILE* cc = fopen(path, "w");
    snprintf(path, sizeof(path), "%s\\clocks_sites.bin", outDir);
    FILE* cs = fopen(path, "wb");
    snprintf(path, sizeof(path), "%s\\clocks_ticks.csv", outDir);
    FILE* ct = fopen(path, "w");
    if (!cc || !cs || !ct) {
        fclose(rep);
        return 2;
    }
    fprintf(cc, "case,k,hooked,stranded,writes,reads,gates\n");
    fprintf(ct, "k,tick,fps,mode,muted,counter");
    for (int i = 0; i < 2 + kFcHolds; i++) {
        fprintf(ct, ",slot%d", i);
    }
    fprintf(ct, "\n");
    *counter = 5000;
    for (int pass = 0; pass < clockWrites + 3; pass++) {
        bool strand = pass >= clockWrites;
        int k = strand ? clockStrand[pass - clockWrites] : pass;
        g_fps60 = 1;
        g_fpsImmsFast = 1;
        g_shadowOn = true;
        failAt(k, strand);
        installFrameClocks();
        int writes = g_writeCount;
        noFail();
        clockSites(cs);
        fprintf(cc, "%s,%d,%d,%d,%d,%d,%d\n", strand ? "stranded" : "rollback", k,
                (int)g_fcHooked, (int)g_fcStranded, writes, g_fcReadsPatched, (int)g_fcGatesOk);
        if (strand) {
            // the hook left in, at every fps mode and in both stock contexts,
            // with the fix on and muted
            static const struct { int ticks, fps, mode, muted; } kSegs[] = {
                {100, 120, 2, 0}, {100, 120, 1, 0}, {100, 60, 2, 0}, {60, 30, 2, 0},
                {60, 30, 1, 0},   {100, 120, 2, 1}, {100, 60, 1, 0},
            };
            int t = 0;
            for (const auto& s : kSegs) {
                bool patched = s.fps != 30;
                g_fps60 = patched;
                g_fpsImmsFast = s.fps == 120;
                g_shadowOn = patched;
                shadow = (uint8_t)s.mode;
                *real = patched ? (uint8_t)1 : (uint8_t)s.mode;
                g_timerFixMuted = s.muted;
                for (int i = 0; i < s.ticks; i++, t++) {
                    (*counter)++;
                    frameClockOnTick();
                    fprintf(ct, "%d,%d,%d,%d,%d,%u", k, t, s.fps, s.mode, s.muted, *counter);
                    for (int j = 0; j < 2 + kFcHolds; j++) {
                        fprintf(ct, ",%u", slots[j]);
                    }
                    fprintf(ct, "\n");
                }
            }
            g_timerFixMuted = 0;
        }
        resetClocks();
    }
    fclose(cc);
    fclose(cs);
    fclose(ct);
    fprintf(rep, "turn writes %d\nclock writes %d\nPASS\n", turnWrites, clockWrites);
    fclose(rep);
    return 0;
}

static void installSpeedFix() {
    if (g_speedFixTried || !g_eng.main) {
        return;
    }
    if (!g_cfg.fixRunSpeed && !g_cfg.fixJumpHeight) {
        return;
    }
    g_speedFixTried = true;
    // one page near main.dll: [0..32) the scale floats, [32..) the detours
    uint8_t* cave = allocNear(g_eng.main, 8192);
    if (!cave) {
        logf("movement fix: no code cave near main.dll, not patched");
        return;
    }
    g_playerScale = (float*)cave;
    g_animScale = (float*)(cave + 4);
    g_jumpScale = (float*)(cave + 8);
    g_gateScale = (float*)(cave + 12);
    g_gateInvScale = (float*)(cave + 16);
    g_driftScale = (float*)(cave + 20);
    *g_driftScale = 1.0f;
    *g_playerScale = 1.0f;
    *g_animScale = 1.0f;
    *g_jumpScale = 1.0f;
    *g_gateScale = 1.0f;
    *g_gateInvScale = 1.0f;
    // [32..64) is the hoisted-decay pool, one k^ts per site
    float* hoistSlots = (float*)(cave + 32);
    // [64..80) the turn-rate constants and its square-root count
    float* turnOne = (float*)(cave + 64);
    float* turnZero = (float*)(cave + 68);
    uint8_t* turnCount = cave + 72;
    uint8_t* cur = cave + 80;
    uint8_t* end = cave + 8192;
    if (g_cfg.fixRunSpeed) {
        // run target speed: xmm2 holds the target constant at this point
        if (installScaleDetour(cur, end, kRunPatchRva, kRunResumeRva, kRunOrig, sizeof(kRunOrig), 2,
                               g_playerScale, "run speed")) {
            g_speedFixInstalled = true;
        }
        if (g_cfg.fixAirAccel) {
            int done = 0;
            const int accels = (int)(sizeof(kAirAccelSites) / sizeof(kAirAccelSites[0]));
            for (int i = 0; i < accels; i++) {
                // xmm0 already holds a*ts here, so the extra multiply goes after
                if (installScaleDetour(cur, end, kAirAccelSites[i][0], kAirAccelSites[i][1],
                                       kAirAccelOrig[i], sizeof(kAirAccelOrig[i]), 0,
                                       g_playerScale, nullptr, /*scaleAfter=*/true)) {
                    done++;
                }
            }
            logf("airborne acceleration: %d of %d sites scaled to ts^2", done, accels);
            done = 0;
            const int swims = (int)(sizeof(kSwimAccelSites) / sizeof(kSwimAccelSites[0]));
            for (int i = 0; i < swims; i++) {
                // the displaced load fills the register, so the multiply goes after
                if (installScaleDetour(cur, end, kSwimAccelSites[i][0], kSwimAccelSites[i][1],
                                       kSwimAccelOrig[i], sizeof(kSwimAccelOrig[i]),
                                       kSwimAccelReg[i], g_playerScale, nullptr,
                                       /*scaleAfter=*/true)) {
                    done++;
                }
            }
            logf("swimming acceleration: %d of %d sites scaled to ts^2", done, swims);
        }
        if (g_cfg.fixStickDrift) {
            installStickDrift(cur, end, g_driftScale);
        }
        if (g_cfg.fixAirGates) {
            int done = 0;
            const int gates = (int)(sizeof(kAirGateSites) / sizeof(kAirGateSites[0]));
            for (int i = 0; i < gates; i++) {
                // every one of these loads the constant into xmm0, so the
                // multiply goes after the displaced instruction
                if (installScaleDetour(cur, end, kAirGateSites[i][0], kAirGateSites[i][1],
                                       kAirGateOrig[i], sizeof(kAirGateOrig[i]), 0, g_gateScale,
                                       nullptr, /*scaleAfter=*/true)) {
                    done++;
                }
            }
            bool pick = installJumpPickDetour(cur, end);
            logf("jump path thresholds: %d of %d scaled, variant select %s", done, gates,
                 pick ? "scaled" : "NOT patched");
        }
        installHoistDecay(cur, end, hoistSlots);
        // installed or not, cur comes back past anything of the cave that
        // patched code still points into
        installTurnRate(cur, end, turnCount, turnOne, turnZero);
        if (g_cfg.fixSlopeTerm) {
            int done = 0;
            for (auto& site : kSlopeSites) {
                // xmm1 is the destination of the displaced load, so the
                // multiply has to come after it
                if (installScaleDetour(cur, end, site[0], site[1], kSlopeOrig,
                                       sizeof(kSlopeOrig), 1, g_playerScale, nullptr,
                                       /*scaleAfter=*/true)) {
                    done++;
                }
            }
            logf("slope speed term: %d of %d sites scaled", done,
                 (int)(sizeof(kSlopeSites) / sizeof(kSlopeSites[0])));
        }
        if (g_cfg.fixAnimRate) {
            for (auto& site : kAnimSites) {
                installScaleDetour(cur, end, site[0], site[1], kAnimOrig, sizeof(kAnimOrig), 1,
                                   g_animScale, "anim rate", /*scaleAfter=*/true);
            }
        }
    }
    if (g_cfg.fixJumpHeight) {
        // xmm0 holds timeScale * 5.0 on its way into the launch accumulator
        installScaleDetour(cur, end, kJumpSiteRva, kJumpResumeRva, kJumpOrig, sizeof(kJumpOrig), 0,
                           g_jumpScale, "jump height");
    }
    if (g_cfg.fixLaunchVelocity) {
        int done = 0;
        const int launches = (int)(sizeof(kLaunchSites) / sizeof(kLaunchSites[0]));
        for (int i = 0; i < launches; i++) {
            const LaunchSite& ls = kLaunchSites[i];
            // scale the register on its way into the store, so the detour has
            // to emit the multiply before the displaced instruction
            if (installScaleDetour(cur, end, ls.rva, ls.rva + ls.len, ls.orig, ls.len,
                                   ls.reg, g_jumpScale, nullptr)) {
                done++;
            }
        }
        logf("launch velocities: %d of %d sites patched", done, launches);
    }
}

// Scale the jog block for 60 fps, or put the stock values back.
static int g_jogReapplied = 0;

static void applyJogParams(bool scaled, float ts) {
    if (!g_cfg.fixRunSpeed || !g_eng.main) {
        return;
    }
    bool changed = false;
    for (auto& p : kJogParams) {
        float* addr = (float*)(g_eng.main + p.rva);
        float want = p.stock;
        if (scaled) {
            if (p.tsPower == JOG_BLEND) {
                want = 1.0f - powf(1.0f - p.stock, ts);
            } else {
                for (int i = 0; i < p.tsPower; i++) {
                    want *= ts;
                }
            }
        }
        if (*addr == want) {
            continue;
        }
        // the game reloads this block on some transitions, so keep it applied
        // rather than assuming one write sticks
        writeProtected(addr, &want, sizeof(want));
        changed = true;
    }
    int32_t* frames = (int32_t*)(g_eng.main + kChargeFramesRva);
    int32_t wantFrames = scaled ? (int32_t)(kChargeFramesStock / ts + 0.5f) : kChargeFramesStock;
    if (*frames != wantFrames) {
        writeProtected(frames, &wantFrames, sizeof(wantFrames));
        changed = true;
    }
    if (scaled != g_jogParamsScaled) {
        g_jogParamsScaled = scaled;
        g_jogReapplied = 0;
        logf("run speed: jog parameters %s", scaled ? "scaled for 60 fps" : "restored to stock");
    } else if (changed && g_jogReapplied < 8) {
        g_jogReapplied++;
        logf("run speed: jog parameters were overwritten by the game, re-applied (%d)",
             g_jogReapplied);
    }
}

// Called from the watcher: the detour's multiplier follows the engine's own
// time scale while the fix is active, and is 1.0 (a no-op) otherwise.
static void updateSpeedFix() {
    if (!g_playerScale) {
        return;
    }
    bool on = g_cfg.fixRunSpeed && g_fps60 && !g_speedFixMuted;
    float want = on ? patchTimeScale() : 1.0f;
    if (*g_playerScale != want) {
        *g_playerScale = want;
    }
    if (g_animScale) {
        float animWant = (on && g_cfg.fixAnimRate && want > 0.05f) ? 1.0f / want : 1.0f;
        if (*g_animScale != animWant) {
            *g_animScale = animWant;
        }
    }
    if (g_jumpScale) {
        // the jump fix has its own config flag and its own key, so that a
        // movement A/B never silently changes the jump as well
        bool jumpOn = g_cfg.fixJumpHeight && g_fps60 && !g_jumpFixMuted;
        float jumpWant = jumpOn ? (1.0f / patchTimeScale()) : 1.0f;
        if (*g_jumpScale != jumpWant) {
            *g_jumpScale = jumpWant;
        }
    }
    // rides the movement A/B: it is how fast she moves while she recoils
    updateStickDrift(on && g_cfg.fixStickDrift, patchTimeScale());
    if (g_gateScale) {
        // the thresholds ride the movement A/B, because they are part of how
        // fast she moves and A/B-ing half of that would measure nothing
        bool gateOn = on && g_cfg.fixAirGates;
        float gateWant = gateOn ? patchTimeScale() : 1.0f;
        if (*g_gateScale != gateWant) {
            *g_gateScale = gateWant;
        }
        // ride the movement A/B, for the same reason the gates do
        updateHoistDecay(on && g_cfg.fixHoistDecay, patchTimeScale());
        updateTurnRate(on && g_cfg.fixTurnRate, patchTimeScale());
        if (g_gateInvScale) {
            float inv = (gateWant > 0.05f) ? 1.0f / gateWant : 1.0f;
            if (*g_gateInvScale != inv) {
                *g_gateInvScale = inv;
            }
        }
    }
    applyJogParams(on, want > 0.05f ? want : 1.0f);
}

// ---------------------------------------------------------------------------
// Scripted input harness
//
// Why this exists
// ---------------
// Every measurement in this project came from playing the game and reading the
// log, and the noise in that is larger than most of the effects being chased.
// Three consecutive 30 fps jumps in one test log launched at 3.049, 1.793 and
// 3.373 per tick -- a 1.9x spread from human variation alone -- while the bugs
// being hunted are 20-50% effects. Two of the three diagnoses I made against
// that baseline were wrong, and one "confirmed" fix turned out to be a detour
// that had never executed correctly at all.
//
// So the harness replaces the player for the duration of a test. It writes the
// analog stick and the action bits directly, on a fixed wall-clock script, and
// samples the result once per tick. Two runs at different frame rates are then
// directly comparable, because the script means the same thing in real time at
// every rate -- which is exactly the property the whole patch is trying to
// establish.
//
// Where it hooks
// --------------
// main+3AF020 is the player's per-tick state dispatcher: a jump table at
// main+3AF8A0 over pl00+0xE35 that calls main+3B2CF0 for ground movement,
// main+3B3FF0 for the jump, and so on. Its first five bytes are one
// relocatable instruction, and rcx holds the player object. Hooking its entry
// puts the harness after the pad update for the tick and before anything reads
// the stick, which is the only place an injected input is deterministic.
//
// An external input tool (AutoHotkey, a virtual pad driver, a Cheat Engine
// timer) cannot get that ordering, and could not do the sampling half at all:
// only code inside the tick can sample once per tick. Since the sampler has to
// live here regardless, driving the input from the same place costs nothing.
//
// Cost control
// ------------
// The hook does no I/O and takes no locks -- it writes into a static array and
// returns. The report is written afterwards, from the watcher thread, so a run
// is not perturbed by its own measurement.
// ---------------------------------------------------------------------------

// Pad state, as the player code reads it. The stick bytes are signed; the
// action words are bitfields, one "held" and one edge-triggered, and the jump
// is bit 33 in both (main+3B4B2E tests 0x200000000 against the held word to
// keep charging a jump, main+3B497B tests it against the pressed word to start
// one).
static const uint32_t kPadStickX = 0xB6B128;
static const uint32_t kPadStickY = 0xB6B129;
static const uint32_t kPadHeld = 0xB6B0A8;
static const uint32_t kPadPress = 0xB6B0D8;
static const uint64_t kActJump = 0x200000000ull;
// main+B6B134 is the *target heading*: the world-space direction the stick is
// asking for, which is the stick deflection combined with the camera. The
// ground handler turns pl00+0xB4 (the facing) towards it through a mode-indexed
// turn-rate table at main+7A82F0, and the airborne steering scales its
// acceleration by (PI - 1.7*|facing - heading|)/PI.
//
// I first labelled this the camera angle. It is not, and the difference matters
// for where it is sampled: with the stick centred it holds whatever it last
// held, so reading it on the first tick of a run -- during `settle`, stick at
// zero -- captures a stale value from before the run began. It is sampled on
// the first tick the script actually deflects the stick instead.
//
// Two runs with the same script but a different camera produce different
// headings, which makes them different experiments however identical the stick
// input was. That is what the comparison warns about.
//
// An open question, and the reason travelDir below exists: the pad block at
// main+B6B0A0..B6B168 is filled through a base pointer, so I have not found the
// code that computes this heading from the stick. If it is computed by the pad
// task earlier in the tick, then writing the stick bytes at the top of the
// player update raises the magnitude the movement code sees without updating
// the direction it turns towards -- she would move, but along whatever heading
// was last computed rather than the one the script asked for.
//
// Rather than guess, the run records the direction she actually travelled. That
// detects the problem whatever causes it, and it is the thing that has to match
// between two runs for the comparison to mean anything.
static const uint32_t kHeadingRef = 0xB6B134;
static const uint32_t kPlayerFacing = 0xB4;  // pl00+0xB4, turned towards the heading

// The smoothed position offsets at pl00+0x10A0 (x), +0x10A4 (y) and +0x10A8
// (z). main+3A77B9 adds them straight onto the transform once per tick:
//
//     transform.x += pl00+0x10A0
//     transform.z += pl00+0x10A8
//
// so they are a per-tick displacement -- a velocity -- and they are produced by
// a blend toward a freshly computed target whose coefficient is per-tick too
// (0.3 at main+3A76C4, 0.03 at main+3A766F, 0.1 at main+3A77EE). None of those
// constants is in any patch table.
//
// That is two compounding frame-rate dependencies in the middle of ground
// movement, which is where the remaining "it is almost right but something is
// off" lives. Rather than patch it on a reading of the disassembly -- which has
// already been wrong twice in this area -- the run records the offsets and the
// animation rate, so the two rates can be compared directly.
static const uint32_t kPlayerOfsX = 0x10A0;
static const uint32_t kPlayerOfsY = 0x10A4;
static const uint32_t kPlayerOfsZ = 0x10A8;
static const uint32_t kPlayerAnimRate = 0xF54;

struct HarnessStep {
    uint32_t ms;       // wall-clock duration, so the script is rate-independent
    int8_t dirX;       // -1, 0, +1; scaled by HarnessStick
    int8_t dirY;
    uint64_t actions;  // held this step; the press edge is synthesised
    // Radians to add to the heading captured at the start of the run. The
    // injected stick sets how HARD she is asked to move but not WHICH WAY:
    // the direction comes from main+B6B134, which the pad task computes from
    // the real stick and the camera, and with the real stick centred it holds
    // whatever it last held. Writing the stick alone therefore produces a run
    // in a stale direction that no script step can change -- the first version
    // of the ground-turn step moved her facing by 0.0002 rad in 700 ms.
    //
    // So the run commands the heading directly. A turn is then the same turn at
    // every frame rate and from any camera, which is also what finally makes
    // two runs comparable: the old "these runs travelled in different
    // directions" warning fired on every single cross-rate comparison.
    float dHeading;
    const char* label;
};

// A run, a jump out of that run, and a stop. Long enough for the airborne
// steering block to reach equilibrium (its time constant is 0.22 s) and short
// enough to fit comfortably in one clear patch of ground.
// The ground turn is step 3. Until it was added the script ran dead straight
// on the ground and only ever turned in the air, so the one thing a player
// could see wrong -- a judder when rounding a corner on foot -- was the one
// thing the test never did.
static const HarnessStep kHarnessDefault[] = {
    {600, 0, 0, 0, 0.0f, "settle"},
    {1200, 0, 1, 0, 0.0f, "run straight"},
    // the symptom is a SLIGHT turn, so these are gentle and go both ways
    {600, 0, 1, 0, -0.35f, "slight turn left"},
    {600, 0, 1, 0, +0.35f, "slight turn right"},
    {600, 0, 1, 0, 0.0f, "straight again"},
    {300, 0, 1, kActJump, 0.0f, "jump"},
    {500, 0, 1, 0, 0.0f, "airborne, holding forward"},
    // Steering in mid-air is the whole point of the block fixed at main+3B547C
    // and its three duplicates, and of the v < 3.0 gate in front of it. A script
    // that only ever holds one direction never exercises any of it, so the turn
    // is deliberate: it forces the airborne accelerate path to run with a large
    // camera-alignment term instead of the near-zero one a straight run gives.
    {900, 0, 1, 0, +1.2f, "airborne, steering across"},
    {600, 0, 0, 0, 0.0f, "stop"},
};

// The live script. It is the default above unless the ini overrides it, because
// the two things worth testing next -- a slope, and a dash rather than a run --
// need a different script and nothing else, and rebuilding the DLL to change a
// test is a good way to end up testing the build instead of the game.
// samples one run can hold: 800 is 6.6 s at 120 fps, which bounds how long a
// custom script may usefully be
#define HARNESS_MAX 800
#define HARNESS_STEPS_MAX 16
static HarnessStep g_script[HARNESS_STEPS_MAX];
static char g_scriptLabel[HARNESS_STEPS_MAX][28];
static int g_scriptN = 0;
static bool g_scriptCustom = false;
static uint32_t g_scriptTotalMs = 0;

// Step<n>=<ms>,<dirX>,<dirY>,<action>,<label>
//   dirX/dirY are -1, 0 or +1 and are scaled by HarnessStick
//   action is `none` or `jump`
// A malformed step anywhere discards the whole custom script, steps already
// parsed included, and the built-in one runs instead -- with its own length,
// which is what the rest of the run is sized from.
static void harnessLoadScript() {
    char ini[MAX_PATH];
    snprintf(ini, sizeof(ini), "%sokami.ini", g_baseDir);
    g_scriptN = 0;
    g_scriptCustom = false;
    for (int i = 1; i <= HARNESS_STEPS_MAX; i++) {
        char key[16], val[160];
        snprintf(key, sizeof(key), "Step%d", i);
        GetPrivateProfileStringA("Harness", key, "", val, sizeof(val), ini);
        if (!val[0]) {
            break;
        }
        int ms = 0, dx = 0, dy = 0;
        float dh = 0.0f;
        char act[24] = {0}, lab[28] = {0};
        // the turn is optional and comes after the action, so a script written
        // before the heading command still parses -- it simply never turns
        int got = sscanf(val, "%d,%d,%d,%23[^,],%f,%27[^\r\n]", &ms, &dx, &dy, act, &dh, lab);
        if (got < 5) {
            dh = 0.0f;
            got = sscanf(val, "%d,%d,%d,%23[^,],%27[^\r\n]", &ms, &dx, &dy, act, lab);
        }
        if (got < 4 || ms <= 0 || dx < -1 || dx > 1 || dy < -1 || dy > 1) {
            logf("harness: %s=%s is malformed -- using the built-in script instead", key, val);
            g_scriptN = 0;
            break;
        }
        uint64_t actions = 0;
        if (!_stricmp(act, "jump")) {
            actions = kActJump;
        } else if (_stricmp(act, "none") && strcmp(act, "-") && strcmp(act, "0")) {
            logf("harness: %s has unknown action '%s' (want none or jump) -- using the"
                 " built-in script instead", key, act);
            g_scriptN = 0;
            break;
        }
        snprintf(g_scriptLabel[g_scriptN], sizeof(g_scriptLabel[0]), "%s", lab[0] ? lab : act);
        g_script[g_scriptN].ms = (uint32_t)ms;
        g_script[g_scriptN].dirX = (int8_t)dx;
        g_script[g_scriptN].dirY = (int8_t)dy;
        g_script[g_scriptN].actions = actions;
        g_script[g_scriptN].dHeading = dh;
        g_script[g_scriptN].label = g_scriptLabel[g_scriptN];
        g_scriptN++;
    }
    g_scriptCustom = g_scriptN > 0;
    if (!g_scriptCustom) {
        g_scriptN = (int)(sizeof(kHarnessDefault) / sizeof(kHarnessDefault[0]));
        for (int i = 0; i < g_scriptN; i++) {
            g_script[i] = kHarnessDefault[i];
        }
    }
    g_scriptTotalMs = 0;
    for (int i = 0; i < g_scriptN; i++) {
        g_scriptTotalMs += g_script[i].ms;
    }
    logf("harness: %s script, %d steps, %u ms total",
         g_scriptCustom ? "CUSTOM (from okami.ini)" : "built-in", g_scriptN, g_scriptTotalMs);
    // 800 samples is 6.6 s at 120 fps; a longer script loses its tail exactly
    // at the rate the test exists to measure
    uint32_t capMs = (uint32_t)(HARNESS_MAX * 1000.0 / 120.0);
    if (g_scriptTotalMs > capMs) {
        logf("harness: WARNING this script is %u ms but only %u ms of it fits in the sample"
             " buffer at 120 fps -- the tail will be dropped there and kept at 30,"
             " which makes the two runs incomparable. Shorten it.",
             g_scriptTotalMs, capMs);
    }
    for (int i = 0; i < g_scriptN; i++) {
        logf("harness:   %2d. %5u ms  stick(%+d,%+d) turn %+.2f rad %-6s %s", i + 1,
             g_script[i].ms, g_script[i].dirX, g_script[i].dirY,
             (double)g_script[i].dHeading,
             g_script[i].actions ? "JUMP" : "-", g_script[i].label);
    }
}

// Offline self-test, driven by tools/verify_harness_script.py: loads the
// script from <dir>\okami.ini exactly as F3 does and writes what it chose to
// <outDir>\script.txt -- the source, the step count and total length, then one
// line per step.
extern "C" __declspec(dllexport) int OkamiHarnessScriptSelfTest(const char* dir,
                                                               const char* outDir) {
    snprintf(g_baseDir, sizeof(g_baseDir), "%s\\", dir);
    harnessLoadScript();
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\script.txt", outDir);
    FILE* f = fopen(path, "w");
    if (!f) {
        return 2;
    }
    fprintf(f, "%s %d %u\n", g_scriptCustom ? "custom" : "builtin", g_scriptN, g_scriptTotalMs);
    for (int i = 0; i < g_scriptN; i++) {
        const HarnessStep& s = g_script[i];
        fprintf(f, "%u,%d,%d,%s,%.2f,%s\n", s.ms, s.dirX, s.dirY, s.actions ? "jump" : "none",
                (double)s.dHeading, s.label);
    }
    fclose(f);
    return 0;
}

struct HarnessSample {
    float ms;
    float x, y, z;
    float hs, vy;
    // pl00+0xB0 is the slope term: it is 0 on flat ground, which is exactly
    // where FixSlopeTerm has no effect, so a run that never sees it non-zero
    // has not tested that fix at all. pl00+0xE14 is the jump launch velocity,
    // 5.4 on the running jump and 4.2 on the standing one -- reading it back
    // is the direct observable for the variant selector at main+3B41E6.
    float b0, launch;
    float facing;  // pl00+0xB4, so the trace shows whether she turned at all
    float ofsX, ofsY, ofsZ;  // pl00+0x10A0/A4/A8, added to the transform each tick
    float animRate;          // pl00+0xF54
    uint8_t st, sub;
};

struct HarnessRun {
    bool used;
    int fps;          // the mode the ladder was in
    float tickRate;   // the rate actually achieved, which is not the same thing
    int n;
    float heading;    // the target heading, sampled under real stick input
    float startX, startZ;
    bool jumped;      // did she ever reach the airborne state
    bool headingSet;  // the target heading has been sampled under real input
    bool truncated;   // ran out of sample space
    HarnessSample s[HARNESS_MAX];
};
// slot 3 is the passthrough control. It is nominally 30 fps, but it is NOT the
// same measurement as slot 0: slot 0 is the patched DLL with its fixes restored,
// slot 3 is the game with no patches in it at all. Keeping them apart is the
// whole point of having a control, so they never share a slot or a file.
static HarnessRun g_hruns[4];  // 0 = 30 fps, 1 = 60, 2 = 120, 3 = stock

// What a comparison actually needs, small enough to write to a file.
//
// Keeping only this means a baseline survives the game closing -- which matters
// because the workflow is "run at 30, toggle, run at 120", and anything that
// ends the process in between (a crash, an ini edit, a rebuild) otherwise
// throws the baseline away. It also makes runs comparable across *builds*:
// the previous build's 120 fps run is still on disk to diff the next one
// against, which is the only way to tell a fix from a no-op without holding
// both in one session.
// The comparison grid spans whatever the script is, so a custom script is
// still comparable with itself. gridMs goes into the record: two runs taken
// with different scripts are not comparable at all, and without this they would
// silently line up column for column and look like they were.
#define HARNESS_GRID 12
struct HarnessSummary {
    bool used;
    bool stock;   // recorded with Passthrough=1: the unpatched control
    float gridMs;  // script length / HARNESS_GRID -- identifies the script
    int fps;
    float tickRate;
    float heading, startX, startZ;
    float travelDir;  // atan2 of the net displacement: which way she actually went
    bool jumped;
    float totalDist, groundPeak, airPeak, rise, airMs, airDist;
    // travelled / intended. pl00+0xE48 IS the per-tick displacement the
    // movement code asked for, so this ratio is 1.0 when she is free and
    // collapses when she is pressed against geometry. A run at 0.05 still
    // looks like a completed run in every other number.
    float moveEff;
    float dist[HARNESS_GRID];
    float height[HARNESS_GRID];
    char stamp[24];
};
static HarnessSummary g_hsum[4];   // most recent per rate, loaded from disk
static HarnessSummary g_hprevSum[4];  // the one before it, for the noise floor

// main+3AF020's prologue: `mov [rsp+10h], rbx`, one relocatable instruction of
// exactly the five bytes a jump needs, with no branch target inside it.
static const uint32_t kHarnessHookRva = 0x3AF020;
static const uint8_t kHarnessHookOrig[5] = {0x48, 0x89, 0x5C, 0x24, 0x10};

// The entry stub, as one template so it can be read back and disassembled
// rather than trusted. tools/check_patch_sites.py checks that this decodes to
// the instructions the comments claim, that every push has its matching pop in
// reverse order, and that rsp is 16-byte aligned at the call -- all three are
// things a hand-assembled stub gets wrong silently, and this one had never run
// when it was written.
//
// rcx already holds the player object on entry, so it doubles as the callback's
// first argument. rsp is 16n+8 at a function entry; seven pushes take it to
// 16n, and 0x20 of shadow space keeps it there, which is what the ABI wants at
// the call. Only rcx is live at this point (the dispatcher takes one integer
// argument and no floats), so the volatile xmm registers need no saving.
static const uint8_t kHarnessStub[] = {
    0x50, 0x51, 0x52, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52, 0x41, 0x53,
    // push rax, rcx, rdx, r8, r9, r10, r11
    0x48, 0x83, 0xEC, 0x20,                                // sub rsp, 0x20
    0x48, 0xB8, 0, 0, 0, 0, 0, 0, 0, 0,                    // movabs rax, <callback>
    0xFF, 0xD0,                                            // call rax
    0x48, 0x83, 0xC4, 0x20,                                // add rsp, 0x20
    0x41, 0x5B, 0x41, 0x5A, 0x41, 0x59, 0x41, 0x58, 0x5A, 0x59, 0x58,
    // pop r11, r10, r9, r8, rdx, rcx, rax
};
static const size_t kHarnessStubFnAt = 17;  // offset of the imm64 inside it

static volatile LONG g_harnessActive = 0;
static volatile LONG g_harnessDone = 0;
static volatile LONG g_harnessAbort = 0;
static LONGLONG g_harnessStart = 0;
static int g_harnessFps = 0;
static int g_harnessSlot = 0;
static uint64_t g_harnessPrevActions = 0;
static uint8_t* g_harnessTramp = nullptr;
// Set only once the entry hook is actually in place. Without it a run can be
// started that nothing will ever advance or finish: the callback is what ends
// a run, so with Harness=0 (or a prologue that did not match) F3 would leave
// the overlay reading "HARNESS starting" forever and never write a report.
static bool g_harnessHooked = false;
static volatile LONG g_harnessStepIdx = -1;  // written by the tick, read by the overlay
static volatile LONG g_harnessMs = 0;
static char g_harnessOverlay[128] = "";

static void harnessPath(char* out, size_t n) {
    snprintf(out, n, "%sokami_harness.csv", g_baseDir);
}

static void harnessSave() {
    char path[MAX_PATH];
    harnessPath(path, sizeof(path));
    FILE* f = fopen(path, "w");
    if (!f) {
        logf("harness: could not write %s", path);
        return;
    }
    fprintf(f, "# okami harness runs -- one line per rate, newest wins on load\n");
    fprintf(f, "# fps,stock,gridMs,tickRate,heading,travelDir,startX,startZ,jumped,total,"
               "groundPeak,airPeak,rise,airMs,airDist,moveEff,stamp,dist[12],height[12]\n");
    for (int i = 0; i < 4; i++) {
        const HarnessSummary& h = g_hsum[i];
        if (!h.used) {
            continue;
        }
        fprintf(f, "%d,%d,%.1f,%.3f,%.4f,%.4f,%.2f,%.2f,%d,%.3f,%.3f,%.3f,%.3f,%.1f,"
                   "%.3f,%.4f,%s",
                h.fps, h.stock ? 1 : 0, (double)h.gridMs, (double)h.tickRate,
                (double)h.heading, (double)h.travelDir, (double)h.startX,
                (double)h.startZ, h.jumped ? 1 : 0, (double)h.totalDist,
                (double)h.groundPeak, (double)h.airPeak, (double)h.rise,
                (double)h.airMs, (double)h.airDist, (double)h.moveEff, h.stamp);
        for (int g = 0; g < HARNESS_GRID; g++) {
            fprintf(f, ",%.3f", (double)h.dist[g]);
        }
        for (int g = 0; g < HARNESS_GRID; g++) {
            fprintf(f, ",%.3f", (double)h.height[g]);
        }
        fprintf(f, "\n");
    }
    fclose(f);
}

static void harnessLoad() {
    char path[MAX_PATH];
    harnessPath(path, sizeof(path));
    FILE* f = fopen(path, "r");
    if (!f) {
        return;
    }
    char line[2048];
    int loaded = 0;
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '#' || line[0] == '\n') {
            continue;
        }
        HarnessSummary h;
        memset(&h, 0, sizeof(h));
        int jumped = 0;
        char* p2 = line;
        // fixed-width prefix, then the two float runs
        int stock = 0;
        int got = sscanf(p2, "%d,%d,%f,%f,%f,%f,%f,%f,%d,%f,%f,%f,%f,%f,%f,%f,%23[^,]",
                         &h.fps, &stock, &h.gridMs, &h.tickRate, &h.heading, &h.travelDir,
                         &h.startX, &h.startZ, &jumped, &h.totalDist, &h.groundPeak,
                         &h.airPeak, &h.rise, &h.airMs, &h.airDist, &h.moveEff, h.stamp);
        // an older file has no moveEff: it parses 15 and stops, and every field
        // from there on would be shifted, so it is discarded rather than read
        if (got < 16) {
            continue;
        }
        h.stock = stock != 0;
        h.jumped = jumped != 0;
        // walk past the 17 prefix fields to the grids
        int commas = 0;
        while (*p2 && commas < 17) {
            if (*p2 == ',') {
                commas++;
            }
            p2++;
        }
        for (int g = 0; g < HARNESS_GRID * 2 && *p2; g++) {
            float v = (float)atof(p2);
            if (g < HARNESS_GRID) {
                h.dist[g] = v;
            } else {
                h.height[g - HARNESS_GRID] = v;
            }
            char* comma = strchr(p2, ',');
            if (!comma) {
                break;
            }
            p2 = comma + 1;
        }
        h.used = true;
        int slot = h.stock ? 3 : (h.fps >= 120 ? 2 : (h.fps >= 60 ? 1 : 0));
        g_hsum[slot] = h;
        loaded++;
    }
    fclose(f);
    if (loaded) {
        logf("harness: loaded %d earlier run(s) from okami_harness.csv -- a baseline"
             " from a previous session is still usable", loaded);
    }
}

static int harnessFpsNow() {
    return g_fps60 ? (g_fpsImmsFast ? 120 : 60) : 30;
}

static int harnessSlotFor(int fps) {
    if (g_cfg.passthrough) {
        return 3;
    }
    return fps >= 120 ? 2 : (fps >= 60 ? 1 : 0);
}

static const char* harnessSlotName(int slot, int fps, char* buf, size_t n) {
    if (slot == 3) {
        snprintf(buf, n, "stock");
    } else {
        snprintf(buf, n, "%d", fps);
    }
    return buf;
}

static void harnessReleasePad() {
    if (!g_eng.main) {
        return;
    }
    *(volatile uint64_t*)(g_eng.main + kPadHeld) &= ~kActJump;
    *(volatile uint64_t*)(g_eng.main + kPadPress) &= ~kActJump;
    *(volatile int8_t*)(g_eng.main + kPadStickX) = 0;
    *(volatile int8_t*)(g_eng.main + kPadStickY) = 0;
}

static void harnessTickImpl(uint8_t* pl) {
    if (!g_eng.playerSlot || pl != *g_eng.playerSlot) {
        return;  // some other actor using the same dispatcher
    }
    // a run has to happen entirely in one mode or the comparison is meaningless
    if (harnessFpsNow() != g_harnessFps) {
        InterlockedExchange(&g_harnessAbort, 1);
        InterlockedExchange(&g_harnessActive, 0);
        InterlockedExchange(&g_harnessDone, 1);
        harnessReleasePad();
        return;
    }
    double ms = (double)(qpc() - g_harnessStart) * 1000.0 / (double)g_qpcFreq;

    uint32_t acc = 0;
    const HarnessStep* step = nullptr;
    for (int i = 0; i < g_scriptN; i++) {
        if (ms < (double)(acc + g_script[i].ms)) {
            step = &g_script[i];
            break;
        }
        acc += g_script[i].ms;
    }
    if (!step) {
        InterlockedExchange(&g_harnessActive, 0);
        InterlockedExchange(&g_harnessDone, 1);
        harnessReleasePad();
        return;
    }

    InterlockedExchange(&g_harnessStepIdx, (LONG)(step - g_script));
    InterlockedExchange(&g_harnessMs, (LONG)ms);

    // sample before driving: this is what the previous tick produced
    HarnessRun& r = g_hruns[g_harnessSlot];
    uint8_t* xf = *(uint8_t**)(pl + 0xa8);
    if (xf && r.n >= HARNESS_MAX) {
        r.truncated = true;
    }
    // outside the buffer check: a truncated run still jumped, and reporting
    // otherwise would look like the variant-selector bug rather than a full
    // sample buffer
    if (pl[0xe35] == 3) {
        r.jumped = true;
    }
    if (xf && r.n < HARNESS_MAX) {
        if (r.n == 0) {
            r.startX = *(volatile float*)(xf + 0);
            r.startZ = *(volatile float*)(xf + 8);
        }
        // the base heading is whatever the camera had when the run began;
        // every turn after that is commanded relative to it
        if (!r.headingSet && (step->dirX || step->dirY)) {
            r.heading = *(volatile float*)(g_eng.main + kHeadingRef);
            r.headingSet = true;
        }
        HarnessSample& smp = r.s[r.n++];
        smp.ms = (float)ms;
        smp.x = *(volatile float*)(xf + 0);
        smp.y = *(volatile float*)(xf + 4);
        smp.z = *(volatile float*)(xf + 8);
        smp.hs = *(volatile float*)(pl + 0xe48);
        smp.vy = *(volatile float*)(pl + 0xe54);
        smp.b0 = *(volatile float*)(pl + 0xb0);
        smp.launch = *(volatile float*)(pl + 0xe14);
        smp.facing = *(volatile float*)(pl + kPlayerFacing);
        smp.ofsX = *(volatile float*)(pl + kPlayerOfsX);
        smp.ofsY = *(volatile float*)(pl + kPlayerOfsY);
        smp.ofsZ = *(volatile float*)(pl + kPlayerOfsZ);
        smp.animRate = *(volatile float*)(pl + kPlayerAnimRate);
        smp.st = pl[0xe35];
        smp.sub = pl[0xe36];
    }

    int mag = g_cfg.harnessStick;
    *(volatile int8_t*)(g_eng.main + kPadStickX) = (int8_t)(step->dirX * mag);
    *(volatile int8_t*)(g_eng.main + kPadStickY) = (int8_t)(step->dirY * mag);
    // command the direction as well as the magnitude, every tick
    if (r.headingSet && (step->dirX || step->dirY)) {
        float want = r.heading + step->dHeading;
        while (want > 3.14159265f) {
            want -= 6.28318531f;
        }
        while (want < -3.14159265f) {
            want += 6.28318531f;
        }
        *(volatile float*)(g_eng.main + kHeadingRef) = want;
    }
    if (step->actions) {
        *(volatile uint64_t*)(g_eng.main + kPadHeld) |= step->actions;
        uint64_t edge = step->actions & ~g_harnessPrevActions;
        if (edge) {
            *(volatile uint64_t*)(g_eng.main + kPadPress) |= edge;
        }
    }
    g_harnessPrevActions = step->actions;
}

extern "C" void harnessOnPlayerUpdate(uint8_t* pl) {
    if (!g_harnessActive) {
        return;
    }
    if (guardedCall([](void* p) { harnessTickImpl((uint8_t*)p); }, pl)) {
        InterlockedExchange(&g_harnessActive, 0);
        InterlockedExchange(&g_harnessAbort, 1);
        InterlockedExchange(&g_harnessDone, 1);
    }
}

// entry hook: save the volatiles, call the callback with rcx (the player) as
// its argument, restore, run the displaced instruction, continue. Written as
// bytes rather than a naked function so the MSVC build gets it too.
static bool installHarnessHook() {
    if (!g_cfg.harness || !g_eng.main) {
        return false;
    }
    uint8_t* site = g_eng.main + kHarnessHookRva;
    if (memcmp(site, kHarnessHookOrig, sizeof(kHarnessHookOrig)) != 0) {
        logf("harness: main+%X does not hold the expected prologue, not hooked",
             kHarnessHookRva);
        return false;
    }
    uint8_t* cave = allocNear(g_eng.main, 4096);
    if (!cave) {
        logf("harness: no code cave near main.dll");
        return false;
    }
    uint8_t* c = cave;
    size_t n = 0;
    memcpy(c + n, kHarnessStub, sizeof(kHarnessStub));
    uint64_t fn = (uint64_t)&harnessOnPlayerUpdate;
    memcpy(c + n + kHarnessStubFnAt, &fn, 8);
    n += sizeof(kHarnessStub);
    if (!copyDisplaced(c + n, kHarnessHookOrig, sizeof(kHarnessHookOrig), site)) {
        logf("harness: prologue cannot be relocated");
        return false;
    }
    n += sizeof(kHarnessHookOrig);
    c[n++] = 0xE9;
    int32_t back = (int32_t)((int64_t)(site + sizeof(kHarnessHookOrig)) - (int64_t)(c + n + 4));
    memcpy(c + n, &back, 4);
    n += 4;
    g_harnessTramp = cave;

    uint8_t patch[5];
    patch[0] = 0xE9;
    int64_t rel = (int64_t)cave - (int64_t)(site + 5);
    if (rel != (int32_t)rel) {
        logf("harness: cave out of reach");
        return false;
    }
    int32_t rel32 = (int32_t)rel;
    memcpy(patch + 1, &rel32, 4);
    if (!writeProtected(site, patch, sizeof(patch))) {
        logf("harness: could not write the hook");
        return false;
    }
    g_harnessHooked = true;
    harnessLoadScript();
    harnessLoad();
    logf("harness: player update hooked at main+%X (press %s to run the input script)",
         kHarnessHookRva, g_cfg.harnessName);
    return true;
}

static void harnessStart() {
    if (g_harnessActive) {
        return;
    }
    if (!g_harnessHooked) {
        logf("harness: not hooked (Harness=0, or the prologue at main+%X did not match),"
             " so there is nothing to run", kHarnessHookRva);
        snprintf(g_harnessOverlay, sizeof(g_harnessOverlay), "HARNESS NOT INSTALLED");
        return;
    }
    if (!g_eng.playerSlot || !*g_eng.playerSlot) {
        logf("harness: no player object -- load a save and stand on flat ground first");
        return;
    }
    g_harnessFps = harnessFpsNow();
    g_harnessSlot = harnessSlotFor(g_harnessFps);
    // keep the last run at this rate: running the same rate twice is the only
    // way to know the harness's own noise floor, and a delta smaller than that
    // floor means nothing
    if (g_hsum[g_harnessSlot].used) {
        g_hprevSum[g_harnessSlot] = g_hsum[g_harnessSlot];
    }
    HarnessRun& r = g_hruns[g_harnessSlot];
    r.used = true;
    r.fps = g_harnessFps;
    r.tickRate = 0.0f;
    r.n = 0;
    r.jumped = false;
    r.headingSet = false;
    r.truncated = false;
    r.heading = 0.0f;
    r.startX = r.startZ = 0.0f;
    g_harnessPrevActions = 0;
    InterlockedExchange(&g_harnessAbort, 0);
    InterlockedExchange(&g_harnessDone, 0);
    g_harnessStart = qpc();
    InterlockedExchange(&g_harnessActive, 1);
    logf("harness: run started at %d fps (%s script, %u ms) -- hands off the controller",
         g_harnessFps, g_scriptCustom ? "custom" : "built-in", g_scriptTotalMs);
    snprintf(g_harnessOverlay, sizeof(g_harnessOverlay), "HARNESS starting");
}

// distance travelled in the xz plane up to each sample
static double harnessDistAt(const HarnessRun& r, double ms, double* height) {
    if (r.n <= 0) {
        return 0.0;
    }
    double d = 0.0;
    double y0 = (double)r.s[0].y;
    double h = 0.0;
    for (int i = 1; i < r.n; i++) {
        if ((double)r.s[i].ms > ms) {
            break;
        }
        double dx = (double)r.s[i].x - (double)r.s[i - 1].x;
        double dz = (double)r.s[i].z - (double)r.s[i - 1].z;
        double step = sqrt(dx * dx + dz * dz);
        if (step < 300.0) {  // ignore warps
            d += step;
        }
        h = (double)r.s[i].y - y0;
    }
    if (height) {
        *height = h;
    }
    return d;
}

static void harnessReport() {
    if (g_harnessAbort) {
        logf("harness: run ABORTED (frame rate changed or the player went away) -- discarded");
        snprintf(g_harnessOverlay, sizeof(g_harnessOverlay), "HARNESS ABORTED");
        InterlockedExchange(&g_harnessStepIdx, -1);
        g_hruns[g_harnessSlot].used = false;
        InterlockedExchange(&g_harnessAbort, 0);
        return;
    }
    HarnessRun& r = g_hruns[g_harnessSlot];
    InterlockedExchange(&g_harnessStepIdx, -1);
    if (r.n < 8) {
        logf("harness: run produced only %d samples -- discarded", r.n);
        snprintf(g_harnessOverlay, sizeof(g_harnessOverlay), "HARNESS FAILED (no samples)");
        r.used = false;
        return;
    }
    // the rate the game actually ran at, which is what the numbers mean --
    // a 120 fps run that only reached 90 is not a 120 fps measurement
    double span = (double)r.s[r.n - 1].ms - (double)r.s[0].ms;
    r.tickRate = (span > 1.0) ? (float)((r.n - 1) * 1000.0 / span) : 0.0f;

    // summary
    double peak = 0.0, groundPeak = 0.0, airDist = 0.0, rise = 0.0;
    double airStartMs = -1.0, airEndMs = -1.0, launchY = 0.0;
    double wantSum = 0.0, gotSum = 0.0, blockedFromMs = -1.0;
    int lowRun = 0;
    for (int i = 1; i < r.n; i++) {
        double dt = ((double)r.s[i].ms - (double)r.s[i - 1].ms) / 1000.0;
        if (dt <= 1e-6) {
            continue;
        }
        double dx = (double)r.s[i].x - (double)r.s[i - 1].x;
        double dz = (double)r.s[i].z - (double)r.s[i - 1].z;
        double step = sqrt(dx * dx + dz * dz);
        if (step > 300.0) {
            continue;
        }
        // what the movement code asked for on this tick, against what it got
        double want = (double)r.s[i - 1].hs;
        if (want > 0.02) {
            wantSum += want;
            gotSum += step;
            if (step < want * 0.5) {
                if (++lowRun >= 5 && blockedFromMs < 0.0) {
                    blockedFromMs = (double)r.s[i - 4].ms;
                }
            } else {
                lowRun = 0;
            }
        }
        double v = step / dt;
        if (v > peak) {
            peak = v;
        }
        if (r.s[i].st != 3 && v > groundPeak) {
            groundPeak = v;
        }
        if (r.s[i].st == 3) {
            if (airStartMs < 0.0) {
                airStartMs = (double)r.s[i].ms;
                launchY = (double)r.s[i].y;
            }
            airEndMs = (double)r.s[i].ms;
            airDist += step;
            double up = (double)r.s[i].y - launchY;
            if (up > rise) {
                rise = up;
            }
        }
    }
    double totalDist = harnessDistAt(r, 1e9, nullptr);

    // A run where nothing moved compares against another such run as a perfect
    // 0% match, which is the most dangerous possible output: it reads as a
    // pass. Anything that could produce it gets called out before the numbers.
    bool moved = totalDist > 5.0;
    if (!moved) {
        logf("harness: *** RUN INVALID -- Amaterasu did not move (%.1f units) ***", totalDist);
        logf("harness:     the input injection did not reach the movement code, or she was");
        logf("harness:     not free to move (cutscene, menu, water, wall). Do NOT compare");
        logf("harness:     this run: two runs that both fail this way report a 0%% delta.");
        snprintf(g_harnessOverlay, sizeof(g_harnessOverlay), "HARNESS INVALID (no movement)");
        r.used = false;
        return;
    }
    double moveEff = (wantSum > 1e-6) ? gotSum / wantSum : 1.0;
    bool blocked = moveEff < 0.70;
    if (blocked) {
        logf("harness: *** RUN BLOCKED -- she only travelled %.0f%% of what the movement"
             " code asked for ***", moveEff * 100.0);
        logf("harness:     pl00+0xE48 is the displacement the code requested for each tick,"
             " and she covered %.1f of an intended %.1f units.", gotSum, wantSum);
        if (blockedFromMs >= 0.0) {
            logf("harness:     first pinned at %.0f ms into the run.", blockedFromMs);
        }
        logf("harness:     She was against geometry. Every DISTANCE in this run is wrong --"
             " total, air distance and the grid. The per-tick speed field is still valid,"
             " because a wall does not change what the controller asks for. Re-run on open"
             " ground before comparing distances.");
    } else if (moveEff < 0.92) {
        logf("harness:   NOTE travelled %.0f%% of the requested distance -- she brushed"
             " something; treat small distance deltas with suspicion", moveEff * 100.0);
    }
    if (!r.jumped) {
        logf("harness: WARNING -- she never left the ground; the jump half of this run is"
             " meaningless (wrong action bit, or no room to jump)");
    }
    if (r.truncated) {
        logf("harness: WARNING -- sample buffer full, the tail of this run was dropped");
    }
    double nominal = (double)r.fps;
    if (r.tickRate > 1.0f && fabs((double)r.tickRate - nominal) > nominal * 0.10) {
        logf("harness: WARNING -- configured %d fps but the run actually ticked at %.1f/s;"
             " the comparison is against the achieved rate, not the intended one",
             r.fps, (double)r.tickRate);
    }
    char myName[16];
    harnessSlotName(g_harnessSlot, r.fps, myName, sizeof(myName));
    logf("harness: [%s] run complete -- %d ticks at %.1f/s, %.1f total dist, "
         "ground peak %.1f/s, air peak %.1f/s", myName, r.n, (double)r.tickRate, totalDist,
         groundPeak, peak);
    logf("harness:   start (%.1f, %.1f) target heading %.3f rad%s", (double)r.startX,
         (double)r.startZ, (double)r.heading,
         r.headingSet ? "" : " (never sampled -- the stick never left centre)");
    double travelDir = atan2((double)r.s[r.n - 1].z - (double)r.s[0].z,
                             (double)r.s[r.n - 1].x - (double)r.s[0].x);
    logf("harness:   travelled %.3f rad from start, facing %.3f -> %.3f",
         travelDir, (double)r.s[0].facing, (double)r.s[r.n - 1].facing);
    // Did the commanded turns actually happen? If the heading write is not
    // reaching the movement code this is the line that says so, rather than the
    // run quietly measuring a straight line and calling it a turn.
    {
        float fmin = r.s[0].facing, fmax = r.s[0].facing;
        for (int i = 1; i < r.n; i++) {
            if (r.s[i].facing < fmin) {
                fmin = r.s[i].facing;
            }
            if (r.s[i].facing > fmax) {
                fmax = r.s[i].facing;
            }
        }
        float swept = fmax - fmin;
        float asked = 0.0f;
        for (int i = 0; i < g_scriptN; i++) {
            float d = g_script[i].dHeading;
            if (d < 0.0f) {
                d = -d;
            }
            if (d > asked) {
                asked = d;
            }
        }
        logf("harness:   facing swept %.3f rad, script asked for %.3f%s", (double)swept,
             (double)(asked * 2.0f),
             (swept < asked) ? "  *** SHE DID NOT TURN -- heading command not reaching"
                               " the movement code, every turn result is void ***"
                             : "");
    }

    // Tick regularity. A run with a stall in it is not comparable with a clean
    // one however close the totals land, and the totals alone will not show it.
    double dtMin = 1e9, dtMax = 0.0, dtSum = 0.0, dtSum2 = 0.0;
    for (int i = 1; i < r.n; i++) {
        double dt = (double)r.s[i].ms - (double)r.s[i - 1].ms;
        if (dt < dtMin) {
            dtMin = dt;
        }
        if (dt > dtMax) {
            dtMax = dt;
        }
        dtSum += dt;
        dtSum2 += dt * dt;
    }
    int nd = r.n - 1;
    double dtMean = nd > 0 ? dtSum / nd : 0.0;
    double dtSd = (nd > 1) ? sqrt(fabs(dtSum2 / nd - dtMean * dtMean)) : 0.0;
    logf("harness:   tick interval %.2f ms mean, %.2f-%.2f, sd %.2f%s", dtMean, dtMin, dtMax,
         dtSd, (dtMax > dtMean * 3.0 && dtMax > 20.0) ? "   <- STALLED, run is suspect" : "");

    // What the run actually exercised. "We tested it and it was fine" is worth
    // nothing if the script never reached the code, and every fix in this patch
    // has a condition under which it does nothing at all.
    float b0Max = 0.0f, launchMax = 0.0f, hsMax = 0.0f;
    int airTicks = 0;
    uint8_t subSeen[256];
    memset(subSeen, 0, sizeof(subSeen));
    for (int i = 0; i < r.n; i++) {
        if (fabs((double)r.s[i].b0) > (double)b0Max) {
            b0Max = (float)fabs((double)r.s[i].b0);
        }
        if (r.s[i].launch > launchMax) {
            launchMax = r.s[i].launch;
        }
        if (r.s[i].hs > hsMax) {
            hsMax = r.s[i].hs;
        }
        if (r.s[i].st == 3) {
            airTicks++;
        }
        subSeen[r.s[i].sub] = 1;
    }
    char subs[96];
    size_t sn = 0;
    for (int i = 0; i < 256 && sn + 5 < sizeof(subs); i++) {
        if (subSeen[i]) {
            sn += (size_t)snprintf(subs + sn, sizeof(subs) - sn, "%s%02X", sn ? "," : "", i);
        }
    }
    logf("harness:   coverage: peak per-tick speed %.3f, %d airborne ticks, sub-states {%s}",
         (double)hsMax, airTicks, subs);
    logf("harness:   coverage: launch velocity peaked at %.2f (%s)", (double)launchMax,
         launchMax > 5.0f ? "running jump -- the fast variant was reached"
                          : (launchMax > 0.1f ? "STANDING jump only -- the running variant"
                                                " was never selected"
                                              : "no jump recorded"));
    if (b0Max < 0.01f) {
        logf("harness:   coverage: pl00+0xB0 stayed at 0, so this run was entirely on flat"
             " ground -- FixSlopeTerm and the takeoff slope term were NOT exercised."
             " Repeat on a hill to test those.");
    } else {
        logf("harness:   coverage: pl00+0xB0 reached %.3f, so the slope terms were"
             " exercised", (double)b0Max);
    }
    logf("harness:   jump rise %.1f, airborne %.0f ms, air distance %.1f (%.1f/s)",
         rise, (airEndMs >= 0.0 ? airEndMs - airStartMs : 0.0), airDist,
         (airEndMs > airStartMs) ? airDist * 1000.0 / (airEndMs - airStartMs) : 0.0);

    // condense to the record that outlives the process
    HarnessSummary sum;
    memset(&sum, 0, sizeof(sum));
    sum.used = true;
    sum.stock = g_cfg.passthrough;
    sum.fps = r.fps;
    sum.tickRate = r.tickRate;
    sum.heading = r.heading;
    sum.startX = r.startX;
    sum.startZ = r.startZ;
    sum.jumped = r.jumped;
    sum.totalDist = (float)totalDist;
    sum.groundPeak = (float)groundPeak;
    sum.airPeak = (float)peak;
    sum.rise = (float)rise;
    sum.airMs = (float)(airEndMs >= 0.0 ? airEndMs - airStartMs : 0.0);
    sum.airDist = (float)airDist;
    sum.travelDir = (float)travelDir;
    sum.moveEff = (float)moveEff;
    sum.gridMs = (float)g_scriptTotalMs / (float)HARNESS_GRID;
    for (int g = 0; g < HARNESS_GRID; g++) {
        double h = 0.0;
        sum.dist[g] = (float)harnessDistAt(r, (double)(g + 1) * (double)sum.gridMs, &h);
        sum.height[g] = (float)h;
    }
    SYSTEMTIME st;
    GetLocalTime(&st);
    snprintf(sum.stamp, sizeof(sum.stamp), "%04u-%02u-%02u_%02u:%02u:%02u", st.wYear,
             st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    g_hsum[g_harnessSlot] = sum;
    harnessSave();

    // the full per-tick trace, so a run can be taken apart offline instead of
    // only compared against another run through the summary
    {
        char tpath[MAX_PATH];
        if (g_cfg.passthrough) {
            snprintf(tpath, sizeof(tpath), "%sokami_harness_stock.csv", g_baseDir);
        } else {
            snprintf(tpath, sizeof(tpath), "%sokami_harness_%dfps.csv", g_baseDir, r.fps);
        }
        // Do not overwrite the last trace at this rate. Two runs in a row is
        // the documented procedure for the noise floor, and losing the first
        // one to the second is exactly what happened on the first real session.
        char prev[MAX_PATH];
        snprintf(prev, sizeof(prev), "%.*s.prev.csv", (int)(strlen(tpath) - 4), tpath);
        remove(prev);
        rename(tpath, prev);
        FILE* tf = fopen(tpath, "w");
        if (tf) {
            fprintf(tf, "# %s  %d fps nominal, %.1f/s achieved, heading %.4f,"
                        " moveEff %.3f%s\n", sum.stamp, r.fps, (double)r.tickRate,
                    (double)r.heading, moveEff, blocked ? " BLOCKED" : "");
            fprintf(tf, "tick,ms,x,y,z,hspeed,vy,b0,launch,facing,ofsx,ofsy,ofsz,animrate,state,sub\n");
            for (int i = 0; i < r.n; i++) {
                const HarnessSample& q = r.s[i];
                fprintf(tf,
                        "%d,%.2f,%.3f,%.3f,%.3f,%.5f,%.5f,%.5f,%.3f,%.4f,"
                        "%.5f,%.5f,%.5f,%.5f,%02X,%02X\n",
                        i, (double)q.ms, (double)q.x, (double)q.y, (double)q.z,
                        (double)q.hs, (double)q.vy, (double)q.b0, (double)q.launch,
                        (double)q.facing, (double)q.ofsX, (double)q.ofsY, (double)q.ofsZ,
                        (double)q.animRate, q.st, q.sub);
            }
            fclose(tf);
            logf("harness:   per-tick trace written to %s (%d rows)",
                 g_cfg.passthrough ? "okami_harness_stock.csv" : tpath, r.n);
        }
    }

    // the same rate run twice: this is the noise floor, and nothing smaller
    // than it is a result
    const HarnessSummary& pv = g_hprevSum[g_harnessSlot];
    if (pv.used) {
        double spread = (pv.totalDist > 0.5)
                            ? fabs((double)sum.totalDist - (double)pv.totalDist) * 100.0 /
                                  (double)pv.totalDist
                            : 0.0;
        logf("harness: repeatability at [%s] -- %.1f (%s) then %.1f, spread %.1f%%."
             " Treat any cross-rate delta below this as noise.",
             myName, (double)pv.totalDist, pv.stamp, (double)sum.totalDist, spread);
    } else {
        logf("harness: no repeat run at [%s] yet -- press the key twice in the same mode"
             " to establish the noise floor before trusting a cross-rate delta", myName);
    }

    // compare against every other rate on record, including runs loaded from
    // disk -- an earlier session, or an earlier build
    for (int other = 0; other < 4; other++) {
        if (other == g_harnessSlot || !g_hsum[other].used) {
            continue;
        }
        const HarnessSummary& b = g_hsum[other];
        char bName[16];
        harnessSlotName(other, b.fps, bName, sizeof(bName));
        logf("harness: ==== [%s] %s vs [%s] %s ====", bName, b.stamp, myName, sum.stamp);
        if (b.stock != sum.stock) {
            logf("harness:   (this is the comparison that matters: one side is the"
                 " unpatched game)");
        }
        if (b.tickRate > 1.0f &&
            fabs((double)b.tickRate - (double)b.fps) > (double)b.fps * 0.10) {
            logf("harness:   WARNING the [%s] baseline actually ticked at %.1f/s",
                 bName, (double)b.tickRate);
        }
        double dh = fabs((double)b.heading - (double)sum.heading);
        if (dh > 3.14159) {
            dh = 6.28318 - dh;
        }
        if (dh > 0.20) {
            logf("harness:   WARNING target heading differed by %.2f rad between these"
                 " runs -- same stick, different camera, so she was asked to run in a"
                 " different direction. Airborne acceleration is scaled by how well the"
                 " facing matches it, so this comparison is confounded.", dh);
        }
        double dx0 = (double)b.startX - (double)sum.startX;
        double dz0 = (double)b.startZ - (double)sum.startZ;
        double dstart = sqrt(dx0 * dx0 + dz0 * dz0);
        if (dstart > 30.0) {
            logf("harness:   WARNING runs started %.0f units apart; different ground means"
                 " different slope terms", dstart);
        }
        if (!b.jumped || !sum.jumped) {
            logf("harness:   WARNING one of these runs never left the ground");
        }
        if (b.moveEff < 0.70f || sum.moveEff < 0.70f) {
            logf("harness:   *** one of these runs was BLOCKED ([%s] %.0f%%, [%s] %.0f%%) --"
                 " every distance below is meaningless ***", bName, (double)b.moveEff * 100.0,
                 myName, (double)sum.moveEff * 100.0);
        }
        double dTravel = fabs((double)b.travelDir - (double)sum.travelDir);
        if (dTravel > 3.14159) {
            dTravel = 6.28318 - dTravel;
        }
        if (dTravel > 0.25) {
            logf("harness:   *** these runs travelled in DIFFERENT DIRECTIONS (%.2f rad"
                 " apart) ***", dTravel);
            logf("harness:       The script drives the stick, but the direction she turns"
                 " towards comes from main+B6B134, which the pad task may compute before"
                 " the injected stick is written. Same distance in different directions"
                 " is not the same experiment -- re-run both with the camera untouched"
                 " and from the same spot.");
        }
        if (b.gridMs > 0.1f && fabs((double)b.gridMs - (double)sum.gridMs) > 1.0) {
            logf("harness:   *** these two runs used DIFFERENT SCRIPTS (%.0f ms vs %.0f ms"
                 " total) -- the columns line up but they are not the same experiment ***",
                 (double)b.gridMs * HARNESS_GRID, (double)sum.gridMs * HARNESS_GRID);
        }
        logf("harness:    t(ms)  dist%-5s dist%-5s  delta   height%-5s height%-5s",
             bName, myName, bName, myName);
        for (int g = 0; g < HARNESS_GRID; g++) {
            double db = (double)b.dist[g];
            double dr = (double)sum.dist[g];
            double delta = (db > 0.5) ? (dr - db) * 100.0 / db : 0.0;
            logf("harness:   %6u  %8.1f  %8.1f  %+6.1f%%  %9.1f %9.1f",
                 (unsigned)((g + 1) * (double)sum.gridMs), db, dr, delta,
                 (double)b.height[g], (double)sum.height[g]);
        }
        double pct = (b.totalDist > 0.5)
                         ? ((double)sum.totalDist - (double)b.totalDist) * 100.0 /
                               (double)b.totalDist
                         : 0.0;
        logf("harness:   TOTAL   %8.1f  %8.1f  %+6.1f%%   <- 0%% means the two rates match"
             " (at %.1f/s vs %.1f/s actual)",
             (double)b.totalDist, (double)sum.totalDist, pct, (double)b.tickRate,
             (double)sum.tickRate);
        logf("harness:   jump    rise %.1f vs %.1f, air %.0f ms vs %.0f ms,"
             " air dist %.1f vs %.1f",
             (double)b.rise, (double)sum.rise, (double)b.airMs, (double)sum.airMs,
             (double)b.airDist, (double)sum.airDist);
        if (b.moveEff < 0.70f || sum.moveEff < 0.70f) {
            snprintf(g_harnessOverlay, sizeof(g_harnessOverlay),
                     "HARNESS BLOCKED (%.0f%% travelled) -- MOVE TO OPEN GROUND",
                     (double)(sum.moveEff < b.moveEff ? sum.moveEff : b.moveEff) * 100.0);
            break;
        }
        snprintf(g_harnessOverlay, sizeof(g_harnessOverlay), "HARNESS %s vs %s: %+.1f%%",
                 bName, myName, pct);
    }
}

// ---------------------------------------------------------------------------
// Jump measurement
//
// "Can I clear this wall" is a question about how far she rises, so measure
// exactly that: from the sample where the vertical velocity turns positive to
// the one where it turns negative again. That definition also covers the wall
// jump, whose impulse lands part-way through a fall. The launch velocity is
// reported back out of the rise (v0 = sqrt(2 * g * rise)) rather than sampled
// directly, because the sampler can only ever catch it a few milliseconds
// late, by which point gravity has already eaten into it.
// ---------------------------------------------------------------------------

static volatile LONG g_lastJumpRise = 0;  // units x 10, for the overlay

// The wind-up is the window in which holding the button charges the launch
// accumulator: pl00+0xE3C counts it down and pl00+0xE14 grows while it lasts.
// Recording how long it really ran, and how far the accumulator actually got,
// is the only way to tell a window that is too short from a charge rate that
// is too low -- the launch velocity alone cannot separate them.
static double g_windupMs = 0.0;    // duration of the last wind-up
static float g_windupPeak = 0.0f;  // the accumulator's value at its end

static void trackWindup(uint16_t timer, float launch) {
    static bool winding = false;
    static LONGLONG start = 0;
    static float peak = 0.0f;
    if (timer > 0) {
        if (!winding) {
            winding = true;
            start = qpc();
            peak = launch;
        } else if (launch > peak) {
            peak = launch;
        }
    } else if (winding) {
        winding = false;
        g_windupMs = (double)(qpc() - start) * 1000.0 / (double)g_qpcFreq;
        g_windupPeak = peak;
    }
}

// Tracing a jump
//
// Three sessions of static analysis produced two confident fixes that changed
// nothing measurable, because I was reading the ground movement target while
// every `peak=` in the log was tagged `@03` -- airborne. The way out of that is
// not another hypothesis, it is a measurement that distinguishes them.
//
// So the trace records both sides at once: the world-space distance actually
// covered since the previous sample, and the velocity fields that are supposed
// to explain it. If `world` matches `E48 * ticks_per_second`, the overspeed is
// in the speed field and the target is the place to look. If it does not,
// something else is moving her and no amount of work on the target will help.
static void trackJump(float y, float vy, const uint8_t st[2]) {
    static bool airborne = false;
    static float baseY = 0.0f;
    static float peakY = 0.0f;
    static float prevVy = 0.0f;
    static float peakVy = 0.0f;
    static int traced = 0;
    static LONGLONG launchAt = 0;
    static uint8_t launchState[2] = {0, 0};
    // horizontal speed at take-off, so a jump that feels wrong can be
    // attributed to the arc rather than to how fast she was already moving
    static float launchSpeed = 0.0f;
    // previous sample's world position, for the trace's ground-truth speed
    static float traceX = 0.0f, traceZ = 0.0f;
    static LONGLONG traceAt = 0;
    if (!airborne) {
        if (prevVy <= 0.0f && vy > 0.5f) {
            airborne = true;
            baseY = y;
            peakY = y;
            peakVy = vy;
            traced = 0;
            launchAt = qpc();
            launchState[0] = st[0];
            launchState[1] = st[1];
            launchSpeed = g_plVel[0];
            traceX = g_plPos[0];
            traceZ = g_plPos[2];
            traceAt = qpc();
        }
    } else {
        if (y > peakY) {
            peakY = y;
        }
        if (vy > peakVy) {
            peakVy = vy;
        }
        // the per-sample climb: enough to recover the real per-tick gravity in
        // each mode and to see any stretch where it is suppressed
        if (g_cfg.jumpTrace && traced < 80) {
            traced++;
            int hz = g_fps60 ? (g_fpsImmsFast ? 120 : 60) : 30;
            double dx = (double)g_plPos[0] - (double)traceX;
            double dz = (double)g_plPos[2] - (double)traceZ;
            double dt = (double)(qpc() - traceAt) / (double)g_qpcFreq;
            double world = (dt > 1e-6) ? sqrt(dx * dx + dz * dz) / dt : 0.0;
            logf("  jtrace %2d y %+8.2f vy %6.3f | world %7.1f/s | E48 %6.3f (%6.1f/s) "
                 "E4C %6.3f E50 %6.3f E58 %6.3f E5C %6.3f | b0 %5.3f sub %02X flags %08X",
                 traced, (double)(y - baseY), (double)vy, world,
                 (double)g_plVel[0], (double)g_plVel[0] * hz,
                 (double)g_plVel[1], (double)g_plVel[2],
                 (double)g_plVel[4], (double)g_plVel[5],
                 (double)g_plB0, g_plSub, g_plFlags);
            traceX = g_plPos[0];
            traceZ = g_plPos[2];
            traceAt = qpc();
        }
        if (vy <= 0.0f) {
            airborne = false;
            double rise = (double)peakY - (double)baseY;
            double climbMs = (double)(qpc() - launchAt) * 1000.0 / (double)g_qpcFreq;
            // a room change moves her hundreds of units in one sample
            if (rise > 0.5 && rise < 500.0) {
                InterlockedExchange(&g_lastJumpRise, (LONG)(rise * 10.0));
                // vy at launch and the time spent climbing separate a weaker
                // launch from a stronger gravity: both would shorten the rise
                // vy at launch and the time spent climbing separate a weaker
                // launch from a stronger gravity: both shorten the rise. "want"
                // is the rise that launch velocity should give against the
                // engine's own gravity, so rise/want below 1 means the flight
                // is losing height that the launch had paid for.
                double want = (double)peakVy * (double)peakVy / (2.0 * (double)kGravityPerTick);
                // the horizontal speed field is in units per tick, so the
                // real-world figure needs the tick rate this mode runs at
                int hz = g_fps60 ? (g_fpsImmsFast ? 120 : 60) : 30;
                // the fingerprint, not one flag: this is the line that gets
                // compared across modes, so it has to say for itself which
                // state it was measured in
                char fp[64];
                fixFingerprint(fp, sizeof(fp));
                logf("jump: rise %.1f (want %.1f) vy %.2f climb %.0f ms | hs %.3f/tick "
                     "(%.0f/s) | windup %.0f ms -> %.2f | state %02X/%02X fps=%d %s",
                     rise, want, (double)peakVy, climbMs,
                     (double)launchSpeed, (double)launchSpeed * hz,
                     g_windupMs, (double)g_windupPeak,
                     launchState[0], launchState[1], hz, fp);
            }
        }
    }
    prevVy = vy;
}

// ---------------------------------------------------------------------------
// On-screen overlay (a small topmost layered window over the game)
//
// The game runs borderless, so a click-through topmost window is enough to
// show which mode and which experimental gate set is active without having
// to read the log. GDI only: it never touches the swap chain.
// ---------------------------------------------------------------------------

static HWND g_overlayWnd = nullptr;
static SRWLOCK g_overlayLock = SRWLOCK_INIT;
static char g_overlayText[640] = "";
// up to three lines: the status; while one is up, the loading screen's rates
// (the tracer build puts its step and instruction there instead), otherwise
// the integer family's check; and the day/night clock's
static const int kOverlayH = 86;
static const int kOverlayWarnH = 26;  // one more line for the red NOT INSTALLED one
static char g_installProblems[240] = "";  // noteInstallProblems
static const int kOverlayW = 1200;  // ~100 characters: the whole loading line fits
static const int kNoticeW = 760, kNoticeH = 40;  // a notice's window (the width if unmeasured)
static HWND g_gameWnd = nullptr;
// horizontal player speed over the last second, for the overlay: an objective
// readout of whether an experimental gate set has slowed gameplay down
static volatile LONG g_liveSpeed = 0;

// Rolling tick and present rate, updated about once a second.
//
// Without this on screen there is no way to tell a 120 fps run from a 120 fps
// run that only achieved 95 because something else was loading -- and the two
// produce completely different numbers from an identical script. The status
// line has carried these for a while, but only every five seconds and only in
// the log, which is no use while deciding whether the run you just did counts.
static volatile LONG g_liveTicks = 0;    // ticks per second x10
static volatile LONG g_livePresents = 0;  // presents per second x10

static BOOL CALLBACK findGameWnd(HWND h, LPARAM) {
    DWORD pid = 0;
    GetWindowThreadProcessId(h, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(h) || GetWindow(h, GW_OWNER)) {
        return TRUE;
    }
    RECT r;
    if (!GetWindowRect(h, &r) || (r.right - r.left) < 320 || (r.bottom - r.top) < 240) {
        return TRUE;
    }
    g_gameWnd = h;
    return FALSE;
}

static void setOverlayText(const char* text) {
    AcquireSRWLockExclusive(&g_overlayLock);
    snprintf(g_overlayText, sizeof(g_overlayText), "%s", text);
    ReleaseSRWLockExclusive(&g_overlayLock);
    if (g_overlayWnd) {
        InvalidateRect(g_overlayWnd, nullptr, TRUE);
    }
}

// A notice for a few seconds (the frame rate after F9, a failed install),
// shown by the same window when the status overlay is off: then the window is
// only up while a notice is. With the overlay on, notices go to the log only:
// the status line already carries the mode and the red NOT INSTALLED line.
static char g_noticeText[200] = "";
static volatile LONG g_noticeSerial = 0;  // bumped per notice, so the window refits its text
static volatile LONGLONG g_noticeUntilMs = 0;
static volatile LONG g_noticeDeferMs = 0;  // a start-up notice's length, timed from the window
static bool g_noticeWarn = false;

// `deferred`: the notice's time starts when the game window is first found
// (the start-up notice is raised before the game has a window)
static void showNotice(const char* text, int ms, bool warn = false, bool deferred = false) {
    AcquireSRWLockExclusive(&g_overlayLock);
    snprintf(g_noticeText, sizeof(g_noticeText), "%s", text);
    g_noticeWarn = warn;
    ReleaseSRWLockExclusive(&g_overlayLock);
    InterlockedIncrement(&g_noticeSerial);
    if (deferred) {
        InterlockedExchange(&g_noticeDeferMs, ms);
    } else {
        InterlockedExchange(&g_noticeDeferMs, 0);
        InterlockedExchange64(&g_noticeUntilMs, (LONGLONG)GetTickCount64() + ms);
    }
    logf("notice: %s", text);
    if (g_overlayWnd) {
        InvalidateRect(g_overlayWnd, nullptr, TRUE);
    }
}

static bool noticeActive() {
    return !g_cfg.overlay &&
           (g_noticeDeferMs > 0 || (LONGLONG)GetTickCount64() < g_noticeUntilMs);
}

static HFONT overlayFont() {
    return CreateFontA(22, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                       OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, FF_DONTCARE,
                       "Consolas");
}

// the notice's window fits its text; a fixed width cut the install warning off
static int noticeWidth() {
    char text[sizeof(g_noticeText)];
    AcquireSRWLockShared(&g_overlayLock);
    snprintf(text, sizeof(text), "%s", g_noticeText);
    ReleaseSRWLockShared(&g_overlayLock);
    int w = kNoticeW;
    HDC dc = GetDC(g_overlayWnd);
    if (dc) {
        HFONT font = overlayFont();
        HGDIOBJ old = SelectObject(dc, font);
        SIZE sz;
        if (GetTextExtentPoint32A(dc, text, (int)strlen(text), &sz)) {
            w = sz.cx + 24;  // the 10 px the text is drawn in by, and a margin
        }
        SelectObject(dc, old);
        DeleteObject(font);
        ReleaseDC(g_overlayWnd, dc);
    }
    return w;
}

static LRESULT CALLBACK overlayProc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        RECT rc;
        GetClientRect(h, &rc);
        HBRUSH bg = CreateSolidBrush(RGB(8, 8, 8));
        FillRect(dc, &rc, bg);
        DeleteObject(bg);
        HFONT font = overlayFont();
        HGDIOBJ oldFont = SelectObject(dc, font);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, RGB(255, 210, 70));
        char text[sizeof(g_overlayText)];
        bool warn = false;
        AcquireSRWLockShared(&g_overlayLock);
        if (!g_cfg.overlay) {
            snprintf(text, sizeof(text), "%s", g_noticeText);
            warn = g_noticeWarn;
        } else {
            memcpy(text, g_overlayText, sizeof(text));
        }
        ReleaseSRWLockShared(&g_overlayLock);
        text[sizeof(text) - 1] = 0;
        RECT tr = rc;
        tr.left += 10;
        const char* nl = strchr(text, '\n');
        if (!g_cfg.overlay) {
            SetTextColor(dc, warn ? RGB(255, 80, 80) : RGB(255, 210, 70));
            DrawTextA(dc, text, -1, &tr, DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX);
        } else if (nl && !strncmp(text, "!! ", 3)) {
            // the NOT INSTALLED line in red, the rest as usual below it
            tr.top += 4;
            SetTextColor(dc, RGB(255, 80, 80));
            DrawTextA(dc, text, (int)(nl - text), &tr, DT_LEFT | DT_SINGLELINE | DT_NOPREFIX);
            SetTextColor(dc, RGB(255, 210, 70));
            tr.top += kOverlayWarnH;
            DrawTextA(dc, nl + 1, -1, &tr, DT_LEFT | DT_NOPREFIX);
        } else if (nl) {
            tr.top += 4;
            DrawTextA(dc, text, -1, &tr, DT_LEFT | DT_NOPREFIX);
        } else {
            DrawTextA(dc, text, -1, &tr, DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX);
        }
        SelectObject(dc, oldFont);
        DeleteObject(font);
        EndPaint(h, &ps);
        return 0;
    }
    if (msg == WM_DESTROY) {
        g_overlayWnd = nullptr;
        return 0;
    }
    return DefWindowProcA(h, msg, wp, lp);
}

static DWORD WINAPI overlayThread(LPVOID) {
    WNDCLASSEXA wc;
    memset(&wc, 0, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = overlayProc;
    wc.hInstance = g_ourInstance;
    wc.hCursor = LoadCursorA(nullptr, (LPCSTR)IDC_ARROW);
    wc.lpszClassName = "OkamiHackfixOverlay";
    if (!RegisterClassExA(&wc)) {
        logf("overlay: RegisterClass failed (%lu)", GetLastError());
        return 0;
    }
    g_overlayWnd = CreateWindowExA(
        WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        wc.lpszClassName, "okami hackfix", WS_POPUP, 40, 40, kOverlayW, kOverlayH, nullptr, nullptr,
        g_ourInstance, nullptr);
    if (!g_overlayWnd) {
        logf("overlay: CreateWindow failed (%lu)", GetLastError());
        return 0;
    }
    SetLayeredWindowAttributes(g_overlayWnd, 0, 205, LWA_ALPHA);
    if (g_cfg.overlay) {
        ShowWindow(g_overlayWnd, SW_SHOWNA);
    }
    logf("overlay: window created%s", g_cfg.overlay ? "" : " (notices only)");
    int reposition = 0;
    bool shown = g_cfg.overlay;
    LONG shownSerial = 0;
    for (;;) {
        MSG m;
        while (PeekMessageA(&m, nullptr, 0, 0, PM_REMOVE)) {
            TranslateMessage(&m);
            DispatchMessageA(&m);
        }
        if (!g_cfg.overlay) {
            // notices only: up while one lasts, placed over the game window
            bool want = noticeActive();
            LONG serial = g_noticeSerial;
            if (want && (!shown || serial != shownSerial)) {
                g_gameWnd = nullptr;
                EnumWindows(findGameWnd, 0);
                RECT r;
                if (g_gameWnd && GetWindowRect(g_gameWnd, &r)) {
                    LONG defer = InterlockedExchange(&g_noticeDeferMs, 0);
                    if (defer > 0) {
                        InterlockedExchange64(&g_noticeUntilMs,
                                              (LONGLONG)GetTickCount64() + defer);
                    }
                    SetWindowPos(g_overlayWnd, HWND_TOPMOST, r.left + 40, r.top + 40,
                                 noticeWidth(), kNoticeH, SWP_NOACTIVATE | SWP_SHOWWINDOW);
                    InvalidateRect(g_overlayWnd, nullptr, TRUE);
                    shown = true;
                    shownSerial = serial;
                }
            } else if (!want && shown) {
                ShowWindow(g_overlayWnd, SW_HIDE);
                shown = false;
            }
            Sleep(50);
            continue;
        }
        if (--reposition <= 0) {
            reposition = 20;  // ~1 s
            g_gameWnd = nullptr;
            EnumWindows(findGameWnd, 0);
            RECT r;
            if (g_gameWnd && GetWindowRect(g_gameWnd, &r)) {
                int h = kOverlayH + (g_installProblems[0] ? kOverlayWarnH : 0);
                SetWindowPos(g_overlayWnd, HWND_TOPMOST, r.left + 40, r.top + 40, kOverlayW, h,
                             SWP_NOACTIVATE | SWP_SHOWWINDOW);
            }
        }
        Sleep(50);
    }
}

// label for gate set n (1-based) from GateSetNames, or "set n"
static const char* gateSetLabel(int n, char* buf, size_t bufLen) {
    const char* p = g_cfg.gateSetNames;
    for (int i = 1; i < n && *p; i++) {
        const char* bar = strchr(p, '|');
        if (!bar) {
            p = "";
            break;
        }
        p = bar + 1;
    }
    if (n <= 0 || !*p) {
        // an unnamed set still needs a label; "set %d" had no argument here
        if (n > 0) {
            snprintf(buf, bufLen, "set %d", n);
        } else {
            snprintf(buf, bufLen, "off");
        }
        return buf;
    }
    const char* bar = strchr(p, '|');
    size_t len = bar ? (size_t)(bar - p) : strlen(p);
    if (len >= bufLen) {
        len = bufLen - 1;
    }
    memcpy(buf, p, len);
    buf[len] = 0;
    return buf;
}

// ---------------------------------------------------------------------------
// Loading-screen field watch
//
// cCockLoading (vtable main+6AFF88) animates two things the eye reads as speed:
//   +0x6C  the sign's phase: +0.3 per update, wrapped into +-pi by 13F2E0; the
//          draw scales the sign by 1 + 0.1 sin(phase), one pulse per 2pi/0.3
//          updates, 0.70 s at the stock 30 Hz (phase_steps.h, main+4003AF)
//   +0x70  the dot count: +1 when the frame counter's % 10 gate fires, back to 0
//          after 8, one dot per 10 stock ticks, 0.33 s (frame_clocks.h, 4003E0)
// Slot 3 of the vtable, its update (main+400370), is the only pointer to that
// function in the image, so pointing it at a wrapper sees every live instance
// without touching code. The wrapper runs the original, then times both fields
// in real seconds. The overlay shows them on a second line while a loading
// screen is up, and the log gets one line per screen. Installed in every mode,
// Passthrough included, so the stock run is measured the same way.
// ---------------------------------------------------------------------------

static const uint32_t kLoadingVtableSlotRva = 0x6AFFA0;  // vtable 6AFF88, slot 3
static const uint32_t kLoadingUpdateRva = 0x400370;
static const double kStockDotSecs = 10.0 / 30.0;
static const double kStockSignSecs = 6.283185307179586 / 0.3 / 30.0;

typedef void (*LoadingUpdateFn)(void*);
static LoadingUpdateFn g_loadingUpdateOrig = nullptr;

struct LoadingWatch {
    LONGLONG startedAt, lastSeen;  // qpc; lastSeen 0 = no screen up
    uint32_t updates;
    float phase;
    int dots;
    LONGLONG dotAt, wrapAt;  // qpc of the last dot and the last sign wrap, 0 = none yet
    uint32_t dotFc;          // the frame counter at the last dot
    double dotSum, wrapSum, dotTicks;
    int dotN, wrapN;
};
static LoadingWatch g_lw = {};
static SRWLOCK g_lwLock = SRWLOCK_INIT;

// One update's fields at time `now` (qpc) and frame counter `fc`.
static void loadingSample(const uint8_t* p, LONGLONG now, uint32_t fc) {
    float phase = *(const volatile float*)(p + 0x6C);
    int dots = *(const volatile int*)(p + 0x70);
    AcquireSRWLockExclusive(&g_lwLock);
    LoadingWatch& w = g_lw;
    if (!w.lastSeen) {
        w = LoadingWatch{};  // a new screen: nothing to time against yet
        w.startedAt = now;
    } else {
        // any change of the count is one firing of the gate, 7 -> 0 included;
        // the first one only starts the clock
        if (dots != w.dots) {
            if (w.dotAt) {
                w.dotSum += (double)(now - w.dotAt) / (double)g_qpcFreq;
                w.dotTicks += (double)(uint32_t)(fc - w.dotFc);
                w.dotN++;
            }
            w.dotAt = now;
            w.dotFc = fc;
        }
        // the phase only ever goes up, so going down is the wrap: one pulse
        if (phase < w.phase - 1.0f) {
            if (w.wrapAt) {
                w.wrapSum += (double)(now - w.wrapAt) / (double)g_qpcFreq;
                w.wrapN++;
            }
            w.wrapAt = now;
        }
    }
    w.phase = phase;
    w.dots = dots;
    w.lastSeen = now;
    w.updates++;
    ReleaseSRWLockExclusive(&g_lwLock);
}

static void loadingUpdateHook(void* self) {
    g_loadingUpdateOrig(self);
    loadingSample((const uint8_t*)self, qpc(),
                  g_eng.frameCounter ? *(volatile uint32_t*)g_eng.frameCounter : 0);
}

static void installLoadingWatch() {
    uint8_t* main = g_eng.main;
    if (!main) {
        return;
    }
    uint64_t* slot = (uint64_t*)(main + kLoadingVtableSlotRva);
    if (*slot != (uint64_t)(main + kLoadingUpdateRva)) {
        logf("loading watch: vtable slot main+%X does not hold main+%X in this build, not "
             "installed", kLoadingVtableSlotRva, kLoadingUpdateRva);
        return;
    }
    g_loadingUpdateOrig = (LoadingUpdateFn)(main + kLoadingUpdateRva);
    // one aligned 8-byte store: a thread reading the slot sees the old or the new
    // pointer, both of which run the update
    uint64_t hook = (uint64_t)&loadingUpdateHook;
    if (!writeProtected(slot, &hook, sizeof(hook))) {
        logf("loading watch: the vtable slot could not be written, not installed");
        return;
    }
    logf("loading watch: cCockLoading's update wrapped at vtable main+%X (stock: a dot every "
         "%.3f s, a sign pulse every %.3f s)", kLoadingVtableSlotRva, kStockDotSecs,
         kStockSignSecs);
}

// "0.33 s (stock 0.33) OK", or how far off, from a sum of n intervals
static void loadingRate(char* out, size_t n, double sum, int count, double stock) {
    if (count <= 0) {
        snprintf(out, n, "-- (stock %.2f)", stock);
        return;
    }
    double mean = sum / count;
    double r = stock / mean;  // > 1: faster than stock
    if (r > 1.1) {
        snprintf(out, n, "%.2f s (stock %.2f) %.1fx FAST", mean, stock, r);
    } else if (r < 0.9) {
        snprintf(out, n, "%.2f s (stock %.2f) %.1fx SLOW", mean, stock, 1.0 / r);
    } else {
        snprintf(out, n, "%.2f s (stock %.2f) OK", mean, stock);
    }
}

// The overlay's second line while a screen is up; false when none is.
static bool loadingOverlayLine(char* out, size_t n) {
    if (!g_loadingUpdateOrig) {
        return false;
    }
    AcquireSRWLockShared(&g_lwLock);
    LoadingWatch w = g_lw;
    ReleaseSRWLockShared(&g_lwLock);
    if (!w.lastSeen || qpc() - w.lastSeen > g_qpcFreq / 2) {
        return false;
    }
    char dot[64], sign[64];
    loadingRate(dot, sizeof(dot), w.dotSum, w.dotN, kStockDotSecs);
    loadingRate(sign, sizeof(sign), w.wrapSum, w.wrapN, kStockSignSecs);
    snprintf(out, n, "LOADING  dot every %s | sign pulse %s", dot, sign);
    return true;
}

static void appendLoadingLine(char* line, size_t n) {
    char second[200];
    // a loading screen while one is up, otherwise the integer family's check
    if (loadingOverlayLine(second, sizeof(second)) ||
        menuOverlayLine(second, sizeof(second)) ||
        (!g_cfg.passthrough && integerOverlayLine(second, sizeof(second)))) {
        size_t u = strlen(line);
        snprintf(line + u, n - u, "\n%s", second);
    }
    // then the day/night clock's time and rate
    if (!g_cfg.passthrough && dayOverlayLine(second, sizeof(second))) {
        size_t u = strlen(line);
        snprintf(line + u, n - u, "\n%s", second);
    }
}

// From the watcher loop: once a screen has been gone for half a second, log
// what it measured and start over.
static void pollLoadingWatch(LONGLONG now) {
    if (!g_loadingUpdateOrig) {
        return;
    }
    AcquireSRWLockExclusive(&g_lwLock);
    LoadingWatch w = g_lw;
    bool ended = w.lastSeen && now - w.lastSeen > g_qpcFreq / 2;
    if (ended) {
        g_lw.lastSeen = 0;
    }
    ReleaseSRWLockExclusive(&g_lwLock);
    if (!ended) {
        return;
    }
    double secs = (double)(w.lastSeen - w.startedAt) / (double)g_qpcFreq;
    char dot[64], sign[64];
    loadingRate(dot, sizeof(dot), w.dotSum, w.dotN, kStockDotSecs);
    loadingRate(sign, sizeof(sign), w.wrapSum, w.wrapN, kStockSignSecs);
    const char* steps = g_cfg.passthrough        ? "none (PASSTHROUGH)"
                        : !g_phasePool.patched   ? "not installed"
                        : g_phaseFixMuted        ? "MUTED"
                                                 : "on";
    logf("loading screen: %.1f s, %u updates (%.1f/s) | dot every %s over %d, %.1f ticks "
         "each | sign pulse %s over %d | fps=%d clocks=/%u steps=%s",
         secs, w.updates, secs > 0 ? w.updates / secs : 0.0, dot, w.dotN,
         w.dotN ? w.dotTicks / w.dotN : 0.0, sign, w.wrapN,
         g_fps60 ? (g_fpsImmsFast ? 120 : 60) : 30,
         g_fcHooked && g_fcs.sN ? (unsigned)g_fcs.sN : 1u, steps);
}

// Offline self-test, driven by tools/verify_loading_watch.py without the game.
// Installs the watch on a mapped main.dll (the slot check and the write), then
// plays loadingSample a loading screen on a synthetic clock: the sign stepped
// and wrapped as 400370 does, with the step phase_steps.h leaves it, and the
// dots advanced by 4003D0's `% 10` gate on whatever frame_clocks.h gives its
// read -- the counter itself, or H(10,0) from the real frameClockStep. The
// watch must measure stock in stock and fixed runs and 4x in the unfixed 120.
// report.txt: one line per case, then the poll's reset.
extern "C" __declspec(dllexport) int OkamiLoadingWatchSelfTest(const char* mainPath,
                                                               const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) {
        return 2;
    }
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    g_eng.main = (uint8_t*)m;
    installLoadingWatch();
    uint64_t* slot = m ? (uint64_t*)((uint8_t*)m + kLoadingVtableSlotRva) : nullptr;
    bool installed = slot && *slot == (uint64_t)&loadingUpdateHook &&
                     (uint8_t*)g_loadingUpdateOrig == (uint8_t*)m + kLoadingUpdateRva;
    fprintf(rep, "install %s\n", installed ? "ok" : "FAIL");
    int fails = installed ? 0 : 1;
    int dotSlot = -1;  // the counter the dots' read is given
    for (int i = 0; i < kFcReads; i++) {
        if (kFrameClockReads[i].rva == 0x4003E0) {
            dotSlot = kFrameClockReads[i].slot;
        }
    }
    if (dotSlot < 0) {
        fprintf(rep, "FAIL the dots' read 4003E0 is not in frame_clocks.h\n");
        fclose(rep);
        return 1;
    }
    g_qpcFreq = 10000000;
    struct Case {
        const char* name;
        uint32_t fps, n;  // n: ticks per stock tick
        bool fixed;
    };
    const Case cases[] = {
        {"stock30", 30, 1, false},
        {"unfixed120", 120, 4, false},
        {"fixed120", 120, 4, true},
        {"fixed60", 60, 2, true},
    };
    alignas(16) uint8_t obj[0x400];
    LONGLONG t = 0;
    for (const Case& c : cases) {
        memset(obj, 0, sizeof(obj));
        g_lw = LoadingWatch{};
        g_fcs = FrameClockState{};
        uint32_t slots[kFcSlotCount] = {};
        float phase = 0.0f;
        int dots = 0;
        uint32_t fc = 1000;
        const float step = c.fixed ? 0.3f / (float)c.n : 0.3f;
        for (uint32_t k = 0; k < c.fps * 12; k++) {  // 12 s of screen
            fc++;
            frameClockStep(fc, c.fixed ? c.n : 0u, c.fixed ? c.fps / 60u : 0u,
                           c.fixed ? 60u : c.fps, !c.fixed && c.fps == 30, slots);
            if (slots[dotSlot] % 10 == 0 && ++dots > 7) {
                dots = 0;
            }
            phase += step;
            if (phase > 3.14159265f) {
                phase -= 6.28318531f;
            }
            memcpy(obj + 0x6C, &phase, 4);
            memcpy(obj + 0x70, &dots, 4);
            t = 1 + (LONGLONG)k * g_qpcFreq / c.fps;
            loadingSample(obj, t, fc);
        }
        LoadingWatch w = g_lw;
        double dot = w.dotN ? w.dotSum / w.dotN : 0.0;
        double sign = w.wrapN ? w.wrapSum / w.wrapN : 0.0;
        double speed = c.fixed ? 1.0 : (double)c.n;  // how much faster than stock
        double wantDot = kStockDotSecs / speed, wantSign = kStockSignSecs / speed;
        char vDot[64], vSign[64];
        loadingRate(vDot, sizeof(vDot), w.dotSum, w.dotN, kStockDotSecs);
        loadingRate(vSign, sizeof(vSign), w.wrapSum, w.wrapN, kStockSignSecs);
        const char* verdict = speed > 1.0 ? "4.0x FAST" : "OK";
        bool ok = w.dotN >= 20 && w.wrapN >= 10 && fabs(dot / wantDot - 1.0) < 0.01 &&
                  fabs(sign / wantSign - 1.0) < 0.01 && strstr(vDot, verdict) &&
                  strstr(vSign, verdict);
        fails += !ok;
        fprintf(rep, "%s %s dot=%.4f want=%.4f n=%d [%s] sign=%.4f want=%.4f n=%d [%s]\n",
                ok ? "ok  " : "FAIL", c.name, dot, wantDot, w.dotN, vDot, sign, wantSign,
                w.wrapN, vSign);
    }
    // half a second after the last update the screen counts as closed
    pollLoadingWatch(t + g_qpcFreq / 4);
    bool keptOpen = g_lw.lastSeen != 0;
    pollLoadingWatch(t + g_qpcFreq);
    bool closed = g_lw.lastSeen == 0;
    loadingSample(obj, t + 2 * g_qpcFreq, 0);
    bool fresh = g_lw.updates == 1 && g_lw.dotN == 0 && g_lw.wrapN == 0;
    bool pollOk = keptOpen && closed && fresh;
    fails += !pollOk;
    fprintf(rep, "%s poll: open at 0.25 s %d, closed at 1 s %d, next screen starts clean %d\n",
            pollOk ? "ok  " : "FAIL", keptOpen, closed, fresh);
    fprintf(rep, "%s\n", fails ? "FAIL" : "PASS");
    fclose(rep);
    return fails ? 1 : 0;
}

// What the ini asks for that did not go in: for the log, and for a red first
// line on the overlay (g_installProblems). On 2026-09-25 a whole session was
// played with seven families missing (no room for their caves), said only in
// the log and past the right edge of the overlay's one line.
static void noteInstallProblems() {
    char out[sizeof(g_installProblems)] = "";
    size_t u = 0;
    int n = 0;
    auto add = [&](bool missing, const char* name) {
        if (!missing) {
            return;
        }
        n++;
        if (u < sizeof(out)) {
            u += (size_t)snprintf(out + u, sizeof(out) - u, "%s%s", u ? ", " : "", name);
        }
    };
    auto missingState = [](const char* s) { return strcmp(s, "NOT INSTALLED") == 0; };
    const int timers = (int)(sizeof(kTimerSites) / sizeof(kTimerSites[0]));
    const int memTimers = (int)(sizeof(kMemTimerSites) / sizeof(kMemTimerSites[0]));
    const int leaTimers = (int)(sizeof(kLeaTimerSites) / sizeof(kLeaTimerSites[0]));
    if (!g_cfg.passthrough) {
        add((g_cfg.fixRunSpeed || g_cfg.fixJumpHeight) && !g_speedFixInstalled, "movement");
        add(g_cfg.fixActionTimers && g_timerPatched < timers, "action timers");
        add(g_cfg.fixActionTimers && g_memTimerPatched < memTimers, "memory timers");
        add(g_cfg.fixActionTimers && g_leaTimerPatched < leaTimers, "lea timers");
        add(g_cfg.fixFramePhases && !g_framePhasePatched, "frame phases");
        add(g_cfg.fixFrameClocks && !g_fcHooked, "frame clocks");
        add(g_cfg.fixModeConstants && !g_modeSelectsPatched, "mode constants");
        add(g_cfg.fixModeMultipliers && !g_modeMultPatched, "mode multipliers");
        add(g_cfg.fixPhaseSteps && !g_phasePool.patched, "phase steps");
        add(g_cfg.fixDecay && !g_decayPool.patched, "decay factors");
        add(!g_shadowOk, "shadow mode byte");
        add(g_cfg.fixIntegerSkips && missingState(integerSkipState()), "integers");
        add(g_cfg.fixDayClock && missingState(dayClockState()), "day clock");
        add(g_cfg.fixMenuTransitions && missingState(menuTransitionState()), "menus");
        add(g_cfg.fixWorldAnims && missingState(worldAnimState()), "world anims");
        add(g_cfg.fixTaskWaits && missingState(taskWaitState()), "task waits");
        add(g_cfg.drawDistance > 1 && !g_drawDistanceDone, "draw distance");
    }
    add(g_cfg.enemyWatch && !g_ewOn, "enemy watch");
    add(g_cfg.brushWatch && !g_bwReady, "brush watch");
    snprintf(g_installProblems, sizeof(g_installProblems), "%s", out);
    if (n) {
        logf("NOT INSTALLED (%d): %s -- the lines above say why; the overlay shows this in red",
             n, out);
    } else {
        logf("installs: everything the ini asks for went in");
    }
}

// The overlay's text, after a red NOT INSTALLED line when something is missing.
static void setOverlayWithProblems(const char* line) {
    if (!g_installProblems[0]) {
        setOverlayText(line);
        return;
    }
    char text[sizeof(g_overlayText)];
    snprintf(text, sizeof(text), "!! NOT INSTALLED: %s (see okami_hackfix.log)\n%s",
             g_installProblems, line);
    setOverlayText(text);
}

static void updateOverlay() {
    if (!g_cfg.overlay) {
        return;
    }
    char setBuf[64];
    char line[640];
    if (g_cfg.passthrough) {
        // Nothing below applies: there are no fixes to report the state of, and
        // showing "speed stock | jump stock" would read as a patched build with
        // everything muted, which is the one thing this must not be mistaken for.
        double tps0 = (double)g_liveTicks / 10.0;
#ifdef OKAMI_TRACER
        if (tracerOverlay(line, sizeof(line), tps0)) {
            setOverlayText(line);
            return;
        }
#endif
        size_t n0 = (size_t)snprintf(line, sizeof(line),
                                     "OKAMI PASSTHROUGH -- STOCK GAME, NO PATCHES"
                                     " | %.0f Hz tick", tps0);
        LONG pidx = g_harnessStepIdx;
        if (g_harnessActive && pidx >= 0 && pidx < g_scriptN) {
            snprintf(line + n0, sizeof(line) - n0, "  >>> HARNESS %d/%d %s %.1fs <<<",
                     (int)pidx + 1, g_scriptN, g_script[pidx].label,
                     (double)g_harnessMs / 1000.0);
        } else if (g_harnessOverlay[0]) {
            snprintf(line + n0, sizeof(line) - n0, "  [%s]", g_harnessOverlay);
        }
        appendLoadingLine(line, sizeof(line));
        setOverlayWithProblems(line);
        return;
    }
    const char* mode = g_fps60 ? (g_fpsImmsFast ? "120 fps" : "60 fps") : "30 fps (stock)";
    const char* speedMode = (g_playerScale && *g_playerScale < 0.99f) ? "REAL-TIME" : "stock";
    const char* jumpMode = (g_jumpScale && *g_jumpScale > 1.01f) ? "FIXED" : "stock";
    const char* timerMode = (g_timerMask && *g_timerMask) ? "FIXED" : "stock";
    // the steps' ticks per stock tick, as the clocks show theirs: /4 in play at
    // 120, /2 in the stock 60 Hz menus, /1 at 30 fps -- and at 60 fps in those
    // menus, where the shipped step is the right one
    char phaseBuf[16];
    snprintf(phaseBuf, sizeof(phaseBuf), "/%ld", (long)g_poolN);
    const char* phaseMode = g_phaseFixMuted ? "MUTED" : phaseBuf;
    // everything the timer key gates, and everything the phase key gates
    int timerSites = g_timerPatched + g_memTimerPatched + g_leaTimerPatched +
                     g_inputWindowOk + g_frameGateOk + g_framePhasePatched;
    int stepSites = g_phasePool.patched + g_decayPool.patched;
    double rise = (double)g_lastJumpRise / 10.0;
    if (g_setCount) {
        snprintf(line, sizeof(line),
                 "OKAMI %s | speed %s | jump %s %.1f | timers %s %d | steps %s %d | "
                 "walk %ld/s | set %d/%d: %s",
                 mode, speedMode, jumpMode, rise, timerMode, timerSites,
                 phaseMode, stepSites, (long)g_liveSpeed,
                 g_activeSet, g_setCount,
                 gateSetLabel(g_activeSet, setBuf, sizeof(setBuf)));
    } else {
        snprintf(line, sizeof(line),
                 "OKAMI %s | speed %s | jump %s %.1f | timers %s %d | steps %s %d | walk %ld/s",
                 mode, speedMode, jumpMode, rise, timerMode, timerSites,
                 phaseMode, stepSites, (long)g_liveSpeed);
    }
    // The achieved rate, because a run taken while the game was not keeping up
    // is not a measurement of the mode it was nominally in, and nothing else on
    // screen would have said so.
    {
        double tps = (double)g_liveTicks / 10.0;
        double pps = (double)g_livePresents / 10.0;
        int want = g_fps60 ? (g_fpsImmsFast ? 120 : 60) : 30;
        bool low = tps > 1.0 && tps < want * 0.92;
        size_t u0 = strlen(line);
        // the present hook is only installed in 60/120 mode, so pps is a real
        // zero at 30 fps rather than a stalled renderer -- say nothing instead
        if (pps > 0.5) {
            snprintf(line + u0, sizeof(line) - u0, " | %.0f Hz tick, %.0f present%s", tps, pps,
                     low ? " *** BELOW TARGET ***" : "");
        } else {
            snprintf(line + u0, sizeof(line) - u0, " | %.0f Hz tick%s", tps,
                     low ? " *** BELOW TARGET ***" : "");
        }
    }
    // The context the stock game would be in here, from the shadow mode byte:
    // what the animation slowdown has to follow (4x at 120 in gameplay, 2x in
    // the 60 Hz menus).
    if (g_shadowOn) {
        uint8_t sm = *g_shadowMode;
        size_t u1 = strlen(line);
        if (sm == 1 || sm == 2) {
            snprintf(line + u1, sizeof(line) - u1, " | stock %d Hz", sm == 1 ? 60 : 30);
        } else {
            snprintf(line + u1, sizeof(line) - u1, " | stock mode %u", (unsigned)sm);
        }
    }
    // the frame-counter clocks: their ticks per stock tick (1 = stock, as in
    // 30 fps mode or muted), or that the hook is missing
    if (g_cfg.fixFrameClocks && !g_cfg.passthrough) {
        size_t u2 = strlen(line);
        if (g_fcHooked) {
            snprintf(line + u2, sizeof(line) - u2, " | clocks /%u",
                     g_fcs.sN ? (unsigned)g_fcs.sN : 1u);
        } else {
            snprintf(line + u2, sizeof(line) - u2, " | CLOCKS NOT INSTALLED");
        }
    }
    if (g_cfg.fixMenuTransitions && !g_cfg.passthrough) {
        size_t u = strlen(line);
        snprintf(line + u, sizeof(line) - u, " | menus %s /%ld", menuTransitionState(),
                 (long)g_mtN);
    }
    if (g_cfg.fixWorldAnims && !g_cfg.passthrough) {
        size_t u = strlen(line);
        worldStatusTail(line + u, sizeof(line) - u);
    }
    if (g_cfg.fixIntegerSkips && !g_cfg.passthrough) {
        size_t u = strlen(line);
        snprintf(line + u, sizeof(line) - u, " | integers %s /%u", integerSkipState(),
                 g_isPool ? (unsigned)g_isPool[kIntegerSkipMaskOffset] + 1u : 1u);
    }
    // A play-tester may have the sound off, so a beep is not a signal: the
    // harness has to say what it is doing on screen or it says nothing.
    LONG idx = g_harnessStepIdx;
    size_t used = strlen(line);
    if (g_harnessActive && idx >= 0 && idx < g_scriptN) {
        snprintf(line + used, sizeof(line) - used, "  >>> HARNESS %d/%d %s %.1fs <<<",
                 (int)idx + 1, g_scriptN, g_script[idx].label,
                 (double)g_harnessMs / 1000.0);
    } else if (g_harnessOverlay[0]) {
        snprintf(line + used, sizeof(line) - used, "  [%s]", g_harnessOverlay);
    }
    appendLoadingLine(line, sizeof(line));
    setOverlayWithProblems(line);
}

#ifdef OKAMI_TRACER
#include "tracer_runtime.h"
#endif

// The overlay's window; it also carries the notices when the overlay is off.
static void startOverlayWindow() {
    HANDLE ot = CreateThread(nullptr, 0, overlayThread, nullptr, 0, nullptr);
    if (ot) {
        CloseHandle(ot);
    }
}

// The patch gave up before changing anything. The game then looks fine and
// just runs at 30, so the player is told on screen as well as in the log.
static void noticeGameUntouched(const char* why) {
    char note[200];
    snprintf(note, sizeof(note), "Okami HD high-FPS patch: %s, the game runs as shipped", why);
    showNotice(note, 12000, true, true);
    if (g_cfg.overlay) {
        setOverlayText(note);
    }
    startOverlayWindow();
}

// ---------------------------------------------------------------------------
// Watcher thread
// ---------------------------------------------------------------------------

static DWORD WINAPI watcherThread(LPVOID) {
    // wait for both engine DLLs to be loaded (up to 2 minutes)
    bool loaded = false;
    for (int i = 0; i < 2400 && !loaded; i++) {
        loaded = GetModuleHandleA("flower_kernel.dll") && GetModuleHandleA("main.dll");
        if (!loaded) {
            Sleep(50);
        }
    }
    if (!loaded) {
        logf("FATAL: engine DLLs not loaded; patch inactive");
        noticeGameUntouched("the game's engine did not load");
        return 0;
    }
    {
        const uint8_t* m = (const uint8_t*)GetModuleHandleA("main.dll");
        nearPrime(m, nearImageSpan(m), "by the watcher, after main.dll loaded");
        unprimeNearPool();
        nearLogPool("main.dll loaded");
    }
    if (!resolveEngine()) {
        logf("FATAL: engine layout verification failed; game left untouched (stock 30 fps)");
        noticeGameUntouched("game version not recognised");
        return 0;
    }
    initTiming();
    logDisplayInfo();
    // Wraps the enemies' updates and changes nothing, in Passthrough too. First,
    // because its evidence is stock code the action timers rewrite (main+238B5B,
    // the +0xE76 timer): after them it never started in the game.
    installEnemyWatch();
    if (g_cfg.passthrough) {
        logf("PASSTHROUGH: no patches installed. The game runs exactly as shipped;"
             " only the harness and the overlay are active.");
        logf("PASSTHROUGH: use this to record the control run that every other"
             " measurement is compared against.");
        logf("PASSTHROUGH: F9 and the A/B keys are inert -- there is nothing installed"
             " for them to toggle, so they log nothing rather than implying they did.");
    } else {
        installTaskGate();
        installSlotGates();
        checkFpsImms();
        installSpeedFix();
        installActionTimers();
        installMemoryTimers();
        installLeaTimers();
        checkInputWindows();
        checkFrameGates();
        installFramePhases();
        installFrameClocks();
        installModeConstants();
        installModeMultipliers();
        installConstPools();
        // last, so its byte check sees what the others left; applyFpsMode
        // switches it on below
        installShadowMode();
        installIntegerSkips();
        installDayClock();
        installMenuTransitions();
        installWorldAnims();
        installTaskWaits();
        installDrawDistance();
    }
    installHarnessHook();
    installLoadingWatch();
    installBrushWatch();  // reads only: in Passthrough too, for the stock baseline
#ifdef OKAMI_TRACER
    tracerInstall();
#endif
    nearLogPool("after the installs");
    noteInstallProblems();
    startOverlayWindow();

    g_fps60 = (!g_cfg.passthrough && g_cfg.defaultFps != 30) ? 1 : 0;
    // Fps120=1 with DefaultFps=60 is the development-era way to start at 120
    g_fast120 = (g_cfg.defaultFps == 120 || (g_cfg.fps120 && g_cfg.defaultFps == 60)) ? 1 : 0;
    if (g_cfg.passthrough) {
        logf("PASSTHROUGH: stock 30 fps, nothing pinned");
    } else if (g_fps60) {
        setConfigRefleshRate(60.0f);
        applyFpsMode(false);
        logf("60 fps mode active (PS2 display mode off, mode byte pinned to 1)");
    } else {
        logf("starting in stock 30 fps mode (DefaultFps=30)");
    }
    // the player sees the patch loaded, at which rate, or that part of it did
    // not go in (an unknown game version shows as the latter)
    if (g_installProblems[0]) {
        showNotice("Okami HD high-FPS patch: some fixes did not go in (see okami_hackfix.log)",
                   12000, true, true);
    } else if (!g_cfg.passthrough) {
        char note[160];
        int rate = !g_fps60 ? 30 : (g_fast120 && g_fpsImmsOk) ? 120 : 60;
        snprintf(note, sizeof(note), "Okami HD high-FPS patch: %d fps (%s: 30 / 60 / 120)", rate,
                 g_cfg.toggleVk ? g_cfg.toggleName : "no key");
        showNotice(note, 5000, false, true);
    }
#ifdef OKAMI_TRACE
    installTickTrace();
    // NOTE: the body-state dispatcher hook (0x1C2880) is disabled: it hangs
    // the save loading screen. Only the motion-channel hook is safe there.
    installMotionTrace();
#endif
#ifdef OKAMI_DIAG
    installDiag();
#endif

    if (g_cfg.toggleVk) {
        logf("press %s to cycle 30 / 60 / 120 fps%s", g_cfg.toggleName,
             g_cfg.requireFocus ? " (game window must be focused)" : "");
    } else {
        logf("hotkey toggle disabled");
    }
    if (g_cfg.speedToggleVk) {
        logf("press %s to A/B the movement fixes", g_cfg.speedToggleName);
    }
    if (g_cfg.jumpToggleVk && g_cfg.fixJumpHeight) {
        logf("press %s to A/B the jump height fix", g_cfg.jumpToggleName);
    }
    if (g_cfg.timerToggleVk && g_cfg.fixActionTimers) {
        logf("press %s to A/B the action timer fix", g_cfg.timerToggleName);
    }
    if (g_cfg.phaseToggleVk && g_cfg.fixPhaseSteps) {
        logf("press %s to A/B the phase step fix", g_cfg.phaseToggleName);
    }

    uint32_t lastCounter = g_eng.frameCounter ? *g_eng.frameCounter : 0;
    LONG lastPresents = g_presentCount;
    LONGLONG lastStatus = qpc();
    float lastPos[3] = {0, 0, 0};
    bool havePos = false;
    double pathLen = 0.0;      // horizontal path length since the last status line
    double maxStep = 0.0;      // largest 100 ms horizontal displacement
    double lastStep = 0.0;     // most recent 100 ms horizontal displacement
    uint8_t lastState[2] = {0, 0};
    uint8_t peakState = 0;     // player state byte at the peak
    int sampleTick = 0;
    bool harnessKeyWasDown = false;
    double speedRing[10] = {0};   // 10 samples of 100 ms = the last second
    int speedIdx = 0;
    bool keyWasDown = false;
    bool markKeyWasDown = false;
    bool setKeyWasDown = false;
    bool speedKeyWasDown = false;
    bool jumpKeyWasDown = false;
    bool timerKeyWasDown = false;
    bool phaseKeyWasDown = false;
    bool integerKeyWasDown = false;
    LONGLONG lastMark = qpc();
    int markCount = 0;
    bool fixKeyWasDown = false;
    int lastFixStateMode = -1;  // 0 = 30, 1 = 60, 2 = 120; -1 forces a first dump
    for (;;) {
        // 100 Hz: fine enough for the jump tracker to land near the apex; the
        // speed readout below still averages over its own 100 ms grid
        Sleep(10);
        // hotkey (edge-triggered on the physical key state)
        if (g_cfg.toggleVk) {
            bool down = (GetAsyncKeyState((int)g_cfg.toggleVk) & 0x8000) != 0;
            if (down && !keyWasDown && (!g_cfg.requireFocus || gameHasFocus()) &&
                g_cfg.passthrough) {
                logf("F9 ignored: Passthrough=1, there is nothing patched to toggle");
            } else if (down && !keyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                // 30 -> 60 -> 120 -> 30; 120 only where the game's immediates
                // are the ones checkFpsImms knows (else 60 -> 30)
                int rung = !g_fps60 ? 30 : (g_fast120 && g_fpsImmsOk) ? 120 : 60;
                int next = rung == 30 ? 60 : (rung == 60 && g_fpsImmsOk) ? 120 : 30;
                InterlockedExchange(&g_fast120, next == 120 ? 1 : 0);
                if ((next != 30) != (g_fps60 != 0)) {
                    InterlockedExchange(&g_fps60, next != 30 ? 1 : 0);
                    applyFpsMode(true);
                }
                // the ladder follows g_fast120 below, in this same pass
                char note[96];
                snprintf(note, sizeof(note), "Okami HD: %d fps%s", next,
                         next == 30 ? " (the game as shipped)" : "");
                showNotice(note, 2500);
                // remembered for the next launch, in okami_hackfix.ini only:
                // a development-era okami.ini keeps the start rate it names
                if (!g_cfg.iniLegacy && g_cfg.iniPath[0]) {
                    char v[8];
                    snprintf(v, sizeof(v), "%d", next);
                    if (!WritePrivateProfileStringA("Main", "DefaultFps", v, g_cfg.iniPath)) {
                        logf("F9: could not save DefaultFps=%s to %s (%lu)", v, g_cfg.iniPath,
                             GetLastError());
                    }
                }
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            keyWasDown = down;
        }
        if (g_cfg.fixToggleVk && !g_cfg.passthrough) {
            bool down = (GetAsyncKeyState((int)g_cfg.fixToggleVk) & 0x8000) != 0;
            if (down && !fixKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                g_cfg.fixes = !g_cfg.fixes;
                InterlockedExchange(&g_fixesActive, (g_fps60 && g_cfg.fixes) ? 1 : 0);
                logf("fixes -> %s", g_cfg.fixes ? "on" : "off");
                updateOverlay();
                if (g_cfg.beep) {
                    MessageBeep(MB_ICONASTERISK);
                }
            }
            fixKeyWasDown = down;
        }
        if (g_cfg.setVk && g_setCount) {
            bool down = (GetAsyncKeyState((int)g_cfg.setVk) & 0x8000) != 0;
            if (down && !setKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                selectGateSet((g_activeSet + 1) % (g_setCount + 1));
                updateOverlay();
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            setKeyWasDown = down;
        }
        if (g_cfg.speedToggleVk && !g_cfg.passthrough) {
            bool down = (GetAsyncKeyState((int)g_cfg.speedToggleVk) & 0x8000) != 0;
            if (down && !speedKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                LONG muted = InterlockedExchange(&g_speedFixMuted, g_speedFixMuted ? 0 : 1);
                logf("movement fixes -> %s", muted ? "on" : "off");
                updateSpeedFix();
                updateModeConstants();
                logFixState("movement key");
                updateOverlay();
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            speedKeyWasDown = down;
        }
        if (g_cfg.jumpToggleVk && g_cfg.fixJumpHeight && !g_cfg.passthrough) {
            bool down = (GetAsyncKeyState((int)g_cfg.jumpToggleVk) & 0x8000) != 0;
            if (down && !jumpKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                LONG muted = InterlockedExchange(&g_jumpFixMuted, g_jumpFixMuted ? 0 : 1);
                logf("jump height fix -> %s", muted ? "on" : "off");
                updateSpeedFix();
                logFixState("jump key");
                updateOverlay();
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            jumpKeyWasDown = down;
        }
        if (g_cfg.timerToggleVk && g_cfg.fixActionTimers && !g_cfg.passthrough) {
            bool down = (GetAsyncKeyState((int)g_cfg.timerToggleVk) & 0x8000) != 0;
            if (down && !timerKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                InterlockedExchange(&g_timerFixMuted, g_timerFixMuted ? 0 : 1);
                logf("action timer fix -> %s", g_timerFixMuted ? "off" : "on");
                updateActionTimers();
                updateModeMultipliers();
                updateInputWindows();
                updateFrameGates();
                updateFrameClockGates();
                updateSlowFrame();
                updateDayClock();
                logFixState("timer key");
                updateOverlay();
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            timerKeyWasDown = down;
        }
        if (g_cfg.phaseToggleVk && g_cfg.fixPhaseSteps && !g_cfg.passthrough) {
            bool down = (GetAsyncKeyState((int)g_cfg.phaseToggleVk) & 0x8000) != 0;
            if (down && !phaseKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                InterlockedExchange(&g_phaseFixMuted, g_phaseFixMuted ? 0 : 1);
                logf("phase steps and decay -> %s", g_phaseFixMuted ? "stock" : "real time");
                updateConstPools();
                logFixState("phase key");
                updateOverlay();
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            phaseKeyWasDown = down;
        }
        if (g_cfg.integerToggleVk && g_cfg.fixIntegerSkips && !g_cfg.passthrough) {
            bool down = (GetAsyncKeyState((int)g_cfg.integerToggleVk) & 0x8000) != 0;
            if (down && !integerKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                InterlockedExchange(&g_integerFixMuted, g_integerFixMuted ? 0 : 1);
                updateIntegerSkips();
                logFixState("integer key");
                updateOverlay();
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            integerKeyWasDown = down;
        }
        if (g_cfg.harnessVk) {
            bool down = (GetAsyncKeyState((int)g_cfg.harnessVk) & 0x8000) != 0;
            if (down && !harnessKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                harnessStart();
                if (g_cfg.beep) {
                    MessageBeep(MB_OK);
                }
            }
            harnessKeyWasDown = down;
        }
        // Watchdog. A run is ended by the tick callback, so anything that stops
        // the player's state dispatcher from being called -- a menu, a cutscene,
        // a load -- leaves the run active forever with the overlay stuck mid
        // script. Give it the script's length plus three seconds and then bin it.
        if (g_harnessActive && g_harnessStart) {
            double aliveMs = (double)(qpc() - g_harnessStart) * 1000.0 / (double)g_qpcFreq;
            if (aliveMs > (double)g_scriptTotalMs + 3000.0) {
                logf("harness: run did not finish within %.0f ms of its %u ms script --"
                     " the player update stopped being called (menu, cutscene or load)."
                     " Discarded.", aliveMs, g_scriptTotalMs);
                InterlockedExchange(&g_harnessAbort, 1);
                InterlockedExchange(&g_harnessActive, 0);
                InterlockedExchange(&g_harnessDone, 1);
                harnessReleasePad();
            }
        }
        if (InterlockedExchange(&g_harnessDone, 0)) {
            harnessReport();
            if (g_cfg.beep) {
                MessageBeep(MB_ICONASTERISK);
            }
        }
        if (g_cfg.markVk) {
            bool down = (GetAsyncKeyState((int)g_cfg.markVk) & 0x8000) != 0;
            if (down && !markKeyWasDown && (!g_cfg.requireFocus || gameHasFocus())) {
                LONGLONG now = qpc();
                double secs = (double)(now - lastMark) / (double)g_qpcFreq;
                lastMark = now;
                markCount++;
                logf("==== MARK %d (%.1f s since the previous mark) ====", markCount, secs);
                logGateStats(secs > 0.001 ? secs : 1.0);
                if (g_cfg.beep) {
                    MessageBeep(MB_ICONEXCLAMATION);
                }
            }
            markKeyWasDown = down;
        }
#ifdef OKAMI_TRACER
        tracerPoll();
#endif
        if (g_fps60) {
            // keep mode=1 (60 fps engine config) and the present hook alive
            *(volatile uint8_t*)g_eng.modeByte = 1;
            installPresentHook();
            checkPresentHookAlive();
        }
        // the shadow mode stub at the memset's return point ran: the engine
        // start cleared its frame block after the install
        if (g_shCave && ((volatile uint8_t*)g_shCave)[1]) {
            ((volatile uint8_t*)g_shCave)[1] = 0;
            logf("shadow mode: frame block cleared (engine start after the install); the memset"
                 " stub ran, real mode=%u shadow=%u",
                 (unsigned)*(volatile uint8_t*)g_eng.modeByte, (unsigned)*g_shadowMode);
        }
        // 30 fps mode is left entirely to the game: its own writers (restored
        // to 2) and menu code (which uses 1) manage the byte as in stock
        // player sampling: every pass for the jump tracker, every tenth for
        // the 10 Hz speed readout
        float pos[3];
        uint8_t st[2];
        bool havePlayer = playerPos(pos, st);
        if (havePlayer) {
            trackWindup(g_plWindup, g_plLaunch);
            trackJump(pos[1], g_plVel[3], st);
        }
        if (++sampleTick >= 10) {
            sampleTick = 0;
            if (havePlayer) {
                if (havePos) {
                    double dx = pos[0] - lastPos[0], dz = pos[2] - lastPos[2];
                    double d = sqrt(dx * dx + dz * dz);
                    lastStep = d;
                    if (d < 300.0) {  // ignore warps
                        pathLen += d;
                        if (d > maxStep) {
                            maxStep = d;
                            peakState = st[1];
                        }
                    }
                }
                lastPos[0] = pos[0];
                lastPos[1] = pos[1];
                lastPos[2] = pos[2];
                lastState[0] = st[0];
                lastState[1] = st[1];
                havePos = true;
            } else {
                havePos = false;
            }
            // rolling 1 s speed for the overlay
            {
                double step = 0.0;
                if (havePos && lastStep < 300.0) {
                    step = lastStep;
                }
                speedRing[speedIdx] = step;
                speedIdx = (speedIdx + 1) % 10;
                double sum = 0.0;
                for (int i = 0; i < 10; i++) {
                    sum += speedRing[i];
                }
                InterlockedExchange(&g_liveSpeed, (LONG)sum);
                // per-sample trace for comparing movement speeds between modes
                if (g_cfg.speedLog && step > 0.5) {
                    logf("spd %6.1f/s st=%02X/%02X sub=%u chg=%u anim=%.3f fps=%d fix=%d vel=%.3f",
                         step * 10.0, lastState[0], lastState[1], (unsigned)g_plSub,
                         (unsigned)g_plCharge, (double)g_plAnimRate, g_fps60 ? 60 : 30,
                         (g_playerScale && *g_playerScale < 0.99f) ? 1 : 0, (double)g_plVel[0]);
                }
            }
        }
        applyFpsLadder(g_fast120 && g_fps60 != 0);
        updateIntegerSkips();
        updateDayClock();
        updateSpeedFix();
        updateModeConstants();
        updateModeMultipliers();
        updateActionTimers();
        updateInputWindows();
        updateFrameGates();
        updateFrameClockGates();
        updateSlowFrame();
        updateConstPools();
        // after every mode change, once all of the above have settled, say what
        // is actually armed -- a log that shows a toggle but not its outcome is
        // how a muted fix survived a whole session unnoticed
        {
            int modeNow = (g_fps60 ? (g_fpsImmsFast ? 2 : 1) : 0);
            if (modeNow != lastFixStateMode) {
                lastFixStateMode = modeNow;
                logFixState("fps mode");
            }
        }
        // rolling tick/present rate for the overlay, about once a second
        {
            static LONGLONG rateAt = 0;
            static uint32_t rateCounter = 0;
            static LONG ratePresents = 0;
            LONGLONG nowR = qpc();
            uint32_t cNow = g_eng.frameCounter ? *g_eng.frameCounter : 0;
            if (rateAt == 0) {
                rateAt = nowR;
                rateCounter = cNow;
                ratePresents = g_presentCount;
            } else if (nowR - rateAt >= g_qpcFreq) {
                double secs = (double)(nowR - rateAt) / (double)g_qpcFreq;
                LONG pr = g_presentCount;
                InterlockedExchange(
                    &g_liveTicks, (LONG)((double)(uint32_t)(cNow - rateCounter) / secs * 10.0));
                InterlockedExchange(
                    &g_livePresents, (LONG)((double)(pr - ratePresents) / secs * 10.0));
                rateAt = nowR;
                rateCounter = cNow;
                ratePresents = pr;
            }
        }
        pollLoadingWatch(qpc());
        pollBrushWatch(qpc());
        pollEnemyWatch(qpc());
        pollMenuTransitions(qpc());
        updateOverlay();
        if (g_cfg.statusInterval > 0) {
            LONGLONG now = qpc();
            if (now - lastStatus >= g_cfg.statusInterval * g_qpcFreq) {
                double secs = (double)(now - lastStatus) / (double)g_qpcFreq;
                measureIntegerSkips(now);
                measureDayClock(now);
                measureWorldAnims(now);
                measureTaskWaits(now);
                uint32_t c = g_eng.frameCounter ? *g_eng.frameCounter : 0;
                LONG p = g_presentCount;
                // player position and horizontal speed, so a walk test in each
                // mode measures game speed objectively
                char posInfo[192] = "";
                // anything muted by an A/B key is named here, so a status line
                // on its own is enough to know whether a measurement is valid
                char mutedInfo[64] = "";
                {
                    size_t mn = 0;
                    const struct { volatile LONG* f; const char* n; } kMutes[] = {
                        {&g_speedFixMuted, "movement"}, {&g_jumpFixMuted, "jump"},
                        {&g_timerFixMuted, "timers"},   {&g_phaseFixMuted, "phase"},
                    };
                    for (auto& mu : kMutes) {
                        if (*mu.f) {
                            mn += (size_t)snprintf(mutedInfo + mn, sizeof(mutedInfo) - mn,
                                                   "%s%s", mn ? "," : " MUTED=", mu.n);
                        }
                    }
                }
                // pos/st are the sample taken at the top of this pass
                if (havePlayer) {
                    snprintf(posInfo, sizeof(posInfo),
                             " player=(%.0f %.0f %.0f) path=%.1f/s peak=%.1f/s@%02X st=%02X/%02X fixes=%s%s",
                             (double)pos[0], (double)pos[1], (double)pos[2], pathLen / secs,
                             maxStep * 10.0, peakState, st[0], st[1],
                             g_fixesActive ? "on" : "off", mutedInfo);
                }
                char setInfo[32] = "";
                if (g_setCount) {
                    snprintf(setInfo, sizeof(setInfo), " set=%d/%d", g_activeSet, g_setCount);
                }
                pathLen = 0.0;
                maxStep = 0.0;
                char watchInfo[200] = "";
                if (g_cfg.watchBytes[0]) {
                    size_t wn = 0;
                    const char* wp = g_cfg.watchBytes;
                    while (*wp && wn + 16 < sizeof(watchInfo)) {
                        while (*wp == ' ' || *wp == ',') {
                            wp++;
                        }
                        if (!*wp) {
                            break;
                        }
                        char* endp = nullptr;
                        unsigned long rva = strtoul(wp, &endp, 16);
                        if (endp == wp) {
                            break;
                        }
                        wp = endp;
                        uint8_t* addr = g_eng.main + rva;
                        if (readableRange(addr, 1)) {
                            wn += (size_t)snprintf(watchInfo + wn, sizeof(watchInfo) - wn,
                                                   "%s%lX=%02X", wn ? " " : " watch=", rva,
                                                   *(volatile uint8_t*)addr);
                        }
                    }
                }
                if (g_fixesActive) {
                    char tk[256] = "";
                    size_t tn = 0;
                    for (int i = 0; i < g_taskClassCount && tn + 40 < sizeof(tk); i++) {
                        if (g_taskClasses[i].skipped) {
                            tn += (size_t)snprintf(tk + tn, sizeof(tk) - tn, " %s:%u/%u",
                                                   g_taskClasses[i].name,
                                                   g_taskClasses[i].skipped,
                                                   g_taskClasses[i].steps);
                            g_taskClasses[i].skipped = 0;
                            g_taskClasses[i].steps = 0;
                        }
                    }
                    if (tk[0]) {
                        logf("half-rate:%s", tk);
                    }
                }
                logGateStats(secs);
                char fp[64];
                fixFingerprint(fp, sizeof(fp));
                // the stock game's mode, while the real byte is pinned, and the
                // ticks per step of the frame counter copies (S, and U for the
                // elapsed windows) with the per-tick hook's calls per second
                // the hook's calls since the previous status line, taken on
                // every line: the line omits them with the patch off (F9), and
                // a count taken only when shown averaged the whole 30 fps
                // stretch into the first rate back (hook=197.0/s at 58.7 ticks/s)
                static LONG lastFcTicks = 0;
                LONG fcTicksNow = g_fcTicks;
                double hookRate = (double)(fcTicksNow - lastFcTicks) / secs;
                lastFcTicks = fcTicksNow;
                char shadowInfo[96] = "";
                if (g_shadowOn) {
                    size_t u = (size_t)snprintf(shadowInfo, sizeof(shadowInfo),
                                                " shadow=%u phaseN=%u stepsN=%ld",
                                                (unsigned)*g_shadowMode,
                                                (unsigned)(g_fcHooked ? g_fcs.sN : g_slowN),
                                                (long)g_poolN);
                    if (g_fcHooked) {
                        snprintf(shadowInfo + u, sizeof(shadowInfo) - u, " clockU=%u hook=%.1f/s",
                                 (unsigned)g_fcs.uN, hookRate);
                    }
                }
                logf("status: %.1f ticks/s, %.1f presents/s (cfg fps=%u tscale=%.3f "
                     "mode=%u%s ps2=%u) %s %s%s%s%s",
                     (double)(c - lastCounter) / secs, (double)(p - lastPresents) / secs,
                     (unsigned)*(volatile uint8_t*)g_eng.fpsByte,
                     g_eng.timeScale ? (double)*(volatile float*)g_eng.timeScale : 0.0,
                     (unsigned)*(volatile uint8_t*)g_eng.modeByte, shadowInfo,
                     (unsigned)g_eng.isPs2Disp(), g_fps60 ? "60fps mode" : "30fps mode",
                     fp, posInfo, setInfo, watchInfo);
                lastCounter = c;
                lastPresents = p;
                lastStatus = now;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// DirectInput8 forwarding
// ---------------------------------------------------------------------------

typedef HRESULT(WINAPI* DirectInput8CreateFn)(HINSTANCE, DWORD, REFIID, LPVOID*,
                                              LPUNKNOWN);
static DirectInput8CreateFn g_realDirectInput8Create = nullptr;
static HMODULE g_realDinput8Module = nullptr;

extern "C" __declspec(dllexport) HRESULT WINAPI DirectInput8Create(
    HINSTANCE hinst, DWORD version, REFIID riidltf, LPVOID* ppvOut,
    LPUNKNOWN punkOuter) {
    if (!g_realDirectInput8Create) {
        return E_FAIL;  // DIERR_GENERIC equivalent; init logged the cause
    }
    return g_realDirectInput8Create(hinst, version, riidltf, ppvOut, punkOuter);
}

// ---------------------------------------------------------------------------
// DllMain
// ---------------------------------------------------------------------------

static void init() {
    LARGE_INTEGER f;
    if (QueryPerformanceFrequency(&f) && f.QuadPart > 0) {
        g_qpcFreq = f.QuadPart;
    }
    g_startTicks = qpc();

    // our own directory (== game folder): config + log live there
    char path[MAX_PATH];
    if (GetModuleFileNameA(g_ourInstance, path, MAX_PATH) == 0) {
        GetModuleFileNameA(nullptr, path, MAX_PATH);
    }
    char* slash = strrchr(path, '\\');
    if (slash) {
        slash[1] = 0;
    } else {
        path[0] = 0;
    }
    strncpy(g_baseDir, path, sizeof(g_baseDir) - 1);

    char logPath[MAX_PATH];
    snprintf(logPath, sizeof(logPath), "%sokami_hackfix.log", g_baseDir);
    // Keep the previous run. A test is usually "that was fine, I changed one
    // thing, now it is not", and the run being compared against is exactly the
    // one that opening this file in "w" would have thrown away.
    {
        char prevPath[MAX_PATH];
        snprintf(prevPath, sizeof(prevPath), "%sokami_hackfix.prev.log", g_baseDir);
        remove(prevPath);
        rename(logPath, prevPath);
    }
    g_log = fopen(logPath, "w");
    if (!g_log) {
        g_log = fopen("okami_hackfix.log", "w");
    }
    // The build stamp ties a log to the binary that produced it. Without it a
    // run started before the DLL was replaced reads exactly like a run started
    // after, which is a silent way to spend an evening testing the old build.
    // The wall clock anchors the relative timestamps to when the game was
    // actually played.
    {
        SYSTEMTIME st;
        GetLocalTime(&st);
        logf("Okami HD high-FPS patch v" OKAMI_HACKFIX_VERSION " starting"
             " (built " __DATE__ " " __TIME__ " %s)"
             " at %04u-%02u-%02u %02u:%02u:%02u local -- t=0.000 is this moment",
#if defined(__clang__)
             "clang",
#elif defined(_MSC_VER)
             "msvc",
#else
             "gcc",
#endif
             st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    }
    // the caves' first chunk, before the game's allocations crowd main.dll
    // (see allocNear)
    primeNearPool();
    if (g_nearChunkCount) {
        nearLogPool("DllMain");
    } else {
        logf("caves: main.dll not mapped yet; %s", g_ldrCookie
                                                       ? "the loader will say when it is"
                                                       : "no loader notification, the watcher "
                                                         "will reserve them");
    }
    loadConfig();
#ifdef OKAMI_TRACER
    {
        // The records must describe the stock game, and only in the stock game
        // does the mode byte say which context (30 or 60 Hz) each tick ran in.
        // So this build is Passthrough whatever the ini says, and the overlay
        // is how the route is followed, so it is always on.
        char ini[MAX_PATH];
        snprintf(ini, sizeof(ini), "%sokami.ini", g_baseDir);
        tracerLoadConfig(ini);
        g_cfg.passthrough = true;
        g_cfg.overlay = true;
        logf("TRACER BUILD: Passthrough and Overlay forced on");
    }
#endif
    AddVectoredExceptionHandler(0, exceptionLogger);  // last in line, log only

    char realPath[MAX_PATH];
    if (g_cfg.proxyDll[0]) {
        if (strchr(g_cfg.proxyDll, ':') || g_cfg.proxyDll[0] == '\\') {
            strncpy(realPath, g_cfg.proxyDll, sizeof(realPath) - 1);
            realPath[sizeof(realPath) - 1] = 0;
        } else {
            snprintf(realPath, sizeof(realPath), "%s%s", g_baseDir, g_cfg.proxyDll);
        }
    } else {
        GetSystemDirectoryA(realPath, MAX_PATH);
        strncat(realPath, "\\dinput8.dll", sizeof(realPath) - strlen(realPath) - 1);
    }
    HMODULE real = LoadLibraryA(realPath);
    if (!real) {
        logf("FATAL: cannot load %s (err %lu)", realPath, (unsigned long)GetLastError());
        return;
    }
    g_realDinput8Module = real;
    g_realDirectInput8Create =
        (DirectInput8CreateFn)GetProcAddress(real, "DirectInput8Create");
    if (!g_realDirectInput8Create) {
        logf("FATAL: DirectInput8Create not found in %s", realPath);
        return;
    }
    logf("forwarding DirectInput8Create to %s", realPath);

    HANDLE h = CreateThread(nullptr, 0, watcherThread, nullptr, 0, nullptr);
    if (h) {
        CloseHandle(h);
    } else {
        logf("FATAL: watcher thread creation failed (err %lu)",
             (unsigned long)GetLastError());
    }
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved) {
    switch (reason) {
        case DLL_PROCESS_ATTACH:
            g_ourInstance = hinst;
            DisableThreadLibraryCalls(hinst);
            init();
            break;
        case DLL_PROCESS_DETACH:
            if (!reserved) {
                unprimeNearPool();  // unloaded early: the loader must not call back into us
            }
#ifdef OKAMI_TRACER
            tracerAtExit();
#endif
            if (g_timePeriodSet) {
                timeEndPeriod(1);
            }
            AcquireSRWLockExclusive(&g_logLock);
            if (g_log) {
                fclose(g_log);
                g_log = nullptr;
            }
            ReleaseSRWLockExclusive(&g_logLock);
            break;
        default:
            break;
    }
    return TRUE;
}
