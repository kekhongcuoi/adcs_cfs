#!/usr/bin/env sh
cd "$(dirname "$0")"
echo "ADCS Ground Station: http://127.0.0.1:8000"
exec python3 server.py
