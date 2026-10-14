#!/usr/bin/env bash
# AgentCraft Engineering Lab — one-command deployment script.
#
# Usage:
#   ./deploy.sh up        # build + start all services (core + neo4j + observability)
#   ./deploy.sh down      # stop all services (volumes preserved)
#   ./deploy.sh status    # show service health
#   ./deploy.sh logs      # tail logs
#   ./deploy.sh backup    # backup PostgreSQL + Neo4j to ./backups/
#   ./deploy.sh update    # pull + rebuild + restart (zero-downtime not guaranteed)
#   ./deploy.sh migrate   # run alembic migrations only
#   ./deploy.sh test-runner  # run integration smoke tests
#
# Prerequisites:
#   - Docker + Docker Compose v2 installed
#   - .env file present (copy from .env.production.example)
#   - External network created: docker network create agentcraft-proxy
#     (only needed if NPM is on a separate compose stack)
#
# Mission J-FIX-02: profiles are passed as separate --profile flags
# (the correct Docker Compose syntax). The PROFILES env var is a
# space-separated list, NOT a single comma-joined argument.

set -euo pipefail

cd "$(dirname "$0")"

# ---- config ----
# Space-separated list of compose profiles to start.
# Extracted from docker-compose.yml: core, neo4j, observability, test.
# The 'test' profile is excluded from default 'up' to avoid starting
# the test-runner container in production.
PROFILES="${PROFILES:-core neo4j observability}"
ENV_FILE="${ENV_FILE:-.env}"

# Build the --profile flags array. Each profile gets its own --profile flag.
# Mission J-FIX-02: 'docker compose --profile "core neo4j"' is INVALID;
# the correct form is 'docker compose --profile core --profile neo4j'.
PROFILE_FLAGS=()
for p in $PROFILES; do
  PROFILE_FLAGS+=("--profile" "$p")
done

COMPOSE="docker compose"

# ---- commands ----

case "${1:-help}" in
  help|--help|-h)
    echo "AgentCraft Engineering Lab — deploy script"
    echo ""
    echo "Usage: $0 {up|down|status|logs|backup|update|migrate|test-runner}"
    echo ""
    echo "Commands:"
    echo "  up           Build + start all services (core + neo4j observability)"
    echo "  down         Stop all services (volumes preserved)"
    echo "  status       Show service health"
    echo "  logs         Tail logs (Ctrl-C to exit)"
    echo "  backup       Backup PostgreSQL + Neo4j to ./backups/"
    echo "  update       Pull code + rebuild + restart + migrate"
    echo "  migrate      Run alembic migrations only"
    echo "  test-runner  Run integration smoke tests"
    echo ""
    echo "Environment:"
    echo "  PROFILES     Compose profiles to start (default: 'core neo4j observability')"
    echo "  ENV_FILE     .env file to use (default: .env)"
    echo "  BACKUP_DIR   Backup output dir (default: ./backups)"
    exit 0
    ;;
  up|down|status|logs|backup|update|migrate|test-runner)
    # Valid command — proceed to .env check below.
    ;;
  *)
    echo "Unknown command: ${1:-<empty>}"
    echo "Run '$0 help' for usage."
    exit 1
    ;;
esac

# All commands below require .env
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found."
  echo "Copy .env.production.example to .env and fill in real values:"
  echo "  cp .env.production.example .env"
  echo "  # then edit .env with strong passwords"
  exit 1
fi

