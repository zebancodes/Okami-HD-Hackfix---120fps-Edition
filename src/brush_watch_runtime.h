// The Rejuvenation watch. Included
// once by dinput8_proxy.cpp. It changes nothing in the game: from the watcher
// thread, about 100 times a second, it reads the brush object and after each
// use of the brush says which stage of Rejuvenation failed, if one did.
//
// Rejuvenation is judged on the CPU from a mask the GPU renders
// (tools/gen_brush_watch.py has the addresses and their evidence):
//   1. a restorable object in view offers itself: the candidate (+0xCB8);
//   2. the first stroke asks the renderer for the target's mask. The renderer
//      draws the missing part into render target 10, copies that to a CPU
//      texture of the target's own format, maps it and samples 256 x 224
//      pixels as 4-byte BGRA: non-black is mask. That is the saved mask. A
//      render target of another format (an add-on that upgrades the game's
//      BGRA8 targets to FP16 does exactly this) reads back nothing, or noise;
//   3. a stroke that touches the mask engages the target (+0xC84);
//   4. on release the evaluation inks a square of half-width size/4 at each
//      stroke point on a 256 x 224 canvas and counts the mask's pixels and the
//      inked ones among them: 40% inked restores the object.
// The watch follows 1 and 3 live, sees each capture as a change of the saved
// mask, reads the evaluation's result, and recomputes 4 itself from the saved
// mask and the stroke points exactly as the game does (brushCover, checked
// against the game's own code by tools/verify_brush_watch.py). It logs one
// "brush:" line per use and, where a target was offered, writes
// brush_watch\attempt_NNN.bmp: the mask red, the ink blue, both yellow.
#include "brush_watch.h"

#include <immintrin.h>

static bool g_bwReady = false;
static int g_bwPrev = 0;       // the brush state at the previous poll
static int g_bwAttempts = 0;

struct BrushAttempt {
    bool active, snapped;
    LONGLONG t0;
    int candidate, engaged;    // the first non-negative seen, else -1
    int maxState;
    uint32_t maskSum0, maskSum;  // the saved mask's checksum when it began, and at the last poll
    int captures;              // how often the saved mask changed while it ran
    int requests;              // polls that saw the one-tick capture request (may miss some)
    float ratio;               // the game's, if the watch saw it before the idle state cleared it
    bool ratioSeen;
    uint32_t bits, points, strokes;
    uint16_t map;
};
static BrushAttempt g_ba = {};
static uint8_t g_bwMask[kBrushCanvasW * kBrushCanvasH];
static uint8_t g_bwInk[kBrushCanvasW * kBrushCanvasH];
static uint8_t g_bwPts[0x600 * kBrushPointSize];

struct BrushCover {
    uint32_t masked, inked, ink;  // mask pixels, inked mask pixels, inked pixels
    int mx0, mx1, my0, my1, ix0, ix1, iy0, iy1;  // their bounds on the canvas (x0 > x1: none)
    float ratio;                  // as the game computes it, for a map with one mask
};

