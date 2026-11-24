from datetime import timedelta

from app.scanner.checks.common import (
    INTERNET_CIDRS,
    TCP,
    admin_ports_in,
    bool_field,
    is_int,
    parse_timestamp,
)
from app.scanner.models import Severity, Status
from app.scanner.registry import check

S3_FLAGS = (
    "block_public_acls",
    "ignore_public_acls",
    "block_public_policy",
    "restrict_public_buckets",
)
MAX_KEY_AGE = timedelta(days=90)


@check(
    "AWS-S3-01",
    "S3 bucket blocks public access",
    Severity.HIGH,
    "aws",
    "s3_buckets",
    "name",
)
def s3_blocks_public_access(bucket, snapshot_time):
    block = bucket.get("public_access_block")
    if block is None:
        return Status.FAIL, "no public access block configured"
    if not isinstance(block, dict):
        return Status.CANNOT_SCAN, f"public_access_block is {block!r}, expected an object"
    off = [flag for flag in S3_FLAGS if block.get(flag) is not True]
    if off:
        return Status.FAIL, "public access block flags false or missing: " + ", ".join(off)
    return Status.PASS, "all four public access block flags are true"


@check(
    "AWS-EC2-01",
    "Security group doesn't expose SSH or RDP to the internet",
    Severity.CRITICAL,
    "aws",
    "security_groups",
    "group_id",
)
def security_group_admin_ports(group, snapshot_time):
    label = f"security group {group.get('group_id')} ({group.get('name')})"
    problems = []
    unreadable = []
    for rule in group.get("ingress") or []:
        protocol = str(rule.get("protocol")).lower()
        from_port = rule.get("from_port")
        to_port = rule.get("to_port")
        all_traffic = protocol == "-1"

        bad = [p for p in (from_port, to_port) if not is_int(p) and not (all_traffic and p is None)]
        if bad:
            unreadable.append(f"port {bad[0]!r} is not an integer")
            continue

        sources = [cidr for cidr in rule.get("cidrs") or [] if cidr in INTERNET_CIDRS]
        if not sources:
            continue

        exposed = admin_ports_in(from_port, to_port) if protocol in TCP else []
        if all_traffic:
            ports = "all protocols and all ports"
        elif exposed and from_port == to_port:
            ports = f"tcp {from_port}"
        elif exposed:
            covered = ", ".join(str(port) for port in exposed)
            ports = f"tcp {from_port}-{to_port} (covers {covered})"
        else:
            continue
        problems.append(f"{ports} open to {', '.join(sources)}")

    if problems:
        return Status.FAIL, f"{label}: " + "; ".join(problems)
    if unreadable:
        return Status.CANNOT_SCAN, f"{label}: " + "; ".join(unreadable)
    return Status.PASS, f"{label}: no SSH or RDP open to the internet"


@check(
    "AWS-IAM-01",
    "Console users have MFA",
    Severity.HIGH,
    "aws",
    "iam_users",
    "user_name",
)
def console_users_have_mfa(user, snapshot_time):
    if not bool_field(user, "console_access"):
        return Status.PASS, "no console access"
    if not bool_field(user, "mfa_enabled"):
        return Status.FAIL, "console access without MFA"
    return Status.PASS, "console access with MFA"


@check(
    "AWS-IAM-02",
    "No active access key is older than 90 days",
    Severity.MEDIUM,
    "aws",
    "iam_users",
    "user_name",
)
def access_keys_not_old(user, snapshot_time):
    old = []
    for key in user.get("access_keys") or []:
        if key.get("status") != "Active":
            continue
        age = snapshot_time - parse_timestamp(key.get("created_at"))
        if age > MAX_KEY_AGE:
            old.append(f"{key.get('key_id')} is {age.days} days old")
    if old:
        return Status.FAIL, "active access keys older than 90 days: " + "; ".join(old)
    return Status.PASS, "no active access key older than 90 days"


@check(
    "AWS-RDS-01",
    "RDS instance isn't publicly accessible",
    Severity.HIGH,
    "aws",
    "rds_instances",
    "db_instance_id",
)
def rds_not_public(instance, snapshot_time):
    if bool_field(instance, "publicly_accessible"):
        return Status.FAIL, "instance is publicly accessible"
    return Status.PASS, "instance is not publicly accessible"
