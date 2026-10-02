// Enemy watch:
// what a hit does to an enemy, in numbers the log can compare between 120 fps
// and F9's stock 30. In play, hit enemies "rag doll" at 120 and not at 30,
// and nothing the patch logged could say how: which enemy, how far it flew,
// how high, how long it stayed up, how often it was hit, what states it went
// through.
//
// Every enemy class (enemy_watch.h: each class whose RTTI lists cEm as a
// base) has its update in vtable slot 8. Each slot is pointed at a thunk that
// saves the argument registers (rcx, rdx, r8, r9, xmm0-3), calls
// ewSample(this), restores them and jumps to the update, which then returns
// straight to its caller: the update runs exactly as before, and the sample
// reads an object its caller still holds. The game's code is not written.
//
// A sample is read under the fault guard: hit points, the state bytes, the
// invulnerability, vy, the rotation and the position through +A8. A drop in
// hit points is a hit. The first starts an episode for that enemy, from where
// it stood before it. Until it settles (2 s after the last hit, not falling,
// its state unchanged for half a second; or 6 s after the last hit; or not
// updated for 1.5 s), the watch adds up the ground it covered, its top
// height, the time it spent falling (vy != 0), how far it turned, each state
// it entered, and once per stock tick (every N-th update, N = fps / 30) its
// height and distance from the start. Then it logs two lines:
//
//   enemy: em00 hit 3x in 1.23 s (at 0.00 0.40 0.83 s, damage 10 10 10,
//     invulnerable 10 10 10 ticks) | moved 185 (ends 160 away), top +42,
//     falling 0.93 s, turned 0.20/3.10/0.00 rad | 120 fps, enemy fixes /4 |
//     states 2.0.0 2.3.0@0.07 ...
//   enemy:   em00 per stock tick, height/distance: 0/0 5/8 12/16 ...
//
// The same hit at 120 and at F9's 30 should read the same.
#include "enemy_watch.h"

static const int kEwTracks = 16, kEwMaxHits = 12, kEwMaxStates = 16, kEwMaxSamples = 90;
static const int kEwThunkSize = 96;
static const int kEwThunkSamplerAt = 32, kEwThunkOrigAt = 74;  // the two imm64s

struct EwSnap {
    float x, y, z, r[3], vy;
    int32_t hp;
    uint8_t st[3], iv;
    uint64_t vt;
};
struct EwTrack {
    const uint8_t* obj;
    uint64_t vt;
    int cls;          // kEwClasses index, -1 unknown
    LONGLONG seen;    // time of the last sample, 0 = free
    EwSnap last;
    // the episode, while hits > 0
    int hits;
    LONGLONG start, lastHit, lastChange;
    uint32_t updates;
    float x0, y0, z0;
    double path, top, air, rot[3];
    float hitAt[kEwMaxHits];
    int32_t hitDmg[kEwMaxHits];
    uint8_t hitIv[kEwMaxHits];
    uint8_t st[kEwMaxStates][3];
    float stAt[kEwMaxStates];
    int nSt;
    int16_t h[kEwMaxSamples], d[kEwMaxSamples];
    int nS;
    unsigned n0, actor0;
    bool nChanged, unseen;
};
static EwTrack g_ew[kEwTracks];
static SRWLOCK g_ewLock = SRWLOCK_INIT;
static bool g_ewOn = false;
static uint8_t* g_ewCave = nullptr;
static int g_ewThunks = 0;
// the self-test's clock and N; 0 = the real ones
static LONGLONG g_ewFakeNow = 0;
static unsigned g_ewFakeN = 0;
static bool g_ewBreakSample = false;  // --break sample: one sample per update
// the last episodes finished, for the self-test
static EwTrack g_ewDone[4];
static int g_ewDoneN = 0;

static LONGLONG ewNow() { return g_ewFakeNow ? g_ewFakeNow : qpc(); }

// Updates per stock tick: the game ticks at the frame rate in play.
static unsigned ewTicksPerStock() {
    if (g_ewFakeN) return g_ewFakeN;
    return g_fps60 ? (g_fpsImmsFast ? 4u : 2u) : 1u;
}

static unsigned ewActorN() {
    if (g_ewFakeN) return g_ewFakeN;
    return g_waPool ? (unsigned)g_waN[kWaGroupActor] : 1u;
}