// The evaluation, exactly: main+17ECC0's ink (cvttss2si, sar, the 32-bit sums
// and the unsigned bounds tests included) and main+17DC90's counts and ratio.
static void brushCover(const uint8_t* mask, const uint8_t* pts, uint32_t n, uint8_t* ink,
                       BrushCover& c) {
    memset(ink, 0, (size_t)kBrushCanvasW * kBrushCanvasH);
    for (uint32_t i = 0; i < n; i++) {
        const uint8_t* p = pts + (size_t)i * kBrushPointSize;
        if (!p[0]) {
            continue;
        }
        float x, y, sz;
        memcpy(&x, p + 4, 4);
        memcpy(&y, p + 8, 4);
        memcpy(&sz, p + 12, 4);
        int32_t h = _mm_cvtt_ss2si(_mm_set_ss(sz)) >> 2;
        if (h <= 0) h = 1;
        int32_t cy = _mm_cvtt_ss2si(_mm_set_ss(y)) >> 1;
        int32_t cx = _mm_cvtt_ss2si(_mm_set_ss(x)) >> 1;
        int64_t y0 = (int32_t)((uint32_t)cy - (uint32_t)h), y1 = (int32_t)((uint32_t)cy + (uint32_t)h);
        int64_t x0 = (int64_t)cx - h, x1 = (int32_t)((uint32_t)cx + (uint32_t)h);
        for (int64_t yy = y0; yy <= y1; yy++) {
            if ((uint64_t)yy > 0xDF) continue;
            for (int64_t xx = x0; xx <= x1; xx++) {
                if ((uint64_t)xx <= 0xFF) ink[xx * kBrushCanvasH + yy] |= 1;
            }
        }
    }
    c = BrushCover{};
    c.mx0 = c.ix0 = kBrushCanvasW;
    c.my0 = c.iy0 = kBrushCanvasH;
    c.mx1 = c.my1 = c.ix1 = c.iy1 = -1;
    for (int x = 0; x < kBrushCanvasW; x++) {
        for (int y = 0; y < kBrushCanvasH; y++) {
            bool m = (mask[x * kBrushCanvasH + y] & 1) != 0, k = ink[x * kBrushCanvasH + y] != 0;
            if (m) {
                c.masked++;
                c.inked += k;
                c.mx0 = x < c.mx0 ? x : c.mx0;
                c.mx1 = x > c.mx1 ? x : c.mx1;
                c.my0 = y < c.my0 ? y : c.my0;
                c.my1 = y > c.my1 ? y : c.my1;
            }
            if (k) {
                c.ink++;
                c.ix0 = x < c.ix0 ? x : c.ix0;
                c.ix1 = x > c.ix1 ? x : c.ix1;
                c.iy0 = y < c.iy0 ? y : c.iy0;
                c.iy1 = y > c.iy1 ? y : c.iy1;
            }
        }
    }
    // counts go to float first (cvtdq2ps), then the division is in double
    c.ratio = c.masked ? (float)((double)(float)c.inked / ((double)(float)c.masked * kBrushNeed))
                       : 0.0f;
}

static uint32_t brushMaskSum(const volatile uint8_t* m) {
    uint32_t h = 2166136261u;  // FNV-1a over the whole mask
    for (int i = 0; i < kBrushCanvasW * kBrushCanvasH; i++) {
        h = (h ^ m[i]) * 16777619u;
    }
    return h;
}

// The mask red, the ink blue, both yellow, at twice the canvas: the game's
// 512 x 448 screen coordinates.
static bool brushWriteBmp(const char* path, const uint8_t* mask, const uint8_t* ink) {
    const int w = 2 * kBrushCanvasW, h = 2 * kBrushCanvasH, row = w * 3;
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    uint8_t hdr[54] = {'B', 'M'};
    uint32_t size = 54 + (uint32_t)(row * h), off = 54, dib = 40, planesBpp = 1 | (24 << 16);
    int32_t ww = w, hh = h;
    memcpy(hdr + 2, &size, 4);
    memcpy(hdr + 10, &off, 4);
    memcpy(hdr + 14, &dib, 4);
    memcpy(hdr + 18, &ww, 4);
    memcpy(hdr + 22, &hh, 4);
    memcpy(hdr + 26, &planesBpp, 4);
    bool ok = fwrite(hdr, 1, 54, f) == 54;
    static uint8_t line[2 * kBrushCanvasW * 3];
    for (int py = h - 1; py >= 0 && ok; py--) {  // bottom-up
        for (int px = 0; px < w; px++) {
            int i = (px / 2) * kBrushCanvasH + py / 2;
            bool m = (mask[i] & 1) != 0, k = ink[i] != 0;
            uint8_t r = 24, g = 24, b = 28;
            if (m && k) r = 240, g = 210, b = 60;
            else if (m) r = 170, g = 40, b = 40;
            else if (k) r = 60, g = 110, b = 230;
            line[px * 3] = b;
            line[px * 3 + 1] = g;
            line[px * 3 + 2] = r;
        }
        ok = fwrite(line, 1, row, f) == (size_t)row;
    }
    return fclose(f) == 0 && ok;
}

