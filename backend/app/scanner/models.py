from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    CANNOT_SCAN = "CANNOT_SCAN"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Finding:
    check_id: str
    title: str
    provider: str
    account_id: str
    region: str | None
    resource_id: str | None
    status: Status
    severity: Severity
    details: str
