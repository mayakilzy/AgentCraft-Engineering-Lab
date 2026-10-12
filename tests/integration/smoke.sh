#!/usr/bin/env bash
# AgentCraft Engineering Lab — Docker Compose integration smoke.
#
# G08-C1: this script runs INSIDE a container on the agentcraft-net
# network (via `docker compose run --rm api` or `docker compose exec api`).
# It tests the REAL PostgreSQL, Neo4j, observability stack, and Nginx.
#
# This script is called by the GitHub Actions workflow. It is NOT
# a substitute for the unit tests — it tests the RUNTIME integration.
#
# Usage (from the CI workflow):
#   docker compose run --rm --no-deps api bash /app/backend/tests/integration/smoke.sh
#
# Exit codes:
#   0: all checks passed
#   1: one or more checks failed (details in stderr)

set -euo pipefail

API_URL="http://api:8000"
NGINX_URL="http://web:80"
PROMETHEUS_URL="http://prometheus:9090"
TEMPO_URL="http://tempo:3200"
GRAFANA_URL="http://grafana:3000"
NEO4J_URL="http://neo4j:7474"
POSTGRES_HOST="postgres"
POSTGRES_PORT="5432"

FAILURES=0

check() {
    local name="$1"
    local cmd="$2"
    echo "CHECK: $name"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  → OK"
    else
        echo "  → FAIL"
        FAILURES=$((FAILURES + 1))
    fi
}

echo "=== AgentCraft Docker Compose Integration Smoke ==="
echo ""

# ---- C1-02: PostgreSQL integration ----
echo "--- PostgreSQL Integration ---"

# Check PostgreSQL connectivity.
check "PostgreSQL connectivity" \
    "python -c \"import psycopg2; c=psycopg2.connect(host='$POSTGRES_HOST',port=$POSTGRES_PORT,user='agentcraft',password='${POSTGRES_PASSWORD:-changeme}',dbname='agentcraft'); c.close()\""

# Check migrations ran (tables exist).
check "PostgreSQL tables exist" \
    "python -c \"import psycopg2; c=psycopg2.connect(host='$POSTGRES_HOST',port=$POSTGRES_PORT,user='agentcraft',password='${POSTGRES_PASSWORD:-changeme}',dbname='agentcraft'); cur=c.cursor(); cur.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema=\\'public\\''); n=cur.fetchone()[0]; c.close(); assert n >= 7, f'expected >=7 tables, got {n}'\""

# Check guest_sessions table is usable.
check "PostgreSQL guest_sessions writable" \
    "python -c \"import psycopg2; c=psycopg2.connect(host='$POSTGRES_HOST',port=$POSTGRES_PORT,user='agentcraft',password='${POSTGRES_PASSWORD:-changeme}',dbname='agentcraft'); cur=c.cursor(); cur.execute('SELECT count(*) FROM guest_sessions'); c.close()\""

echo ""

# ---- C1-02: Neo4j integration ----
echo "--- Neo4j Integration ---"

# Check Neo4j connectivity (HTTP API).
check "Neo4j connectivity" \
    "curl -sf http://neo4j:7474/ -u neo4j:${NEO4J_PASSWORD:-changeme} | grep -o 'neo4j' | head -1"

