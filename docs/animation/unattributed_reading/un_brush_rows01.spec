# The celestial brush's per-tick update 16C7E0 (the brush object 8909C0), 2026-09-30
group player
count 16CA1D | Brush techniques: hold each active technique's remaining ticks +128[id] (10, 30 or 120, copied from +124 when one is recognized) between stock ticks.
notyet 16CA1F notyet:16CA43 | Brush techniques: between stock ticks the held count's decremented copy in EAX must not end the technique; take the still-active path.
count 16CA8E (0x16CA84,0x16CA91,(0x16CA84,0x16CA8A,0x16CA8C,0x16CA8E),None) | Brush: pace the 300-tick window +D34 (174DB0) after which the repeat count +D30 resets.
count 16CF76 (0x16CF6F,0x16CF78,(0x16CF6F,0x16CF72,0x16CF74,0x16CF76),None) | Brush state 4: pace the wait +68 (60 ticks from 171940/174DB0) before the recognized technique is applied.
count 16D132 (0x16D12B,0x16D134,(0x16D12B,0x16D12E,0x16D130,0x16D132),None) | Brush state 5: pace the 60-tick wait +6C that evaluation mode 6 (174740) arms, before state 6 closes the brush.
count 16D28A (0x16D27C,0x16D28C,(0x16D27C,0x16D282,0x16D284,0x16D28A),None) | Brush idle: pace the 20-tick cooldown +E28 after the brush closes, before it can open again.
count 16D752 (0x16D748,0x16D755,(0x16D748,0x16D74E,0x16D750,0x16D752),None) | Brush drawing: pace the delay +21B4 that 1709B0 arms (with +21B0 = 1) before it signals +21B8 = 1.
count 16F097 | Brush: hold the counter +21DC whose multiples of 30 play sound 0x74, so the sound repeats once a stock second.
notyet 16F06A notyet:16F097 | Brush: the modulo-30 test reads the old +21DC; between stock ticks take the no-sound path so a held count plays 0x74 once.
count 170396 | Brush timed effect: pace the duration +1C (100 to 370 ticks from 174DB0, by the effect mode +18) before it stops.
blend 16F75F | Brush strokes: each entry's +0C approaches +10 by 0.25 of the gap a tick (at least 0.5, clamped): the approach's factor.
lin 16F767 | Brush strokes: the approach's minimum step 0.5 a tick.
lin 16F76F | Brush strokes: each entry's global +84565C grows by 3 a tick up to +845660.
