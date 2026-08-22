// DINPUT8 proxy for Okami HD -- 60 FPS unlock
//
// Loaded as `DINPUT8.dll` next to okami.exe because flower_kernel.dll imports
// DirectInput8Create by name. Forwards that call to the real system
// dinput8.dll and applies a runtime patch set to the game:
//
//   1. Disable the PS2 display mode (IsPs2DispMode -> false). The PC port
//      boots in PS2 presentation mode, which is what locks the engine at
//      30 Hz with its native step configuration.
//   2. Force the engine's 60 fps configuration flag (main.dll .data byte
//      B6AC45 -> 1). Every flower_tick then writes fps=60 and timeScale=0.5,
//      which keeps game-time running at real speed at double the tick rate.
//   3. Hook the swap chain's Present (IDXGISwapChain vtable slot 8): call it
//      without vsync wait and enforce a 16.667 ms game-step grid ourselves.
//      The stock swap chain is created for a 30 Hz video mode, so its own
//      Present(1) blocks 33.3 ms per frame (the 30 fps lock). Patching the
//      present path decouples the step rate from the swap chain's mode.
//
// Numbers in the patches are final for the retail Steam build of main.dll /
// flower_kernel.dll (build 6990973). The patch is applied in memory only;
// no game files are modified.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>  // REFIID, LPUNKNOWN

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>

// ---------------------------------------------------------------------------
// Logging (okami_hackfix.log next to the game)
// ---------------------------------------------------------------------------

static FILE* g_log = nullptr;

