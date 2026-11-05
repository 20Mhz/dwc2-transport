# Replay provenance

`hostlab-ch340.replay`: eight successful conventional GET_DESCRIPTOR(DEVICE)
records, extracted from HostLab commit 6df8d90,
`docs/evidence/m4-20261102/pend/baseline/user.jsonl`, using
`scripts/import-hostlab-replay.py --limit 8`. Original capture revision 7703dff.
Physical Pi kernel 6.12.47+rpt-rpi-v6; CH340 1a86:7523. Payload is a public
18-byte device descriptor with no unique serial number. Latencies are user
submit→done observations, not bus-only timing. Fixture is replayed on the
mock's 1209:0001 virtual identity, with CH340 response data; this is historical
replay, never a hardware SDK pass. HostLab's MIT license applies (LICENSE).

Original user.jsonl SHA256:
`429f1159dc3fab6f3464b9e2ba8e6c25872c555b039254f670551c837b760726`.
# M7 recovery-identity descriptor fixture

`apple-recovery-1281-descriptors.hex` contains only cached USB device and
configuration descriptor bytes from the Pi's November 4, 2026 observation of
`05ac:1281` (23:17:55 UTC, SDK source e1f9b5b / application 7bc4a98).
It contains no string descriptors or serial data. It exercises two interfaces,
including interface 1 with zero-endpoint alternate 0 and two-endpoint alternate 1.
Its recovery label is a shared public identifier association, not verified DFU
operation or a captured recovery-entry sequence. The original observation stays
local; M7 public evidence records the bounded descriptor/state observations.
