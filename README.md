# stock_data

## Optimize PIT data for the frozen 250-stock cohort

`pilot_300/manifest.json` contains a frozen `expansion_250` cohort: 250 symbols, including 27 delisted companies. `scripts/export_optimize_fundamentals.py` verifies the frozen manifest and its source hashes before operating on it.

Run the three stages against the optimize development environment only:

```bash
python scripts/export_optimize_fundamentals.py --prepare
```

This imports the frozen symbol-to-CIK identities into the optimize whitelist and queues the existing cold SEC pipeline for financial facts and filing-header metadata. It does not queue PageIndex document indexing; the export does not consume those trees, and actual earnings releases are collected by the dedicated SEC scan below. It is safe to rerun; already active or ready cold stages are skipped. Wait for the cold jobs to finish in the optimize admin pipeline view.

```bash
python scripts/export_optimize_fundamentals.py --scan-events
```

This runs the optimize SEC backfill for actual 6-K releases and 8-K Item 2.02 over the latest five years. It writes a coverage report alongside the export. It does not reconstruct historical planned earnings calendars.

```bash
python scripts/export_optimize_fundamentals.py --export
```

The prepare/export stages prompt for the optimize admin email and password; do not put credentials in commands or source files. The optimize API defaults to `http://localhost:8000`; override with `--api-base` if needed. Event scanning and export require Docker and refuse targets outside an `agent-optimize-*` container.

Exports are written under `pilot_300/<SYMBOL>/fundamentals.json`, with `pilot_300/fundamentals_export_manifest.json`, `pilot_300/sector_classification_current_non_pit.csv`, and `pilot_300/earnings_schedule_observations_non_pit.csv` plus metadata sidecars. Financial `filing_date` and `available_at` use the verified SEC acceptance time; `sec_filed_date` preserves the SEC filing date. SIC intervals represent successive SEC disclosure observations, not proven economic effective dates. Saved Alpha Vantage schedule observations are non-PIT and are exported only if already stored; they do not reconstruct historical planned dates. Actual SEC release events are kept separate. Sector labels reuse the frozen FMP current-profile classification and are not PIT. Missing or conflicting fields remain explicit gaps.


XPRO's historical financial and SIC records include an `issuer_lineage` field when they come from predecessor CIK 0001575828. The original fact's `accepted_at` is its publication time; `issuer_lineage.known_at` is when the later 1:1 issuer transition was disclosed and should not be confused with the earlier fact's availability. This frozen 250-symbol sample is selected retrospectively and is not a point-in-time historical universe.

FRC's bank financial statements are not available through the existing SEC periodic-filing path. MTR uses modified cash-basis trust statements; its original reported figures have not been equated with ordinary-company metrics. Empty fields remain gaps. For XPRO, individual fields can also be missing where the original tags do not establish the configured metric definition.


## Expand financial history and export the strategy feedback fields

The optimize job API accepts an explicit `history_years` (1–20) for incremental cold or warm expansion. The initial defaults are cold 10 years and warm 5 years. The exporter only expands cold data:

```bash
python scripts/export_optimize_fundamentals.py --extend-history --history-years 15
python scripts/export_optimize_fundamentals.py --export --start-date 2016-01-01 --end-date 2026-10-26
```

Wait for the submitted platform jobs to finish before export. Existing CompanyFacts caches are reused; old database periods are added without rewriting the existing range. Changing a default alone does not expand companies already ingested. A year count is anchored to each source's latest report year, not a fixed calendar date. The October 27 expansion retains 2015 period inputs as lookback for a requested decision window beginning in 2016; younger issuers retain only their available history. The actual SEC earnings-event scan remains in its separately recorded five-year window and has not been extended by the financial export option.

The feedback lists 12 field groups (despite its “11” heading). The export includes 18 exact `us-gaap` tags: the requested tags and alternatives plus two approved common-metric aliases, `PaymentsToAcquireProductiveAssets` and `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost`. Each remains stored under its exact source tag. `DebtCurrent` and `LongTermDebtCurrent` are not silently substituted for `ShortTermBorrowings`; dividend and depreciation alternatives also remain separate named tags. Each row keeps its original unit, economic period, SEC accession, verified acceptance time, and PIT assessment. Absence is recorded in `coverage.additional_fields`. Source conflicts or unverified periods remain explicitly ineligible. Financial versions disclosed after the export end date are excluded.

`WeightedAverageDilutedShares` is the period weighted diluted EPS denominator. It is not ordinary shares outstanding at a historical instant. Multiplying it by a close produces a size proxy, not strict PIT market capitalization. A strict or explicitly estimated market-capitalization calculation must use the platform's separately traced ordinary-share and corporate-action inputs.

Cash-flow tags retain the original reported duration, which may be year-to-date rather than one quarter. `PaymentsOfDividends` records cash paid in a reporting period; it does not fill the missing dividend announcement/revision event chain.


October 27 history expansion acceptance is recorded in `pilot_300/fundamentals_history_acceptance.json`. All 248 eligible SEC sources completed; FRC and MTR remain explicit source gaps. The 250 files contain 585,214 financial versions, of which 571,806 pass strict PIT checks; noneligible versions remain flagged for audit. The original 1,497,688 CompanyFacts rows retained their values and snapshot hashes, and 2,568,925 older records were added. See the acceptance JSON and `fundamentals_export_manifest.json` for per-tag coverage and missing-symbol lists.


## Market benchmark and reference data

Unified entry: [pilot_300/benchmarks/README.md](pilot_300/benchmarks/README.md). Read `manifest.json` and resolve each `file` relative to that directory. SPY, QQQ, IWM, RSP and the 11 sector ETFs are now together with the existing style, rates, volatility and credit references. Files retain their own ranges and adjustment bases; the 14 ETF update includes vendor snapshot `adj_close`, not vendor revision PIT. Source snapshots and scoped audits are retained. Top-level SPY/IWM remain legacy compatibility exports; new consumers should use benchmarks. Exporter: `scripts/export_etf_benchmarks.py` (stage fresh downloads to a temporary output directory).
