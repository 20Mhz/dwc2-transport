# M7 observations and local release candidate — November 4, 2026

The M7 software and local **1.2.0-rc1** candidate are implemented and tested.
Physical D1 baseline, D2 cable-only reconnection and D4 lifecycle tests passed.
Both `05ac:12a7` and shared recovery identity `05ac:1281` were observed at
different times. The intervening mode-entry sequence was not recorded or
attributed to a specific action; DFU operation was not tested. The earlier
reboot-confounded attempt is retained separately.

## Physical coverage

| Test | Result | Evidence |
| --- | --- | --- |
| D1 stable baseline | PASS: 16 polls in 8 seconds at 05ac:1281; one standard descriptor probe; no errors or state changes | [D1 recording](bundle/D1/result.json) |
| D2 independent-power cable reconnection | PASS: address 13 disappeared, address 14 appeared, descriptor probe passed; operator confirmed maintained power and no reboot | [D2 recording](bundle/D2/observer-0.jsonl), [operator context](bundle/operator-context.json) |
| D3 documented non-destructive recovery-state transition | NOT_RUN_NO_VERIFIED_PROCEDURE | [Manufacturer procedure assessment](../../m7-release.md) |
| D4 independent startup/termination | PASS: three fresh observers, each saw the target, emitted a signal summary and exited 0 | [D4 recording](bundle/D4/result.json) |

[bundle/result.json](bundle/result.json) reports
`physical_validation_complete=true` for D1/D2/D4 and
`manual_state_transition_complete=false` for D3. The verifier distinguishes file
integrity, physical coverage and a documented mode-entry test. It rejects
promotion of D2 to PASS without explicit operator confirmation of cable
reconnection, maintained power and no reboot.

D2 ran with 0.5-second polling, opt-in standard descriptor probes, a 900-second
ceiling and stop-after-reconnect. It ended after 892 polls, approximately
445.92 seconds. It recorded one disappearance/reappearance pair, two successful
probes and no probe or sampling errors. The observed absence interval was
approximately 4.572 seconds; it is the interval between sampled observations,
not an exact physical unplug duration. Presence generation advanced from 1 to 2.
Transition cause remains unknown in the original event stream.

In the [earlier attempt](prior-attempts/D2-reboot/assessment.json), address 7
disappeared and address 8 returned. The operator reported needing a reboot
because the Apple TV appeared asleep and no remote was available. That attempt
cannot separate reconnection from reboot and remains inconclusive. Sleep is
operator-reported context, not a state established by USB descriptors. The later
cable-only repeat began after the operator manually woke the device, then kept
power connected throughout. Neither run establishes a cable/power/device fault
or explains M6's older transient error. M6 evidence remains unchanged and is not
counted as new M7 testing.

The [cleanup observation](cleanup.json), taken after the final recovery-identity
D1/D2/D4 runs, found no lingering M7 discovery, inspection or observer processes.
The collector also waited for and reaped each child. No automatic device
reset, configuration change, driver detach, mode switch or firmware/security
operation was issued.

## Provenance

Host: Pi Zero W Rev 1.1, hardware revision `9000c1`, ARMv6 Linux
`6.12.47+rpt-rpi-v6`, native DWC2. Both observed identities were high speed at
slot `1-1`, with EP0 64 bytes and no bound interface driver. Exact A1427 model,
firmware and boot state remain unverified. Serial descriptors were not requested
and sysfs serial was not read.

The [application-family baseline](additional-observations/D1-application/result.json)
records `05ac:12a7` with interface `ff/fe/02`, bulk OUT `02` and IN `81`,
512-byte packets. Its operating-state assessment remains ambiguous. The
[recovery inspection](recovery-inspection.json) records `05ac:1281`, two
interfaces and a 57-byte configuration. Interface 0 is `fe/01/02` with bulk
OUT `04`. Interface 1 is `ff/ff/51`: alternate 0 has zero endpoints, alternate 1
has IN `81` and OUT `02`, each 512 bytes. These are configuration alternatives;
the observer recorded alternate 0 active. No alternate-setting command was sent.

