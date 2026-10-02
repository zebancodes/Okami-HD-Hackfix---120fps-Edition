stock | Text token scanner 1CC570 skips controller-dependent token ranges until B8/BB/BD tags; these advances consume encoded text bytes, with bounds against the input length. | 1CC63C 1CC754
stock | Text scanners 1CC360 and 1CCA50 advance an encoded-text cursor by the parsed token length inside bounded scanning loops. | 1CC533 1CCC2D
stock | 45AE60 resource allocation relocates five file offsets by the resource base, guarded by bit 4 in +64 so each source resource is relocated once. | 45AEDE 45AEE2 45AEE6 45AEEA 45AEEE
stock | Heap free 1283B4 updates allocated byte accounting and coalesces two adjacent free-block sizes by header/payload lengths. These are allocator operations. | 1283D8 128418 12845C
stock | Resource relocation 132AD0 adds the supplied file base to non-null array pointers once per loaded record and copies prior record links. | 132B21 132BC8
