# pl04 appendage state (3A6120)
fixed | pl04 appendage: +414C[part] advances along the preset path once each stock tick (count 3A62A9) | 3A62A9
fixed | pl04 appendage: +414C[part] counts down the 90-tick target follow once each stock tick; the old-value zero test is gated between ticks | 3A65A7
fixed | pl04 appendage: all six return-to-anchor approaches use xmm7's 0.3, adjusted at its 3A6661 load to 1-(1-0.3)^s | 3A6671 3A6692 3A66B4 3A671E 3A6740 3A6762
