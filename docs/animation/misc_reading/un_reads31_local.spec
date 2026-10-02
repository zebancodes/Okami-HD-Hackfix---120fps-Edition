stock | cPad::Key_set writes +80/+84 from the current stick sample or current mouse delta, then adds the current opposing trigger contributions. The outputs are recomputed earlier in this same input-sampling call. | 1835E3 1835F4 183953 18395F
stock | 1BC720 seeds a 624-word random-number state array from the supplied seed vector, then mixes each array word in bounded initialization loops. | 1BC7D4 1BC83B
stock | 3E3440 sums model resource counts and high-bit transitions inside bounded loops over the model's subresources. The outputs count resource elements, not elapsed frames. | 3E34B1 3E34BD 3E34F2
stock | 4457C0 normalizes an angle relative to the previous angle by whole 360-degree turns in bounded-value while loops before its separate angular limit is applied. | 445B74 445BB4
stock | hx wireless-controller sample 140050 recomputes stick values from the current hardware sample, applies a dead zone, then restores an axis from that same sample when only its partner is nonzero. | 140172
stock | 14F150 filters a vector of file-name records, shifts retained records, destroys the removed strings, and reduces the end pointer by one 80-byte element. | 14F3E3 14F543
stock | cPad::mergeJoyWork adds action values from one current controller sample into a combined sample inside a 121-action loop. The additions combine devices, not elapsed frames. | 187506 187510
stock | 18B580 erases a supplied substring, moves the remaining bytes, updates string length, and writes the new terminator. | 18B616
stock | 1D08F0 and 1D2060 advance an encoded-text cursor and consumed length by each token's parsed length while scanning text commands. | 1D09CB 1D2100
stock | 3F1E60 grows an eight-byte-element vector, moves the old allocation, frees it, and reconstructs the end pointer using the old element count and new base. | 3F1ED9
stock | 496550 applies a supplied resource/reward delta, clamps the resulting total to capacity, and records positive earned amounts; changes are tied to the caller's award or consumption. | 496587 4965B9
stock | Compressed-stream decoders 120240 and 1221D0 consume variable-length bits from a byte cursor and store the shifted bit reservoir and its residual bit count. 12031D reconstructs a decoded delta sample from the preceding decoded value. | 12031D 121F44 121F52 124054 124061
