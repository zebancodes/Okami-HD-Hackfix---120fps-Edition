group objects
blend 35D346 | objScroll 35D0E0: shared five-percent coefficient returns all three scale axes toward one in state five
blend 35BD8F | objScroll 35B840: alpha eases thirty percent toward the distance-derived visibility target clamped above zero
blend 35BDB9 | objScroll 35B840: alpha eases thirty percent toward one in the complementary distance branch
blend 221120 | ut65 221070: alpha eases twenty percent toward 0.3 or one according to player height
blend 230EA5 | utd7 230E20: alpha eases twenty percent toward the ground-dependent +1624 endpoint, retaining the height test's endpoint scaling
pre 231437 | utd7 231200: scale the complete clamped signed yaw step returned by 2DE0A0 before adding the old yaw and wrapping
srcblend 23146D | utd7 231200: root a copy of the +162C easing factor for X, leaving its already-paced ramp in stock units
srcblend 231492 | utd7 231200: root a copy of the +162C easing factor for Y, leaving the ramp and other axes unchanged
srcblend 2314B9 | utd7 231200: root a copy of the +162C easing factor for Z, leaving the ramp in stock units
blend 5600CF | uta4 55FFF0: ground height eases ten percent toward the higher of its ray result and the other object's height
count 5601BD | uta4 55FFF0: pace the three-frame material flipbook index; every update still copies the held index into the four materials and the index wraps at three
blend 5608E9 | uta4 5607A0: alpha eases five percent toward 0.6 in state one
count 560905 | uta4 5607A0: hold the positive +1110 cooldown decrement store; computed AX is discarded before the phase calculation
blend 560A95 | uta4 5607A0: X eases one percent toward the fixed placement X while outside the twenty-unit dead zone
blend 560AB9 | uta4 5607A0: Z eases one percent toward the fixed placement Z while outside the twenty-unit dead zone
count 560B4F | uta4 5607A0: hold the regular positive +1112 decrement store; AX is discarded before the external flag read
count 560B72 | uta4 5607A0: hold the flag-dependent extra +1112 decrement store; later conditions reload the stored field
blend 56F4FB | utb6 56F330: Y eases ten percent toward its already-paced sine phase plus the fixed ground offset
pre 56F5C3 | utb6 56F330: scale the complete clamped signed pitch step before adding the old pitch and wrapping
pre 56F5E1 | utb6 56F330: scale the complete clamped signed yaw step before adding the old yaw and wrapping
srcblend 56F697 | utb6 56F330: alpha eases twenty percent toward 0.4; copy XMM6's coefficient because it also supplies the stock motion-start rate
srcblend 56F6AE | utb6 56F330: alpha eases twenty percent toward zero in the far-distance branch, retaining the shared stock-unit coefficient