struct EwRead {
    const uint8_t* self;
    EwSnap s;
    bool ok;
};
static void ewReadBody(void* arg) {
    EwRead* r = (EwRead*)arg;
    const uint8_t* o = r->self;
    const float* p = *(float* const*)(o + kEwPosPtr);
    if (!p) return;
    EwSnap& s = r->s;
    s.vt = *(const uint64_t*)o;
    s.x = p[0];
    s.y = p[1];
    s.z = p[2];
    memcpy(s.r, o + kEwRot, 12);
    memcpy(&s.vy, o + kEwVy, 4);
    memcpy(&s.hp, o + kEwHp, 4);
    memcpy(s.st, o + kEwState, 3);
    s.iv = o[kEwInvuln];
    r->ok = true;
}

static float ewWrap(float a) {
    while (a > 3.14159265f) a -= 6.28318531f;
    while (a < -3.14159265f) a += 6.28318531f;
    return a;
}

static void ewLogEpisode(const EwTrack& t) {
    const char* name = t.cls >= 0 ? kEwClasses[t.cls].name : "em??";
    double secs = (double)(t.lastHit - t.start) / (double)g_qpcFreq;
    char hits[160] = "", dmg[120] = "", iv[120] = "", st[400] = "";
    int nh = t.hits < kEwMaxHits ? t.hits : kEwMaxHits;
    for (int i = 0; i < nh; i++) {
        size_t u = strlen(hits), v = strlen(dmg), w = strlen(iv);
        snprintf(hits + u, sizeof(hits) - u, "%s%.2f", i ? " " : "", t.hitAt[i]);
        snprintf(dmg + v, sizeof(dmg) - v, "%s%d", i ? " " : "", (int)t.hitDmg[i]);
        snprintf(iv + w, sizeof(iv) - w, "%s%d", i ? " " : "", (int)t.hitIv[i]);
    }
    for (int i = 0; i < t.nSt; i++) {
        size_t u = strlen(st);
        if (i == 0) {
            snprintf(st + u, sizeof(st) - u, "%d.%d.%d", t.st[i][0], t.st[i][1], t.st[i][2]);
        } else {
            snprintf(st + u, sizeof(st) - u, " %d.%d.%d@%.2f", t.st[i][0], t.st[i][1], t.st[i][2],
                     t.stAt[i]);
        }
    }
    double net = sqrt((double)(t.last.x - t.x0) * (t.last.x - t.x0) +
                      (double)(t.last.z - t.z0) * (t.last.z - t.z0));
    unsigned fps = t.n0 == 4 ? 120 : t.n0 == 2 ? 60 : 30;
    logf("enemy: %s hit %dx in %.2f s (at %s s, damage %s, invulnerable %s ticks) | moved %.0f "
         "(ends %.0f away), top %+.0f, falling %.2f s, turned %.2f/%.2f/%.2f rad | %u fps, enemy "
         "fixes %s%u%s | states %s%s",
         name, t.hits, secs, hits, dmg, iv, t.path, net, t.top, t.air, t.rot[0], t.rot[1],
         t.rot[2], fps, t.actor0 > 1 ? "/" : "off /", t.actor0,
         t.nChanged ? ", fps or fixes changed" : "", st, t.unseen ? " | cut short (not updated)" : "");
    char line[kEwMaxSamples * 12 + 1] = "";
    for (int i = 0; i < t.nS; i++) {
        size_t u = strlen(line);
        snprintf(line + u, sizeof(line) - u, "%s%d/%d", i ? " " : "", t.h[i], t.d[i]);
    }
    logf("enemy:   %s per stock tick, height/distance: %s%s", name, line,
         t.nS == kEwMaxSamples ? " ..." : "");
}

// Finish t's episode: keep a copy for the self-test and hand it back to log.
static void ewFinish(EwTrack& t, EwTrack* out) {
    *out = t;
    g_ewDone[g_ewDoneN % 4] = t;
    g_ewDoneN++;
    t.hits = 0;
}

static int ewClassOf(uint64_t vt) {
    for (int i = 0; i < kEwClassCount; i++) {
        if (vt == (uint64_t)(g_eng.main + kEwClasses[i].vtable)) return i;
    }
    return -1;
}

