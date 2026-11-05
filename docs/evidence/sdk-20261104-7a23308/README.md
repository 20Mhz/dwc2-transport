# SDK physical validation, 2026-11-04

Actual userspace SDK binaries built from `7a23308`, deployed over SSH to
Raspberry Pi Zero W Rev 1.1, ARMv6l, Raspbian 13, running kernel
`6.12.47+rpt-rpi-v6`, bound controller `dwc2`. Device CH340 `1a86:7523`,
full speed, interface driver `ch341`. `metadata.json` records binary SHA256s,
revision, UTC time and exact parameters. These files are actual Pi output.

| Check | Observed result |
|---|---|
| Full regression | 168 checks, 0 failures (`regression.stdout`) |
| Regression plus SIGTERM cleanup | 169 checks, 0 failures (`termination.stdout`) |
| Each regression's sync/async descriptor reads | 50/50 sync and 25/25 async, 18 bytes |
| Each regression's ep0 cancellation | 25/25 accepted, 25/25 CANCELLED, raw -2 |
| Each regression's bulk IN cancellation | 5/5 accepted, 5/5 CANCELLED, raw -2 |
| Each regression's bulk IN deadline | 5/5 TIMEOUT, raw cancellation -2 |
| Reset and descriptor recovery | 1/1 per regression |
| Close with pending control/reopen | 20/20 per regression |
| Close with pending bulk IN and subsequent descriptor | PASS per regression |
| File descriptor cleanup | before/after counts equal per regression |
| Separate startup/shutdown processes | 20/20, one descriptor per process |
| Diagnostic transfer batch | 50/50, no errors/timeouts |
| Configuration and product string | 39-byte config, 3 endpoints, `USB Serial` |
| Post-run binding | ch341 restored, same device path |
| Physical cable disconnect/reconnect | SKIP; no physical operator |
| Apple TV A1427 | unavailable, not tested |

`summary.json` records 28 subprocesses, all exit 0. `inspection.stdout` and
`post-discovery.stdout` are structured device/driver records.

HostLab session: `hostlab-session/`, analysis: `hostlab-analysis.json`.
30/30 successful control URBs, 90 channel starts, three phases reconstructed
per transfer, zero unattributed/ambiguous channel events. usbmon final stats:
60 recorded, 0 queued, 0 dropped. Session warnings [], teardown errors [].
Fast-profile limitations: no submit/enqueue pointer probes or channel-number
arguments; the analyzer reports 30 unpaired usbmon/kprobe instances. This is
not a direct URB-pointer-correlation validation; see docs/instrumentation.md.
Pi's deployed HostLab revision is `9f61353`, distinct from the local research
checkout `6df8d90`. No kernel/module/firmware changes were made by these runs.
