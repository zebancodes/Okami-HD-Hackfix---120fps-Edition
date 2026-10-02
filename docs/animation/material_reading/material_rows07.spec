group objects
# ut6f loops over six materials using one table rate per channel.
pre 224B03 | ut6f: scale each table-driven material U scroll step before adding it

# em2c holds its 0.05 in xmm8 (a nine-byte RIP load); scale only its two
# color additions, leaving the rest of that function's xmm8 uses alone.
src 279B67 | em2c material channel +54: scale the 0.05 increment
src 279B89 | em2c material channel +58: scale the 0.05 increment

# Human and object material alpha fades, one fixed 0.05 rate per direction.
lin 31D5BB | hm10 material 2 alpha: scale rising 0.05
lin 31D5F3 | hm10 material 2 alpha: scale falling 0.05
lin 31E8E7 | hm19 material 1 alpha: scale falling 0.05
lin 31E8F9 | hm19 material 2 alpha: scale rising 0.05
lin 331D5B | hm6e material 2 alpha: scale rising 0.05
lin 331D93 | hm6e material 2 alpha: scale falling 0.05
lin 331F3B | hm6f material 2 alpha: scale rising 0.05
lin 331F73 | hm6f material 2 alpha: scale falling 0.05

# The two enemy/object material U phases wrap by whole units after these rates.
lin 2E84EC | et24 material 0 U: scale the -0.01 scroll step
lin 515A7F | es13 material 1 U: scale the -0.01 scroll step
lin 5A977F | utf0 material 1 U state A: scale the 0.002 scroll step
lin 5A9789 | utf0 material 1 U state B: scale the 0.01 scroll step
