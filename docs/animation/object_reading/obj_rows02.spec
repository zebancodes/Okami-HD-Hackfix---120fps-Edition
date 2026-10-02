group objects
# utb6 update 56F760, state byte +E36. Even states initialize and fall
# through to their odd, repeated update state. The 2DE0A0 call returns bounded
# +B0/+B4 angular changes; its caller-local limits are passed in stack slots.
lin 56F8C0 | utb6 case 1: scale the first angular limit passed to 2DE0A0, which bounds +B0's continuous turn each tick
lin 56F8CC | utb6 case 1: scale the second angular limit passed to 2DE0A0, which bounds +B4's continuous turn
srcblend 56F9DE | utb6 case 1: position x approaches the computed target by dynamic +E14 each tick
srcblend 56F9FF | utb6 case 1: position y uses the same +E14 approach factor
srcblend 56FA22 | utb6 case 1: position z uses the same +E14 approach factor
countlast 56FA3C | utb6 case 1: hold +E14 constant through each stock period while its converted blend runs; add the full 0.07 only on the last tick, after the approach

lin 56FA95 | utb6 case 3: scale 2DE0A0's first angular limit for its repeated +B0 turn
lin 56FAA1 | utb6 case 3: scale 2DE0A0's second angular limit for its repeated +B4 turn

lin 56FCB4 | utb6 case 5: scale 2DE0A0's first angular limit for its repeated +B0 turn
lin 56FCC0 | utb6 case 5: scale 2DE0A0's second angular limit for its repeated +B4 turn
srcblend 56FDFD | utb6 case 5: position x approaches the computed target by dynamic +E14 each tick
srcblend 56FE1E | utb6 case 5: position y uses the same +E14 approach factor
srcblend 56FE41 | utb6 case 5: position z uses the same +E14 approach factor
countlast 56FE5B | utb6 case 5: hold +E14 through the stock period and add the full 0.04 on its last tick, after the converted approach

lin 56FE7E | utb6 case 7: a shared literal bounds both +B0 and +B4 changes returned by 2DE0A0 every tick
count 56FF02 | utb6 case 7: commit +E3C's increment once per stock tick; the following comparison reads the advanced ax, so its transition can be up to three quarters of a stock tick early at 120

lin 56FF59 | utb6 case 9: scale 2DE0A0's first angular limit for its repeated +B0 turn
lin 56FF65 | utb6 case 9: scale 2DE0A0's second angular limit for its repeated +B4 turn
callscale 56FFE6 (0x2DA410,"xmm1") | utb6 case 9: 2DA410 moves position by stock-valued +E48 each tick; scale the caller-local distance argument, while +E48's own rise and decay retain their cadence

lin 570078 | utb6 case 11: scale 2DE0A0's first angular limit for its repeated +B0 turn
lin 570084 | utb6 case 11: scale 2DE0A0's second angular limit for its repeated +B4 turn
callscale 570105 (0x2DA410,"xmm1") | utb6 case 11: 2DA410 moves position by stock-valued +E48 each tick; scale only this call's distance
