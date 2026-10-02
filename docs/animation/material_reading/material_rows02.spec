group objects
# et08 slot update 2E2FA0: six material V offsets take a fixed signed step,
# then wrap back into [-1,1] if necessary. Only the initial step is a rate.
lin 2E2FBD | et08 material 0 V: scale the -0.03 scroll step before the wrap checks
lin 2E300D | et08 material 1 V: scale the -0.03 scroll step
lin 2E304D | et08 material 3 V: scale the -0.06 scroll step
lin 2E308D | et08 material 5 V: scale the -0.06 scroll step
lin 2E30CD | et08 material 7 V: scale the -0.03 scroll step
lin 2E310D | et08 material 8 V: scale the -0.03 scroll step

# ut1d slot update 532BC0: material 0/1/2 each has U and V scroll; material
# 2 V has a literal zero step and only normalizes an out-of-range offset.
lin 532C5F | ut1d material 0 U: scale the 0.008 scroll step before wrapping
lin 532CA2 | ut1d material 0 V: scale the 0.01 scroll step
lin 532CE2 | ut1d material 1 U: scale the 0.008 scroll step
lin 532D18 | ut1d material 1 V: scale the -0.01 scroll step
lin 532DB7 | ut1d material 2 U: scale the 0.01 scroll step
