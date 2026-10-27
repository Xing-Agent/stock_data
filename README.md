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
