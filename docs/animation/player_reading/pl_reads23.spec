# Completed six-function batch.
fixed | pl00 all-slot auxiliary update (3CCC50): +1470/+1474/+1478 position gains s of persistent stock-valued +14F0/+14F4/+14F8 velocity, then vertical velocity loses 0.6 on the last tick of each stock period | 3CCDCD 3CCDE2 3CCDEB 3CCDF4
fixed | pl00 all-slot auxiliary update (3CCC50): +15B8[slot] lifetime advances on stock ticks and its old-value zero transition is held between them | 3CCE52

stock | pl00 state handler 3BDCB0: +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3BDD19
fixed | pl00 state handler 3BDCB0, sub-state 3: +E3C advances on stock ticks through memory_timers.h and +F80 gains the phase_steps.h-scaled 0.5 step | 3BDDF2 3BDE09
left | pl00 state handler 3BDCB0, sub-state 3: vertical speed +E54 conditionally loses 0.119 or gains 0.255 each update around a global threshold; its two predecessor steps at 3BDE41/3BDE4B still need an explicit rate conversion | 3BDE53
fixed | pl00 state handler 3BDCB0, sub-state 1: +E3C advances on stock ticks through memory_timers.h and +F80 gains the phase_steps.h-scaled 0.5 step | 3BE196 3BE1AD
fixed | pl00 state handler 3BDCB0, sub-state 1: position.y gains s of 0.68 and vertical speed +E54 gains s of 0.306 through lin 3BE1E7/3BE1FC | 3BE1EF 3BE204
stock | pl00 state handler 3BDCB0: +E48 damping uses port mode table 7A8218, already rewritten for the current rate by mode_constants.h | 3BE22A
stock | pl00 state handler 3BDCB0: the input-built acceleration added to +E48 already carries the port time scale | 3BE279
stock | pl00 state handler 3BDCB0: the rotated +E48 vector is already a current-rate displacement when added to position.x/y/z | 3BE2E1 3BE2F7 3BE30E

follows | pl00 state 3C3C70: after motion advance refreshes the pose, submodel 0 y gets the full sin(+E3C degrees) x 0.8 pose offset; its phase is paced by count 3C3F3B | 3C3F36
fixed | pl00 state 3C3C70: +E3C's eight-degree sine-wobble phase step advances once per stock tick | 3C3F3B
stock | pl00 state 3C3C70: +E48 and +B8 damping use port mode tables 7A8160 and 7A8240, already rewritten for the current rate by mode_constants.h | 3C3FED 3C4012
stock | pl00 state 3C3C70: both acceleration terms added to +E48 already carry the port time scale | 3C402E 3C405C
fixed | pl00 state 3C3C70: both 2DA510 approaches use caller table factors converted by turn_callers.h | 3C4092 3C40C8
fixed | pl00 state 3C3C70: +10B0/+10B8 gain s of ground-vector acceleration and position gains s of the resulting stock-valued velocities; their subsequent 0.9 damping is already rewritten by decay_factors.h | 3C412A 3C4148 3C415B 3C4173 3C4188 3C41A0

stock | pl00 state 3CC270: +B8 damping uses port mode table 7A8240, already rewritten for the current rate by mode_constants.h | 3CC2AB
once | pl00 state 3CC270, state-start path: +B4 turns toward the linked actor with a pi-radian limit once after +E36 advances immediately to 1 | 3CC401
fixed | pl00 state 3CC270: persistent +E48 damping by 0.4 runs once per stock tick through count 3CC466 | 3CC466
stock | pl00 state 3CC270: root-motion +EC8 gains +E48, already a displacement for the current-rate tick, immediately before 2DA3D0 applies it | 3CC481

fixed | pl00 timer helper 3CD1A0: both +115C countdown paths advance on stock ticks and hold their old-value zero transitions between them | 3CD1DF 3CD2D9

fixed | pl00 sequencer 3CD460: +114A advances on stock ticks; its first-tick and two helper-derived threshold effects are held between them | 3CD583
fixed | pl00 sequencer 3CD460: +1150 advances on stock ticks; its every-eighth-tick effect and threshold-path reset are held between them | 3CD5CF

# Dormant sibling of 3CCC50 (3CCEA0).
# It has no static call/data-pointer/export path in this build. If a future caller is
# introduced, these verdicts assume the helper remains a per-frame single-slot update.
fixed | pl00 dormant single-slot auxiliary update (3CCEA0): +1470/+1474/+1478 position gains s of persistent stock-valued +14F0/+14F4/+14F8 velocity, then vertical velocity loses 0.6 on the last tick of each stock period | 3CCFCE 3CCFE8 3CCFF2 3CCFFC
fixed | pl00 dormant single-slot auxiliary update (3CCEA0): +15B8[slot] lifetime advances on stock ticks and its old-value zero transition is held between them | 3CD076
