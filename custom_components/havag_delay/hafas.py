"""INSA HAFAS request building, parsing and departure selection.

Pure logic without Home Assistant or network imports, so it can be unit tested on its own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

ENDPOINT = "https://reiseauskunft.insa.de/bin/mgate.exe"
BERLIN = ZoneInfo("Europe/Berlin")

# Public client identity of the INSA (Sachsen-Anhalt) HAFAS endpoint, the same one the
# open-source hafas-client library uses. Not a secret.
_CLIENT: dict[str, Any] = {
    "client": {"type": "IPH", "id": "NASA", "v": "4000200", "name": "nasaPROD"},
    "ext": "NASA.1",
    "ver": "1.44",
    "auth": {"type": "AID", "aid": "nasa-apps"},
}


class HafasError(Exception):
    """The endpoint answered with an error."""


@dataclass(frozen=True)
class Stop:
    """A stop returned by a location search."""

    id: str
    name: str


@dataclass(frozen=True)
class Departure:
    """One departure of a line from the stop."""

    line: str
    direction: str
    planned: datetime
    actual: datetime | None
    cancelled: bool

    @property
    def effective(self) -> datetime:
        """Predicted time, falling back to the planned time."""
        return self.actual or self.planned


def _body(meth: str, req: dict[str, Any]) -> dict[str, Any]:
    return {
        "lang": "de",
        "svcReqL": [{"cfg": {"polyEnc": "GPA"}, "meth": meth, "req": req}],
        **_CLIENT,
    }


def build_station_board_request(stop_id: str, now: datetime, duration: int = 60) -> dict[str, Any]:
    """Request body for the departures of a stop, starting at ``now`` (Halle local time)."""
    local = now.astimezone(BERLIN)
    return _body(
        "StationBoard",
        {
            "type": "DEP",
            "date": local.strftime("%Y%m%d"),
            "time": local.strftime("%H%M%S"),
            "stbLoc": {"type": "S", "extId": stop_id, "lid": f"A=1@L={stop_id}@"},
            "dur": duration,
            "maxJny": 40,
        },
    )


def build_location_request(query: str) -> dict[str, Any]:
    """Request body for a stop name search."""
    return _body(
        "LocMatch",
        {"input": {"loc": {"type": "S", "name": query}, "maxLoc": 10, "field": "S"}},
    )


def _service_result(raw: dict[str, Any]) -> dict[str, Any]:
    svc = (raw.get("svcResL") or [{}])[0]
    if raw.get("err") != "OK" or svc.get("err") != "OK":
        raise HafasError(svc.get("err") or raw.get("err") or "unknown")
    return svc.get("res") or {}


def _to_datetime(date: str, time: str, tz_minutes: int) -> datetime:
    """Convert HAFAS ``YYYYMMDD`` plus ``HHMMSS`` (or ``DDHHMMSS`` with day offset)."""
    day_offset = int(time[:-6]) if len(time) > 6 else 0
    t = time[-6:]
    tz = timezone(timedelta(minutes=tz_minutes))
    base = datetime(
        int(date[:4]), int(date[4:6]), int(date[6:8]), int(t[:2]), int(t[2:4]), int(t[4:6]), tzinfo=tz
    )
    return base + timedelta(days=day_offset)


def parse_departures(raw: dict[str, Any]) -> list[Departure]:
    """Read the departures out of a raw StationBoard response."""
    res = _service_result(raw)
    prods = (res.get("common") or {}).get("prodL") or []
    departures: list[Departure] = []
    for jny in res.get("jnyL") or []:
        stop = jny.get("stbStop") or {}
        if not stop.get("dTimeS"):
            continue
        tz = stop.get("dTZOffset", 60)
        prodx = jny.get("prodX")
        prod = prods[prodx] if isinstance(prodx, int) and 0 <= prodx < len(prods) else {}
        departures.append(
            Departure(
                line=prod.get("nameS") or prod.get("number") or "",
                direction=jny.get("dirTxt") or "",
                planned=_to_datetime(jny["date"], stop["dTimeS"], tz),
                actual=_to_datetime(jny["date"], stop["dTimeR"], tz) if stop.get("dTimeR") else None,
                cancelled=bool(stop.get("dCncl")),
            )
        )
    return departures


def parse_stops(raw: dict[str, Any]) -> list[Stop]:
    """Read the stops out of a raw location search response."""
    res = _service_result(raw)
    stops: list[Stop] = []
    for loc in (res.get("match") or {}).get("locL") or []:
        name = loc.get("name") or ""
        if loc.get("type") != "S" or not loc.get("extId") or name.endswith("(virt.)"):
            continue
        stops.append(Stop(id=str(loc["extId"]), name=name))
    return stops


def _matches(dep: Departure, line: str, direction: str) -> bool:
    return dep.line == line and direction.lower() in dep.direction.lower()


def select_upcoming(
    departures: list[Departure],
    *,
    line: str,
    direction: str,
    now: datetime,
    offset_minutes: int = 0,
) -> Departure | None:
    """Pick the first non-cancelled departure predicted at least ``offset_minutes`` from now.

    Uses the predicted time, so a late tram that was planned earlier still counts and a tram
    that has already left does not. Times have minute precision, so ``now`` is compared at
    minute resolution (a 09:15:00 check keeps a tram predicted for 09:23 with an 8 minute offset).
    """
    earliest = now.replace(second=0, microsecond=0) + timedelta(minutes=offset_minutes)
    candidates = [
        d
        for d in departures
        if not d.cancelled and _matches(d, line, direction) and d.effective >= earliest
    ]
    return min(candidates, key=lambda d: d.effective, default=None)


def _clock(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def describe_departure(dep: Departure | None, line: str) -> dict[str, Any]:
    """Result dictionary with a German message for notifications."""
    if dep is None:
        return {
            "status": "not-found",
            "planned": None,
            "actual": None,
            "delay_minutes": None,
            "cancelled": False,
            "text": f"Keine passende Abfahrt der Linie {line} gefunden.",
        }
    result: dict[str, Any] = {
        "planned": dep.planned.isoformat(),
        "actual": dep.actual.isoformat() if dep.actual else None,
        "cancelled": dep.cancelled,
    }
    planned = _clock(dep.planned)
    if dep.cancelled:
        return {
            **result,
            "actual": None,
            "status": "cancelled",
            "delay_minutes": None,
            "text": f"Linie {line} um {planned} fällt aus.",
        }
    if dep.actual is None:
        return {
            **result,
            "status": "no-realtime",
            "delay_minutes": None,
            "text": f"Linie {line} um {planned} geplant, keine Echtzeitdaten verfügbar.",
        }
    delay = math.floor((dep.actual - dep.planned).total_seconds() / 60 + 0.5)
    if delay <= 0:
        return {
            **result,
            "status": "on-time",
            "delay_minutes": 0,
            "text": f"Linie {line} um {planned} ist pünktlich.",
        }
    unit = "Minute" if delay == 1 else "Minuten"
    return {
        **result,
        "status": "delayed",
        "delay_minutes": delay,
        "text": (
            f"Linie {line} um {planned} geplant, tatsächlich {_clock(dep.actual)} "
            f"({delay} {unit} verspätet)."
        ),
    }


def describe_upcoming(dep: Departure | None, line: str, now: datetime) -> dict[str, Any]:
    """Like ``describe_departure`` plus the minutes until departure."""
    result = describe_departure(dep, line)
    if dep is None:
        return {**result, "in_minutes": None}
    in_minutes = max(0, math.floor((dep.effective - now).total_seconds() / 60 + 0.5))
    return {**result, "in_minutes": in_minutes, "text": f"{result['text']} Abfahrt in {in_minutes} Min."}
