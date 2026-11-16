from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from .days import day_in_label, normalize_day

MAX_ROWS = 120_000
MAX_BYTES = 30 * 1024 * 1024
ALIASES = {
    "id": ["addressid", "serviceid", "id"],
    "address": ["combinedaddress", "fulladdress", "address", "streetaddress"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng", "long"],
    "day": ["collectionday", "serviceday", "weekday", "day", "partitioncollectionday", "garbagecollectionday", "garbageday", "recyclingcollectionday", "recyclingday"],
    "quality": ["coordinatestatus", "coordinatequality", "locationstatus"],
    "site": ["siteid", "mustlinkid", "buildingid"],
    "access": ["collectionaccess", "pickupaccess", "collectionlocationtype"],
}


class InputError(ValueError):
    def __init__(self, message, errors=None, *, available_days=None, available_sheets=None):
        super().__init__(message)
        self.errors = errors or []
        self.available_days = available_days or {}
        self.available_sheets = available_sheets or []


def token(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@dataclass
class Dataset:
    rows: list[dict]
    columns: list[str]
    source: str
    sheet: str
    excluded: int
    warnings: list[str]
    mapping: dict
    day: str = "MONDAY"
    day_source: str = "column"
    available_days: dict = field(default_factory=dict)

    @property
    def digest(self):
        # Cached exports include original order, source-row numbers and mapping.
        # Geometry is order-independent, but its upload/export receipt is not.
        data = {"source":self.source,"sheet":self.sheet,"columns":self.columns,
                "mapping":self.mapping,"excluded":self.excluded,"warnings":self.warnings,"rows":self.rows,
                "day":self.day,"day_source":self.day_source,"available_days":self.available_days}
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def preview(self):
        return {"source": self.source, "sheet": self.sheet, "count": len(self.rows),
                "day": self.day, "day_source": self.day_source, "available_days": self.available_days,
                "excluded": self.excluded, "columns": self.columns, "mapping": self.mapping,
                "warnings": self.warnings, "coordinate_status": dict(Counter(row["quality"] for row in self.rows)),
                "distinct_coordinates": len({(r["lat"], r["lon"]) for r in self.rows}),
                "preview": [{"id": r["id"], "address": r["address"], "lat": r["lat"], "lon": r["lon"], "quality": r["quality"]} for r in self.rows[:6]]}


def select_sheet(workbook, name, selected_day):
    candidates = []
    for title in workbook.sheetnames:
        if any(any(token(v) in ALIASES["latitude"] for v in row)
               and any(token(v) in ALIASES["longitude"] for v in row)
               for row in workbook[title].iter_rows(max_row=25, values_only=True)):
            candidates.append(title)
    candidates = candidates or workbook.sheetnames
    hint = selected_day or day_in_label(Path(name).stem)
    matching = [title for title in candidates if day_in_label(title) == hint] if hint else []
    named_days = [title for title in candidates if day_in_label(title)]
    if len(matching) == 1:
        return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    if not hint and len(named_days) == 1:
        return named_days[0]
    raise InputError("This workbook has multiple address sheets. Choose an Excel sheet in Upload options; sheets are never combined.",
                     available_sheets=candidates)


def parse_upload(content: bytes, name: str, mapping=None, sheet="", confirm_monday=False, collection_day="") -> Dataset:
    if len(content) > MAX_BYTES:
        raise InputError("Upload is too large. The local limit is 30 MiB.")
    suffix = Path(name).suffix.lower()
    selected_day = normalize_day(collection_day)
    if collection_day and not selected_day:
        raise InputError("Choose a valid collection day.")
    sheet_used = ""
    if suffix in {".csv", ".tsv"}:
        try:
            source = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            source = content.decode("cp1252")
        try:
            dialect = csv.Sniffer().sniff(source[:8192], delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel_tab if suffix == ".tsv" else csv.excel
        # Sniffer cannot infer escaped quotes from a sample containing none.
        # Excel/RFC CSV uses doubled quotes even when they first occur much later
        # (the user's DMS provenance note is one such row).
        dialect.doublequote = True
        indexed = [(i, row) for i, row in enumerate(csv.reader(io.StringIO(source), dialect), 1) if any(text(v) for v in row)]
        source_numbers = [i for i, _ in indexed]
        matrix = [row for _, row in indexed]
    elif suffix == ".xlsx":
        workbook = None
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 300 * 1024 * 1024:
                    raise InputError("This workbook expands beyond the 300 MiB local limit.")
            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            if sheet:
                if sheet not in workbook.sheetnames:
                    raise InputError(f"Sheet {sheet!r} is not in this workbook.")
                sheet_used = sheet
            else:
                sheet_used = select_sheet(workbook, name, selected_day)
            matrix = []
            source_numbers = []
            for source_number, row in enumerate(workbook[sheet_used].iter_rows(values_only=True), 1):
                if any(text(v) for v in row):
                    matrix.append(list(row))
                    source_numbers.append(source_number)
                if len(matrix) > MAX_ROWS + 30:
                    raise InputError("A sheet may contain at most 120,000 address rows.")
        except InputError:
            raise
        except Exception as exc:
            raise InputError("Could not read this .xlsx workbook. Save a CSV or a normal .xlsx and try again.") from exc
        finally:
            if workbook is not None:
                workbook.close()
    else:
        raise InputError("Upload a .csv, .tsv or .xlsx file with latitude and longitude.")
    if not matrix:
        raise InputError("The selected file or sheet is empty.")
    # Handles both a normal CSV header and the delivered Monday workbook's title/summary rows.
    header_index = next((i for i, row in enumerate(matrix[:25])
                         if any(token(c) in ALIASES["latitude"] for c in row)
                         and any(token(c) in ALIASES["longitude"] for c in row)), 0)
    columns = [text(c) or f"Column{j + 1}" for j, c in enumerate(matrix[header_index])]
    if len(set(columns)) != len(columns):
        raise InputError("Column headers must be unique.")
    lookup = {token(c): c for c in columns}
    resolved = {}
    for field, aliases in ALIASES.items():
        resolved[field] = (mapping or {}).get(field) or next((lookup[a] for a in aliases if a in lookup), "")
        if resolved[field] and resolved[field] not in columns:
            raise InputError(f"Mapped column {resolved[field]!r} does not exist.")
    if not resolved["latitude"] or not resolved["longitude"]:
        raise InputError("Latitude and Longitude columns are required.", [{"row": "header", "message": "Recognised names: Latitude/Lat and Longitude/Lon/Lng. Rename columns or supply a column mapping."}])
    body = matrix[header_index + 1:]
    if len(body) > MAX_ROWS:
        raise InputError("The selected file may contain at most 120,000 address rows.")
    rows, errors, warnings = [], [], []
    day_counts = Counter()
    if resolved["day"]:
        column = columns.index(resolved["day"])
        for values in body:
            day = normalize_day(values[column] if column < len(values) else "")
            if day:
                day_counts[day] += 1
        if selected_day:
            selected = selected_day
        elif len(day_counts) == 1:
            selected = next(iter(day_counts))
        elif len(day_counts) > 1:
            raise InputError("This file contains multiple collection days. Choose a collection day in Upload options to partition one day at a time.",
                             available_days=dict(day_counts))
        else:
            raise InputError("The collection-day column has no recognised weekdays. Use Monday through Sunday or their abbreviations.")
        day_source = "column"
        hint = day_in_label(sheet_used) or day_in_label(Path(name).stem)
        if hint and hint != selected:
            warnings.append(f"Using {selected.title()} from the collection-day column; the file or worksheet name suggests {hint.title()}.")
    else:
        selected = selected_day or day_in_label(sheet_used) or day_in_label(Path(name).stem) or ("MONDAY" if confirm_monday else "")
        if not selected:
            raise InputError("No collection day was found in the rows, worksheet or filename. Choose a collection day in Upload options to confirm this file's day.")
        day_source = "selection" if selected_day or confirm_monday else "worksheet" if day_in_label(sheet_used) else "filename"
        day_counts[selected] = len(body)
    ids = set()
    excluded = 0
    for offset, values in enumerate(body, header_index + 1):
        number = source_numbers[offset]
        raw = {key: (values[j] if isinstance(values[j], str) else text(values[j])) if j < len(values) else "" for j, key in enumerate(columns)}
        get = lambda field: raw.get(resolved[field], "").strip()
        if resolved["day"]:
            day = normalize_day(get("day"))
            if not day:
                errors.append({"row": number, "message": f"Collection day {get('day')!r} is blank or unrecognised."})
                continue
            if day != selected:
                excluded += 1
                continue
        identity = get("id") if resolved["id"] else f"ROW-{number:06d}"
        try:
            lat, lon = float(get("latitude")), float(get("longitude"))
        except (ValueError, TypeError):
            errors.append({"row": number, "id": identity, "message": "Latitude and longitude must both be numbers."})
            continue
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            errors.append({"row": number, "id": identity, "message": "Coordinates are not finite WGS 84 latitude/longitude."})
            continue
        if not (49.65 <= lat <= 50.1 and -97.6 <= lon <= -96.85):
            errors.append({"row": number, "id": identity, "message": "Outside the frozen Winnipeg geography. Check swapped coordinates or location."})
            continue
        if not identity or identity in ids:
            errors.append({"row": number, "id": identity, "message": "AddressId is blank or duplicated. Distinct services need distinct IDs; no rows are merged."})
            continue
        ids.add(identity)
        quality = get("quality") or "Uploaded coordinate"
        estimated = any(word in quality.lower() for word in ("approx", "estimat", "interpolat", "placeholder", "display only"))
        access_value = token(get("access"))
        access = "alley" if access_value in {"alley", "backalley", "laneway"} else "curbside" if access_value in {"curbside", "frontstreet", "curb"} else "unknown"
        rows.append({"id": identity, "address": get("address") or identity, "lat": lat, "lon": lon,
                     "quality": quality, "trusted": not estimated, "site": get("site"), "access": access, "source_row": number, "raw": raw,
                     "day": selected})
    if errors:
        raise InputError(f"Fix {len(errors):,} invalid {selected.title()} row(s) before partitioning. No partial input was accepted.", errors[:100])
    if not rows:
        raise InputError(f"No {selected.title()} address rows remain in this file. Check the selected collection day.", available_days=dict(day_counts))
    if not any(r["trusted"] for r in rows):
        raise InputError("At least one reliable coordinate is required. Estimated points cannot create boundaries.")
    if not resolved["id"]:
        warnings.append("No AddressId column: stable source-row IDs were generated. Original rows remain separate.")
    if excluded:
        warnings.append(f"Selected {selected.title()}; excluded {excluded:,} rows for other collection days.")
    if any(not r["trusted"] for r in rows):
        warnings.append("Estimated points will be assigned after geographic boundaries are fixed.")
    if not resolved["quality"]:
        warnings.append("Uploaded coordinates have not been independently validated as property or pickup positions.")
    return Dataset(rows, columns, Path(name).name, sheet_used, excluded, warnings, resolved,
                   selected, day_source, dict(day_counts))

