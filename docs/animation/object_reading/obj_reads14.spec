once | et0f 2E4ED0 and 2E5030: +E36 advances after motion setup or an effect in separate stage helpers; the new stage selects the next helper on the following update | 2E4FAB 2E50F3
fixed | et0f 2E4ED0 and 2E5030: +1138 counts down only on stock ticks in both stage helpers | 2E4FB9 2E50F9
once | et73 2F6470: +E36 advances immediately after motion setup in this stage helper, before the new motion is advanced | 2F64E6
stock | et73 2F6470: +E10/+E18 are freshly computed as direction differences and divided by the current magnitude; they are normalized direction components, not accumulated animation steps | 2F6612 2F662A
fixed | et69 4D1350: +E36's 89-step effect cooldown now decrements only on stock ticks after being reloaded when the nearby-target test succeeds | 4D144A
once | ut0c 215E90 and 2162B0: +E36 advances once after sound/state setup or completion of a fixed 16-element cleanup loop; the next stage selects another handler | 215F8F 216312
once | ut2d 2193D0: +E36 advances immediately after motion setup in this stage helper | 21943D
fixed | ut6d 223F20: the +E35 sound cooldown and +E36 action countdown now decrement only on stock ticks | 224055 22408C
