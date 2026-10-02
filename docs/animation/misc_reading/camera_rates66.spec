group objects
callscale 482C8C | Camera pitch approach: scale the angular limit; its XMM2 coefficient comes from the already time-correct mode table 7A82D0 minus one.
callscale 482CB5 | Camera pitch approach: scale the angular limit while retaining the mode-table coefficient already corrected by mode_constants.
callblend 482D3F | Camera pitch approach: correct the constant 0.08 approach coefficient and the constant angular limit together.
callblend 482D8B | Camera pitch approach: correct the repeated positive-error approach's constant coefficient and limit.
callblend 482DCE | Camera pitch approach: correct the constant-coefficient ground-height branch and angular limit.
callblend 482E28 | Camera pitch approach: correct the constant-coefficient pitch branch and angular limit.
root 482E83 | Camera pitch velocity: take the stock-period root of the shared 0.98 damping factor used by all three magnitude thresholds.
callblend 482F1D | Camera pitch approach: correct the first magnitude-threshold approach and its angular limit.
callblend 482F4C | Camera pitch approach: correct the additional positive-error approach and its angular limit.
callblend 482F84 | Camera pitch approach: correct the second magnitude-threshold approach and its angular limit.
callblend 482FB3 | Camera pitch approach: correct the additional second-threshold approach and its angular limit.
callscale 482FF1 | Camera pitch approach: correct the angular cap only; the coefficient is the already time-correct 7A82D0 mode-table value minus one.
callscale 48306C | Camera state-2 pitch approach: correct the angular cap only, retaining the already corrected mode-table coefficient.
callscale 4830DF | Camera state-5 pitch approach: correct the angular cap only, retaining the already corrected mode-table coefficient.
callscale 483137 | Camera state-7/11 pitch approach: correct the angular cap only, retaining the already corrected 7A82D8 mode-table coefficient.
callscale 483189 | Camera scripted pitch approach: correct the angular cap only, retaining the already corrected mode-table coefficient.
gatefn 475E60 | Camera transition program: advance the 32-sample cursor, accumulated weight, seven pose approaches and dependent derived camera pose together at stock cadence.
lin 36763A | cKiType fading appearance: scale the shared 0.2 alpha increment used by D20/D24/D28 before the three unit clamps.

