import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from app.scanner.models import Finding

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    account_ids TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans (id),
    check_id TEXT NOT NULL,
    title TEXT NOT NULL,
    provider TEXT NOT NULL,
    account_id TEXT NOT NULL,
    region TEXT,
    resource_id TEXT,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS findings_scan_id ON findings (scan_id);
"""

FILTER_COLUMNS = ("status", "severity", "provider", "account_id", "check_id")

FINDINGS_ORDER = """
    CASE status WHEN 'FAIL' THEN 0 WHEN 'CANNOT_SCAN' THEN 1 ELSE 2 END,
    CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
    check_id,
    resource_id,
    id
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def database_path() -> str:
    return os.environ.get("DATABASE_PATH", "/data/gauntlet.db")


@contextmanager
def connect():
    conn = sqlite3.connect(database_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(os.path.dirname(database_path()) or ".", exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.execute(
            "UPDATE scans SET status = 'FAILED', finished_at = ?, error = ?"
            " WHERE status = 'RUNNING'",
            (now(), "interrupted by an API restart"),
        )


def insert_scan(account_ids: list[str] | None) -> int:
    stored = None if account_ids is None else json.dumps(account_ids)
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO scans (status, started_at, account_ids) VALUES ('RUNNING', ?, ?)",
            (now(), stored),
        )
        return cursor.lastrowid


def complete_scan(scan_id: int, findings: list[Finding]) -> None:
    rows = [
        (
            scan_id,
            f.check_id,
            f.title,
            f.provider,
            f.account_id,
            f.region,
            f.resource_id,
            f.status,
            f.severity,
            f.details,
        )
        for f in findings
    ]
    with connect() as conn:
        conn.executemany(
            "INSERT INTO findings (scan_id, check_id, title, provider, account_id, region,"
            " resource_id, status, severity, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            "UPDATE scans SET status = 'COMPLETED', finished_at = ? WHERE id = ?",
            (now(), scan_id),
        )


def fail_scan(scan_id: int, error: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE scans SET status = 'FAILED', finished_at = ?, error = ? WHERE id = ?",
            (now(), error, scan_id),
        )


def scan_row_to_dict(row: sqlite3.Row) -> dict:
    scan = dict(row)
    scan["account_ids"] = None if row["account_ids"] is None else json.loads(row["account_ids"])
    return scan


def list_scans() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM scans ORDER BY id DESC").fetchall()
        counts = conn.execute(
            "SELECT scan_id, status, COUNT(*) AS n FROM findings GROUP BY scan_id, status"
        ).fetchall()
    by_scan: dict[int, dict[str, int]] = {}
    for c in counts:
        by_scan.setdefault(c["scan_id"], {})[c["status"]] = c["n"]
    return [(scan_row_to_dict(row), by_scan.get(row["id"], {})) for row in rows]


def get_scan(scan_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    return None if row is None else scan_row_to_dict(row)


def finding_counts(scan_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT account_id, severity, status, COUNT(*) AS n FROM findings"
            " WHERE scan_id = ? GROUP BY account_id, severity, status ORDER BY account_id",
            (scan_id,),
        ).fetchall()


def query_findings(scan_id: int, filters: dict, page: int, page_size: int) -> tuple[list, int]:
    where = ["scan_id = ?"]
    params: list = [scan_id]
    # Column names come from FILTER_COLUMNS, never from the request; values are always parameters.
    for column in FILTER_COLUMNS:
        value = filters.get(column)
        if value is not None:
            where.append(f"{column} = ? COLLATE NOCASE")
            params.append(value)
    where_sql = " AND ".join(where)

    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM findings WHERE {where_sql}", params).fetchone()[
            0
        ]
        rows = conn.execute(
            f"SELECT * FROM findings WHERE {where_sql} ORDER BY {FINDINGS_ORDER} LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return [dict(row) for row in rows], total
