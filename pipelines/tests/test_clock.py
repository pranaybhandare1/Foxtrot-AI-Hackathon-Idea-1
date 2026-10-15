"""The clock model, exercised on the exact scenarios found in the real export."""

from datetime import datetime, timedelta

from t1d_pipelines.sources.carelink.clock import (
    ClockChange,
    LocalTimeResolver,
    pump_segments,
    receipt_segments,
    repair_day_spikes,
    segment_corrections,
)

T = datetime.fromisoformat


def minutes(start: str, *offsets: int) -> list[datetime]:
    return [T(start) + timedelta(minutes=m) for m in offsets]


def test_corrections_sum_later_deltas():
    changes = [
        ClockChange(T("2026-03-08 20:52"), T("2026-03-08 21:52")),  # +1h (DST, applied late)
        ClockChange(T("2026-07-11 14:18"), T("2026-07-11 11:18")),
    ]  # -3h (fly west)
    assert segment_corrections(changes) == [timedelta(hours=-2), timedelta(hours=-3), timedelta(0)]


def test_pump_change_row_belongs_to_previous_segment():
    assert pump_segments([False, True, False, True, False]) == [0, 0, 1, 1, 2]


def test_forward_change_advances_when_clock_passes_old_time():
    change = ClockChange(T("2026-08-10 02:41"), T("2026-08-10 08:41"))  # +6h (fly to Europe)
    ts = minutes("2026-08-10 02:30", 0, 5, 10) + minutes("2026-08-10 08:46", 0, 5)
    assert receipt_segments(ts, [change]) == [0, 0, 0, 1, 1]


def test_backward_change_uses_the_drop_to_disambiguate_the_overlap():
    change = ClockChange(T("2026-07-11 14:18"), T("2026-07-11 11:18"))  # -3h: 11:18-14:18 happens twice
    ts = minutes("2026-07-11 14:05", 0, 5, 10) + minutes("2026-07-11 11:20", 0, 5, 10)
    assert receipt_segments(ts, [change]) == [0, 0, 0, 1, 1, 1]


def test_small_backward_change_without_visible_drop_is_bounded():
    change = ClockChange(T("2026-09-20 20:49:02"), T("2026-09-20 20:48:02"))  # -1 min
    ts = [T("2026-09-20 20:45:18"), T("2026-09-20 20:50:18"), T("2026-09-20 20:55:18")]
    seg = receipt_segments(ts, [change])
    assert seg[0] == 0 and seg[-1] == 1  # at most the row inside the 1-min window is ambiguous


def test_wrong_date_then_fix_chain_including_backfilled_row():
    """2026-08-18: clock set +18h by mistake for 24 s, then -24h. A backfilled reading was
    stamped with the wrong clock; the next ones with the corrected clock."""
    a = ClockChange(T("2026-08-18 02:54:54"), T("2026-08-18 20:55:55"))
    b = ClockChange(T("2026-08-18 20:56:19"), T("2026-08-17 20:56:19"))
    ts = [
        T("2026-08-18 02:37:00"),  # before (Europe clock)
        T("2026-08-18 20:39:56"),  # stamped with the wrong (+18h) clock
        T("2026-08-17 20:42:56"),  # corrected (home) clock, backfilled
        T("2026-08-17 21:00:00"),
    ]
    seg = receipt_segments(ts, [a, b])
    assert seg == [0, 1, 2, 2]
    corr = segment_corrections([a, b])
    final_equiv = [t + corr[s] for t, s in zip(ts, seg, strict=True)]
    assert final_equiv == sorted(final_equiv)  # true order restored
    assert final_equiv[0] == T("2026-08-17 20:38:01")  # Europe clock -> home clock (-6h, +61 s slip)
    assert final_equiv[1] == T("2026-08-17 20:39:56")  # wrong-date stamp -> -24h


def test_day_spike_repaired_only_between_consistent_neighbours():
    ts = [T("2026-08-18 20:59:56"), T("2026-08-19 21:03:56"), T("2026-08-18 21:04:56")]
    fixed, flags = repair_day_spikes(ts)
    assert flags == [False, True, False] and fixed[1] == T("2026-08-18 21:03:56")
    # neighbours 6h apart (a real clock change) -> not a spike
    ts2 = [T("2026-08-18 02:37:00"), T("2026-08-18 20:39:56"), T("2026-08-17 20:42:56")]
    assert repair_day_spikes(ts2)[1] == [False, False, False]


def test_local_time_home_dst_travel_and_invalid():
    r = LocalTimeResolver("America/New_York")
    # DST applied late: device still on -5h after 2am on 2026-03-08, true local is -4h
    assert r.offset(T("2026-03-08 15:00"), timedelta(hours=-5)) == (timedelta(hours=-4), "home")
    assert r.offset(T("2026-02-15 15:00"), timedelta(hours=-5)) == (timedelta(hours=-5), "home")
    # 29-minute clock slip still counts as home
    assert r.offset(T("2026-07-01 15:00"), timedelta(hours=-4, minutes=-29)) == (timedelta(hours=-4), "home")
    assert r.offset(T("2026-08-12 15:00"), timedelta(hours=2, minutes=1)) == (timedelta(hours=2), "travel")
    assert r.offset(T("2026-08-18 00:40"), timedelta(hours=20))[1] == "home_fallback_invalid_device_offset"


def test_observed_time_zones_most_recent_evidence_wins():
    from t1d_pipelines.sources.carelink.clock import ObservedTimeZones

    h = timedelta(hours=1)
    obs = ObservedTimeZones([(T("2026-07-09 14:00"), -7 * h), (T("2026-08-10 03:00"), -4 * h)])
    # trip the pump never recorded: observation newer than the last pump zone change -> observation wins
    assert obs.resolve(T("2026-07-09 20:00"), -4 * h, T("2026-07-01 00:00")) == -7 * h
    # pump reset on arrival after the last observation (Europe) -> pump wins
    assert obs.resolve(T("2026-08-10 12:00"), 2 * h, T("2026-08-10 06:41")) is None
    # agreement, and stale observations, change nothing
    assert obs.resolve(T("2026-08-10 05:00"), -4 * h, None) is None
    assert obs.resolve(T("2026-08-14 05:00"), -5 * h, None) is None
    assert obs.resolve(T("2026-01-01 05:00"), -5 * h, None) is None  # before any observation
