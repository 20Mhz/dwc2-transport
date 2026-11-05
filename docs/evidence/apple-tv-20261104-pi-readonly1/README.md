# First actual Apple TV SDK run, 2026-11-04

Device discovered on the physical Pi after the owner moved it from the Mac:
05ac:12a7, product string `AppleTV`, manufacturer `Apple Inc.`, high speed,
/dev/bus/usb/001/003, DWC2. Board Pi Zero W Rev 1.1, kernel 6.12.47+rpt-rpi-v6.
SDK binaries are release source d8853d831bc2021c240fd2cd1ec0693528ac7d02;
metadata.json records hashes. The owner identifies the physical box as A1427;
USB identifiers alone do not independently verify this model.

Actual passed device checks:
- 18-byte device descriptor, USB 2.00, ep0 max packet 64.
- One 32-byte configuration, interface 0 with bulk OUT 0x02 and IN 0x81,
  each max packet size 512. Endpoints were described, not claimed or used.
- Manufacturer/product/serial string descriptor reads, language 0409.
- 25/25 asynchronous standard device descriptor reads, zero errors/timeouts.
- Five independent process restarts, each with a successful descriptor read.
- Post-run discovery matched the same device identity/address.

## Instrumentation gap and harness defect

The Pi rebooted during the cable move. Standard usbmon was not loaded afterward.
`hostlab-mon` exited 1 because /dev/usbmon0 did not exist. Ten additional SDK
reads succeeded, and ftrace recorded 30 channel starts, but usbmon recorded no
URBs and phase attribution was unavailable. session.json retains the warning;
hostlab-analysis.json reports 0 device URBs and 30 unattributed starts.

The original capture runner incorrectly emitted overall `state: passed` based
on subprocess exit codes. That raw summary is preserved as evidence of the
harness defect. It is **not** a complete instrumentation pass. The runner was
fixed to require observed transfers, exact phases, zero unattributed/ambiguous
channel starts, no drops, no session warnings and successful teardown. Six
no-hardware tests now include missing-usbmon, drop and incomplete-phase cases.
A fresh capture is required after enabling standard usbmon.

The profile reports `apple_other_or_unknown` for PID 12a7; it is not one of
its known DFU/recovery IDs. No class/vendor requests, endpoint traffic, driver
detachment, USB reset, firmware changes or mode-switch commands were used.
Raw string descriptor evidence includes the device-reported unique serial;
console/doc summaries omit its value. No remote repository push was performed.
