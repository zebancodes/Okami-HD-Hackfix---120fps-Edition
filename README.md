Okami HD High-FPS Patch
=======================

Unlocks the Steam PC release of Okami HD (大神绝景版) from its 30 fps
presentation lock, with an in-game hotkey to switch back to stock 30 fps
semantics on demand. Built and tested against build 6990973 (buildid from
`appmanifest_587620.acf`, latest as of 2026-08).

Features
--------

- 60 fps gameplay: the game's frame pipeline runs at a smooth 60 Hz with the
  engine's own 60 fps configuration (fps=60, timeScale=0.5), keeping game
  speed at real-time.
- 30 fps stock mode via hotkey (**F9**): restores the unpatched engine
  semantics instantly, in-game, without restarting. Required for game
  actions that are tuned for 30 fps and break at 60 fps (most notably the
  wall jump - see below).
- Runtime-only patch: nothing on disk is modified, Steam validation is
  unaffected, uninstall = delete the two files.

Why a hotkey toggle is needed
-----------------------------

The engine's 60 fps path is real and mostly complete - key-event windows,
animation keyframe durations, movement speeds, the body-command cadence and
the animation frame->time conversions are all correctly compensated at
60 fps, and normal running/jumping/combat behaves correctly.

One action is **not**: the wall jump (壁ジャンプ / 蹬墙二段跳). At 60 fps it
plays its effects, rumble and spin animation but applies **no launch
velocity** - the character spins in place and gains no height. Evidence
points to the action's launch-velocity data table (parsed at runtime from
the player motion data `data_pc/pl/pl00.dat`) resolving to zero on the
60 fps index, while the remainder of the engine compensates correctly.

Because the underlying data is encrypted (M2 cipher) and the exact zero
index has not yet been pinned down, the practical solution is a **live
switch**: play at 60 fps for the smooth experience, tap **F9** when a wall
jump is needed and the game instantly returns to stock 30 fps semantics
(where every action works exactly like the unpatched game). The switch is
instant; no reload, no restart.

How the 30 fps lock works (reverse-engineered)
----------------------------------------------

- The game boots with its "PS2 display mode" flag enabled, which drives the
  whole presentation pipeline to 30 fps.
- Every frame, `flower_tick` (main.dll) writes the engine's frame
  configuration: `fps = 30`, `timeScale = 1.0` unless the config byte at
  `main.dll+0xB6AC45` equals `1`, in which case it writes `fps = 60`,
  `timeScale = 0.5` (the engine's native 60 fps mode).
- The DXGI swap chain is created for a **30 Hz** fullscreen mode on a
  60 Hz display, so `IDXGISwapChain::Present(1, 0)` blocks 33.3 ms per
  call. The game host loop only drains `flower_tick()`, so the swap chain's
  present cadence *is* the game step rate: 30 steps/second.

Implementing 60 fps
-------------------

The patch applies four coordinated fixes at runtime (in memory only):

1. **Disable PS2 display mode** - calls the engine's own
   `SetPs2DispMode(false)` (`flower_kernel.dll+0x164F0`) once the engine
   DLLs are loaded.

2. **Pin the engine's 60 fps configuration byte** (`main.dll+0xB6AC45` ->
   `1`). flower_tick only writes the 60 fps settings while it reads 1. The
   game's system-state machine rewrites the byte to 2 (30 fps semantics)
   throughout gameplay, so the patch:
   - rewrites the immediate operand of all four `mov byte ptr [mode], 2`
     sites in main.dll (RVAs 0x14A051, 0x14A1F6, 0x14A64C, 0x608F4E) to 1,
     so the engine's own writers emit the 60 fps configuration;
   - continuously re-asserts the byte as a safety net.

3. **Decouple the game step rate from the swap chain's 30 Hz mode** - hook
   `IDXGISwapChain::Present` (vtable slot 8 of the swap chain object global
   at `flower_kernel.dll+0x11C290`): present asynchronously (no vblank
   wait) and enforce a fixed 16.667 ms game-step grid with
   `QueryPerformanceCounter` instead. The hook lives in the shared class
   vtable, so resolution changes / swap chain recreation keep it active.

