#!/usr/bin/env python3
import os, time, runpy
from pathlib import Path

POLL = float(os.getenv("MAILCAM_POLL", "10"))  # seconds between passes
SCRIPT = Path(__file__).with_name("mailcam_detector.py")

while True:
    try:
        # run the detector as if invoked directly
        runpy.run_path(str(SCRIPT), run_name="__main__")
    except SystemExit:
        # treat normal exits as "end of pass"
        pass
    except Exception as e:
        print(f"[mailcam_loop] error: {e}", flush=True)
    time.sleep(POLL)
