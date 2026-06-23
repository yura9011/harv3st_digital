#!/usr/bin/env bash
cd /home/yura/formadigital-pocket
exec /home/yura/formadigital-pocket/.venv/bin/python -m uvicorn pocket_api:app --host 0.0.0.0 --port 3123
