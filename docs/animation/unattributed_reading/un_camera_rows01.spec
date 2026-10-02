# Camera modes (dispatched by 476B00, 4760E0 and 475C70), 2026-09-30. Their 2DA570
# approaches are the survey's "camera: read as a whole elsewhere" rows: a constant
# factor gets callblend, a factor from a mode table mode_constants.h already
# corrects gets callscale (the limit only), as 482C8C/482D3F.
group objects
# 478450
count 47881B (0x47880F,0x47881E,(0x47880F,0x478816,0x478819,0x47881B),None) | Camera mode 478450: pace the 90-tick hold +292 set when the view is blocked.
callblend 478A73 | Camera mode 478450: turn yaw +1B4 behind the target: constant 0.3 approach and its 0.0349 limit.
count 478A8A | Camera mode 478450: pace the 90-tick turn-behind window +410.
callblend 478B19 | Camera mode 478450: yaw toward the requested +39C: constant 0.1 approach and its limit.
count 478B1E | Camera mode 478450: pace the yaw request's duration +398.
callblend 478B53 | Camera mode 478450: pitch +1B0 toward +3A4: constant 0.2 approach and its limit.
count 478B58 | Camera mode 478450: pace the pitch request's duration +3A0 (30 ticks on entry).
callblend 478B8A | Camera mode 478450 (mode 9): pitch toward -0.314: constant 0.2 approach and its 0.0105 limit.
# 47C9D0
count 47CFA7 (0x47CF7E,0x47CFAA,(0x47CF7E,0x47CF85,0x47CF89,0x47CF8C,0x47CF8E,0x47CF96,0x47CF9E,0x47CFA2,0x47CFA5,0x47CFA7),None) | Camera mode 47C9D0: pace the idle delay +3B8 (counted while the stick is still) before 468420 recenters.
callscale 47D0A4 | Camera mode 47C9D0: yaw toward +39C; the factor is the 7A82D8 mode-table value minus one, which mode_constants corrects: scale the limit only.
count 47D0A9 | Camera mode 47C9D0: pace the yaw request's duration +398.
callblend 47D0E9 | Camera mode 47C9D0: yaw behind the target: constant 0.05 approach and its 0.0698 limit.
count 47D0EE | Camera mode 47C9D0: pace the turn-behind window +484.
# 47DAB0, a copy of 47C9D0
count 47E0E6 (0x47E0BD,0x47E0E9,(0x47E0BD,0x47E0C4,0x47E0C8,0x47E0CB,0x47E0CD,0x47E0D5,0x47E0DD,0x47E0E1,0x47E0E4,0x47E0E6),None) | Camera mode 47DAB0: pace the idle delay +3B8 before 468420 recenters.
callscale 47E201 | Camera mode 47DAB0: yaw toward +39C; the mode-table factor is already corrected: scale the limit only.
count 47E206 | Camera mode 47DAB0: pace the yaw request's duration +398.
callblend 47E246 | Camera mode 47DAB0: yaw behind the target: constant 0.05 approach and its limit.
count 47E24B | Camera mode 47DAB0: pace the turn-behind window +484.
# 47A3A0
blend 47A43B | Camera mode 47A3A0: field of view +1D0 approaches 65 by 0.15 a tick.
blend 47A677 | Camera mode 47A3A0: distance +200 approaches the global 7A7C0C by 0.1 a tick.
callscale 47AA70 | Camera mode 47A3A0: approach with the 7A8330 mode-table factor (corrected by mode_constants): scale the 0.0087 limit only.
callscale 47AAC9 | Camera mode 47A3A0: the chained second approach with the 7A8330 factor: scale its limit only.
callscale 47AB22 | Camera mode 47A3A0: the third 7A8330-factor approach: scale its limit only.
callblend 47AC05 | Camera mode 47A3A0: turn yaw behind the target: constant 0.3 approach and its 0.0349 limit.
count 47AC1B | Camera mode 47A3A0: pace the turn-behind window +410.
callscale 47ACBA | Camera mode 47A3A0: yaw toward +39C with the corrected 7A82D8 factor: scale the limit only.
count 47ACBF | Camera mode 47A3A0: pace the yaw request's duration +398.
count 47B5B5 (0x47B585,0x47B5B8,(0x47B585,0x47B58C,0x47B595,0x47B59E,0x47B5A7,0x47B5B0,0x47B5B3,0x47B5B5),None) | Camera mode 47A3A0: pace the recenter delay +3B8.
# 477F90
callblend 4780FC | Camera mode 477F90: +1C4 toward xmm8: constant 0.2 approach and its 0.279 limit.
callblend 47811C | Camera mode 477F90: +1C0 toward xmm8: constant 0.2 approach and its limit.
count 478121 | Camera mode 477F90: pace the request's duration +398.
# 470AE0
callblend 470F25 | Camera mode 470AE0: yaw toward +39C: constant 0.1 approach and its 0.1396 limit.
count 470F2A | Camera mode 470AE0: pace the yaw request's duration +398.
callblend 470F5F | Camera mode 470AE0: pitch toward +3A4: constant 0.2 approach and its limit.
count 470F64 | Camera mode 470AE0: pace the pitch request's duration +3A0.
# 46B080
count 46B61A (0x46B5F1,0x46B61D,(0x46B5F1,0x46B5F8,0x46B5FC,0x46B5FF,0x46B601,0x46B609,0x46B611,0x46B615,0x46B618,0x46B61A),None) | Camera mode 46B080: pace the idle delay +3B8 before the pitch returns to +3B0.
callblend 46B725 | Camera mode 46B080: yaw +1B4 toward the target's bearing: constant 0.9 approach and its 0.349 limit.
callblend 46B74E | Camera mode 46B080: pitch +1B0 toward +3A4: constant 0.2 approach and its 0.0349 limit.
callscale 46B7A3 | Camera mode 46B080: yaw toward +39C with the corrected 7A82D8 factor: scale the limit only.
count 46B7A8 | Camera mode 46B080: pace the yaw request's duration +398.
callblend 46B7EB | Camera mode 46B080: yaw behind the target: constant 0.05 approach and its limit.
count 46B7F0 | Camera mode 46B080: pace the turn-behind window +484.
