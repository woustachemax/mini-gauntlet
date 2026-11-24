from datetime import UTC, datetime

ADMIN_PORTS = (22, 3389)
INTERNET_CIDRS = ("0.0.0.0/0", "::/0")
TCP = ("tcp", "6")


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def admin_ports_in(low: int, high: int) -> list[int]:
    return [port for port in ADMIN_PORTS if low <= port <= high]


def parse_port_range(text) -> tuple[int, int]:
    text = str(text).strip()
    low, separator, high = text.partition("-")
    if not separator:
        high = low
    try:
        return int(low), int(high)
    except ValueError:
        raise ValueError(f"port {text!r} is not a number or a range") from None


def bool_field(resource: dict, field: str) -> bool:
    value = resource.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} is {value!r}, expected true or false")
    return value


def parse_timestamp(value) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{value!r} is not an ISO 8601 timestamp") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
