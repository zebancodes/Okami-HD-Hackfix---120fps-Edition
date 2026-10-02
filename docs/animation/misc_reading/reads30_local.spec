stock | objCock 20CB60 stores canonical wrapped B0/B4/B8 angles without adding any phase to those stored angles; E0/E4/E8 are combined only in a temporary matrix input. | 20CC09 20CC22 20CC2F
once | ut9e collision teleport copies the remembered position, advances the destination height by 50, and sets E36=2; entering phase 2 clears +1150 before continued motion. The displacement belongs to the teleport event. | 22AC3A 22AD98
once | ut2b vtable initialization slot 9 creates two children, sets E34=1, and wraps the existing yaw (plus zero) for each fixed child placement. | 57A6DE 57A780
once | uta9 vtable initialization slot 9 sets E34=1, creates two children, and applies paired fixed quarter-turn placement offsets before constructing their matrices. | 56601B 5660B3
once | ut35 vtable initialization slot 9 initializes the object and four attachments, with a fixed 15-unit placement displacement. | 6515FE
stock | utd7 230BC0 adds three to the bounded +1628 action strength after the triggered action/sound and clamps it to 60. This is an action count, not elapsed time. | 230C7A
once | uta8 E36=0 setup changes E36 to 1 before decrementing the finite action count +E44 and starting the motion and sound. Further updates enter another phase. | 5655F7
stock | utbd 22E430 subtracts the wrapped difference between the current parent/model basis angle and the previous stored basis +110C from the child angle. The function records the new basis at exit; this compensates existing motion rather than advancing a separate clock. | 22E6E7
stock | 127B78 accounts heap allocated bytes using payload, alignment and header lengths after allocating a block, and updates the allocation high-water mark. | 127CF1
stock | 1334A0 and 134F10 relocate resource array pointers by the supplied file base in bounded loading loops. | 1335C6 134F3F
stock | 150060 and 1636F0 grow vector containers, copy/move the old allocation, free it, and reconstruct the end pointer from the old element count and new base. | 150153 163769
stock | 35A170 and 35A2A0 remove destroyed objects from pointer vectors via memmove and decrement the vectors' end pointers by one eight-byte element. | 35A211 35A24D 35A354 35A385
stock | 35A820 inserts a supplied number of elements into a vector, allocates or shifts data as needed, and reconstructs base/end/capacity pointers. | 35A9AF 35A9B7 35A9BB 35AA4D 35AAD8
