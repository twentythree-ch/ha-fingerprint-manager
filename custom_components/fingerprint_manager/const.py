"""Constants for the Fingerprint Manager integration."""

DOMAIN = "fingerprint_manager"

# ── Configuration keys ────────────────────────────────────────────────────────
CONF_SENSOR_ENTITY = "sensor_entity_id"
CONF_EVENT_TYPE = "event_type"
CONF_ESPHOME_DEVICE = "esphome_device"

# Default ESPHome event name fired on every fingerprint scan
DEFAULT_EVENT_TYPE = "esphome.fingerprint_scan"

# ── Options storage key ───────────────────────────────────────────────────────
FINGERPRINT_STORAGE = "fingerprints"

# ── HA events fired by this component ────────────────────────────────────────
EVENT_FINGERPRINT_SCAN = "fingerprint_manager_scan"
EVENT_FINGERPRINT_ENROLLED = "fingerprint_manager_enrolled"

# ── Service names ─────────────────────────────────────────────────────────────
SERVICE_START_ENROLLMENT = "start_enrollment"
SERVICE_CANCEL_ENROLLMENT = "cancel_enrollment"
SERVICE_DELETE_FINGERPRINT = "delete_fingerprint"
SERVICE_UPDATE_FINGERPRINT = "update_fingerprint"

# ── Common attribute keys ─────────────────────────────────────────────────────
ATTR_FINGERPRINT_ID = "fingerprint_id"
ATTR_USER = "user"
ATTR_LABEL = "label"
ATTR_MATCHED = "matched"
ATTR_CONFIDENCE = "confidence"
ATTR_NUM_SCANS = "num_scans"

# ── Status values ─────────────────────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_ENROLLING = "enrolling"
STATE_MATCHED = "matched"
STATE_UNKNOWN_FINGER = "unknown_finger"
