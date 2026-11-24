from datetime import UTC, datetime, timedelta

import pytest

from app.scanner.engine import evaluate
from app.scanner.models import Status
from app.scanner.registry import CHECKS

SNAPSHOT = datetime(2026, 10, 1, tzinfo=UTC)
ACCOUNT = {"account_id": "test-account"}


def run(check_id, resource):
    finding = evaluate(CHECKS[check_id], ACCOUNT, resource, SNAPSHOT)
    return finding.status, finding.details


def test_all_ten_checks_are_registered():
    assert sorted(CHECKS) == [
        "AWS-EC2-01",
        "AWS-IAM-01",
        "AWS-IAM-02",
        "AWS-RDS-01",
        "AWS-S3-01",
        "AZ-NSG-01",
        "AZ-STG-01",
        "GCP-GCS-01",
        "GCP-GCS-02",
        "GCP-VPC-01",
    ]


# AWS-S3-01


def bucket(**flags):
    block = {
        "block_public_acls": True,
        "ignore_public_acls": True,
        "block_public_policy": True,
        "restrict_public_buckets": True,
    }
    block.update(flags)
    return {"name": "b1", "public_access_block": block}


def test_s3_all_flags_true_passes():
    assert run("AWS-S3-01", bucket())[0] is Status.PASS


def test_s3_false_flags_fail_and_are_named():
    status, details = run("AWS-S3-01", bucket(block_public_acls=False, ignore_public_acls=False))
    assert status is Status.FAIL
    assert "block_public_acls" in details
    assert "ignore_public_acls" in details
    assert "block_public_policy" not in details


def test_s3_null_block_fails():
    status, details = run("AWS-S3-01", {"name": "b1", "public_access_block": None})
    assert status is Status.FAIL
    assert details == "no public access block configured"


def test_s3_missing_flag_fails():
    resource = bucket()
    del resource["public_access_block"]["restrict_public_buckets"]
    status, details = run("AWS-S3-01", resource)
    assert status is Status.FAIL
    assert "restrict_public_buckets" in details


def test_s3_block_that_is_not_an_object_cannot_scan():
    assert run("AWS-S3-01", {"name": "b1", "public_access_block": "yes"})[0] is Status.CANNOT_SCAN


# AWS-EC2-01


def group(*rules):
    return {"group_id": "sg-1", "name": "test-group", "ingress": list(rules)}


def rule(protocol="tcp", from_port=22, to_port=22, cidrs=("0.0.0.0/0",)):
    return {"protocol": protocol, "from_port": from_port, "to_port": to_port, "cidrs": list(cidrs)}


def test_ec2_ssh_from_internet_fails_with_details():
    status, details = run("AWS-EC2-01", group(rule()))
    assert status is Status.FAIL
    assert "sg-1" in details
    assert "test-group" in details
    assert details == "security group sg-1 (test-group): tcp 22 open to 0.0.0.0/0"


def test_ec2_ssh_from_ipv6_internet_fails():
    status, details = run("AWS-EC2-01", group(rule(cidrs=["::/0"])))
    assert status is Status.FAIL
    assert "::/0" in details


@pytest.mark.parametrize(
    ("from_port", "to_port", "expected"),
    [
        (3000, 3500, Status.FAIL),
        (3389, 3389, Status.FAIL),
        (20, 22, Status.FAIL),
        (22, 25, Status.FAIL),
        (0, 65535, Status.FAIL),
        (8000, 9000, Status.PASS),
        (23, 3388, Status.PASS),
        (443, 443, Status.PASS),
    ],
)
def test_ec2_port_ranges_are_inclusive(from_port, to_port, expected):
    assert run("AWS-EC2-01", group(rule(from_port=from_port, to_port=to_port)))[0] is expected


def test_ec2_range_details_name_the_covered_port():
    status, details = run("AWS-EC2-01", group(rule(from_port=3000, to_port=3500)))
    assert status is Status.FAIL
    assert "tcp 3000-3500 (covers 3389)" in details


def test_ec2_protocol_minus_one_with_null_ports_fails():
    status, details = run("AWS-EC2-01", group(rule(protocol="-1", from_port=None, to_port=None)))
    assert status is Status.FAIL
    assert "all protocols and all ports" in details


