# M8 USB identity assessment

Both descriptor sets were physically observed on the owner-identified Apple TV
at the Pi's slot `1-1`; M7 captured them in separate sessions. That is not a
captured transition or independent authentication of the A1427 model.

| Observation | Source-backed association | Remaining uncertainty |
| --- | --- | --- |
| `05ac:12a7`, `ff/fe/02`, bulk OUT `02` / IN `81` | USB ID registry calls it a TV device; usbmuxd publishes the matching interface signature | Application-family association, ambiguous operating state; no usbmux exchange, firmware or model verification |
| `05ac:1281`, recovery product/configuration strings, interface 1 alternate 1 bulk IN `81` / OUT `02` | libirecovery lists `1281` as a shared recovery ID and its receive implementation uses interface 1/alternate 1 with IN `81` | Consistent descriptors, not proof that recovery commands work or that a particular boot/security state is active |
| Unknown identifiers | Unknown unless a referenced record exists | Apple manufacturer or a changed address does not imply DFU |

Primary project sources: pinned [USB IDs](https://github.com/usbids/usbids/blob/5eb613762db1e34b9218da63a88f22dd26f743c5/usb.ids),
[usbmuxd interface definitions](https://github.com/libimobiledevice/usbmuxd/blob/3ded00c9985a5108cfc7591a309f9a23d57a8cba/src/usb.h),
[libirecovery mode identifiers](https://github.com/libimobiledevice/libirecovery/blob/046344f7fe4413e42e71046a34230850be3f758a/include/libirecovery.h)
and [receive implementation](https://github.com/libimobiledevice/libirecovery/blob/046344f7fe4413e42e71046a34230850be3f758a/src/libirecovery.c#L3848).
These are primary sources for those projects, not Apple certification.

The [USB-IF DFU 1.1 specification](https://www.usb.org/sites/default/files/DFU_1.1.pdf)
defines a DFU-mode interface triple `fe/01/02`, but also specifies zero
non-control endpoints and a DFU descriptor set with one interface. The observed
`1281` configuration has two interfaces and bulk endpoints. Its class triple
therefore does not establish a matching standard DFU descriptor set, much less
execution of a DFU protocol or payload. No class/vendor commands, alternate
selection or protocol transactions were tested. Standard descriptors support
a provisional USB association; they do not authenticate firmware, hardware or
security state. Database 1.2.0 retains explicit confidence and
`state_verified=false`.

Apple's [model page](https://support.apple.com/en-us/101605) associates A1427
with third-generation Apple TV. Its [restore instructions](https://support.apple.com/en-au/108807)
document micro-USB/power connection preparation followed by a software restore.
Those pages do not establish a non-destructive sequence that guarantees entry
into a distinct USB identity on this unit. M8 therefore records
`PENDING_VERIFIED_PROCEDURE` and does not prescribe third-party button sequences.
Community mode claims are not promoted to physical evidence or used as device
instructions. The cause of the earlier identity difference remains unknown.
