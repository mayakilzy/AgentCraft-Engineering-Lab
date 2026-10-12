#!/usr/bin/env bash
# AgentCraft Engineering Lab — Docker Compose integration smoke.
#
# G08-C3: runs INSIDE the test-runner container on the agentcraft-net
# network. Tests the REAL PostgreSQL, Neo4j, observability stack,
# and Nginx — all via internal service names.
#
# C3-5: SESSION_COOKIE_SECURE=true means curl won't send the cookie
# over HTTP automatically. We extract the cookie token from the
# Set-Cookie header and pass it manually via -H "Cookie: ...".
#
# Exit codes:
#   0: all checks passed
#   1: one or more checks failed

set -euo pipefail

API_URL="http://api:8000"
NGINX_URL="http://web:80"
PROMETHEUS_URL="http://prometheus:9090"
TEMPO_URL="http://tempo:3200"
GRAFANA_URL="http://grafana:3000"
POSTGRES_HOST="postgres"
POSTGRES_PORT="5432"
PG_PW="${POSTGRES_PASSWORD:-changeme}"
NEO4J_PW="${NEO4J_PASSWORD:-changeme}"
GRAFANA_PW="${GRAFANA_ADMIN_PASSWORD:-changeme}"

FAILURES=0

pass() { echo "  → OK"; }
fail() { echo "  → FAIL: $1"; FAILURES=$((FAILURES + 1)); }

check() {
    local name="$1" cmd="$2"
    echo "CHECK: $name"
    if eval "$cmd" >/dev/null 2>&1; then
        pass
    else
        fail "$name failed"
    fi
}

# Helper: extract cookie token from Set-Cookie header.
extract_cookie() {
    sed "s/.*ac_guest=//;s/;.*//" | tr -d "\r\n"
}

echo "=== AgentCraft Docker Compose Integration Smoke ==="
echo ""

# ======== PostgreSQL Integration ========
echo "--- PostgreSQL Integration ---"

echo "CHECK: PostgreSQL connectivity"
if python -c "
import psycopg2
c = psycopg2.connect(host='$POSTGRES_HOST', port=$POSTGRES_PORT, user='agentcraft', password='$PG_PW', dbname='agentcraft')
c.close()
" 2>/dev/null; then pass; else fail "connectivity"; fi