def test_ec2_udp_cannot_expose_ssh():
    assert run("AWS-EC2-01", group(rule(protocol="udp")))[0] is Status.PASS


def test_ec2_private_source_passes():
    assert run("AWS-EC2-01", group(rule(cidrs=["10.0.0.0/8"])))[0] is Status.PASS


def test_ec2_no_ingress_rules_passes():
    assert run("AWS-EC2-01", group())[0] is Status.PASS


@pytest.mark.parametrize(
    ("protocol", "from_port", "to_port"),
    [
        ("tcp", "twenty-two", 22),
        ("tcp", 22, None),
        ("tcp", True, 22),
        ("-1", "all", None),
    ],
)
def test_ec2_non_integer_port_cannot_scan(protocol, from_port, to_port):
    resource = group(rule(protocol=protocol, from_port=from_port, to_port=to_port))
    status, details = run("AWS-EC2-01", resource)
    assert status is Status.CANNOT_SCAN
    assert "is not an integer" in details


def test_ec2_real_exposure_beats_an_unreadable_rule():
    resource = group(rule(from_port="twenty-two"), rule(from_port=3389, to_port=3389))
    assert run("AWS-EC2-01", resource)[0] is Status.FAIL


# AWS-IAM-01


def user(**fields):
    return {"user_name": "u1", "console_access": True, "mfa_enabled": True, **fields}


def test_iam_console_user_with_mfa_passes():
    assert run("AWS-IAM-01", user())[0] is Status.PASS


def test_iam_console_user_without_mfa_fails():
    assert run("AWS-IAM-01", user(mfa_enabled=False))[0] is Status.FAIL


def test_iam_user_without_console_cannot_fail():
    assert run("AWS-IAM-01", user(console_access=False, mfa_enabled=False))[0] is Status.PASS


def test_iam_non_boolean_console_access_cannot_scan():
    status, details = run("AWS-IAM-01", user(console_access="yes"))
    assert status is Status.CANNOT_SCAN
    assert "console_access" in details


# AWS-IAM-02


def key(age, status="Active", key_id="key-1"):
    created = (SNAPSHOT - age).isoformat().replace("+00:00", "Z")
    return {"key_id": key_id, "status": status, "created_at": created}


def keys_user(*keys):
    return {"user_name": "u1", "access_keys": list(keys)}


def test_iam_key_exactly_90_days_old_passes():
    assert run("AWS-IAM-02", keys_user(key(timedelta(days=90))))[0] is Status.PASS


def test_iam_key_91_days_old_fails_with_id_and_age():
    status, details = run("AWS-IAM-02", keys_user(key(timedelta(days=91))))
    assert status is Status.FAIL
    assert "key-1" in details
    assert "91 days" in details


def test_iam_key_just_over_90_days_fails():
    assert run("AWS-IAM-02", keys_user(key(timedelta(days=90, hours=1))))[0] is Status.FAIL


def test_iam_inactive_old_key_is_ignored():
    assert run("AWS-IAM-02", keys_user(key(timedelta(days=900), "Inactive")))[0] is Status.PASS


def test_iam_only_the_active_old_key_is_reported():
    resource = keys_user(
        key(timedelta(days=320), key_id="active-key"),
        key(timedelta(days=900), "Inactive", key_id="inactive-key"),
    )
    status, details = run("AWS-IAM-02", resource)
    assert status is Status.FAIL
    assert "active-key is 320 days old" in details
    assert "inactive-key" not in details


def test_iam_user_without_keys_passes():
    assert run("AWS-IAM-02", keys_user())[0] is Status.PASS


def test_iam_bad_created_at_cannot_scan():
    bad_key = {"key_id": "key-1", "status": "Active", "created_at": "last tuesday"}
    status, details = run("AWS-IAM-02", keys_user(bad_key))
    assert status is Status.CANNOT_SCAN
    assert "last tuesday" in details


# AWS-RDS-01


def test_rds_private_instance_passes():
    resource = {"db_instance_id": "db1", "publicly_accessible": False}
    assert run("AWS-RDS-01", resource)[0] is Status.PASS


