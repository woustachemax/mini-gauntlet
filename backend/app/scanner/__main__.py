import logging
import time
from collections import Counter

from app.scanner.engine import load_snapshot, run_scan, score


def escape(text: str) -> str:
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode() for c in text)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    start = time.perf_counter()
    findings = run_scan(load_snapshot())
    elapsed = time.perf_counter() - start

    for f in findings:
        print(
            f"{f.status:<12} {f.severity:<9} {f.check_id:<11} "
            f"{escape(f.account_id):<38} {escape(f.resource_id or '-'):<28} {escape(f.details)}"
        )

    print()
    counts = Counter(f.status for f in findings)
    print(f"Findings: {len(findings)} ({', '.join(f'{s} {n}' for s, n in counts.items())})")
    print(f"Overall score: {score(findings)}")
    for account_id in dict.fromkeys(f.account_id for f in findings):
        account_findings = [f for f in findings if f.account_id == account_id]
        print(f"  {escape(account_id):<38} {score(account_findings)}")
    print(f"Scan took {elapsed:.2f}s")


if __name__ == "__main__":
    main()
