#!/usr/bin/env bash
# =============================================================================
# setup.sh - anywhere2opus full environment setup
# Compatible with: Ubuntu, Debian, Oracle Linux, RHEL, Rocky Linux, AlmaLinux
# Usage:
#   ./setup.sh            # full setup (docker db + app)
#   ./setup.sh --app-only # skip Docker, just install Python deps + run app
# =============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-$USER}"
DB_CONTAINER="anywhere2opus_db"
DB_NAME="anywhere2opus"
DB_USER="anywhere2opus"
DB_PASS="anywhere2opus"
DB_PORT="5432"
APP_PORT="8000"
VENV_DIR="$REPO_DIR/venv"
ENV_FILE="$REPO_DIR/.env"
SERVICE_NAME="anywhere2opus.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
APP_ONLY=false

# ── Parse args ────────────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --app-only) APP_ONLY=true ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo -e "\033[1;34m[INFO]\033[0m $*"; }
success() { echo -e "\033[1;32m[OK]\033[0m $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m $*"; }
error()   { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

detect_os() {
  if command -v dnf &>/dev/null; then echo "dnf"
  elif command -v yum &>/dev/null; then echo "yum"
  elif command -v apt-get &>/dev/null; then echo "apt"
  else error "Package manager not found (dnf/yum/apt)"; fi
}

has_systemd() {
  command -v systemctl &>/dev/null && [[ -d /run/systemd/system ]]
}

# ── 1. System dependencies ────────────────────────────────────────────────────
install_system_deps() {
  info "Installing system dependencies..."
  local PM
  PM=$(detect_os)

  if [[ "$PM" == "apt" ]]; then
    apt-get update -qq
    apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      build-essential libpq-dev curl git ca-certificates gnupg
  else
    # RHEL/Oracle/Rocky/Alma
    $PM install -y python3 python3-pip gcc libpq-devel curl git ca-certificates
    # python3-venv may be a separate package
    python3 -m venv --help &>/dev/null || $PM install -y python3-virtualenv || true
  fi
  success "System dependencies installed"
}

# ── 2. Docker ─────────────────────────────────────────────────────────────────
install_docker() {
  if command -v docker &>/dev/null; then
    success "Docker already installed ($(docker --version))"
    return
  fi

  info "Installing Docker..."
  local PM
  PM=$(detect_os)

  if [[ "$PM" == "apt" ]]; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  else
    # RHEL/Oracle/Rocky/Alma — use Docker CE repo
    . /etc/os-release
    local REPO_URL="https://download.docker.com/linux/centos/docker-ce.repo"
    curl -fsSL "$REPO_URL" -o /etc/yum.repos.d/docker-ce.repo
    $PM install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  fi

  systemctl enable --now docker
  # Add current user to docker group
  if [[ -n "$APP_USER" && "$APP_USER" != "root" ]]; then
    usermod -aG docker "$APP_USER" || true
  fi
  success "Docker installed and started"
}

start_docker() {
  if ! systemctl is-active --quiet docker 2>/dev/null; then
    info "Starting Docker service..."
    systemctl start docker || service docker start || true
  fi
}

# ── 3. PostgreSQL container ────────────────────────────────────────────────────
setup_database() {
  info "Checking PostgreSQL container ($DB_CONTAINER)..."
  start_docker

  if docker ps -a --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
    local state
    state=$(docker inspect -f '{{.State.Status}}' "$DB_CONTAINER" 2>/dev/null || echo "unknown")
    if [[ "$state" == "running" ]]; then
      success "Container '$DB_CONTAINER' already running"
      return
    fi
    info "Container '$DB_CONTAINER' exists but is '$state' — starting..."
    docker start "$DB_CONTAINER"
  else
    info "Creating container '$DB_CONTAINER' (postgres:16-alpine)..."
    docker run -d \
      --name "$DB_CONTAINER" \
      --restart unless-stopped \
      -e POSTGRES_DB="$DB_NAME" \
      -e POSTGRES_USER="$DB_USER" \
      -e POSTGRES_PASSWORD="$DB_PASS" \
      -p "${DB_PORT}:5432" \
      -v anywhere2opus_pgdata:/var/lib/postgresql/data \
      postgres:16-alpine
    success "Container '$DB_CONTAINER' created"
  fi

  info "Waiting for PostgreSQL to be ready..."
  local attempts=0
  until docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" &>/dev/null; do
    attempts=$((attempts + 1))
    if [[ $attempts -ge 30 ]]; then
      error "PostgreSQL did not become ready after 30 attempts"
    fi
    sleep 2
  done
  success "PostgreSQL is ready"
}

# ── 4. Python virtual environment ─────────────────────────────────────────────
setup_python() {
  info "Setting up Python virtual environment..."
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  pip install --upgrade pip -q
  pip install -r "$REPO_DIR/requirements.txt" -q
  success "Python dependencies installed"
}

# ── 5. .env file ──────────────────────────────────────────────────────────────
setup_env() {
  if [[ -f "$ENV_FILE" ]]; then
    success ".env already exists — skipping"
    return
  fi

  info "Creating .env from .env.example..."
  cp "$REPO_DIR/.env.example" "$ENV_FILE"

  # Override database URL to use the Docker container
  sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg2://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}|" "$ENV_FILE"
  sed -i "s|DB_HOST=.*|DB_HOST=localhost|" "$ENV_FILE"
  sed -i "s|SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')|" "$ENV_FILE"

  success ".env created"
}

# ── 6. Alembic migrations ─────────────────────────────────────────────────────
run_migrations() {
  info "Running database migrations..."
  source "$VENV_DIR/bin/activate"
  cd "$REPO_DIR"
  alembic upgrade head
  success "Migrations applied"
}

# ── 7. Service management ─────────────────────────────────────────────────────
install_service() {
  if [[ "$EUID" -ne 0 ]]; then
    warn "Skipping systemd service installation: root privileges required"
    return 1
  fi

  if ! has_systemd; then
    warn "Skipping systemd service installation: systemd not available"
    return 1
  fi

  info "Installing systemd service ($SERVICE_NAME)..."
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=anywhere2opus API
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStartPre=-/usr/bin/docker start $DB_CONTAINER
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port $APP_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME" >/dev/null
  success "Systemd service installed"
}

start_app_with_systemd() {
  info "Starting anywhere2opus with systemd on port $APP_PORT..."
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  systemctl restart "$SERVICE_NAME"
  sleep 4

  if systemctl is-active --quiet "$SERVICE_NAME"; then
    success "anywhere2opus running via systemd on http://0.0.0.0:${APP_PORT}/connectors"
  else
    error "Application failed to start under systemd. Check: journalctl -u $SERVICE_NAME -n 100"
  fi
}

start_app_with_nohup() {
  info "Starting anywhere2opus on port $APP_PORT..."
  source "$VENV_DIR/bin/activate"
  cd "$REPO_DIR"

  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  sleep 1

  nohup uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" \
    > /tmp/anywhere2opus.log 2>&1 &
  local PID=$!
  disown "$PID"

  sleep 4
  if kill -0 "$PID" 2>/dev/null; then
    success "anywhere2opus running (PID $PID) on http://0.0.0.0:${APP_PORT}/connectors"
  else
    error "Application failed to start. Check /tmp/anywhere2opus.log"
  fi
}

start_app() {
  if install_service; then
    start_app_with_systemd
  else
    start_app_with_nohup
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo ""
  echo "=================================================="
  echo "  anywhere2opus setup"
  echo "=================================================="
  echo ""

  if [[ "$EUID" -ne 0 ]] && [[ "$APP_ONLY" == false ]]; then
    warn "Not running as root. Docker operations may fail."
    warn "Run: sudo ./setup.sh   (or use --app-only to skip Docker)"
    echo ""
  fi

  install_system_deps

  if [[ "$APP_ONLY" == false ]]; then
    install_docker
    setup_database
  else
    warn "--app-only mode: skipping Docker and database setup"
  fi

  setup_python
  setup_env
  run_migrations
  start_app

  echo ""
  echo "=================================================="
  echo "  Setup complete!"
  echo "  Web UI:  http://localhost:${APP_PORT}/connectors"
  echo "  API:     http://localhost:${APP_PORT}/connectors/api/v1"
  echo "  Docs:    http://localhost:${APP_PORT}/docs"
  if has_systemd && [[ "$EUID" -eq 0 ]]; then
    echo "  Service:  systemctl status ${SERVICE_NAME}"
    echo "  Logs:     journalctl -u ${SERVICE_NAME} -f"
    echo "  Restart:  systemctl restart ${SERVICE_NAME}"
  else
    echo "  Logs:    tail -f /tmp/anywhere2opus.log"
    echo "  Restart: pkill -f uvicorn; ./setup.sh --app-only"
  fi
  echo "=================================================="
  echo ""
}

main "$@"
