fixed | es17 35E290: each of its three mutually exclusive opacity increments uses its own scaled RIP rate | 35E2F4 35E33A 35E37B
fixed | es17 35E290: the +107C yaw phase is advanced by its scaled 0.5 step before wrapping | 35E3B3
stock | esp17 192F80: slot 4 derives each RGBA lane from template bytes on this call and clears the temporary lanes at 1931CC; these stores do not accumulate an elapsed-time step | 193134 193152 193170 19319F
fixed | esp04 19E210: three slot-14 random motion samples are scaled after multiplying by their axis speeds and before the object position/yaw additions | 19E277 19E2A1 19E2EB
