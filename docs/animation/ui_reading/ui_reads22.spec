once | cOptionCalibration 146F40: its virtual slot 1 setup moves sprite 3A by 11 only when the detected controller product is type 4; this is part of option initialization | 1470E6
fixed | cOptionCalibration 147570: the +A2 sine gauge phase increments by five degrees only on stock ticks at 14776D | 147776
fixed | cOptionControllerSelect/cOptionPairing 147FF0: +80 elapsed ticks now increment only on stock ticks | 147FFF
stock | UI sprite collection 1B7500: +20 is the number of live elements found by scanning an array in this call, then used as a loop bound; it is recomputed from collection contents | 1B7585
stock | UI sprite collection 1B8590/1B8650: +C10 is the number of allocated entries, changed by one on insert and remove operations | 1B8628 1B86BF
fixed | cMcLoad/cMcSave 1BF1D0/1BF490: +200 is a request wait counter, now decremented on stock ticks in both request handlers | 1BF1F2 1BF4B0
