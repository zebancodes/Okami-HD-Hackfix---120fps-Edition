group objects
gatefn 33DE40 | cCarryObj floating state: run the coupled height-selected acceleration, velocity clamp/damping, position integration, and collision transition together at stock cadence; motion selection does not advance its animation clock.
gatefn 4990A0 | cItemObj floating state: run the coupled height-selected acceleration, velocity clamp/damping, position integration, and collision transition together at stock cadence.
gatefn 498D00 | cItemObj falling state: keep the coupled XYZ integration, gravity, contact checks, impact restitution, and state transitions together at stock cadence.
pre 2172B1 | ut12 falling phase: add the original +E54 vertical velocity divided by N to position; the ground-contact clamp and phase transition remain immediate.
lin 217360 | ut12 falling phase: subtract 0.5/N from the original vertical velocity per tick.
count 2310F0 | utd7 trailing position history: advance its sixty-entry sampling cursor once per stock tick; held ticks refresh the current slot.
lin 231157 | utd7 exit growth: shared 0.05 scale increment is divided by N before all three scale channels and the 1.6 clamp.
