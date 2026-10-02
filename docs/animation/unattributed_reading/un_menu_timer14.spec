# These sub-screen handlers use the menu's stock 60 Hz cadence.
group menu
count 6013CB | 601270: pace the +1B wait after 5FFF10 until 80 ticks or the user's advance input
count 601440 | 601270: pace the next +1B wait until 80 ticks or advance input
count 6014E4 | 601270: pace the third +1B wait until 80 ticks or advance input
count 601588 | 601270: pace the fourth +1B wait until 80 ticks or advance input
count 6015F1 | 601270: pace the +1B twenty-tick delay in state twelve
count 601644 | 601270: pace the +1B fifty-tick wait or advance input
count 6016DA | 601270: pace the next +1B fifty-tick wait or advance input
count 60173B | 601270: pace the +1B twenty-tick delay before the next message
count 60178C | 601270: pace the final +1B eighty-tick wait or advance input
lin 606B1B | 606A80 state three: scale the 19.66667 Y slide step during the three-tick page transition
count 606B28 | same transition: pace the +4 count until three updates and the reset to state one
lin 606B99 | 606A80 state two: scale the opposing 19.66667 Y slide step
count 606BA6 | same transition: pace the +4 count until three updates and the reset to state one