def test_rds_public_instance_fails():
    resource = {"db_instance_id": "db1", "publicly_accessible": True}
    assert run("AWS-RDS-01", resource)[0] is Status.FAIL


def test_rds_missing_field_cannot_scan():
    assert run("AWS-RDS-01", {"db_instance_id": "db1"})[0] is Status.CANNOT_SCAN


# AZ-STG-01


def test_storage_blocking_public_blobs_passes():
    resource = {"name": "st1", "allow_blob_public_access": False}
    assert run("AZ-STG-01", resource)[0] is Status.PASS


def test_storage_allowing_public_blobs_fails():
    resource = {"name": "st1", "allow_blob_public_access": True}
    assert run("AZ-STG-01", resource)[0] is Status.FAIL


def test_storage_non_boolean_field_cannot_scan():
    resource = {"name": "st1", "allow_blob_public_access": "false"}
    assert run("AZ-STG-01", resource)[0] is Status.CANNOT_SCAN


# AZ-NSG-01


def nsg(*rules):
    return {"name": "nsg-1", "rules": list(rules)}


def nsg_rule(**fields):
    defaults = {
        "name": "r1",
        "direction": "Inbound",
        "access": "Allow",
        "protocol": "Tcp",
        "source": "*",
        "destination_ports": "22",
    }
    return {**defaults, **fields}


def test_nsg_ssh_from_anywhere_fails_with_details():
    status, details = run("AZ-NSG-01", nsg(nsg_rule()))
    assert status is Status.FAIL
    assert "nsg-1" in details
    assert "r1" in details
    assert details == "NSG nsg-1: rule r1 allows Tcp ports 22 from *"


def test_nsg_range_details_name_the_covered_port():
    status, details = run("AZ-NSG-01", nsg(nsg_rule(destination_ports="3380-3400")))
    assert status is Status.FAIL
    assert details == "NSG nsg-1: rule r1 allows Tcp ports 3380-3400 (covers 3389) from *"


@pytest.mark.parametrize("source", ["*", "Internet", "INTERNET", "any", "Any", "0.0.0.0/0", "::/0"])
def test_nsg_internet_sources_fail(source):
    assert run("AZ-NSG-01", nsg(nsg_rule(source=source)))[0] is Status.FAIL


@pytest.mark.parametrize("source", ["10.0.0.0/8", "VirtualNetwork", "203.0.113.5"])
def test_nsg_other_sources_pass(source):
    assert run("AZ-NSG-01", nsg(nsg_rule(source=source)))[0] is Status.PASS


def test_nsg_deny_rule_passes():
    assert run("AZ-NSG-01", nsg(nsg_rule(access="Deny")))[0] is Status.PASS


def test_nsg_outbound_rule_passes():
    assert run("AZ-NSG-01", nsg(nsg_rule(direction="Outbound")))[0] is Status.PASS


@pytest.mark.parametrize(
    ("protocol", "expected"),
    [("Tcp", Status.FAIL), ("*", Status.FAIL), ("Udp", Status.PASS), ("Icmp", Status.PASS)],
)
def test_nsg_protocols(protocol, expected):
    assert run("AZ-NSG-01", nsg(nsg_rule(protocol=protocol)))[0] is expected


@pytest.mark.parametrize(
    ("ports", "expected"),
    [
        ("*", Status.FAIL),
        ("3389", Status.FAIL),
        ("3380-3400", Status.FAIL),
        ("80,443,3389", Status.FAIL),
        ("80, 22", Status.FAIL),
        ("8000-9000", Status.PASS),
        ("80,443", Status.PASS),
        ("23-3388", Status.PASS),
    ],
)
def test_nsg_destination_ports(ports, expected):
    assert run("AZ-NSG-01", nsg(nsg_rule(destination_ports=ports)))[0] is expected


@pytest.mark.parametrize("ports", ["ssh", "22-", "", 22])
def test_nsg_unreadable_ports_cannot_scan(ports):
    status, details = run("AZ-NSG-01", nsg(nsg_rule(destination_ports=ports)))
    assert status is Status.CANNOT_SCAN
    assert "r1" in details


# GCP-GCS-01


