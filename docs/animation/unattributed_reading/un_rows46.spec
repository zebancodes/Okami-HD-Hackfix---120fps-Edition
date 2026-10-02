# 2026-10-01, seventh batch: the last of the unattributed candidates
group objects
# the map scripts' per-tick updates (the +18 field of their 7AD9B0 records) and what they call
count 5015C7 | Map 109's script (501560, from 501660 and 5099D0): pace the 20-tick delay B6D788+9C before a free slot of five is filled.
count 5428AE | Map 201's script (5427E0, from 547980): pace the 10-tick countdown B71D60+254.
count 54447A | Map 201's script (5443F0, from 547980): pace the 90-tick countdown B71D60+258 (the js after it cannot fire: the jne before the subtraction keeps 0 away).
count 579B02 | Map 207's script (579220): pace its tick count B72F58+4 (an event at 600).
count 58F5D5 | Map 20F's script (58F4F0, from 58FC20): pace the tick count 7A8CB0+8 (a flicker every 2 ticks, events at 30 and 60).
count 590FF5 (0x590FE5,0x590FF7,(0x590FE5,0x590FE9,0x590FEB,0x590FED,0x590FF5),None) | Map 301's script (590F10, from 5944E0): pace the countdown byte B73000+20.
count 596BA2 | Map 302's script (596AF0, from 598670): pace the 50-tick sound period B73010+22.
count 5971F6 | Map 302's script (597100, from 598670): pace the 90-tick sound period B73010+21.
count 597AF0 | Map 302's script (597A30, from 598670): pace the 30-tick sound period B73010+20.
src 59AC5B | Map 303's script (59ABA0, from 5A2620): an object's +D2C fades in by xmm7 a tick.
lin 5BCA47 | A map script (5BC850, from the update 5C1760): the angle +10 turns toward its target by at most 0.0698 a tick: the lower limit (threshold and step).
lin 5BCA54 | 5BC850: the upper limit 0.0698.
lin 5C24A9 | A map script (5C22D0, from the update 5C4300): the same turn's lower limit.
lin 5C24B6 | 5C22D0: the upper limit.
lin 622D84 | A map script (622D00, from the update 622C40): the objects' +D2C fades in by 0.05 a tick.
# other per-tick countdowns
count 50B0B6 | 50AF10 (from 50D3C0): pace the countdown +3B54.
count 50B3EE | 50B230 (from 50D3C0): pace the 120-tick countdown +3B54.
count 539CDA | 539C70 (state 2 of the state table 7C18A0): pace the countdown +1078.
src 5F81F0 | 5F8190, a task whose wait(1) loop (5F820B) stays per tick (task_waits.h left it a poll): an object's +D2C fades in by xmm6 a pass, in doubles.
group menu
count 6000B6 | Menu 600040 (from 600FF0): pace the 450-tick idle count +18.
notyetneg 6000BA notyet:600108 | Menu 600040: the limit test reads the old count (cx); between stock ticks take the not-yet path (jle).
count 601C46 | Menu 601B70 (from 600FF0): pace the 8-tick count +1B.
count 60216A reg | Menu 601D50 (from 600FF0): pace the alpha byte +3B's fade by 0x10 a tick (the subtraction in ecx; between stock ticks the old value is stored back).
