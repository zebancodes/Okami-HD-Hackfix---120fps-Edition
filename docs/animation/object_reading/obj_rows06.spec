group objects
# utb7 update 570890: state 7's +E48 rise already has a phase_steps.h row,
# so the persistent value stays in stock units while its 2DA410 move is
# scaled at the call. State 9 has a separate literal vertical rise.
callscale 571197 (0x2DA410,"xmm1") | utb7 state 7: scale only the caller-local distance passed to 2DA410, keeping +E48 stock-valued
lin 5712C2 | utb7 state 9: position y rises by one stock unit each tick until the +D2C countdown ends
