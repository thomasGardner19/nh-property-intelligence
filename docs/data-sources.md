# Data sources

This document defines the locked source contracts for the NH Property Intelligence Platform MVP. These source choices should be treated as the baseline for v0.1 unless a later design decision explicitly replaces them.

## Canonical geography design

New Hampshire municipalities will be anchored to the U.S. Census Bureau **county subdivision** geography rather than Census `place` geography.

The canonical municipal identifier will be the Census county-subdivision GEOID, constructed from:

- State FIPS
- County FIPS
- County subdivision FIPS

For New Hampshire, State FIPS is `33`.

The canonical municipal dimension will retain the Census GEOID and standardized municipality/county names. New Hampshire Department of Revenue Administration municipality names will be mapped into this dimension rather than used as primary identifiers.

This design allows the platform to reconcile source-specific naming differences while preserving a stable geography key across sources.

## U.S. Census American Community Survey

### Locked dataset

**2024 ACS 5-Year Detailed Tables**

API dataset path:

`/data/2024/acs/acs5`

### Grain

One record per **New Hampshire county subdivision × ACS vintage**.

County subdivision geography is used as the municipal anchor because it aligns more closely with New Hampshire towns than Census `place` geography.

### Locked variables

| Census variable | Description |
| --- | --- |
| `NAME` | Census geography name |
| `B01003_001E` | Total population estimate |
| `B01003_001M` | Total population margin of error |
| `B19013_001E` | Median household income estimate |
| `B19013_001M` | Median household income margin of error |
| `B25077_001E` | Median owner-occupied home value estimate |
| `B25077_001M` | Median owner-occupied home value margin of error |
| `B25064_001E` | Median gross rent estimate |
| `B25064_001M` | Median gross rent margin of error |
| `B25001_001E` | Total housing units estimate |
| `B25001_001M` | Total housing units margin of error |
| `B25003_001E` | Occupied housing units estimate |
| `B25003_001M` | Occupied housing units margin of error |
| `B25003_002E` | Owner-occupied housing units estimate |
| `B25003_002M` | Owner-occupied housing units margin of error |

The API response must also retain the geography fields returned for:

- `state`
- `county`
- `county subdivision`

The ingestion layer will preserve the ACS vintage, variable identifiers, raw geography name, margins of error, source URL, and ingestion metadata.

## New Hampshire Department of Revenue Administration

### Locked dataset

**2025 Municipal Tax Rates**

### Grain

One record per **municipality × tax year**.

### Expected source fields

The municipal tax-rate ingestion will retain the published municipality name and the following source measures when present:

- Municipality
- Date
- Valuation
- Valuation Including Utilities
- Municipal Tax Rate
- County Tax Rate
- State Education Tax Rate
- Local Education Tax Rate
- Total Tax Rate
- Total Commitment

The source municipality name will be preserved as `municipality_name_raw` and mapped to the canonical Census county-subdivision municipal dimension.

DRA municipality names must not be used as the warehouse primary key.

The ingestion layer must preserve tax year, source file name, source URL, and ingestion timestamp because report layouts and definitions may change between publication years.

## Federal Housing Finance Agency

### Locked dataset

**Annual County House Price Index (HPI)**

### Grain

One record per **county × year**.

The normalized dataset should retain the county identifier and available annual HPI measures, including:

- State code
- County name
- County FIPS
- Year
- Annual appreciation/change
- HPI
- HPI rebased to 1990, when supplied
- HPI rebased to 2000, when supplied

Exact workbook header names will be confirmed programmatically during ingestion and normalized in staging rather than assumed from presentation labels.

### Important semantic constraint

FHFA HPI is **county-level market context** in v0.1.

It must not be represented as municipality- or town-level appreciation. For example, Rockingham County HPI may provide market context for Salem, but it does not constitute a Salem-specific appreciation measure.

Derived measures such as 1-year, 5-year, and 10-year appreciation or CAGR must remain explicitly labeled as county metrics.

If a future version requires municipality-level home-value trends, those should be derived from an appropriate municipality-level source, such as multiple ACS vintages or another validated dataset.

## Source-to-model relationship

The three locked source grains are intentionally different:

- Census ACS: municipality (county subdivision) × vintage
- NH DRA: municipality × tax year
- FHFA: county × year

The warehouse model must preserve these grains rather than forcing all observations into a municipality-level fact table.

The expected dimensional relationship is:

```text
DIM_MUNICIPALITY
    ├── FACT_ACS_HOUSING
    └── FACT_MUNICIPAL_TAX

DIM_COUNTY
    └── FACT_COUNTY_HPI

DIM_MUNICIPALITY
    └── county_key → DIM_COUNTY
```

The municipality scorecard mart may combine town-level Census and DRA measures with clearly labeled county-level FHFA context through the municipality-to-county relationship.
