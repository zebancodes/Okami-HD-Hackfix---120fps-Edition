group objects
lin 566398 | uta9 moving platform: scale its constant upward Y step before the 65-unit height clamp.
lin 5663C3 | uta9 moving platform: scale its downward Y step before clamping to the saved lower height.
lin 566409 | uta9 moving platform: scale the shared half-unit X/Z tracking step; retain the 20-unit spatial dead zone and endpoint clamps.
lin 566725 | uta9 sinking platform: scale its constant two-unit downward Y step while motion advance remains independently time-correct.
count 566801 | uta9 platform sound clock: commit E40 only on stock ticks; all subsequent arithmetic uses the previous value saved in R8D.
notyet 566814 notyet:56683F | uta9 periodic platform sound: force the modulo comparison's not-due branch between stock ticks so a held E40 cannot replay the same sound.
blend 46CF46 | Camera follower: correct the shared 0.2 easing coefficient for both target XYZ and camera XYZ approaches.
blend 46D174 | Camera alternate follower: correct the shared 0.2 easing coefficient for target XYZ, keeping derived orientation spatial.
blend 46D378 | Camera return follower: correct the shared 0.2 target XYZ and camera XY easing coefficient.
blend 46D507 | Camera return follower: correct the separate 0.3 camera-Z easing coefficient.
gatefn 4A8B50 | Coupled model tether: evaluate spring acceleration, velocity friction, sign-crossing stop, position integration, bounds and settlement together at stock cadence.
gatefn 330B90 | Custom motion program: advance its independent 1344 clock, sampled root delta, vertical calibration and dependent path interpolation together at stock cadence.
gatefn 5ADF40 | Paired sliding panels: preserve the complete coupled opening/closing movement, endpoint clamps and saved-flag completion events at stock cadence.
gatefn 5FD490 | Paired sliding panels: preserve both panels' opposing motion, endpoint clamps and saved-flag completion events at stock cadence.
gatefn 221190 | Linked sweeping beam: preserve growth, angle sweep, six-tick sound clock, collision segment and fade state together at stock cadence.
