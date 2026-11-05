# API 1.0 lifetime and threading contract

The public C ABI is major 1 (`dt_api_version() == 0x10000`). Headers define
all enum values and fixed public layouts. Shared-library SONAME is 1.
Incompatible changes require a new major. This is experimental software:
API stability does not imply universal controller/device validation.

Create an independent `dt_context` for linux-usbfs or mock. Discovery returns
an allocated snapshot; free with `dt_device_list_free`. Open an exact snapshot
path; a path can be reused after disconnect. Linux compares cached VID/PID at
open but cannot distinguish identical replacements. Re-enumerate after a lost
device. `dt_device_get_info` is a borrowed discovery snapshot.

Serialize calls on a context and all its children. Independent contexts can
run on separate threads. There are no worker threads, global default backends,
or callbacks. Do not call from a signal handler. Set a `sig_atomic_t` flag,
use finite reap waits, then close from normal code.

Synchronous control timeout 0 means no deadline. Descriptor helpers use
1000 ms. Linux synchronous timeouts follow kernel jiffy granularity. Submit
timeout 0 means no deadline. Async deadlines are serviced by `dt_reap`;
applications must keep pumping it. `wait_ms` bounds each reap's wait and never
cancels a transfer by itself; 0 polls and -1 waits indefinitely. Interrupted
polls retain the original monotonic deadline. Cancellation/reaping syscall
and scheduling latency can extend a nominal budget.

Each submission allocates an opaque transfer owned by its device. OUT payload
is copied immediately. IN data is accessible only after reap. The result and
buffer stay valid until `dt_transfer_free` or device close. A successful reap
means a result is available; check its status separately. Free before reap
returns BUSY. Up to 64 transfers may be allocated per device. Control data is
limited to 4096 bytes; bulk/interrupt payload to 1 MiB. No mmap/DMA buffer API.

Cancellation acceptance does not guarantee CANCELLED: completion can win the
race, including after HCD completion but before giveback. NOT_PENDING still
requires a reap. A deadline-triggered cancellation reports TIMEOUT only if
its result is CANCELLED; an already successful completion remains successful.
Queued completions take precedence when the caller services a late deadline.
Never infer bus progress from cancelled actual_length; HostLab found zero
reported length despite partial controller progress.

Disconnect drains pending results with NO_DEVICE. Linux closes the usbfs fd
before synthesizing results if the kernel can no longer reap them. Mock
reconnect permanently invalidates old handles; rediscover and reopen. Close
cancels pending work, closes usbfs (which kills remaining work), then frees
buffers/URBs. Context destruction closes all child devices and transfers.

Endpoint submissions require an explicit interface claim; Linux validates
endpoint/interface membership. The mock has interface 0 and two bulk endpoints.
Detachment is explicit and close/release attempts to restore only drivers
this handle detached. Restore failures are reported by release; close has no
error result and restoration is best effort. SIGKILL cannot run restoration;
usbfs releases claims but a previously detached driver may remain unbound.
Use HostLab's explicit reattach tool if needed. Reset refuses outstanding
transfers/claims on that handle; release/reap first and avoid resetting a
physical device being used by another context/process. Rediscover/reopen if
reset returns NO_DEVICE. No firmware or kernel changes are involved.
