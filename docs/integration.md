# HostLab integration, P0

Inspected actual source and evidence at HostLab commit `6df8d90` (API 0.4).
HostLab has one existing untracked file, `docs/evidence/m4-20261102.zip`;
no HostLab files were changed. M0–M4 live in `docs/plan.md`, bringup,
architecture, M3 results and M4 feasibility/control/enumeration documents.

Reuse: MIT-licensed usbfs syscall mappings, sysfs enumeration, speed mapping,
standard descriptor defaults, virtual-time behavior and cancellation race
semantics from `src/lib/backend_linux.c`, `backend_mock.c`, `usb_backend.c`.
Adapted code is attributed in source and NOTICE. No HostLab dependency at
build or runtime. Public structures derive from the conventional HostLab
fields; the new opaque context/device API freezes ownership separately.

Stabilization needed: HostLab's process-wide default mock, caller-owned
transfer private pointers, incomplete pending-work cleanup on close, and
restarting poll timeouts after EINTR are unsuitable as a stable SDK contract.
The SDK owns contexts and transfer resources; instrumentation stays external.
No phase-hold, mapped DMA, authorization, port control or kernel ABI is exposed.

Evidence checked: `docs/evidence/m4-20261102/pend/baseline/{probe.json,user.jsonl}`
records Pi Zero W Rev 1.1, kernel `6.12.47+rpt-rpi-v6`, eight channels,
buffer DMA, `1a86:7523` and successful 18-byte GET_DESCRIPTOR results.
`pend/bulk-cancel/pend.json` records 5 cancellations, status -2 and five
channel releases; `recover/*`, `enum/reset/*` record reset/reattach recovery.
These are historical HostLab results, not SDK validation. Static research on
6.18.59 must not be treated as the running hardware kernel.

`hostlab-ctl` already does conventional control, asynchronous endpoint
submission, cancel and reset. `hostlab-mon` records usbmon; Python
`hostlab-probe`, `hostlab-session`, `hostlab-analyze` consume sysfs/tracefs
and correlate userspace timestamps, USB URBs and controller phases.
Keep using these tools as external processes and evidence readers; the SDK
never links to internal kernel structures or copies the tracing machinery.

Build reuse: the existing Docker image contains armel GCC and QEMU ARM1176.
Use static ARMv6KZ builds (ARM1176 supports this architecture) rather than
Debian armhf libraries that may require ARMv7. Deployment follows HostLab's
SSH/tar approach with SDK-specific paths and revision manifests.
