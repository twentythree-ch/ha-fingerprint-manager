"""Constants for the Fingerprint Manager integration."""

DOMAIN = "fingerprint_manager"

# ── Configuration keys ────────────────────────────────────────────────────────
# Optional: sensor entity from the ESPHome device that shows the last finger ID.
CONF_SENSOR_ENTITY = "sensor_entity_id"

# Required: the event prefix used in the ESPHome YAML (e.g. "esphome.test_node").
# All esphome `homeassistant.event` calls in the template must share this prefix.
CONF_EVENT_PREFIX = "event_prefix"

# Required: ESPHome device name as seen in HA services (hyphens → underscores),
# e.g. "esphome_garage_fingerprint" for a device named "esphome-garage-fingerprint".
CONF_ESPHOME_DEVICE = "esphome_device"

# ── ESPHome event suffixes (appended to CONF_EVENT_PREFIX) ───────────────────
# These match the event names used in the ESPHome template:
#   on_finger_scan_matched  → {prefix}_finger_scan_matched
#   on_enrollment_scan      → {prefix}_enrollment_scan
#   on_enrollment_done      → {prefix}_enrollment_done
#   on_enrollment_failed    → {prefix}_enrollment_failed
EVENT_SUFFIX_MATCHED = "_finger_scan_matched"
EVENT_SUFFIX_UNMATCHED = "_finger_scan_unmatched"
EVENT_SUFFIX_INVALID = "_finger_scan_invalid"
EVENT_SUFFIX_MISPLACED = "_finger_scan_misplaced"
EVENT_SUFFIX_ENROLLMENT_SCAN = "_enrollment_scan"
EVENT_SUFFIX_ENROLLMENT_DONE = "_enrollment_done"
EVENT_SUFFIX_ENROLLMENT_FAILED = "_enrollment_failed"

# ── Options storage key ───────────────────────────────────────────────────────
FINGERPRINT_STORAGE = "fingerprints"

# ── HA events fired by this component ────────────────────────────────────────
EVENT_FINGERPRINT_SCAN = "fingerprint_manager_scan"
EVENT_FINGERPRINT_ENROLLED = "fingerprint_manager_enrolled"
EVENT_FINGERPRINT_ENROLLMENT_FAILED = "fingerprint_manager_enrollment_failed"

# ── Service names ─────────────────────────────────────────────────────────────
SERVICE_START_ENROLLMENT = "start_enrollment"
SERVICE_CANCEL_ENROLLMENT = "cancel_enrollment"
SERVICE_DELETE_FINGERPRINT = "delete_fingerprint"
SERVICE_DELETE_ALL_FINGERPRINTS = "delete_all_fingerprints"
SERVICE_UPDATE_FINGERPRINT = "update_fingerprint"

# ── Common attribute keys ─────────────────────────────────────────────────────
ATTR_FINGERPRINT_ID = "fingerprint_id"
ATTR_USER = "user"
ATTR_LABEL = "label"
ATTR_MATCHED = "matched"
ATTR_CONFIDENCE = "confidence"
ATTR_NUM_SCANS = "num_scans"
ATTR_SCAN_NUM = "scan_num"

# ── Status values ─────────────────────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_ENROLLING = "enrolling"
STATE_MATCHED = "matched"
STATE_UNKNOWN_FINGER = "unknown_finger"
STATE_INVALID_SCAN = "invalid_scan"
STATE_FINGER_MISPLACED = "finger_misplaced"
