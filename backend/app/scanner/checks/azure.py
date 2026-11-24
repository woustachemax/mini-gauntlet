from app.scanner.checks.common import admin_ports_in, bool_field, parse_port_range
from app.scanner.models import Severity, Status
from app.scanner.registry import check

INTERNET_SOURCES = ("*", "internet", "any", "0.0.0.0/0", "::/0")


def port_ranges(value) -> list[tuple[int, int]]:
    if not isinstance(value, str):
        raise ValueError(f"destination_ports {value!r} is not a string")
    if value.strip() == "*":
        return [(0, 65535)]
    return [parse_port_range(part) for part in value.split(",")]


@check(
    "AZ-STG-01",
    "Storage account blocks public blob access",
    Severity.HIGH,
    "azure",
    "storage_accounts",
    "name",
)
def storage_blocks_public_blobs(account, snapshot_time):
    if bool_field(account, "allow_blob_public_access"):
        return Status.FAIL, "storage account allows public blob access"
    return Status.PASS, "public blob access is disabled"


@check(
    "AZ-NSG-01",
    "NSG doesn't expose SSH or RDP to the internet",
    Severity.CRITICAL,
    "azure",
    "network_security_groups",
    "name",
)
def nsg_admin_ports(nsg, snapshot_time):
    label = f"NSG {nsg.get('name')}"
    problems = []
    unreadable = []
    for rule in nsg.get("rules") or []:
        if str(rule.get("direction")).lower() != "inbound":
            continue
        if str(rule.get("access")).lower() != "allow":
            continue
        source = str(rule.get("source"))
        if source.strip().lower() not in INTERNET_SOURCES:
            continue
        protocol = str(rule.get("protocol"))
        if protocol.lower() not in ("tcp", "*"):
            continue

        ports = rule.get("destination_ports")
        try:
            ranges = port_ranges(ports)
        except ValueError as exc:
            unreadable.append(f"rule {rule.get('name')}: {exc}")
            continue

        exposed = sorted({port for low, high in ranges for port in admin_ports_in(low, high)})
        if exposed:
            covered = ", ".join(str(port) for port in exposed)
            problems.append(
                f"rule {rule.get('name')} allows {protocol} ports {ports} "
                f"(covers {covered}) from {source}"
            )

    if problems:
        return Status.FAIL, f"{label}: " + "; ".join(problems)
    if unreadable:
        return Status.CANNOT_SCAN, f"{label}: " + "; ".join(unreadable)
    return Status.PASS, f"{label}: no SSH or RDP open to the internet"
