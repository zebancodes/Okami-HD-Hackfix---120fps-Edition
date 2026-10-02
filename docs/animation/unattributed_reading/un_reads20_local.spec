once | 1D3950: +57 advances from zero to one after starting the player's scripted action; subsequent calls only wait for 3F33A0 and finally set FF | 1D3A04
once | 1D3BF0/1D3C80: +57 advances from zero to one after starting the NPC action; subsequent calls only wait for 3055A0 | 1D3C4E 1D3CDE
stock | 206340: remove an actor pointer from the 32-entry 9C1D30 list and decrement its occupancy 9C1E30 on successful removal | 206371
stock | 3DF2C0/3DF370/3DF460: definite-heap available-block counts and low-water mark accompany allocation or freeing of one model, not elapsed updates | 3DF2CA 3DF39A 3DF46F
stock | 3CC870: hit-combo score +118C increments on a newly accepted collision, capped at 99 with high score +118E; callers 2DC7B0 and 2DD1A0 first mark the target contact E72 bit 7 and contact record bit 1 before awarding the hit | 3CC87A
stock | 3CE0D0: hit-combo score +118C capped at 99 and high score +118E; this is the same score award as 3CC870, not the separately initialized +1188 decay clock | 3CE0D0
stock | 4362E0: persistent per-kind collection counts at DFC, capped at 999, increment only after 416880/416B10/416CB0 accept and record a new collectible with 436810 | 4362F3
fixed | 239010: generated gatefn at the function entry paces both parity-based hit shake and the +10C0 hit-stop decrement; the audited callers discard the return value | 239068
fixed | 303F00/304190: generated gatefn entries pace the complete quantized villager and shadow alpha fades, including these byte stores | 303FBD 30425D
fixed | 30EB40: generated gatefn entry paces the whole mood-particle helper, keeping the +1277 countdown, spawn event and random reload on the same stock tick | 30EC13
fixed | cPad Actuater 1825A0: generated flag-group gatefn entry keeps the whole rumble update at the port's sixty-hertz cadence, including every slot's +4 delay and +6 duration decrement | 182602 182618
fixed | 2DC3B0: generated gatefn entry paces the complete object alpha-byte approach, including minimum quantized steps and clamps; these branch stores are inside the gated helper | 2DC4C7 2DC51C
