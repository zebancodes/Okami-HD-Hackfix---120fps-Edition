# Scripted task loops. task_waits.h already multiplies these wait(1) calls by N;
# the following loop body therefore executes once per stock tick.
once | 5868A0 is registered as a scripted transition callback by 4C0CD0; these three initial brightness raises happen only when the callback starts, before its first wait | 5868E4 5868FF 58691A
follows | 5868A0 loops on the brightness threshold and then opacity; the loop waits at 586960 and 586ADA are both selected task_waits.h loop calls, so these stores run once per stock tick | 5869B5 586A23 586A3E 586A59
once | 617E70 is installed as the same scripted transition callback for the other stage; these three raises precede its first wait | 617EB4 617ECF 617EEA
follows | 617E70 waits at 617F30 and 6180AA through task_waits.h before continuing the brightness and opacity loops; each subsequent pass is one stock tick | 617F85 617FF3 61800E 618029
follows | 530860 is a scripted scene transition: task_waits.h selects its wait(1) loop calls at 530A30 and 530B60, so these fades and the 30-pass counter run at stock pace; the first pass starts once before the waits | 5309C7 5309EB 530A96 530AA5 530AF7 530B07 530BBC