4. **Set the config refresh rate to 60** via the engine's own
   `SystemConfig::SetRefleshRate(60)` (`main.dll+0x162E40`).

Together these make the game run at 60 steps/s with the engine's correct
60 fps frame configuration, so game time stays at real speed while
animation and input run twice as smoothly.

Hotkey toggle (F9)
------------------

Press **F9** in-game to switch between the two modes live:

| Mode  | Engine config          | Step rate | Behavior |
|-------|------------------------|-----------|----------|
| 60 fps (default) | fps=60, timeScale=0.5 (mode byte pinned to 1), PS2 disp off | 16.667 ms (async present + own pacing) | smooth, 55-60 fps |
| 30 fps | fps=30, timeScale=1.0 (mode byte 2), PS2 disp on | 33.3 ms (stock vsync present) | stock semantics: wall jump and all 30 fps-tuned actions work |

Switching to 30 fps:
- restores the swap chain's `Present` vtable slot to the original
  implementation (the 30 Hz present block returns, so the step rate drops
  to 30/s);
- restores the mode-writer immediates from 1 back to 2 and re-asserts
  mode=2, so flower_tick emits the 30 fps configuration;
- re-enables PS2 display mode.

Switching back to 60 fps re-applies all four fixes. The switch takes effect
on the next frame; a beep plays and the choice is logged to
`okami_hackfix.log`.

The key is polled with `GetAsyncKeyState` (edge-triggered) from the patch's
own thread, so it works without any window or message loop and is
independent of focus.

Usage
-----

Windows:

- Copy `DINPUT8.dll` and `okami.ini` into the game folder
  (`<Steam>\steamapps\common\Okami\`), next to `okami.exe`, then start the
  game from Steam.
- Press **F9** in-game to toggle 60/30 fps. The log file `okami_hackfix.log`
  is written next to the game and reports each switch
  (`toggle -> 60/30 fps mode`) plus `status:` lines
  with the measured frame rate and engine config (`cfg fps` / `tscale`).
- To uninstall, delete `DINPUT8.dll`, `okami.ini` and `okami_hackfix.log`.

Why `DINPUT8.dll`? `flower_kernel.dll` imports `DirectInput8Create` by
name, so a proxy DLL placed in the game folder is loaded by the system
loader and forwards to the real `%SystemRoot%\System32\dinput8.dll` while
applying the runtime patches in `DllMain`/a watcher thread. Same technique
as the DGS (The Great Ace Attorney) high-FPS patch this project is modeled
on.

Build
-----

Requires [pixi](https://pixi.sh) (Windows only; conda-forge MinGW toolchain):

    pixi run -e build configure
    pixi run -e build build
    pixi run -e build deploy    # copies DINPUT8.dll + okami.ini into the game

Output lands in `.build/bin/`. `deploy` copies into
`D:\SteamLibrary\steamapps\common\Okami` by default (edit `tools/deploy.py`
if your library lives elsewhere).

A tracing variant (per-frame instrumentation for reverse engineering) can
be built with `-DOKAMI_TRACE=ON` into `.build-trace`.

Notes / limitations
-------------------

- Frame pacing is a fixed 16.667 ms step enforced by the patch. A machine
  that cannot sustain 60 fps will show dropped steps rather than smooth
  30 fps; use the F9 toggle to drop to 30 fps on weak hardware.
- Presentation at 60 fps is asynchronous (vsync bypassed) to decouple from
  the 30 Hz swap mode; on very fast-moving scenes a tear line may
  occasionally be visible (30 fps mode is fully vsync'd).
- The wall jump only works reliably in 30 fps mode. All other movement,
  jumps and actions work in both modes.

Project layout
--------------

    pixi.toml               pixi workspace, Windows-only build env + tasks
    CMakeLists.txt          Ninja build of the proxy DLL (+ optional trace)
    src/dinput8_proxy.cpp   proxy + runtime patch engine (60/30 fps toggle)
    src/dinput8_proxy.def   DLL exports (DirectInput8Create)
    src/mingw_guard_fix.c   MinGW CRT stack-canary workaround
    tools/                  RE + analysis scripts (pefile/capstone), deploy
    okami.ini               notes; the hotkey is F9

License: MIT (see LICENSE).
