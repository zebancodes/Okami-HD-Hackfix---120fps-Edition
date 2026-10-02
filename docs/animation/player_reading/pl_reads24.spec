stock | wp47 (39B950): +E10/+E18 multiply the normalized origin-to-target vector by the fixed +E28 length to construct the collision-probe endpoint passed to 2DC7B0; these are geometry, not displacement | 39BA24 39BA28
fixed | wp47 (39C0B0): +E18 is a continuously updated collision radius; scale its +3/-6 ramp steps while preserving the 53/21 spatial thresholds | 39C3BC 39C3F4
fixed | wp47 (39C540): +E18 is a continuously updated collision radius; scale its +3/-6 ramp steps while preserving the 53/21 spatial thresholds | 39C79E 39C832
fixed | wp47 (39C540): +E3C is a 10-tick terminal-state countdown; count-gate its decrement so the zero test transitions on stock cadence | 39C8C5
once | wp49 (39D600): +E36 increments only during the state-0 initialization path; it is a one-shot state/event count, not elapsed time | 39D656
fixed | wp49 (39D600): +B0/+B8 receive random perturbations every update; scale each draw before accumulation so higher update rates produce proportionally smaller steps | 39D69F 39D6D1 39D76B
once | wp51 (39E020): +E44 loses 60 times byte +109B when the bit-25 hit flag is present; this is event/damage magnitude, not elapsed ticks | 39E07F
once | wp51 (39E020): +E44 loses 600 once when +1088 reports its event; this is event/damage magnitude, not a clock | 39E0E3
