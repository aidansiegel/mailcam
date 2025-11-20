#!/usr/bin/env bash
set -euo pipefail
export MAILCAM_DISABLE_DETECTOR=1
# Extra safety: prefer low CPU priority on this process
exec nice -n 10 /home/user/restreamenv/bin/python /home/user/mailcam/restream.py
