# Consume HostLab instrumentation externally

```
sudo /path/to/dwc2-hostlab/bin/hostlab-session run --out /tmp/sdk-trace \
  --bindir /path/to/dwc2-hostlab/bin --profile fast -- \
  /path/to/usb-diagnostics --device /dev/bus/usb/001/002 --repeat 30 --jsonl
/path/to/dwc2-hostlab/bin/hostlab-analyze /tmp/sdk-trace --json /tmp/analysis.json
```

The SDK CLI reuses HostLab's MIT JSONL writer and clock sampler. Schema 1
records carry setup bytes, monotonic submit/reap times, actual length, SDK
status and raw kernel status. A reap timestamp is not a hardware completion
timestamp. Real-time/monotonic snapshots allow usbmon clock correlation;
mock output intentionally uses virtual timestamps without a wallclock snapshot.

Existing HostLab owns usbmon, tracefs setup/teardown and phase reconstruction.
No internal kernel struct ABI is exposed or linked into the SDK. The fast
profile used in the evidence reconstructs three channel runs per control
transfer, but does not install submit/enqueue/giveback probes and therefore
cannot establish direct URB-pointer joins or channel numbers. This explains
its nonzero `usbmon_unpaired_with_kprobes` count. Do not interpret that count
as dropped USB records. Inspect session warnings, usbmon stats and the selected
profile when evaluating a capture. No external measurement hardware is needed.

References checked during implementation: Linux
[usbfs implementation, v6.12](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/core/devio.c)
and [USB host API](https://www.kernel.org/doc/html/latest/driver-api/usb/usb.html).
The actual Pi kernel remains 6.12.47+rpt-rpi-v6, independent of current docs.
