#!/usr/bin/env python3
import os, json, time, signal, threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# ---- config via env ----
BROKER   = os.getenv('MAILCAM_MQTT_HOST', '10.0.0.2')
USER     = os.getenv('MAILCAM_MQTT_USER', 'delivery')
PASS     = os.getenv('MAILCAM_MQTT_PASS', 'changeme')
TOPIC    = os.getenv('MAILCAM_MQTT_TOPIC', 'home/mailcam/delivery')
STATE    = os.getenv('MAILCAM_STATE_FILE','/var/tmp/mailcam_delivery_state.json')
RESET_H  = int(os.getenv('MAILCAM_RESET_HOUR','3'))  # reset “today” at 03:00

LOCK = threading.Lock()
CURR = set()
TODAY= set()
LAST_RESET_DAY = None

def _now_ts():
    return int(time.time())

def _local_day():
    return datetime.now().timetuple().tm_yday

def _ensure_reset_if_needed():
    global TODAY, LAST_RESET_DAY
    day = _local_day()
    hour = datetime.now().hour
    if LAST_RESET_DAY != day and hour >= RESET_H:
        TODAY = set()
        LAST_RESET_DAY = day

def _load_state():
    global CURR, TODAY, LAST_RESET_DAY
    try:
        with open(STATE, 'r') as f:
            s = json.load(f)
        CURR  = set(s.get('current', []))
        TODAY = set(s.get('today', []))
        LAST_RESET_DAY = _local_day()
    except Exception:
        CURR, TODAY = set(), set()
        LAST_RESET_DAY = _local_day()

def _write_state():
    tmp = STATE + ".tmp"
    out = {
        "ts": _now_ts(),
        "current": sorted(CURR),
        "today": sorted(TODAY)
    }
    with open(tmp, 'w') as f:
        json.dump(out, f)
    os.replace(tmp, STATE)

def _coerce_services(payload: dict):
    """
    Accept both payload shapes:

    A) event schema:
       {"entered":[...], "current":[...], "today":[...], "ts":...}

    B) simple schema (from restream /simulate):
       {"timestamp":"YYYY-mm-dd HH:MM:SS", "services":[...]}
    """
    if any(k in payload for k in ("entered","current","today")):
        entered = set(map(str.lower, payload.get("entered", [])))
        current = set(map(str.lower, payload.get("current", [])))
        today   = set(map(str.lower, payload.get("today",   [])))
        ts      = payload.get("ts", _now_ts())
        return entered, current, today, ts

    if "services" in payload:
        services = set(map(str.lower, payload.get("services", [])))
        # Treat this as “entered”; we’ll merge into current/today below
        return services, set(), set(), _now_ts()

    # Unknown schema; ignore
    return set(), set(), set(), None

def on_connect(cli, userdata, flags, rc, properties=None):
    print(f"[sidecar] connected rc={rc}; subscribing {TOPIC}", flush=True)
    cli.subscribe(TOPIC)

def on_message(cli, userdata, msg):
    global CURR, TODAY
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
    except Exception as e:
        print(f"[sidecar] bad json: {e}", flush=True); return

    entered, current, today, ts = _coerce_services(payload)
    if ts is None:
        print(f"[sidecar] ignored payload (unknown schema): {payload}", flush=True)
        return

    with LOCK:
        _ensure_reset_if_needed()
        changed = False

        if entered:
            CURR |= entered
            TODAY |= entered
            changed = True

        if current:
            CURR = set(current)
            changed = True

        if today:
            TODAY = set(today)
            changed = True

        if changed:
            _write_state()
            print(f"[sidecar] wrote state: curr={sorted(CURR)} today={sorted(TODAY)}", flush=True)

def main():
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    _load_state()
    _ensure_reset_if_needed()
    _write_state()

    c = mqtt.Client()
    c.username_pw_set(USER, PASS)
    c.on_connect = on_connect
    c.on_message = on_message

    c.connect(BROKER, 1883, 60)
    try:
        c.loop_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
