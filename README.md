# Fingerprint Manager for Home Assistant

A custom Home Assistant integration that bridges an **ESPHome-based fingerprint reader** (Grow R503 / Grow 503 and compatible) with Home Assistant, providing:

- **Named users** — assign a person's name to each fingerprint slot
- **Multiple fingers per user** — enroll as many slots as you like for the same user
- **Automation triggers** — every scan fires a `fingerprint_manager_scan` event carrying the user name, perfect for automations (open a garage, unlock a door, …)
- **Services** — enroll, delete, and rename fingerprints directly from the HA UI or automations
- **Status sensors** — real-time reader state and last-user sensors

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | 2024.1 or newer |
| ESPHome device | Grow R503 / Grow 503 or any `fingerprint_grow`-based build |
| ESPHome firmware | Must use `homeassistant.event` actions (see [ESPHome configuration](#esphome-configuration)) |

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → *Custom repositories*
2. Add `https://github.com/twentythree-ch/ha-fingerprint-manager` as an **Integration**
3. Search for **Fingerprint Manager** and install it
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/fingerprint_manager/` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## ESPHome Configuration

Your ESPHome YAML must fire `homeassistant.event` actions so the component can receive scan and enrollment results.

A ready-to-use template is provided in [`esphome_example.yaml`](esphome_example.yaml).

**Key points:**

- All events share a common prefix (e.g. `esphome.garage_fingerprint`).  
  Set this prefix in the integration options as **Event prefix**.
- The ESPHome device exposes four HA actions via its `api:` block:  
  `enroll`, `cancel_enroll`, `delete`, `delete_all`.  
  These are called automatically by the integration's services.

**Events fired by ESPHome → received by this component:**

| ESPHome trigger | HA event (with prefix `esphome.garage_fingerprint`) | Data |
|---|---|---|
| `on_finger_scan_matched` | `esphome.garage_fingerprint_finger_scan_matched` | `finger_id`, `confidence` |
| `on_finger_scan_unmatched` | `esphome.garage_fingerprint_finger_scan_unmatched` | — |
| `on_finger_scan_invalid` | `esphome.garage_fingerprint_finger_scan_invalid` | — (status → `invalid_scan`) |
| `on_finger_scan_misplaced` | `esphome.garage_fingerprint_finger_scan_misplaced` | — (status → `finger_misplaced`) |
| `on_enrollment_scan` | `esphome.garage_fingerprint_enrollment_scan` | `finger_id`, `scan_num` |
| `on_enrollment_done` | `esphome.garage_fingerprint_enrollment_done` | `finger_id` |
| `on_enrollment_failed` | `esphome.garage_fingerprint_enrollment_failed` | `finger_id` |

---

## Setup in Home Assistant

1. Go to **Settings → Devices & Services → Add Integration → Fingerprint Manager**
2. Fill in the form:

| Field | Example | Description |
|---|---|---|
| **Name** | Garage Fingerprint Reader | Friendly name for the integration instance |
| **Event prefix** | `esphome.garage_fingerprint` | The common prefix of all `homeassistant.event` calls in your ESPHome YAML |
| **ESPHome device name** | `esphome_garage_fingerprint` | HA service prefix for the device (device name with hyphens replaced by underscores) |
| **Fingerprint ID sensor** | `sensor.garage_fingerprint_fingerprint_id` | Optional — the ESPHome sensor showing the last matched finger ID |

> **Tip:** The ESPHome device name can be found by inspecting the available services under **Developer Tools → Services** and looking for `esphome.<device>_enroll`.

---

## Entities

After setup, two sensor entities are created under a **Fingerprint Manager** device:

| Entity | Description | Example states |
|---|---|---|
| `sensor.<name>_status` | Current reader state | `idle`, `matched`, `unknown_finger`, `invalid_scan`, `finger_misplaced`, `enrolling`, `enrolling_1`, `enrolling_2` |
| `sensor.<name>_last_user` | Name of the last matched user | `Alice`, `Bob`, `null` |

The **Status** sensor also exposes all enrolled fingerprint mappings as the `fingerprints` attribute (list of `{fingerprint_id, user, label}` dicts).

---

## Services

All services are available under the `fingerprint_manager` domain.

### `fingerprint_manager.start_enrollment`

Enroll a new fingerprint and assign it to a user.

```yaml
service: fingerprint_manager.start_enrollment
data:
  fingerprint_id: 5        # slot 1–200
  user: Alice
  label: Left index finger  # optional
  num_scans: 2             # optional, default 2
```

The integration immediately:
1. Pre-registers the slot → user mapping in Home Assistant
2. Calls `esphome.<device>_enroll` so the reader starts scanning
3. Waits for the `enrollment_done` event (green LED breathing) or `enrollment_failed` (red flashing)

On failure the mapping is automatically removed.

---

### `fingerprint_manager.cancel_enrollment`

Abort the current enrollment.

```yaml
service: fingerprint_manager.cancel_enrollment
```

---

### `fingerprint_manager.delete_fingerprint`

Delete one slot from both the HA mapping and the ESPHome reader.

```yaml
service: fingerprint_manager.delete_fingerprint
data:
  fingerprint_id: 5
```

---

### `fingerprint_manager.delete_all_fingerprints`

Wipe **all** slots from the HA mapping and the ESPHome reader.

```yaml
service: fingerprint_manager.delete_all_fingerprints
```

---

### `fingerprint_manager.update_fingerprint`

Rename a fingerprint mapping (no hardware interaction).

```yaml
service: fingerprint_manager.update_fingerprint
data:
  fingerprint_id: 5
  user: Alice          # optional
  label: Right thumb   # optional
```

---

## Events

### `fingerprint_manager_scan`

Fired on every scan (matched **and** unmatched).

```yaml
event_type: fingerprint_manager_scan
data:
  fingerprint_id: 5          # integer; null for unmatched
  user: Alice                # null for unmatched / unknown finger
  label: Left index finger   # null for unmatched / unknown finger
  matched: true              # false if not recognised
  confidence: 98             # present only for matched scans
  config_entry_id: abc123
```

### `fingerprint_manager_enrolled`

Fired when ESPHome confirms a successful enrollment (`on_enrollment_done`).

```yaml
event_type: fingerprint_manager_enrolled
data:
  fingerprint_id: 5
  user: Alice
  label: Left index finger
  config_entry_id: abc123
```

### `fingerprint_manager_enrollment_failed`

Fired when ESPHome reports an enrollment failure (`on_enrollment_failed`).

```yaml
event_type: fingerprint_manager_enrollment_failed
data:
  fingerprint_id: 5
  config_entry_id: abc123
```

---

## Example Automations

### Open the garage when Alice or Bob scans their finger

```yaml
automation:
  alias: Garage fingerprint access
  trigger:
    - platform: event
      event_type: fingerprint_manager_scan
      event_data:
        matched: true
  condition:
    - condition: template
      value_template: "{{ trigger.event.data.user in ['Alice', 'Bob'] }}"
  action:
    - service: cover.open_cover
      target:
        entity_id: cover.garage_door
```

### Notify on unknown fingerprint

```yaml
automation:
  alias: Unknown finger alert
  trigger:
    - platform: event
      event_type: fingerprint_manager_scan
      event_data:
        matched: false
  action:
    - service: notify.mobile_app_my_phone
      data:
        message: "Unknown fingerprint scanned at garage reader!"
```

### Enroll Alice's left index finger via script

```yaml
script:
  enroll_alice:
    alias: Enroll Alice slot 1
    sequence:
      - service: fingerprint_manager.start_enrollment
        data:
          fingerprint_id: 1
          user: Alice
          label: Left index finger
          num_scans: 2
```

---

## How it Works

```
ESPHome reader                    Home Assistant
─────────────────                 ─────────────────────────────────────────
finger placed
  → fingerprint_grow matches      → fires esphome.<prefix>_finger_scan_matched
                                         (finger_id, confidence)
                                  → Fingerprint Manager looks up user
                                  → fires fingerprint_manager_scan
                                         (user, label, matched, confidence)
                                  → your automation triggers ✓

service start_enrollment called
                                  → fingerprint_manager pre-registers mapping
                                  → calls esphome.<device>_enroll
ESPHome reader starts scanning
  → on_enrollment_scan            → fires esphome.<prefix>_enrollment_scan
                                         → status sensor: enrolling_1
  → on_enrollment_done            → fires esphome.<prefix>_enrollment_done
                                         → status sensor: idle
                                         → fires fingerprint_manager_enrolled
  (or on_enrollment_failed)       → fires esphome.<prefix>_enrollment_failed
                                         → mapping removed, fires …_enrollment_failed
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| No scan events received | Verify the **Event prefix** matches your ESPHome YAML exactly (case-sensitive) |
| `start_enrollment` does nothing | Verify **ESPHome device name** matches `esphome.<device>_enroll` in Developer Tools → Services |
| Sensor not updating | Sensor monitoring is optional; rely on events (prefix-based) for reliability |
| Unknown finger scanned | The slot is not registered — use `start_enrollment` to enroll it |

---

## License

MIT
