# M6 passive state and diagnostic recovery

`usb-observe` is a Python 3.9+ diagnostic application around SDK discovery.
Its default mode calls `usb-discover` and reads only cached sysfs metadata and
`descriptors`; it does not open usbfs, claim interfaces or issue USB requests.
The SDK remains reusable and independent of Apple classification/state logic.

```sh
tools/usb-observe --bin build/armv6 --port 1-1 --duration 30 --interval .5
# Explicitly add standard read-only descriptor probes on appearance/change:
sudo tools/usb-observe --bin build/armv6 --port 1-1 --duration 120 \
  --probe-on-connect --kernel-errors --stop-after-reconnect
```

All runs are bounded (default 30 seconds, maximum one hour and 10,000 samples).
`--port` selects a physical sysfs slot, allowing VID changes to be recorded at
that location even if the new vendor is not Apple. Without it, Apple non-hub
slots are discovered and followed. A topology slot is not proof of a physical
unit's identity; neither addresses nor descriptor hashes authenticate a device.
No serial attribute is read. USB speed, active configuration, interface and
endpoint descriptors, binding, bus/address and port path are included.

Events are versioned JSONL: meta, connected, disconnected, reconnected,
state_changed (changed fields), device_error, discovery_error,
diagnostics_recovered, discovery_recovered, descriptor_probe_ok/error,
kernel_enumeration_error, facility_unavailable and summary. Optional kernel
errors emit only fixed categories, topology and errno; raw messages/serials
are omitted. An initial kernel-log snapshot establishes a baseline; only new
errors are emitted. Log permission failures are recorded, not hidden.

Sampling failures are unknown state, not evidence of a disconnect. A device
that vanishes during cached reads gets a structured error; a subsequent empty
inventory records disappearance. Descriptor/identity reads are checked for
coherency to avoid combining two device addresses. On reconnect the optional
probe starts a fresh process, discovers/opens the current path, reads standard
descriptors and closes normally. Failed probes retry with a one-second delay
within the run budget. No automatic reset, configuration change, driver detach,
firmware action or mode switch is used. Recovery means the diagnostic software
can resume reads; it does not mean repair of the Apple TV.

SIGINT/SIGTERM handlers set a flag only. The sampling loop emits a final signal
summary and exits; child commands have finite timeouts and are killed/reaped
on timeout. The remaining observation budget caps new command waits. A signal
while a child is running can take up to that child's remaining timeout to finish.
The SDK itself retains its documented explicit, caller-serviced deadlines.

State snapshots can miss transitions shorter than the polling interval, or
unplug/replug at the same address with no sampled absence/descriptor change.
A PID or interface change observed without absence is a state_changed event,
not an invented physical disconnect. No DFU/recovery transition is initiated.
An operator may follow documented manufacturer connection procedures while
recording; mode labels remain database associations, with model uncertainty.

## Reproducible M6 capture

Run on the Pi from a complete source or release bundle, with a fresh local
raw path and a separate redacted destination:

```sh
sudo python3 scripts/pi/m6-validate.py --bin ./bin \
  --raw-out .local-evidence/m6-run-1 --bundle /tmp/m6-redacted \
  --hostlab /home/USER/dwc2-hostlab --port 1-1
bin/usb-evidence-verify /tmp/m6-redacted
```

The collector reuses the existing bounded Apple TV capture, validates standard
reads/trace completeness, records a passive baseline and tests SIGTERM cleanup.
`--observer-log PATH` adds a separately recorded manual unplug/replug window.
It never reports physical reconnect coverage unless the log contains actual
disconnected/reconnected events; post-reconnect descriptor success is separate.

Raw trace/evidence stays local under `.local-evidence/` (Git-ignored). The
versioned/exported bundle contains redacted descriptors, identification sources,
metadata/source/binary hashes, results, observer events, a trace summary and raw
file references/hashes rather than raw traces. SHA-256 manifests cover all
exported files. The verifier rejects missing/extra/tampered files, path traversal,
serial leaks, malformed reports and transfer results that contradict a pass.
Checksums establish integrity, not an authenticated provenance signature.
Raw input manifests must verify before export. The public verifier also
recomputes observer summaries and reconnect claims from the included event logs.

The fast HostLab profile supports three-phase reconstruction and time
correlation but does not provide direct URB-pointer joins or channel numbers.
The report states this explicitly. Empty or incomplete traces cannot pass.
Missing optional strings remain visible as per-index statuses/warnings; mandatory
device/configuration failure causes inspection failure. `--include-serial`
is an explicit inspector opt-in and is not used by the M6 collector.

## Physical results

The [November 4 M6 evidence](evidence/m6-20261104/README.md) includes a real
manual USB cable reconnection at slot `1-1`. Address 4 disappeared, address 5
appeared with a failed control probe, then disappeared; address 6 appeared and
passed a descriptor probe. One cached-read NoDevice error and one probe protocol
error were retained. The observer stopped automatically after the recovered
read. Their root cause was not isolated. No errno is inferred from this older
observer's protocol status; current events preserve the SDK's errno when given.
The subsequent full read-only capture passed at address 7. Addresses are
observations at different times, not stable device identifiers.
