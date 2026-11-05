# Apple TV discovery attempt, 2026-11-04

Result: **UNAVAILABLE**, not a hardware test pass.

Physical host: Raspberry Pi Zero W Rev 1.1, running Linux
6.12.47+rpt-rpi-v6. SDK binaries: deployed v1.0.0 source
`d8853d831bc2021c240fd2cd1ec0693528ac7d02`; hashes in metadata.json.
Capture began at 13:33:08 UTC (10:33:08 America/Santiago) and waited up to
120 seconds. All 61 Apple-profile discovery samples returned an empty device
list. The initial general inventory showed the root hub and CH340 1a86:7523.

No Apple device was selected, so no Apple TV descriptor reads, mode inference,
transfer regression or HostLab trace were executed. summary.json records
`state: unavailable`, `device: null`, and process return codes. The capture
process exited 2 by design. A physical cable connection is needed to continue.

The new bounded descriptor capture runner has four passing no-hardware tests
for absent/multiple-device gating, successful read reporting, failed transfers
and lost connections. These tests are separate from physical validation.
The runner's source hash is recorded in capture-script.sha256; the SDK itself
was not changed. SHA256SUMS verifies the captured output and local test log.
