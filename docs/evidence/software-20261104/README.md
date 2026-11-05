# Software validation, 2026-11-04

Actual command logs, not CI service results. No remote push or hosted CI run.
SOURCE_SHA256SUMS identifies the final implementation and test inputs.

| Environment | Result |
|---|---|
| macOS AppleClang 21, ASan/UBSan static build | 5/5 CTest suites |
| macOS shared library and installed executable | 5/5 suites, installed discovery works |
| Linux aarch64 GCC 12.2, ASan/UBSan static build | 6/6 suites |
| Linux shared library + installed CMake consumer | 5/5 suites, consumer and installed CLI run |
| ARMv6 static Make build + QEMU ARM1176 | core, 185 async checks, replay, descriptor, 14 CLI invocations |
| ARMv6 CMake cross toolchain + QEMU ARM1176 | 5/5 CTest suites (incl. Linux syscall contracts) |
| ARMv7 instruction negative control | runs on Cortex-A7 emulator, traps on ARM1176 as expected |
| Shared ABI export inspection | 31 documented public symbols, no private helpers |

Linux syscall tests exercise the actual backend with wrapped syscalls: repeated
EINTR retains a 5 ms absolute wait budget, timeout cancels then reaps, disconnect
closes before synthetic results are drained, and old handles reject submissions.
Physical behavior is recorded separately under sdk-20261104-7a23308.

The supplied standalone Dockerfile was built successfully using its pinned
multiarchitecture Debian base. Build tools are distribution packages; precise
compiler/QEMU versions are recorded in the ARM log. Make's final binaries were
rebuilt after formatting; CMake cross tests verify the same final source.
