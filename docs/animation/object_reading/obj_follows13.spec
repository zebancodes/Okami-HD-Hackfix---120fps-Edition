follows | et2e 2EAD00: the patched 2EAD28 pre-add scales the selected max of 0.02 and 2.1 minus caller target before B4 accumulation; 2EAD4D only wraps that same phase | 2EAD33 2EAD4D
follows | et2f 62E0B0: patched 62E117 scales the selected +1 or -0.2 1174 step and 62E284 scales only the +1170 phase add; the 1174 clamp and both final stores consume those results | 62E125 62E13F 62E29B
follows | cKiType000 to cKiType003 209FD0: patched 20A044 supplies the 0.06 decrease for either one or two D2C subtractions | 20A059 20A069
follows | ut05 214690: patched +2 and -2 source operands at 2146CA and 214753 respectively feed the two 10A8 stores | 2146D5 214766
follows | utbb 22BE90: patched signed 0.05 sources at 22BEAB and 22BECB feed the D2C add; the later store clamps the same result to zero to one | 22BEDE 22BEF4
follows | cTubomi et40/44/45 2E0FE0: patched 2E109C adds the scaled 0.5585054 step to submodel three E4 before wrapping at 13F2E0 | 2E10C3
follows | ut86 225F90 state eight: patched 22619F provides the 0.02 D2C decrease until zero switches E36 to nine | 2261A7
follows | ut92 228170: patched 228190 supplies the 0.05 decrement once per subrecord in the loop; each 5C store uses that source and clamps negative results to zero | 2281AC
follows | et24 2E83E0: patched 2E8484 scales the whole 0.02 random component plus mutable 0.05 base before the 1084 phase add | 2E848F
follows | et44 and et45 2ED7E0 and 2ED8B0: patched angular operands at 2ED800 and 2ED8D0 feed the submodel-three E4 stores after the angle wrap | 2ED81D 2ED8ED
follows | utd1 230400: patched 23046F supplies the shared 0.0122173 return-to-zero step to both signs of each of the four B4 angle updates | 23050A