// Copy what the evaluation used: the saved mask (it was copied to mask 0 for
// the check and is kept until the next capture) and the stroke points (kept
// until the brush opens again, which a 20-tick cooldown keeps it from doing
// before the watch sees the brush closed).
static void brushSnapshot(const uint8_t* base) {
    BrushAttempt& a = g_ba;
    const uint8_t* b = base + kBrushRva;
    memcpy(g_bwMask, base + kBrushSavedMaskRva, sizeof(g_bwMask));
    a.points = *(const volatile uint32_t*)(base + kBrushPointCountRva);
    if (a.points > 0x600) a.points = 0x600;
    memcpy(g_bwPts, base + kBrushPointsRva, (size_t)a.points * kBrushPointSize);
    a.strokes = *(const volatile uint32_t*)(base + kBrushStrokeCountRva);
    a.bits = *(const volatile uint32_t*)(base + kBrushBitsRva);
    a.map = *(const volatile uint16_t*)(base + kBrushMapRva);
    if (*(const volatile int32_t*)(b + kBrushStateOff) != 0) {
        a.ratio = *(const volatile float*)(base + kBrushRatioRva);  // the idle state zeroes it
        a.ratioSeen = true;
    }
    a.snapped = true;
}

// One line, and the verdict: which stage stopped it. Returns the verdict's
// short name for the image's file name.
static const char* brushVerdict(char* out, size_t n, const BrushAttempt& a, const BrushCover& c) {
    char mb[64] = "", ib[64] = "";
    if (c.masked) snprintf(mb, sizeof(mb), " at x %d-%d y %d-%d", c.mx0, c.mx1, c.my0, c.my1);
    if (c.ink) snprintf(ib, sizeof(ib), " at x %d-%d y %d-%d", c.ix0, c.ix1, c.iy0, c.iy1);
    double pct = c.masked ? 100.0 * c.inked / c.masked : 0.0;
    const char* tag;
    int u;
    if (a.candidate < 0 && a.engaged < 0) {
        tag = "none";
        u = snprintf(out, n, "no restorable target was on offer (not a Rejuvenation spot, or not in"
                     " view)");
    } else if (a.map == 0x312) {
        tag = "map312";
        u = snprintf(out, n, "map 0x312 has seven masks and a check of its own; the game says %s",
                     a.bits ? "RESTORED" : "not restored");
    } else if (!c.masked) {
        tag = "empty_mask";
        u = snprintf(out, n, "target %d %s, NOT RESTORED: its mask is EMPTY. %s The GPU readback of"
                     " render target 10 gave nothing; an add-on that changes the game's render-target"
                     " formats (RenoDX's BGRA8 -> FP16 upgrade) breaks this readback",
                     a.candidate >= 0 ? a.candidate : a.engaged,
                     a.engaged >= 0 ? "engaged" : "offered, never engaged",
                     a.captures ? "A capture wrote it empty."
                     : a.requests ? "A capture was asked for and the mask stayed empty."
                                  : "No capture was seen and the mask stayed empty.");
    } else if (a.engaged < 0) {
        tag = "not_engaged";
        u = snprintf(out, n, "target %d offered, never engaged: no stroke touched its mask (mask %u px%s,"
                     " ink %u px%s)", a.candidate, c.masked, mb, c.ink, ib);
    } else if (a.bits || c.ratio >= 1.0f) {
        tag = "restored";
        u = snprintf(out, n, "target %d RESTORED: %u of its %u mask px inked = %.0f%% (needs %.0f%%);"
                     " mask%s, ink%s", a.engaged, c.inked, c.masked, pct, 100.0 * kBrushNeed, mb, ib);
    } else {
        tag = "too_little_ink";
        u = snprintf(out, n, "target %d NOT RESTORED: %u of its %u mask px inked = %.0f%%, needs %.0f%%;"
                     " mask%s, ink%s", a.engaged, c.inked, c.masked, pct, 100.0 * kBrushNeed, mb, ib);
    }
    // the game's own verdict beside the watch's, where both exist
    size_t at = u > 0 && (size_t)u < n ? (size_t)u : n;
    if (a.engaged >= 0 && a.map != 0x312 && at < n) {
        bool agree = (a.bits != 0) == (c.ratio >= 1.0f) &&
                     (!a.ratioSeen || a.ratio == c.ratio || a.ratio == 0.0f);
        snprintf(out + at, n - at, " [game: %s, ratio %s; watch ratio %.3f%s]",
                 a.bits ? "restored" : "not restored",
                 a.ratioSeen ? (a.ratio == 0.0f ? "not seen" : "seen") : "not seen", c.ratio,
                 agree ? "" : ", DISAGREE: the mask or points changed after the check");
    }
    return tag;
}

