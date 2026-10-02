once | 202C40 sets up a knockback (direction +E10/+E18 from the positions, its scale, speed +E48, heading snapped by 2DDF90 with a 2 pi limit plus a random jitter); its three callers (1E6D20, 1F4610, 1FAB80) call it once, in sub-state 0 before advancing +E36. 202DC0 moves by it each tick. | 202CF3 202D15 202D36 202D3A 202D70 202D7D
once | 23B9F0: +88 is the manager's phase; each increment is one transition after its action completes. | 23BA6F 23BAF1 23BB09 23BB31
fixed | 5FB060 (map 312's script update) is a gatefn row: everything in it runs once a stock tick. | 5FB843 5FB852 5FBA68 5FBA78 5FBA93 5FBC50 5FBE4D
fixed | vt79E318 sub-state 3: +D2C's 0.05 decrement is lin row 21F65B (8 bytes before the store). | 21F663
fixed | vt79E318 slot 5 copy: +D2C's 0.05 decrement is lin row 21F96B. | 21F973
once | Map scripts' init functions (the +08 field of their 7AD9B0 records) run once when the map loads. | 58FAE7 5A238A
