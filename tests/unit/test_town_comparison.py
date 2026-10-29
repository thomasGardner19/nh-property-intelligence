"""Only synthetic geography identities and fictional indicators are used here."""

import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nh_property_intelligence.town_comparison import ComparisonError, generate_comparison, main

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_town_scorecard.csv"
TOWNS = ["Synthetic Alpha", "Synthetic Beta"]


def modified_csv(tmp_path, *, changes=None, duplicate=False, drop=None, header_case=False):
    with FIXTURE.open(newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        rows = list(reader)
    if changes:
        rows[0].update(changes)
    if duplicate:
        rows.append(rows[0].copy())
    if drop:
        fields.remove(drop)
    path = tmp_path / "synthetic.csv"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow([field.upper() if header_case else field for field in fields])
        writer.writerows([row[field] for field in fields] for row in rows)
    return path


def test_two_towns_formatting_order_and_source_context():
    report = generate_comparison(FIXTURE, TOWNS[::-1])
    assert report.index("Synthetic Beta") < report.index("Synthetic Alpha")
    assert "| Median household income | $125,000.00 | $100,000.00 |" in report
    assert "| Median owner-occupied home value | $625,000.00 | $400,000.00 |" in report
    assert "| Estimated annual property tax on median home | $10,000.00 | $8,000.00 |" in report
    assert "| Home-value-to-income ratio | 5.00× | 4.00× |" in report
    assert "| Estimated property-tax-to-income ratio | 8.00% | 8.00% |" in report
    assert "| FHFA county 5-year cumulative appreciation | 25.00% | 25.00% |" in report
    assert "| ACS 5-year vintage | 2023 | 2023 |" in report
    assert "| DRA tax year | 2024 | 2024 |" in report
    assert "| FHFA county HPI year | 2025 | 2025 |" in report
    assert "Fictional County" in report
    assert "not a parcel bill" in report
    assert "not town appreciation" in report
    assert "need not align" in report
    assert "used as supplied" in report
    assert report.endswith("\n") and "\r" not in report
    assert report == generate_comparison(FIXTURE, TOWNS[::-1])


def test_five_towns():
    report = generate_comparison(FIXTURE, [f"330150000{i}" for i in range(1, 6)])
    assert report.count("(330150000") == 5
    assert "-5.00%" in report and "0.00%" in report and "12.50%" in report


@pytest.mark.parametrize(
    "selector",
    [
        "3301500001",
        "  sYnThEtIc   ALPHA  ",
        "Synthetic Alpha TOWN",
        "Synthetic Alpha town, Fictional County, New Hampshire",
    ],
)
def test_geoid_and_normalized_names(selector):
    assert generate_comparison(FIXTURE, [selector, TOWNS[1]]) == generate_comparison(FIXTURE, TOWNS)


@pytest.mark.parametrize("missing", ["", "NULL", "N/A", "\\N", "   "])
def test_missing_indicators_are_na(tmp_path, missing):
    columns = [
        "median_household_income",
        "median_owner_occupied_home_value",
        "estimated_annual_property_tax_on_median_home",
        "home_value_to_income_ratio",
        "estimated_property_tax_to_income_ratio",
        "county_hpi_appreciation_5y",
        "acs_vintage",
        "tax_year",
        "county_hpi_year",
        "county_hpi_county_name_raw",
    ]
    path = modified_csv(tmp_path, changes=dict.fromkeys(columns, missing))
    report = generate_comparison(path, TOWNS)
    assert report.count("| N/A |") == 10


def test_ambiguous_name_requires_geoid(tmp_path):
    path = modified_csv(
        tmp_path,
        changes={
            "municipality_name_raw": "Synthetic Beta town, Other County, New Hampshire",
        },
    )
    with pytest.raises(ComparisonError, match="Ambiguous.*3301500001.*3301500002"):
        generate_comparison(path, ["Synthetic Beta", "Synthetic Gamma"])
    assert "3301500001" in generate_comparison(path, ["3301500001", "3301500002"])


@pytest.mark.parametrize(
    "towns, message",
    [
        ([], "2–5"),
        ([TOWNS[0]], "2–5"),
        (TOWNS * 3, "2–5"),
        (["", TOWNS[0]], "must contain"),
        (["No such place", TOWNS[0]], "not found"),
        (["Synthetic", TOWNS[0]], "not found"),
        (["330150000", TOWNS[0]], "not found"),
        ([TOWNS[0], "3301500001"], "Repeated"),
        ([TOWNS[0], TOWNS[0]], "Repeated"),
    ],
)
def test_invalid_selections(towns, message):
    with pytest.raises(ComparisonError, match=message):
        generate_comparison(FIXTURE, towns)


def test_duplicate_csv_identity(tmp_path):
    with pytest.raises(ComparisonError, match="duplicate municipality_geoid"):
        generate_comparison(modified_csv(tmp_path, duplicate=True), TOWNS)


@pytest.mark.parametrize(
    "column",
    [
        "municipality_geoid",
        "municipality_name_raw",
        "county_hpi_county_name_raw",
        "acs_vintage",
        "tax_year",
        "county_hpi_year",
        "median_household_income",
        "county_hpi_appreciation_5y",
    ],
)
def test_missing_columns(tmp_path, column):
    with pytest.raises(ComparisonError, match=f"missing required columns: {column}"):
        generate_comparison(modified_csv(tmp_path, drop=column), TOWNS)


@pytest.mark.parametrize(
    "column, value",
    [
        ("median_household_income", "secret-not-a-number"),
        ("median_household_income", "NaN"),
        ("median_household_income", "Infinity"),
        ("median_household_income", "$100,000"),
        ("median_household_income", "1e999999"),
        ("estimated_property_tax_to_income_ratio", "8%"),
        ("county_hpi_appreciation_5y", "bad"),
        ("tax_year", "2024.5"),
        ("municipality_geoid", "330150001"),
        ("municipality_geoid", "9901500001"),
        ("municipality_name_raw", ""),
    ],
)
def test_malformed_cells(tmp_path, column, value):
    with pytest.raises(ComparisonError, match=column):
        generate_comparison(modified_csv(tmp_path, changes={column: value}), TOWNS)


def test_uppercase_snowflake_headers_and_utf8_bom(tmp_path):
    path = modified_csv(tmp_path, header_case=True)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert generate_comparison(path, TOWNS) == generate_comparison(FIXTURE, TOWNS)


def test_values_are_used_without_recalculation(tmp_path):
    path = modified_csv(tmp_path, changes={"home_value_to_income_ratio": "7.25"})
    assert "| Home-value-to-income ratio | 7.25× | 5.00× |" in generate_comparison(path, TOWNS)


def test_markdown_cells_escape_markup(tmp_path):
    name = "<script>|[link](url)*`\\\nmunicipality"
    path = modified_csv(tmp_path, changes={"municipality_name_raw": name})
    report = generate_comparison(path, ["3301500001", "3301500002"])
    assert "<script>" not in report and "[link]" not in report
    assert "&lt;script&gt;&#124;" in report
    assert len(report.splitlines()[2].split("|")) == 5


def cli_args(path=FIXTURE):
    return ["--csv", str(path), "--town", TOWNS[0], "--town", TOWNS[1]]


def test_cli_stdout_and_file_and_no_overwrite(tmp_path, capsys):
    expected = generate_comparison(FIXTURE, TOWNS)
    assert main(cli_args()) == 0
    assert capsys.readouterr().out == expected
    output = tmp_path / "comparison.md"
    assert main(cli_args() + ["--output", str(output)]) == 0
    assert capsys.readouterr().out == ""
    assert output.read_bytes() == expected.encode("utf-8")
    assert main(cli_args() + ["--output", str(output)]) == 2
    assert "already exists" in capsys.readouterr().err
    assert output.read_bytes() == expected.encode("utf-8")
    # An existing source cannot be overwritten either.
    assert main(cli_args() + ["--output", str(FIXTURE)]) == 2


def test_cli_safe_errors_and_no_output_on_failure(tmp_path, capsys):
    path = modified_csv(tmp_path, changes={"median_household_income": "private-cell-content"})
    output = tmp_path / "comparison.md"
    assert main(cli_args(path) + ["--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert "median_household_income" in captured.err
    assert "private-cell-content" not in captured.err
    assert captured.out == "" and not output.exists()
    assert main(cli_args(tmp_path / "missing.csv")) == 2
    assert "Error:" in capsys.readouterr().err
    assert main(cli_args() + ["--output", str(tmp_path / "missing" / "report.md")]) == 2


@pytest.mark.parametrize("content", ["", "a,a\n1,2\n", "bad\xff"])
def test_cli_invalid_files(tmp_path, capsys, content):
    path = tmp_path / "bad.csv"
    path.write_bytes(content.encode("latin-1"))
    assert main(cli_args(path)) == 2
    assert "Error:" in capsys.readouterr().err


def test_cli_malformed_csv_records(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text(FIXTURE.read_text() + '"unterminated\n', encoding="utf-8")
    assert main(cli_args(path)) == 2
    assert "Error:" in capsys.readouterr().err
    path.write_text(FIXTURE.read_text() + "too,few,columns\n", encoding="utf-8")
    assert main(cli_args(path)) == 2
    assert "column count" in capsys.readouterr().err


def test_module_entrypoint():
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "nh_property_intelligence.town_comparison", *cli_args()],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert result.stdout == generate_comparison(FIXTURE, TOWNS)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "nh_property_intelligence.town_comparison",
            "--csv",
            str(FIXTURE),
            "--town",
            "Synthetic Alpha",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode != 0 and "2–5" in result.stderr and result.stdout == ""
