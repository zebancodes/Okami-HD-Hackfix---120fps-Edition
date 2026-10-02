group objects
pre 56414C | uta7 platform: scale the complete positive passenger-load torque before adding it to angular velocity E14.
pre 564175 | uta7 platform: scale the complete negative passenger-load torque before adding it to angular velocity E14.
srcx 5641C6 | uta7 platform: scale the sustained secondary passenger torque when accumulating E14.
srcx 56420B | uta7 platform: scale the sustained opposing passenger torque when accumulating E14.
lin 564271 | uta7 platform: scale the height-error spring acceleration before subtracting it from E14.
count 5642FE | uta7 platform: commit the E3E force-duration countdown only on stock ticks; its decremented register and flags are not used after the store.
lin 5642F6 | uta7 platform: scale the sustained E3E acceleration while its countdown advances at stock cadence.
count 564358 | uta7 platform: commit the E40 force-duration countdown only on stock ticks; later code does not consume the decremented register.
lin 564350 | uta7 platform: scale the sustained E40 acceleration while retaining its force magnitude and duration in stock units.
lin 5643B2 | uta7 platform: scale the passenger acceleration in the alternate mode branch alongside its already corrected baseline acceleration.
lin 5643FF | uta7 platform: scale the coupled submodel spring force before the existing rate-correct 0.996 damping.
srcx 56445E | uta7 platform: integrate angular velocity E14 into submodel B8 with the current step duration before wrapping and clamping the angle.
pre 56309A | uta5 platform: scale the complete positive passenger-load torque before adding it to angular velocity E14.
pre 5630C3 | uta5 platform: scale the complete opposing passenger-load torque before adding it to angular velocity E14.
count 563182 | uta5 platform: commit the E3E force-duration countdown only on stock ticks; its temporary decremented value is unused afterwards.
lin 56317A | uta5 platform: scale the sustained E3E acceleration while retaining stock force duration.
count 5631E0 | uta5 platform: commit the E40 force-duration countdown only on stock ticks alongside the existing corrected force increment.
srcx 563252 | uta5 platform: integrate angular velocity E14 into submodel B0 with the current step duration before wrapping and boundary response.
