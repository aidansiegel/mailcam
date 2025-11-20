#!/usr/bin/env python3
"""
Mailcam Detector - Pure ONNX Runtime implementation
Fetches images from HTTP snapshot URL and runs delivery detection model
"""
import os
import sys
import time
import json
import yaml
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timedelta

import numpy as np
from PIL import Image
import requests
import paho.mqtt.client as mqtt

# Optional: set single-threaded for lower CPU usage
os.environ.setdefault("ORT_NUM_THREADS", "1")

try:
    import onnxruntime as ort
except ImportError:
    print("[mailcam] ERROR: onnxruntime not available", flush=True)
    sys.exit(1)

# ===== Configuration =====
CFG_PATH = Path(__file__).with_name("mailcam.yml")

def load_config():
    """Load and validate configuration"""
    if not CFG_PATH.exists():
        print(f"[mailcam] ERROR: Config not found at {CFG_PATH}", flush=True)
        sys.exit(1)

    with open(CFG_PATH) as f:
        cfg = yaml.safe_load(f)

    # Validate required sections
    for section in ("model", "mqtt", "source"):
        if section not in cfg:
            print(f"[mailcam] ERROR: Missing '{section}' in config", flush=True)
            sys.exit(1)

    return cfg

CFG = load_config()
MODEL_CFG = CFG["model"]
MQTT_CFG = CFG["mqtt"]
SOURCE_CFG = CFG["source"]

# Model parameters
MODEL_PATH = MODEL_CFG["path"]
IMGSZ = int(MODEL_CFG.get("imgsz", 640))
CONF_MIN = float(MODEL_CFG.get("conf_min", 0.30))
AREA_MIN_FRAC = float(MODEL_CFG.get("area_min_frac", 0.0005))
ALLOW_LABELS = set(MODEL_CFG.get("allow_labels", []))

# MQTT parameters
MQTT_HOST = MQTT_CFG["host"]
MQTT_PORT = int(MQTT_CFG.get("port", 1883))
MQTT_USER = MQTT_CFG.get("user", "")
MQTT_PASS = MQTT_CFG.get("password", "")
STATE_TOPIC = MQTT_CFG.get("state_topic", "mailcam/state")
DETAIL_TOPIC = MQTT_CFG.get("detail_topic", "mailcam/details")

# Source parameters
SOURCE_KIND = SOURCE_CFG.get("kind", "image")
SOURCE_URL = SOURCE_CFG.get("url", "")
POLL_SEC = float(SOURCE_CFG.get("poll_sec", 2.5))
TIMEOUT_SEC = float(SOURCE_CFG.get("timeout_sec", 5.0))

# Allow override via environment
POLL_SEC = float(os.getenv("MAILCAM_POLL", POLL_SEC))

print(f"[mailcam] Config loaded from {CFG_PATH}", flush=True)
print(f"[mailcam] Model: {MODEL_PATH}", flush=True)
print(f"[mailcam] Source: {SOURCE_KIND} @ {SOURCE_URL}", flush=True)
print(f"[mailcam] Poll interval: {POLL_SEC}s", flush=True)
print(f"[mailcam] Allow labels: {sorted(ALLOW_LABELS)}", flush=True)

# ===== Daily Carrier Tracking =====
class DailyCarrierTracker:
    """Tracks daily carrier detections with 3 AM reset"""

    def __init__(self, carriers: List[str], reset_hour: int = 3):
        self.carriers = carriers
        self.reset_hour = reset_hour
        self.detections = {carrier: None for carrier in carriers}  # Stores timestamp or None
        self.current_day = self._get_current_day()

    def _get_current_day(self) -> datetime:
        """Get the current day reference (date at reset_hour)"""
        now = datetime.now()
        # If before reset hour, we're still in "yesterday"
        if now.hour < self.reset_hour:
            reference = now - timedelta(days=1)
        else:
            reference = now
        return reference.replace(hour=0, minute=0, second=0, microsecond=0)

    def check_and_reset(self):
        """Check if we need to reset (past 3 AM on a new day)"""
        current_day = self._get_current_day()
        if current_day > self.current_day:
            print(f"[mailcam] Daily reset triggered (past {self.reset_hour}:00 AM)", flush=True)
            self.detections = {carrier: None for carrier in self.carriers}
            self.current_day = current_day
            return True
        return False

    def mark_detected(self, carrier: str, timestamp: float = None):
        """Mark a carrier as detected (only first detection of the day is recorded)"""
        if carrier not in self.carriers:
            return False

        if self.detections[carrier] is None:
            self.detections[carrier] = timestamp or time.time()
            print(f"[mailcam] First detection of {carrier} today at {datetime.fromtimestamp(self.detections[carrier]).strftime('%I:%M %p')}", flush=True)
            return True  # New detection
        return False  # Already detected today

    def is_detected(self, carrier: str) -> bool:
        """Check if carrier was detected today"""
        return self.detections.get(carrier) is not None

    def get_summary(self) -> Dict:
        """Get summary of today's detections"""
        summary = {
            "date": self.current_day.strftime("%Y-%m-%d"),
            "carriers": {}
        }
        for carrier in self.carriers:
            if self.detections[carrier]:
                summary["carriers"][carrier] = {
                    "detected": True,
                    "timestamp": self.detections[carrier],
                    "time": datetime.fromtimestamp(self.detections[carrier]).strftime("%I:%M %p")
                }
            else:
                summary["carriers"][carrier] = {
                    "detected": False
                }
        return summary

