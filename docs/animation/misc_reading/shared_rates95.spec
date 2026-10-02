group actor
blend 3048F3 | Shared actor tracking: correct the 0.05 X approach toward the fresh linked-model target.
blend 304915 | Shared actor tracking: correct the corresponding 0.05 Z approach.
blend 30D468 | Shared actor return state: correct its repeated 0.05 X-position approach toward the stored target.
blend 30D48C | Shared actor return state: correct its repeated 0.05 Z-position approach.
gatefn 3D3400 | Eight-slot ballistic effect controller: advance each slot's position, acceleration, completion test and age together at stock cadence. Its sole direct caller is the frame dispatcher and uses only state mutations.
group menu
pre 40CEAC | UI page transition: scale the completed spacing-over-duration step before adding it to the first row's X position.
pre 40CED3 | UI page transition: scale the corresponding second-row X step after division; the shared spacing constant keeps its original value.
count 4385A2 | Confirmation menu: pace the fifteen-tick exit delay; selection commands remain on their input-event paths.
