fixed | et6f 2F3F40: one scaled 0.03 step in xmm6 feeds the three material U additions in the loop | 2F3F86
fixed | utce 5A5AD0: the scaled 0.1 in xmm7 feeds each material +5C subtraction in the four-material loop | 5A5BCD
fixed | hm5d 32CA40 and hm5e 32D0C0: each scaled 0.05 in xmm6 feeds both increasing and decreasing material alpha paths | 32CAE9 32CB73 32CBA4 32D18A 32D214 32D245
fixed | ut2c 57BA60: each branch uses its own compounded 0.2 approach to material alpha +5C | 57BC3A 57BC53
fixed | em6a 2D48E0 and es18 35E5F0: their random U/V steps use a scaled 0.03 before calling the material wrap helpers | 238711 238716 35E571 35E576
follows | em6a/es18 U/V helper: these stores only normalize a U/V phase by an integral unit after adding the scaled random step | 238729 238749 238769 23877C 35E589 35E5A9 35E5C9 35E5DC
fixed | ut52 21DF20: both +/- paths scale the current +1078 material U step before its addition or subtraction | 21DF67 21DF9C
follows | ut52 21DF20: these stores only normalize the already-scaled U phase by a whole unit | 21DF7D 21DFB2
follows | esp20 1A6C60: material 0 V at 1A6EBF only subtracts the whole-unit period after the scaled phase crosses its +2 bound | 1A6EBF
