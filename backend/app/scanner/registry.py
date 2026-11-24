from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.scanner.models import Severity, Status

CheckFunction = Callable[[dict, datetime], tuple[Status, str]]


@dataclass(frozen=True)
class Check:
    check_id: str
    title: str
    severity: Severity
    provider: str
    collection: str
    resource_id_field: str
    run: CheckFunction


CHECKS: dict[str, Check] = {}


def check(check_id, title, severity, provider, collection, resource_id_field):
    def register(func: CheckFunction) -> CheckFunction:
        if check_id in CHECKS:
            raise ValueError(f"duplicate check id {check_id}")
        CHECKS[check_id] = Check(
            check_id, title, severity, provider, collection, resource_id_field, func
        )
        return func

    return register


def checks_for(provider: str) -> list[Check]:
    return [c for c in CHECKS.values() if c.provider == provider]
