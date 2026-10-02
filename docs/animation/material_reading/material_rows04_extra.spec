group objects
# The xmm8 RIP loads at 3933D2 and 397359 have a REX prefix and cannot be
# retargeted by the eight-byte literal handler. Scale their consumers.
src 3933E8 | wp20 material 1 U: scale the shared 0.05 before subtraction
src 393412 | wp20 material 2 U: scale the shared 0.05 before subtraction
src 39343C | wp20 material 3 U: scale the shared 0.05 before subtraction
src 393466 | wp20 material 4 U: scale the shared 0.05 before subtraction
src 3973F2 | wp35 first material 0 U: scale the shared 0.05 before addition
src 39741C | wp35 first material 1 U: scale the shared 0.05 before addition
src 397558 | wp35 second material 0 U: scale the shared 0.05 before addition
src 397582 | wp35 second material 1 U: scale the shared 0.05 before addition
