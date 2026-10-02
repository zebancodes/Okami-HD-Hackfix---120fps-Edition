group objects
# et67 stores three fixed rates in .data; all RIP references to those words
# are these reads. Its U phases wrap by whole units after a scaled increment.
lin 2F1AC4 | et67 material 3 V: scale the 0.008 scroll step
lin 2F1B3E | et67 submodel 5 angle: scale the 0.03 rotation step
lin 2F1B63 | et67 material 4 V: scale the 0.008 scroll step

# wp2a and uta6 have one 0.1 channel step on each of two switch branches;
# each branch updates all three RGB components before its state check.
lin 396D48 | wp2a material 1 RGB: scale the downward 0.1 step
lin 396D90 | wp2a material 1 RGB: scale the upward 0.1 step
lin 562C77 | uta6 material 3 RGB: scale the downward 0.1 step
lin 562CCF | uta6 material 3 RGB: scale the upward 0.1 step
