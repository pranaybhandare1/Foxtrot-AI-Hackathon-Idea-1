"""Raw parser, episode detection and bolus assembly on small synthetic inputs."""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from t1d_pipelines.sources.carelink.clean.glucose import _episodes
from t1d_pipelines.sources.carelink.clean.insulin import boluses
from t1d_pipelines.sources.carelink.raw import RawParseError, parse_file

HEADER = "Index,Date,Time,New Device Time,BG Source,BG Reading (mg/dL),Sensor Glucose (mg/dL),Bolus Source,Alert"
SAMPLE = "\r\n".join(
    [
        "Last Name,First Name,Patient ID,System ID,Start Date,End Date,Device,MiniMed 780G MMT-1884,"
        "Hardware Version,A1.01,Firmware Version,27.11.6",
        '"Doe","Jane","","","08-26-2026 12:00:00 AM","09-24-2026 12:00:00 AM","Serial Number",NG1,Software Version,6.62U',
        "Patient DOB,,,,,,CGM,Guardian™ 4,Instinct",
        "",
        "-------,MiniMed 780G MMT-1884,Pump,NG1,------- ",
        HEADER,
        '0.00000,2026/09/24,23:08:01,,,,,,"ALERT ON HIGH: tone (262)"',
        "-------,MiniMed 780G MMT-1884,Pump,NG1,Aggregated Auto Insulin Data ",
        HEADER,
        "1.00000,2026/09/24,00:00:00,,,,,CLOSED_LOOP_AUTO_INSULIN,",
        "-------,MiniMed 780G MMT-1884,Sensor,NG1,------- ",
        HEADER,
        "2.00000,2026/09/24,23:55:18,,,,143,,",
    ]
)


def test_raw_parser_sections_lineage_and_pii(tmp_path: Path):
    f = tmp_path / "carelink_2026-08-26_to_2026-09-24.csv"
    f.write_bytes(b"\xef\xbb\xbf" + SAMPLE.encode())
    df, meta = parse_file(f, "export_x", "abc")
    assert df["_section"].to_list() == ["pump", "pump_aggregated_auto_insulin", "sensor"]
    assert df["_source_line"].to_list() == [7, 10, 13]
    assert df["Alert"][0] == "ALERT ON HIGH: tone (262)"  # quoted value survives
    assert df["Sensor Glucose (mg/dL)"][2] == "143" and df["BG Source"][0] is None
    assert meta["cgm"] == "Guardian™ 4|Instinct" and meta["has_bom"] and meta["line_endings"] == "CRLF"
    assert "last_name" not in meta and "first_name" not in meta and "patient_dob" not in meta


def test_raw_parser_rejects_ragged_rows(tmp_path: Path):
    f = tmp_path / "carelink_2026-08-26_to_2026-09-24.csv"
    f.write_text(SAMPLE.replace("2.00000,2026/09/24,23:55:18,,,,143,,", "2.00000,2026/09/24,23:55:18,143"))
    with pytest.raises(RawParseError):
        parse_file(f, "export_x", "abc")


def test_episodes_need_min_duration_tolerate_short_gaps_and_end_after_recovery():
    low = lambda v: v < 70  # noqa: E731
    vals = [100, 65, 66, None, 60, 64, 90, 95, 99, 100, 68, 69, 80, 81, 82]
    # first dip: 4 low bins with a 1-bin gap -> episode; second dip: only 2 bins -> not an episode
    assert _episodes(vals, low, min_bins=3, end_bins=3, max_gap_bins=3) == [(1, 5)]
    assert _episodes([60] * 3 + [None] * 5 + [60] * 3, low, 3, 3, 3) == [(0, 2), (8, 10)]


def _frag(seq, kind, n, ts, **kw):
    base = {
        "event_id": f"e{seq}",
        "batch_id": "b",
        "seq": seq,
        "event_type": kind,
        "bolus_number": n,
        "ts_utc": ts,
        "ts_local": ts,
        "date_local": ts.date(),
        "bolus_selected_u": None,
        "bolus_delivered_u": None,
        "bolus_type": "Normal",
        "bolus_source": None,
        "bolus_cancel_reason": None,
        "source_file": "f",
        "source_line": seq,
    }
    return base | kw


def test_bolus_assembly_partial_cancel_and_stray_cancel():
    t0 = datetime(2026, 5, 1, 12, 0)
    s = timedelta(seconds=1)
    events = pl.DataFrame(
        [
            _frag(
                1,
                "bolus_programmed",
                7,
                t0,
                bolus_selected_u=4.0,
                bolus_source="CLOSED_LOOP_BG_CORRECTION_AND_FOOD_BOLUS",
            ),
            _frag(2, "bolus_canceled", 7, t0 + 50 * s, bolus_cancel_reason="User Request"),
            _frag(
                3,
                "bolus_delivered",
                7,
                t0 + 50 * s,
                bolus_selected_u=4.0,
                bolus_delivered_u=1.25,
                bolus_source="CLOSED_LOOP_BG_CORRECTION_AND_FOOD_BOLUS",
            ),
            _frag(4, "bolus_canceled", 9, t0 + timedelta(hours=3), bolus_cancel_reason="User Request"),  # stray
            _frag(5, "bolus_programmed", 7, t0 + timedelta(hours=5), bolus_selected_u=2.0, bolus_source="BOLUS_WIZARD"),
            _frag(
                6,
                "bolus_delivered",
                7,
                t0 + timedelta(hours=5, minutes=2),
                bolus_selected_u=2.0,
                bolus_delivered_u=2.0,
                bolus_source="BOLUS_WIZARD",
            ),
        ]
    )
    b, stray = boluses(events)
    assert stray == 1 and b.height == 2
    first, second = b.row(0, named=True), b.row(1, named=True)
    assert first["was_canceled"] and first["is_partial"] and first["units_delivered"] == 1.25
    assert not second["was_canceled"] and second["pump_mode"] == "manual" and second["delivery_minutes"] == 2.0
