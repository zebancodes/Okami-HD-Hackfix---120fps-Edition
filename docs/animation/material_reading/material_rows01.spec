# em4d/em50 and cKiType023 each use one local step for sixteen material
# channel fades across two six-state switch tables. The only reads of xmm6
# between these loads and their restores are those addss/subss channel steps.
group actor
lin 287E35 | em4d/em50 material channels 4 and 5: scale their shared fade step in xmm6 for all sixteen +50/+54/+58 updates
group objects
lin 36A665 | cKiType023 material channels 4 and 5: scale their shared fade step in xmm6 for all sixteen +50/+54/+58 updates
