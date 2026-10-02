group actor
# These ten animal action handlers share the same +1170 random wait. A LEA
# decrements the loaded value; the following `test ecx` fires the reload/event
# when the old count was zero. Keep both the store and its event test at the
# stock cadence so a held zero does not fire again between stock ticks.
count 1D60E1 | an00: pace the +1170 wait
notyet 1D60E7 notyet:1D6116 | an00: suppress the +1170 reload event between stock ticks
count 1DD683 | an04/an0d/an0e: pace the +1170 wait
notyet 1DD689 notyet:1DD6B8 | an04/an0d/an0e: suppress the +1170 reload event between stock ticks
count 1E0F36 | an06/an08: pace the +1170 wait
notyet 1E0F3C notyet:1E0F6B | an06/an08: suppress the +1170 reload event between stock ticks
count 1E3B73 | an07: pace the +1170 wait
notyet 1E3B79 notyet:1E3BA8 | an07: suppress the +1170 reload event between stock ticks
count 1E7403 | an09: pace the +1170 wait
notyet 1E7409 notyet:1E7438 | an09: suppress the +1170 reload event between stock ticks
count 1EA349 | an0b: pace the +1170 wait
notyet 1EA34F notyet:1EA364 | an0b: suppress the +1170 reload event between stock ticks
count 1ED649 | an0c: pace the +1170 wait
notyet 1ED64F notyet:1ED664 | an0c: suppress the +1170 reload event between stock ticks
count 1F4D43 | an19: pace the +1170 wait
notyet 1F4D49 notyet:1F4D78 | an19: suppress the +1170 reload event between stock ticks
count 1FB14E | an1e: pace the +1170 wait
notyet 1FB154 notyet:1FB183 | an1e: suppress the +1170 reload event between stock ticks
count 1FEA54 | an02/an1b/an1f/an20: pace the +1170 wait
notyet 1FEA5A notyet:1FEA89 | an02/an1b/an1f/an20: suppress the +1170 reload event between stock ticks
