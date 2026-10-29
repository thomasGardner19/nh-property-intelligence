"""Compare 2–5 municipalities from a local MART_TOWN_SCORECARD CSV (stdlib only)."""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path


class ComparisonError(ValueError):
    """An actionable local input error."""


# These are source columns, not newly calculated indicators.
METRICS = (
    ("Median household income", "median_household_income", "currency"),
    ("Median owner-occupied home value", "median_owner_occupied_home_value", "currency"),
    (
        "Estimated annual property tax on median home",
        "estimated_annual_property_tax_on_median_home",
        "currency",
    ),
    ("Home-value-to-income ratio", "home_value_to_income_ratio", "multiple"),
    ("Estimated property-tax-to-income ratio", "estimated_property_tax_to_income_ratio", "percent"),
    ("FHFA county 5-year cumulative appreciation", "county_hpi_appreciation_5y", "percent"),
    ("ACS 5-year vintage", "acs_vintage", "year"),
    ("DRA tax year", "tax_year", "year"),
    ("FHFA county HPI year", "county_hpi_year", "year"),
)
IDENTITY = ("municipality_geoid", "municipality_name_raw", "county_hpi_county_name_raw")
REQUIRED = (*IDENTITY, *(column for _, column, _ in METRICS))
MISSING = {"", "null", "n/a", "\\n"}
GEOID = re.compile(r"33[0-9]{8}\Z")
CENSUS_NAME = re.compile(
    r"(?P<base>.+) (?P<kind>town|city)"
    r"(?P<context>,\s*[^,]+ county,\s*new hampshire)?\Z"
)


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _aliases(name: str) -> set[str]:
    normalized = _normalized(name)
    aliases = {normalized}
    match = CENSUS_NAME.fullmatch(normalized)
    if match:
        aliases.add(match["base"])
        aliases.add(f"{match['base']} {match['kind']}")
    return aliases


def _cell(value: str) -> str:
    """Keep CSV text inside a single Markdown cell, including untrusted markup."""
    return (
        html.escape(" ".join(value.split()), quote=True)
        .replace("|", "&#124;")
        .replace("`", "&#96;")
        .replace("*", "&#42;")
        .replace("_", "&#95;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("\\", "&#92;")
    )


def _number(value: str, column: str, line: int, kind: str) -> Decimal | None:
    if value.casefold() in MISSING:
        return None
    # Raw machine numbers only: do not infer currency, thousands separators or percent units.
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value):
        raise ComparisonError(f"CSV record {line}: malformed number in {column}.")
    try:
        number = Decimal(value)
        # Bound rendering size and arithmetic; these comfortably exceed scorecard magnitudes.
        if not number.is_finite() or number.copy_abs() > Decimal("1e15"):
            raise InvalidOperation
        if kind == "year" and (number != number.to_integral_value() or not 1000 <= number <= 9999):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise ComparisonError(f"CSV record {line}: invalid number in {column}.") from None
    return number


def _read_scorecard(path: str | Path) -> list[dict[str, str | Decimal | None]]:
    rows: list[dict[str, str | Decimal | None]] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = [column.strip().lower() for column in next(reader, [])]
        if len(header) != len(set(header)):
            raise ComparisonError("CSV contains duplicate column names.")
        missing = sorted(set(REQUIRED) - set(header))
        if missing:
            raise ComparisonError(f"CSV is missing required columns: {', '.join(missing)}.")
        for line, values in enumerate(reader, start=2):
            if len(values) != len(header):
                raise ComparisonError(f"CSV record {line}: column count does not match the header.")
            row: dict[str, str | Decimal | None] = dict(zip(header, map(str.strip, values)))
            geoid = str(row["municipality_geoid"])
            if not GEOID.fullmatch(geoid):
                raise ComparisonError(
                    f"CSV record {line}: municipality_geoid must be a ten-digit NH GEOID."
                )
            if geoid in seen:
                raise ComparisonError(f"CSV contains duplicate municipality_geoid {geoid}.")
            seen.add(geoid)
            if str(row["municipality_name_raw"]).casefold() in MISSING:
                raise ComparisonError(f"CSV record {line}: municipality_name_raw is required.")
            for _, column, kind in METRICS:
                row[column] = _number(str(row[column]), column, line, kind)
            rows.append(row)
    return rows


