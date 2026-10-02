once | Motion-state entry advances E36 from zero to one immediately after selecting its motion; subsequent updates bypass initialization. | 20013C
once | Randomized facing initialization is enclosed by E36 zero, flips only the constructed relative direction, then advances E36 to one and sets the final wrapped angle. | 20024B 200282 200292
follows | E37 counts two completed motions, decremented only after the time-corrected 4B9C80 motion completion result. | 2002E7
stock | Resource data census resets +8C to zero, scans four bounded groups and counts matching B04/B16/B21/B2B/BB1 records; it is not a frame clock. | 2104E2 210541
stock | Heap release accounting increments the free-slot count only for a non-null object immediately before its destructor and release. | 211EEA
stock | Successful heap allocation decrements its free-slot count and updates a minimum watermark; the failed allocation path skips it. | 211FCA
stock | Registry removal decrements its population only after finding and clearing the matching registered pointer. | 23AB41
stock | Battle reset repairs a bounded signed inventory field after clearing the battle arrays; this is discrete reset bookkeeping. | 23AE3A
stock | Spawn census initializes the counters and pointer table at entry, then counts created slots while scanning four bounded groups of data records. | 23E466 23E488
once | Pooled actor activation clears the pending pool flag and hidden D40 bit before subtracting the matching 10000-unit hiding offset; the next update cannot activate that same pending slot again. | 23F15E
once | Movement setup copies the requested duration, computes three target-minus-position velocities and changes E35 to three; the initial duration decrement belongs to this setter invocation. | 2F5081
stock | AddXYZ constructs a fresh position from the linked model position and rotated data offset immediately before adding the fixed ten-unit Y offset. | 2FFB6E
once | Shared actor initialization zeroes its position and advances E36 from zero to one. | 305C9B
follows | E37 advances from zero to one only after 30F230 returns motion completion; that helper unconditionally advances the time-corrected 4B9C80 motion. | 308ACE 309C97 30A84E 30C2B0 30E36A
once | Death-effect phase entry initializes its motion or effects under E37 zero and advances E37 to one before subsequent updates. | 30AF46 30B1AE
once | Fixed-facing phase entry runs under E37 zero and advances E37 to one after initialization. | 30B9D5
once | Randomized wait construction selects sixty to eighty-nine ticks on phase entry and advances E37 to one. | 30D2FB
once | Randomized motion selection runs on phase-zero entry and advances E37 to one. | 30E0A3
follows | Linked-motion completion advances E37 from one to two only after 4B9C80 reports completion; phase two bypasses this increment. | 311535
stock | Resource request failure counts unsuccessful allocation attempts and resets the shared +1814 tally on success; the per-record retry cooldown controls attempt timing separately. | 313911 313B13
stock | Bounded registry insertion increments its length only after initializing the new record at old-count times 128, with a forty-eight-slot bound. | 314177
stock | Root-motion setup unconditionally calls 30F230 and therefore 4B9C80 before multiplying the freshly evaluated EC4 displacement by the fixed spatial factor one-half. | 315C97 3166E7
once | Actor phase entry toggles its +1324 selector under E36 zero and then advances E36 to one. | 316436 316796
