# 2026-10-02: the gates taken out on 10-01 and cDogLikeHm's, replaced by rows
# of their own (un_rows50.spec).
fixed | HUD number slide 1C8D80: the +48 store is reached from the inc (by a jmp) and the dec; counts on both (1C8DA6, 1C8DC3) and a notyetneg on the 10 test (1C8DA1) pace it; its layout update 1B54E0 runs every tick | 1C8DC5
fixed | Camera 4763F0: the transition count +290 is count row 476805 and its blend factor blendr 47683D. 4A0900's call of 4763F0 follows 481A10 with a length of 0 (r13d), so that pass never reaches the count | 476808
fixed | cCarryObj 33DE40 float bob: +E54's change is zfirst 33DEF4/33DEFE, its damping count-factor 33DF2C, the height step src 33DF41 | 33DF15 33DF34 33DF49
fixed | vtca 375FF0: count rows on the countdown +E36 (37613B) and the phase +1070 (376141), a notyet on the end test (375FFA) and a void callgate on the phase's sound call (376136) | 37613B 376141
fixed | cDogLikeHm 4873A0, state 4: the heading's spin is pre 4875AB with its decay countlast 4875B8, the approach toward +1234 lin 4874B6 (step and snap bound), +E36 count 4875FB with its sounds' callgate 48762A; the root motion (2DA3D0) and sub-states 0..3's motion advance (4B9B70) run every tick | 48752C 4875C0 4875C8 4875FB
