"""Reconstruct absolute time (UTC) and true local time from the pump's hand-set clock.

The problem
-----------
Every CareLink timestamp is the pump's wall clock at the time. You change that clock by
hand: DST, travel, and the occasional wrong date. Each change is logged as a pump event
('New Device Time') holding the old and new clock readings. The data is full of them
(a trip to Europe, a -24h date fix, a DST change applied 19 hours late), so device time
is neither monotonic nor comparable across segments.

The model
---------
Clock changes split the history into segments. If we know the UTC offset of the LAST
segment (config), then for any earlier segment k

    utc = device_ts + sum(delta_j for every change j at or after k) - final_offset

where delta_j = new_j - old_j. This holds whatever the reason for a change (travel or
mistake), so UTC is always monotonic and joinable with other sources (Oura, Apple).

Which segment a row belongs to
------------------------------
- Pump events are logged in true sequence (the export's Index), and the change event
  itself sits in that sequence, so a pump row's segment is simply the number of changes
  before it.
- Sensor rows are stamped when the pump RECEIVES them, with the clock at receipt (backfilled
  readings get receipt_clock - age). They are also in receipt sequence, but carry no change
  markers, so we walk them and advance to the next segment when either
    (a) the stamp jumps past the old clock value of the next change (clock moved forward), or
    (b) the stamp drops by more than a minute while the next change is a backward one.
  Backward changes smaller than the reading interval leave no visible drop. Rows inside
  that window are then off by at most |delta| (a few minutes in this data).

Local time
----------
The pump clock is your intended wall clock, but it can lag (e.g. DST applied late) or be
wrong. The local UTC offset of a segment is inferred as follows: if the device offset is
within 35 min of one of your home zone's offsets, use the home zone's DST rules at that
instant; otherwise it's travel, so round to the nearest 15 min.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ONE_MINUTE = timedelta(minutes=1)
ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class ClockChange:
    old: datetime  # device clock just before the change
    new: datetime  # device clock just after

    @property
    def delta(self) -> timedelta:
        return self.new - self.old


def segment_corrections(changes: list[ClockChange]) -> list[timedelta]:
    """correction[k] = sum of deltas of changes k..n-1; segment n (the last) has correction 0."""
    out = [timedelta(0)] * (len(changes) + 1)
    for k in range(len(changes) - 1, -1, -1):
        out[k] = out[k + 1] + changes[k].delta
    return out


def pump_segments(is_change: list[bool]) -> list[int]:
    """Segment per pump row (forward order). A change row belongs to the segment before it."""
    seg, out = 0, []
    for flag in is_change:
        out.append(seg)
        if flag:
            seg += 1
    return out


def repair_day_spikes(
    ts: list[datetime], tolerance: timedelta = timedelta(minutes=10)
) -> tuple[list[datetime], list[bool]]:
    """Fix isolated rows stamped whole days ahead of both neighbours.

    Seen after the 2026-08-18 date mix-up: the sensor kept a +24h clock for its
    SENSOR_ERROR markers while glucose readings were stamped correctly. A row is repaired
    only if its neighbours agree with each other (0..30 min apart) and subtracting whole
    days puts it between them.
    """
    out, flags = list(ts), [False] * len(ts)
    for i in range(1, len(ts) - 1):
        prev, cur, nxt = ts[i - 1], ts[i], ts[i + 1]
        if not (cur - prev > timedelta(hours=1) and cur - nxt > timedelta(hours=1)):
            continue
        if not timedelta(0) <= nxt - prev <= timedelta(minutes=30):
            continue
        days = round((cur - nxt) / ONE_DAY)
        fixed = cur - days * ONE_DAY
        if days >= 1 and prev - tolerance <= fixed <= nxt + tolerance:
            out[i], flags[i] = fixed, True
    return out, flags


def receipt_segments(
    ts: list[datetime],
    changes: list[ClockChange],
    tolerance: timedelta = 2 * ONE_MINUTE,
    drop_tolerance: timedelta = ONE_MINUTE,
) -> list[int]:
    """Segment per sensor row (forward receipt order), per the rules in the module docstring."""
    k, n = 0, len(changes)
    out: list[int] = []
    prev: datetime | None = None
    for t in ts:
        dropped = prev is not None and t < prev - drop_tolerance
        used_drop = False
        while k < n:
            change = changes[k]
            if t > change.old + tolerance:
                k += 1
            elif dropped and not used_drop and change.delta < timedelta(0):
                k += 1
                used_drop = True
            else:
                break
        out.append(k)
        prev = t
    return out


class LocalTimeResolver:
    """Map (utc, device offset) -> best estimate of true local UTC offset."""

    def __init__(self, home_timezone: str):
        self.zone = ZoneInfo(home_timezone)
        # standard and daylight offsets of the home zone, sampled across a year
        probes = [datetime(2026, m, 15, 12) for m in (1, 7)]
        self.home_offsets = {self.zone.utcoffset(p) for p in probes}

    def offset(self, utc: datetime, device_offset: timedelta) -> tuple[timedelta, str]:
        if not timedelta(hours=-12) <= device_offset <= timedelta(hours=14):
            return self._home(utc), "home_fallback_invalid_device_offset"
        if any(abs(device_offset - h) <= timedelta(minutes=35) for h in self.home_offsets):
            return self._home(utc), "home"
        quarter = timedelta(minutes=15)
        return round(device_offset / quarter) * quarter, "travel"

    def home_offset_at(self, utc: datetime) -> timedelta:
        """The home zone's UTC offset at this instant (DST-aware)."""
        return self._home(utc)

    def _home(self, utc: datetime) -> timedelta:
        aware = utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(self.zone)
        return aware.utcoffset()


class ObservedTimeZones:
    """Correct pump-clock local time with independently observed UTC offsets (e.g. Oura's phone time zone).

    Rule: when the pump-derived offset and the latest observation disagree, the more recent evidence
    wins. A pump clock change of >= 30 min after the observation means you reset the pump on arrival
    (pump wins); otherwise the observation shows a move the pump never recorded, or a mis-set pump
    clock (observation wins). Observations older than `max_age` are ignored.
    """

    def __init__(self, observations: list[tuple[datetime, timedelta]], max_age: timedelta = timedelta(hours=36)):
        observations = sorted(observations)
        self.times = [t for t, _ in observations]
        self.offsets = [o for _, o in observations]
        self.max_age = max_age

    def resolve(self, utc: datetime, pump_offset: timedelta, pump_zone_changed_at: datetime | None) -> timedelta | None:
        """The observed offset to use instead of `pump_offset`, or None to keep the pump's."""
        i = bisect_right(self.times, utc) - 1
        if i < 0 or utc - self.times[i] > self.max_age:
            return None
        observed = self.offsets[i]
        if observed == pump_offset:
            return None
        if pump_zone_changed_at is not None and pump_zone_changed_at > self.times[i]:
            return None
        return observed


def zone_change_times(
    changes: list[ClockChange],
    corrections: list[timedelta],
    final_offset: timedelta,
    min_delta: timedelta = timedelta(minutes=30),
) -> list[datetime | None]:
    """For each clock segment, the UTC instant of the most recent real time-zone change (>= 30 min) before it."""
    out: list[datetime | None] = [None]
    last: datetime | None = None
    for k, change in enumerate(changes):
        if abs(change.delta) >= min_delta:
            last = change.old + corrections[k] - final_offset  # the change instant, in UTC
        out.append(last)
    return out
