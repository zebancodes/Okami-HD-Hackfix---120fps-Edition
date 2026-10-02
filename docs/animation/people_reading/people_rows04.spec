group actor
# hm28's +E3C word is a 300-tick state wait. Its local AX value is decremented
# and written back while nonzero; keep that write on stock ticks.
count 323A0E | hm28: decrement the +E3C state wait once per stock tick