# Initialize daily tracker
CARRIER_TRACKER = DailyCarrierTracker(sorted(ALLOW_LABELS), reset_hour=3)
print(f"[mailcam] Daily tracker initialized (resets at 3:00 AM)", flush=True)

# ===== ONNX Runtime Model Loading =====
def load_onnx_model(model_path: str):
    """Load ONNX model with CPU provider"""
    if not Path(model_path).exists():
        print(f"[mailcam] ERROR: Model not found at {model_path}", flush=True)
        sys.exit(1)

    print(f"[mailcam] Loading ONNX model via onnxruntime {ort.__version__}...", flush=True)

    # Configure session options for single-threaded execution
    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = 1
    sess_options.inter_op_num_threads = 1
    sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    sess = ort.InferenceSession(model_path, sess_options, providers=["CPUExecutionProvider"])

    # Get input/output metadata
    inp = sess.get_inputs()[0]
    out = sess.get_outputs()[0]

    print(f"[mailcam] Input: {inp.name} {inp.shape}", flush=True)
    print(f"[mailcam] Output: {out.name} {out.shape}", flush=True)
    print(f"[mailcam] Model loaded successfully", flush=True)

    return sess, inp.name

# Load model once at startup
SESSION, INPUT_NAME = load_onnx_model(MODEL_PATH)

# ===== Image Processing =====
def letterbox(im: Image.Image, new_shape=(640, 640), color=(114, 114, 114)):
    """Resize image with aspect ratio preservation (letterboxing)"""
    iw, ih = im.size
    w, h = new_shape
    scale = min(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)

    # Resize
    resized = im.resize((nw, nh), Image.BILINEAR)

    # Create canvas and paste
    canvas = Image.new("RGB", new_shape, color)
    pad_x, pad_y = (w - nw) // 2, (h - nh) // 2
    canvas.paste(resized, (pad_x, pad_y))

    return canvas, scale, (pad_x, pad_y), (iw, ih)

def preprocess_image(im: Image.Image, imgsz: int = 640) -> np.ndarray:
    """Preprocess image for YOLO ONNX model"""
    # Letterbox
    im_resized, _, _, _ = letterbox(im, (imgsz, imgsz))

    # Convert to numpy and normalize
    arr = np.asarray(im_resized).astype(np.float32) / 255.0

    # HWC -> CHW
    arr = arr.transpose(2, 0, 1)

    # Add batch dimension: CHW -> NCHW
    arr = arr[None, ...]

    return arr

# ===== YOLO Output Decoding =====
def sigmoid(x):
    """Sigmoid activation"""
    return 1.0 / (1.0 + np.exp(-x))

def ensure_probs(obj, cls):
    """Convert logits to probabilities if needed"""
    # If values are outside [0,1], apply sigmoid
    if (np.max(obj) > 1.5) or (np.min(obj) < -0.5) or (np.max(cls) > 1.5) or (np.min(cls) < -0.5):
        return sigmoid(obj), sigmoid(cls)
    return obj, cls

