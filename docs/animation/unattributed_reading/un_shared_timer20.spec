group menu
count 1C8F57 (0x1C8F50,0x1C8F59,(0x1C8F50,0x1C8F53,0x1C8F55,0x1C8F57),None) | 1C8F30 message manager: pace four delayed-release counters, synthesizing not-finished flags before freeing the resource on zero
count 1D391F | 1D3910 message-command pause: +1C counts forty-five updates then +57 becomes FF; pace the counter while completion reads its stored value
count 3E2C38 | 3E2B60 screen color fade: hold the +E progress store between stock ticks; byte colors are reconstructed from the old phase and fixed endpoints, and updated R10W is discarded
count 432A87 | 432A70 menu resource shutdown: pace the +34 countdown; cleanup reads the stored field and clears active +4A after freeing it
notyet 432AD4 notyet:432AE9 | 432A70: suppress the one-tick-remaining notification between stock ticks, so holding +34 at one cannot play the sound repeatedly
count 43C6FF | 43C6F0 menu dispatcher: pace the +8C notification delay while leaving input handling on every update
notyet 43C70F notyet:43C752 | 43C6F0: suppress the +8C-equals-one notification between stock ticks so holding the delay cannot repeat its sound
count 43FA9A | 43FA90 menu dispatcher: pace the +8C notification delay while leaving input handling on every update
notyet 43FAAA notyet:43FAFB | 43FA90: suppress the +8C-equals-one notification between stock ticks so holding the delay cannot repeat its sound
count 3D8ED7 (0x3D8ECA,0x3D8ED9,(0x3D8ECA,0x3D8ECE,0x3D8ED3,0x3D8ED5,0x3D8ED7),None) | 3D8EB0 camera controller: pace the positive four-tick +7 hold delay and keep all flag and input processing on every update
group actor
count 1DC143 | 1DC130: pace +1184's positive countdown; its zero event immediately reloads nine hundred stock ticks
count 1EC992 | 1EC980: hold the +1170 random-target delay store; the event tests the old EDX and reloads the field after drawing a new target
notyet 1EC998 notyet:1ECA9B | 1EC980: allow the random-target event only on stock ticks, including the old-counter-equals-zero call after the last decrement
count 2030D1 | 2030B0: hold the +1170 random-target delay store while preserving its old EDX event test
notyet 2030D7 notyet:20314C | 2030B0: gate the old-counter-zero event with its countdown so target selection and RNG draws have exact stock cadence
count 203190 | 203160: hold the +1170 random-target delay store while preserving its old R9D event test
notyet 203196 notyet:203217 | 203160: gate the old-counter-zero event with its countdown so target selection and RNG draws have exact stock cadence
count 203896 | 203890: pace the +1228 three-update particle-spawn period; the event reloads zero immediately so a held phase cannot repeat it
count 203C7A | 203C70: pace the +11B3 three-update particle-spawn period; the event reloads zero immediately so a held phase cannot repeat it
