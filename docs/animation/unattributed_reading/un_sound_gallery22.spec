group menu
srcx 448A74 | 4487E0 audio mixer: scale the negative +B04 approach step for +AAC before its target clamp, preserving the stored stock-unit rate
srcx 448A81 | 4487E0 audio mixer: scale the positive +B04 approach step for +AAC before its target clamp
srcx 448ABA | 4487E0 audio mixer: scale the negative +B08 approach step for +AB0 before its target clamp
srcx 448AC7 | 4487E0 audio mixer: scale the positive +B08 approach step for +AB0 before its target clamp
srcx 448B00 | 4487E0 audio mixer: scale the negative +B0C approach step for +AB4 before its target clamp
srcx 448B0D | 4487E0 audio mixer: scale the positive +B0C approach step for +AB4 before its target clamp
srcx 448B46 | 4487E0 audio mixer: scale the negative +B10 approach step for +AB8 before its target clamp
srcx 448B53 | 4487E0 audio mixer: scale the positive +B10 approach step for +AB8 before its target clamp
srcx 448B8C | 4487E0 audio mixer: scale the negative +B14 approach step for +ABC before its target clamp
srcx 448B99 | 4487E0 audio mixer: scale the positive +B14 approach step for +ABC before its target clamp
srcx 448BD2 | 4487E0 audio mixer: scale the negative +B18 approach step for +AC0 before its target clamp
srcx 448BDF | 4487E0 audio mixer: scale the positive +B18 approach step for +AC0 before its target clamp
srcx 448C18 | 4487E0 audio mixer: scale the negative +B1C approach step for +AC4 before its target clamp
srcx 448C25 | 4487E0 audio mixer: scale the positive +B1C approach step for +AC4 before its target clamp
srcx 448C5E | 4487E0 audio mixer: scale the negative +B20 approach step for +AC8 before its target clamp
srcx 448C6B | 4487E0 audio mixer: scale the positive +B20 approach step for +AC8 before its target clamp
srcx 448CA9 | 4487E0 audio mixer: scale the negative +58 approach step in the three-lane +ACC loop before its target clamp
srcx 448CB3 | 4487E0 audio mixer: scale the positive +58 approach step in the three-lane +ACC loop before its target clamp
gatefn 451A30 | 451A30 audio-channel update: keep the coupled remaining-update divisor, remaining count, pan approaches, start delay and lifecycle callbacks at exact stock cadence; both callers discard RAX and its body has no paced sites
pre 160E75 | 160D80 gallery: scale the complete signed analog zoom step after input shaping and division, before adding old +30 and clamping to one through 2.5
lin 1610CF | 160D80 gallery: scale the shared signed horizontal scroll rate once before zoom compensation and its seven layout accumulations
lin 1610D7 | 160D80 gallery: scale the independent image-pan rate before adding old +20
pre 1616EF | 160D80 gallery: scale the complete vertical analog/button pan step before adding old +24 and applying the zoom-dependent bounds
count 456A42 | 4569F0 scripted scene wait state one: pace the +32 timeout while the external readiness condition is still checked on every update
count 456A8A | 4569F0 scripted scene wait state two: pace the +32 timeout while the external readiness condition is still checked on every update
count 456BB3 | 4569F0 scripted scene wait state five: pace the +32 transition countdown and synthesize not-finished flags before its zero event changes the state
count 456C4A | 4569F0 scripted scene wait state six: pace the +32 transition countdown and synthesize not-finished flags before its zero event changes the state
count 456C9B | 4569F0 scripted scene wait state eight: pace the +30 transition countdown and synthesize not-finished sign flags before changing the state
