group objects
# utb7 update 570890, state byte +E36. 2DE0A0 returns a bounded turn for
# +B0/+B4. Each state's two caller-local limits are in stock-tick units.
lin 570A9B | utb7 state 1: scale the first 2DE0A0 angular limit for the repeated +B0 turn
lin 570AA7 | utb7 state 1: scale the second angular limit for +B4
lin 570C88 | utb7 state 3: scale the first angular limit for +B0
lin 570C94 | utb7 state 3: scale the second angular limit for +B4
lin 570EE9 | utb7 state 5: scale the first angular limit for +B0
lin 570EF5 | utb7 state 5: scale the second angular limit for +B4
lin 57110A | utb7 state 7: scale the first angular limit for +B0
lin 571116 | utb7 state 7: scale the second angular limit for +B4
lin 571229 | utb7 state 9: scale the first angular limit for +B0
lin 571235 | utb7 state 9: scale the second angular limit for +B4

# State 3 fades two material alphas from the shared 0.05 step in xmm7.
src 570E18 | utb7 state 3: material 1 alpha rises by 0.05 per stock tick, clamped to one
src 570E52 | utb7 state 3: material 0 alpha falls by 0.05 per stock tick, clamped to zero

# State 5 rises by dynamic +E18, which ramps by 0.3 after the move.
src 570FEC | utb7 state 5: add one high-rate share of the stock-valued +E18 rise to the target height
countlast 570FF0 | utb7 state 5: advance +E18 by the full 0.3 only after the last move in a stock period
