# Apple TV read-only hardware validation — PASS

Actual run on 2026-11-04 at 15:05:37 UTC (12:05:37 America/Santiago).
Host: physical Raspberry Pi Zero W Rev 1.1, ARMv6l, Linux
6.12.47+rpt-rpi-v6, bound controller DWC2. The owner identifies the target
as Apple TV A1427; that physical model is not independently verified by USB IDs.

Device: **05ac:12a7**, high speed, /dev/bus/usb/001/003, manufacturer
`Apple Inc.`, product `AppleTV`. No interface driver binding was reported.
SDK release source: d8853d831bc2021c240fd2cd1ec0693528ac7d02, API 1.0.
Capture runner includes the stricter trace validation at source 9c1213f.
metadata.json records exact binary hashes and the deployed runner source hash.

| Check | Actual result |
|---|---|
| Discovery and open | PASS |
| Standard device descriptor | 18 bytes, USB 2.00, ep0 packet size 64 |
| Configuration descriptor | One configuration, 32 bytes |
| Interface/endpoint descriptors | Interface 0, bulk OUT 0x02 and IN 0x81, max packet 512 |
| Device string reads | Manufacturer, product and serial accessible, language 0409 |
| Asynchronous descriptor batch | 25/25 succeeded, 18 bytes each, zero errors/timeouts |
| Independent process startup/shutdown | 5/5 succeeded, one descriptor each |
| HostLab observed descriptor batch | 10/10 succeeded |
| usbmon | 20 submit/complete records, 0 queued, 0 dropped |
| ftrace/phase reconstruction | 30 channel starts, all 10 control URBs have exact three-phase reconstruction |
| Unattributed/ambiguous channel events | 0/0 |
| Session warnings / teardown errors | [] / []; all registered HostLab probes removed |
| Post-run discovery | Same address and VID/PID, still high speed |
| Overall process result | 11 subprocesses, all exit 0; strict capture state passed |

The fast profile reconstructs channel phases by time correlation. It does not
install direct submit/enqueue URB-pointer probes or report channel numbers;
`usbmon_unpaired_with_kprobes: 10` is expected for this profile. This is not a
validation of direct pointer joins. See docs/instrumentation.md for that limit.

## Operations and boundaries

Only standard device-to-host GET_DESCRIPTOR requests were issued. Endpoint
addresses were read from descriptors; those endpoints were not claimed or
used. No resets, class/vendor requests, security sequences, driver detach,
mode-switch commands or firmware actions were performed. Normal process close
released all userspace handles. Physical unplug/replug resilience and deliberate
transfer cancellation were not part of this read-only profile.

PID 12a7 remains `apple_other_or_unknown`; it is not one of the profile's known
DFU/recovery PIDs. The run does not certify recovery or DFU mode operation.
Raw inspection output includes the device-reported unique USB serial; the
human summaries omit its value. Evidence remains local; nothing was pushed.

After the Pi reboot, usbmon was initially absent. The incomplete first capture
is preserved separately in ../apple-tv-20261104-pi-readonly1. The standard
in-tree usbmon observer was enabled at runtime for this successful repeat;
DWC2, firmware and persistent boot configuration were not changed. The runner
was fixed so missing usbmon or incomplete observations cannot count as an
overall trace pass; its six automated checks pass (runner-tests.log).

SHA256SUMS verifies the collected raw evidence and local runner test log.