def gcs_bucket(*bindings, uniform=True):
    return {"name": "gb1", "uniform_bucket_level_access": uniform, "iam_bindings": list(bindings)}


@pytest.mark.parametrize("member", ["allUsers", "allAuthenticatedUsers"])
def test_gcs_public_member_fails_with_role_and_member(member):
    binding = {"role": "roles/storage.objectViewer", "members": [member, "user:a@example.com"]}
    status, details = run("GCP-GCS-01", gcs_bucket(binding))
    assert status is Status.FAIL
    assert f"{member} has roles/storage.objectViewer" in details


def test_gcs_private_bucket_passes():
    binding = {"role": "roles/storage.objectAdmin", "members": ["group:eng@example.com"]}
    assert run("GCP-GCS-01", gcs_bucket(binding))[0] is Status.PASS


def test_gcs_bucket_without_bindings_passes():
    assert run("GCP-GCS-01", gcs_bucket())[0] is Status.PASS


def test_gcs_malformed_binding_cannot_scan():
    assert run("GCP-GCS-01", gcs_bucket("not-a-binding"))[0] is Status.CANNOT_SCAN


# GCP-GCS-02


def test_gcs_uniform_access_on_passes():
    assert run("GCP-GCS-02", gcs_bucket(uniform=True))[0] is Status.PASS


def test_gcs_uniform_access_off_fails():
    assert run("GCP-GCS-02", gcs_bucket(uniform=False))[0] is Status.FAIL


def test_gcs_uniform_access_missing_cannot_scan():
    assert run("GCP-GCS-02", {"name": "gb1"})[0] is Status.CANNOT_SCAN


# GCP-VPC-01


def firewall(**fields):
    defaults = {
        "name": "fw-1",
        "direction": "INGRESS",
        "disabled": False,
        "source_ranges": ["0.0.0.0/0"],
        "allowed": [{"IPProtocol": "tcp", "ports": ["22"]}],
    }
    return {**defaults, **fields}


def test_vpc_ssh_from_internet_fails_with_details():
    status, details = run("GCP-VPC-01", firewall())
    assert status is Status.FAIL
    assert "fw-1" in details
    assert "tcp 22" in details
    assert "0.0.0.0/0" in details


def test_vpc_ipv6_source_fails():
    assert run("GCP-VPC-01", firewall(source_ranges=["::/0"]))[0] is Status.FAIL


def test_vpc_disabled_rule_passes():
    assert run("GCP-VPC-01", firewall(disabled=True))[0] is Status.PASS


def test_vpc_egress_rule_passes():
    resource = firewall(direction="EGRESS", destination_ranges=["0.0.0.0/0"])
    del resource["source_ranges"]
    assert run("GCP-VPC-01", resource)[0] is Status.PASS


def test_vpc_restricted_source_passes():
    assert run("GCP-VPC-01", firewall(source_ranges=["35.235.240.0/20"]))[0] is Status.PASS


@pytest.mark.parametrize(
    ("allowed", "expected"),
    [
        ([{"IPProtocol": "all"}], Status.FAIL),
        ([{"IPProtocol": "tcp"}], Status.FAIL),
        ([{"IPProtocol": "tcp", "ports": []}], Status.FAIL),
        ([{"IPProtocol": "tcp", "ports": ["3389"]}], Status.FAIL),
        ([{"IPProtocol": "tcp", "ports": ["3000-3500"]}], Status.FAIL),
        ([{"IPProtocol": "tcp", "ports": ["80", "443"]}], Status.PASS),
        ([{"IPProtocol": "tcp", "ports": ["8000-9000"]}], Status.PASS),
        ([{"IPProtocol": "udp", "ports": ["22"]}], Status.PASS),
        ([{"IPProtocol": "udp"}], Status.PASS),
    ],
)
def test_vpc_allowed_entries(allowed, expected):
    assert run("GCP-VPC-01", firewall(allowed=allowed))[0] is expected


@pytest.mark.parametrize("ports", [["twenty-two"], "22"])
def test_vpc_unreadable_ports_cannot_scan(ports):
    allowed = [{"IPProtocol": "tcp", "ports": ports}]
    assert run("GCP-VPC-01", firewall(allowed=allowed))[0] is Status.CANNOT_SCAN
