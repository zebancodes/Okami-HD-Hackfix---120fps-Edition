stock | 2D layout child-composition pass 1B2C60: each node's +4C is reset to zero at 1B2D04 before adding parent rotation +34 and wrapping within the same pass | 1B2D55
stock | 2D layout child-composition pass 1B2C60: +50..+53 are copied from the node's base +38 color at 1B2E4B before multiplying each parent's RGBA; the products derive the composite color each pass | 1B2EBD 1B2EDC 1B2EFB 1B2F1A
stock | 2D layout child-composition pass 1B2C60: +3C/+40 are reset from this pass's local +B0/+B4 at 1B2E3C/41 before adding the parent positions | 1B2F37 1B2F3C
stock | cSSScroll/cSubScrFiles input handler 411C40: the +D2 page/selection byte and +D1 row byte change only after controller LargeBitElement action tests, one selection event at a time | 411D43 411D83 411E0A 411E4A
stock | cSSScroll/cSubScrFiles input handler 411C40: the +24 sprite Y offset changes by one fixed menu row only in the same button-action branches that change +D1; it is menu navigation, not a per-tick movement | 411D92
