group objects
gatefn 22DAD0 | utbc airborne physics: run forces, contact correction, gravity, original 0.99 drag and position integration together at stock cadence; its caller discards the result.
pre 33BD04 | Ball object: scale the completed wind X impulse before accumulating persistent E20 velocity.
pre 33BD0C | Ball object: scale the completed wind Z impulse before accumulating persistent E28 velocity.
src 33BF86 | Ball object airborne physics: scale the complete random acceleration plus 0.2 gravity before subtracting it from vertical velocity.
pre 33BFA7 | Ball object airborne physics: scale the floor spring acceleration before adding it to vertical velocity.
src 33BFC7 | Ball object airborne physics: integrate vertical velocity by the elapsed share of a stock tick; its 0.98 drag is already compounded by decay_factors.
