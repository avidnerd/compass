"""Single local SQLite database (WAL) with explicit numbered migrations."""
import logging
import re
from pathlib import Path

import aiosqlite

from .config import settings

logger = logging.getLogger("compass.db")

# Packaged installs carry the migrations inside app/; a source checkout keeps
# them beside it at backend/migrations.
_BUNDLED_MIGRATIONS = Path(__file__).resolve().parent / "migrations"
MIGRATIONS_DIR = (_BUNDLED_MIGRATIONS if _BUNDLED_MIGRATIONS.is_dir()
                  else Path(__file__).resolve().parents[1] / "migrations")

_conn: aiosqlite.Connection | None = None


async def connect(db_path: str | Path | None = None) -> aiosqlite.Connection:
    """Open (or return) the shared connection. FastAPI runs one process; a
    single serialized aiosqlite connection avoids writer contention."""
    global _conn
    if _conn is None:
        path = Path(db_path or settings.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = await aiosqlite.connect(path)
        _conn.row_factory = aiosqlite.Row
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA foreign_keys=ON")
        await _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


async def close() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


def get() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("Database not connected; call db.connect() first")
    return _conn


async def run_migrations(conn: aiosqlite.Connection | None = None) -> list[int]:
    """Apply numbered migrations (backend/migrations/NNN_*.sql) transactionally."""
    conn = conn or await connect()
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    await conn.commit()
    cur = await conn.execute("SELECT version FROM schema_migrations")
    applied = {row[0] for row in await cur.fetchall()}

    pattern = re.compile(r"^(\d{3})_.+\.sql$")
    ran: list[int] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = pattern.match(path.name)
        if not m:
            continue
        version = int(m.group(1))
        if version in applied:
            continue
        sql = path.read_text()
        try:
            await conn.executescript(sql)
            await conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        ran.append(version)
        logger.info("[db] applied migration %s", path.name)
    return ran
