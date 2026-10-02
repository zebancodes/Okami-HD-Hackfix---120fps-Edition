once | UI sprite shift 1B2500: callers use fixed small dx offsets during initialization, controller changes, and panel setup; this loops through all elements once per layout change | 1B251E
fixed | cSubScrItem 40D910: sprites 13 and 14 now retain their previous +53 alpha on held ticks and multiply by the current factor once per stock period | 40D98D 40D9D8
fixed | cPictureBook 40D6F0: the +51 close-state sequence now progresses on stock ticks after starting the close action | 40D76E
fixed | cSubScrItem 424D40: the +3B image alpha now rises or falls by eight on stock ticks, retaining its old byte on held ticks | 424D9D 424DF5
