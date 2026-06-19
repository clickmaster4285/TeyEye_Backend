#!/usr/bin/env python3
"""Build peshawar-enforcement-disposition.json from tab-separated row files."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
PART_FILES = [
    "disposition_rows_part1.tsv",
    "disposition_rows_part2.tsv",
    "disposition_rows_part3.tsv",
    "disposition_rows_part4.tsv",
]
OUTPUT = DATA_DIR / "peshawar-enforcement-disposition.json"

TITLE = (
    "Disposition list of Assistant/Deputy Collectors of respect of "
    "Collectorate of Customs (Enforcement), Peshawar"
)
ORGANIZATION = {
    "name": "Collectorate of Customs (Enforcement), Peshawar",
    "department": "Enforcement",
    "city": "Peshawar",
}


def parse_row(line: str) -> dict:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 5:
        raise ValueError(f"Expected 5 tab-separated fields, got {len(parts)}: {line!r}")
    s_no, name, father_name, designation, bps = parts
    return {
        "s_no": int(s_no.strip()),
        "name": name.strip(),
        "father_name": father_name.strip(),
        "designation": designation.strip(),
        "bps": str(bps.strip()),
    }


def main() -> None:
    employees: list[dict] = []
    for part in PART_FILES:
        path = DATA_DIR / part
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if not line.strip():
                continue
            employees.append(parse_row(line))

    employees.sort(key=lambda e: e["s_no"])
    expected = list(range(1, len(employees) + 1))
    actual = [e["s_no"] for e in employees]
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        dupes = sorted({n for n in actual if actual.count(n) > 1})
        raise SystemExit(
            f"Serial number check failed: count={len(employees)}, "
            f"missing={missing[:20]}, duplicates={dupes[:20]}"
        )

    payload = {
        "title": TITLE,
        "organization": ORGANIZATION,
        "total_count": len(employees),
        "employees": employees,
    }

    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(employees)} employees to {OUTPUT}")


if __name__ == "__main__":
    main()
