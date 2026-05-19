#!/usr/bin/env bash
set -e
python generate_data.py
uvicorn webhook:app --host 0.0.0.0 --port $PORT
