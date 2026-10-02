group actor
gatefn 5541D0 | Periodic encounter controller: pace its elapsed stage clock, exact threshold events, three recurring spawn delays and resets together at stock cadence; its sole caller discards the result.
count 49430B | Scene teardown: cases three and four are two empty update barriers around 35A0B0; pace these barriers while resource completion states remain live.
count 4AF8C0 (0x4AF8B9,0x4AF8C2,(0x4AF8B9,0x4AF8BC,0x4AF8BE,0x4AF8C0),None) | Integer ramp: pace its positive startup delay before the full-amplitude request.
count 49DD33 | Resource instance: pace its 90-tick timeout while load and completion polling remain live.
count 49DE86 | Resource instance: hold its 30-tick retry-delay byte between stock ticks; its following test reads the positive old EAX value.
count 49E0A6 | Companion resource instance: pace the corresponding 30-tick retry delay and preserve the old-value test.
count 49DCFE (0x49DCF7,0x49DD00,(0x49DCF7,0x49DCFA,0x49DCFC,0x49DCFE),None) | Resource manager: pace its positive five-tick readiness delay after polling all slots.
count 491699 | Dialogue controller: pace its 450-tick wait before starting the next request; the completion path switches phase to two.
