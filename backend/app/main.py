import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import db
from app.scanner.engine import load_snapshot, run_scan, score_from_counts
from app.scanner.models import Severity, Status
from app.scanner.registry import CHECKS

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Mini Gauntlet", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ScanRequest(BaseModel):
    account_ids: Annotated[list[str], Field(min_length=1)] | None = None


def status_counts(counts: dict[str, int]) -> dict[str, int]:
    return {status: counts.get(status, 0) for status in Status}


def scan_summary(scan: dict, counts: dict[str, int]) -> dict:
    return {
        **scan,
        "score": score_from_counts(counts.get(Status.PASS, 0), counts.get(Status.FAIL, 0)),
        "counts": status_counts(counts),
    }


def run_scan_job(scan_id: int, account_ids: list[str] | None) -> None:
    try:
        findings = run_scan(load_snapshot(), account_ids)
        db.complete_scan(scan_id, findings)
    except Exception as exc:
        log.exception("scan %s failed", scan_id)
        db.fail_scan(scan_id, f"{type(exc).__name__}: {exc}")


def known_account_ids() -> set[str] | None:
    try:
        return {str(a.get("account_id")) for a in load_snapshot()["accounts"]}
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/checks")
def list_checks():
    return [
        {
            "id": c.check_id,
            "title": c.title,
            "severity": c.severity,
            "provider": c.provider,
            "collection": c.collection,
            "resource_id_field": c.resource_id_field,
        }
        for c in CHECKS.values()
    ]


@app.post("/api/scans", status_code=202)
def start_scan(body: ScanRequest | None = None):
    account_ids = body.account_ids if body else None
    if account_ids is not None:
        account_ids = list(dict.fromkeys(account_ids))
        known = known_account_ids()
        # If the inventory can't be read here, the scan itself fails and records why.
        if known is not None:
            unknown = [a for a in account_ids if a not in known]
            if unknown:
                raise HTTPException(422, f"unknown account IDs: {', '.join(unknown)}")

    scan_id = db.insert_scan(account_ids)
    threading.Thread(target=run_scan_job, args=(scan_id, account_ids), daemon=True).start()
    return scan_summary(db.get_scan(scan_id), {})


@app.get("/api/scans")
def list_scans():
    return [scan_summary(scan, counts) for scan, counts in db.list_scans()]


@app.get("/api/scans/{scan_id}")
def get_scan(scan_id: int):
    scan = db.get_scan(scan_id)
    if scan is None:
        raise HTTPException(404, "scan not found")

    totals: dict[str, int] = {}
    fails_by_severity = {severity: 0 for severity in Severity}
    per_account: dict[str, dict[str, int]] = {}
    for row in db.finding_counts(scan_id):
        totals[row["status"]] = totals.get(row["status"], 0) + row["n"]
        account = per_account.setdefault(row["account_id"], {})
        account[row["status"]] = account.get(row["status"], 0) + row["n"]
        if row["status"] == Status.FAIL:
            fails_by_severity[row["severity"]] += row["n"]

    return {
        **scan_summary(scan, totals),
        "fail_by_severity": fails_by_severity,
        "accounts": [
            {
                "account_id": account_id,
                "score": score_from_counts(counts.get(Status.PASS, 0), counts.get(Status.FAIL, 0)),
                "counts": status_counts(counts),
            }
            for account_id, counts in per_account.items()
        ],
    }


@app.get("/api/scans/{scan_id}/findings")
def list_findings(
    scan_id: int,
    status: str | None = None,
    severity: str | None = None,
    provider: str | None = None,
    account_id: str | None = None,
    check_id: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    if db.get_scan(scan_id) is None:
        raise HTTPException(404, "scan not found")
    filters = {
        "status": status,
        "severity": severity,
        "provider": provider,
        "account_id": account_id,
        "check_id": check_id,
    }
    items, total = db.query_findings(scan_id, filters, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
