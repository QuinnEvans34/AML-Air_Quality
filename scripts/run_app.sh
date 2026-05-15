#!/usr/bin/env bash
#
# run_app.sh — start the full AirAlert demo stack with one command.
#
# Boots three services in dependency order:
#
#   1. MLflow tracking server     (http://localhost:5001)
#   2. FastAPI serving layer      (http://localhost:8000)
#   3. Next.js dashboard          (http://localhost:3000)
#
# Plus an optional bootstrap training step that runs only when no
# Production-stage models exist yet, so the first invocation on a
# fresh checkout works end-to-end with no manual coordination.
#
# Usage:
#
#   ./scripts/run_app.sh             # normal start; reuse running services
#   ./scripts/run_app.sh --clean     # wipe mlflow.db, mlartifacts, .next, retrain
#   ./scripts/run_app.sh --help      # show this help
#
# Per-service logs land in ./logs/{mlflow,fastapi,dashboard,bootstrap}.log.
# Tail any of them in another terminal to watch one service in detail.
#
# Stop the stack with Ctrl+C — the script traps SIGINT/SIGTERM and
# kills every background process it started.
#
# What this does NOT do:
#   - Start Astro Airflow. The DAG is the rubric-compliant training
#     entry point for daily 06:00 UTC retrains. This script's
#     bootstrap step is the fast path for local demos; for the full
#     pipeline demo run `astro dev start` and trigger the DAG manually.
#   - Install Python or Node deps. Make sure ./.venv is set up
#     (pip install -r requirements.txt) and app/dashboard/node_modules
#     exists (npm install) before first run.

set -euo pipefail

# ────────────────────────────────────────────────────────────────────
#  paths + arguments
# ────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS_DIR="${REPO_ROOT}/logs"
VENV_DIR="${REPO_ROOT}/.venv"
DASHBOARD_DIR="${REPO_ROOT}/app/dashboard"

# Default URIs and ports — override via env if your setup differs.
MLFLOW_HOST="${MLFLOW_HOST:-127.0.0.1}"
MLFLOW_PORT="${MLFLOW_PORT:-5001}"
FASTAPI_HOST="${FASTAPI_HOST:-127.0.0.1}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"
MLFLOW_URL="http://${MLFLOW_HOST}:${MLFLOW_PORT}"
FASTAPI_URL="http://${FASTAPI_HOST}:${FASTAPI_PORT}"
DASHBOARD_URL="http://localhost:${DASHBOARD_PORT}"

CLEAN=0
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    --help|-h)
      sed -n 's/^# \{0,1\}//p' "${BASH_SOURCE[0]}" | sed -n '/^run_app.sh/,/^$/p'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
done

mkdir -p "$LOGS_DIR"

# ────────────────────────────────────────────────────────────────────
#  pretty-print helpers
# ────────────────────────────────────────────────────────────────────

if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GREEN=""; RED=""; RESET=""
fi

step()    { echo "${BOLD}▶${RESET} $*"; }
ok()      { echo "  ${GREEN}✓${RESET} $*"; }
warn()    { echo "  ${RED}⚠${RESET} $*"; }
die()     { echo "${RED}error:${RESET} $*" >&2; exit 1; }

# ────────────────────────────────────────────────────────────────────
#  cleanup on exit — kill anything we started
# ────────────────────────────────────────────────────────────────────

declare -a CHILD_PIDS=()