// One sample of an enemy, under the lock; true when an episode finished.
static bool ewRecord(const uint8_t* obj, const EwSnap& s, LONGLONG now, EwTrack* done) {
    const double hz = (double)g_qpcFreq;
    EwTrack* t = nullptr;
    // for a new enemy: an unused track, else the one seen longest ago that is
    // not in an episode; with all of them in one the new enemy waits
    EwTrack* slot = nullptr;
    for (EwTrack& e : g_ew) {
        if (e.seen && e.obj == obj) {
            t = &e;
            break;
        }
        if (e.seen && e.hits) continue;
        if (!slot || (slot->seen && (!e.seen || e.seen < slot->seen))) slot = &e;
    }
    if (t && t->vt != s.vt) {
        slot = t;  // another object at the same address: start over in place
        t = nullptr;
    }
    if (!t) {
        if (!slot) return false;
        bool finished = false;
        if (slot->seen && slot->hits) {
            ewFinish(*slot, done);
            finished = true;
        }
        *slot = EwTrack{};
        slot->obj = obj;
        slot->vt = s.vt;
        slot->cls = ewClassOf(s.vt);
        slot->seen = now;
        slot->last = s;
        return finished;
    }
    const EwSnap& p = t->last;
    bool hit = s.hp < p.hp;
    if (hit && !t->hits) {
        t->start = now;
        t->updates = 0;
        t->x0 = p.x;
        t->y0 = p.y;
        t->z0 = p.z;
        t->path = t->top = t->air = 0.0;
        t->rot[0] = t->rot[1] = t->rot[2] = 0.0;
        memcpy(t->st[0], p.st, 3);
        t->stAt[0] = 0.0f;
        t->nSt = 1;
        t->nS = 0;
        t->n0 = ewTicksPerStock();
        t->actor0 = ewActorN();
        t->nChanged = t->unseen = false;
        t->lastChange = now;
    }
    if (t->hits || hit) {
        float at = (float)((double)(now - t->start) / hz);
        if (hit) {
            if (t->hits < kEwMaxHits) {
                t->hitAt[t->hits] = at;
                t->hitDmg[t->hits] = p.hp - s.hp;
                t->hitIv[t->hits] = s.iv;
            }
            t->hits++;
            t->lastHit = now;
        }
        double dx = (double)s.x - p.x, dz = (double)s.z - p.z;
        t->path += sqrt(dx * dx + dz * dz);
        for (int k = 0; k < 3; k++) t->rot[k] += fabs((double)ewWrap(s.r[k] - p.r[k]));
        if (s.y - t->y0 > t->top) t->top = s.y - t->y0;
        // the interval since the last sample was a fall if vy was not 0 at its
        // start, or is not 0 at its end with the enemy above where it was hit
        // (vy is 0 on the ground, and at the top of an arc for one sample)
        if (p.vy != 0.0f || (s.vy != 0.0f && p.y > t->y0 + 0.01f)) {
            t->air += (double)(now - t->seen) / hz;
        }
        if (memcmp(s.st, p.st, 3)) {
            if (t->nSt < kEwMaxStates) {
                memcpy(t->st[t->nSt], s.st, 3);
                t->stAt[t->nSt] = at;
                t->nSt++;
            }
            t->lastChange = now;
        }
        unsigned n = g_ewBreakSample ? 1u : t->n0;
        if (t->updates % n == 0 && t->nS < kEwMaxSamples) {
            double ddx = (double)s.x - t->x0, ddz = (double)s.z - t->z0;
            t->h[t->nS] = (int16_t)lround((double)s.y - t->y0);
            t->d[t->nS] = (int16_t)lround(sqrt(ddx * ddx + ddz * ddz));
            t->nS++;
        }
        t->updates++;
        if (ewTicksPerStock() != t->n0 || ewActorN() != t->actor0) t->nChanged = true;
        double sinceHit = (double)(now - t->lastHit) / hz;
        double sinceChange = (double)(now - t->lastChange) / hz;
        if ((sinceHit > 2.0 && s.vy == 0.0f && sinceChange > 0.5) || sinceHit > 6.0) {
            t->last = s;
            t->seen = now;
            ewFinish(*t, done);
            return true;
        }
    }
    t->last = s;
    t->seen = now;
    return false;
}

// Called by the thunks with the enemy in rcx, before its update runs.
static void ewSample(uint8_t* self) {
    if (!g_ewOn || !self) return;
    EwRead r = {self, {}, false};
    if (guardedCall(ewReadBody, &r) || !r.ok) return;
    EwTrack done;
    AcquireSRWLockExclusive(&g_ewLock);
    bool fin = ewRecord(self, r.s, ewNow(), &done);
    ReleaseSRWLockExclusive(&g_ewLock);
    if (fin) ewLogEpisode(done);
}

