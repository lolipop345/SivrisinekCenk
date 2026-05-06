#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

SPOOFDPI_BIN="${SPOOFDPI_BIN:-/Users/hamuz/Desktop/spoofdpi}"
SPOOFDPI_PORT="${SPOOFDPI_PORT:-8080}"

PIDS=()
cleanup() {
    echo
    echo "[stop] cleaning up..."
    if [[ ${#PIDS[@]} -gt 0 ]]; then
        for pid in "${PIDS[@]}"; do
            kill -TERM "$pid" 2>/dev/null || true
        done
    fi
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

port_in_use() { lsof -ti ":$1" >/dev/null 2>&1; }

if port_in_use "$SPOOFDPI_PORT"; then
    echo "[start] SpoofDPI :$SPOOFDPI_PORT already running, reusing"
else
    if [[ ! -x "$SPOOFDPI_BIN" ]]; then
        echo "[start] SpoofDPI not executable at $SPOOFDPI_BIN" >&2
        echo "[start] override with: SPOOFDPI_BIN=/path/to/spoofdpi ./start.sh" >&2
        exit 1
    fi
    echo "[start] launching SpoofDPI -window-size 1 on :$SPOOFDPI_PORT (TLS Client Hello fragmentation for Discord DPI bypass)"
    "$SPOOFDPI_BIN" -window-size 1 -port "$SPOOFDPI_PORT" > /tmp/spoofdpi.log 2>&1 &
    PIDS+=($!)
    for _ in 1 2 3 4 5; do
        sleep 1
        port_in_use "$SPOOFDPI_PORT" && break
    done
    if ! port_in_use "$SPOOFDPI_PORT"; then
        echo "[start] SpoofDPI didn't bind :$SPOOFDPI_PORT, see /tmp/spoofdpi.log" >&2
        exit 1
    fi
fi

echo "[start] launching bot (preflight checks LLM + Discord reachability)"
python -u bot.py