static void brushFinish() {
    BrushAttempt& a = g_ba;
    a.active = false;
    g_bwAttempts++;
    BrushCover c;
    brushCover(g_bwMask, g_bwPts, a.points, g_bwInk, c);
    char verdict[600];
    const char* tag = brushVerdict(verdict, sizeof(verdict), a, c);
    double secs = (double)(qpc() - a.t0) / (double)g_qpcFreq;
    char img[MAX_PATH] = "";
    if (a.candidate >= 0 || a.engaged >= 0) {
        char dir[MAX_PATH];
        snprintf(dir, sizeof(dir), "%sbrush_watch", g_baseDir);
        CreateDirectoryA(dir, nullptr);
        snprintf(img, sizeof(img), "%s\\attempt_%03d_%s.bmp", dir, g_bwAttempts, tag);
        if (!brushWriteBmp(img, g_bwMask, g_bwInk)) {
            snprintf(img, sizeof(img), "(image not written)");
        }
    }
    logf("brush: attempt %d (%.1f s, %u stroke%s, %u points, %d capture%s, fps mode %s): %s%s%s",
         g_bwAttempts, secs, a.strokes, a.strokes == 1 ? "" : "s", a.points, a.captures,
         a.captures == 1 ? "" : "s", g_cfg.passthrough ? "passthrough" : g_fps60 ? "patched" : "stock",
         verdict, img[0] ? "; image " : "", img);
}

// From the watcher thread, every loop (about 100 Hz).
static void pollBrushWatch(LONGLONG now) {
    if (!g_bwReady) {
        return;
    }
    const uint8_t* base = g_eng.main;
    const uint8_t* b = base + kBrushRva;
    int state = *(const volatile int32_t*)(b + kBrushStateOff);
    BrushAttempt& a = g_ba;
    if (state != 0 && g_bwPrev == 0 && !a.active) {
        a = BrushAttempt{};
        a.active = true;
        a.t0 = now;
        a.candidate = a.engaged = -1;
        a.maskSum0 = a.maskSum = brushMaskSum(base + kBrushSavedMaskRva);
    }
    if (a.active && state != 0) {
        int cand = *(const volatile int32_t*)(b + kBrushCandidateOff);
        int eng = *(const volatile int32_t*)(b + kBrushEngagedOff);
        if (cand >= 0 && a.candidate < 0) a.candidate = cand;
        if (eng >= 0 && a.engaged < 0) a.engaged = eng;
        a.requests += *(const volatile int32_t*)(b + kBrushRequestOff) != 0;
        a.maxState = state > a.maxState ? state : a.maxState;
        uint32_t s = brushMaskSum(base + kBrushSavedMaskRva);
        if (s != a.maskSum) {
            a.captures++;
            a.maskSum = s;
        }
        if (state >= 4 && !a.snapped) {
            brushSnapshot(base);  // the evaluation ran in state 3
        }
    }
    if (a.active && state == 0) {
        if (!a.snapped) {
            brushSnapshot(base);
        }
        brushFinish();
    }
    g_bwPrev = state;
}

static void installBrushWatch() {
    if (!g_cfg.brushWatch || !g_eng.main || g_bwReady) {
        return;
    }
    for (const auto& e : kBrushEvidence) {
        if (memcmp(g_eng.main + e.rva, e.bytes, e.len)) {
            logf("brush watch: main+%X differs from main.dll sha1 %s, not started", e.rva,
                 BRUSH_WATCH_MAIN_SHA1);
            return;
        }
    }
    g_bwReady = true;
    logf("brush watch: on (%d instructions checked). Each use of the brush logs a \"brush:\" line;"
         " where a restorable target was on offer it also writes brush_watch\\attempt_NNN.bmp"
         " (mask red, ink blue, both yellow)", (int)(sizeof(kBrushEvidence) / sizeof(kBrushEvidence[0])));
}

// For tools/verify_brush_watch.py: the watch's model of the evaluation, run on
// the verifier's own mask and points, to hold against the game's code.
extern "C" __declspec(dllexport) int OkamiBrushCover(const uint8_t* mask, const uint8_t* pts,
                                                     uint32_t n, uint8_t* inkOut, uint32_t* counts,
                                                     float* ratio) {
    BrushCover c;
    brushCover(mask, pts, n, inkOut, c);
    counts[0] = c.masked;
    counts[1] = c.inked;
    counts[2] = c.ink;
    *ratio = c.ratio;
    return 0;
}

