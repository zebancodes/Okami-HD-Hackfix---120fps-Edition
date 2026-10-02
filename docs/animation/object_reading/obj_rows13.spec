group objects
# et0f's two motion/action helpers each count down the same +1138 wait.
count 2E4FB9 | et0f first helper: pace the +1138 wait
count 2E50F9 | et0f second helper: pace the +1138 wait

# et69's nearby-target effect reloads +E36 to 89 and then counts down AX.
count 4D1448 (0x4D13E8,0x4D144A,(0x4D13E8,0x4D13EF,0x4D13F1,0x4D1448),None) | et69: pace the +E36 effect cooldown

# ut6d has a 30-tick sound wait and a separate action countdown, both
# loaded to AL and conditionally decremented before their stores.
count 224053 (0x224019,0x224055,(0x224019,0x224020,0x224022,0x224053),None) | ut6d: pace the +E35 sound wait
count 22408A (0x224072,0x22408C,(0x224072,0x224079,0x22407B,0x22408A),None) | ut6d: pace the +E36 action countdown
