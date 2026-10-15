# 0004: Reconstruct UTC from pump clock changes

**Status:** accepted · 2026-09-26

## Context
Pump timestamps are a hand-set wall clock. The export has 31 clock changes (DST applied late, trips to
UTC−7 and UTC+2, a mistyped date). Joining with Oura/Apple Health and ordering events both need true time.

## Decision
Anchor on the clock's known UTC offset at export (config) and walk the logged changes backwards:
`utc = device_ts + Σ(later deltas) − final_offset`. Pump rows are segmented by their true sequence (the
change event sits in it). Sensor rows are segmented by receipt order, because they are stamped at receipt.
Local time uses the home timezone's DST rules within ±35 min of a home offset, and the pump's offset otherwise (travel).

## Consequences
- UTC is monotonic in sequence (checks T2/T3) and independently validated (T5).
- The final offset is an assumption: update the config if an export is taken while travelling.
- Travel without a pump-clock change is invisible until another source (Oura) provides timezone data.
