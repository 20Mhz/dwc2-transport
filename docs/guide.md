# SDK operating guide

## Install

Download the ARMv6 archive and its `.sha256` file from the
[1.2.0 release](https://github.com/20Mhz/dwc2-transport/releases/tag/v1.2.0).
On the Pi:

```sh
sha256sum -c dwc2-transport-1.2.0-linux-armv6.tar.gz.sha256
tar -xzf dwc2-transport-1.2.0-linux-armv6.tar.gz
cd dwc2-transport-1.2.0-linux-armv6
sha256sum -c SHA256SUMS
bin/usb-discover --version
bin/usb-observe --help
```

The archive is a userspace bundle. Extraction does not change kernel modules,
boot configuration or target firmware. The C executables are static armel for
ARM1176 / ARMv6KZ. Python helpers require Python 3.9+ without pip dependencies.
macOS supports mock/replay development; physical transport requires Linux.

## Inspect and observe

```sh
bin/usb-discover --json
# Replace the example path with a current discovery result.
sudo bin/usb-inspect --device /dev/bus/usb/001/014 --json
# Cached sysfs observation; no USB requests.
bin/usb-observe --bin ./bin --port 1-1 --duration 30 --interval .5
# Opt in to standard IN descriptor probes and bounded retries.
sudo bin/usb-observe --bin ./bin --port 1-1 --duration 120 --probe-on-connect --probe-attempts 3 --retry-delay 1 --kernel-errors
```

Discovery needs no root access. Descriptor reads open usbfs O_RDWR and may need
`sudo` or a device-specific permissions rule. Serial descriptors are omitted by
default. Hub transfers are refused; oversized configurations report unsupported
rather than silently truncating. Inspection and observation never claim/detach
interfaces, switch modes, select alternate settings or reset the target.

| Observation | Response |
| --- | --- |
| Device disappeared / stale address | Rediscover and reopen the current path; keep the failed read |
| Protocol error or timeout | Preserve actual status/errno; use bounded descriptor retries without assuming a cause |
| Permission failure | Correct local access permissions; repeated USB retries cannot fix it |
| Discovery/cached-read failure | Record unknown state rather than claiming absence |
| SIGINT/SIGTERM | Finish bounded child work, emit the final summary and reap processes |

The observer is limited to one hour and 10,000 samples. Default probing allows
three attempts per observed state. A signal can wait for a child's remaining
deadline. A stable result does not prove the device is in a particular boot mode.

## Record a verifiable session

Use a fresh private output directory on the Pi. HostLab remains an external
installation; no HostLab kernel functionality is added by the SDK.

```sh
sudo python3 scripts/pi/m8-validate.py record --bin ./bin --hostlab /home/USER/dwc2-hostlab --out .local-evidence/m8-run-1 --port 1-1 --duration 30 --interval .5
sudo python3 scripts/pi/m8-validate.py export --raw .local-evidence/m8-run-1 --out /tmp/m8-public-run-1
bin/usb-evidence-verify /tmp/m8-public-run-1
```

The collector checks provenance, DWC2, cached-read consistency, disk space,
serial omission and successful standard descriptor access. It records each
sampling window and writes a timeline. `PASS` means the capture is complete and
consistent; `identity_change_captured` separately reports its experimental result.
Raw stderr and annotation input remain local; exports include redacted events
and raw-file hashes. Checksums provide integrity, not authenticated signatures.

On the recording Pi, an operator can annotate an action they actually performed:

```sh
sudo bin/usb-annotate --session .local-evidence/m8-run-1/session.json --action cable_reconnected
```

An annotation is an operator statement and performs no device action. Timing
windows bound kernel observations, with unmeasured enumeration/cache latency.
Short transitions between polls can be missed. No verified non-destructive
mode-entry procedure is currently prescribed. See the
[session reference](m8-sessions.md) and [identity assessment](m8-identities.md).

## Build and reproduce

For ordinary C development, use the [README build commands](../README.md#quick-start).
For sanitizer checks, configure a separate build with `-DDT_SANITIZERS=ON`.
`make all test` is also supported. CMake installs headers, library, tools,
Python helpers, pkg-config and the `DWC2::dwc2_transport` target.

The ARMv6 build requires Docker and Python 3:

```sh
scripts/build-armv6.sh
```

It checks ELF attributes, runs ARM1176/QEMU tests and rejects an ARMv7 negative
control. CI validates native and ARMv6 builds. Release packaging is a separate
operation using the audited toolchain and pinned runtime source materials.

For full archive reproduction, extract the release's **source archive**, which
includes runtime corresponding sources, then run:

```sh
DT_BUILD_IMAGE=dwc2-transport-build scripts/build-armv6.sh
scripts/package.sh
```

A Git checkout also supports packaging when the files listed in
`data/runtime-source-manifest.json` are available in `build/runtime-sources/`.
Their sizes/hashes and the recorded runtime package versions must match.
Compilation downloads no runtime sources. Docker image creation can download
build tools; updated Debian packages can require a new corresponding-source audit.

`REVISION` identifies compiled SDK provenance; `APPLICATION_REVISION` identifies
packaged helpers/docs. Manifests record exact input/output hashes, image ID and
toolchain versions. The source archive supplies verified `SOURCE_INFO.json` for
builds without Git. Packaging normalizes timestamps, ownership and file order:
fixed inputs reproduce archive bytes, while different compilers may change them.

Archives include source/relink objects, MIT/HostLab attribution, GNU runtime
notices and corresponding sources. Descriptor signatures were not independently
verified and the runtime itself was not rebuilt during validation. Privacy checks
cover known serial encodings, private paths, raw traces and credential patterns;
they do not prove arbitrary secrets absent. Raw development captures and their
Git history are excluded from the distribution snapshot.
