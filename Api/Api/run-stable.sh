#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:99}"
export NODE_OPTIONS="${NODE_OPTIONS:---unhandled-rejections=strict}"

# Start Xvfb only when it is not already running.
if ! pgrep -f "Xvfb ${DISPLAY}" >/dev/null 2>&1; then
  rm -f /tmp/.X99-lock 2>/dev/null || true
  Xvfb "${DISPLAY}" -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
  XVFB_PID=$!
  trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT INT TERM
  sleep 1
fi

# Restart only if the Node process itself exits. The application code is left unchanged.
while :; do
  echo "[stable] starting API..."
  npm start
  rc=$?
  echo "[stable] API exited with code ${rc}; restarting in 3s..."
  sleep 3
done