// From the watcher loop: an enemy not updated for 1.5 s (gone, or the game
// paused) ends its episode.
static void pollEnemyWatch(LONGLONG now) {
    if (!g_ewOn) return;
    EwTrack done[kEwTracks];
    int n = 0;
    AcquireSRWLockExclusive(&g_ewLock);
    for (EwTrack& e : g_ew) {
        if (e.seen && e.hits && now - e.seen > g_qpcFreq * 3 / 2) {
            e.unseen = true;
            ewFinish(e, &done[n++]);
            e.seen = 0;
        }
    }
    ReleaseSRWLockExclusive(&g_ewLock);
    for (int i = 0; i < n; i++) ewLogEpisode(done[i]);
}

// The thunk (84 bytes): save the argument registers, call sampler(rcx),
// restore them, jump to the update.
static int ewEmitThunk(uint8_t* p, const void* sampler, const void* orig) {
    static const uint8_t head[] = {
        0x51, 0x52, 0x41, 0x50, 0x41, 0x51,  // push rcx; push rdx; push r8; push r9
        0x48, 0x83, 0xEC, 0x68,              // sub rsp, 0x68
        0x0F, 0x11, 0x44, 0x24, 0x20,        // movups [rsp+0x20], xmm0
        0x0F, 0x11, 0x4C, 0x24, 0x30,        // movups [rsp+0x30], xmm1
        0x0F, 0x11, 0x54, 0x24, 0x40,        // movups [rsp+0x40], xmm2
        0x0F, 0x11, 0x5C, 0x24, 0x50,        // movups [rsp+0x50], xmm3
        0x48, 0xB8,                          // mov rax, sampler
    };
    static const uint8_t mid[] = {
        0xFF, 0xD0,                          // call rax
        0x0F, 0x10, 0x44, 0x24, 0x20,        // movups xmm0, [rsp+0x20]
        0x0F, 0x10, 0x4C, 0x24, 0x30,        // movups xmm1, [rsp+0x30]
        0x0F, 0x10, 0x54, 0x24, 0x40,        // movups xmm2, [rsp+0x40]
        0x0F, 0x10, 0x5C, 0x24, 0x50,        // movups xmm3, [rsp+0x50]
        0x48, 0x83, 0xC4, 0x68,              // add rsp, 0x68
        0x41, 0x59, 0x41, 0x58, 0x5A, 0x59,  // pop r9; pop r8; pop rdx; pop rcx
        0x48, 0xB8,                          // mov rax, orig
    };
    static const uint8_t tail[] = {0xFF, 0xE0};  // jmp rax
    static_assert(sizeof(head) == kEwThunkSamplerAt, "sampler imm64 offset");
    static_assert(sizeof(head) + 8 + sizeof(mid) == kEwThunkOrigAt, "orig imm64 offset");
    int n = 0;
    memcpy(p + n, head, sizeof(head));
    n += sizeof(head);
    uint64_t v = (uint64_t)sampler;
    memcpy(p + n, &v, 8);
    n += 8;
    memcpy(p + n, mid, sizeof(mid));
    n += sizeof(mid);
    v = (uint64_t)orig;
    memcpy(p + n, &v, 8);
    n += 8;
    memcpy(p + n, tail, sizeof(tail));
    n += sizeof(tail);
    return n;
}

// Unwind data for the thunks' prolog (push rcx, rdx, r8, r9; sub rsp, 0x68),
// so a stack walk from inside the sampler gets through them.
static const uint8_t kEwUnwind[] = {
    0x01, 10, 5, 0x00,  // version 1, prolog 10 bytes, 5 codes, no frame register
    10, 0xC2,           // at 10: alloc small, 12 * 8 + 8 = 0x68
    6, 0x90,            // at 6: push r9
    4, 0x80,            // at 4: push r8
    2, 0x20,            // at 2: push rdx
    1, 0x10,            // at 1: push rcx
    0, 0,               // pad to an even count
};

