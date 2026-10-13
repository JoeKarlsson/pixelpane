# Home Assistant

The board doesn't read Home Assistant; Home Assistant pushes to the board. That
way the board needs no HA token, and it can live on an isolated IoT network as
long as Home Assistant can reach it. Replace `pixelpane.local` below with
your board's address.

## 1. REST commands, a status sensor and a light

`configuration.yaml` (then reload REST commands, RESTful sensors and templates
from Developer tools, no restart needed):

```yaml
rest_command:
  pixelpane:
    url: "http://pixelpane.local/api/{{ path }}"
    method: POST
    content_type: application/json
    timeout: 5
    payload: "{{ body | default({}) | tojson }}"
  pixelpane_unpin:
    url: http://pixelpane.local/api/pin
    method: DELETE
    timeout: 5

rest:
  - resource: http://pixelpane.local/api/health
    scan_interval: 60
    sensor:
      - name: PixelPane
        unique_id: pixelpane_status
        value_template: "{{ value_json.scene }}"
        json_attributes: [power, brightness, pinned, themes, temp_c, throttled, version]

template:
  - light:
      - name: PixelPane
        unique_id: pixelpane_light
        state: "{{ state_attr('sensor.pixelpane', 'power') == true }}"
        level: "{{ ((state_attr('sensor.pixelpane', 'brightness') or 0) * 2.55) | round(0) | int }}"
        effect_list: "{{ ['Playlist', 'On Air', 'Clock', 'Weather', 'Seasonal', 'Fire', 'Plasma'] }}"
        effect: >-
          {% set p = (state_attr('sensor.pixelpane', 'pinned') or {}).get('scene') %}
          {{ {'on_air': 'On Air', 'clock': 'Clock', 'weather': 'Weather', 'seasonal': 'Seasonal',
              'fire': 'Fire', 'plasma': 'Plasma'}.get(p, 'Playlist') }}
        turn_on:
          - action: rest_command.pixelpane
            data: {path: state, body: {power: true}}
          - action: homeassistant.update_entity
            target: {entity_id: sensor.pixelpane}
        turn_off:
          - action: rest_command.pixelpane
            data: {path: state, body: {power: false}}
          - action: homeassistant.update_entity
            target: {entity_id: sensor.pixelpane}
        set_level:
          - action: rest_command.pixelpane
            data:
              path: state
              body: {power: true, brightness: "{{ [1, (brightness / 2.55) | round(0) | int] | max }}"}
        set_effect:
          - if: "{{ effect == 'Playlist' }}"
            then: [{action: rest_command.pixelpane_unpin}]
            else:
              - action: rest_command.pixelpane
                data:
                  path: pin
                  body:
                    scene: >-
                      {{ {'On Air': 'on_air', 'Clock': 'clock', 'Weather': 'weather',
                          'Fire': 'fire', 'Plasma': 'plasma'}.get(effect, 'seasonal') }}
```

## 2. A script so routines never wait on the board

`scripts.yaml`. Call it with `script.turn_on` (not `script.pixelpane_command`
directly) and a board that's unplugged costs your routines nothing:

```yaml
pixelpane_command:
  alias: PixelPane - Send Command
  mode: parallel
  max: 10
  sequence:
    - if: "{{ unpin | default(false) }}"
      then: [{action: rest_command.pixelpane_unpin, continue_on_error: true}]
      else:
        - action: rest_command.pixelpane
          data: {path: "{{ path }}", body: "{{ body | default({}) }}"}
          continue_on_error: true
```

Add steps like these to the routines you already have:

```yaml
# doorbell
- action: script.turn_on
  target: {entity_id: script.pixelpane_command}
  data:
    variables:
      path: notify
      body: {text: Doorbell, icon: bell, color: '#ffcc00', flash: true, seconds: 15}

# meeting starts / ends
- action: script.turn_on
  target: {entity_id: script.pixelpane_command}
  data: {variables: {path: pin, body: {scene: on_air}}}
- action: script.turn_on
  target: {entity_id: script.pixelpane_command}
  data: {variables: {unpin: true}}

# bedtime / morning
- action: script.turn_on
  target: {entity_id: script.pixelpane_command}
  data: {variables: {path: state, body: {power: false}}}
```

Ideas that work well: laundry done (`washer` icon), package at the door
(`package`), front door opened (`door`), a critical homelab alert (`alert`,
flash), National Weather Service warnings (the `nws_alerts` integration), a
city snow emergency, the garage left open.

