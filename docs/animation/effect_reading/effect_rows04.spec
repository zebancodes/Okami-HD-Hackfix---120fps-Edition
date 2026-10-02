group actor
# esp14 slot 1 updates age and position each tick.
count 1A3502 | esp14: advance the +2D8 age on stock ticks
pre 1A356E | esp14: scale the +174 displacement before adding to +164

# esp27 slot 1 transforms two velocity components into three position steps.
# Each product feeds one position addition, so scale the product result.
dst 1A912E | esp27 X: scale the +2D4 velocity product
dst 1A913F | esp27 X: scale the +2D8 velocity product
dst 1A9159 | esp27 Y: scale the +2D8 velocity product
dst 1A915F | esp27 Z: scale the +2D8 velocity product
dst 1A9170 | esp27 Y: scale the +2D4 velocity product
dst 1A9176 | esp27 Z: scale the +2D4 velocity product
