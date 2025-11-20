import os, json, cv2
from twostage import two_stage_hits, ALLOW_DEFAULT

IMG = "/home/user/stream_probe.JPG"   # you already symlinked this
assert os.path.isfile(IMG), f"missing {IMG}"

DET_MODEL   = "/home/user/cpai-models/YOLOv8 Models/Custom Models/ipcam-general-v8.pt"
BRAND_MODEL = "/home/user/mailcam/models/delivery_task.onnx"

im = cv2.imread(IMG); assert im is not None, "cannot read image"
res = two_stage_hits(
    im,
    brand_model_path=BRAND_MODEL,
    det_model_path=DET_MODEL,
    allow=ALLOW_DEFAULT,
    imgsz_brand=640,
    imgsz_det=960,
    conf_det=0.25,
    conf_brand=0.08,        # slightly lower for distant logos
    area_min_frac=0.0004,   # allow small logo boxes
    max_vehicle_crops=12
)
out = "/home/user/mailcam/debug_twostage.jpg"
cv2.imwrite(out, res["annot"])
print(json.dumps({
    "brand_hits": res["hits"][:20],
    "annot": out
}, indent=2))
