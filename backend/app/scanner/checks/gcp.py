from app.scanner.checks.common import (
    INTERNET_CIDRS,
    TCP,
    admin_ports_in,
    bool_field,
    parse_port_range,
)
from app.scanner.models import Severity, Status
from app.scanner.registry import check

PUBLIC_MEMBERS = ("allUsers", "allAuthenticatedUsers")


@check(
    "GCP-GCS-01", "Bucket isn't public", Severity.HIGH,
    "gcp", "gcs_buckets", "name",
)
def bucket_not_public(bucket, snapshot_time):
    public = []
    for binding in bucket.get("iam_bindings") or []:
        for member in binding.get("members") or []:
            if member in PUBLIC_MEMBERS:
                public.append(f"{member} has {binding.get('role')}")
    if public:
        return Status.FAIL, "bucket is public: " + "; ".join(public)
    return Status.PASS, "no public members in IAM bindings"


@check(
    "GCP-GCS-02", "Bucket uses uniform bucket-level access", Severity.LOW,
    "gcp", "gcs_buckets", "name",
)
def bucket_uniform_access(bucket, snapshot_time):
    if not bool_field(bucket, "uniform_bucket_level_access"):
        return Status.FAIL, "uniform bucket-level access is off"
    return Status.PASS, "uniform bucket-level access is on"


@check(
    "GCP-VPC-01", "Firewall rule doesn't expose SSH or RDP to the internet", Severity.CRITICAL,
    "gcp", "firewall_rules", "name",
)
def firewall_admin_ports(rule, snapshot_time):
    label = f"firewall rule {rule.get('name')}"
    if rule.get("disabled") is True:
        return Status.PASS, f"{label} is disabled"
    direction = str(rule.get("direction"))
    if direction.upper() != "INGRESS":
        return Status.PASS, f"{label} is {direction}, not INGRESS"
    sources = [cidr for cidr in rule.get("source_ranges") or [] if cidr in INTERNET_CIDRS]
    if not sources:
        return Status.PASS, f"{label} isn't open to the internet"

    problems = []
    unreadable = []
    for entry in rule.get("allowed") or []:
        protocol = str(entry.get("IPProtocol")).lower()
        ports = entry.get("ports")
        if protocol == "all" or (protocol in TCP and not ports):
            problems.append(f"{protocol} all ports")
            continue
        if protocol not in TCP:
            continue
        if not isinstance(ports, list):
            unreadable.append(f"ports {ports!r} is not a list")
            continue
        for port in ports:
            try:
                low, high = parse_port_range(port)
            except ValueError as exc:
                unreadable.append(str(exc))
                continue
            if admin_ports_in(low, high):
                problems.append(f"tcp {port}")

    if problems:
        return Status.FAIL, f"{label} allows {', '.join(problems)} from {', '.join(sources)}"
    if unreadable:
        return Status.CANNOT_SCAN, f"{label}: " + "; ".join(unreadable)
    return Status.PASS, f"{label} doesn't open SSH or RDP"
