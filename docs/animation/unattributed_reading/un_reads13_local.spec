stock | 551DE0 once per B6AC20 value resets +60 to zero, then forms the circular mean of five actors' angular differences by incremental division by the sample count; 551F61 recomputes the current mean rather than advancing a clock | 551F61
stock | 5355E0 adds the full wrapped target-minus-current heading returned by 20E0B0, so 535625 aligns the actor to the target heading; it is a geometric correction | 535625
once | 652A10 and 652A50 change the bounded -3 to +3 command level at +1070, setting direction +1071; caller 648CE0 invokes them only after 1690C0 returns result two and 16A010 chooses result four to six, and 64A040 invokes the decrement during initialization | 652A10 652A50
stock | 603AB0 updates the selected entry index at +6 on cursor or page navigation: changes are plus/minus one, four, nine or twelve, bounded by the entry count in 7CE080, then decomposed by row and page for 605480; this is an item index, not a clock | 603D29 603D46 6040C1 604116 6041B1 604218 6042C6 60435E 6043D8 604456 6045CB
stock | 603AB0 603D58 writes the boolean inverse of the current +8 flag after a selection action; it is a toggle value | 603D58
stock | 6053E0 decrements the page index at +1; 6054D0 multiplies it by twelve to select the page's twelve entries from the menu table | 6053EA
stock | 608760 decrements the page index at +6; 608970 uses the result times seven to choose the next seven texture entries and their message IDs | 60876A
once | 50AEB0 increments +1 only while it is zero after setting the 3F2230 command state; subsequent calls skip the setup block | 50AEFE
stock | 607360 +5 is the selected entry index: navigation changes it by minus one, four, five or seven, uses modulo seven in 608800, and keeps it aligned with the +6 page index passed to 608970 | 60766D 6076B6 6076CA 607742 607922
stock | 606A80 +1 is the selected entry bounded by the entry count at 7CE172; +3 is the visible first-entry index, adjusted when the selected entry leaves the visible range and used in the row ID calculation plus seven or nine | 606C53 606CBD 60712D 607144
stock | 606A80 606EF3 toggles +40 with setne after a menu action and immediately updates the UI through 608220 | 606EF3
