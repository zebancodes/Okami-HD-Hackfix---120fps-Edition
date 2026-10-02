fixed | cCockGetItemInfo 3FD370: slot 3 decrements the item timer on stock ticks, scales its 1.5 acceleration, then scales updated velocity before adding it to position | 3FD3F3 3FD400 3FD409
stock | cCockGetItemInfo 3FD370: +4 velocity receives -0.45 restitution only when position exceeds a bound, after position is clamped; it is a collision response rather than a continuous per-tick factor | 3FD52E 3FD55B
once | cCockGetItemInfo 3FD370: +20 layout offset of 52 is applied only when the observed mode byte changes from the saved +D8 value | 3FD686 3FD6A8