def _format(value: Decimal | None, kind: str) -> str:
    if value is None:
        return "N/A"
    with localcontext() as context:
        context.prec = 40
        if kind == "currency":
            return f"${value:,.2f}"
        if kind == "percent":
            return f"{value * 100:,.2f}%"
        if kind == "multiple":
            return f"{value:,.2f}×"
        return str(int(value))


def generate_comparison(csv_path: str | Path, towns: Sequence[str]) -> str:
    """Validate the entire CSV and return deterministic Markdown in selection order.

    Select by canonical NH GEOID or normalized name; ambiguous aliases always fail.
    Missing indicators remain N/A. No indicator is recomputed from other columns.
    """
    if isinstance(towns, str) or not 2 <= len(towns) <= 5:
        raise ComparisonError("Select 2–5 distinct municipalities using repeatable --town values.")
    if any(not town.strip() for town in towns):
        raise ComparisonError("Each --town selection must contain a name or canonical GEOID.")
    rows = _read_scorecard(csv_path)
    selected = []
    selected_ids = set()
    for town in towns:
        selector = town.strip()
        matches = [
            row
            for row in rows
            if (
                selector == row["municipality_geoid"]
                if selector.isdecimal()
                else _normalized(selector) in _aliases(str(row["municipality_name_raw"]))
            )
        ]
        if not matches:
            raise ComparisonError(
                "Selection not found. Use a CSV municipality name or exact ten-digit GEOID."
            )
        if len(matches) > 1:
            candidates = ", ".join(str(row["municipality_geoid"]) for row in matches)
            raise ComparisonError(
                f"Ambiguous municipality name. Select an exact GEOID: {candidates}."
            )
        row = matches[0]
        if row["municipality_geoid"] in selected_ids:
            raise ComparisonError("Repeated municipality selection; choose distinct GEOIDs.")
        selected_ids.add(row["municipality_geoid"])
        selected.append(row)

    lines = [
        "# New Hampshire municipality comparison",
        "",
        "| Indicator | "
        + " | ".join(
            f"{_cell(str(row['municipality_name_raw']))} ({row['municipality_geoid']})"
            for row in selected
        )
        + " |",
        "| --- | " + " | ".join("---" for _ in selected) + " |",
    ]
    lines.append(
        "| FHFA county context | "
        + " | ".join(
            "N/A"
            if str(row["county_hpi_county_name_raw"]).casefold() in MISSING
            else _cell(str(row["county_hpi_county_name_raw"]))
            for row in selected
        )
        + " |"
    )
    for label, column, kind in METRICS:
        lines.append(
            f"| {label} | " + " | ".join(_format(row[column], kind) for row in selected) + " |"
        )
    lines.extend(
        [
            "",
            "Source: local MART_TOWN_SCORECARD export; indicators are used as supplied, with display rounding only. N/A means missing in the export.",
            "",
            "Income and home value use Census ACS 5-year estimates. Property tax is an analytical estimate on the median home, not a parcel bill; actual assessments, exemptions and bills can differ.",
            "",
            "FHFA 5-year cumulative appreciation is county-level HPI context, not town appreciation. Ratios show home value as a multiple of income and estimated annual tax as a percentage of income.",
            "",
            "Census ACS vintage, NH DRA tax year and FHFA county HPI year need not align; this comparison does not reconcile their source periods.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="Local scorecard CSV export")
    parser.add_argument(
        "--town", required=True, action="append", help="Name or canonical GEOID (2–5)"
    )
    parser.add_argument(
        "--output", type=Path, help="New Markdown file; existing files are never replaced"
    )
    args = parser.parse_args(argv)
    try:
        report = generate_comparison(args.csv, args.town)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(report)
        else:
            sys.stdout.write(report)
    except FileExistsError:
        print("Error: output file already exists; choose a new --output path.", file=sys.stderr)
        return 2
    except (ComparisonError, csv.Error, UnicodeError, OSError) as error:
        # Never echo CSV cell contents or operating-system paths in diagnostic output.
        message = (
            str(error)
            if isinstance(error, ComparisonError)
            else (
                "Could not read/write local files or parse CSV; check paths, permissions and UTF-8 CSV format."
            )
        )
        print(f"Error: {message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
