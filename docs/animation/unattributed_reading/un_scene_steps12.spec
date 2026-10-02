# 5C4B00 is the scene-update callback installed by 5C5040 via 48C8E0.
# Each listed scalar is a movement amount used in one callback tick. The
# event branches at 5C4F5C are left to execute at their normal cadence.
group actor
lin 5C4B2D | e80/e82/e83 horizontal and vertical scalar movement, held in xmm6 until 5C4D26
lin 5C4B58 | e80 vertical step of 14
lin 5C4B85 | e81 horizontal step of 7
lin 5C4B94 | e81 secondary step of 2
lin 5C4BB1 | e81 vertical step of 8
lin 5C4BC7 | e82/e83/e85/e89 vertical step of 1, held in xmm7 until 5C4D9A
lin 5C4C2B | e84/e88 scalar movement of 2
lin 5C4C81 | e85 vertical step of 8
lin 5C4CAE | e86/e87 scalar movement of 2
lin 5C4CCF | e86/e87 vertical step of 8
lin 5C4CEC | e89 scalar movement of 0.5
lin 5C4D26 | e8a scalar movement of 3, held in xmm6
lin 5C4D63 | e8b scalar movement of 0.3
lin 5C4D84 | e8b vertical step of 1.5
lin 5C4D9A | e8c/e8e scalar movement of 2.5, held in xmm7
lin 5C4DC5 | e8c vertical step of 11
lin 5C4DE2 | e8d scalar movement of 5
lin 5C4E03 | e8d vertical step of 9
lin 5C4E19 | e8e/e8f scalar movement of 6, held in xmm6
lin 5C4E7E | e8f vertical step of 12
lin 5C4EA0 | e90 scalar movement of 0.2
lin 5C4EC1 | e90 vertical step of 0.6
lin 5C4EDE | e91 scalar movement of 14
lin 5C4EFF | e91 vertical step of 10
lin 5C4F1B | e81 horizontal step of 7 in the alternative scene mode
lin 5C4F2B | e81 secondary step of 2 in the alternative scene mode
lin 5C4F4F | e81 vertical step of 8 in the alternative scene mode
