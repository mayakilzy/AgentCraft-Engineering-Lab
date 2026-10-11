"""Migration + ORM tests — A01 gate: clean checkout, migration tests pass.

We exercise the schema against in-memory SQLite. PostgreSQL dialect specifics
(JSONB, native UUID) are verified at the migration SQL level in G07
(Compose) — here we test that the model + migration round-trips.
"""
from __future__ import annotations

import os

# Pin test env BEFORE importing the app.
os.environ["APP_ENV"] = "local"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MENTOR_PROVIDER"] = "disabled"
os.environ["CORS_ORIGINS"] = '["http://localhost:5173"]'

import uuid

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.fixture(scope="module")
def migrated_sqlite():
    """Run the Alembic migration against a fresh in-memory SQLite DB."""
    from alembic import command
    from alembic.config import Config as AlembicConfig
    from app.config import get_settings
    get_settings.cache_clear()
    # Force SQLite in-memory for this migration run.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    get_settings.cache_clear()

    cfg = AlembicConfig("alembic.ini")
    # Alembic resolves the URL from env.py via get_settings(); we override
    # the alembic main option to point to a fresh file DB (in-memory cannot
    # survive across connections). Use a temp file DB instead.
    import tempfile

    fdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    fdb.close()
    os.environ["DATABASE_URL"] = f"sqlite:///{fdb.name}"
    get_settings.cache_clear()
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{fdb.name}")

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{fdb.name}")
    yield engine, fdb.name
    engine.dispose()
    try:
        os.unlink(fdb.name)
    except OSError:
        pass


def test_all_tables_present(migrated_sqlite):
    engine, _ = migrated_sqlite
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "guest_sessions",
        "experiments",
        "runs",
        "run_events",
        "graph_nodes",
        "graph_edges",
        "alembic_version",  # Alembic bookkeeping
    }
    missing = expected - tables
    assert not missing, f"missing tables: {missing}"


def test_indexes_created(migrated_sqlite):
    engine, _ = migrated_sqlite
    inspector = inspect(engine)

    run_indexes = {i["name"] for i in inspector.get_indexes("runs")}
    assert "ix_runs_session_id" in run_indexes
    assert "ix_runs_experiment_id" in run_indexes
    assert "ix_runs_status" in run_indexes

    # Unique constraints declared inline are materialized as unique indexes
    # on SQLite. Inspect both uniques and indexes for the constraint name.
    gn_uniques = {
        u["name"] for u in inspector.get_unique_constraints("graph_nodes")
    }.union({i["name"] for i in inspector.get_indexes("graph_nodes")})
    assert "ux_gn_session_dataset_ref" in gn_uniques

    ge_uniques = {
        u["name"] for u in inspector.get_unique_constraints("graph_edges")
    }.union({i["name"] for i in inspector.get_indexes("graph_edges")})
    assert "ux_ge_session_dataset_src_tgt_rel" in ge_uniques


def test_orm_round_trip(migrated_sqlite):
    """Insert a session + run; query it back through the ORM."""
    from sqlalchemy.orm import Session
    from app.models.guest_session import GuestSession
    from app.models.run import Run
    from datetime import datetime, timedelta, timezone

    engine, _ = migrated_sqlite
    sid = uuid.uuid4()
    rid = uuid.uuid4()
    with Session(engine) as s:
        gs = GuestSession(
            id=sid,
            cookie_token="tok-test-001",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            locale="en",
        )
        s.add(gs)
        s.flush()
        r = Run(
            id=rid,
            session_id=sid,
            experiment_id="graph-first-network",
            mode="guided",
            status="CREATED",
            trace_id="trace-xyz",
        )
        s.add(r)
        s.commit()

    # Read back.
    with Session(engine) as s:
        loaded = s.get(Run, rid)
        assert loaded is not None
        assert loaded.status == "CREATED"
        assert loaded.trace_id == "trace-xyz"


def test_downgrade_is_reversible(migrated_sqlite):
    """Verify the downgrade path produces a clean DB (rollback safety)."""
    from alembic import command
    from alembic.config import Config as AlembicConfig
    from sqlalchemy import inspect

    engine, db_path = migrated_sqlite
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.downgrade(cfg, "base")
    inspector = inspect(engine)
    tables_after = set(inspector.get_table_names())
    # Only alembic_version may remain (no, base removes it too).
    assert "runs" not in tables_after
    assert "graph_nodes" not in tables_after

    # Re-upgrade so subsequent tests in the module can use it.
    command.upgrade(cfg, "head")


def test_fixture_shape():
    """The starter fixture matches its declared expected counts."""
    from app.fixtures.graph_seed import STARTER_FIVE_V1

    assert len(STARTER_FIVE_V1.nodes) == STARTER_FIVE_V1.expected["node_count"]
    assert len(STARTER_FIVE_V1.edges) == STARTER_FIVE_V1.expected["edge_count"]
    # All edge endpoints must reference existing node refs.
    refs = {n.ref for n in STARTER_FIVE_V1.nodes}
    for e in STARTER_FIVE_V1.edges:
        assert e.source_ref in refs, f"edge source not in nodes: {e.source_ref}"
        assert e.target_ref in refs, f"edge target not in nodes: {e.target_ref}"


def test_fixture_lookup_fail_closed():
    from app.fixtures.graph_seed import get_fixture
    assert get_fixture("does-not-exist") is None
