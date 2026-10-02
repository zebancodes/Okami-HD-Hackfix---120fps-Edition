# Okami HD High-FPS Patch

Runs the Steam release of Okami HD at 60 or 120 fps instead of its fixed 30,
with the game's timing kept intact: Amaterasu, enemies, effects, menus and
timers move at the same real-time speed as in the original game. **F9** cycles
30 / 60 / 120 fps in game; 30 is the game as shipped.

It is a `DINPUT8.dll` proxy that patches the game in memory when it starts.
Nothing on disk is changed. Made for Steam build 6990973.

**To play:** copy `DINPUT8.dll` from the release zip next to `okami.exe`.
[release/README.txt](release/README.txt) covers settings, other mods and
Steam Deck / Proton.

**NOTICES:** if Microsoft Defender detects it as a virus, it is a false positive, you may need to restore the DLL if Defender quarantines it.
The .ini also has some features that may not work, that are a side WIP, like draw distance etc...

☕Like the work? Consider buying me a coffee! ko-fi.com/zebancodes ☕

**Bugs:** If you happen to notice any bugs, please report them in the issues tab and I'll take a look when I can!

## Design strategy

The engine has a 60 fps mode of its own, which the stock game uses briefly
during the title sequence: one byte makes it tick at 60 Hz with a time scale
of 0.5. The original patch was built on that mode, and 120 fps extends it to a
time scale of 0.25. The mode was never finished, though. The port scales
physics by the time scale but leaves most durations and per-tick steps in
30 fps units, so timers, effects, fades and many animations run twice as fast
at 60 and four times as fast at 120. Most of this project is fixing that,
under a few rules:

- **Stock is the reference, per context.** Each rate is matched to what the
  unmodified game does in the same place: 30 Hz in play, 60 Hz in some menus.
  N = fps / that rate.
- **Scale the step, never the state.** Stored values stay in stock units;
  only how they are applied changes (`pos += vel / N`, `vel *= k^(1/N)`), so
  any other code reading them still sees stock numbers.
- **Integers are skipped, not scaled.** Counters, random draws and sign flips
  advance only on stock ticks, which is exactly stock behaviour with no
  rounding.
- **Nothing is patched on a guess.** A static census of the game code found
  12,485 places that might hold a per-tick quantity. Each one is patched, or
  excluded with a written reason, in `docs/animation`.
- **Generated and proven.** Patch tables are generated from the game binary,
  never typed by hand. Each generator proves its sites against the code
  (control flow, register liveness, flags) and writes nothing on a mismatch.
  An offline suite emulates the patched code against the original at N = 1, 2
  and 4, and is itself checked by injecting faults it must catch.
- **Install once, switch by data.** All code is written at start-up and F9
  changes only data. At N = 1 every patch computes exactly what the original
  did, so 30 fps mode behaves as the unmodified game.
- **Fail safe.** Engine symbols are resolved by name and every byte is
  checked before it is written. On a game build it does not recognise, the
  patch changes nothing and says so on screen.
- **Measure, don't judge by feel.** A scripted input harness and the log's
  own measurements (movement speed, jump height, loading screens, day clock,
  menu transitions) compare each mode with stock.

## Building

Windows, CMake and Ninja with LLVM clang (or MinGW through pixi:
`pixi run -e build build`):

    cmake --preset clang
    cmake --build --preset clang

The DLL is written to `.build/bin/dinput8.dll`, and
`python tools/make_release.py` packages it with the player readme.
`bash tools/run_suite.sh <seed>` runs the offline suite; it needs Python with
capstone, pefile and unicorn, and reads the installed game's `main.dll`.

## Repository

- `src/`: the proxy (`dinput8_proxy.cpp`) and the generated patch tables.
- `tools/`: analysis, the generators (`gen_*.py`), the verifiers
  (`verify_*.py`, `survey_*.py`, `check_patch_sites.py`) and packaging.
- `docs/technical-notes.md`: the patch fix by fix, with the measurements
  behind each one.
- `docs/animation/`: the animation work: the inventory, the census and the
  per-site reading records.
- `release/`: the player readme and settings file that go in the zip.

## Thanks

This project grew out of Enaium's Okami HD high-FPS patch. Enaium worked out what locks the game to 30 fps (the PS2
display mode, and a 30 Hz present that paces the whole engine), found the
engine's own 60 fps mode and the byte that selects it, and wrote the
`DINPUT8.dll` proxy, the frame pacing, the F9 toggle, the build setup and the
first reverse-engineering scripts. Everything here stands on that work.
Thank you, Enaium.

## License

MIT; see [LICENSE](LICENSE).
