group actor
count 2105D8 | Resource barrier: pace its four-consecutive-idle-update counter; any outstanding record still resets the barrier immediately.
count 2106B1 | Alternate resource barrier: pace the six-consecutive-idle-update counter and retain immediate resets for outstanding records.
count 210BB9 | Spawn manager: hold the retry cooldown word store; the pre-decrement zero test selects work and AX is discarded in the epilogue.
count 238BDC (0x238BD2,0x238BDF,(0x238BD2,0x238BD8,0x238BDA,0x238BDC),None) | Shared actor death delay: gate the register decrement and preserve JNE on held ticks before its completion callback.
count 23AED5 | Battle manager: pace the +232 wait; completion clears both the wait and its +234 active state before calling the next stage.
count 23D789 | Battle manager: pace the active battle elapsed-time counter while retaining its pause and inactive guards.
count 303B7C | Shared actor fade: pace the byte duration from which D20 XYZ alpha is freshly calculated each update.
count 30417B | Shared actor visibility fade: commit the clamped two-unit alpha step at stock cadence before byte quantization can lose a fractional step.
count 304181 | Shared actor visibility fade: commit the duplicate material alpha byte at the same cadence as its +1191 source.
count 305ABA | Shared actor child fade: commit the clamped eight-unit alpha step at stock cadence; later visibility checks reload the stored byte.
count 309104 | Shared actor positional sound: pace the three-tick E3E interval clock.
notyet 30910C 0x309147 | Suppress the corresponding modulo-three sound equality while the E3E clock is held.
count 309257 | Alternate positional sound: pace its three-tick E3E interval clock.
notyet 30925F 0x30929A | Suppress the alternate modulo-three sound equality while the E3E clock is held.
count 3112CB | Linked-motion actor: pace the sixteen-update launch delay; motion advancement remains independently time corrected.
count 311A67 | Linked-motion actor: E37 values two through forty-two are a forty-update wait, so hold this state-counter store between stock ticks.
count 311C01 | Linked-motion actor: pace the forty-five-tick recurring sound interval; firing resets the clock to zero immediately.
count 3121C1 | Alternate linked-motion actor: pace its forty-five-tick recurring sound interval with the same immediate clock reset.
gatefn 311FA0 | Linked-motion actor: the closed view-distance-gated periodic-effect sampler has one direct caller, 311EC3, which discards its result. Run its counter, old-counter threshold and reset together at stock cadence.
count 31331B | Resource manager: pace the three-consecutive-update stability barrier after the bounded record scan.
count 313731 | Resource record: pace the eight-tick retry cooldown; its continuation tests the preserved old clock, so a held positive clock cannot perform the retry.
lin 316ACB | Shared actor: scale the continuous one-unit sinking movement under its active flags.
count 316FEF | Appearance effect record: pace the selected byte hold delay; the old-zero branch resets its state and computed AL is discarded.
