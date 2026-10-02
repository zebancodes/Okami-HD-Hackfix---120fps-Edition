group objects
# uta9's helper approaches all three +D20/+D24/+D28 components with the
# same literal 0.08 factor. Compounding it gives the stock target approach.
blend 566175 | uta9: compound the shared 0.08 XYZ target blend

# cGear's slot-3 update contains its full tick state machine: two waits and
# its gear-angle advances. No previously patched sites are inside it.
gatefn 495950 | cGear: advance the full gear state machine on stock ticks
