group objects
# Shared scalar rates in material scroll and alpha fade loops.
lin 2F3F56 | et6f: scale the 0.03 U step shared by its three materials
lin 5A5B9B | utce: scale the 0.1 alpha step shared by four materials
lin 32CA91 | hm5d: scale the 0.05 alpha step in both branches
lin 32D132 | hm5e: scale the 0.05 alpha step in both branches

# A target alpha is approached by 0.2 on either of two paths.
blend 57BC2D | ut2c: compound the first material alpha approach
blend 57BC46 | ut2c: compound the second material alpha approach

# Callers of the em6a/es18 U/V wrap helpers make their dynamic step from
# a random scalar and this 0.03 literal, which is shared by U and V.
lin 2D4A56 | em6a: scale the random U/V scroll step before the helper call
lin 35E637 | es18: scale the random U/V scroll step before both helper calls

# ut52 places its current material scroll step in +1078 each tick. Scale it
# on both the plus and minus paths, leaving the material value itself intact.
pre 21DF5F | ut52 material 1 U: scale the +1078 step before addition
src 21DF91 | ut52 material 0 U: scale the +1078 step before subtraction
