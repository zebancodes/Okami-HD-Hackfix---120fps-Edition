group player
# pl00 ground offsets (3A75C0)
blend 3A766F | pl00 ground offsets (3A75C0), (+1014 & 0x1F) == 8: +10A0 approaches the rotated +E48 target by 0.03 a tick
blend 3A7695 | pl00 ground offsets (3A75C0), (+1014 & 0x1F) == 8: +10A8 approaches the rotated +E48 target by 0.03 a tick
blend 3A76C4 | pl00 ground offsets (3A75C0): +10A0 approaches the rotated +E48 target by 0.3 a tick; 7A8348 stays 0.3 at every mode
blend 3A76EA | pl00 ground offsets (3A75C0): +10A8 approaches the rotated +E48 target by 0.3 a tick; the same unscaled 7A8348 reader
blend 3A7716 | pl00 ground offsets (3A75C0): +10A4 approaches the rotated +E48 target by 0.3 a tick; 7A834C stays 0.3 at every mode
count 3A7814 | pl00 ground offsets (3A75C0), +E58 bits 14 and 16 path: +10A0 *= 0.1 a stock tick before the reduced move, so keep its store on the first tick of each stock period
count 3A781C | pl00 ground offsets (3A75C0), +E58 bits 14 and 16 path: +10A8 *= 0.1 a stock tick before the reduced move, so keep its store on the first tick of each stock period
