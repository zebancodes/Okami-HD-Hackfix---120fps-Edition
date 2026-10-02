group objects
# uta0, utaf and utb5 each use the same submodel-particle update: a short
# byte countdown, position from velocity, velocity drag/gravity, collision
# damping and state transition. Each is called once by its parent update and
# has no previously patched site inside. Pace the complete state loop.
gatefn 55CA10 | uta0: pace its submodel particle state loop on stock ticks
gatefn 56C470 | utaf: pace its submodel particle state loop on stock ticks
gatefn 56EA30 | utb5: pace its submodel particle state loop on stock ticks
