stock | 1676D0 constructs param_2 from supplied signed-short coordinates before applying the byte-sized vertical offset and optional matrix; these additions modify fresh output coordinates. | 1677A3 1677B3
stock | 17CE00 resets the brush-segment turning-angle totals before summing freshly computed per-point angles in the bounded segment loop; these totals describe the input path. | 17D6CC 17D6E2
stock | 17E760 projects the current supplied brush point onto the stored segment using a geometric dot product divided by squared segment length; it writes that projected point or snaps to an endpoint. | 17E990 17E995
stock | 17EF70 initializes an output vector, transforms screen coordinates through the camera matrix, then divides by W and subtracts viewport offsets. | 17F018 17F01C
once | 1BA350 consumes the successful 168F50 collision/request through 168CF0 before injecting a random lateral velocity impulse. | 1BA610 1BA615
stock | 1BC2E0 constructs a new random offset vector, scales it, optionally mirrors its Y component and finally adds the supplied center. | 1BC380 1BC3A6
stock | 1C9FE0 starts both layout outputs at zero then accumulates glyph widths while walking tokens; at a line terminator it subtracts the trailing inter-glyph spacing. | 1CA187 1CA2D8
once | 1D1B70 increments +19 only after the six-step entrance interpolation completes, entering its audio-wait phase. | 1D1BEA
stock | 140EC0 enumerates the supplied resource table and counts successful matching/loaded entries in its constructor loop. | 141175
