group actor
# esfd has two forms of its state handler, each nudging +14F0 toward the
# selected alpha target by 0.05 in either direction.
lin 362EF7 | esfd first handler: scale the +0.05 alpha approach
lin 362F09 | esfd first handler: scale the -0.05 alpha approach
lin 363055 | esfd second handler: scale the +0.05 alpha approach
lin 363067 | esfd second handler: scale the -0.05 alpha approach

# es13 mirrors es11's random plus mutable-base material phase scroll.
lin 5159FF | es13: scale the random 0.02 phase-step component
srcx 515A0F | es13: scale the mutable 0.05 base phase step

# es49 approaches two angles using the same 0.05 blend factor, then steps
# its +10E8 lifetime countdown while nonzero.
blendr 4A9EE8 | es49 first FixTurnRate approach: compound the 0.05 factor
blendr 4A9EF8 | es49 second FixTurnRate approach: compound the 0.05 factor
count 4A9F31 | es49: decrement the +10E8 lifetime countdown at stock pace
