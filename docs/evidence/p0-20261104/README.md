# First vertical slice, physical Pi, 2026-11-04

Revision and SHA256SUMS identify the source/binaries actually deployed.
`results.txt` is stdout from the physical Pi reached through the configured
SSH alias. Discovery: PASS, CH340 1a86:7523, bound ch341. Device descriptor:
PASS, 18 bytes, `12011001ff000008861a2375640200020001`. Close and process
exit: success. `test-core` ran on the Pi using the mock backend, separately
from the physical descriptor check. No reset, driver detach or kernel changes.
