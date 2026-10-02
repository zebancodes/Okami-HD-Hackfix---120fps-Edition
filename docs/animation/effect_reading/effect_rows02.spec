group actor
# es11 adds a random 0.02 component and a mutable 0.05 base step to its
# +1084 material phase before wrapping by one unit.
lin 2C074F | es11: scale the random 0.02 phase-step component
srcx 2C075F | es11: scale the mutable 0.05 base phase step

# esf2's +1124 value waits eight actor ticks between paired effect calls.
count 5BB382 | esf2: decrement the eight-tick effect cooldown at stock pace
