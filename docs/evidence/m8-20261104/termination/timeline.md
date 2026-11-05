# M8 single-session timeline

Outcome: **NO_IDENTITY_CHANGE_OBSERVED**

Operator annotations are statements; polling windows are not electrical timestamps.

| Event | Port | Identity before → after | Conservative monotonic bounds (ns) |
| --- | --- | --- | --- |
| No sampled transition | — | Stable identity or no confirmed change | See sample windows in timeline.json |

## Uncertainties

- Bounds span cached-read windows; electrical transition time is not measured.
- Operator report receipt is not the measured physical action time.
- Events within one sample cannot be totally ordered from polling.
- Topology does not authenticate the physical unit.

## Operator statements

No operator statement was recorded.
