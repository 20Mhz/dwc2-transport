# M8 single-session timeline

Outcome: **NO_IDENTITY_CHANGE_OBSERVED**

Operator annotations are statements; polling windows are not electrical timestamps.

| Event | Port | Identity before → after | Conservative monotonic bounds (ns) |
| --- | --- | --- | --- |
| No sampled transition | — | Stable identity or no confirmed change | See sample windows in timeline.json |

## Confirmed observations

| Position | Port | VID:PID / address | Sample read window (monotonic ns) |
| --- | --- | --- | --- |
| First | 1-1 | 05ac:1281 / 14 | [42041002570005, 42041044425426] |
| Last | 1-1 | 05ac:1281 / 14 | [42070516249374, 42070557420765] |

## Uncertainties

- Bounds span cached-read windows; electrical transition time is not measured.
- Operator report receipt is not the measured physical action time.
- Events within one sample cannot be totally ordered from polling.
- Topology does not authenticate the physical unit.

## Operator statements

No operator statement was recorded.
