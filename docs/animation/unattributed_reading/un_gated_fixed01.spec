# Candidates inside functions that a gatefn/gate0 row runs only on stock ticks (2026-09-30):
# every step in them already runs once a stock tick, at stock values.
fixed | 476030 (camera shake) is a gatefn row: its amplitude decays, phase advances and wraps and its integer durations run once a stock tick. | 476059 476079 4760A4 4760C4 4760CC
fixed | 5541D0 (periodic encounter controller) is a gatefn row: its stage clock, threshold events and spawn delays run once a stock tick. | 5542AA 554340 554343 554346
fixed | 4AF910 is a gatefn row: its counters run once a stock tick. | 4AF991 4AF9B9
fixed | 48DE00 is a gatefn row: its counter and the value it derives run once a stock tick. | 48DE43 48DE49
fixed | 498D00 is a gatefn row: its float steps run once a stock tick. | 498D3C 498D49
fixed | 57E020 is a gatefn row: its decay runs once a stock tick. | 57E437
fixed | 2DC3B0 is a gatefn row: its steps and decay run once a stock tick. | 2DC472 2DC565
fixed | 1C8D80 is a gatefn row (menu group): its counter runs once a stock tick. | 1C8DC5
fixed | 18FF60 is a gate0 row (effect group): between stock ticks it returns at once, so its counter runs once a stock tick. | 18FF7F