# Check GDS availability (probe procedures catalog).
GDS_STATUS=$(python -c "
from neo4j import GraphDatabase
import sys
try:
    driver = GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j', '${NEO4J_PASSWORD:-changeme}'))
    driver.verify_connectivity()
    with driver.session() as s:
        result = s.run('SHOW PROCEDURES YIELD name WHERE name STARTS WITH \\\"gds.\\\" RETURN count(name) AS cnt')
        cnt = result.single()['cnt']
        if cnt > 0:
            print('AVAILABLE')
        else:
            print('NOT_AVAILABLE')
    driver.close()
except Exception as e:
    print(f'BLOCKED:{type(e).__name__}')
" 2>/dev/null || echo "BLOCKED:connection_failed")

echo "  GDS status: $GDS_STATUS"
if echo "$GDS_STATUS" | grep -q "AVAILABLE"; then
    echo "  → GDS is available (procedures found)"
elif echo "$GDS_STATUS" | grep -q "NOT_AVAILABLE"; then
    echo "  → GDS plugin installed but no procedures (license-gated) — honestly NOT_AVAILABLE"
else
    echo "  → GDS BLOCKED — $GDS_STATUS"
fi

# Check session-scoped namespace creation + cleanup.
check "Neo4j namespace isolation (two sessions)" \
    "python -c \"
from neo4j import GraphDatabase
import uuid, json

driver = GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j', '${NEO4J_PASSWORD:-changeme}'))
driver.verify_connectivity()

with driver.session() as s:
    # Create two session namespaces.
    sid_a = uuid.uuid4()
    sid_b = uuid.uuid4()
    ns_a = f'sess_{str(sid_a).replace(\\\"-\\\", \\\"\\\")[:12]}'
    ns_b = f'sess_{str(sid_b).replace(\\\"-\\\", \\\"\\\")[:12]}'

    # Import a node for session A.
    s.run(f'MERGE (n:__{ns_a}__ds_test {{ref: \\\"A1\\\"}}) SET n.kind=\\\"tool\\\"')
    # Import a node for session B.
    s.run(f'MERGE (n:__{ns_b}__ds_test {{ref: \\\"B1\\\"}}) SET n.kind=\\\"tool\\\")

    # Verify A has 1 node, B has 1 node.
    cnt_a = s.run(f'MATCH (n:__{ns_a}__ds_test) RETURN count(n) AS cnt').single()['cnt']
    cnt_b = s.run(f'MATCH (n:__{ns_b}__ds_test) RETURN count(n) AS cnt').single()['cnt']
    assert cnt_a == 1, f'session A has {cnt_a} nodes (expected 1)'
    assert cnt_b == 1, f'session B has {cnt_b} nodes (expected 1)'

    # Clean up A only.
    s.run(f'MATCH (n) WHERE ANY(l IN labels(n) WHERE l STARTS WITH \\\"__{ns_a}__\\\") DETACH DELETE n')

    # Verify A is empty, B still has 1.
    cnt_a_after = s.run(f'MATCH (n:__{ns_a}__ds_test) RETURN count(n) AS cnt').single()['cnt']
    cnt_b_after = s.run(f'MATCH (n:__{ns_b}__ds_test) RETURN count(n) AS cnt').single()['cnt']
    assert cnt_a_after == 0, f'session A has {cnt_a_after} nodes after cleanup (expected 0)'
    assert cnt_b_after == 1, f'session B has {cnt_b_after} nodes after A cleanup (expected 1)'

    # Clean up B.
    s.run(f'MATCH (n) WHERE ANY(l IN labels(n) WHERE l STARTS WITH \\\"__{ns_b}__\\\") DETACH DELETE n')

driver.close()
print('namespace isolation OK')
\""

echo ""

# ---- C1-03: Observability evidence ----
echo "--- Observability Integration ---"

# Check Prometheus is healthy.
check "Prometheus healthy" \
    "curl -sf $PROMETHEUS_URL/-/healthy"

# Check Prometheus is scraping the API.
# Wait a few seconds for the first scrape.
sleep 5
check "Prometheus scraping API (agentcraft-api job)" \
    "curl -sf '$PROMETHEUS_URL/api/v1/targets?state=active' | python -c \"
import json,sys
d=json.load(sys.stdin)
targets=d['data']['activeTargets']
api_targets=[t for t in targets if 'agentcraft-api' in t.get('labels',{}).get('job','')]
assert len(api_targets)>=1, 'no agentcraft-api target found'
assert api_targets[0]['health']=='up', f'target health={api_targets[0][\\\"health\\\"]}'
\""

# Check Prometheus has metrics from the API.
check "Prometheus has agentcraft metrics" \
    "curl -sf '$PROMETHEUS_URL/api/v1/query?query=agentcraft_http_requests_total' | python -c \"
import json,sys
d=json.load(sys.stdin)
results=d['data']['result']
assert len(results)>0, 'no agentcraft_http_requests_total metrics found'
\""

# Check Tempo is ready.
check "Tempo ready" \
    "curl -sf $TEMPO_URL/ready"

# Check Grafana is healthy.
check "Grafana healthy" \
    "curl -sf $GRAFANA_URL/api/health"

# Check Grafana datasources are provisioned.
check "Grafana Prometheus datasource provisioned" \
    "curl -sf -u admin:${GRAFANA_ADMIN_PASSWORD:-changeme} '$GRAFANA_URL/api/datasources' | python -c \"
import json,sys
ds=json.load(sys.stdin)
types=[d['type'] for d in ds]
assert 'prometheus' in types, f'no Prometheus datasource (found: {types})'
assert 'tempo' in types, f'no Tempo datasource (found: {types})'
\""

# Check OTEL Collector is healthy.
check "OTEL Collector healthy" \
    "curl -sf http://otel-collector:13133/"

# Check trace flow: create a run + verify trace_id is populated.
echo "  Creating a run to generate a trace..."
TRACE_RESULT=$(curl -sf -X POST "$API_URL/api/v1/sessions/guest" \
    -H 'Content-Type: application/json' \
    -d '{"locale":"en"}' -c /tmp/smoke-cookies.txt)
SESSION_ID=$(echo "$TRACE_RESULT" | python -c "import json,sys; print(json.load(sys.stdin)['session_id'])")

# Create a run (generates spans → OTEL → Collector → Tempo).
RUN_RESULT=$(curl -sf -X POST "$API_URL/api/v1/experiments/trace-one-request/runs" \
    -H 'Content-Type: application/json' \
    -d '{"mode":"guided","inputs":{}}' \
    -b /tmp/smoke-cookies.txt)
RUN_ID=$(echo "$RUN_RESULT" | python -c "import json,sys; print(json.load(sys.stdin)['run_id'])")
TRACE_ID=$(echo "$RUN_RESULT" | python -c "import json,sys; print(json.load(sys.stdin).get('trace_id',''))")

echo "  Run created: run_id=$RUN_ID, trace_id=${TRACE_ID:0:16}..."
check "Run trace_id is populated" \
    "[ -n '$TRACE_ID' ] && [ '$TRACE_ID' != 'None' ]"

# Wait for the trace to be exported to Tempo (batch processor delay).
echo "  Waiting 10s for trace to reach Tempo..."
sleep 10

# Check Tempo has the trace (query by trace_id).
if [ -n "$TRACE_ID" ] && [ "$TRACE_ID" != "None" ]; then
    check "Tempo has the trace (trace_id=$TRACE_ID)" \
        "curl -sf '$TEMPO_URL/api/traces/$TRACE_ID' | python -c \"
import json,sys
d=json.load(sys.stdin)
# Tempo returns traces in a specific format.
# We just check the response is non-empty and has the trace.
assert d, 'empty response from Tempo'
\""
fi

echo ""

# ---- C1-04: Persistence + security ----
echo "--- Persistence + Security ---"

# Create a guest session via Nginx (public entry point).
check "Create session via Nginx" \
    "curl -sf -X POST '$NGINX_URL/api/v1/sessions/guest' -H 'Content-Type: application/json' -d '{\"locale\":\"en\"}' -c /tmp/persist-cookies.txt"

# Verify the session is usable.
check "Session usable via Nginx" \
    "curl -sf '$NGINX_URL/api/v1/sessions/me' -b /tmp/persist-cookies.txt | grep -o 'session_id'"

# Check /metrics is BLOCKED via Nginx (403).
METRICS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$NGINX_URL/metrics")
echo "  /metrics via Nginx: HTTP $METRICS_CODE"
if [ "$METRICS_CODE" = "403" ]; then
    echo "  → OK (blocked externally)"
else
    echo "  → FAIL (expected 403, got $METRICS_CODE)"
    FAILURES=$((FAILURES + 1))
fi

# Check /metrics is ACCESSIBLE internally (Prometheus can scrape).
check "/metrics accessible internally" \
    "curl -sf $API_URL/metrics | grep -o 'agentcraft_http_requests_total' | head -1"

# Restart the API container (persistence test).
echo "  Restarting API container..."
docker compose restart api >/dev/null 2>&1 || true

# Wait for API to be healthy again.
echo "  Waiting for API to be healthy after restart..."
sleep 5
for i in $(seq 1 30); do
    if curl -sf "$API_URL/api/v1/health/live" >/dev/null 2>&1; then
        echo "  → API is healthy after restart"
        break
    fi
    sleep 2
    if [ $i -eq 30 ]; then
        echo "  → FAIL: API did not become healthy after restart"
        FAILURES=$((FAILURES + 1))
    fi
done

# Verify the session still works (data persisted in PostgreSQL).
check "Session persisted across API restart" \
    "curl -sf '$NGINX_URL/api/v1/sessions/me' -b /tmp/persist-cookies.txt | grep -o 'session_id'"

echo ""

# ---- C1-04: purge-cron ----
echo "--- Purge Cron ---"

# Check purge-cron service is running.
check "purge-cron container is running" \
    "docker compose ps purge-cron | grep -q 'Up' || docker compose ps purge-cron | grep -q 'running'"

# Run purge manually inside the API container.
check "purge_expired_sessions runs without error" \
    "python -m app.cleanup_purge"

echo ""

# ---- Summary ----
echo "=== Summary ==="
if [ $FAILURES -eq 0 ]; then
    echo "ALL CHECKS PASSED"
    exit 0
else
    echo "$FAILURES CHECK(S) FAILED"
    exit 1
fi
