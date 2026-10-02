once | an03 1DBEF0: slot 9 setup raises the actor Y coordinate by 30 before resetting its motion state | 1DBF7D
fixed | an03 1DBFB0: the +1184 behavior countdown now decrements on stock ticks | 1DBFC8
fixed | an03 1DC560: the randomized +E3C behavior countdown now decrements on stock ticks | 1DC5E8
once | an06/an08 1E1E50: the extra 45 units are added to a randomized +E3C timer when choosing its next behavior, not on each tick | 1E1F7E
follows | an06/an08 1E2790: +B4 reverses sign when the current turn crosses the opposite angular bound; the triggering turn follows the scaled actor motion | 1E2915
follows | an07 1E4500: +E3C decreases only when the scaled motion advance reports animation completion | 1E4556
fixed | an09 1E7AF0: the shared xmm1 step is now scaled before the three D20/D24/D28 growth additions | 1E7D2B
follows | an0b 1EA100: +E37 changes only when the scaled motion advance reports animation completion | 1EA1E6
fixed | an0b 1EAC20: the shared xmm1 step is now scaled before the three D20/D24/D28 growth additions | 1EAE7D
fixed | an0b 1EAFA0: the +E3C action countdown now decrements on stock ticks | 1EB097