// A cave of thunks for `count` targets, the unwind info and the function
// table after them; returns the cave (RX) or null.
static uint8_t* ewBuildThunks(const void* const* targets, int count, const void* sampler) {
    size_t unwindAt = (size_t)count * kEwThunkSize;
    size_t tableAt = (unwindAt + sizeof(kEwUnwind) + 15) & ~(size_t)15;
    size_t size = tableAt + (size_t)count * sizeof(RUNTIME_FUNCTION);
    uint8_t* cave = (uint8_t*)VirtualAlloc(nullptr, size, MEM_COMMIT | MEM_RESERVE,
                                           PAGE_READWRITE);
    if (!cave) return nullptr;
    memset(cave, 0xCC, unwindAt);
    for (int i = 0; i < count; i++) ewEmitThunk(cave + (size_t)i * kEwThunkSize, sampler, targets[i]);
    memcpy(cave + unwindAt, kEwUnwind, sizeof(kEwUnwind));
    RUNTIME_FUNCTION* rf = (RUNTIME_FUNCTION*)(cave + tableAt);
    for (int i = 0; i < count; i++) {
        rf[i].BeginAddress = (DWORD)(i * kEwThunkSize);
        rf[i].EndAddress = (DWORD)(i * kEwThunkSize + kEwThunkOrigAt + 8 + 2);
        rf[i].UnwindData = (DWORD)unwindAt;
    }
    DWORD old;
    if (!VirtualProtect(cave, size, PAGE_EXECUTE_READ, &old)) {
        VirtualFree(cave, 0, MEM_RELEASE);
        return nullptr;
    }
    FlushInstructionCache(GetCurrentProcess(), cave, size);
    RtlAddFunctionTable(rf, (DWORD)count, (DWORD64)cave);
    return cave;
}

static void installEnemyWatch() {
    if (!g_cfg.enemyWatch || !g_eng.main || g_ewOn) {
        return;
    }
    uint8_t* main = g_eng.main;
    for (const auto& e : kEwEvidence) {
        if (memcmp(main + e.rva, e.bytes, e.len)) {
            logf("enemy watch: main+%X differs from main.dll sha1 %s, not started", e.rva,
                 ENEMY_WATCH_MAIN_SHA1);
            return;
        }
    }
    const void* targets[kEwClassCount];
    int nt = 0;
    for (const auto& c : kEwClasses) {
        uint64_t* slot = (uint64_t*)(main + c.vtable + kEwSlotOff);
        if (*slot != (uint64_t)(main + c.update)) {
            logf("enemy watch: %s's update slot main+%X does not hold main+%X, not started", c.name,
                 c.vtable + kEwSlotOff, c.update);
            return;
        }
        const void* u = main + c.update;
        bool have = false;
        for (int i = 0; i < nt; i++) have |= targets[i] == u;
        if (!have) targets[nt++] = u;
    }
    uint8_t* cave = ewBuildThunks(targets, nt, (const void*)&ewSample);
    if (!cave) {
        logf("enemy watch: no memory for the thunks, not started");
        return;
    }
    // all or none: a slot that cannot be written puts the ones before it back
    int written = 0;
    for (const auto& c : kEwClasses) {
        uint64_t* slot = (uint64_t*)(main + c.vtable + kEwSlotOff);
        int k = 0;
        while (targets[k] != main + c.update) k++;
        uint64_t thunk = (uint64_t)(cave + (size_t)k * kEwThunkSize);
        if (!writeProtected(slot, &thunk, 8)) break;
        written++;
    }
    if (written < kEwClassCount) {
        for (int i = 0; i < written; i++) {
            uint64_t orig = (uint64_t)(main + kEwClasses[i].update);
            writeProtected(main + kEwClasses[i].vtable + kEwSlotOff, &orig, 8);
        }
        logf("enemy watch: a vtable slot could not be written, not started");
        return;
    }
    g_ewCave = cave;
    g_ewThunks = nt;
    g_ewOn = true;
    logf("enemy watch: on, %d enemy classes' updates wrapped (%d thunks). Each enemy hit logs an "
         "\"enemy:\" line when it settles: hits, ground covered, top height, time falling, "
         "states, and its height/distance once per stock tick",
         kEwClassCount, nt);
}

// ---------------------------------------------------------------------------
// Offline self-test, driven by tools/verify_enemy_watch.py without the game.
// ---------------------------------------------------------------------------
static const uint8_t* g_ewTestSelf = nullptr;
static int g_ewTestCalls = 0;
#ifdef _MSC_VER
#define EW_NOINLINE __declspec(noinline)
#else
#define EW_NOINLINE __attribute__((noinline))
#endif

// A sampler that clobbers every volatile register the thunk must restore.
static EW_NOINLINE void ewTestSampler(uint8_t* self) {
    g_ewTestSelf = self;
    g_ewTestCalls++;
#if defined(__clang__) || defined(__GNUC__)
    __asm__ volatile(
        "xorps %%xmm0, %%xmm0\n\txorps %%xmm1, %%xmm1\n\txorps %%xmm2, %%xmm2\n\t"
        "xorps %%xmm3, %%xmm3\n\txorl %%edx, %%edx\n\txorl %%r8d, %%r8d\n\t"
        "xorl %%r9d, %%r9d\n\txorl %%ecx, %%ecx"
        :
        :
        : "xmm0", "xmm1", "xmm2", "xmm3", "rdx", "r8", "r9", "rcx");
#endif
}
static EW_NOINLINE uint64_t ewTestOrigInt(void* a, uint64_t b, uint64_t c,
                                                        uint64_t d) {
    return (uint64_t)a * 3 + b * 5 + c * 7 + d * 11;
}
static EW_NOINLINE float ewTestOrigFloat(void* a, float b, float c, float d) {
    return (float)(uintptr_t)a * 0.0f + b * 2.0f + c * 3.0f + d * 5.0f;
}

