#!/usr/bin/env bash
#
# stop_app.sh — forcefully kill whatever is listening on the AirAlert
# demo ports.
#
# Idempotent. Safe to run when nothing's there — prints "already free"
# and exits 0. Aggressive: uses kill -9 with no grace period so orphaned
# webpack/gunicorn/mlflow subprocesses that survive a clean Ctrl+C of
# run_app.sh still get cleared. Re-running run_app.sh after this gives
# you a fresh stack with no port conflicts.
#
# Usage:
#
#   ./scripts/stop_app.sh
#
# Environment overrides (use the same names as run_app.sh):
#
#   DASHBOARD_PORT  default 3000
#   MLFLOW_PORT     default 5001
#   FASTAPI_PORT    default 8000
#
# What this does NOT touch:
#   - The Astro Airflow webserver on port 8080
#   - Any other random process unrelated to the demo
#
# We deliberately target ports, not process names, so a stray mlflow
# server running on a different port for a different project is safe.

set -u

DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"
MLFLOW_PORT="${MLFLOW_PORT:-5001}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"

PORTS=("$DASHBOARD_PORT" "$MLFLOW_PORT" "$FASTAPI_PORT")
LABELS=("dashboard" "mlflow" "fastapi")

if [ -t 1 ]; then
  GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  GREEN=""; YELLOW=""; RED=""; RESET=""
fi

# ────────────────────────────────────────────────────────────────────
#  find PIDs listening on a port — works on macOS and Linux
# ────────────────────────────────────────────────────────────────────

pids_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    # -i tcp:PORT  -t  print PIDs only.  Note: lsof prints "(LISTEN)" by
    # default so we filter for the listening side with -s TCP:LISTEN.
    lsof -ti "tcp:${port}" -s TCP:LISTEN 2>/dev/null || true
    # Also catch processes that hold the port but aren't strictly LISTEN
    # (e.g. ESTABLISHED connections from a parent that didn't release).
    lsof -ti "tcp:${port}" 2>/dev/null || true
  elif command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null || true
  elif command -v ss >/dev/null 2>&1; then
    # Modern Linux fallback. ss -lptn prints lines like:
    #   LISTEN ... ("python3",pid=12345,fd=7))
    ss -lptn "sport = :${port}" 2>/dev/null \
      | sed -n 's/.*pid=\([0-9]\+\).*/\1/p'
  else
    echo "" >&2
  fi
}

# ────────────────────────────────────────────────────────────────────
#  kill anything on each port
# ────────────────────────────────────────────────────────────────────

killed_total=0
for i in "${!PORTS[@]}"; do
  port="${PORTS[$i]}"
  label="${LABELS[$i]}"

  # Collect, dedupe, and strip whitespace.
  pids=$(pids_on_port "$port" | sort -u | xargs)

  if [ -z "${pids:-}" ]; then
    printf "  %s ✓ %s port %s already free\n" "$GREEN" "$RESET" "$port" >&2
    printf "    (%s)\n" "$label" >&2
    continue
  fi

  printf "  %s ⚠ %s port %s held by PID(s): %s\n" "$YELLOW" "$RESET" "$port" "$pids" >&2
  printf "    (%s — killing with SIGKILL)\n" "$label" >&2

  # shellcheck disable=SC2086
  kill -9 $pids 2>/dev/null || true
  killed_total=$((killed_total + 1))

  # Give the kernel a moment to release the socket.
  sleep 0.3

  # Verify the port is actually free now.
  if [ -n "$(pids_on_port "$port" | xargs)" ]; then
    printf "  %s ✗ %s port %s STILL held after kill -9. Manual intervention needed.\n" \
      "$RED" "$RESET" "$port" >&2
  else
    printf "  %s ✓ %s port %s freed\n" "$GREEN" "$RESET" "$port" >&2
  fi
done

if [ "$killed_total" -eq 0 ]; then
  echo "Nothing was running. All three ports were already free." >&2
else
  echo "Stopped $killed_total service(s)." >&2
fi
