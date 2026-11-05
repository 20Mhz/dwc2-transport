# 1.2.0-rc1 — M7 release and operating guide

Historical RC1 reference. For SDK 1.2.0 use the [current operating guide](guide.md)
and [release notes](releases/1.2.0.md); version and publication statements below
describe the M7 preparation stage.

This is a local release candidate for conventional USB diagnostics. The transport
C ABI remains major 1 / API 1.0. The observer is 1.1.0 with event schema 2;
the identification database is independently versioned 1.1.0. No publication or
remote Git push is part of preparing this candidate.

## Supported hardware and evidence

| Platform / device | Support and limits |
| --- | --- |
| Pi Zero W Rev 1.1, ARMv6 / Linux 6.12.47+rpt-rpi-v6 / DWC2 | Native usbfs physically validated; static ARMv6KZ binaries and ARM1176/QEMU checks |
| Owner-identified Apple TV A1427, 05ac:12a7 | Standard descriptor inspection and passive state observation; exact model, firmware and boot state unverified |
| CH340 1a86:7523 on the Pi | Historical SDK regression coverage; M7 does not repeat its reset/bulk tests |
| Other Linux USB host controllers/devices | Conventional usbfs backend; physical compatibility not exhaustively validated |
| macOS | Mock/replay builds and application validation; no physical usbfs backend |
| Apple shared recovery identity 05ac:1281 | Physically observed in M7 with standard descriptor reads; entry mechanism, exact boot state and recovery-protocol behavior unverified |
| Other Apple recovery/DFU identities | Source-backed shared identifiers and simulated classification tests; DFU operation not physically validated |

[M7 hardware coverage](evidence/m7-20261104/README.md) distinguishes actual
recordings from pending operator actions. M6's 25 async reads, five process
runs and ten fully reconstructed control requests remain historical evidence;
they are not counted as new M7 results. Fast tracing provides time correlation,
not direct URB-pointer joins or hardware channel numbers.

## Build and install

Native development:

```sh
cmake -S . -B build/native -DDT_SANITIZERS=ON
cmake --build build/native --parallel 4
ctest --test-dir build/native --output-on-failure
cmake --install build/native --prefix /tmp/dwc2-sdk
```

Use a non-sanitized build for ordinary installation. The C SDK requires a C11
compiler and Linux headers; the observer, collector and verifier require Python
3.9+. Observer installation includes the Python helpers and identity database.
No pip packages are needed.

ARMv6 build from the source tree:

```sh
scripts/build-armv6.sh
scripts/package.sh
```

Docker is required for the supplied cross-build workflow. The base image digest
is pinned in `docker/Dockerfile`; the actual local image ID, Debian package
versions, flags, source hashes and binary hashes are recorded. The build verifies
ARMv6KZ ELF attributes, runs ARM1176/QEMU tests and rejects an ARMv7 negative
control. Build output is static armel. `SOURCE_DATE_EPOCH` is set from the source
commit. The package normalizes tar ownership, timestamps, order and gzip headers;
repackaging the same inputs produces the same archive bytes. Updated compilers
or Debian packages can change binary bytes; cross-toolchain bit identity is not
claimed.

Extract the archive into a user-owned directory on the Pi, then verify:

```sh
cd dwc2-transport-1.2.0-rc1-linux-armv6
sha256sum -c SHA256SUMS
bin/usb-discover --version
bin/usb-observe --help
```

`REVISION` identifies the compiled SDK; `APPLICATION_REVISION` identifies the
packaged helpers/docs. `BUILD_MANIFEST.json` hashes build inputs and binaries;
`APPLICATION_MANIFEST.json` hashes application/source files. `BUILD_IMAGE` and
`TOOLCHAIN_PACKAGES` identify the build environment. They are integrity and
provenance records, not authenticated signatures.

## Read-only diagnostic examples

```sh
bin/usb-discover --profile apple-tv-a1427 --json
sudo bin/usb-inspect --profile apple-tv-a1427 --device 05ac:12a7 --json
# Fully passive: discovery plus cached sysfs attributes/descriptors.
bin/usb-observe --bin ./bin --port 1-1 --duration 30 --interval .5
# Explicitly request standard IN descriptor probes, capped retries and backoff.
sudo bin/usb-observe --bin ./bin --port 1-1 --duration 120 \
  --probe-on-connect --probe-attempts 3 --retry-delay 1 --kernel-errors
```

usbfs reads need permission to open the device node O_RDWR, usually `sudo` or
a device-specific udev/group rule. No interface is claimed or detached by these
diagnostic commands. The reusable SDK also exposes explicit conventional OUT
transfers and reset APIs; the M7 observer/collector never invokes them.

## State classification and timing

