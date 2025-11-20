#!/usr/bin/env python3
import os, time, json, cv2
import paho.mqtt.client as mqtt
from yaml import safe_load

# --- YOLO/Ultralytics optional path ------------------------------------------
import os
YOLO = None
USE_YOLO = os.getenv("MAILCAM_USE_YOLO","0").lower() in ("1","true","yes")
if USE_YOLO:
    try:
        from ultralytics import YOLO  # may import torch
    except Exception as e:
        print(f"[mailcam] YOLO unavailable ({e}); falling back to ONNXRuntime-only", flush=True)
        YOLO = None
        USE_YOLO = False
# -----------------------------------------------------------------------------
# deferred import (see MAILCAM_USE_YOLO)

CFG_PATH = "/home/user/mailcam/detector/mailcam.yml"
CFG = safe_load(open(CFG_PATH))
MQ   = CFG["mqtt"]; BASE = MQ.get("base_topic","mailcam")
MC   = CFG["model"]; PIPE = CFG.get("pipeline", {})

MODEL_PATH = MC["path"]
IMGSZ      = int(MC.get("imgsz", 640))
CONF_MIN   = float(MC.get("conf_min", 0.45))
IOU        = float(MC.get("iou", 0.50))
ALLOW      = set(MC.get("allow_labels", []))
SIDECAR    = MC.get("sidecar_yaml","")

def _label_from_names(names, idx:int) -> str:
    if isinstance(names, dict):
        return names.get(idx) or names.get(str(idx)) or str(idx)
    return str(idx)

def load_model():
    return YOLO(MODEL_PATH, task='detect', verbose=False)

def publish(client, state, details):
    client.publish(f"{BASE}/details", json.dumps(details), qos=0, retain=True)
    client.publish(f"{BASE}/state", state, qos=0, retain=True)

def grab_frame():
    for p in ("/home/user/stream_probe.jpg", "/home/user/stream_probe.JPG"):
        if os.path.exists(p):
            return cv2.imread(p), p
    return None, None

def run_once():
    client = mqtt.Client(client_id=MQ.get("client_id","mailcam-detector"))
    if MQ.get("username"):
        client.username_pw_set(MQ.get("username",""), MQ.get("password",""))
    client.connect(MQ["host"], int(MQ.get("port",1883)), 60)
    client.loop_start()

    im, ipath = grab_frame()
    if im is None:
        publish(client, "Unknown", {"error":"no_frame"})
        client.loop_stop(); client.disconnect(); return

    hits=[]
    try:
        model = load_model()
        r = model.predict(source=im, conf=CONF_MIN, iou=IOU, imgsz=IMGSZ, verbose=False)[0]
        if getattr(r,"boxes",None):
            for b in r.boxes:
                cls  = int(b.cls[0] if hasattr(b.cls,'__len__') else b.cls)
                conf = float(b.conf[0] if hasattr(b.conf,'__len__') else b.conf)
                if 0.0 <= conf <= 1.0:
                    lbl = _label_from_names(getattr(model,'names',{}), cls)
                    if lbl in ALLOW and conf >= CONF_MIN:
                        hits.append({"label":lbl,"conf":round(conf,3)})
        state = "Delivered" if hits else "Not delivered"
        details = {"image": ipath, "allow": sorted(ALLOW),
                   "conf_min": CONF_MIN, "iou": IOU,
                   "evidence":[[time.time(),h["label"],h["conf"]] for h in hits]}
        publish(client, state, details)
    except Exception as e:
        publish(client, "Unknown", {"error": str(e)})
    finally:
        client.loop_stop(); client.disconnect()

if __name__ == "__main__":
    run_once()
