# Optional Apple TV A1427 read-only profile

Historical initial-profile record. Current classification and evidence limits
are summarized in the [M8 identity assessment](m8-identities.md). In database
1.2.0, `12a7` has an application-family association and an ambiguous state;
the earlier `apple_other_or_unknown` label below describes the initial release.

```
usb-discover --profile apple-tv-a1427 --json
usb-inspect --profile apple-tv-a1427 --device /dev/bus/usb/001/003 --json
usb-diagnostics --profile apple-tv-a1427 --device /dev/bus/usb/001/003 --json
```

The profile discovers all devices with Apple VID 05ac, reads publicly exposed
standard descriptors/strings, reports driver/connection status and labels
PID 1227 as DFU and 1280–1283 as recovery. These mode IDs are documented in
[libirecovery's public mode enum](https://github.com/libimobiledevice/libirecovery/blob/master/include/libirecovery.h).
No libirecovery code is linked/copied. Mode IDs are shared across Apple
products: they do not prove Apple TV model A1427. Verify the owned physical
model separately. Other Apple PIDs report apple_other_or_unknown.

The profile does not switch modes, claim interfaces, reset, write firmware,
issue class DFU requests or send vendor control requests. Descriptor requests
are the same SDK operations used for the CH340. A missing device produces
an empty discovery list (success); explicitly selecting a missing device
reports a structured no_device error. The initial CH340 release session had no Apple hardware. A subsequent physical
Apple TV session on 2026-11-04 exercised this profile on the Pi; see the
[hardware record](evidence/apple-tv-20261104-pi-readonly2/README.md).
The owner identifies the box as A1427; USB descriptors alone do not independently
verify the physical model.


## Bounded hardware capture

The Pi must physically enumerate the Apple TV before descriptor tests can run.
Replace the CH340 on the Pi's USB host adapter with the Apple TV connected by a
data-capable micro-USB cable. The third-generation Apple TV also needs its
separate power cord; see [Apple's connection guidance](https://support.apple.com/en-ie/108807).
Use only the cable/power connection steps for these diagnostics.

From the SDK source checkout on the Pi, using an existing binary deployment:

```sh
sudo python3 scripts/pi/apple-tv-diagnostics.py \
  --bin /home/USER/dwc2-transport/dwc2-transport-1.0.0-linux-armv6/bin \
  --out /tmp/apple-tv-capture-1 --wait-seconds 120 \
  --hostlab /home/USER/dwc2-hostlab
```

The runner checks discovery for up to 120 seconds, selects a single Apple
USB device, inspects public descriptors, performs 25 asynchronous descriptor
reads, launches five independent one-read processes and, when requested,
collects ten descriptor reads with the existing HostLab instrumentation.
It records return codes, output, SDK binary hashes, kernel/model and results.
Multiple Apple devices require an exact `--device` path. The physical A1427
model remains unverified by these USB IDs alone.

Exit codes: 0 = the observed descriptor checks passed; 1 = a diagnostic failed;
2 = no Apple device appeared or an exact selection is needed. An unavailable
physical device never counts as a passing hardware test. The runner uses no
reset, interface claim, DFU class request, firmware action or mode-switch command.

## A device connected to a Mac

The SDK's physical backend is Linux usbfs; macOS supports the mock backend.
For a cable attached to a Mac, native IORegistry/System Information can first
confirm the device and its exposed USB identity. Those observations do not
validate the SDK's Linux transport. Use the Pi connection for that test.
Some current macOS versions use `system_profiler SPUSBHostDataType -json`;
check `system_profiler -listDataTypes` before interpreting an empty legacy
`SPUSBDataType` report. Distinguish Apple class-9 USB hubs from an Apple TV.


## Observed Apple TV identity

The tested device enumerated as **05ac:12a7**, high speed, product `AppleTV`,
manufacturer `Apple Inc.`. It exposed one configuration and one interface with
two 512-byte bulk endpoints. Descriptor inspection did not claim or transfer
data on those endpoints. PID 12a7 remains `apple_other_or_unknown` in the mode
classifier: it is not one of the profile's known DFU/recovery IDs. The test
does not certify entry into either mode.

A Pi reboot initially left usbmon unloaded. The first run passed device reads
but had incomplete trace evidence. That initial record is preserved; the
capture runner now requires actual observed URBs/phases, zero drops and clean
instrumentation teardown when `--hostlab` is requested. A missing observer can
no longer become an overall capture pass just because the subprocesses exit 0.

The final repeat passed all checks: 25/25 asynchronous descriptor reads,
five process restarts, and 10/10 instrumented control URBs with three phases
each, zero usbmon drops and clean teardown. SDK source stayed at the validated
v1.0.0 release; the capture harness fix did not change the transport ABI.
