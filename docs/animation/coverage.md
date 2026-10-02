# Coverage: the candidates against the patch

Written by `tools/coverage_report.py` on 2026-10-02 from `sites.csv` (12485 candidates), `classification.csv` and the tables in `src/` (6322 patched ranges).

**Settled: 12485 of 12485 (100%)**: covered 4353, excluded 3905 (library 1626, classified 2222, port-scaled 57), read by hand 4227. **Near a patch, unproven: 0.** **Left: 0** (classified to patch 0, to review 0, never classified 0).

Without the library: settled 10859 of 10859 (100%), 100% with the near ones.

| group | covered | excluded | port | library | read | near | to-patch | review | unclassified | total |
|---|---|---|---|---|---|---|---|---|---|---|
| unattributed | 698 | 601 | 17 | -- | 1866 | -- | -- | -- | -- | 3182 |
| enemies | 706 | 515 | -- | -- | 452 | -- | -- | -- | -- | 1673 |
| objects | 1009 | 112 | 12 | -- | 520 | -- | -- | -- | -- | 1653 |
| library | -- | -- | -- | 1626 | -- | -- | -- | -- | -- | 1626 |
| animals | 521 | 622 | 4 | -- | 314 | -- | -- | -- | -- | 1461 |
| player and weapons | 742 | 127 | 24 | -- | 505 | -- | -- | -- | -- | 1398 |
| ui | 191 | 162 | -- | -- | 192 | -- | -- | -- | -- | 545 |
| materials | 285 | -- | -- | -- | 188 | -- | -- | -- | -- | 473 |
| people | 79 | 63 | -- | -- | 112 | -- | -- | -- | -- | 254 |
| effects | 122 | 20 | -- | -- | 78 | -- | -- | -- | -- | 220 |
| **all** | 4353 | 2222 | 57 | 1626 | 4227 | 0 | 0 | 0 | 0 | 12485 |

Covered, by family: world_anims.h 1939, memory_timers.h 554, world_anims.h literal 539, phase_steps.h 430, action_timers.h 271, decay_factors.h 206, world_anims.h call 178, lea_timers.h 114, integer_skips.h 42, turn_callers.h 38, hoisted_decay.h 9, kAirAccelSites 6, task_waits.h 6, menu_transitions.h 5, menu_transitions.h literal 4, frame_gates.h 3, kStickDriftSites 3, kAirGateSites 2, mode_constants.h 1, kRunPatchRva 1, shadow_mode.h 1, frame_clocks.h tick 1.

Excluded, the classification's reasons (top 8): switch (1035); compared with 4 small values (#0,#1,#2,#3) (430); compared with 3 small values (#0,#1,#2) (138); compared with 5 small values (#0,#1,#2,#3,#4) (90); array index (83); reads feed only arithmetic/calls (76); float stepped with no bound seen (49); dereferenced (39).

Read by hand (`reads.csv`), by verdict: once 1494, stock 1232, fixed 900, follows 601.

Check: of the 1478 candidates `animation_inventory.py` found covered in 2026-09, 1478 remain covered or have documented replacement fixes.

The classification is from 2026-09-18: `review` and `to-patch` shrink only as candidates are read or patched, and a candidate the patch covers some other way (a hook, a skipped call, a retargeted table the rule does not see) still counts as left.
