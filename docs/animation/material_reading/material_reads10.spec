fixed | cDigObj 50E960: the double 0.005 is scaled before addition to the promoted float U phase and the result is narrowed once before storing | 50E98F
follows | cDigObj 50E960: this store only subtracts the whole-unit U wrap after the scaled double addition crosses 1 | 50E99A
fixed | et8d 5486C0: the double 0.0025 is scaled before addition to the promoted float U phase and the result is narrowed once before storing | 5486FA
follows | et8d 5486C0: this store only subtracts the whole-unit U wrap after the scaled double addition crosses 1 | 548705
fixed | cHumanChap 3107E0 is a jump alias for 3107F0, whose 3108D6 add is already scaled by phase_steps.h | 3108E5
