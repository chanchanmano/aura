#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRAVEL_AGENT_DIR="${AI_TRAVEL_AGENT_DIR:-${ROOT_DIR}/ai-travel-agent}"
AURA_CORE_DIR="${ROOT_DIR}/aura_core"

TRAVEL_AGENT_REPO_URL="${AI_TRAVEL_AGENT_REPO_URL:-https://github.com/Burnfireblaze/ai-travel-agent.git}"
TRAVEL_AGENT_BRANCH="${AI_TRAVEL_AGENT_BRANCH:-saurav}"
PYTHON_VERSION="${AI_TRAVEL_AGENT_PYTHON_VERSION:-3.11.8}"
PYENV_ENV_NAME="${AI_TRAVEL_AGENT_PYENV_ENV:-ai-travel-agent-3.11}"

AURA_START_DOCKER="${AURA_START_DOCKER:-1}"
AURA_RUN_SMOKE_TEST="${AURA_RUN_SMOKE_TEST:-1}"
AURA_SKIP_PIP_INSTALL="${AURA_SKIP_PIP_INSTALL:-0}"

log() {
  printf '[bootstrap] %s\n' "$*"
}

fail() {
  printf '[bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

upsert_env_var() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp

  tmp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    $0 ~ "^" key "=" {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print key "=" value
      }
    }
  ' "$file" >"$tmp"
  mv "$tmp" "$file"
}

wait_for_loki() {
  local url="http://localhost:3100/ready"
  local attempt
  for attempt in $(seq 1 45); do
    local body
    body="$(curl -fsS "$url" 2>/dev/null || true)"
    if [[ "$body" == "ready" ]]; then
      log "Loki is ready"
      return 0
    fi
    sleep 2
  done
  fail "Loki did not become ready at ${url}"
}

wait_for_grafana() {
  local url="http://localhost:3000/api/health"
  local attempt
  for attempt in $(seq 1 45); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "Grafana is ready"
      return 0
    fi
    sleep 2
  done
  fail "Grafana did not become ready at ${url}"
}

clone_or_prepare_travel_agent() {
  if [[ ! -d "${TRAVEL_AGENT_DIR}/.git" ]]; then
    if [[ -n "${AI_TRAVEL_AGENT_DIR:-}" ]]; then
      fail "AI_TRAVEL_AGENT_DIR=${TRAVEL_AGENT_DIR} does not look like a git checkout"
    fi
    log "Cloning ai-travel-agent (${TRAVEL_AGENT_BRANCH})"
    git clone --branch "$TRAVEL_AGENT_BRANCH" "$TRAVEL_AGENT_REPO_URL" "$TRAVEL_AGENT_DIR"
    return 0
  fi

  local current_branch
  current_branch="$(git -C "$TRAVEL_AGENT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
  log "Using existing ai-travel-agent checkout at ${TRAVEL_AGENT_DIR} (branch: ${current_branch})"

  if [[ "$current_branch" != "$TRAVEL_AGENT_BRANCH" ]]; then
    if [[ -n "$(git -C "$TRAVEL_AGENT_DIR" status --porcelain)" ]]; then
      log "Existing checkout is dirty; leaving branch unchanged"
    else
      log "Switching existing checkout to ${TRAVEL_AGENT_BRANCH}"
      git -C "$TRAVEL_AGENT_DIR" fetch origin "$TRAVEL_AGENT_BRANCH"
      git -C "$TRAVEL_AGENT_DIR" checkout "$TRAVEL_AGENT_BRANCH"
      git -C "$TRAVEL_AGENT_DIR" pull --ff-only origin "$TRAVEL_AGENT_BRANCH"
    fi
  fi
}

ensure_pyenv_env() {
  require_command pyenv

  if ! pyenv commands | grep -qx 'virtualenv'; then
    fail "pyenv-virtualenv is required. Install it before running this bootstrap."
  fi

  if ! pyenv prefix "$PYTHON_VERSION" >/dev/null 2>&1; then
    log "Installing Python ${PYTHON_VERSION} with pyenv"
    pyenv install -s "$PYTHON_VERSION"
  fi

  if ! pyenv prefix "$PYENV_ENV_NAME" >/dev/null 2>&1; then
    log "Creating pyenv env ${PYENV_ENV_NAME}"
    pyenv virtualenv "$PYTHON_VERSION" "$PYENV_ENV_NAME"
  else
    log "Using existing pyenv env ${PYENV_ENV_NAME}"
  fi

  printf '%s\n' "$PYENV_ENV_NAME" >"${TRAVEL_AGENT_DIR}/.python-version"
}

