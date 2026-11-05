# Bounded physical tests

Build `test-hardware` with the same compiler as the SDK. Run on Linux against
an exact non-hub usbfs path. Default: 50 synchronous descriptor reads, 25 async
reads, 25 control cancellations, 20 close-with-work/reopen cycles, fd-count
comparison. `--ch340-in` is restricted to 1a86:7523: explicitly detaches/claims
interface 0, cancels 5 bulk IN 0x82 transfers and services 5 ten-ms deadlines,
then releases/reattaches. It additionally closes a handle with bulk work pending
and checks subsequent descriptor health. `--reset` checks conventional reset
and a descriptor afterwards. No OUT endpoint or serial port is accessed.

`regression.py` runs these checks twice (the second includes SIGTERM while an
IN transfer is pending), launches 20 separate diagnostic processes and can
invoke existing HostLab capture/analysis. Subprocesses and signal waits are
bounded; it records return codes, stderr, kernel/model, revision and hashes.
SIGKILL restores no detached driver; the harness does not deliberately use it
except as a timeout fallback, in which case inspect/reattach the driver.

Physical cable unplug/replug requires a person and is recorded as skipped in
automated captures. To test: start conventional async IN work, unplug, reap
all NO_DEVICE results, close, reconnect, rediscover and open a new handle.
Never recycle an old discovery address as proof of the same physical device.
Mock and Linux syscall-contract tests cover disconnect result draining in CI.
OUT endpoints, devices behind hubs, multiple physical devices/controllers,
isochronous transfers and Apple TV hardware are not covered by the evidence.