// A synthetic enemy flown through the watch: hits at stock ticks 10 and 22,
// each launching it from where it is on the arc y = vy0 t - g t^2 / 2 and
// x = vx0 t (t in stock ticks since the launch) until it lands, with `n`
// updates per stock tick. The arc is exact at every update, so stock and a
// fixed 120 put it in the same place at every stock tick; `push` > 1 is the
// sideways push still applied whole every update while the fall takes its
// stock time: `push` times the ground.
struct EwFlight {
    unsigned n;
    double push;
};
static bool ewFly(uint8_t* obj, const EwFlight& f, EwTrack* out) {
    const uint64_t vt = (uint64_t)(g_eng.main + kEwClasses[0].vtable);
    memset(obj, 0, 0x1000);
    memcpy(obj, &vt, 8);
    float* pos = (float*)(obj + 0x80);
    const float* pp = pos;
    memcpy(obj + kEwPosPtr, &pp, 8);
    int32_t hp = 100;
    memcpy(obj + kEwHp, &hp, 4);
    obj[kEwState] = 2;
    g_ewFakeN = f.n;
    int before = g_ewDoneN;
    double x = 0, y = 0, vy = 0, yaw = 0;
    double x0 = 0, y0 = 0, yaw0 = 0, launch = 0;
    bool up = false;
    const int hitTicks[] = {10, 22};
    const double g = 0.6, vy0 = 6.0, vx0 = 3.0;
    const uint32_t total = 30 * 5;  // 5 s of stock ticks
    for (uint32_t k = 0; k < total * f.n; k++) {
        double stock = (double)k / f.n;
        g_ewFakeNow = 1000000 + (LONGLONG)((double)k * g_qpcFreq / (30.0 * f.n));
        // where the arc has it now; then a hit on a stock tick launches it
        // from there
        auto arc = [&]() {
            double land = (vy0 + sqrt(vy0 * vy0 + 2.0 * g * y0)) / g;
            double t = stock - launch;
            double u = t < land ? t : land;
            y = t < land ? y0 + vy0 * u - 0.5 * g * u * u : 0.0;
            vy = t < land ? vy0 - g * u : 0.0;
            x = x0 + vx0 * u * f.push;
            yaw = yaw0 + 0.1 * u * f.push;
            if (t >= land) {
                up = false;
                obj[kEwState + 1] = 0;
            }
        };
        if (up) arc();
        if (k % f.n == 0) {
            for (int ht : hitTicks) {
                if ((uint32_t)ht == (uint32_t)stock) {
                    hp -= 10;
                    x0 = x;
                    y0 = y;
                    yaw0 = yaw;
                    launch = stock;
                    up = true;
                    obj[kEwState + 1] = 3;
                    obj[kEwInvuln] = 10;
                    arc();
                }
            }
        }
        memcpy(obj + kEwHp, &hp, 4);
        pos[0] = (float)x;
        pos[1] = (float)y;
        pos[2] = 0.0f;
        float fy = (float)vy, fyaw = (float)yaw;
        memcpy(obj + kEwVy, &fy, 4);
        memcpy(obj + kEwRot + 4, &fyaw, 4);
        ewSample(obj);
    }
    g_ewFakeNow = 0;
    g_ewFakeN = 0;
    if (g_ewDoneN != before + 1) return false;
    *out = g_ewDone[(g_ewDoneN - 1) % 4];
    return true;
}

