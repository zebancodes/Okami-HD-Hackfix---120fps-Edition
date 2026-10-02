group objects
# cCockGameOver's three states count down a transition wait before dispatch.
count 3FCE4E | cCockGameOver: pace the first transition wait
count 3FCE9C | cCockGameOver: pace the second transition wait
count 3FCED3 | cCockGameOver: pace the third transition wait

# cSubScrFilesInfoWanted has an actual state-1 pause countdown. Its +64
# selection changes are driven by controller action tests.
count 4207FD down | cSubScrFilesInfoWanted: pace the state-1 pause countdown

# cSubScrItem state 1 fades a sprite byte by +16 each tick until 0x80.
count 40DA2A | cSubScrItem: pace the selected sprite's alpha fade
