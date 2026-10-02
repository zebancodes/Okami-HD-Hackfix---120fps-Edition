group objects
src 468224 | Camera zoom: integrate the retained zoom velocity by the elapsed share of a stock tick.
srcroot 468230 | Camera zoom: compound its persistent velocity's 0.9 decay.
srcroot 468259 | Camera distance: compound the repeated 0.6 damping below the lower range.
src 468269 | Camera distance: integrate retained distance velocity without changing that velocity's later damping input.
srcroot 468284 | Camera distance: compound its persistent velocity's 0.9 decay.
srcroot 4682F3 | Camera distance: compound the 0.94 release damping while neither held zoom command is active.
pre 46832D | Camera pitch: scale the fresh velocity step before adding persistent pitch; input acceleration already consumes B6AC38.
pre 468345 | Camera yaw: scale the fresh velocity step before adding persistent yaw; input acceleration already consumes B6AC38.
srcroot 468365 | Camera pitch: compound 0.85 velocity damping.
srcroot 46836D | Camera yaw: compound 0.85 velocity damping.
srcroot 46838E | Camera pitch: compound the extra 0.9 damping in the negative-state branch.
srcroot 468392 | Camera yaw: compound the extra 0.9 damping in the negative-state branch.
srcroot 4683B7 | Camera pitch lower clamp: compound 0.4 attenuation while velocity keeps pushing against the bound.
srcroot 4683E9 | Camera pitch upper clamp: compound the same repeated 0.4 attenuation.
srcroot 4684E9 | Alternate camera pitch lower clamp: compound its repeated 0.4 velocity attenuation.
srcroot 468518 | Alternate camera pitch upper clamp: compound its repeated 0.4 velocity attenuation.
pre 468698 | Alternate camera pitch: scale the completed input velocity before accumulating pitch.
pre 4686B0 | Alternate camera yaw: scale the completed input velocity before accumulating yaw.
srcroot 4686C8 | Alternate camera yaw: compound persistent velocity's 0.9 decay.
srcroot 4686D8 | Alternate camera pitch: compound persistent velocity's 0.9 decay.
src 468E40 | Close camera zoom: integrate retained zoom velocity by elapsed time.
srcroot 468E4C | Close camera zoom: compound persistent velocity's 0.9 decay.
srcroot 468E75 | Close camera distance: compound its repeated 0.6 lower-range damping.
src 468E85 | Close camera distance: integrate velocity without changing its later damping input.
srcroot 468EA0 | Close camera distance: compound persistent velocity's 0.9 decay.
srcroot 468F0F | Close camera distance: compound 0.94 release damping.
pre 468F27 | Close camera pitch: scale the completed input velocity before accumulating pitch.
pre 468F3F | Close camera yaw: scale the completed input velocity before accumulating yaw.
srcroot 468F57 | Close camera yaw: compound its 0.85 velocity decay.
srcroot 468F67 | Close camera pitch: compound its 0.85 velocity decay.
srcroot 468F98 | Close camera lower clamp: compound repeated 0.4 velocity attenuation.
srcroot 468FC7 | Close camera upper clamp: compound repeated 0.4 velocity attenuation.
pre 4690CB | Radius camera: scale retained X input velocity before accumulating radius X.
pre 4690E3 | Radius camera: scale retained Y input velocity before accumulating radius Y.
srcroot 469190 | Radius camera lower X bound: compound repeated 0.5 attenuation of the input velocity.
srcroot 4691C4 | Radius camera upper X bound: compound repeated 0.5 attenuation of the input velocity.
srcroot 4691F1 | Radius camera lower Y bound: compound repeated 0.5 attenuation of the input velocity.
srcroot 46921A | Radius camera upper Y bound: compound repeated 0.5 attenuation of the input velocity.
srcroot 46928A | Second radius camera: compound the X input velocity's 0.9 idle damping.
srcroot 46929E | Second radius camera: compound radius X's 0.9 idle damping before integration.
srcroot 4692EB | Second radius camera: compound the Y input velocity's 0.9 idle damping.
srcroot 4692FF | Second radius camera: compound radius Y's 0.9 idle damping before integration.
pre 469313 | Second radius camera: scale retained X input velocity before accumulating radius X.
pre 46932B | Second radius camera: scale retained Y input velocity before accumulating radius Y.
srcroot 469343 | Second radius camera: compound Y input velocity's 0.96 decay after integration.
srcroot 469353 | Second radius camera: compound X input velocity's 0.96 decay after integration.
srcroot 4693E0 | Second radius camera lower X bound: compound repeated 0.5 velocity attenuation.
srcroot 469414 | Second radius camera upper X bound: compound repeated 0.5 velocity attenuation.
srcroot 469444 | Second radius camera lower Y bound: compound repeated 0.5 velocity attenuation.
srcroot 469475 | Second radius camera upper Y bound: compound repeated 0.5 velocity attenuation.
