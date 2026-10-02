stock | 1CA850 renders a text-token stream in a bounded per-call loop: line/glyph positions start from base layout, +90 counts decoded tokens and +80 advances by token byte length; none is elapsed time. | 1CAE15 1CAE94 1CAEA7 1CAEBB
stock | 1BC040 solves line/circle intersections and then translates freshly calculated roots by the supplied center; the output fields are overwritten before these additions. | 1BC276 1BC27F 1BC29D 1BC2A6
stock | 1BAA20 compensates tracked position for the model's old-to-new matrix translation; the old and current positions are copied within this call. | 1BAB96 1BABA6 1BABB1
once | 1BAA20 adds a random lateral impulse only after a successful 168F50 collision/request lookup, then 168CF0 consumes that entry before adding the impulse to velocity. | 1BACB3 1BACB8
stock | 17C6B0 processes the finite 0x600-point brush path: segment counts start at zero, angle fields come from freshly computed dot products, point sums start at zero and are divided by the segment's point count before return. | 17C7F2 17C998 17CBAA 17CCAF 17CCC3 17CCFD 17CD15
once | 1604E0 +2 is the bounded text/page selection moved by JOY_ACTIDX trigger bits; +3 advances from initialization to input phase exactly once. | 1605FA 1606A4 1608F0
once | 160310 +54 selects the next of three actions after the exit delay, and immediately changes +3A/+3B to state 4. | 1603A2
once | 1D04A0 +19 advances from initialization or from the completed six-tick exit interpolation into cleanup; it is a phase selector. | 1D04F2 1D0558
once | 1D0DF0 +19 is the initialization-to-active phase transition, guarded by old +19 equal zero. | 1D0E20
follows | 1C10F0 consumes the mode-divided wait stored at +288, expanded by imuln 1C159E; +284 is its active copy and +10 increments only after the expanded wait expires, then reloads +284. | 1C1162 1C1177
stock | 135CD0 and 135DE0 build keyframe offsets in a bounded array loop: each next entry copies the previous offset before adding that entry's duration. | 135DA9 135E57
stock | 136880 copies the previous keyframe offset into the next array entry before adding the current duration; this rebuilds an adjacent offset rather than accumulating across calls. | 1369E7
stock | 136C40 walks the resource's finite entry count and rewrites each entry's identifier with the result of 136160. | 136C8E
stock | 13A2E0 searches backward/forward over valid resource indices; +3 is the selected index returned by that bounded search. | 13A4E3
