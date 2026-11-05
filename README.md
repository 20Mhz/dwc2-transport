# DWC2 Transport SDK 1.2.0

Experimental C11 USB host SDK for Linux and Raspberry Pi Zero W. It provides
native usbfs, deterministic mock/replay backends, diagnostic tools and bounded
USB observation. No external runtime library dependency or kernel patch is
required. Project code is MIT; HostLab reuse is attributed in [NOTICE](NOTICE).

**[Download 1.2.0](https://github.com/20Mhz/dwc2-transport/releases/tag/v1.2.0)** ·
[Operating guide](docs/guide.md) · [C API contract](docs/api.md) ·
[Documentation index](docs/README.md)

## Capabilities and compatibility

- Discovery, descriptors, control transfers and explicit interface ownership.
- Asynchronous control/bulk/interrupt transfers, completion, cancellation,
  caller-serviced deadlines and conventional reset APIs.
- JSON diagnostics, mock/replay fixtures and external HostLab instrumentation.
- Passive state observation, optional standard IN descriptor probes, operator
  annotations, sampling windows and verified session timelines.

| Platform | Coverage |
| --- | --- |
| Pi Zero W Rev 1.1 / ARMv6 / Linux 6.12.47+rpt-rpi-v6 / DWC2 | Physical usbfs validation; static ARMv6KZ release |
| Other Linux hosts | usbfs backend; hardware compatibility not exhaustively tested |
| macOS | Mock/replay development and tests; physical USB backend is Linux only |

The C ABI remains **major 1 / API 1.0**. Observer and identity database versions
are 1.2.0. Python helpers require Python 3.9+ and no pip packages; the C SDK
and compiled tools do not require Python.

## Quick start

Requires a C11 compiler and CMake 3.16+ (or `make`):

```sh
cmake -S . -B build/release -DCMAKE_BUILD_TYPE=Release
cmake --build build/release --parallel 4
ctest --test-dir build/release --output-on-failure
build/release/usb-inspect --mock --json
cmake --install build/release --prefix "$HOME/.local"
```

Use `find_package(DWC2Transport 1 REQUIRED CONFIG)` and link
`DWC2::dwc2_transport`, or use `dwc2-transport.pc`.
[Complete C example](examples/read_descriptor.c).

On the Pi, extract the ARMv6 release, verify its manifest and use a freshly
discovered USB path:

```sh
sha256sum -c SHA256SUMS
bin/usb-discover --profile apple-tv-a1427 --json
sudo bin/usb-inspect --device /dev/bus/usb/001/014 --json
bin/usb-observe --bin ./bin --port 1-1 --duration 30 --interval .5
```

Discovery and default observation use cached sysfs data. Inspection performs
standard descriptor reads and omits serial strings by default. usbfs reads
usually need `sudo` or suitable device permissions. These diagnostics do not
detach drivers, reset the target, select alternate settings or change firmware.
The reusable C SDK exposes explicit OUT/reset operations to its callers.

## Verified results and limits

CH340 regression coverage includes conventional transfer/cancellation/reset
checks. Apple TV descriptor reads and a power-maintained USB cable reconnect
passed on the Pi. The owner's A1427 identification, firmware and boot/security
state have not been independently authenticated.

| Apple USB observation | Supported conclusion |
| --- | --- |
| `05ac:12a7`, `ff/fe/02` | Apple TV / usbmux-family association; operating state ambiguous |
| `05ac:1281`, recovery strings and bulk interfaces | Shared recovery-associated identity; recovery protocol and DFU execution unverified |
| M8: 60 samples over 30 seconds at `05ac:1281` | Stable capture and interrupted-session cleanup passed; **no identity transition captured** |

The two identities were recorded in separate sessions. A verified,
non-destructive mode-entry procedure remains `PENDING_VERIFIED_PROCEDURE`.
Polling bounds describe kernel observations; they do not measure electrical
transition times. [Sources and identity limits](docs/m8-identities.md).

Native sanitizer, Linux contract, ARM1176/QEMU, source rebuild, archive
determinism and privacy checks passed locally. [Evidence and coverage](docs/README.md#evidence).
The release supplies ARMv6 binaries, library/headers, source, tests, manifests,
runtime notices/corresponding sources and relink objects. See the
[release notes](docs/releases/1.2.0.md) for provenance and remaining limits.
