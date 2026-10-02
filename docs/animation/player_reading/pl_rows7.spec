group player
# --- pl04's three appendages (3A6120), one call per piece each tick ---
count 3A62A9 | pl04 appendage: +414C[part] indexes its preset path, advancing one point per stock tick while the model sits on the current point
count 3A65A7 | pl04 appendage: +414C[part] counts down the 90-tick hold in state 5 while the model follows its target's position
notyet 3A65AF notyet:3A65BC | pl04 appendage: state 5's zero test reads the countdown's old value; between stock ticks it must remain in state 5
blendr 3A6661 | pl04 appendage, state 6/7: xmm7 = 0.3 for each coordinate's return to the preset anchor; all six uses are approach factors, including the second approach when closer than 10
