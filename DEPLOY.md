# AgentCraft Engineering Lab — Deployment Guide

**Mission J-FIX — Docker/NPM Deployment Closure**

---

## 1. Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Docker Engine 24+
- Docker Compose v2
- Nginx Proxy Manager (already running on the server)
- 4 GB RAM minimum (8 GB recommended)
- 20 GB disk

## 2. Quick start

```bash
# 1. Clone
git clone https://github.com/mayakilzy/AgentCraft-Engineering-Lab.git
cd AgentCraft-Engineering-Lab

# 2. Create the external Docker network for NPM (one-time)
docker network create agentcraft-proxy

# 3. Copy production env and fill in secrets
cp .env.production.example .env
nano .env  # replace every CHANGE_ME_* with strong passwords

# 4. Start all services
./deploy.sh up

# 5. Check status
./deploy.sh status
```

## 3. NPM setup

### 3.1 Connect NPM to the app network

Add the `agentcraft-proxy` network to NPM's compose:
```yaml
networks:
  agentcraft-proxy:
    external: true
services:
  app:
    networks:
      - default
      - agentcraft-proxy
```

### 3.2 Create Proxy Host in NPM UI

1. NPM admin UI → Hosts → Proxy Hosts → Add
2. Domain: `your-domain.example.com`
3. Scheme: `http`, Forward Hostname: `web`, Forward Port: `80`
4. Websockets Support: ✓
5. SSL tab: request Let's Encrypt cert, Force SSL, HTTP/2

### 3.3 Verify
```bash
curl -I https://your-domain.example.com
```

## 4. Compose profiles

| Profile | Services | When |
|---|---|---|
| `core` | postgres, api, web, purge-cron | Always |
| `neo4j` | neo4j (+ GDS plugin) | E04, E06 |
| `observability` | otel-collector, prometheus, tempo, grafana | E07-E10, monitoring |
| `test` | test-runner | CI only |

Default: `PROFILES="core neo4j observability"`

## 5. Environment variables

See `.env.production.example`. Critical:
- `APP_ENV=production` (fail-closed)
- `SESSION_COOKIE_SECURE=true`
- `CORS_ORIGINS=https://your-domain.example.com`
- `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` (strong)

## 6. Backup & restore

### Backup
```bash
./deploy.sh backup
# Creates backups/postgres-<timestamp>.sql + backups/neo4j-<timestamp>/
```

### Restore PostgreSQL
```bash
cat backups/postgres-<timestamp>.sql | docker compose exec -T postgres psql -U agentcraft agentcraft
```

### Restore Neo4j
```bash
docker compose stop neo4j
docker cp backups/neo4j-<timestamp>/neo4j-<timestamp>.dump \
    $(docker compose ps -q neo4j):/data/dumps/neo4j.dump
docker compose exec -T neo4j neo4j-admin database load neo4j \
    --from-path=/data/dumps --overwrite-destination=true
docker compose start neo4j
```

## 7. Troubleshooting

```bash
./deploy.sh logs          # all logs
docker compose logs api   # backend
docker compose ps         # service health
```

Common:
- `production config is insecure` — default password in .env
- NPM can't reach app — verify `agentcraft-proxy` network exists and both NPM + web are attached
- Neo4j GDS not loaded — check `docker compose logs neo4j | grep -i gds`

## 8. Health checks

| Service | Check |
|---|---|
| api | `curl /api/v1/health/live` → `{"status":"ok"}` |
| web | `wget http://localhost/` → 200 |
| postgres | `pg_isready` |
| neo4j | `wget http://localhost:7474` |
| grafana | `curl /api/health` |

## 9. What was NOT runtime-tested

This guide was prepared without Docker. The following are CONFIG READY but not RUNTIME VERIFIED:
- Docker image builds
- Compose service startup
- NPM proxy host creation
- TLS certificate issuance
- End-to-end HTTPS flow

After deploying, run `./deploy.sh test-runner` to verify.
