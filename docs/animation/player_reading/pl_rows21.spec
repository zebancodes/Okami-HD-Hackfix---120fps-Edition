group player
# pl01 movement (3B2CF0)
count 3B3318 factor | pl01 (3B2CF0, state 3 and mode 8): +E48 takes 0.94 damping before the move once on the first tick of each stock period; the other modes use their already-rewritten table
pre 3B3B8B | pl01 (3B2CF0), conditional ground nudge: persistent +10B8 gains s of the 0.1-scaled z acceleration
pre 3B3B93 | pl01 (3B2CF0), conditional ground nudge: persistent +10B0 gains s of the 0.1-scaled x acceleration
pre 3B3BAB | pl01 (3B2CF0), conditional ground nudge: position.x gains s of the persistent +10B0 velocity before the existing 0.9^s damping
pre 3B3BC2 | pl01 (3B2CF0), conditional ground nudge: position.z gains s of the persistent +10B8 velocity before the existing 0.9^s damping