`data/device-identification-v1.json` contains pinned public source references,
confidence, identity association and state assessment. The generated private C
table is checked against that file. The Python observer reads the same database.
Application, recovery, DFU, unknown and ambiguous categories are distinct.
For `12a7`, `identity_category=application` describes a family association and
`state_category=ambiguous` preserves the unknown operating state. Recovery and
DFU IDs come from public libirecovery definitions shared across Apple products;
their `state_verified=false` prevents a PID label from becoming a protocol or
security-state claim. Unknown Apple IDs remain unknown.

Schema 2 records sequence numbers, UTC and monotonic timestamps, elapsed time,
presence generations, previous addresses, observed absence durations and state
transition durations. Timing spans sampled observations; it is not the exact
physical cable-removal time. Every observed failure is retained, including
repeated identical failures. Transition causes remain `unknown`. A topology
slot and matching descriptors do not authenticate a particular physical unit.

An observed absence followed by the same USB address creates a new presence
generation. Address changes without a sampled absence are state changes. An
unplug/replug entirely between polls with unchanged observations can be missed;
the observer does not invent a disconnect. Discovery failure is unknown state,
not proof of device absence. Incomplete cached descriptors cause explicit errors.

M7 also observed `05ac:1281` after the earlier `05ac:12a7` recordings. These
were observations at different times; the intervening transition was not
continuously recorded and is not attributed to a particular operator action.
The shared recovery-ID association comes from the pinned database sources.
Standard descriptor access does not verify recovery commands or DFU operation.

## Error and recovery guide

| Observation | Diagnostic behavior / operator action |
| --- | --- |
| `no_device` / stale usbfs path | Record failure, rediscover current topology/address, open a fresh inspector process |
| `protocol` with errno, such as EPROTO | Preserve actual status/errno and failed attempt; use bounded standard-read retry; cause remains unknown |
| Timeout | Reap the bounded child command, record observer/subprocess timeout; do not infer a USB timeout errno that was not returned |
| Permission or privacy failure | Record the observer/device domain; stop retrying that operation; fix permissions or tool-version mismatch |
| Retry exhaustion | Emit `descriptor_probe_exhausted`; mark recording incomplete; no reset is attempted |
| Driver/configuration/interface change | Emit changed fields and a fresh snapshot; do not detach/reconfigure the device |
| Kernel log unavailable | Record facility warning; preserve remaining observations |
| SIGINT/SIGTERM | Stop sampling, finish/reap bounded child work, emit final summary |

Default probe policy is at most three attempts per newly observed state, with
1- and 2-second retry delays. CLI bounds are 1..10 attempts, initial delay
0.05..30 seconds, delay cap 30 seconds, duration at most one hour and 10,000
samples. New state/generation starts a new bounded operation. Each attempt and
retry schedule is explicit. Child timeout is capped by the remaining run budget.
Signal shutdown can wait for the bounded child deadline; the collector escalates
to killing its process group if graceful shutdown cannot finish.

The M6 address 4→5→6 sequence shows software recovery after a protocol error.
It does not establish cable, power, controller or device fault. The old error log
omitted errno; M7 preserves errno when provided and does not backfill that result.

## Manufacturer procedures and the operator

