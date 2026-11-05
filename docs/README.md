# Documentation

Start with the [operating guide](guide.md) for installation, diagnostics,
collection and release reproduction. The [root README](../README.md) summarizes
capabilities, supported hardware and current limits.

| Reference | Purpose |
| --- | --- |
| [C API contract](api.md) | Ownership, threading, deadlines, cancellation and cleanup |
| [1.2.0 release notes](releases/1.2.0.md) | Delivered files, validation and known limits |
| [Bounded sessions and timelines](m8-sessions.md) | Collector, operator statements, timing bounds and verifier |
| [Apple USB identity assessment](m8-identities.md) | Primary references; application, recovery and DFU distinctions |
| [Instrumentation](instrumentation.md) | External HostLab tracing and correlation limits |
| [Replay fixtures](../tests/fixtures/README.md) | Fixture provenance and simulation boundaries |
| [Hardware regression guide](../tests/hardware/README.md) | Explicit device-specific tests and their effects |

## Evidence

| Record | Result |
| --- | --- |
| [M6](evidence/m6-20261104/README.md) | 25 async reads, five process runs, ten traced requests and descriptor recovery after a reconnect error |
| [M7](evidence/m7-20261104/README.md) | Stable observation, cable-only reconnect and independent observer lifecycles passed; identities observed separately |
| [M8](evidence/m8-20261104/README.md) | Bounded stable capture and interrupted cleanup passed; no identity transition captured; procedure pending |

These reports distinguish hardware observations, operator statements and
simulated tests. Integrity verification does not authenticate a physical model,
prove a causal mechanism or certify a recovery/DFU protocol.

## Historical references

[M7 release candidate](m7-release.md), [M6 observer](m6-observer.md),
[M6 identification](m6-identification.md), [initial Apple TV profile](apple-tv-a1427.md)
and [HostLab integration assessment](integration.md) describe earlier milestones.
Their versions and results remain historical. Use the current guide and M8
identity assessment for 1.2.0. Legacy raw traces and development Git history
are retained locally and excluded from the public distribution snapshot.
