# HAVAG Delay

Home Assistant custom integration that tells automations whether a HAVAG (Halle/Saale) tram or bus is on time, and how late it is.

It reads the live data of the INSA timetable service (the same data the official app shows). The endpoint is unofficial, so use it for personal automations and keep the call rate low.

## Install with HACS

1. HACS > three-dot menu > **Custom repositories**.
2. Add `https://github.com/JoernBerkefeld/ha-havag-delay` as category **Integration**.
3. Find **HAVAG Delay** in HACS, download it, restart Home Assistant.
4. Settings > Devices & services > **Add integration** > **HAVAG Delay**.
5. Enter a stop name (for example `Betriebshof Freiimfelder`), the line (`10`) and optionally a direction (`Soltauer Str.`, a part of the destination name). Pick the stop from the results.

Set up one entry per line and direction.

## The action `havag_delay.get_departure`

Returns a result for use in automations. Nothing is cached: each call fetches live data.

| Field | Meaning |
|---|---|
| `offset_minutes` (optional) | Only consider departures predicted at least this many minutes from now, for example the time you need to reach the stop. Leave it out (or 0) for the very next departure. |
| `config_entry_id` (optional) | Which line to use. Only needed if you set up several. |

The action always returns the **next tram to arrive, by predicted time** (cancelled ones are skipped). A late tram that was planned earlier still counts while it has not left yet, and a tram that has already gone does not. With and without an offset the same rule applies, so the two never disagree. Times have minute precision, so "now" is compared at minute resolution: a check at 09:15 with an offset of 8 includes a tram predicted for 09:23.

Result:

```yaml
status: delayed          # on-time | delayed | cancelled | no-realtime | not-found | error
planned: "2026-11-13T09:38:00+01:00"
actual: "2026-11-13T09:41:00+01:00"
delay_minutes: 3
cancelled: false
in_minutes: 11           # minutes until the predicted departure
text: "Linie 10 um 09:38 geplant, tatsächlich 09:41 (3 Minuten verspätet). Abfahrt in 11 Min."
```

If the timetable service cannot be reached, the action returns `status: error` with a message in `text` instead of failing, so a notification still goes out.

Use it with `response_variable`:

```yaml
actions:
  - action: havag_delay.get_departure
    data:
      offset_minutes: 8
    response_variable: havag
  - action: notify.mobile_app_YOUR_PHONE
    data:
      message: "{{ havag.text }}"
```

## Examples

- `examples/automation-morning.yaml`: Mon-Fri checks at three times, each for the first tram predicted at least 8 minutes later, to a phone and Alexa.
- `examples/automation-door.yaml`: when a door opens in a time window, send the next departure to one phone in the morning and another in the afternoon.
- `examples/helpers.yaml`: the three editable check times.

Replace the `YOUR_...` placeholders with your own notify services and door sensor.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The Home Assistant test plugin needs Linux. On Windows, run the pure logic tests only:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_hafas.py --noconftest
```

The earlier Node.js and add-on version is in the git history.
