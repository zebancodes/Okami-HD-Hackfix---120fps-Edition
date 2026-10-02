group objects
# cBallObj 33ABC0 loads a sole 0.1 factor into xmm6 at entry. All nine uses
# before its restore multiply persistent +E48/+E20/+E28 by that factor in
# three movement branches. Root the factor once for elapsed-tick damping.
root 33ACE5 | cBallObj: compound the shared 0.1 momentum decay for all three vector components in all three branches
