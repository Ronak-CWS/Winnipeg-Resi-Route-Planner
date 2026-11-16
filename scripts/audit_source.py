"""Read the supplied Winnipeg workbook without changing it."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def label(value):
    return "<blank>" if value is None or str(value).strip() == "" else str(value).strip()


def audit(path):
    before = sha256(path)
    book = load_workbook(path, read_only=True, data_only=True)
    sheets = []
    row_sets = {}
    for sheet in book.worksheets:
        iterator = sheet.iter_rows(values_only=True)
        headers = list(next(iterator))
        ids = Counter()
        addresses = Counter()
        columns = [Counter() for _ in headers]
        rows = Counter()
        blank_rows = 0
        incomplete_rows = []
        invalid_collection_day_cells = []
        last_data_row = 1
        for row_number, row in enumerate(iterator, start=2):
            if all(label(value) == "<blank>" for value in row):
                blank_rows += 1
                continue
            last_data_row = row_number
            rows[tuple(row)] += 1
            for counter, value in zip(columns, row):
                counter[label(value)] += 1
            if label(row[0]) != "<blank>":
                ids[label(row[0])] += 1
            if label(row[1]) != "<blank>":
                addresses[label(row[1])] += 1
            if label(row[0]) == "<blank>" or label(row[1]) == "<blank>":
                incomplete_rows.append(row_number)
            for index in (3, 4):
                if label(row[index]) not in {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"}:
                    invalid_collection_day_cells.append({"row": row_number, "column": index + 1,
                                                         "address_id": row[0], "value": row[index]})
        duplicate_ids = {key: count for key, count in ids.items() if count > 1}
        sheets.append({
            "name": sheet.title,
            "headers_raw": headers,
            "worksheet_max_row": sheet.max_row,
            "last_data_row": last_data_row,
            "populated_data_rows": sum(rows.values()),
            "blank_data_rows": blank_rows,
            "unique_address_ids": len(ids),
            "duplicate_address_id_count": len(duplicate_ids),
            "duplicate_address_id_extra_rows": sum(value - 1 for value in duplicate_ids.values()),
            "duplicate_address_ids_sample": dict(list(duplicate_ids.items())[:20]),
            "unique_exact_address_strings": len(addresses),
            "duplicate_exact_address_string_extra_rows": sum(value - 1 for value in addresses.values() if value > 1),
            "duplicate_exact_full_rows": sum(value - 1 for value in rows.values() if value > 1),
            "missing_by_column": {f"{index + 1}:{label(header)}": columns[index]["<blank>"] for index, header in enumerate(headers)},
            "incomplete_identity_row_numbers": incomplete_rows,
            "invalid_collection_day_cells": invalid_collection_day_cells,
            "garbage_collection_day_counts": dict(sorted(columns[3].items())),
            "column_e_counts": dict(sorted(columns[4].items())),
            "yard_waste_cycle_counts": dict(sorted(columns[5].items())),
            "column_e_equals_garbage_day_rows": sum(count for row, count in rows.items() if row[3] == row[4]),
        })
        row_sets[sheet.title] = rows
    book.close()
    monday_expected = Counter({row: count for row, count in row_sets["Sheet1"].items() if label(row[3]).upper() == "MONDAY"})
    monday_actual = row_sets["Monday"]
    expected_ids = Counter()
    actual_ids = Counter()
    for row, count in monday_expected.items():
        expected_ids[row[0]] += count
    for row, count in monday_actual.items():
        actual_ids[row[0]] += count
    after = sha256(path)
    if before != after:
        raise RuntimeError("Source workbook changed during inspection")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(path.resolve()),
        "source_sha256": before,
        "source_size_bytes": path.stat().st_size,
        "source_unchanged_after_read": True,
        "sheets": sheets,
        "monday_reconciliation": {
            "master_monday_rows": sum(monday_expected.values()),
            "monday_sheet_rows": sum(monday_actual.values()),
            "exact_row_multiset_equal": monday_actual == monday_expected,
            "address_id_multiset_equal": actual_ids == expected_ids,
            "monday_rows_not_in_master_monday_subset": sum((monday_actual - monday_expected).values()),
            "master_monday_rows_not_in_monday_sheet": sum((monday_expected - monday_actual).values()),
            "master_differing_rows": [{"address_id": row[0], "garbage_day": row[3], "column_e": row[4], "occurrences": count} for row, count in (monday_expected - monday_actual).items()],
            "monday_differing_rows": [{"address_id": row[0], "garbage_day": row[3], "column_e": row[4], "occurrences": count} for row, count in (monday_actual - monday_expected).items()],
        },
        "interpretation": {
            "sheet1_column_e": "Header is whitespace. Monday labels column E RecyclingCollectionDay. Confirm the master column meaning before adopting it.",
            "counts": "Address rows are not confirmed calls, cart lifts, loads, or route-days. Keep the Monday view separate from the master total.",
            "scope": "Area 1 completeness and included collection streams require operational confirmation.",
            "not_present_in_schema": ["latitude", "longitude", "ASL_or_rear_load", "front_or_rear_collection_access", "Miller_route_id", "cart_counts_and_sizes", "yard_or_receiving_facilities", "truck_capacity"],
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.workbook)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
