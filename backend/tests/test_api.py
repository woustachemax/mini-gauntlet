import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

INVENTORY = Path(__file__).resolve().parents[2] / "data" / "inventory.json"
STATUS_ORDER = {"FAIL": 0, "CANNOT_SCAN": 1, "PASS": 2}
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("INVENTORY_PATH", str(INVENTORY))
    monkeypatch.setenv("SIMULATED_LATENCY_SCALE", "0")
    with TestClient(app) as test_client:
        yield test_client


def wait_for(client, scan_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        scan = client.get(f"/api/scans/{scan_id}").json()
        if scan["status"] != "RUNNING":
            return scan
        time.sleep(0.02)
    raise AssertionError(f"scan {scan_id} still RUNNING after {timeout}s")


def start(client, body=None):
    response = client.post("/api/scans", json=body)
    assert response.status_code == 202, response.text
    return response.json()


@pytest.fixture
def scan_id(client):
    scan = start(client)
    assert wait_for(client, scan["id"])["status"] == "COMPLETED"
    return scan["id"]


def findings(client, scan_id, **params):
    response = client.get(f"/api/scans/{scan_id}/findings", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_checks_catalog(client):
    checks = client.get("/api/checks").json()
    assert len(checks) == 10
    ec2 = next(c for c in checks if c["id"] == "AWS-EC2-01")
    assert ec2 == {
        "id": "AWS-EC2-01",
        "title": "Security group doesn't expose SSH or RDP to the internet",
        "severity": "CRITICAL",
        "provider": "aws",
        "collection": "security_groups",
        "resource_id_field": "group_id",
    }


def test_cors_allows_the_dashboard(client):
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_start_scan_returns_running_then_completes(client):
    scan = start(client)
    assert scan["status"] == "RUNNING"
    assert scan["account_ids"] is None
    assert scan["finished_at"] is None
    assert scan["score"] is None
    assert scan["counts"] == {"PASS": 0, "FAIL": 0, "CANNOT_SCAN": 0}

    done = wait_for(client, scan["id"])
    assert done["status"] == "COMPLETED"
    assert done["error"] is None
    assert done["counts"] == {"PASS": 27, "FAIL": 18, "CANNOT_SCAN": 4}
    assert done["score"] == 60.0
    assert done["fail_by_severity"] == {"CRITICAL": 7, "HIGH": 8, "MEDIUM": 2, "LOW": 1}
    assert {a["account_id"]: a["score"] for a in done["accounts"]} == {
        "123456789012": 58.3,
        "210987654321": 66.7,
        "8f14e45f-ceea-4e7a-9d3b-2f6c1a0b7d21": 57.1,
        "example-corp-gcp": 63.6,
    }


def test_timestamps_are_utc_iso_8601(client, scan_id):
    scan = client.get(f"/api/scans/{scan_id}").json()
    for field in ("started_at", "finished_at"):
        assert scan[field].endswith("Z")
        assert datetime.fromisoformat(scan[field]).utcoffset().total_seconds() == 0
    assert scan["finished_at"] >= scan["started_at"]


def test_scan_with_account_ids(client):
    scan = start(client, {"account_ids": ["example-corp-gcp"]})
    assert scan["account_ids"] == ["example-corp-gcp"]
    done = wait_for(client, scan["id"])
    assert done["counts"] == {"PASS": 7, "FAIL": 4, "CANNOT_SCAN": 0}
    assert done["score"] == 63.6
    assert [a["account_id"] for a in done["accounts"]] == ["example-corp-gcp"]


def test_list_scans_newest_first_with_scores_and_counts(client):
    first = start(client, {"account_ids": ["example-corp-gcp"]})
    wait_for(client, first["id"])
    second = start(client)
    wait_for(client, second["id"])

    scans = client.get("/api/scans").json()
    assert [s["id"] for s in scans] == [second["id"], first["id"]]
    assert scans[0]["score"] == 60.0
    assert scans[0]["counts"] == {"PASS": 27, "FAIL": 18, "CANNOT_SCAN": 4}
    assert scans[1]["account_ids"] == ["example-corp-gcp"]
    expected_keys = {"id", "status", "started_at", "finished_at", "account_ids", "error"}
    assert expected_keys | {"score", "counts"} <= scans[0].keys()


def test_empty_account_list_is_422(client):
    assert client.post("/api/scans", json={"account_ids": []}).status_code == 422


def test_unknown_account_is_422(client):
    response = client.post("/api/scans", json={"account_ids": ["example-corp-gcp", "nope"]})
    assert response.status_code == 422
    assert "nope" in response.json()["detail"]
    assert client.get("/api/scans").json() == []


def test_unknown_scan_is_404(client):
    assert client.get("/api/scans/999").status_code == 404
    assert client.get("/api/scans/999/findings").status_code == 404


@pytest.mark.parametrize(
    "params", [{"page_size": 101}, {"page_size": 0}, {"page": 0}, {"page": "x"}]
)
def test_bad_paging_is_422(client, scan_id, params):
    response = client.get(f"/api/scans/{scan_id}/findings", params=params)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("params", "total"),
    [
        ({"status": "FAIL"}, 18),
        ({"status": "fail"}, 18),
        ({"status": "cannot_scan"}, 4),
        ({"severity": "critical"}, 18),
        ({"severity": "Low"}, 3),
        ({"provider": "AZURE"}, 7),
        ({"provider": "gcp"}, 11),
        ({"account_id": "210987654321"}, 7),
        ({"account_id": "EXAMPLE-CORP-GCP"}, 11),
        ({"check_id": "aws-ec2-01"}, 9),
        ({"status": "fail", "provider": "gcp"}, 4),
        ({"status": "bogus"}, 0),
    ],
)
def test_filters(client, scan_id, params, total):
    page = findings(client, scan_id, page_size=100, **params)
    assert page["total"] == total
    assert len(page["items"]) == total
    for key, value in params.items():
        assert all(item[key].lower() == value.lower() for item in page["items"])


def test_filter_values_are_parameters_not_sql(client, scan_id):
    page = findings(client, scan_id, status="FAIL' OR '1'='1")
    assert page["total"] == 0


def test_pagination(client, scan_id):
    first = findings(client, scan_id, page_size=10)
    assert (first["total"], first["page"], first["page_size"]) == (49, 1, 10)
    assert len(first["items"]) == 10
    assert len(findings(client, scan_id, page_size=10, page=5)["items"]) == 9
    assert findings(client, scan_id, page_size=10, page=6)["items"] == []
    assert findings(client, scan_id)["page_size"] == 25

    paged_ids = [
        item["id"]
        for page in range(1, 6)
        for item in findings(client, scan_id, page_size=10, page=page)["items"]
    ]
    all_ids = [item["id"] for item in findings(client, scan_id, page_size=100)["items"]]
    assert paged_ids == all_ids
    assert len(set(all_ids)) == 49


def test_findings_order(client, scan_id):
    items = findings(client, scan_id, page_size=100)["items"]

    def key(item):
        return (
            STATUS_ORDER[item["status"]],
            SEVERITY_ORDER[item["severity"]],
            item["check_id"],
            item["resource_id"] or "",
        )

    assert [key(i) for i in items] == sorted(key(i) for i in items)
    assert items[0]["status"] == "FAIL"
    assert items[0]["severity"] == "CRITICAL"
    assert items[0]["check_id"] == "AWS-EC2-01"
    assert items[-1]["status"] == "PASS"
    assert items[-1]["severity"] == "LOW"


def test_finding_fields(client, scan_id):
    [item] = findings(client, scan_id, check_id="AWS-EC2-01", status="CANNOT_SCAN")["items"]
    assert item == {
        "id": item["id"],
        "scan_id": scan_id,
        "check_id": "AWS-EC2-01",
        "title": "Security group doesn't expose SSH or RDP to the internet",
        "provider": "aws",
        "account_id": "210987654321",
        "region": "us-east-1",
        "resource_id": "sg-0b1c2d3e4f5a60002",
        "status": "CANNOT_SCAN",
        "severity": "CRITICAL",
        "details": "security group sg-0b1c2d3e4f5a60002 (corrupt-record): "
        "port 'twenty-two' is not an integer",
    }


def test_missing_inventory_marks_scan_failed(client, tmp_path, monkeypatch):
    monkeypatch.setenv("INVENTORY_PATH", str(tmp_path / "missing.json"))
    scan = start(client)
    done = wait_for(client, scan["id"])
    assert done["status"] == "FAILED"
    assert "missing.json" in done["error"]
    assert done["finished_at"] is not None
    assert done["score"] is None
    assert findings(client, scan["id"])["total"] == 0


def test_restart_marks_running_scans_failed(client):
    stale_id = db.insert_scan(None)
    with TestClient(app):
        pass
    scan = client.get(f"/api/scans/{stale_id}").json()
    assert scan["status"] == "FAILED"
    assert "restart" in scan["error"]


def test_scan_uses_real_latency_concurrently(client, monkeypatch):
    monkeypatch.setenv("SIMULATED_LATENCY_SCALE", "1")
    started = time.perf_counter()
    scan = start(client)
    done = wait_for(client, scan["id"])
    elapsed = time.perf_counter() - started
    assert done["status"] == "COMPLETED"
    assert 3.0 <= elapsed < 4.0
