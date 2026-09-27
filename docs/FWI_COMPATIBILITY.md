# FWI dataset compatibility review

Reviewed repository commit `971491084b5093f12cf2a32b0c7718c00323f4b0` (v3 data,
June 2021–August 2026). Source: [Fish Welfare Initiative](https://github.com/fish-welfare-initiative/fwi-farm-data-india).
Data license: **CC-BY-4.0**. Attribution: Fish Welfare Initiative (2026),
*FWI Farm Data — India (June 2021–August 2026)*. The original downloads and license
are in the ignored `data/fwi-source` directory on this machine.

The original Pondwise schema could not safely ingest these CSVs as daily records.
The updated app imports all four files into versioned research tables, preserves
every original column/value, and provides water-quality trends and chatbot evidence
from a selected snapshot. It does not claim that research data establishes a complete
farm inventory, FCR, financial performance or causal intervention effects.

| Source | Verified rows | Required distinction / application support |
| --- | ---: | --- |
| water_quality.csv | 13,567 | Multiple pond visits per day; exact times, morning/evening, follow-ups, equipment, water chemistry and corrective actions preserved. Typed water metrics support trends. |
| enrolled_ponds.csv | 324 | 323 distinct ponds, one repeated enrollment survey. Preserve both surveys, program status, acreage, depth, feed/fish sources and practices. |
| stocking_harvest.csv | 1,699 | Full/partial stocking and harvest events, lifecycle, polyculture ratios, species weights, fish/shrimp counts, verification and pond preparation retained. |
| dropouts.csv | 128 | Program exit date, tenancy and reason retained; leaving a program does not mean harvesting all fish. |

## Semantic gaps addressed

- Water quality belongs to a **pond visit**, independently of a stocking batch.
  The new **Water visits** page also captures this for your own farm, including
  observer identity, equipment, repeat visits and corrective-action follow-up.
- TAN as NH3-N, TAN as NH3, and unionized NH3 are separate metrics. No conversion
  or concatenation is inferred across the August 2025 measurement change.
- Secchi depth is in **centimeters**, TDS in **ppt**, and temperature in °C.
- Original area remains in acres in research rows; do not feed it into `area_m2`
  without explicit conversion (1 acre = 4,046.8564224 m²). Imported ponds are not
  silently created with invented area/depth values.
- Enrollment and water measurement dates share a column name but have different
  meanings. Separate source tables and `source_date` preserve the correct meaning.
- All dates in the inspected CSVs parse as **MM/DD/YYYY**, not DD/MM/YYYY.
- Missing/NA values remain as published. Numeric views exclude missing values
  rather than replacing them with zero. Some fields were deliberately not collected.
- Visit mortality is since the previous visit. Visit feed observations and farmer-
  reported fish weights cannot substitute for a continuous daily log or growth sample series.
- Public IDs use the `ara2_` namespace. Older `pond_` releases are rejected rather
  than accidentally joined; snapshots are selected individually and never pooled.

## Import behavior

Managers open **FWI data**, select the downloaded snapshot or upload all four CSVs,
review the manifest/issues, and import. SHA-256 hashes make repeat imports
idempotent. Every row gets a source file and CSV record number; repeated surveys
are not deduplicated by pond ID. Inserts are one transaction. Invalid required
dates/IDs/schema reject the snapshot. Nonnumeric water observations are retained
and reported but excluded from numerical trends. Each snapshot keeps its own IDs.

Research data remains separate from production records. This prevents double-
counting repeated visits, assigning ambiguous events to invented batches, and
converting missing harvest weights to zero. All source fields are browsable;
not every field has a dedicated operational editor or derived KPI yet.

## Interpretation limits

The upstream dictionary documents a duplicate pond survey, a future-dated/planned
event relative to the release, absent harvest weights, changing equipment and
non-random treatment/control assignment. Inspect the dates and source labels before
research comparisons. The importer preserves future-dated events as reported;
analytics date filters determine inclusion. It does not silently relabel them as actual.

Trends are observation-weighted and show counts. More follow-up visits at troubled
ponds can change the apparent average even without a population-level change.
Reported in-range flags are preserved, not recomputed using today's thresholds.
No FCR/stock or financial KPI is calculated from the FWI snapshot.

Remaining operational extensions include a species-level stocking-event ledger,
restocking/transfers, shrimp inventory, a full corrective-action task workflow,
and enrollment/dropout management. Their source information is already retained
for analysis and future mapping.

Reference: [FWI data dictionary](https://github.com/fish-welfare-initiative/fwi-farm-data-india/blob/main/docs/data_dictionary.md).
