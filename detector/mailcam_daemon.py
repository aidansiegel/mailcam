#!/usr/bin/env python3
import os, time, json, cv2
from pathlib import Path
from yaml import safe_load
from paho.mqtt.client import Client
from ultralytics import YOLO

CFG  = safe_load(open("/home/user/mailcam/detector/mailcam.yml"))
M, MQ, SRC = CFG["model"], CFG["mqtt"], CFG["source"]
ALLOW = set(M.get("allow_labels", []))
CONF  = float(M.get("conf_min", 0.45))
IOU   = float(M.get("iou", 0.50))
IMSZ  = int(M.get("imgsz", 640))
POLL  = float(os.getenv("MAILCAM_POLL", "2.5"))  # seconds (2–3s recommended)
BASE  = "mailcam"

# Load model once
model = YOLO(M["path"], task="detect", verbose=False)

cli = Client(client_id="mailcam-daemon")
cli.username_pw_set(MQ.get("username",""), MQ.get("password",""))
cli.connect(MQ["host"], int(MQ.get("port",1883)), 60)

def grab_frame():
    if SRC.get("type") == "image":
        p = SRC.get("path", str(Path.home()/ "stream_probe.JPG"))
        return cv2.imread(p)
    url = SRC.get("url","")
    cap = cv2.VideoCapture(url)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None

def publish(state, details):
    cli.loop_start()
    cli.publish(f"{BASE}/details", json.dumps(details), qos=0, retain=True)
    cli.publish(f"{BASE}/state", state, qos=0, retain=True)
    cli.loop_stop()

next_t = time.monotonic()
while True:
    frame = grab_frame()
    hits = []
    if frame is not None:
        r = model.predict(source=frame, conf=CONF, iou=IOU, imgsz=IMSZ, verbose=False)[0]
        if getattr(r,"boxes",None) is not None:
            h, w = frame.shape[:2]
            for b in r.boxes:
                cls  = int(b.cls[0] if hasattr(b.cls,'__len__') else b.cls)
                conf = float(b.conf[0] if hasattr(b.conf,'__len__') else b.conf)
                if 0.0 <= conf <= 1.0:
                    label = model.names.get(cls, str(cls))
                    x1,y1,x2,y2 = map(float, b.xyxy[0].tolist())
                    area = ((x2-x1)*(y2-y1))/max(1,w*h)
                    if label in ALLOW and conf >= CONF and area >= 0.002:
                        hits.append({"label":label, "conf":round(conf,3)})

    state = "Delivered" if hits else "Not delivered"
    details = {"mode":"detect","allow":sorted(ALLOW),"conf_min":CONF,"imgsz":IMSZ,
               "evidence":[[time.time(), h["label"], h["conf"]] for h in hits]}
    publish(state, details)

    # driftless sleep
    next_t += POLL
    time.sleep(max(0.0, next_t - time.monotonic()))
