stock | 3F53F0: +350 counts 80-byte records in a bounded sentinel walk during table setup; it is a record count, not elapsed updates | 3F5416
stock | 3F68D0/403B20: add the caller-supplied amount to a numeric total and saturate to 0..999999999; these setters keep amounts in stock units and contain no autonomous step | 3F68D0 403B20
once | 417C90: B1F5F0 counts a newly posted loader notification; +58 becomes one in the same call and prevents a second count while that notification remains active | 417CD0
stock | 459C10: +80 is occupancy of an eight-entry request queue; append one 80-byte record and link it to the caller's selected bucket | 459C2D
once | 48C080/48C0D0/48C120: byte +1 changes zero to one immediately after initialization or starting an asynchronous operation; later calls only poll its completion | 48C0A6 48C0FC 48C146
stock | 496500/496530: apply caller-supplied health and maximum-health amounts to save-state +8 and +C; health clamps to current maximum and maximum health clamps to zero, with no autonomous tick step | 496521 496542
stock | 4337C0: save-state +14 receives the difference between the newly purchased upgrade level +299 and its previous level +29D, then +29D is overwritten with +299 in the same call | 4338BC
stock | 43E650/43E9A0/43ED00: clear +C0 to zero, count eligible entries in a bounded 256-item inventory scan, then build the displayed record list and set its row/page bounds | 43E6BD 43EA0E 43ED6D
stock | 5B6990 scene initializer: clear the scene record's +48 then tally five completed-condition flags, using the resulting zero-through-five count to select the scenario message | 5B6A67 5B6AD7 5B6B47 5B6BB7 5B6C27
once | ut71 5B0B20/5B0BE0/5B0C80/5B0D40/5B0DE0/5B0E60/5B0F20: +E37 advances zero to one after starting its motion and setting the part flag; subsequent calls only advance scaled motion or test its end | 5B0BB9 5B0C46 5B0D19 5B0DA4 5B0E44 5B0EFE 5B0F86
stock | et25 61F3E0: clear +10A0 each invocation and tally the six child resources whose asynchronous fade has completed; it is a fresh completion count, not elapsed updates | 61F43E
