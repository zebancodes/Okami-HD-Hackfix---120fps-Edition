group objects
count 22FF88 | utd1: pace the recurring three-tick effect counter.
notyetneg 22FF8E 0x22FFBF | utd1: the effect compares old CL with one; take its JLE hold path between stock ticks to prevent repeated spawns.
count 509D64 | ut1b shake: hold the sampled X position between stock ticks.
count 509D84 | ut1b shake: hold the sampled Y position between stock ticks.
count 509DA5 | ut1b shake: hold the sampled Z position between stock ticks.
count 509DAA | ut1b shake: pace its ten-tick duration together with the three position commits and preserve the unfinished JNE branch.
group menu
gatefn 15F000 | Held-input slider: run acceleration counters, quantized volume increments, clamp resets and repeat sound together at stock cadence; all three callers discard the result.
src 40CC05 | Page transition: scale the complete spacing/duration X step on the first page.
src 40CC30 | Page transition: scale the complete spacing/duration X step on the second page.
group actor
gatefn 444DE0 | Sound instance controller: run the pre-start delay, play age and state transitions together at stock cadence; callers discard the result and mixer maintenance stays in 455A60.
count 455AB6 | Sound mixer: pace each active slot's age while middleware status and maintenance continue each update.
count 455B13 | Sound mixer: commit the clamped integer fade at stock cadence while the middleware volume application remains live.