## 3. A feed automation for the live scenes

One automation keeps the data scenes fresh: every 10 minutes and whenever
something changes. Adjust the entity ids to yours; every call continues on
error so an unplugged board never fails it.

```yaml
- id: pixelpane_feed
  alias: PixelPane - Feed
  mode: queued
  max: 3
  max_exceeded: silent
  triggers:
    - trigger: time_pattern
      minutes: /10
    - trigger: state
      entity_id: media_player.office
  actions:
    - action: weather.get_forecasts
      target: {entity_id: weather.home}
      data: {type: twice_daily}
      response_variable: fc
      continue_on_error: true
    - variables:
        periods: "{{ (fc or {}).get('weather.home', {}).get('forecast', []) }}"
        player: "{{ 'media_player.office' if is_state('media_player.office', 'playing') else '' }}"
    - action: rest_command.pixelpane
      continue_on_error: true
      data:
        path: data/weather
        body:
          temp: "{{ state_attr('weather.home', 'temperature') }}"
          condition: "{{ states('weather.home') }}"
          high: "{{ periods | selectattr('is_daytime') | map(attribute='temperature') | first | default(none) }}"
          low: "{{ periods | rejectattr('is_daytime') | map(attribute='temperature') | first | default(none) }}"
    - action: rest_command.pixelpane
      continue_on_error: true
      data:
        path: data/now_playing
        body:
          state: "{{ 'playing' if player else 'idle' }}"
          title: "{{ state_attr(player, 'media_title') if player else '' }}"
          artist: "{{ state_attr(player, 'media_artist') if player else '' }}"
          art: >-
            {% set pic = state_attr(player, 'entity_picture') if player else '' %}
            {{ '' if not pic else pic if pic.startswith('http') else 'http://homeassistant.local:8123' ~ pic }}
    - action: rest_command.pixelpane
      continue_on_error: true
      data:
        path: data/tiles
        body:
          items: >-
            {{ [{'kind': 'temp', 'value': states('sensor.office_temperature') | float(0), 'label': 'office'},
                {'kind': 'aqi', 'value': states('sensor.outdoor_aqi') | float(0)},
                {'kind': 'co2', 'value': states('sensor.office_co2') | float(0), 'label': 'office'}] }}
```

A tile with a `kind` is a reading: send the raw number and the board decides how it
looks. The whole panel takes on a mood (frost creeping in when it's cold, heat
shimmer when it's hot, clear sparkling air or thick smog, condensation when it's
humid, murky bubbles when CO2 is high), the number counts up in a color that
follows it, an arrow shows the trend over the last half hour and a sparkline the
last five hours. When a reading turns bad (unhealthy air, too hot or cold, stuffy,
low battery) the board shows that tile right away, once an hour at most. The
comfortable range, colors and alerts are in the tiles plugin's settings.

For album art, let the board fetch from Home Assistant:
`{"plugins": {"now_playing": {"art_hosts": ["http://homeassistant.local:8123/"]}}}`.

## Data the scenes understand

| Key | Fields |
|-----|--------|
| `weather` | `temp`, `condition` (HA's names: sunny, rainy, partlycloudy, ...), `high`, `low`, `precip` (%), `wind` (mph: slants the rain, and 15 or more adds streaks), `unit` (`F` or `C`) |
| `now_playing` | `state` (playing/idle), `title`, `artist`, `player`, `art` (image URL under an allowed host) |
| `next_event` | `title`, `start` (ISO time; shown if within 12 hours) |
| `homelab` | `alerts`, `names`, `warnings`, `checks_total`, `checks_passing`, `hosts: [{name, cpu, temp}]`, `nas: {used_pct, used_tb, up_mbs, down_mbs}`, `net: {wan_ms, dns_queries, blocked_pct}`, `ups: [{battery, load, status}]`, `plex: {watching}`. Every page is optional |
| `tiles` | `items`, a list of readings `{kind, value, label, unit, history, alert}` and cards `{icon, text, color, level (0-1, draws a gauge), sub}`. `kind` is `temp`, `aqi` (US EPA), `humidity` (%), `co2` (ppm) or `battery` (%). `unit` (`F`/`C`) overrides the plugin's for one temp tile; `history` (a list of earlier values) replaces the board's own samples; `"alert": false` stops that tile jumping the queue |
