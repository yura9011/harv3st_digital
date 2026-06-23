#!/usr/bin/env bash
# Wrapper: sets Chromium library path before launching Harv3st
export LD_LIBRARY_PATH="/home/yura/formadigital-pocket/.chromium-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PLAYWRIGHT_BROWSERS_PATH="/home/yura/.cache/ms-playwright"
exec /home/yura/formadigital_app/services/harv3st/.venv/bin/python \
  /home/yura/formadigital_app/services/harv3st/manager.py server
