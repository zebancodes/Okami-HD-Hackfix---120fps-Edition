group objects
gatefn 55D010 | uta1 spring update: the void caller 55CECA ignores the result; the entire previously unpatched spring, damping, integration, countdowns and completion events run at stock cadence.
lin 630BEF | et30 supplemental motion: scale only the steady negative 0.2 blend-weight fade; the event-bit impulse of 1 remains immediate and the event bit is cleared after use.
srcx 630D64 | et30 supplemental motion: advance the independent +125C motion frame by one stock-frame fraction while preserving the shared XMM9 one used by the duration limit.
srcroot 2118DB | cObjSimpleEmRoll sustained scale growth: use the per-tick root of 1.33 when B6AC5C is active; preserve the shared source constant.
srcroot 2E4FE8 | et0f dismissal: compose the 0.1 alpha decay across fractional stock ticks until the state-one reset.
pre 4F2A23 | ut25 platform passenger: scale the complete +1150 platform velocity before adding it to player Y, matching platform integration.
pre 4F1EAF | ut25 rising platform state 7: scale acceleration +115C before adding it to stock-unit velocity +1150; retain the velocity clamps.
pre 4F21B2 | ut25 rising platform state 11: scale acceleration +115C before adding it to stock-unit velocity +1150; retain the velocity clamps.
pre 4F242F | ut25 descending platform state 15: scale acceleration +115C before adding it to stock-unit velocity +1150; retain the velocity clamps.
pre 4F2552 | ut25 descending platform state 17: scale acceleration +115C before adding it to stock-unit velocity +1150; retain the velocity clamps.
src 4F1EFE | ut25 state 7: integrate platform Y with a fraction of the stock-unit +1150 velocity.
src 4F2204 | ut25 state 11: integrate platform Y with a fraction of the stock-unit +1150 velocity.
src 4F2481 | ut25 state 15: integrate platform Y with a fraction of the stock-unit +1150 velocity.
src 4F25A4 | ut25 state 17: integrate platform Y with a fraction of the stock-unit +1150 velocity.
count 21335B float | ut01 animation restart delay: advance the +1090 stock-frame counter once per stock tick; +1094 clears on the completion event and action starts reset the counter.
lin 57F597 | ut48 raised platform: rise one unit per stock tick, clamped to +E14 plus 100.
lin 57F5D4 | ut48 lowered platform: descend one unit per stock tick, clamped to +E14.
lin 21CBDF | ut49 platform restoration: rise 1.5 units per stock tick until the +E14 height clamp.