case "${1:-help}" in
  up)
    echo ">>> Building and starting AgentCraft (profiles: $PROFILES)..."
    $COMPOSE --env-file "$ENV_FILE" "${PROFILE_FLAGS[@]}" up -d --build
    echo ""
    echo ">>> Waiting for services to become healthy (30s)..."
    sleep 30
    $COMPOSE --env-file "$ENV_FILE" "${PROFILE_FLAGS[@]}" ps
    echo ""
    echo ">>> Done. Check status with: ./deploy.sh status"
    ;;

  down)
    echo ">>> Stopping AgentCraft (volumes preserved)..."
    $COMPOSE --env-file "$ENV_FILE" "${PROFILE_FLAGS[@]}" down
    ;;

  status)
    $COMPOSE --env-file "$ENV_FILE" "${PROFILE_FLAGS[@]}" ps
    ;;

  logs)
    $COMPOSE --env-file "$ENV_FILE" "${PROFILE_FLAGS[@]}" logs --tail=100 -f
    ;;

  backup)
    BACKUP_DIR="${BACKUP_DIR:-./backups}"
    TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
    mkdir -p "$BACKUP_DIR"

    # ---- PostgreSQL backup ----
    # Uses POSTGRES_USER and POSTGRES_DB from .env (not hardcoded).
    # Mission J-FIX-03: detect failure and exit non-zero.
    echo ">>> Backing up PostgreSQL..."
    PG_USER=$(grep -E "^POSTGRES_USER=" "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
    PG_DB=$(grep -E "^POSTGRES_DB=" "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
    PG_USER="${PG_USER:-agentcraft}"
    PG_DB="${PG_DB:-agentcraft}"
    PG_DUMP_FILE="$BACKUP_DIR/postgres-$TIMESTAMP.sql"
    if $COMPOSE --env-file "$ENV_FILE" exec -T postgres pg_dump -U "$PG_USER" "$PG_DB" > "$PG_DUMP_FILE"; then
      # Verify the dump is non-empty and starts with the expected header.
      if [ -s "$PG_DUMP_FILE" ] && head -1 "$PG_DUMP_FILE" | grep -q "PostgreSQL database dump"; then
        echo "  ✓ PostgreSQL backup: $PG_DUMP_FILE ($(wc -c < "$PG_DUMP_FILE") bytes)"
      else
        echo "  ✗ PostgreSQL backup FAILED: dump file is empty or invalid"
        rm -f "$PG_DUMP_FILE"
        exit 1
      fi
    else
      echo "  ✗ PostgreSQL backup FAILED: pg_dump exited with code $?"
      rm -f "$PG_DUMP_FILE"
      exit 1
    fi

    # ---- Neo4j backup ----
    # Mission J-FIX-03: Neo4j 5.x uses 'neo4j-admin database dump'.
    # The dump must be written to a path INSIDE the container's /data
    # volume, then copied out. The service must be running (online dump
    # is supported for full+tx backups in Neo4j 5.x Community Edition).
    echo ">>> Backing up Neo4j..."
    NEO4J_DUMP_DIR="/data/dumps"
    NEO4J_DUMP_NAME="neo4j-$TIMESTAMP.dump"
    NEO4J_CONTAINER=$($COMPOSE --env-file "$ENV_FILE" ps -q neo4j 2>/dev/null || echo "")
    if [ -n "$NEO4J_CONTAINER" ]; then
      # Create the dump inside the container.
      if $COMPOSE --env-file "$ENV_FILE" exec -T neo4j neo4j-admin database dump neo4j \
          --to-path="$NEO4J_DUMP_DIR" --overwrite-destination=true 2>/dev/null; then
        # Copy the dump out to the host.
        mkdir -p "$BACKUP_DIR/neo4j-$TIMESTAMP"
        if docker cp "$NEO4J_CONTAINER:$NEO4J_DUMP_DIR/neo4j.dump" \
            "$BACKUP_DIR/neo4j-$TIMESTAMP/$NEO4J_DUMP_NAME" 2>/dev/null; then
          echo "  ✓ Neo4j backup: $BACKUP_DIR/neo4j-$TIMESTAMP/$NEO4J_DUMP_NAME"
        else
          echo "  ⚠️  Neo4j dump created in container but copy-out failed"
        fi
      else
        echo "  ⚠️  Neo4j dump failed (neo4j-admin database dump not available or service not ready)"
      fi
    else
      echo "  ⚠️  Neo4j service not running — skipping Neo4j backup"
    fi

    echo ">>> Backup complete: $BACKUP_DIR/"
    ls -la "$BACKUP_DIR/" | tail -10
    ;;

  update)
    echo ">>> Pulling latest code..."
    git pull --ff-only
    echo ">>> Rebuilding images..."
    $COMPOSE --env-file "$ENV_FILE" "${PROFILE_FLAGS[@]}" build
    echo ">>> Restarting services..."
    $COMPOSE --env-file "$ENV_FILE" "${PROFILE_FLAGS[@]}" up -d
    echo ">>> Running migrations..."
    $COMPOSE --env-file "$ENV_FILE" exec -T api alembic upgrade head
    echo ">>> Update complete."
    ;;

  migrate)
    echo ">>> Running alembic migrations..."
    $COMPOSE --env-file "$ENV_FILE" exec -T api alembic upgrade head
    ;;

  test-runner)
    echo ">>> Running integration smoke tests..."
    $COMPOSE --env-file "$ENV_FILE" --profile test run --rm test-runner
    ;;
esac
