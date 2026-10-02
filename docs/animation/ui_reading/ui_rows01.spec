group objects
# cCockCompas vtable slot 3 updates its gameplay HUD compass color. Each of
# four angle sectors changes one of the four RGBA bytes by +15 and the other
# three by -15. Preserve the stock 30 Hz integer color sequence.
count 3FAE87 | compass sector 1: advance color byte +71 once per stock tick
count 3FAE8B | compass sector 1: advance color byte +72 once per stock tick
count 3FAE8F | compass sector 1: advance color byte +73 once per stock tick
count 3FAE93 | compass sector 1: advance color byte +70 once per stock tick
count 3FAEA1 | compass sector 2: advance color byte +72 once per stock tick
count 3FAEA5 | compass sector 2: advance color byte +73 once per stock tick
count 3FAEA9 | compass sector 2: advance color byte +71 once per stock tick
count 3FAEAD | compass sector 2: advance color byte +70 once per stock tick
count 3FAEBC | compass sector 3: advance color byte +73 once per stock tick
count 3FAEC0 | compass sector 3: advance color byte +72 once per stock tick
count 3FAEC4 | compass sector 3: advance color byte +71 once per stock tick
count 3FAEC8 | compass sector 3: advance color byte +70 once per stock tick
count 3FAED7 | compass sector 4: advance color byte +70 once per stock tick
count 3FAEDB | compass sector 4: advance color byte +73 once per stock tick
count 3FAEDF | compass sector 4: advance color byte +72 once per stock tick
count 3FAEE3 | compass sector 4: advance color byte +71 once per stock tick
