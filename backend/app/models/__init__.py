"""ORM models package. Mirrors `02_ARCHITECTURE_AND_CONTRACTS.md` §2.

G07-C2-01: added PurgeTask model for recoverable Neo4j cleanup.
"""
from app.models.purge_task import PurgeTask  # noqa: F401