static void logf(const char* fmt, ...) {
    if (!g_log) {
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
}

// ---------------------------------------------------------------------------
// Offsets (RVAs) in the retail binaries
// ---------------------------------------------------------------------------

// main.dll
static constexpr uintptr_t kModeByteRva = 0x0B6AC45;  // 1 -> engine 60 fps cfg
static constexpr uintptr_t kSysCfgSingletonRva = 0x152C10;
static constexpr uintptr_t kSysCfgSetRefleshRva = 0x162E40;

// flower_kernel.dll
static constexpr uintptr_t kFkSetPs2DispRva = 0x164F0;   // SetPs2DispMode(bool)
static constexpr uintptr_t kFkSwapChainPtrRva = 0x11C290;  // IDXGISwapChain*

static uint8_t* g_main = nullptr;
static uint8_t* g_fk = nullptr;

// ---------------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------------

static LONGLONG qpcUs() {
    static LARGE_INTEGER freq;
    static volatile LONG initDone = 0;
    if (!initDone) {
        if (!QueryPerformanceFrequency(&freq)) {
            freq.QuadPart = 1;
        }
        InterlockedExchange(&initDone, 1);
    }
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    return now.QuadPart * 1000000LL / freq.QuadPart;
}

// ---------------------------------------------------------------------------
// Present shim + swap chain vtable patch
// ---------------------------------------------------------------------------

static HRESULT(__fastcall* g_origPresent)(void*, UINT, UINT) = nullptr;
static volatile LONG g_presentPatched = 0;

extern "C" HRESULT __fastcall presentShim(void* sc, UINT sync, UINT flags) {
    // present asynchronously (no vblank wait): the swap chain targets a 30 Hz
    // mode, so a synchronous present would block 33.3 ms and re-lock 30 fps
    HRESULT hr = g_origPresent(sc, 0, flags);

    // enforce a 60 Hz game-step clock on the frame thread
    static LONGLONG nextUs = 0;
    LONGLONG now = qpcUs();
    if (nextUs == 0 || now >= nextUs) {
        nextUs = now;
    }
    nextUs += 16667;
    LONGLONG remain = nextUs - qpcUs();
    if (remain > 3000) {
        // keep CPU usage sane: sleep most of the wait, spin the remainder
        Sleep((DWORD)((remain - 2000) / 1000));
    }
    while (qpcUs() < nextUs) {
        // spin to the exact 16.667 ms boundary
    }
    return hr;
}

// Patch the Present slot of the DXGI swap chain vtable. All swap chains of
// the same class share the vtable, so resolution changes / swap chain
// recreates keep the patch active.
static void patchSwapChainPresent() {
    if (g_presentPatched || !g_fk) {
        return;
    }
    uint8_t* sc = *(uint8_t**)(g_fk + kFkSwapChainPtrRva);
    if (!sc || !*(void**)sc) {
        return;  // not created yet; caller retries
    }
    void** vt = *(void***)sc;
    HRESULT(__fastcall* cur)(void*, UINT, UINT) =
        (HRESULT(__fastcall*)(void*, UINT, UINT))vt[8];
    if (!cur || cur == &presentShim) {
        return;
    }
    DWORD old;
    if (!VirtualProtect(&vt[8], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
        logf("warn: present vtable VirtualProtect failed err=%lu",
             (unsigned long)GetLastError());
        return;
    }
    g_origPresent = cur;
    vt[8] = (void*)&presentShim;
    InterlockedExchange(&g_presentPatched, 1);
    logf("present hooked: orig=%p at %p", (void*)g_origPresent, (void*)(vt + 8));
}

// Keep the hook alive across swap chain recreation.
static void checkPresentHookAlive() {
    if (!g_presentPatched || !g_fk) {
        return;
    }
    uint8_t* sc = *(uint8_t**)(g_fk + kFkSwapChainPtrRva);
    if (!sc || !*(void**)sc) {
        return;
    }
    void** vt = *(void***)sc;
    if (vt[8] != (void*)&presentShim) {
        g_origPresent = NULL;
        InterlockedExchange(&g_presentPatched, 0);
        logf("swap chain vtable changed; re-hooking");
        patchSwapChainPresent();
    }
}

// ---------------------------------------------------------------------------
// Engine-side fixes
// ---------------------------------------------------------------------------

static void disablePs2DispMode() {
    typedef void(__fastcall* SetFlagFn)(uint8_t);
    ((SetFlagFn)(g_fk + kFkSetPs2DispRva))(0);
    logf("PS2 display mode disabled");
}

// The engine pairs its frame-window compensation with the framerate mode
// byte (B6AC45): <=1 keeps the 60 Hz semantics of every compensated timer at
// 60 ticks/s (key timers decay 1/tick, keyframe durations double, movement
// speeds switch). The game's own system-state machine rewrites it to 2
// (30 Hz semantics) throughout gameplay, which at our 60 Hz tick rate makes
// every frame-counted window run twice as fast in real time. Pin it to 1 by
// rewriting the `mov byte ptr [mode], 2` immediates in main.dll.
static constexpr uintptr_t kModeWriter2Sites[] = {0x14A051, 0x14A1F6,
                                                  0x14A64C, 0x608F4E};

static void pinModeByteTo1() {
    for (uintptr_t rva : kModeWriter2Sites) {
        uint8_t* p = g_main + rva + 6;  // C6 05 disp32 imm8 -> imm8
        DWORD old;
        if (!VirtualProtect(p, 1, PAGE_EXECUTE_READWRITE, &old)) {
            logf("warn: mode pin VirtualProtect failed at %p", (void*)p);
            continue;
        }
        *p = 1;
    }
    logf("mode byte writers pinned to 1 (%d sites)",
         (int)(sizeof(kModeWriter2Sites) / sizeof(kModeWriter2Sites[0])));
}

static void setConfigRefleshRate(float rate) {
    typedef void* (*GetSingletonFn)();
    typedef void(__fastcall* SetFloatFn)(void*, float);
    void* sysCfg = ((GetSingletonFn)(g_main + kSysCfgSingletonRva))();
    if (sysCfg) {
        ((SetFloatFn)(g_main + kSysCfgSetRefleshRva))(sysCfg, rate);
        logf("config refresh rate set to %.0f", (double)rate);
    }
}

// ---------------------------------------------------------------------------
// Per-frame key-state tracing (OKAMI_TRACE builds only)
// ---------------------------------------------------------------------------

#ifdef OKAMI_TRACE
static constexpr uintptr_t kTickRva = 0x4B63B0;       // flower_tick
static constexpr uintptr_t kKeyTableRva = 0x0B6AD00;  // cKs key object
static constexpr uintptr_t kFrameCounterRva2 = 0x0B6AC20;
static constexpr uintptr_t kFpsByteRva2 = 0x0B6AC44;
static constexpr uintptr_t kModeByteRva2 = 0x0B6AC45;
static constexpr uintptr_t kTimeScaleRva2 = 0x0B6AC38;
static constexpr size_t kKeyDump = 0x1D0;

__attribute__((used)) uint8_t* g_tickTramp = nullptr;
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
    uint8_t mode = *(volatile uint8_t*)(g_main + kModeByteRva2);
    uint8_t fps = *(volatile uint8_t*)(g_main + kFpsByteRva2);
    float ts = *(volatile float*)(g_main + kTimeScaleRva2);
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
__attribute__((used)) uint8_t* g_moveTramp = nullptr;
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
__attribute__((used)) uint8_t* g_chan3Tramp = nullptr;
static uint8_t g_chan3Saved[15];
__attribute__((used)) uint8_t* g_chan4Tramp = nullptr;
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
    back[0] = 0x48;
    back[1] = 0xB8;
    uint64_t retAddr = (uint64_t)(target + 15);
    memcpy(back + 2, &retAddr, 8);
    back[10] = 0xFF;
    back[11] = 0xE0;

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
__attribute__((used)) uint8_t* g_bstTramp = nullptr;
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
    back[0] = 0x48;
    back[1] = 0xB8;
    uint64_t retAddr = (uint64_t)(target + 15);
    memcpy(back + 2, &retAddr, 8);
    back[10] = 0xFF;
    back[11] = 0xE0;

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
__attribute__((used)) uint8_t* g_motTramp = nullptr;
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
    back[0] = 0x48;
    back[1] = 0xB8;
    uint64_t retAddr = (uint64_t)(target + 19);
    memcpy(back + 2, &retAddr, 8);
    back[10] = 0xFF;
    back[11] = 0xE0;

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
__attribute__((used)) uint8_t* g_gcbTramp = nullptr;
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
// 30/60 fps hotkey toggle
// ---------------------------------------------------------------------------

static constexpr UINT kToggleVk = VK_F9;

static volatile LONG g_fps60 = 1;      // 1 = patched 60 fps, 0 = stock 30 fps
static volatile LONG g_lastToggle = 0;

static void setWritersTo(int imm) {
    for (uintptr_t rva : kModeWriter2Sites) {
        uint8_t* p = g_main + rva + 6;
        DWORD old;
        if (VirtualProtect(p, 1, PAGE_EXECUTE_READWRITE, &old)) {
            *p = (uint8_t)imm;
        }
    }
}

static void setPs2Mode(uint8_t v) {
    typedef void(__fastcall* SetFlagFn)(uint8_t);
    ((SetFlagFn)(g_fk + kFkSetPs2DispRva))(v);
}

static void applyFpsMode() {
    if (g_fps60) {
        setWritersTo(1);
        setPs2Mode(0);
        *(volatile uint8_t*)(g_main + kModeByteRva) = 1;
        patchSwapChainPresent();
        logf("toggle -> 60 fps mode (patched)");
    } else {
        setWritersTo(2);
        setPs2Mode(1);
        *(volatile uint8_t*)(g_main + kModeByteRva) = 2;
        if (g_presentPatched) {
            uint8_t* sc = *(uint8_t**)(g_fk + kFkSwapChainPtrRva);
            if (sc && *(void**)sc) {
                void** vt = *(void***)sc;
                DWORD old;
                if (VirtualProtect(&vt[8], sizeof(void*),
                                   PAGE_EXECUTE_READWRITE, &old)) {
                    vt[8] = (void*)g_origPresent;
                }
            }
            InterlockedExchange(&g_presentPatched, 0);
        }
        logf("toggle -> 30 fps mode (stock semantics)");
    }
}

// ---------------------------------------------------------------------------
// Watcher thread
// ---------------------------------------------------------------------------

static DWORD WINAPI watcherThread(LPVOID) {
    // wait for both engine DLLs to be loaded
    for (int i = 0; i < 400; i++) {
        HMODULE fm = GetModuleHandleA("flower_kernel.dll");
        HMODULE mm = GetModuleHandleA("main.dll");
        if (fm && mm) {
            g_fk = (uint8_t*)fm;
            g_main = (uint8_t*)mm;
            break;
        }
        Sleep(50);
    }
    if (!g_fk || !g_main) {
        logf("FATAL: engine DLLs not loaded (fk=%p main=%p)", (void*)g_fk,
             (void*)g_main);
        return 0;
    }
    logf("main.dll=%p flower_kernel.dll=%p", (void*)g_main, (void*)g_fk);

    disablePs2DispMode();
    setConfigRefleshRate(60.0f);
    pinModeByteTo1();
#ifdef OKAMI_TRACE
    installTickTrace();
    // NOTE: the body-state dispatcher hook (0x1C2880) is disabled: it hangs
    // the save loading screen. Only the motion-channel hook is safe there.
    installMotionTrace();
#endif

    // engine counters for status reporting
    static constexpr uintptr_t kFrameCounterRva = 0x0B6AC20;   // per-tick dword
    static constexpr uintptr_t kFpsByteRva = 0x0B6AC44;        // 30/60
    static constexpr uintptr_t kTimeScaleRva = 0x0B6AC38;      // float 1.0/0.5

    uint32_t lastCounter = 0;
    LONGLONG lastUs = 0;
    logf("press F9 to toggle 30/60 fps");
    for (int i = 0; i < 12000; i++) {
        Sleep(50);
        // keyboard hotkey (edge-triggered)
        SHORT ks = GetAsyncKeyState(kToggleVk);
        LONG down = (ks & 1) ? 1 : 0;
        if (down && !g_lastToggle) {
            InterlockedXor(&g_fps60, 1);
            applyFpsMode();
            MessageBeep(0xFFFFFFFF);
        }
        g_lastToggle = down;
        if (g_fps60) {
            // keep mode=1 (60 fps engine config) and the present patch alive
            *(volatile uint8_t*)(g_main + kModeByteRva) = 1;
            patchSwapChainPresent();
            checkPresentHookAlive();
        } else {
            // keep mode=2 (30 fps engine config)
            *(volatile uint8_t*)(g_main + kModeByteRva) = 2;
        }
        if ((i % 50) == 0) {  // every 2.5 s
            uint32_t c = *(volatile uint32_t*)(g_main + kFrameCounterRva);
            LONGLONG now = qpcUs();
            if (lastUs != 0 && now > lastUs) {
                double secs = (double)(now - lastUs) / 1000000.0;
                double fps = (double)(c - lastCounter) / secs;
                logf("status: %.1f fps over %.2fs (cfg fps=%u tscale=%.3f)",
                     fps, secs,
                     (unsigned)*(volatile uint8_t*)(g_main + kFpsByteRva),
                     (double)*(volatile float*)(g_main + kTimeScaleRva));
            }
            lastCounter = c;
            lastUs = now;
        }
    }
    return 0;
}

// ---------------------------------------------------------------------------
// DirectInput8 forwarding
// ---------------------------------------------------------------------------

typedef HRESULT(WINAPI* DirectInput8CreateFn)(HINSTANCE, DWORD, REFIID, LPVOID*,
                                              LPUNKNOWN);
static DirectInput8CreateFn g_realDirectInput8Create = nullptr;
static HMODULE g_realDinput8Module = nullptr;
static HINSTANCE g_ourInstance = nullptr;

extern "C" HRESULT WINAPI DirectInput8Create(HINSTANCE hinst, DWORD version,
                                             REFIID riidltf, LPVOID* ppvOut,
                                             LPUNKNOWN punkOuter) {
    return g_realDirectInput8Create(hinst, version, riidltf, ppvOut, punkOuter);
}

// ---------------------------------------------------------------------------
// DllMain
// ---------------------------------------------------------------------------

static void init() {
    if (g_log) {
        return;
    }
    char path[MAX_PATH];
    GetModuleFileNameA(nullptr, path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) {
        slash[1] = 0;
    }
    strcat(path, "okami_hackfix.log");
    g_log = fopen(path, "w");
    if (!g_log) {
        g_log = fopen("okami_hackfix.log", "w");
    }
    logf("Okami HD 60 FPS hackfix starting");

    char syspath[MAX_PATH];
    GetSystemDirectoryA(syspath, MAX_PATH);
    strcat(syspath, "\\dinput8.dll");
    HMODULE real = LoadLibraryA(syspath);
    if (!real) {
        logf("FATAL: cannot load real %s (err %lu)", syspath,
             (unsigned long)GetLastError());
        return;
    }
    g_realDinput8Module = real;
    g_realDirectInput8Create =
        (DirectInput8CreateFn)GetProcAddress(real, "DirectInput8Create");
    if (!g_realDirectInput8Create) {
        logf("FATAL: DirectInput8Create not found in system dinput8.dll");
        return;
    }

    HANDLE h = CreateThread(nullptr, 0, watcherThread, nullptr, 0, nullptr);
    if (h) {
        CloseHandle(h);
    }
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID) {
    switch (reason) {
        case DLL_PROCESS_ATTACH:
            g_ourInstance = hinst;
            init();
            break;
        case DLL_PROCESS_DETACH:
            if (g_log) {
                fclose(g_log);
                g_log = nullptr;
            }
            break;
        default:
            break;
    }
    return TRUE;
}
