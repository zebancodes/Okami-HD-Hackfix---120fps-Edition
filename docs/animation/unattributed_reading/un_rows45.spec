# 2026-10-01, sixth batch
group menu
# the screen transition B65E80, driven by 48A920's task loop (its wait 48ABDE stays per tick: the loop sets the mode byte)
count 48AA86 float | Screen transition 48A920 (mode 3): pace the 6-tick count B65E9C (its ease B65EA0 is recomputed from it each pass).
count 48AD2C float | Screen transition 48AD20 (mode 2, from 48A830): pace the 6-tick count +1C (the slide +28 is recomputed from it).
group objects
srcblend 48DD9A | 48DCE0 (from 48EC20): +EC approaches its target by a third of the gap a tick.
count 48F331 | 48F300 (from 48E9C0): pace the countdown +E4 while the player is farther than 400.
count 48FF69 | 48FE70 (from 48ECA0): pace the 50-tick delay +159.
count 49125A | 491200 (from 48E9C0): pace the countdown +E6.
notyet 491261 notyet:491266 | 491200: the end test reads the old count (cx); between stock ticks take the not-yet path.
count 495F36 | 495E40: pace the 8-tick spawn period +94 (an effect each time it runs out).
notyet 495F3C notyet:495FAB | 495E40: the period test reads the old count (ecx); between stock ticks take the not-yet path.
src 4D2644 | Map 103's script (4D2600, from 4D2280 and 4DBF90): an object's +D2C fades by 0.01 a tick, in doubles.
group human
lin 4ABC08 | Villager 4ABA90 (from 30C780): +E14 turns by 15 degrees a tick while its motion time is under 30.