cleanup() {
  local exit_code=$?
  echo
  step "Stopping services…"
  # First pass: graceful SIGTERM to direct children so they get a chance
  # to flush logs and unbind sockets.
  for pid in "${CHILD_PIDS[@]:-}"; do
    [ -z "${pid:-}" ] && continue
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
  # Second pass: SIGKILL anything still alive.
  for pid in "${CHILD_PIDS[@]:-}"; do
    [ -z "${pid:-}" ] && continue
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  # Third pass: aggressively clear the ports in case any grandchild
  # (webpack subprocess under next-dev, gunicorn worker under mlflow,
  # etc.) was orphaned and is still holding a socket. stop_app.sh
  # targets ports, not process trees, so this catches them all.
  DASHBOARD_PORT="$DASHBOARD_PORT" \
  MLFLOW_PORT="$MLFLOW_PORT" \
  FASTAPI_PORT="$FASTAPI_PORT" \
  bash "${REPO_ROOT}/scripts/stop_app.sh" 2>/dev/null || true
  ok "All child processes terminated and ports released."
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

# ────────────────────────────────────────────────────────────────────
#  pre-flight: aggressively clear our ports
# ────────────────────────────────────────────────────────────────────
#
# Ctrl+C from a previous run sometimes leaves grandchildren behind
# (next-dev's webpack subprocess, mlflow's gunicorn workers). The trap
# handler kills our direct children but can't always reach grandchildren
# fast enough. Re-running run_app.sh then collides on the port. We
# delegate this to stop_app.sh so the logic lives in one place and can
# also be invoked manually when needed.

step "Clearing demo ports (force-killing any stale processes)…"
DASHBOARD_PORT="$DASHBOARD_PORT" \
MLFLOW_PORT="$MLFLOW_PORT" \
FASTAPI_PORT="$FASTAPI_PORT" \
bash "${REPO_ROOT}/scripts/stop_app.sh"

# ────────────────────────────────────────────────────────────────────
#  prerequisite checks
# ────────────────────────────────────────────────────────────────────

step "Checking prerequisites…"

[ -d "$VENV_DIR" ] || die ".venv not found at $VENV_DIR. Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

command -v mlflow  >/dev/null || die "mlflow not on PATH. Did you activate .venv? Did pip install succeed?"
command -v uvicorn >/dev/null || die "uvicorn not on PATH. Same as above."
command -v npm     >/dev/null || die "npm not installed. Install Node 20+ from https://nodejs.org/"
command -v node    >/dev/null || die "node not installed."
command -v curl    >/dev/null || die "curl not installed (needed for health checks)."

[ -d "$DASHBOARD_DIR" ] || die "Dashboard project not found at $DASHBOARD_DIR."

ok "Python venv, mlflow, uvicorn, npm, node, curl all present."

export MLFLOW_TRACKING_URI="${MLFLOW_URL}"

# ────────────────────────────────────────────────────────────────────
#  optional --clean step
# ────────────────────────────────────────────────────────────────────

if [ "$CLEAN" -eq 1 ]; then
  step "Cleaning state (--clean was passed)…"
  cd "$REPO_ROOT"
  rm -rf mlflow.db mlartifacts mlruns
  rm -rf "${DASHBOARD_DIR}/.next"
  # Stale features files force the bootstrap script to rebuild against
  # the current _HISTORY_DAYS value in transform.py.
  find include/data/features -name 'features_*.csv' -delete 2>/dev/null || true
  find include/models -name 'metrics_*.json' -delete 2>/dev/null || true
  find include/models -name '*.pkl' -delete 2>/dev/null || true
  ok "MLflow state + dashboard build + stale features/metrics removed."
fi

# ────────────────────────────────────────────────────────────────────
#  helper: poll a URL until it returns 2xx OR a specific 5xx is OK
# ────────────────────────────────────────────────────────────────────

wait_for_url() {
  local url="$1"
  local label="$2"
  local timeout="${3:-30}"
  local accept_503="${4:-no}"   # FastAPI in degraded mode returns 503 from /health
  local i=0
  while [ "$i" -lt "$timeout" ]; do
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$url" || echo "000")
    if [[ "$code" =~ ^2 ]]; then
      ok "$label ready ($url)"
      return 0
    fi
    if [ "$accept_503" = "yes" ] && [ "$code" = "503" ]; then
      ok "$label ready in degraded mode ($url, 503 — no Production model yet)"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

port_in_use() {
  local port="$1"
  # macOS lsof is usually available; fall back to /dev/tcp probe.
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$port" >/dev/null 2>&1
  else
    (echo >"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1
  fi
}

# ────────────────────────────────────────────────────────────────────
#  step 1: MLflow tracking server
# ────────────────────────────────────────────────────────────────────

step "Starting MLflow tracking server on port ${MLFLOW_PORT}…"

cd "$REPO_ROOT"
# --host 0.0.0.0 so the Astro container can reach it via host.docker.internal.
# --serve-artifacts so artifact uploads/downloads route through HTTP and
# cross the container/host boundary cleanly.
mlflow server \
  --backend-store-uri "sqlite:///${REPO_ROOT}/mlflow.db" \
  --artifacts-destination "${REPO_ROOT}/mlartifacts" \
  --serve-artifacts \
  --host 0.0.0.0 \
  --port "$MLFLOW_PORT" \
  >"${LOGS_DIR}/mlflow.log" 2>&1 &
CHILD_PIDS+=("$!")

if ! wait_for_url "$MLFLOW_URL" "MLflow" 30; then
  warn "MLflow didn't respond within 30s. Check ${LOGS_DIR}/mlflow.log"
  exit 1
fi

# ────────────────────────────────────────────────────────────────────
#  step 2: bootstrap training (only if no Production models)
# ────────────────────────────────────────────────────────────────────

step "Checking MLflow Model Registry for Production-stage models…"

NEEDS_BOOTSTRAP=$(python3 - <<'PY'
import os, sys
from mlflow.tracking import MlflowClient
client = MlflowClient(tracking_uri=os.environ.get("MLFLOW_TRACKING_URI"))
locations = ["red_butte", "smithfield", "ledges"]
need = False
for loc in locations:
    name = f"AirAlert_{loc}"
    try:
        versions = client.get_latest_versions(name, stages=["Production"])
        if not versions:
            need = True
            print(f"  • missing Production version: {name}", file=sys.stderr)
    except Exception:
        need = True
        print(f"  • registered model not found: {name}", file=sys.stderr)
print("yes" if need else "no")
PY
)

if [ "$NEEDS_BOOTSTRAP" = "yes" ]; then
  TODAY=$(date -u +%Y-%m-%d)
  step "Running bootstrap training for ${TODAY}…"
  cd "$REPO_ROOT"
  if python3 scripts/bootstrap_train.py "$TODAY" >"${LOGS_DIR}/bootstrap.log" 2>&1; then
    ok "Bootstrap complete. See ${LOGS_DIR}/bootstrap.log for the metrics summary."
  else
    warn "Bootstrap training failed. Check ${LOGS_DIR}/bootstrap.log"
    exit 1
  fi
else
  ok "All three AirAlert_* models already at Production. Skipping bootstrap."
fi

# ────────────────────────────────────────────────────────────────────
#  step 3: FastAPI serving layer
# ────────────────────────────────────────────────────────────────────

step "Starting FastAPI serving layer on port ${FASTAPI_PORT}…"

cd "$REPO_ROOT"
# Note: we don't pass --reload here. --reload restarts on file changes
# which is useful in dev terminals but produces extra log noise when
# the script orchestrates the lifecycle.
uvicorn include.src.serve:app \
  --host "$FASTAPI_HOST" \
  --port "$FASTAPI_PORT" \
  >"${LOGS_DIR}/fastapi.log" 2>&1 &
CHILD_PIDS+=("$!")

# /health may return 503 ("Model cache is empty") in the brief moment
# before lifespan finishes the registry load. Treat 200 OR 503 as "up."
if ! wait_for_url "${FASTAPI_URL}/health" "FastAPI" 30 yes; then
  warn "FastAPI didn't respond within 30s. Check ${LOGS_DIR}/fastapi.log"
  exit 1
fi

# ────────────────────────────────────────────────────────────────────
#  step 4: Next.js dashboard
# ────────────────────────────────────────────────────────────────────

step "Starting Next.js dashboard on port ${DASHBOARD_PORT}…"

if [ ! -d "${DASHBOARD_DIR}/node_modules" ]; then
  step "Installing dashboard npm dependencies (first run)…"
  (cd "$DASHBOARD_DIR" && npm install --silent >"${LOGS_DIR}/dashboard.log" 2>&1) || {
    warn "npm install failed. Check ${LOGS_DIR}/dashboard.log"
    exit 1
  }
  ok "npm install complete."
fi

(
  cd "$DASHBOARD_DIR"
  # Pass FASTAPI_URL through to the dashboard so its API routes know
  # where to proxy.
  export FASTAPI_URL="${FASTAPI_URL}"
  export RAW_DATA_DIR="${REPO_ROOT}/include/data/raw"
  npm run dev >>"${LOGS_DIR}/dashboard.log" 2>&1 &
  echo "$!" >"${LOGS_DIR}/.dashboard.pid"
)
CHILD_PIDS+=("$(cat "${LOGS_DIR}/.dashboard.pid")")
rm -f "${LOGS_DIR}/.dashboard.pid"

if ! wait_for_url "$DASHBOARD_URL" "Dashboard" 45; then
  warn "Dashboard didn't respond within 45s. Check ${LOGS_DIR}/dashboard.log"
  exit 1
fi

# ────────────────────────────────────────────────────────────────────
#  ready
# ────────────────────────────────────────────────────────────────────

cat <<EOF

${BOLD}✓ AirAlert stack is up.${RESET}

  ${BOLD}Dashboard:${RESET}        ${DASHBOARD_URL}
  ${BOLD}FastAPI docs:${RESET}     ${FASTAPI_URL}/docs
  ${BOLD}MLflow UI:${RESET}        ${MLFLOW_URL}

${DIM}Logs (tail in another terminal to watch a service):${RESET}
  tail -f ${LOGS_DIR}/mlflow.log
  tail -f ${LOGS_DIR}/fastapi.log
  tail -f ${LOGS_DIR}/dashboard.log
  tail -f ${LOGS_DIR}/bootstrap.log   ${DIM}# only present if bootstrap ran${RESET}

${DIM}Ctrl+C to stop everything.${RESET}

EOF

# Park here and wait for any child to exit (or Ctrl+C).
wait
