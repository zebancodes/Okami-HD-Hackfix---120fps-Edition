group actor
# hm18/hm32 render callbacks repeatedly blend the submodel pose with the
# actor's +14F8/+1458 weight. Those weights already have scaled 0.2 updates;
# the pose blend itself must run once per stock tick to avoid compounding.
gatefn 31E070 | hm18: blend its submodel pose once per stock tick
gatefn 3259C0 | hm32: blend its submodel pose once per stock tick
