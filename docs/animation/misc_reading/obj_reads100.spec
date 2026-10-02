stock | Submodel projection reads fresh B0 orientation after 4B9C80 in both callers, 208E90 and 36A0B0, then projects it into B0/B8 with sine/cosine and a fixed spatial factor. It is not recurrent damping. | 207A00
stock | Both callers, 2E0610 and 2EDA70, advance 4B9C80 immediately before this state branch. The helper projects freshly evaluated submodel B0 into B0/B8 using direction and a spatial factor. | 2E047D
once | et6f decrements component health by ten only after consuming and clearing that component's +11B2 bit 1; the same event bit cannot decrement it again. | 2F3313
once | et2f phase-zero entry computes the linked-model centroid, selects facing and adds a fixed fifteen-degree offset, then advances E36 to one. | 62EE0B 62EE29
once | et30 phase-zero entry computes the linked-model centroid, selects facing and adds a fixed fifteen-degree offset, then advances E36 to one. | 6318CA 6318E1
fixed | ut35 B8 damping reads the indexed mode table at 7A81E8, already rewritten to stock-factor raised to elapsed time by mode_constants.h. | 651C85
