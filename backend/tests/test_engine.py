import logging
import time
from collections import Counter
from pathlib import Path

import pytest

from app.scanner.engine import load_snapshot, run_scan, score
from app.scanner.models import Finding, Severity, Status
from app.scanner.registry import CHECKS, Check

INVENTORY = Path(__file__).resolve().parents[2] / "data" / "inventory.json"

GOOD_BUCKET = {
    "name": "good-bucket",
    "region": "us-east-1",
    "public_access_block": {
        "block_public_acls": True,
        "ignore_public_acls": True,
        "block_public_policy": True,
        "restrict_public_buckets": True,
    },
}


def snapshot(*accounts):
    return {"snapshot_taken_at": "2026-10-01T00:00:00Z", "accounts": list(accounts)}


def aws_account(account_id="111111111111", resources=None, errors=None):
    return {
        "provider": "aws",
        "account_id": account_id,
        "simulated_latency_ms": 0,
        "errors": errors or {},
        "resources": resources or {},
    }


def finding(status):
    return Finding("X-1", "t", "aws", "a", None, None, status, Severity.LOW, "")


def test_collection_in_errors_gives_one_cannot_scan_per_check():
    account = aws_account(errors={"iam_users": "AccessDenied"})
    findings = run_scan(snapshot(account))

    assert sorted(f.check_id for f in findings) == ["AWS-IAM-01", "AWS-IAM-02"]
    for f in findings:
        assert f.status is Status.CANNOT_SCAN
        assert f.resource_id is None
        assert "AccessDenied" in f.details


def test_missing_collection_gives_no_findings():
    assert run_scan(snapshot(aws_account())) == []


def test_collection_that_is_not_a_list_cannot_scan():
    findings = run_scan(snapshot(aws_account(resources={"rds_instances": "oops"})))
    assert [(f.check_id, f.status) for f in findings] == [("AWS-RDS-01", Status.CANNOT_SCAN)]


def test_check_that_raises_does_not_stop_the_scan(monkeypatch, caplog):
    def explode(resource, snapshot_time):
        raise RuntimeError("boom")

    broken = Check("TEST-BOOM", "Always raises", Severity.LOW, "aws", "s3_buckets", "name", explode)
    monkeypatch.setitem(CHECKS, "TEST-BOOM", broken)
    account = aws_account(resources={"s3_buckets": [GOOD_BUCKET, "not-a-dict"]})

    with caplog.at_level(logging.WARNING):
        findings = run_scan(snapshot(account))

    by_check = {(f.check_id, f.resource_id): f for f in findings}
    assert len(findings) == 4
    assert by_check[("TEST-BOOM", "good-bucket")].status is Status.CANNOT_SCAN
    assert "boom" in by_check[("TEST-BOOM", "good-bucket")].details
    assert by_check[("AWS-S3-01", "good-bucket")].status is Status.PASS
    assert by_check[("AWS-S3-01", None)].status is Status.CANNOT_SCAN
    assert "TEST-BOOM" in caplog.text


def test_account_ids_filter():
    accounts = [
        aws_account("aaa", {"s3_buckets": [GOOD_BUCKET]}),
        aws_account("bbb", {"s3_buckets": [GOOD_BUCKET]}),
    ]
    findings = run_scan(snapshot(*accounts), account_ids=["bbb"])
    assert [f.account_id for f in findings] == ["bbb"]


def test_finding_carries_region_and_registry_metadata():
    [f] = run_scan(snapshot(aws_account(resources={"s3_buckets": [GOOD_BUCKET]})))
    assert f.region == "us-east-1"
    assert f.title == "S3 bucket blocks public access"
    assert f.severity is Severity.HIGH
    assert f.provider == "aws"


def test_load_snapshot_requires_inventory_path(monkeypatch):
    monkeypatch.delenv("INVENTORY_PATH", raising=False)
    with pytest.raises(RuntimeError, match="INVENTORY_PATH"):
        load_snapshot()


def test_score_is_none_without_pass_or_fail():
    assert score([]) is None
    assert score([finding(Status.CANNOT_SCAN), finding(Status.CANNOT_SCAN)]) is None


def test_score_ignores_cannot_scan_and_rounds():
    findings = [
        finding(Status.PASS),
        finding(Status.PASS),
        finding(Status.FAIL),
        finding(Status.CANNOT_SCAN),
    ]
    assert score(findings) == 66.7


@pytest.fixture(scope="module")
def real_scan():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("INVENTORY_PATH", str(INVENTORY))
        mp.setenv("SCAN_WORKERS", "4")
        start = time.perf_counter()
        findings = run_scan(load_snapshot())
        elapsed = time.perf_counter() - start
    return findings, elapsed


def test_real_inventory_runs_accounts_concurrently(real_scan):
    _, elapsed = real_scan
    # The slowest account sleeps 3 s; run one after another they would add up to 8 s.
    assert 3.0 <= elapsed < 4.0


def test_real_inventory_totals(real_scan):
    findings, _ = real_scan
    counts = Counter(f.status for f in findings)
    assert len(findings) == 49
    assert counts[Status.PASS] == 27
    assert counts[Status.FAIL] == 18
    assert counts[Status.CANNOT_SCAN] == 4
    assert score(findings) == 60.0


def test_real_inventory_per_account_scores_and_fail_severities(real_scan):
    findings, _ = real_scan
    scores = {
        account_id: score([f for f in findings if f.account_id == account_id])
        for account_id in {f.account_id for f in findings}
    }
    assert scores == {
        "123456789012": 58.3,
        "210987654321": 66.7,
        "8f14e45f-ceea-4e7a-9d3b-2f6c1a0b7d21": 57.1,
        "example-corp-gcp": 63.6,
    }
    fails = Counter(f.severity for f in findings if f.status is Status.FAIL)
    assert fails == {Severity.CRITICAL: 7, Severity.HIGH: 8, Severity.MEDIUM: 2, Severity.LOW: 1}
