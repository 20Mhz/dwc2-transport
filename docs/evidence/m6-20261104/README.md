# M6 Apple TV characterization and diagnostic recovery — 2026-11-04

M6 passed on the physical Pi Zero W and owner-identified Apple TV A1427.
The manual cable test recovered descriptor reads after observed disconnects
and transient errors. The software issued only standard device-to-host USB
requests and cached sysfs reads. It issued no device reset, mode switch,
configuration change, driver detach, firmware or security-state command.

## Host, device and provenance

Host: Raspberry Pi Zero W Rev 1.1, ARMv6, kernel
`6.12.47+rpt-rpi-v6`, native DWC2. Device: `05ac:12a7`, high speed, sysfs slot
`1-1`, one configuration and interface `ff/fe/02`, bulk OUT `02` and IN `81`
with 512-byte packets, endpoint 0 with 64-byte packets. Configuration is
self-powered, reports 2 mA bus draw and no remote wakeup. No interface driver
was bound. Manufacturer/product strings were `Apple Inc.` / `AppleTV`;
configuration/interface strings were `Apple Mobile Device` /
`Apple USB Multiplexor`. Serial index 3 was skipped and redacted.

The source-backed database labels this identity `apple_tv_usb` with
documented-family confidence. The interface supports a descriptor-level
usbmux inference; no usbmux protocol traffic was tested. Physical A1427 model,
firmware, exact boot state and OS health remain unverified. See the pinned
[classification sources](../../m6-identification.md).

Release: **1.1.0**, unchanged C ABI major 1 / API 1.0. Identity database and
observer schema implementation are independently versioned 1.0.0.
The static SDK binaries were built from
`4d145b1b908c15af9783a36bbd1a6aa0959487e1`; their source and binary hashes are
in [BUILD_MANIFEST.json](BUILD_MANIFEST.json). The manual observer ran that
application revision. The automated capture ran application revision
`d713d411344e29b6896c121b0618984f1aec66b8`. Final evidence-verifier checks ran
at `2a0dd94`. [Capture context](capture-context.json) records this distinction.
HostLab was unchanged at `6df8d90`.

## Results

| Check | Actual result |
| --- | --- |
| Standard descriptors | Device, full configuration, interface, endpoints and four non-serial strings passed |
| Asynchronous descriptor reads | 25/25 successful |
| Independent SDK process starts | 5/5 successful |
| Traced control requests | 10/10 successful with complete SETUP/DATA/STATUS reconstruction |
| HostLab channels | 30 starts; 0 unattributed, 0 ambiguous |
| usbmon | 20 records, queued 0, dropped 0 |
| Trace session / teardown | No warnings / no errors |
| Passive baseline | 6 polls over 3 seconds; no probes, no errors |
| SIGTERM | Ready observer emitted signal summary and exited 0 |
| Physical reconnection | Two disappearances and two reappearances; recovered descriptor read |
| Raw and redacted manifests | SHA-256 verified; public evidence verifier passed |

The manual window ran at 0.5-second intervals with opt-in standard descriptor
probes and a 1200-second ceiling; it stopped automatically after 34 polls
(about 17 seconds). The owner unplugged only the USB cable and reconnected it
to the same Pi adapter, keeping power connected. The recorded sequence was:

1. Address 4 connected and passed its descriptor probe.
2. A cached sysfs read reported `no_device`, then the slot was absent.
3. Address 5 appeared; its standard control probe reported `protocol`.
4. The slot was absent again, then address 6 appeared and passed its probe.
5. The observer emitted a complete summary with reason `reconnected` and exited 0.

This is a recovery test with transient errors, not an error-free cable test.
The summary reports one cached-read error, two successful probes and one failed
probe. The two disappearance/reappearance episodes were not independently
explained; no cable, power or device fault is inferred. The recorded observer
version omitted errno for the failed control probe; the current implementation
preserves it when supplied by the SDK. No errno is invented for this log.
The automated full validation afterward saw address 7 and passed. Matching
topology/descriptors and operator context do not authenticate a physical unit.

Two earlier bounded observer windows ended before the operator response and
recorded stable presence only. They are retained in local raw storage and are
not counted as reconnection passes. No additional USB operating mode was
physically exercised. Timeout, malformed input, missing strings, identity and
binding changes remain automated-test coverage rather than fabricated hardware
observations.

## Software checks

| Environment | Result / log |
| --- | --- |
| macOS native sanitizers | 10/10 CTest targets passed: [log](software-native-final.log) |
| Linux sanitizers | 11/11 CTest targets passed: [log](software-linux-final.log) |
| ARMv6 static / QEMU ARM1176 | C unit, async, replay, descriptor and Python/CLI tests passed; ELF v6KZ checked; ARMv7 negative control rejected: [log](software-armv6-final.log) |
| Final Python changes | Observer 13, evidence 7, capture 6 tests passed: [log](software-python-final.log) |
| Installation | Installed tools, helper lookup, help and mock inspection passed: [log](software-install.log) |

The native/Linux/ARM logs precede the final Python-only evidence checks; C
build inputs and binary hashes stayed unchanged. The final Python tests cover
errno preservation, raw manifest validation and inconsistent reconnect claims.
No remote CI or remote Git push is claimed.

## Reproduce and verify

From the release root on the Pi, use fresh output directories:

```sh
sudo bin/usb-observe --bin ./bin --port 1-1 --duration 1200 --interval .5 \
  --probe-on-connect --kernel-errors --stop-after-reconnect > /tmp/cable.jsonl
# While recording, manually unplug/reconnect only the data cable.
sudo python3 scripts/pi/m6-validate.py --bin ./bin \
  --raw-out .local-evidence/m6-new --bundle /tmp/m6-public-new \
  --hostlab /home/USER/dwc2-hostlab --port 1-1 \
  --observer-log /tmp/cable.jsonl
bin/usb-evidence-verify /tmp/m6-public-new
```

From the source tree, verify this checked-in export:

```sh
tools/usb-evidence-verify docs/evidence/m6-20261104/bundle
```

[bundle/result.json](bundle/result.json) records all checks, both observer
summaries and physical reconnect/probe outcomes.
[bundle/observer-1.jsonl](bundle/observer-1.jsonl) preserves the complete manual
window, including failures. [bundle/metadata.json](bundle/metadata.json) records
host, source and binary provenance. [bundle/inspection.json](bundle/inspection.json)
contains redacted descriptors and bindings. [bundle/trace-summary.json](bundle/trace-summary.json)
states the tracing limitation: the fast profile reconstructs phases using time
correlation and does **not** provide direct URB-pointer correlation or channel
numbers. Ten usbmon URBs are therefore unpaired with direct kprobe pointers;
that does not represent ten lost requests.

Full raw recordings remain in Git-ignored `.local-evidence/m6/` locally and in
the Pi release directory's `.local-evidence/`. The public bundle contains hashes
and paths to raw files, not the raw traces or serial descriptors. The original
capture-only and automated-validation manifests were preserved before adding
the manual log and writing a manifest for the combined raw collection. SHA-256
manifests establish file integrity, not authenticated provenance. The outer
manifest covers this report and software logs; the inner manifest covers the
machine-readable bundle. Release packaging excludes legacy raw evidence.
