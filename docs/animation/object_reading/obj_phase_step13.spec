group objects
pre 2EAD28 | et2e 2EAD00: scale xmm2 after max of 0.02 and 2.1 minus the caller target, immediately before adding it to persistent B4 phase
pre 62E117 | et2f 62E0B0: scale the selected +1 or -0.2 change to +1174 before adding it, preserving the zero-to-one clamp
src 62E284 | et2f 62E0B0: scale xmm9 only in the +1170 interpolation phase add, preserving its separate uses as reference value and endpoint threshold
lin 20A044 | cKiType000 to cKiType003 shared update: scale the 0.06 D2C decrease, which can be applied twice when E79 low nibble is F
lin 2146CA | ut05 214690: scale the +2 change to the 10A8 state value before its zero threshold
lin 214753 | ut05 214690: scale the -2 change to the 10A8 state value before its -12 threshold
lin 22BEAB | utbb 22BE90: scale the -0.05 D2C fade when 115A is set
lin 22BECB | utbb 22BE90: scale the +0.05 D2C fade when E35 selects phases one to three
lin 2E109C | cTubomi et40/44/45 2E0FE0: scale the 0.5585054 angular step before the submodel-three E4 wrap
