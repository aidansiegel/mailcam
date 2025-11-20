import cv2, json
from typing import List, Dict, Tuple
from ultralytics import YOLO

ALLOW_DEFAULT = {"amazon","dhl","fedex","ups","usps"}

def _boost_contrast_bgr(im_bgr):
    lab = cv2.cvtColor(im_bgr, cv2.COLOR_BGR2LAB)
    L,a,b = cv2.split(lab)
    L = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(L)
    return cv2.cvtColor(cv2.merge([L,a,b]), cv2.COLOR_LAB2BGR)

def _veh_label_ok(lbl: str) -> bool:
    lbl = (lbl or "").lower()
    keys = ("car","truck","bus","van","vehicle","pickup","suv","person","bicycle","motorcycle")
    return any(k in lbl for k in keys)

def _collect_proposals(frame_bgr, det_model_paths, imgsz_det, conf_det, max_det=120):
    """Try each detector in order; return proposals and which model hit."""
    H, W = frame_bgr.shape[:2]
    for det_path in det_model_paths:
        try:
            det = YOLO(det_path, task="detect", verbose=False)
        except Exception:
            continue
        r = det.predict(source=frame_bgr, conf=conf_det, iou=0.5,
                        imgsz=imgsz_det, max_det=max_det, verbose=False)[0]
        names = getattr(det, "names", {})
        props = []
        if getattr(r,"boxes",None) is not None:
            for b in r.boxes:
                try:
                    cls  = int(b.cls[0] if hasattr(b.cls,'__len__') else b.cls)
                    conf = float(b.conf[0] if hasattr(b.conf,'__len__') else b.conf)
                    if not (0.0 <= conf <= 1.0):  # bogus conf -> skip
                        continue
                    lbl  = names.get(cls, f"cls-{cls}")
                    if not _veh_label_ok(lbl):
                        continue
                    x1,y1,x2,y2 = map(int, (b.xyxy[0].tolist() if hasattr(b.xyxy,'tolist') else b.xyxy))
                    pad = int(0.15 * max(x2-x1, y2-y1))
                    X1 = max(0, x1 - pad); Y1 = max(0, y1 - pad)
                    X2 = min(W, x2 + pad); Y2 = min(H, y2 + pad)
                    if X2-X1 >= 12 and Y2-Y1 >= 12:
                        props.append((X1,Y1,X2,Y2,lbl,conf))
                except Exception:
                    pass
        if props:
            return props, det_path, names
    return [], None, {}

def two_stage_hits(
    frame_bgr,
    brand_model_path: str,
    det_model_path: str,
    allow: set = None,
    imgsz_brand: int = 640,
    imgsz_det: int = 1280,     # bump to 1280 for small distant objects
    conf_det: float = 0.18,    # slightly lower to get distant vans
    conf_brand: float = 0.08,  # permissive; second-stage is filtered by area + allow
    area_min_frac: float = 0.0003,
    max_vehicle_crops: int = 16,
    debug_draw_proposals: bool = True,
) -> Dict:
    """
    Returns: dict(mode, hits[], annot, debug)
    """
    allow = allow or ALLOW_DEFAULT
    H, W = frame_bgr.shape[:2]

    # Stage 0: light enhancement
    im = _boost_contrast_bgr(frame_bgr)

    # Stage 1: general detector (try provided model, then COCO fallback)
    det_order = [det_model_path, "yolov8n.pt"]
    proposals, used_det_model, det_names = _collect_proposals(
        im, det_order, imgsz_det=imgsz_det, conf_det=conf_det, max_det=160
    )

    ann = frame_bgr.copy()
    if debug_draw_proposals:
        for (x1,y1,x2,y2,lbl,conf) in proposals[:max_vehicle_crops]:
            cv2.rectangle(ann,(x1,y1),(x2,y2),(255,0,0),2)
            cv2.putText(ann,f"{lbl} {conf:.2f}",(x1,max(12,y1-6)),
                        cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,0,0),1,cv2.LINE_AA)

    # Fallback to center crop if nothing found
    if not proposals:
        nh, nw = int(H/1.6), int(W/1.6)
        y0 = (H - nh)//2; x0 = (W - nw)//2
        proposals = [(x0,y0,x0+nw,y0+nh,"center",1.0)]

    # Stage 2: brand ONNX (fixed 640)
    brand = YOLO(brand_model_path, task="detect", verbose=False)
    brand_names = getattr(brand, "names", {})
    hits: List[Dict] = []

    for (x1,y1,x2,y2,via,base_conf) in proposals[:max_vehicle_crops]:
        crop = im[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        r2 = brand.predict(source=crop, conf=conf_brand, iou=0.5,
                           imgsz=imgsz_brand, max_det=200, verbose=False)[0]
        if getattr(r2,"boxes",None) is None:
            continue
        for b in r2.boxes:
            try:
                cls  = int(b.cls[0] if hasattr(b.cls,'__len__') else b.cls)
                conf = float(b.conf[0] if hasattr(b.conf,'__len__') else b.conf)
                if not (0.0 <= conf <= 1.0):  # stale/invalid
                    continue
                lab  = brand_names.get(cls, f"cls-{cls}")
                if lab not in allow:
                    continue
                cx1,cy1,cx2,cy2 = map(int, (b.xyxy[0].tolist() if hasattr(b.xyxy,'tolist') else b.xyxy))
                X1,Y1,X2,Y2 = x1+cx1, y1+cy1, x1+cx2, y1+cy2
                area = max(0.0, (X2-X1)*(Y2-Y1)/(W*H))
                if area < area_min_frac:
                    continue
                hits.append({"label":lab,"conf":round(conf,3),
                             "xyxy":[int(X1),int(Y1),int(X2),int(Y2)],
                             "via":str(via)})
                cv2.rectangle(ann,(X1,Y1),(X2,Y2),(0,255,0),2)
                cv2.putText(ann,f"{lab} {conf:.2f}",(X1,max(12,Y1-6)),
                            cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,0),1,cv2.LINE_AA)
            except Exception:
                pass

    return {
        "mode": "two-stage",
        "hits": hits,
        "annot": ann,
        "debug": {
            "proposal_count": len(proposals),
            "used_det_model": used_det_model,
            "detector_labels_example": list(det_names.values())[:20]
        }
    }