Apple's [model page](https://support.apple.com/en-us/101605) associates A1427
with third-generation Apple TV and its micro-USB service port. Apple's
[warning/restore procedure](https://support.apple.com/en-au/108807), reviewed
November 4, 2026, documents disconnecting HDMI/power, attaching a data-capable
micro-USB cable, and reconnecting power for that generation. The subsequent
Restore action reinstalls software and is outside this milestone.

No applicable manufacturer-documented, non-destructive procedure that guarantees
entry into a distinct USB recovery state was verified. The documented connection
preparation does not promise a PID change or DFU operation. Third-party repair
guides, such as [Leawo's guide](https://www.leawo.com/pt/assets/pdf/iosfix.pdf),
describe remote-button sequences; those are third-party reports, not verified
Apple instructions for this unit. Their mode claims are not used as physical
evidence and their sequences are not prescribed here.

For the safe cable test: leave Pi and Apple TV power connected; after the
collector prints `ready`, unplug only the USB data cable, wait about three
seconds, reconnect it to the same Pi OTG adapter, and let observation finish.
All physical buttons/cables/power remain under operator control. D3 remains
`NOT_RUN_NO_VERIFIED_PROCEDURE`; unavailable cable intervention is
`PENDING_OPERATOR`. A stable recording cannot be promoted to a recovery-state
pass. No software state-entry, restore, firmware or bypass command is provided.

## Evidence collection and privacy

From an installed release, choose fresh local paths:

```sh
sudo python3 scripts/pi/m7-validate.py record --bin ./bin \
  --hostlab /home/USER/dwc2-hostlab --out .local-evidence/m7-D1 \
  --test D1 --duration 8
sudo python3 scripts/pi/m7-validate.py record --bin ./bin \
  --hostlab /home/USER/dwc2-hostlab --out .local-evidence/m7-D2 \
  --test D2 --duration 900
sudo python3 scripts/pi/m7-validate.py record --bin ./bin \
  --hostlab /home/USER/dwc2-hostlab --out .local-evidence/m7-D4 \
  --test D4 --duration 10 --iterations 3
python3 scripts/pi/m7-validate.py assemble --out /tmp/m7-public \
  --recording .local-evidence/m7-D1 --recording .local-evidence/m7-D2 \
  --recording .local-evidence/m7-D4 --operator-context /tmp/m7-operator.json \
  --pending-reason 'No verified non-destructive recovery-entry procedure'
bin/usb-evidence-verify /tmp/m7-public
```

`/tmp/m7-operator.json` records the actual operator report. For D2, use the
following values only after the operator explicitly confirms these conditions:

```json
{"D2":{"source":"operator_report","cable_reconnected":true,"power_maintained":true,"reboot_reported":false}}
```

If a reboot was needed, record `reboot_reported=true` and leave
`power_maintained=null` when uninterrupted power is unverified. Re-enumeration
and descriptor recovery can still be verified, but the cable-only test is then
`INCONCLUSIVE_OPERATOR_REBOOT`. Without confirmation it is
`PENDING_OPERATOR_CONFIRMATION`. The verifier rejects a manual cable-only pass
whose operator conditions are missing or contradictory. These reports are
operator statements, not independent authentication of the physical action.

Each recording includes exact SDK/application/installed HostLab revisions,
hardware revision, kernel/controller, binary and helper hashes, parameters,
full event history, errors, actual return codes and a completion manifest.
The minimal Pi need not have Git installed: installed HostLab's `REVISION` and
tool hashes are recorded. Unknown provenance prevents a pass. D4 launches and
reaps independent observers; it never resets hardware. Failed/aborted attempts
remain local with their actual status and are not silently relabeled.

The inspector skips serial descriptors by default, including aliases with other
string roles. The observer never reads the sysfs serial attribute. Raw stderr
stays local; exported recordings contain sanitized structured observations and
raw-file hashes. Public verification checks ordering, completeness, generations,
current-address probe recovery, outcome consistency, controller provenance and
nested manifests. Simulation tests are labeled in test source and are not bundled
as physical observations. Public documentation and engineering inference remain
separate from observed device states.

`PUBLIC_AUDIT.json` records archive checks for credential/key patterns, private
home paths, raw file types, serial fields and known legacy serial encodings.
Pattern scanning cannot prove absence of arbitrary unknown secrets. The archive
omits Git history and legacy raw traces; existing local Git history contains
historical raw captures and is not a public source-push artifact. Publication
requires a separate authorization and review of the actual publication surface.

## License and attribution audit

Project SDK/helpers are MIT; HostLab adaptations retain the attribution in
`NOTICE`. The SDK does not ship HostLab experimental kernel patches. USB facts
and source URLs are recorded; complete external ID databases or Apple protocol
implementations are not vendored.

Static binaries contain Debian GNU libc/GCC runtime code. The archive includes
the toolchain's copyright notices, LGPL-2.1 and GPL license texts in `licenses/`.
The GCC runtime notice includes its runtime exception. Package versions, rather
than an old version string in an inherited copyright file, identify the installed
runtime. Application source/build scripts and relinkable `.o` files are supplied
under `source/` and `relink/`; there is no restriction against relinking modified
runtime libraries for personal use. GNU libc upstream source is available from
[Sourceware](https://sourceware.org/git/glibc.git); Debian source/patch history is
available from [Debian glibc sources](https://sources.debian.org/src/glibc/).

For example, from the release root with an ARM toolchain and a replacement libc:

```sh
arm-linux-gnueabi-gcc -march=armv6kz -marm -static \
  relink/tools/cli.o relink/tools/hostlab/jsonl.o \
  relink/tools/hostlab/clock.o relink/tools/diagnostics/descriptors.o \
  lib/libdwc2_transport.a -L/path/to/modified/armel/libc -o usb-inspect-relinked
```

The compiler still requires its matching startup files and runtime search path;
use a complete replacement sysroot/toolchain when changing those. The complete
application can also be rebuilt from `source/`. Toolchain executables, QEMU,
Docker image contents and external library source trees are not redistributed
inside this archive. This audit records supplied materials and component
licenses; it does not claim a hosted release has been approved or published.

## Release notes

1.2.0-rc1 adds explicit identity/state confidence, schema-2 ordered transitions,
observed timing and address-reuse generations, bounded transparent probe retries,
actual errno/domain/returncode preservation, stale-path rediscovery, strict M7
recordings, physical lifecycle collection, privacy scanning, deterministic
packaging, build-environment provenance, source and relink materials. Existing
M6 evidence and C ABI are preserved. No Apple protocol, recovery-state entry or
firmware functionality is introduced.
