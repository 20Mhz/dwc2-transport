# M8 state observation and 1.2.0 final local release

M8's software, physical read-only capture, cleanup, source-build and release
checks passed. The experimental result is **NO_IDENTITY_CHANGE_OBSERVED**.
The manufacturer-verified non-destructive state-entry step remains
**PENDING_VERIFIED_PROCEDURE**. No physical action was requested or automated;
M7's separate observations are not joined into a fictitious transition.

This report uses the milestone date November 4, 2026 in America/Santiago.
Recordings retain UTC timestamps, including November 5 UTC where applicable.

## Physical results

| Check | Actual observation |
| --- | --- |
| Host | Pi Zero W Rev 1.1, hardware revision 9000c1, ARMv6, Linux 6.12.47+rpt-rpi-v6, DWC2 |
| Preflight | Two consistent cached reads; sufficient free space; selected slot 1-1; serial not read |
| Final continuous session | 60 samples over approximately 30.001 seconds; configured interval 0.5 seconds |
| Sampling uncertainty | Maximum actual start-to-start gap 501,677,941 ns; individual read windows preserved |
| Identity | 05ac:1281, high speed, address 14 throughout sampled observations |
| Standard read-only probe | One successful inspection, default serial redaction; no interface/configuration changes |
| Changes/errors/warnings | No observed disappearance, reappearance or identity change; zero diagnostic errors and warnings |
| Operator annotations | None: no verified physical procedure was prescribed |
| Controlled interruption | Separate RC2 session became ready, handled SIGTERM, emitted signal summary, exited 0; collector reaped |
| Cleanup | No lingering M8 discovery, inspection or observer process |
| Physical mode-entry experiment | PENDING_VERIFIED_PROCEDURE; no non-destructive applicable entry sequence verified |

The final capture is [session/](session/), with [machine-readable timeline](session/timeline.json),
[timeline table](session/timeline.md), [events](session/observer-0.jsonl),
[preflight](session/preflight.json), [provenance](session/metadata.json) and
[result](session/result.json). The [interrupted session](termination/result.json),
[control outcome](termination-control.json) and [cleanup observation](cleanup.json)
are separate evidence. A prior RC2 stable capture is retained locally.

No interval is an exact electrical transition measurement. Cached reads have
start/end windows; scheduling and descriptor probes can widen intervals. No
transition was observed in this recording, so it supplies no before/after
transition bounds or causal explanation. A short event between polls could be
missed. Operator statements, when present, have separate report/ingestion times
and cannot independently prove a hardware action. See the
[session methodology](../../m8-sessions.md).
Kernel enumeration/cache latency is unmeasured; the intervals bound observations
and do not establish bounds on the earlier physical cable or power action.

## Identity conclusions

`12a7` remains an application-family/usbmux descriptor association with ambiguous
operating state. `1281` is a source-backed shared recovery association whose
alternate-interface endpoints are consistent with published libirecovery code.
Its `fe/01/02` triple alone does not establish a matching standard DFU descriptor
set or execution of DFU operations. Exact A1427 model, firmware, boot/security
state and the mechanism behind the earlier identity difference remain
unverified. No recovery-protocol commands were issued. The
[concise identity assessment](../../m8-identities.md) cites USB-IF, project and
manufacturer sources and distinguishes their authority.

M6 and M7 evidence remains historical. M7's separately observed `12a7` and
`1281` sessions establish observations at different times, not their intervening
transition. M8's deterministic fixtures derive from those snapshots and are
explicit **simulations**, not experimental success. Annotations were tested in
software; no operator statement or mode-entry action was fabricated for this
physical capture.

## Source and software validation

The final session ran SDK/application source
`f4b559cb1f88dd2af775939828f72a1fa6accd21`. The interrupted RC2 run records its
own earlier source and helper hashes. Installed HostLab revision is
`9f61353dff0b671a4c089461c55665ca8a74777c`, reported by its installed revision
manifest with tool hashes. The supporting local checkout remains unchanged at
`6df8d90` on branch `main`; the SDK branch is `master`.

Later changes added a structured failed-preflight error path and its deterministic
regression. That failure path is software-tested, not claimed as a physical
unplug experiment. `REVISION` identifies compiled SDK source and
`APPLICATION_REVISION` identifies packaged helper/docs source. Binary and source
hashes are in [BUILD_MANIFEST.json](BUILD_MANIFEST.json); environment identity
and package versions are in [BUILD_IMAGE](BUILD_IMAGE) and
[TOOLCHAIN_PACKAGES](TOOLCHAIN_PACKAGES).

[software-validation.json](software-validation.json) records 14 native and 15
Linux sanitizer/CTest targets, ARM1176/QEMU and ELF checks, ARMv7 rejection,
targeted Python suites, installation and source-export reconstruction.
The source archive built using its wrapper without `.git` and reproduced the CLI
and static-library bytes. Hosted CI was not run. An early cleanup fixture raced
by writing in a signal handler; it was fixed to set a flag like the real observer.
Failed software/preflight/retrieval attempts remain local and are not counted as
physical passes.

## Release, privacy and acceptance

Final local version **1.2.0**, C ABI major 1 / API 1.0, provides separate source
and static ARMv6 archives, library/headers/tools/tests, identity database 1.2.0,
M6/M7/M8 summaries, runtime source/notices, relink materials and SHA-256 manifests.
Repeated archive construction uses normalized order, ownership and timestamps.
Matching binary bytes requires the recorded toolchain; arbitrary toolchain
updates are not promised identical output. [Release notes](../../releases/1.2.0.md).

`LICENSE_AUDIT.json` and `PUBLIC_AUDIT.json` accompany archives. Runtime archives
are checked against official Debian source-descriptor hashes; descriptor
signatures were not independently verified. Pattern scanning checks project
credential/key patterns, private paths, serial fields and known serial encodings,
but cannot prove absolute absence of arbitrary secrets. Nested upstream source
archives are hash-verified rather than recursively pattern-scanned. Raw stderr,
annotation inputs, private local captures and Git history are excluded from
public artifacts. Unique serials were omitted by default.

The outer manifest covers this report, acceptance/software summaries and nested
exports. Checksums establish integrity, not authenticated physical provenance.
[acceptance.json](acceptance.json) explicitly retains the pending procedure;
M8's criteria permit this documented experimental limit while completing
unrelated software/release work. Capture PASS is not transition PASS.

```sh
tools/usb-evidence-verify docs/evidence/m8-20261104/session
tools/usb-evidence-verify docs/evidence/m8-20261104/termination
```

See the [collection/reproduction guide](../../m8-sessions.md) for bounded
commands and annotation rules. Raw evidence stays in Git-ignored local storage
and the Pi's release evidence directories. No firmware/security state was changed
by the software. Nothing was published, remotely tagged or pushed.
