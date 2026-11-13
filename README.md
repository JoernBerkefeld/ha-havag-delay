# ha-havag-delay

Small HTTP service that reports the live delay of a HAVAG departure, for use in Home Assistant notifications.

Default setup: line **10** towards **Soltauer Str.** at **Halle (Saale), Betriebshof Freiimfelder Str.** (stop ID `3937`). Each call looks up the line 10 departure scheduled **8 minutes** from now (±3 min) and returns its actual time and delay.

Data comes from the INSA HAFAS endpoint through `hafas-client`. It is unofficial, so the service caches for 45 s. Do not poll it more often than about once a minute.

## API

`GET /next?stop=&line=&direction=&offset=&tolerance=` (all optional, defaults in `config.json`): the departure planned `offset` minutes from now.

`GET /upcoming?stop=&line=&direction=`: the next non-cancelled departure from now on; the reply adds `inMinutes`.

```json
{
    "status": "delayed",
    "planned": "2026-11-13T09:38:00+01:00",
    "actual": "2026-11-13T09:41:00+01:00",
    "delayMinutes": 3,
    "cancelled": false,
    "text": "Linie 10 um 09:38 geplant, tatsächlich 09:41 (3 Minuten verspätet)."
}
```

`status` is one of `on-time`, `delayed`, `cancelled`, `no-realtime`, `not-found`, `error`.

## Another stop or line

```bash
npm run find-stop -- "Marktplatz"
```

Put the printed ID in `config.json` (`stop`) or pass `stop=`, `line=`, `direction=` in the URL of the Home Assistant `rest_command`.

## Run locally

```bash
npm ci --no-workspaces
npm test
npm start
```

## Install on Home Assistant OS

1. Copy this folder (without `node_modules`) to the `addons` share of Home Assistant, for example `\\homeassistant\addons\havag_delay`.
2. Settings > Add-ons > Add-on Store > menu > Check for updates. Under "Local add-ons", install **HAVAG Delay** and start it.
3. Note the add-on hostname on its Info page. Use it in the `url` of `rest_command.havag_next`. If it differs from `local-havag-delay`, change it.
4. Add `homeassistant/configuration-snippet.yaml` to `configuration.yaml` and restart.
5. Create the automation from `homeassistant/automation.yaml` and replace the two notify services.

The three check times (default 09:15, 09:30, 09:45, Monday to Friday) are the helpers `input_datetime.havag_check_1..3`. Edit them under Settings > Devices & services > Helpers. Note: `initial` in the snippet resets them to these defaults on every Home Assistant restart; remove `initial` once you have set your own times in the UI.

## Door notifications

`homeassistant/automation-door.yaml` sends the next line 10 departure (`/upcoming`, no offset) when a door contact opens: 09:15-10:15 to your phone, 14:30-15:30 to your wife's phone, with a 10-minute cooldown. Replace the door sensor and both notify placeholders.

## Test without waiting

Developer Tools > Actions: run `rest_command.havag_next` and read the response, or run the automation manually.
