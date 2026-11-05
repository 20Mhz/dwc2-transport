# M8 bounded sessions, timelines and final release

M8 extends the existing observer rather than the C transport ABI. Default
`usb-observe` behavior remains cached sysfs observation. Sessions opt in to
standard IN descriptor probes and one compact record for every sampling window.
The application remains Python 3.9+ with no pip dependencies; the C ABI remains
major 1 / API 1.0.

## Collect on the Pi

From an installed release, choose a new private output directory:

```sh
sudo python3 scripts/pi/m8-validate.py record --bin ./bin \
  --hostlab /home/USER/dwc2-hostlab --out .local-evidence/m8-run-1 \
  --port 1-1 --duration 30 --interval .5
sudo python3 scripts/pi/m8-validate.py export \
  --raw .local-evidence/m8-run-1 --out /tmp/m8-public-run-1
bin/usb-evidence-verify /tmp/m8-public-run-1
```

Preflight checks current identity, two consistent cached reads, DWC2, kernel,
hardware/source/binary provenance, disk space and default serial omission.
Recording starts before any request for an operator action. The first successful
standard descriptor probe produces a `ready` message. The collector reuses
M7's bounded child management and signal handling; no device operation is
performed by a signal handler. Children are waited for and reaped. Capture output
is capped at 64 MiB, observation at one hour and 10,000 samples, with the existing
bounded probe retries. Incomplete or truncated output cannot verify as PASS.

Current manufacturer-procedure status is `PENDING_VERIFIED_PROCEDURE`; no physical
action is requested by the default recording. See the [identity assessment](m8-identities.md).
The absence of a captured identity transition is a valid experimental result,
not an inferred success. It does not prevent completing software/release work.

## Operator statements

Run annotation commands on the **recording Pi**, while the session is active.
The statement must describe an action actually reported by the operator:

```sh
sudo bin/usb-annotate --session .local-evidence/m8-run-1/session.json \
  --action cable_disconnected
sudo bin/usb-annotate --session .local-evidence/m8-run-1/session.json \
  --action cable_reconnected
```

Other accepted actions are `power_changed`, `manual_restart`,
`procedure_started` and `procedure_completed`. Recording one does not perform
it, verify its cause or validate a procedure. No free-text device identifiers
are accepted. An optional `--claimed-time-utc` is explicitly operator-claimed;
by default only report receipt time is known. Annotations have a session UUID,
Pi monotonic receipt time and UTC receipt time. The observer separately stamps
ingestion, preserving receipt/ingestion order uncertainty. Wrong-session,
malformed, replaced, oversized and partial final annotation inputs are recorded
as errors rather than silently dropped or treated as hardware events.

Session IDs identify recordings, not devices. Input is bounded to 256 statements,
4 KiB per statement and 256 KiB total. Each append uses a locked write. Operator
statements are always labeled `operator_statement` and
`independently_verified=false`; annotation presence cannot turn a negative
transition result into a positive one.

## Read the timeline

`timeline.json` and `timeline.md` describe a **single** continuous recording.
Each compact sample references the previous full descriptor/state snapshot and
contains the start/end of the cached-read window. The validator requires one
ordered sample per poll, valid references and generations, coherent presence,
monotonic timestamps, a complete summary and a successful standard probe.

The timeline identifies the last confirmed sample of the old identity, first
sampled absence (if any), first confirmed new identity, descriptor/state
differences, annotations and errors. A conservative transition bound spans the
start of the last old sample through completion of the first new sample. This
is deliberately wider than an exact read instant, which was not measured.
Kernel enumeration/cache latency is unmeasured: these intervals bound kernel
observations, not the timing of an earlier physical cable or power action.
Nominal interval and maximum actual start-to-start gap are both reported:
descriptor probes or scheduling can widen the gap beyond the requested interval.
Monotonic time governs order; wall-clock jumps are flagged.

A same-identity reconnect is distinct from an identity change. Address changes
without observed absence remain state changes, not invented unplug events.
Failed sampling is unknown state. Transitions shorter than a sampling gap can
be missed. Matching topology is not authentication of a physical unit. M7's
separate observations are never joined to fabricate a physical transition;
derived test fixtures are explicitly simulations. Causes stay unknown unless
separately established, and operator claims remain a separate evidence category.

Exports include redacted structured observations, provenance, timelines and
manifests. Raw stderr and annotation input remain local, referenced by hashes.
`usb-evidence-verify` recomputes the timeline from events and rejects inconsistent
completion/outcome claims, altered bounds, missing samples and invalid provenance.
`PASS` refers to a complete, consistent capture; the separate
`identity_change_captured` field reports whether its experimental objective
occurred.

## Reproduce release archives

Repository checkout (Git, Docker, Python 3 and the recorded cross-build image):

```sh
DT_BUILD_IMAGE=dwc2-transport-build scripts/build-armv6.sh
scripts/package.sh
```

The output includes separate ARMv6 and source archives with SHA-256 files.
Tar ownership, timestamps, order and gzip headers are normalized. Exact source,
application and binary hashes, image ID and package versions are recorded.
Repeated packaging from the same inputs must match bytes. Toolchain updates can
change binaries; matching bytes across arbitrary compiler versions are not
claimed.

The source archive has a checksum-verified `SOURCE_INFO.json`, so the same build
wrapper works without `.git`. It never borrows a containing repository's Git
revision. `make` and CMake can also build the exported source directly. Source
checksums detect modifications before using an exported revision as provenance.
Runtime source archives already shipped under `licenses/runtime-sources/` are
reused during packaging, without downloading anything during compilation.

`LICENSE_AUDIT.json`, `NOTICE`, runtime notices, application source and relinkable
objects accompany both archives. GNU libc 2.36-8 source, Debian patches and
cross-toolchain-base 66 source are included, with SHA-256 pins checked against
official Debian source descriptors. The actual runtime package versions must
match those pins; updated toolchains require an updated audit. Descriptor
signatures were not independently verified and the runtime itself was not
rebuilt in these tests. These are recorded limits, not claims of a separate
legal certification. Existing GCC runtime exception text is retained.

Public artifact checks cover credentials/key patterns, personal home paths,
structured serial fields, known legacy serial encodings, raw capture file types
and accidental private evidence directories. Nested upstream source archives
are verified against their pins rather than recursively pattern-scanned.
Pattern scanning does not prove absolute absence of arbitrary secrets. Git
history and local raw recordings are excluded. Building an archive does not
publish it. The public distribution uses a reviewed source snapshot and
explicitly uploaded release assets; see the [current release notes](releases/1.2.0.md).

M6 and M7 summaries remain historical observations. M8's report must independently
state its captured identities, transition outcome, pending procedure and source
revision. Version promotion follows the M8 software, hardware-run, archive and
evidence checks; a pending verified physical procedure is retained as an explicit
experimental limitation under M8's acceptance criteria.