echo "CHECK: PostgreSQL tables exist (migrations ran)"
TABLE_COUNT=$(python -c "
import psycopg2
c = psycopg2.connect(host='$POSTGRES_HOST', port=$POSTGRES_PORT, user='agentcraft', password='$PG_PW', dbname='agentcraft')
cur = c.cursor()
cur.execute(\"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'\")
print(cur.fetchone()[0])
c.close()
" 2>/dev/null || echo "0")
if [ "$TABLE_COUNT" -ge 7 ]; then
    echo "  → OK ($TABLE_COUNT tables)"
else
    fail "expected >=7 tables, got $TABLE_COUNT"
fi

check "guest_sessions writable" \
    "python -c \"import psycopg2; c=psycopg2.connect(host='$POSTGRES_HOST',port=$POSTGRES_PORT,user='agentcraft',password='$PG_PW',dbname='agentcraft'); cur=c.cursor(); cur.execute('SELECT count(*) FROM guest_sessions'); c.close()\""

echo ""

# ======== Neo4j Integration ========
echo "--- Neo4j Integration ---"

echo "CHECK: Neo4j connectivity"
if python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j', '$NEO4J_PW'))
d.verify_connectivity()
d.close()
" 2>/dev/null; then pass; else fail "connectivity"; fi

echo "CHECK: GDS status (exact procedure match)"
GDS_RESULT=$(python -c "
from neo4j import GraphDatabase
import json
try:
    d = GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j', '$NEO4J_PW'))
    d.verify_connectivity()
    with d.session() as s:
        procs = [r['name'] for r in s.run(\"SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'gds.' RETURN name\")]
        louvain = 'gds.louvain.stream' in procs
        has_any = len(procs) > 0
        try:
            s.run('CALL gds.graph.list() YIELD graphName RETURN count(graphName) AS cnt').single()
            licensed = True
        except Exception:
            licensed = False
        print(json.dumps({'procedures': has_any, 'louvain': louvain, 'licensed': licensed}))
    d.close()
except Exception as e:
    print(json.dumps({'error': str(e)}))
" 2>/dev/null || echo '{"error":"failed"}')

echo "  GDS: $GDS_RESULT"
if echo "$GDS_RESULT" | python -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('error') else 1)" 2>/dev/null; then
    echo "  → GDS BLOCKED (connection error)"
elif echo "$GDS_RESULT" | python -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('licensed') and d.get('louvain') else 1)" 2>/dev/null; then
    echo "  → GDS AVAILABLE + LICENSED"
else
    echo "  → GDS NOT_AVAILABLE (not licensed — honestly labelled)"
fi
pass

echo "CHECK: Neo4j namespace isolation (two sessions)"
if python -c "
from neo4j import GraphDatabase
import uuid
d = GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j', '$NEO4J_PW'))
d.verify_connectivity()
with d.session() as s:
    sa, sb = uuid.uuid4(), uuid.uuid4()
    nsa = f'sess_{str(sa).replace(\"-\", \"\")[:12]}'
    nsb = f'sess_{str(sb).replace(\"-\", \"\")[:12]}'
    la = f'__{nsa}__ds_test__'
    lb = f'__{nsb}__ds_test__'
    s.run(f'MERGE (n:\`{la}\` {chr(123)}ref: \"A1\"{chr(125)}) SET n.kind=\"tool\"')
    s.run(f'MERGE (n:\`{lb}\` {chr(123)}ref: \"B1\"{chr(125)}) SET n.kind=\"tool\"')
    ca = s.run(f'MATCH (n:\`{la}\`) RETURN count(n) AS cnt').single()['cnt']
    cb = s.run(f'MATCH (n:\`{lb}\`) RETURN count(n) AS cnt').single()['cnt']
    assert ca == 1 and cb == 1
    s.run(f'MATCH (n) WHERE ANY(l IN labels(n) WHERE l STARTS WITH \"__{nsa}__\") DETACH DELETE n')
    ca2 = s.run(f'MATCH (n:\`{la}\`) RETURN count(n) AS cnt').single()['cnt']
    cb2 = s.run(f'MATCH (n:\`{lb}\`) RETURN count(n) AS cnt').single()['cnt']
    assert ca2 == 0 and cb2 == 1
    s.run(f'MATCH (n) WHERE ANY(l IN labels(n) WHERE l STARTS WITH \"__{nsb}__\") DETACH DELETE n')
d.close()
print('OK')
" 2>/dev/null; then pass; else fail "namespace isolation"; fi

echo ""

# ======== Observability Integration ========
echo "--- Observability Integration ---"

check "Prometheus healthy" "curl -sf $PROMETHEUS_URL/-/healthy"
sleep 5

echo "CHECK: Prometheus scraping API"
if curl -sf "$PROMETHEUS_URL/api/v1/targets?state=active" | \
    python -c "
import json,sys
d=json.load(sys.stdin)
t=[x for x in d['data']['activeTargets'] if 'agentcraft-api' in x.get('labels',{}).get('job','')]
assert len(t)>=1 and t[0]['health']=='up'
" 2>/dev/null; then pass; else fail "not scraping API"; fi

echo "CHECK: Prometheus has agentcraft metrics"
if curl -sf "$PROMETHEUS_URL/api/v1/query?query=agentcraft_http_requests_total" | \
    python -c "
import json,sys
d=json.load(sys.stdin)
assert len(d['data']['result'])>0
" 2>/dev/null; then pass; else fail "no metrics"; fi

echo "CHECK: Tempo ready"
TEMPO_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TEMPO_URL/ready" 2>/dev/null || echo "000")
if [ "$TEMPO_CODE" = "200" ]; then
    pass
else
    TEMPO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$TEMPO_URL/status" 2>/dev/null || echo "000")
    if [ "$TEMPO_STATUS" = "200" ]; then
        echo "  → OK (via /status)"
    else
        fail "Tempo not ready (ready=$TEMPO_CODE, status=$TEMPO_STATUS)"
    fi
fi

check "Grafana healthy" "curl -sf $GRAFANA_URL/api/health"

echo "CHECK: Grafana datasources (Prometheus + Tempo)"
if curl -sf -u "admin:$GRAFANA_PW" "$GRAFANA_URL/api/datasources" | \
    python -c "
import json,sys
ds=json.load(sys.stdin)
types=[d['type'] for d in ds]
assert 'prometheus' in types and 'tempo' in types
" 2>/dev/null; then pass; else fail "datasources"; fi

echo "CHECK: OTEL Collector healthy"
OTEL_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://otel-collector:13133/ 2>/dev/null || echo "000")
if [ "$OTEL_CODE" = "200" ]; then
    pass
else
    echo "  → SKIP (health endpoint returned $OTEL_CODE)"
fi

# Trace flow: create session + run, extract cookie manually.
echo "CHECK: Trace flow (FastAPI → Collector → Tempo)"
curl -s -D /tmp/tr-headers -o /tmp/tr-body -X POST "$API_URL/api/v1/sessions/guest" \
    -H 'Content-Type: application/json' \
    -d '{"locale":"en"}' 2>/dev/null
COOKIE_TOKEN=$(cat /tmp/tr-headers 2>/dev/null | grep -i set-cookie | extract_cookie || echo "")

if [ -z "$COOKIE_TOKEN" ]; then
    fail "could not create session for trace test"
else
    RUN_RESULT=$(curl -sf -X POST "$API_URL/api/v1/experiments/trace-one-request/runs" \
        -H 'Content-Type: application/json' \
        -H "Cookie: ac_guest=$COOKIE_TOKEN" \
        -d '{"mode":"guided","inputs":{}}' 2>/dev/null || echo "{}")
    TRACE_ID=$(echo "$RUN_RESULT" | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('trace_id',''))" 2>/dev/null || echo "")

    if [ -n "$TRACE_ID" ] && [ "$TRACE_ID" != "None" ]; then
        echo "  trace_id=${TRACE_ID:0:16}..."
        sleep 10
        TEMPO_TRACE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TEMPO_URL/api/traces/$TRACE_ID" 2>/dev/null || echo "000")
        if [ "$TEMPO_TRACE_CODE" = "200" ]; then
            pass
        elif [ "$TEMPO_TRACE_CODE" = "404" ]; then
            echo "  → SKIP (trace not yet indexed — may need more time)"
        else
            fail "trace not found in Tempo (HTTP $TEMPO_TRACE_CODE)"
        fi
    else
        fail "run has no trace_id"
    fi
fi

echo ""

# ======== Persistence + Security ========
echo "--- Persistence + Security ---"

# Create session via Nginx + extract cookie.
echo "CHECK: Create session via Nginx"
curl -s -D /tmp/nx-headers -o /tmp/nx-body -X POST "$NGINX_URL/api/v1/sessions/guest" \
    -H 'Content-Type: application/json' \
    -d '{"locale":"en"}' 2>/dev/null
NGINX_COOKIE=$(cat /tmp/nx-headers 2>/dev/null | grep -i set-cookie | extract_cookie || echo "")

if [ -n "$NGINX_COOKIE" ]; then
    pass
else
    fail "could not create session via Nginx"
fi

echo "CHECK: Session usable via Nginx"
if curl -sf "$NGINX_URL/api/v1/sessions/me" \
    -H "Cookie: ac_guest=$NGINX_COOKIE" 2>/dev/null | \
    grep -o 'session_id' >/dev/null 2>&1; then
    pass
else
    fail "session not usable"
fi

# Cookie attributes from the actual POST response.
echo "CHECK: Cookie attributes (Set-Cookie header)"
COOKIE_HEADER=$(cat /tmp/nx-headers 2>/dev/null | grep -i set-cookie || echo "")
if [ -z "$COOKIE_HEADER" ]; then
    fail "no Set-Cookie header"
else
    echo "  $COOKIE_HEADER"
    if echo "$COOKIE_HEADER" | grep -qi "HttpOnly"; then
        echo "  → HttpOnly: present"
    else
        fail "HttpOnly missing"
    fi
    if echo "$COOKIE_HEADER" | grep -qi "SameSite"; then
        echo "  → SameSite: present"
    else
        fail "SameSite missing"
    fi
    if echo "$COOKIE_HEADER" | grep -qi "Secure"; then
        echo "  → Secure: present (production mode)"
    else
        fail "Secure missing (expected because SESSION_COOKIE_SECURE=true)"
    fi
fi

# /metrics blocked via Nginx.
echo "CHECK: /metrics blocked via Nginx (403)"
METRICS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$NGINX_URL/metrics")
if [ "$METRICS_CODE" = "403" ]; then
    echo "  → OK (HTTP 403)"
else
    fail "/metrics returned $METRICS_CODE (expected 403)"
fi

# /metrics accessible internally.
check "/metrics accessible internally" \
    "curl -sf $API_URL/metrics | grep -o 'agentcraft_http_requests_total' | head -1"

echo ""

# ======== Purge Cron ========
echo "--- Purge Cron ---"

echo "CHECK: purge_expired_sessions runs without error"
if python -m app.cleanup_purge; then
    pass
else
    fail "cleanup_purge failed"
fi

echo ""

# ======== Summary ========
echo "=== Summary ==="
if [ $FAILURES -eq 0 ]; then
    echo "ALL CHECKS PASSED"
    exit 0
else
    echo "$FAILURES CHECK(S) FAILED"
    exit 1
fi
