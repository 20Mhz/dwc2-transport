# Final packaged release revalidation, 2026-11-04

Exact release source: `d8853d831bc2021c240fd2cd1ec0693528ac7d02`.
Archive: `dwc2-transport-1.0.0-linux-armv6.tar.gz`; SHA256 in ARCHIVE_SHA256.
`scripts/deploy.sh pizero` actually deployed the versioned archive, verified
all 105 packaged-file checksums on the Pi and ran `usb-discover --version`.
The archive includes the static SDK archive, public headers, three diagnostic
tools, C example, test binaries, fixtures, documentation, LICENSE and NOTICE.

The packaged regression runner executed on the physical Pi against CH340
1a86:7523 with `--ch340-in --reset`. Final source was rebuilt after formatting,
public export declarations, bounded replay parsing and build-system changes.

- 26 subprocesses, all exit 0 (`summary.json`).
- Full regression: 168 checks, zero failures.
- Regression with SIGTERM and pending bulk work: 169 checks, zero failures.
- 20 separate diagnostic processes: all succeeded.
- Driver restored to ch341 (`post-discovery.stdout`).
- Hardware/kernel/model and hashes of exact executed binaries: `metadata.json`.
- Physical cable disconnect/reconnect and Apple TV hardware remain untested.

No HostLab trace was repeated for this release packaging check; the earlier
7a23308 capture under sdk-20261104-7a23308 remains the tracing evidence.
The SDK's physical checks were rerun on the final binaries; they are not
inferred from the older capture. CI workflow additionally passed local
`actionlint` validation; no hosted CI run or remote push was performed.