install_travel_agent_deps() {
  if [[ "$AURA_SKIP_PIP_INSTALL" == "1" ]]; then
    log "Skipping pip install because AURA_SKIP_PIP_INSTALL=1"
    return 0
  fi

  log "Installing ai-travel-agent dependencies into ${PYENV_ENV_NAME}"
  (
    cd "$TRAVEL_AGENT_DIR"
    PYENV_VERSION="$PYENV_ENV_NAME" pyenv exec python -m pip install --upgrade pip setuptools wheel
    PYENV_VERSION="$PYENV_ENV_NAME" pyenv exec python -m pip install -e ".[dev,embeddings]"
  )
}

ensure_travel_agent_env() {
  local env_file="${TRAVEL_AGENT_DIR}/.env"
  if [[ ! -f "$env_file" ]]; then
    log "Creating ${env_file} from .env.example"
    cp "${TRAVEL_AGENT_DIR}/.env.example" "$env_file"
  else
    log "Reusing existing ${env_file}"
  fi

  upsert_env_var "$env_file" "AURA_ENABLED" "true"
  upsert_env_var "$env_file" "AURA_REPO_PATH" "$ROOT_DIR"
  upsert_env_var "$env_file" "AURA_POLICY_PATH" "./aura_policy.yml"
  upsert_env_var "$env_file" "AURA_LOG_HOST" "localhost"
  upsert_env_var "$env_file" "AURA_LOG_PORT" "3100"
  upsert_env_var "$env_file" "AURA_SERVICE_NAME" "ai-travel-agent"
  upsert_env_var "$env_file" "AURA_TIMEOUT_S" "2.0"

  if ! grep -q '^GROQ_API_KEY=.\+' "$env_file"; then
    log "GROQ_API_KEY is still empty in ${env_file}; live LLM runs will need that filled in"
  fi
}

start_aura_stack() {
  if [[ "$AURA_START_DOCKER" != "1" ]]; then
    log "Skipping Docker startup because AURA_START_DOCKER=${AURA_START_DOCKER}"
    return 0
  fi

  require_command docker
  require_command curl

  log "Starting Aura Docker stack"
  docker compose -f "${AURA_CORE_DIR}/docker-compose.yml" up -d
  wait_for_loki
  wait_for_grafana
}

run_smoke_test() {
  if [[ "$AURA_RUN_SMOKE_TEST" != "1" ]]; then
    log "Skipping smoke test because AURA_RUN_SMOKE_TEST=${AURA_RUN_SMOKE_TEST}"
    return 0
  fi

  log "Running Aura smoke test"
  AI_TRAVEL_AGENT_DIR="$TRAVEL_AGENT_DIR" PYENV_VERSION="$PYENV_ENV_NAME" pyenv exec python "${ROOT_DIR}/aura_test.py"
}

print_next_steps() {
  cat <<EOF

[bootstrap] Setup complete
[bootstrap] Grafana: http://localhost:3000
[bootstrap] Loki: http://localhost:3100
[bootstrap] Smoke test: ${ROOT_DIR}/aura_test.py
[bootstrap] Travel agent env: ${TRAVEL_AGENT_DIR}/.env

[bootstrap] Next useful command:
cd "${TRAVEL_AGENT_DIR}" && \\
PYENV_VERSION="${PYENV_ENV_NAME}" pyenv exec python scripts/run_mixed_60_single_log.py --total-runs 10 --success-runs 5 --failure-runs 5
EOF
}

main() {
  require_command git
  clone_or_prepare_travel_agent
  ensure_pyenv_env
  install_travel_agent_deps
  ensure_travel_agent_env
  start_aura_stack
  run_smoke_test
  print_next_steps
}

main "$@"