// Offline: map main.dll without running it, check the evidence, then play
// brush uses through the watch by writing the brush object's fields the way
// the game does, and check each verdict and image.
extern "C" __declspec(dllexport) int OkamiBrushWatchSelfTest(const char* mainPath,
                                                             const char* outDir) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s\\report.txt", outDir);
    FILE* rep = fopen(path, "w");
    if (!rep) return 2;
    HMODULE m = LoadLibraryExA(mainPath, nullptr, DONT_RESOLVE_DLL_REFERENCES);
    if (!m) {
        fprintf(rep, "FAIL load\n");
        fclose(rep);
        return 1;
    }
    g_eng.main = (uint8_t*)m;
    g_cfg.brushWatch = true;
    snprintf(g_baseDir, sizeof(g_baseDir), "%s\\", outDir);
    if (!g_qpcFreq) g_qpcFreq = 10000000;
    installBrushWatch();
    if (!g_bwReady) {
        fprintf(rep, "FAIL evidence\n");
        fclose(rep);
        return 1;
    }
    int fails = 0;
    uint8_t* base = g_eng.main;
    uint8_t* b = base + kBrushRva;
    auto put32 = [&](uint8_t* p, uint32_t v) { memcpy(p, &v, 4); };
    auto putf = [&](uint8_t* p, float v) { memcpy(p, &v, 4); };
    uint8_t* saved = base + kBrushSavedMaskRva;
    // a rectangle of mask, x 40-79, y 30-69 (1600 px)
    auto fillMask = [&](bool on) {
        memset(saved, 0, sizeof(g_bwMask));
        for (int x = 40; x < 80 && on; x++)
            for (int y = 30; y < 70; y++) saved[x * kBrushCanvasH + y] = 1;
    };
    // n points of size 21 (half-width 5) along y = 2*yc from x = 2*x0, step 2*dx
    auto points = [&](int n, int x0, int dx, int yc) {
        uint8_t* p = base + kBrushPointsRva;
        memset(p, 0, (size_t)0x600 * kBrushPointSize);
        for (int i = 0; i < n; i++) {
            uint8_t* r = p + (size_t)i * kBrushPointSize;
            r[0] = 3;
            putf(r + 4, (float)(2 * (x0 + i * dx)));
            putf(r + 8, (float)(2 * yc));
            putf(r + 12, 21.0f);
        }
        put32(base + kBrushPointCountRva, (uint32_t)n);
        put32(base + kBrushStrokeCountRva, 1);
    };
    LONGLONG t = 1000;
    // one use of the brush, polled at 100 Hz: the states the game goes through,
    // with the candidate/engaged/capture/result as given
    auto use = [&](int cand, int eng, bool capture, bool maskOn, bool restored, bool request) {
        put32(b + kBrushCandidateOff, (uint32_t)-1);
        put32(b + kBrushEngagedOff, (uint32_t)-1);
        put32(b + kBrushStateOff, 0);
        pollBrushWatch(t += 100000);
        int drawn = 0;
        for (int s : {1, 2, 2, 2}) {
            put32(b + kBrushStateOff, (uint32_t)s);
            // the first stroke asks for the mask for one tick; the renderer
            // then writes it (or, with capture false, does not)
            put32(b + kBrushRequestOff, s == 2 && drawn == 0 && request ? 1u : 0u);
            if (s == 2) {
                put32(b + kBrushCandidateOff, (uint32_t)cand);
                if (capture && drawn == 1) fillMask(maskOn);
                if (eng >= 0 && drawn == 2) put32(b + kBrushEngagedOff, (uint32_t)eng);
                drawn++;
            }
            pollBrushWatch(t += 100000);
        }
        put32(b + kBrushRequestOff, 0);
        // the evaluation, as main+17B9A0 leaves it
        BrushCover c;
        brushCover(saved, base + kBrushPointsRva, *(uint32_t*)(base + kBrushPointCountRva), g_bwInk, c);
        put32(base + kBrushBitsRva, restored ? 1u : 0u);
        putf(base + kBrushRatioRva, eng >= 0 ? c.ratio : 0.0f);
        uint16_t map = 0x100;
        memcpy(base + kBrushMapRva, &map, 2);
        for (int s : {4, 5, 6}) {
            put32(b + kBrushStateOff, (uint32_t)s);
            pollBrushWatch(t += 100000);
        }
        put32(b + kBrushEngagedOff, (uint32_t)-1);
        put32(b + kBrushStateOff, 0);
        pollBrushWatch(t += 100000);
    };
    // find the last "brush:" verdict by re-running the verdict on the attempt
    // the watch finished: the self-test reads it back from the log line it
    // would write, rebuilt here from g_ba and the snapshot
    auto last = [&](char* out, size_t n) {
        BrushCover c;
        brushCover(g_bwMask, g_bwPts, g_ba.points, g_bwInk, c);
        brushVerdict(out, n, g_ba, c);
    };
    char v[600];
    struct Case {
        const char* what;
        bool maskBefore;  // the saved mask from an earlier capture: filled, or never written
        int cand, eng;
        bool capture, maskOn, restored, request;
        int n, x0, dx, yc;
        const char* want;
        const char* file;  // the image's tag, or nullptr: none written
    } cases[] = {
        {"no target on offer", true, -1, -1, false, true, false, false, 20, 10, 2, 50,
         "no restorable target was on offer", nullptr},
        {"a capture wrote the mask empty", true, 9, -1, true, false, false, true, 20, 40, 2, 50,
         "its mask is EMPTY. A capture wrote it empty.", "empty_mask"},
        {"a capture asked for, the mask stayed empty", false, 9, -1, true, false, false, true, 20,
         40, 2, 50, "its mask is EMPTY. A capture was asked for and the mask stayed empty.",
         "empty_mask"},
        {"no capture seen, the mask stayed empty", false, 9, -1, false, false, false, false, 20, 40,
         2, 50, "its mask is EMPTY. No capture was seen and the mask stayed empty.", "empty_mask"},
        {"stroke beside the mask", false, 9, -1, true, true, false, true, 20, 100, 2, 100,
         "offered, never engaged: no stroke touched its mask (mask 1600 px at x 40-79 y 30-69",
         "not_engaged"},
        // 20 points 2 canvas px apart at y 50: x 35-82 by y 45-55 inked,
        // 40 x 11 = 440 of 1600 mask px = 28%
        {"too little ink", false, 9, 9, true, true, false, true, 20, 40, 2, 50,
         "target 9 NOT RESTORED: 440 of its 1600 mask px inked = 28%, needs 40%", "too_little_ink"},
        // two more rows of points: y 40, 50, 60 cover y 35-65 = 31 rows x 40 = 1240 px = 78%
        {"restored", false, 9, 9, true, true, true, true, 0, 0, 0, 0,
         "target 9 RESTORED: 1240 of its 1600 mask px inked = 78% (needs 40%)", "restored"},
    };
    for (auto& k : cases) {
        if (k.n) {
            points(k.n, k.x0, k.dx, k.yc);
        } else {
            points(0, 0, 0, 0);
            uint8_t* p = base + kBrushPointsRva;
            int i = 0;
            for (int yc : {40, 50, 60})
                for (int j = 0; j < 20; j++, i++) {
                    uint8_t* r = p + (size_t)i * kBrushPointSize;
                    r[0] = 3;
                    putf(r + 4, (float)(2 * (40 + 2 * j)));
                    putf(r + 8, (float)(2 * yc));
                    putf(r + 12, 21.0f);
                }
            put32(base + kBrushPointCountRva, (uint32_t)i);
        }
        fillMask(k.maskBefore);
        int before = g_bwAttempts;
        use(k.cand, k.eng, k.capture, k.maskOn, k.restored, k.request);
        last(v, sizeof(v));
        bool ok = g_bwAttempts == before + 1 && strstr(v, k.want) != nullptr &&
                  !strstr(v, "DISAGREE");
        if (k.file) {
            snprintf(path, sizeof(path), "%s\\brush_watch\\attempt_%03d_%s.bmp", outDir, g_bwAttempts,
                     k.file);
            FILE* f = fopen(path, "rb");
            long size = -1;
            if (f) {
                fseek(f, 0, SEEK_END);
                size = ftell(f);
                fclose(f);
            }
            ok = ok && size == 54 + 2 * kBrushCanvasW * 3 * 2 * kBrushCanvasH;
        }
        fprintf(rep, "%s %s: %s\n", ok ? "ok  " : "FAIL", k.what, v);
        fails += !ok;
    }
    fprintf(rep, "%s (%d failures)\n", fails ? "FAIL" : "PASS", fails);
    fclose(rep);
    return fails ? 1 : 0;
}
