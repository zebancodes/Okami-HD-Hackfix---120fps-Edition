group menu
# The item sub-screen's two branches brighten RGB/alpha bytes by 16 on
# each menu tick until the alpha reaches 128.
count 40E07E | cSubScrItem state 2 sprite 12 red: step once per stock menu tick
count 40E090 | cSubScrItem state 2 sprite 12 green: step once per stock menu tick
count 40E0A2 | cSubScrItem state 2 sprite 12 blue: step once per stock menu tick
count 40E0C9 | cSubScrItem state 1 sprite 11 red: step once per stock menu tick
count 40E0DB | cSubScrItem state 1 sprite 11 green: step once per stock menu tick
count 40E0ED | cSubScrItem state 1 sprite 11 blue: step once per stock menu tick
count 40E0FB | cSubScrItem state 1 sprite 11 alpha: step once per stock menu tick