def nms(xyxy: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> List[int]:
    """Non-maximum suppression"""
    idx = np.argsort(-scores)
    keep = []

    while idx.size:
        i = idx[0]
        keep.append(i)

        if idx.size == 1:
            break

        rest = idx[1:]
        xx1 = np.maximum(xyxy[i, 0], xyxy[rest, 0])
        yy1 = np.maximum(xyxy[i, 1], xyxy[rest, 1])
        xx2 = np.minimum(xyxy[i, 2], xyxy[rest, 2])
        yy2 = np.minimum(xyxy[i, 3], xyxy[rest, 3])

        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        a_i = (xyxy[i, 2] - xyxy[i, 0]) * (xyxy[i, 3] - xyxy[i, 1])
        a_r = (xyxy[rest, 2] - xyxy[rest, 0]) * (xyxy[rest, 3] - xyxy[rest, 1])

        iou = inter / (a_i + a_r - inter + 1e-6)
        idx = rest[iou < iou_threshold]

    return keep

def decode_yolo_output(output: np.ndarray, conf_threshold: float, img_width: int, img_height: int,
                       imgsz: int = 640) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Decode YOLOv8 ONNX output to boxes, class IDs, and scores
    Returns: (xyxy_boxes, class_ids, confidences) in original image coordinates
    """
    o = output[0]

    # Handle batch dimension
    if o.ndim == 3:
        o = o[0]  # [84, 8400] or [8400, 84]

    # Ensure shape is [N, 84] where N is number of anchors
    if o.shape[0] < o.shape[1]:
        o = o.T  # Transpose to [8400, 84]

    if o.shape[1] < 6:
        # Invalid output shape
        return np.zeros((0, 4)), np.zeros(0, dtype=int), np.zeros(0)

    # Parse output: [x, y, w, h, objectness, class_probs...]
    xywh = o[:, :4]
    obj = o[:, 4]
    cls_probs = o[:, 5:]

    # Ensure probabilities
    obj, cls_probs = ensure_probs(obj, cls_probs)

    # Get best class and confidence
    cls_ids = np.argmax(cls_probs, axis=1)
    cls_max = cls_probs[np.arange(cls_probs.shape[0]), cls_ids]
    conf = obj * cls_max

    # Filter by confidence
    mask = conf >= conf_threshold
    if not np.any(mask):
        return np.zeros((0, 4)), np.zeros(0, dtype=int), np.zeros(0)

    xywh = xywh[mask]
    cls_ids = cls_ids[mask]
    conf = conf[mask]

    # Convert xywh to xyxy (in 640x640 space)
    x_center, y_center, w, h = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
    x1 = x_center - w / 2
    y1 = y_center - h / 2
    x2 = x_center + w / 2
    y2 = y_center + h / 2
    xyxy = np.stack([x1, y1, x2, y2], axis=1)

    # Scale back to original image size
    # Assuming letterbox was applied with same padding on both sides
    scale = min(imgsz / img_width, imgsz / img_height)
    pad_x = (imgsz - img_width * scale) / 2
    pad_y = (imgsz - img_height * scale) / 2

    xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - pad_x) / scale
    xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - pad_y) / scale

    # Clip to image bounds
    xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, img_width)
    xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, img_height)

    return xyxy, cls_ids, conf

# ===== Image Fetching =====
def fetch_image_http(url: str, timeout: float = 5.0) -> Optional[Image.Image]:
    """Fetch image from HTTP URL"""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        from io import BytesIO
        img = Image.open(BytesIO(response.content))

        # Convert to RGB if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        return img

    except requests.exceptions.RequestException as e:
        print(f"[mailcam] HTTP fetch error: {e}", flush=True)
        return None
    except Exception as e:
        print(f"[mailcam] Image load error: {e}", flush=True)
        return None

def fetch_image_file(path: str) -> Optional[Image.Image]:
    """Load image from file"""
    try:
        img = Image.open(path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img
    except Exception as e:
        print(f"[mailcam] File load error: {e}", flush=True)
        return None

def fetch_image() -> Optional[Image.Image]:
    """Fetch image based on source configuration"""
    if SOURCE_KIND == "image":
        if SOURCE_URL.startswith("http://") or SOURCE_URL.startswith("https://"):
            return fetch_image_http(SOURCE_URL, TIMEOUT_SEC)
        elif SOURCE_URL.startswith("file://"):
            return fetch_image_file(SOURCE_URL[7:])
        else:
            return fetch_image_file(SOURCE_URL)
    else:
        print(f"[mailcam] ERROR: Unsupported source kind: {SOURCE_KIND}", flush=True)
        return None

# ===== Label Mapping =====
def load_labels(labels_path: str) -> Dict[int, str]:
    """Load label names from file"""
    if not labels_path or not Path(labels_path).exists():
        print(f"[mailcam] WARNING: Labels file not found, using numeric IDs", flush=True)
        return {}

    try:
        with open(labels_path) as f:
            lines = [line.strip() for line in f if line.strip()]
            return {i: name for i, name in enumerate(lines)}
    except Exception as e:
        print(f"[mailcam] WARNING: Failed to load labels: {e}", flush=True)
        return {}

LABELS = load_labels(MODEL_CFG.get("labels", ""))

def get_label_name(class_id: int) -> str:
    """Get label name for class ID"""
    return LABELS.get(class_id, str(class_id))

# ===== Detection Pipeline =====
def run_detection(img: Image.Image) -> List[Dict]:
    """Run detection on image and return filtered hits"""
    img_width, img_height = img.size
    img_area = img_width * img_height

    # Preprocess
    input_arr = preprocess_image(img, IMGSZ)

    # Run inference
    output = SESSION.run(None, {INPUT_NAME: input_arr})

    # Decode
    xyxy, cls_ids, confs = decode_yolo_output(output, CONF_MIN, img_width, img_height, IMGSZ)

    # Apply NMS
    if len(xyxy) > 0:
        keep_idx = nms(xyxy, confs, iou_threshold=0.45)
        xyxy = xyxy[keep_idx]
        cls_ids = cls_ids[keep_idx]
        confs = confs[keep_idx]

    # Filter by allowed labels and area
    hits = []
    for i in range(len(xyxy)):
        label = get_label_name(cls_ids[i])
        conf = float(confs[i])
        x1, y1, x2, y2 = xyxy[i]

        # Calculate area fraction
        box_area = (x2 - x1) * (y2 - y1)
        area_frac = box_area / max(1, img_area)

        # Filter
        if label in ALLOW_LABELS and area_frac >= AREA_MIN_FRAC:
            hits.append({
                "label": label,
                "conf": round(conf, 3),
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "area_frac": round(area_frac, 6)
            })

    return hits

# ===== MQTT Publishing =====
def setup_mqtt() -> mqtt.Client:
    """Setup MQTT client"""
    client = mqtt.Client(client_id="mailcam-detector-onnx")

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        print(f"[mailcam] Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}", flush=True)
    except Exception as e:
        print(f"[mailcam] MQTT connection error: {e}", flush=True)

    return client

def publish_homeassistant_discovery(client: mqtt.Client):
    """Publish Home Assistant MQTT discovery configuration"""
    # Device info shared across all entities
    device = {
        "identifiers": ["mailcam_detector"],
        "name": "Mailcam Detector",
        "manufacturer": "Custom",
        "model": "ONNX Detector",
        "sw_version": "2.0"
    }

    # Carrier icons mapping
    carrier_icons = {
        "fedex": "mdi:truck-fast",
        "ups": "mdi:package-variant-closed",
        "usps": "mdi:mailbox",
        "amazon": "mdi:amazon",
        "dhl": "mdi:truck"
    }

    # Create binary sensor for each carrier (resets daily at 3 AM)
    for carrier in sorted(ALLOW_LABELS):
        carrier_config = {
            "name": f"Mailcam {carrier.upper()} Today",
            "state_topic": f"mailcam/carriers/{carrier}",
            "payload_on": "yes",
            "payload_off": "no",
            "unique_id": f"mailcam_carrier_{carrier}",
            "device_class": "occupancy",
            "icon": carrier_icons.get(carrier.lower(), "mdi:truck-delivery"),
            "device": device
        }
        client.publish(
            f"homeassistant/binary_sensor/mailcam/{carrier}/config",
            json.dumps(carrier_config),
            qos=1,
            retain=True
        )

    # Sensor: Daily Summary (with timestamps)
    summary_config = {
        "name": "Mailcam Daily Summary",
        "state_topic": "mailcam/daily_summary",
        "value_template": "{{ value_json.date | default('Unknown') }}",
        "json_attributes_topic": "mailcam/daily_summary",
        "unique_id": "mailcam_daily_summary",
        "icon": "mdi:clipboard-text-clock",
        "device": device
    }
    client.publish(
        "homeassistant/sensor/mailcam/daily_summary/config",
        json.dumps(summary_config),
        qos=1,
        retain=True
    )

    # Sensor: Current Status (for backward compatibility)
    status_config = {
        "name": "Mailcam Current Status",
        "state_topic": STATE_TOPIC,
        "unique_id": "mailcam_current_status",
        "icon": "mdi:eye",
        "device": device
    }
    client.publish(
        "homeassistant/sensor/mailcam/current_status/config",
        json.dumps(status_config),
        qos=1,
        retain=True
    )

    # Sensor: Detection Details (raw)
    details_config = {
        "name": "Mailcam Detection Details",
        "state_topic": DETAIL_TOPIC,
        "value_template": "{{ value_json.hit_count | default(0) }}",
        "json_attributes_topic": DETAIL_TOPIC,
        "unique_id": "mailcam_detection_details",
        "unit_of_measurement": "hits",
        "icon": "mdi:information",
        "device": device
    }
    client.publish(
        "homeassistant/sensor/mailcam/details/config",
        json.dumps(details_config),
        qos=1,
        retain=True
    )

    print(f"[mailcam] Published Home Assistant discovery configuration", flush=True)

def publish_carrier_states(client: mqtt.Client):
    """Publish individual carrier states (yes/no)"""
    try:
        for carrier in CARRIER_TRACKER.carriers:
            state = "yes" if CARRIER_TRACKER.is_detected(carrier) else "no"
            client.publish(f"mailcam/carriers/{carrier}", state, qos=0, retain=True)
    except Exception as e:
        print(f"[mailcam] MQTT carrier state publish error: {e}", flush=True)

def publish_daily_summary(client: mqtt.Client):
    """Publish daily summary with timestamps"""
    try:
        summary = CARRIER_TRACKER.get_summary()
        client.publish("mailcam/daily_summary", json.dumps(summary), qos=0, retain=True)
    except Exception as e:
        print(f"[mailcam] MQTT summary publish error: {e}", flush=True)

def publish_results(client: mqtt.Client, state: str, details: Dict):
    """Publish detection results to MQTT"""
    try:
        # Publish current detection state
        client.publish(STATE_TOPIC, state, qos=0, retain=True)
        client.publish(DETAIL_TOPIC, json.dumps(details), qos=0, retain=True)

        # Publish individual carrier states
        publish_carrier_states(client)

        # Publish daily summary
        publish_daily_summary(client)
    except Exception as e:
        print(f"[mailcam] MQTT publish error: {e}", flush=True)

# ===== Main Loop =====
def main():
    """Main detection loop"""
    print(f"[mailcam] Starting detection loop", flush=True)

    mqtt_client = setup_mqtt()
    mqtt_client.loop_start()  # Start MQTT network loop once

    # Publish Home Assistant discovery configuration
    publish_homeassistant_discovery(mqtt_client)

    next_time = time.monotonic()
    iteration = 0

    try:
        while True:
            iteration += 1

            # Check for daily reset (at 3 AM)
            if CARRIER_TRACKER.check_and_reset():
                # Publish updated states after reset
                publish_carrier_states(mqtt_client)
                publish_daily_summary(mqtt_client)

            # Fetch image
            img = fetch_image()

            if img is None:
                # Publish error state
                details = {
                    "error": "Failed to fetch image",
                    "timestamp": time.time(),
                    "iteration": iteration
                }
                publish_results(mqtt_client, "Unknown", details)
            else:
                # Run detection
                try:
                    hits = run_detection(img)

                    # Track carriers in daily tracker
                    current_timestamp = time.time()
                    for hit in hits:
                        carrier = hit["label"]
                        is_new = CARRIER_TRACKER.mark_detected(carrier, current_timestamp)
                        # Note: is_new will be True only for first detection of the day

                    # Determine state
                    if hits:
                        state = "Delivered"
                    else:
                        state = "Not delivered"

                    # Build details
                    details = {
                        "state": state,
                        "timestamp": current_timestamp,
                        "iteration": iteration,
                        "image_size": [img.width, img.height],
                        "conf_min": CONF_MIN,
                        "area_min_frac": AREA_MIN_FRAC,
                        "allow_labels": sorted(ALLOW_LABELS),
                        "hits": hits,
                        "hit_count": len(hits)
                    }

                    # Publish
                    publish_results(mqtt_client, state, details)

                    # Log periodically (every 10 iterations)
                    if iteration % 10 == 0:
                        carriers_detected = [c for c in CARRIER_TRACKER.carriers if CARRIER_TRACKER.is_detected(c)]
                        print(f"[mailcam] Iteration {iteration}: {state}, {len(hits)} hit(s) | Today: {carriers_detected}", flush=True)

                except Exception as e:
                    print(f"[mailcam] Detection error: {e}", flush=True)
                    import traceback
                    traceback.print_exc()

                    details = {
                        "error": str(e),
                        "timestamp": time.time(),
                        "iteration": iteration
                    }
                    publish_results(mqtt_client, "Unknown", details)

            # Drift-free sleep
            next_time += POLL_SEC
            sleep_time = max(0.0, next_time - time.monotonic())
            time.sleep(sleep_time)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[mailcam] Shutting down...", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"[mailcam] Fatal error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