extern "C" __declspec(dllexport) int OkamiEnemyWatchSelfTest(const char* mainPath,
                                                            const char* outDir, int breakMode) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) return 2;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    g_eng.main = (uint8_t*)m;
    if (!g_qpcFreq) g_qpcFreq = 10000000;
    int fails = 0;
    // 1. the install: evidence, every slot at a thunk that samples and jumps to
    //    the update the table names, unwind data found for each thunk
    g_cfg.enemyWatch = true;
    installEnemyWatch();
    fprintf(rep, "%s install: %d classes, %d thunks\n", g_ewOn ? "ok  " : "FAIL", kEwClassCount,
            g_ewThunks);
    fails += !g_ewOn;
    if (g_ewOn) {
        int bad = 0;
        for (const auto& c : kEwClasses) {
            uint64_t t = *(uint64_t*)(g_eng.main + c.vtable + kEwSlotOff);
            uint8_t* th = (uint8_t*)t;
            uint64_t smp, org;
            memcpy(&smp, th + kEwThunkSamplerAt, 8);
            memcpy(&org, th + kEwThunkOrigAt, 8);
            DWORD64 base = 0;
            PRUNTIME_FUNCTION rf = RtlLookupFunctionEntry((DWORD64)(th + 20), &base, nullptr);
            bool ok = th >= g_ewCave && th < g_ewCave + (size_t)g_ewThunks * kEwThunkSize &&
                      smp == (uint64_t)&ewSample && org == (uint64_t)(g_eng.main + c.update) &&
                      rf && base == (DWORD64)g_ewCave &&
                      base + rf->BeginAddress == (DWORD64)th;
            if (!ok) {
                fprintf(rep, "FAIL slot of %s: thunk %p sampler %llx orig %llx unwind %p\n",
                        c.name, (void*)th, (unsigned long long)smp, (unsigned long long)org,
                        (void*)rf);
                bad++;
            }
        }
        fprintf(rep, "%s slots: %d of %d at a thunk of their own update, with unwind data\n",
                bad ? "FAIL" : "ok  ", kEwClassCount - bad, kEwClassCount);
        fails += bad != 0;
    }
    // 2. the thunk: arguments reach the update in every register, its return
    //    value reaches the caller, and the sampler sees the object first
    {
        const void* t2[2] = {(const void*)&ewTestOrigInt, (const void*)&ewTestOrigFloat};
        uint8_t* cave = ewBuildThunks(t2, 2, (const void*)&ewTestSampler);
        bool ok = cave != nullptr;
        if (ok) {
            typedef uint64_t (*FI)(void*, uint64_t, uint64_t, uint64_t);
            typedef float (*FF)(void*, float, float, float);
            void* self = (void*)(uintptr_t)0x123456789A;
            g_ewTestCalls = 0;
            uint64_t ri = ((FI)cave)(self, 0x1111, 0x2222, 0x3333);
            float rf = ((FF)(cave + kEwThunkSize))(self, 1.5f, 2.5f, 3.5f);
            ok = ri == ewTestOrigInt(self, 0x1111, 0x2222, 0x3333) &&
                 rf == ewTestOrigFloat(self, 1.5f, 2.5f, 3.5f) && g_ewTestCalls == 2 &&
                 g_ewTestSelf == (const uint8_t*)self;
            fprintf(rep, "%s thunk: int args -> %llx (want %llx), float args -> %g (want %g), "
                    "sampler ran %d times\n", ok ? "ok  " : "FAIL", (unsigned long long)ri,
                    (unsigned long long)ewTestOrigInt(self, 0x1111, 0x2222, 0x3333), rf,
                    ewTestOrigFloat(self, 1.5f, 2.5f, 3.5f), g_ewTestCalls);
        } else {
            fprintf(rep, "FAIL thunk: no cave\n");
        }
        fails += !ok;
    }
    // 3. the episode: the same flight at 30 and at a fixed 120 reads the same,
    //    and 120 with only the fall fixed reads four times the ground
    g_ewOn = true;
    g_ewBreakSample = breakMode == 1;
    alignas(16) static uint8_t obj[0x1000];
    EwTrack s30, f120, u120;
    bool got = ewFly(obj, {1, 1.0}, &s30) && ewFly(obj, {4, 1.0}, &f120) &&
               ewFly(obj, {4, 4.0}, &u120);
    g_ewBreakSample = false;
    if (!got) {
        fprintf(rep, "FAIL episodes: a flight did not end in exactly one episode\n");
        fails++;
    } else {
        auto show = [&](const char* name, const EwTrack& t) {
            fprintf(rep, "     %s: hits %d over %.3f s, moved %.1f, top %.1f, falling %.3f s, "
                    "turned %.2f, states %d, samples %d\n", name, t.hits,
                    (double)(t.lastHit - t.start) / g_qpcFreq, t.path, t.top, t.air, t.rot[1],
                    t.nSt, t.nS);
        };
        show("stock 30         ", s30);
        show("fixed 120        ", f120);
        show("120, fall fixed  ", u120);
        auto within = [](double a, double b, double tol) { return fabs(a - b) <= tol * fabs(b) + 1.0; };
        // the episode ends on the first update past 2 s: at 120 that can be a
        // quarter tick before stock's last sample, so one sample fewer
        // the flight is the same function of time in both, so the totals and
        // the samples match to rounding
        bool same = f120.hits == s30.hits && abs(f120.nS - s30.nS) <= 1 && s30.nS >= 30 &&
                    f120.nSt == s30.nSt && within(f120.path, s30.path, 0.01) &&
                    within(f120.top, s30.top, 0.01) && fabs(f120.air - s30.air) <= 1.0 / 30.0 &&
                    within(f120.rot[1], s30.rot[1], 0.01);
        int worst = 0;
        int common = f120.nS < s30.nS ? f120.nS : s30.nS;
        for (int i = 0; same && i < common; i++) {
            int dh = abs(f120.h[i] - s30.h[i]), dd = abs(f120.d[i] - s30.d[i]);
            if (dh > 1 || dd > 1) same = false;
            worst = dh > worst ? dh : worst;
            worst = dd > worst ? dd : worst;
        }
        fprintf(rep, "%s fixed 120 reads as stock 30 (per stock tick, worst gap %d)\n",
                same ? "ok  " : "FAIL", worst);
        bool fast = u120.path > 3.0 * s30.path && u120.hits == s30.hits;
        fprintf(rep, "%s 120 with only the fall fixed reads %.1fx the ground\n", fast ? "ok  " : "FAIL",
                s30.path > 0 ? u120.path / s30.path : 0.0);
        fails += !same + !fast;
    }
    // 4. the poll ends an episode whose enemy stopped updating
    {
        memset(g_ew, 0, sizeof(g_ew));
        g_ewFakeN = 1;
        EwSnap a = {};
        a.hp = 50;
        a.vt = 1;
        g_ewFakeNow = 5000000;
        EwTrack d;
        ewRecord(obj, a, g_ewFakeNow, &d);
        a.hp = 40;
        a.vy = 1.0f;
        g_ewFakeNow += g_qpcFreq / 30;
        ewRecord(obj, a, g_ewFakeNow, &d);
        int before = g_ewDoneN;
        pollEnemyWatch(g_ewFakeNow + g_qpcFreq);
        bool kept = g_ewDoneN == before;
        pollEnemyWatch(g_ewFakeNow + 2 * g_qpcFreq);
        bool ended = g_ewDoneN == before + 1 && g_ewDone[before % 4].unseen;
        g_ewFakeNow = 0;
        g_ewFakeN = 0;
        fprintf(rep, "%s poll: kept at 1.0 s, ended at 2.0 s\n", kept && ended ? "ok  " : "FAIL");
        fails += !(kept && ended);
    }
    // 5. more enemies than tracks: sixteen in episodes, and a seventeenth
    //    updating every tick neither takes a track nor cuts one short
    {
        memset(g_ew, 0, sizeof(g_ew));
        g_ewFakeN = 1;
        static uint8_t many[kEwTracks + 1][16];
        int before = g_ewDoneN;
        EwTrack d;
        LONGLONG now = 9000000;
        for (int i = 0; i < kEwTracks; i++) {
            EwSnap a = {};
            a.vt = 1;
            a.hp = 50;
            ewRecord(many[i], a, now, &d);
            a.hp = 40;
            a.vy = 1.0f;
            ewRecord(many[i], a, now + 1, &d);
        }
        EwSnap b = {};
        b.vt = 1;
        b.hp = 30;
        bool tracked = false;
        for (int k = 0; k < 60; k++) {
            now += g_qpcFreq / 30;
            ewRecord(many[kEwTracks], b, now, &d);
        }
        for (EwTrack& e : g_ew) tracked |= e.obj == many[kEwTracks];
        int active = 0;
        for (EwTrack& e : g_ew) active += e.hits > 0;
        bool ok = !tracked && active == kEwTracks && g_ewDoneN == before;
        g_ewFakeN = 0;
        fprintf(rep, "%s busy: %d enemies in episodes, a 17th waits (tracked %d, cut short %d)\n",
                ok ? "ok  " : "FAIL", active, (int)tracked, g_ewDoneN - before);
        fails += !ok;
        memset(g_ew, 0, sizeof(g_ew));
    }
    g_ewOn = false;
    fprintf(rep, "%s\n", fails ? "FAILED" : "all checks passed");
    fclose(rep);
    return fails ? 1 : 0;
}
