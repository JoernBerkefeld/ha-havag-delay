"""Tests for the pure HAFAS logic (no Home Assistant needed)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Load hafas.py directly so the tests do not need Home Assistant installed.
_path = Path(__file__).parent.parent / "custom_components" / "havag_delay" / "hafas.py"
_spec = importlib.util.spec_from_file_location("havag_hafas", _path)
hafas = importlib.util.module_from_spec(_spec)
sys.modules["havag_hafas"] = hafas
_spec.loader.exec_module(hafas)

CET = timezone(timedelta(minutes=60))
DIR_SOLTAUER = "Halle (Saale), Soltauer Str."
DIR_HBF = "Halle (Saale), Hauptbahnhof (Tram/Bus)"
NOW = datetime(2026, 11, 13, 9, 30, tzinfo=CET)


def at(h: int, m: int) -> datetime:
    return datetime(2026, 11, 13, h, m, tzinfo=CET)


def dep(planned, delay_min=None, *, line="10", direction=DIR_SOLTAUER, cancelled=False):
    actual = planned + timedelta(minutes=delay_min) if delay_min is not None else None
    return hafas.Departure(line, direction, planned, actual, cancelled)


def jny(prodx, direction, planned, real=None, **stop_extra):
    stop = {"dTimeS": planned, "dTZOffset": 60, **stop_extra}
    if real:
        stop["dTimeR"] = real
    return {"date": "20261113", "prodX": prodx, "dirTxt": direction, "stbStop": stop}


def raw_board(jny_list):
    return {
        "err": "OK",
        "svcResL": [
            {
                "err": "OK",
                "res": {"common": {"prodL": [{"nameS": "10"}, {"nameS": "21"}]}, "jnyL": jny_list},
            }
        ],
    }


# ---- parsing ---------------------------------------------------------------------------


def test_parse_departures_reads_line_direction_and_times():
    [d] = hafas.parse_departures(raw_board([jny(0, DIR_SOLTAUER, "093800", "093900")]))
    assert d.line == "10"
    assert d.direction == DIR_SOLTAUER
    assert d.planned == at(9, 38)
    assert d.actual == at(9, 39)
    assert d.cancelled is False


def test_parse_departures_day_offset_and_cancelled():
    [d] = hafas.parse_departures(raw_board([jny(0, DIR_SOLTAUER, "01000500", None, dCncl=True)]))
    assert d.planned == datetime(2026, 11, 14, 0, 5, tzinfo=CET)
    assert d.cancelled is True
    assert d.actual is None


def test_parse_departures_skips_entries_without_time_and_handles_unknown_product():
    raw = raw_board([{"date": "20261113", "prodX": 0, "dirTxt": "x", "stbStop": {}}, jny(7, "x", "093800")])
    [d] = hafas.parse_departures(raw)
    assert d.line == ""


def test_parse_departures_raises_on_error():
    with pytest.raises(hafas.HafasError):
        hafas.parse_departures({"err": "OK", "svcResL": [{"err": "PARSE"}]})
    with pytest.raises(hafas.HafasError):
        hafas.parse_departures({"err": "AUTH"})


def test_parse_stops_filters_virtual_and_non_stops():
    raw = {
        "err": "OK",
        "svcResL": [
            {
                "err": "OK",
                "res": {
                    "match": {
                        "locL": [
                            {"type": "S", "extId": "3937", "name": "Halle (Saale), Betriebshof Freiimfelder Str."},
                            {"type": "S", "extId": "9390176", "name": "Halle (Saale), Betriebshof Freiimfelder Str. (virt.)"},
                            {"type": "A", "extId": "1", "name": "Some address"},
                        ]
                    }
                },
            }
        ],
    }
    assert hafas.parse_stops(raw) == [hafas.Stop("3937", "Halle (Saale), Betriebshof Freiimfelder Str.")]


def test_station_board_request_uses_halle_local_time():
    body = hafas.build_station_board_request("3937", datetime(2026, 11, 13, 8, 30, 5, tzinfo=timezone.utc))
    req = body["svcReqL"][0]["req"]
    assert (req["date"], req["time"]) == ("20261113", "093005")
    assert req["stbLoc"]["extId"] == "3937"
    summer = hafas.build_station_board_request("3937", datetime(2026, 7, 13, 8, 30, 5, tzinfo=timezone.utc))
    assert summer["svcReqL"][0]["req"]["time"] == "103005"


# ---- selection -------------------------------------------------------------------------

KW = {"line": "10", "direction": "Soltauer Str.", "now": NOW}


def test_offset_takes_the_first_departure_predicted_at_least_that_far_ahead():
    deps = [dep(at(9, 23), 0), dep(at(9, 38), 3), dep(at(9, 53), 0)]
    # now 09:30, offset 8 -> earliest 09:38; 09:23 has left, 09:38 is predicted 09:41
    assert hafas.select_upcoming(deps, offset_minutes=8, **KW).planned == at(9, 38)


def test_offset_counts_a_late_tram_that_was_planned_earlier():
    deps = [dep(at(9, 33), 6), dep(at(9, 42), 0)]  # first is planned 09:33, predicted 09:39
    assert hafas.select_upcoming(deps, offset_minutes=8, **KW).planned == at(9, 33)


def test_offset_skips_a_tram_that_is_too_soon_even_if_planned_later():
    deps = [dep(at(9, 36), 0), dep(at(9, 40), 0)]  # 09:36 is only 6 minutes away
    assert hafas.select_upcoming(deps, offset_minutes=8, **KW).planned == at(9, 40)


def test_offset_compares_at_minute_resolution():
    # Trigger fires at 09:15:00.2; the 09:23 tram must still count for an 8 minute offset.
    now = datetime(2026, 11, 13, 9, 15, 0, 200_000, tzinfo=CET)
    deps = [dep(at(9, 23), 0), dep(at(9, 38), 0)]
    kw = {"line": "10", "direction": "Soltauer Str.", "now": now}
    assert hafas.select_upcoming(deps, offset_minutes=8, **kw).planned == at(9, 23)


def test_offset_zero_is_the_next_departure():
    deps = [dep(at(9, 23), 0), dep(at(9, 38), 0)]
    assert hafas.select_upcoming(deps, **KW).planned == at(9, 38)
    assert hafas.select_upcoming(deps, offset_minutes=0, **KW) == hafas.select_upcoming(deps, **KW)


def test_select_upcoming_ignores_other_lines_and_directions():
    deps = [dep(at(9, 38), 0, line="1"), dep(at(9, 38), 0, direction=DIR_HBF), dep(at(9, 38), 0, line="110")]
    assert hafas.select_upcoming(deps, **KW) is None


def test_select_upcoming_uses_predicted_time():
    deps = [dep(at(9, 23), 0), dep(at(9, 28), 4), dep(at(9, 38), 0)]
    assert hafas.select_upcoming(deps, **KW).planned == at(9, 28)  # predicted 09:32, still ahead


def test_select_upcoming_skips_cancelled_gone_and_other_lines():
    deps = [
        dep(at(9, 31), None, cancelled=True),
        dep(at(9, 20), 0),
        dep(at(9, 32), 0, line="21"),
        dep(at(9, 38), 0),
    ]
    assert hafas.select_upcoming(deps, **KW).planned == at(9, 38)
    assert hafas.select_upcoming([], **KW) is None


# ---- messages --------------------------------------------------------------------------


def test_describe_on_time_and_early():
    assert hafas.describe_departure(dep(at(9, 38), 0), "10")["status"] == "on-time"
    early = hafas.describe_departure(dep(at(9, 38), -1), "10")
    assert early["status"] == "on-time"
    assert early["delay_minutes"] == 0
    assert "pünktlich" in early["text"]


def test_describe_delayed_with_plural_and_singular():
    r = hafas.describe_departure(dep(at(9, 38), 3), "10")
    assert r["status"] == "delayed"
    assert r["delay_minutes"] == 3
    assert r["text"] == "Linie 10 um 09:38 geplant, tatsächlich 09:41 (3 Minuten verspätet)."
    assert "1 Minute verspätet" in hafas.describe_departure(dep(at(9, 38), 1), "10")["text"]


def test_describe_rounds_seconds_to_the_nearest_minute():
    planned = at(9, 38)
    d = hafas.Departure("10", DIR_SOLTAUER, planned, planned + timedelta(seconds=89), False)
    assert hafas.describe_departure(d, "10")["delay_minutes"] == 1
    d = hafas.Departure("10", DIR_SOLTAUER, planned, planned + timedelta(seconds=29), False)
    assert hafas.describe_departure(d, "10")["status"] == "on-time"


def test_describe_cancelled_no_realtime_and_not_found():
    c = hafas.describe_departure(dep(at(9, 38), None, cancelled=True), "10")
    assert c["status"] == "cancelled"
    assert "fällt aus" in c["text"]
    n = hafas.describe_departure(dep(at(9, 38), None), "10")
    assert n["status"] == "no-realtime"
    assert "09:38" in n["text"]
    assert hafas.describe_departure(None, "10")["status"] == "not-found"


def test_describe_upcoming_adds_minutes_until_departure():
    r = hafas.describe_upcoming(dep(at(9, 38), 3), "10", NOW)
    assert r["in_minutes"] == 11  # predicted 09:41, now 09:30
    assert r["text"].endswith("(3 Minuten verspätet). Abfahrt in 11 Min.")
    none = hafas.describe_upcoming(None, "10", NOW)
    assert none["status"] == "not-found"
    assert none["in_minutes"] is None
