import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import app.scanner.checks  # noqa: F401  (registers every check)
from app.scanner.checks.common import parse_timestamp
from app.scanner.models import Finding, Status
from app.scanner.registry import Check, checks_for

log = logging.getLogger(__name__)


def load_snapshot(path: str | None = None) -> dict:
    path = path or os.environ.get("INVENTORY_PATH")
    if not path:
        raise RuntimeError("INVENTORY_PATH is not set")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_scan(snapshot: dict, account_ids: list[str] | None = None) -> list[Finding]:
    snapshot_time = parse_timestamp(snapshot["snapshot_taken_at"])
    accounts = snapshot["accounts"]
    if account_ids is not None:
        accounts = [a for a in accounts if a.get("account_id") in account_ids]

    workers = int(os.environ.get("SCAN_WORKERS", "4"))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(scan_account, accounts, [snapshot_time] * len(accounts))
        return [finding for account_findings in results for finding in account_findings]


def scan_account(account: dict, snapshot_time: datetime) -> list[Finding]:
    scale = float(os.environ.get("SIMULATED_LATENCY_SCALE", "1"))
    time.sleep(account.get("simulated_latency_ms", 0) / 1000 * scale)
    checks = checks_for(account.get("provider"))
    if not checks:
        log.warning(
            "account %r has unknown provider %r", account.get("account_id"), account.get("provider")
        )
    findings = []
    for check in checks:
        findings.extend(run_check(check, account, snapshot_time))
    return findings


def run_check(check: Check, account: dict, snapshot_time: datetime) -> list[Finding]:
    errors = account.get("errors") or {}
    resources = account.get("resources") or {}

    if check.collection in errors:
        details = f"{errors[check.collection]}: could not read {check.collection}"
        return [make_finding(check, account, None, Status.CANNOT_SCAN, details)]

    items = resources.get(check.collection)
    if items is None:
        return []
    if not isinstance(items, list):
        details = f"{check.collection} is not a list"
        return [make_finding(check, account, None, Status.CANNOT_SCAN, details)]

    return [evaluate(check, account, resource, snapshot_time) for resource in items]


def evaluate(check: Check, account: dict, resource, snapshot_time: datetime) -> Finding:
    try:
        status, details = check.run(resource, snapshot_time)
    except Exception as exc:
        status, details = Status.CANNOT_SCAN, f"could not evaluate: {exc}"

    finding = make_finding(check, account, resource, status, details)
    if status is Status.CANNOT_SCAN:
        log.warning(
            "%s on %r in account %r: %r",
            check.check_id,
            finding.resource_id,
            finding.account_id,
            details,
        )
    return finding


def make_finding(check: Check, account: dict, resource, status: Status, details: str) -> Finding:
    region = None
    resource_id = None
    if isinstance(resource, dict):
        region = resource.get("region")
        resource_id = resource.get(check.resource_id_field)
    return Finding(
        check_id=check.check_id,
        title=check.title,
        provider=check.provider,
        account_id=str(account.get("account_id")),
        region=None if region is None else str(region),
        resource_id=None if resource_id is None else str(resource_id),
        status=status,
        severity=check.severity,
        details=details,
    )


def score(findings: list[Finding]) -> float | None:
    passed = sum(1 for f in findings if f.status is Status.PASS)
    failed = sum(1 for f in findings if f.status is Status.FAIL)
    return score_from_counts(passed, failed)


def score_from_counts(passed: int, failed: int) -> float | None:
    if passed + failed == 0:
        return None
    return round(100 * passed / (passed + failed), 1)
