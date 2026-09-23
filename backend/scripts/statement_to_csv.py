"""Convert a supported bank statement into Aurum's normalized review CSV.

The command is deliberately local: document bytes never leave the machine.
Run from backend/: python -m scripts.statement_to_csv statement.pdf output.csv
"""
import argparse
import csv
from pathlib import Path

from fastapi import HTTPException

from app.importers import resolve_importers

FIELDS = (
    "source_row",
    "date",
    "type",
    "amount",
    "account_currency",
    "transaction_amount",
    "currency",
    "description",
    "details",
    "purpose",
    "importable",
    "warning",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a supported bank statement to normalized CSV")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-skipped", action="store_true")
    args = parser.parse_args()

    candidates = resolve_importers(args.input.name)
    if not candidates:
        parser.error("unsupported input extension")
    errors: list[str] = []
    preview = None
    content = args.input.read_bytes()
    for importer in candidates:
        try:
            preview = importer.parse(args.input.name, content)
            break
        except HTTPException as exc:
            if exc.status_code != 422:
                raise
            errors.append(str(exc.detail))
    if preview is None:
        parser.error("statement format was not recognized: " + "; ".join(errors))

    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for row in preview.rows:
            if not row.importable and not args.include_skipped:
                continue
            data = row.model_dump(mode="json")
            writer.writerow({field: data.get(field) for field in FIELDS})
    print(f"{preview.provider}: wrote {sum(row.importable or args.include_skipped for row in preview.rows)} rows")
    for warning in preview.warnings:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