Recovery product/configuration strings were `Apple Mobile Device (Recovery Mode)`;
alternate-interface string was `Apple USB Serial Interface`. Serial index 4 was
redacted. The ID and descriptors are evidence of a recovery-associated USB
identity, not verified DFU operation or successful recovery-protocol commands.
[Inspection provenance](recovery-inspection-context.json) includes binary/source
hashes and the output file timestamp; [state observations](state-observations.json)
separate the two identities from the unobserved intervening transition.

| Recording | SDK binary source | Application source |
| --- | --- | --- |
| Final recovery D1 / D2 / D4 | `e1f9b5bbd684835e47420e9f87e1034c3f08cab7` | `7bc4a98c592c36b20f369abca7101d43c797e693` |
| Additional application D1 / D4 | `e1f9b5bbd684835e47420e9f87e1034c3f08cab7` | `2dbd67e9c060b1b2858331d89b0df80cd743ef59` |
| Earlier reboot-confounded D2 | `e31539effd3e71f2dda8aade14603b79df54f502` | `7732d973b88390dbb3a58b2452b96a9d6e1a1a3a` |

The earlier D2 preceded the static-archive ordering fix; C transport/diagnostic
behavior was unchanged. Final D1/D2/D4 exercised the resulting release binaries.
Later changes added structured invalid-report handling and a regression fixture
for the observed alternate interfaces. Exact helper and
binary hashes are preserved in each recording's metadata. `REVISION` and
`APPLICATION_REVISION` in the archive distinguish binary source from packaged
application/docs source.

The installed Pi HostLab tools report revision
`9f61353dff0b671a4c089461c55665ca8a74777c` through their installed `REVISION`
manifest; session/analyzer hashes are recorded. The local research checkout is
`6df8d90` and was not modified. M7 reuses sysfs/usbfs and optional kernel-log
enumeration errors; it does not repeat M6's tracing experiment or claim direct
URB-pointer correlation.

## Software and release checks

[software-validation.json](software-validation.json) records the coverage:
12 native and 13 Linux sanitizer/CTest targets passed. ARMv6 Make/QEMU tests,
ELF v6KZ checks and ARMv7 rejection passed. Final Python suites passed:
observer 19, evidence 7, M7 recording 7, privacy 2 and capture 6 tests.
Installed wrappers resolve the Python helpers/database; mock inspection passed.
Hosted CI was not run.

Two packages from identical inputs matched byte for byte. The source inside
the candidate rebuilt and passed its ARMv6 tests; the CLI binary and static SDK
library matched the supplied bytes after fixing incremental archive member
order. Supplied CLI objects and SDK library relinked successfully and ran under
ARM1176/QEMU. [BUILD_MANIFEST.json](BUILD_MANIFEST.json), [BUILD_IMAGE](BUILD_IMAGE)
and [TOOLCHAIN_PACKAGES](TOOLCHAIN_PACKAGES) record source, binary and environment
provenance. The archive includes MIT attribution, runtime license notices,
application source and relinkable objects.

## Verify, repeat and preserve privacy

```sh
tools/usb-evidence-verify docs/evidence/m7-20261104/bundle
```

See the [release guide](../../m7-release.md) for installed collection commands,
bounded retry policy, the cable-only procedure and operator-context
format. No remote is used by the observer: it requires ordinary USB enumeration,
which is checked before requesting physical action. Any manual wake/reboot must
finish before a clean cable-only window, with power maintained during that window.

Raw recordings and failed/preflight attempts remain local in Git-ignored
`.local-evidence/m7/` and the Pi release's `.local-evidence/`. Initial D1/D4
recordings are also retained locally and as additional public observations.
The reboot-confounded attempt is retained under `prior-attempts/`.
Exported recordings omit raw stderr and
contain raw-file hashes instead. Software build logs remain local because they
contain development paths. The outer manifest covers this report, software
summary, cleanup observation and the nested public bundle. SHA-256 establishes
integrity, not authenticated physical provenance. Public archive scans check
credential/key patterns, home paths, raw file types, structured serial fields
and known legacy serial encodings; arbitrary unknown secrets are not proven
absent. Git history and legacy raw captures are excluded. Nothing is published
or pushed.
