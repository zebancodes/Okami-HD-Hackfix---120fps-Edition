group objects
# uta4 has three independent approach factors in its state-1 update. The
# +1110 wait is loaded into AX, conditionally decremented, then stored.
count 561067 (0x56105B,0x56106A,(0x56105B,0x561062,0x561065,0x561067),None) | uta4: pace the +1110 state wait
blend 56107D | uta4: compound the 0.05 scale approach
blend 5610B4 | uta4: compound the 0.1 XYZ target approach
blend 56112D | uta4: compound the 0.01 XYZ target approach

# ut65's whole helper advances one scripted submodel effect, with its pose
# transitions and angle step in the same update; no existing patch is inside.
gatefn 2217F0 | ut65: pace the scripted submodel effect update on stock ticks
