# Apple TV discovery on the Mac, 2026-11-04

The owner clarified that the Apple TV cable is connected to the Mac, not the
Pi. Read-only IORegistry discovery at 13:43:32 UTC (10:43:32 America/Santiago)
found nine USB devices. The only Apple VID entries were class-9 hubs
05ac:800b and 05ac:800c; no Apple TV, DFU (05ac:1227) or recovery
(05ac:1280–1283) device was enumerated. State: **unavailable**.

`discovery.json` preserves the relevant Apple entries, host kernel, command,
timestamp and discovery count. It excludes unrelated device serial numbers
and the IORegistry root's unrelated system properties. SHA256SUMS verifies it.
`system_profiler SPUSBHostDataType -json` independently showed the same USB
inventory; this macOS version lists SPUSBHostDataType rather than the older
SPUSBDataType. The empty legacy report was not treated as proof of absence.

No Apple TV descriptor transfer or SDK hardware test executed. macOS registry
inspection is separate from Linux usbfs/DWC2 validation. A physical connection
that enumerates on the relevant host is required before testing can continue.
