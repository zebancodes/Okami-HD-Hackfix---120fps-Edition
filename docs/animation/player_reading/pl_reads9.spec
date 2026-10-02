fixed | wp51 (39EAC0): +10F0 loses the slow-motion dt in sub-states 3 and 1, scaled at xmm6's copy (dst 39EAFC) | 39EB60 39EC43
fixed | wp51 (39EE30): +10F0, +E18, and +E28 lose their slow-motion-dt steps, scaled at xmm6's copy (dst 39EE66) | 39EF81 39F07D 39F156 39F24C
left | wp51 steering helper (39F770): +B0's 0.15 approach factor is shared by per-tick calls 39E883/39EE82 and the one-shot call 39EC09; scaling 39F82F globally would corrupt the one-shot, so it needs a caller-aware helper patch | 39F860
fixed | wp51 steering helper (39F770): +B4 keeps the stock 50-degree limit at one-shot call 39EC09, while per-tick callers scale their 4-degree arguments at 39E872 and 39EE6F | 39F896
fixed | wp51 (39F2B0): both +10F0 countdowns lose dt and +E18 gains 0.3 x dt, scaled at xmm8's copy (dst 39F2E8) | 39F4CC 39F5E9 39F633
once | wp55 (3A0160), launch: +E14 gains 7 once before the launch direction is normalized | 3A0210
once | wp55 (3A0160), launch: the normalized direction is multiplied by 6.5 and stored as the persistent velocity +E10/+E14/+E18 once as sub-state 0 starts | 3A023D 3A0251 3A0259
once | wp55 (3A0160), launch: position.y gains 0.5 once during the sub-state-0 placement | 3A026E
fixed | wp55 (3A0160), sub-state 1: position gains s of persistent velocity +E10/+E14/+E18 each tick (pre 3A0352/3A0373/3A038C) | 3A0360 3A0378 3A0391
fixed | wp5a (3A0FE0): the hit radius +E18's +3/-6 per-tick steps are s-scaled at 3A10D0 and 3A1104 | 3A10DF 3A1117
fixed | wp5a (3A0FE0): +10F0's sound countdown loses the slow-motion dt, scaled at xmm6's copy (dst 3A100B) | 3A11A8
fixed | wp5e (3A1A30): +D2C loses 0.03 x the slow-motion dt, scaled at xmm6's copy (dst 3A1A51) | 3A1B1F
