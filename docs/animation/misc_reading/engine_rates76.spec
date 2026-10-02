group actor
count 4B320B down | Area-gated event delay: count the positive +1C duration down only on stock ticks; a held tick must retain the not-complete JNE branch.
count 4B323E | Event cooldown +111: commit the decremented byte only on stock ticks; the function returns immediately after the store.
count 4B33C0 | Periodic positional sound: commit its thirty-tick cooldown only on stock ticks; the zero test before it schedules the next sound.
count 4BE6DB | Movie volume fade: commit the remaining-duration decrement at stock cadence, coupled to the original linear remaining-duration step.
count 4BE6E3 | Movie volume fade: commit the dependent volume step at stock cadence; the following code reloads the stored volume before applying it to middleware.
count 4C1194 | Script prompt timeout: advance its +8 frame clock only on stock ticks, retaining the 300-frame timeout.
count 4C15AE | Script prompt timeout: advance the first branch's +8 duration clock only on stock ticks before the 240/600-frame limits.
count 4C1695 | Script prompt timeout: advance the alternate branch's +8 duration clock only on stock ticks.
count 4C1A58 (0x4C1A51,0x4C1A5B,(0x4C1A51,0x4C1A54,0x4C1A56,0x4C1A58),None) | Script prompt countdown: gate the register decrement, store back to the same +8 field, and preserve the not-complete JNE outcome on a held tick.
