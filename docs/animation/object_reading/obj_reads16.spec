fixed | et2e 2EA790: the +1158 orbit phase's 0.05 step and +B4 rotation's 0.08 step are scaled before their wrap checks | 2EA7E2 2EA87B 2EAA4C
follows | et2e 2EA790: the conditional 6.28 subtraction only wraps a previously scaled +1158 or +B4 phase | 2EA7FC 2EA895 2EAA66
fixed | et2e 2EA790: the descending Y step is a scaled 0.25 and the capped +E37 stage counter increments on stock ticks | 2EA8F7 2EA950
once | et2e 2EA790: +E37 advances after its first orbit placement and selects the next stage; the +50 Y placement is in the subsequent one-time setup that resets +E37 and increments +E36 | 2EA85D 2EAA10
