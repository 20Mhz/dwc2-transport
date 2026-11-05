# Mac recheck after reported reconnect, 2026-11-04

Owner reported reconnecting and powering the Apple TV. IORegistry snapshots
at 14:50:13, 14:50:23 and 14:50:33 UTC (11:50 America/Santiago) each showed
8 USB devices, with only two Apple entries: class-9 hubs 05ac:800b/800c.
No non-hub Apple USB device enumerated, so no descriptor transfers executed.
A separate topology check outside the sandbox showed the same device tree.
A recent USB enumeration/error log query returned no matching records; absence
of those logs does not establish whether the electrical connection works.

The owner subsequently reported **no front LED** after the HDMI-disconnected,
USB-first, then-power connection sequence. This is an owner observation, not
an electrical measurement or a demonstrated device fault. Power-only testing
with USB/HDMI disconnected, a 30-second power-off interval and a known-working
outlet was requested; its result is pending. No firmware action, mode-switch
command, USB reset or device-driver change was performed.

`discovery.json` contains actual registry samples; `owner-observation.json`
separates the owner's LED report from the observed host inventory. Files are
covered by SHA256SUMS. Hardware SDK validation remains unavailable until the
device enumerates on a supported test host.

## Power-only follow-up

The owner subsequently reported that the LED was on, and suggested the device
may have been sleeping earlier. Sleep was not independently established.
After the owner confirmed reconnecting USB with power on and HDMI disconnected,
macOS IORegistry and USB Host System Information still showed only Apple hubs,
with no non-hub Apple USB device. `powered-followup.json` records this later
state separately from the initial unlit-LED observation. The Pi host was also
rechecked and showed only its DWC2 root hub; the CH340 was absent and no
Apple device had appeared. Next
isolation options offered were moving the powered target to that Pi path or
verifying/replacing the current Mac data cable. No device fault was inferred.
