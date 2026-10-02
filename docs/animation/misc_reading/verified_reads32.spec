fixed | uta1 spring 55D010 is now gated as a complete update, including both velocity writes, Y integration and state countdowns; 55CECA ignores its return and no inner patch previously existed. | 55D0EA 55D113 55D120 55D1D6 55D253
fixed | et30 blend weight uses the scaled negative fade literal at 630BEF; both the raw +1260 sum and its 0..1 clamp follow that fade, while the cleared event bit still injects an immediate unit impulse. | 630C05 630C1F
fixed | et30 +125C frame advances through scaled source addition 630D64; XMM9 retains one for the terminal frame limit. | 630D7B
