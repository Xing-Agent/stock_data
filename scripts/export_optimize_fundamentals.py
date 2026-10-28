#!/usr/bin/env python3
"""Prepare and export the frozen 250-symbol SEC cohort from optimize."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UTC = timezone.utc

METRICS = (
    "Revenue", "CostOfRevenue", "EBIT", "NetIncome", "DilutedEPS", "CurrentAssets",
    "CurrentLiabilities", "LongTermDebt", "TotalAssets", "StockholdersEquity",
    "IntangiblesAndGoodwill", "OperatingCashFlow", "WeightedAverageDilutedShares",
    "IncomeBeforeTax", "InterestExpense", "IntangibleAssetsNetExcludingGoodwill", "Goodwill",
)
EXTRA_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue", "AccountsReceivableNetCurrent", "InventoryNet",
    "Liabilities", "ShortTermBorrowings", "DebtCurrent", "LongTermDebtCurrent",
    "RetainedEarningsAccumulatedDeficit", "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
    "PaymentsOfDividends",
    "PaymentsOfDividendsCommonStock", "PaymentsForRepurchaseOfCommonStock",
    "ProceedsFromIssuanceOfCommonStock", "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
)
METRICS = (*METRICS, *EXTRA_TAGS)
COHORT_ID = "pilot300-expansion250"


class ApiResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        return json.loads(self._body)


class ApiClient:
    def __init__(self, base_url: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    def _request(self, method: str, path: str, body: Any = None,
                 params: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None) -> ApiResponse:
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=data, headers={**self.headers, **(headers or {})}, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return ApiResponse(response.status, response.read())
        except HTTPError as exc:
            return ApiResponse(exc.code, exc.read())
        except URLError as exc:
            raise RuntimeError(f"API request failed for {path}: {exc.reason}") from exc

    def get(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Any = None,
             headers: dict[str, str] | None = None) -> ApiResponse:
        return self._request("POST", path, body=json, headers=headers)


def five_years_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 5)
    except ValueError:  # February 29
        return day.replace(year=day.year - 5, day=28)


def load_cohort(manifest_path: Path, draft_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    draft_bytes = draft_path.read_bytes()
    if manifest.get("status") != "frozen_sample_and_download_windows":
        raise ValueError("Expected the frozen pilot_300 manifest")
    if hashlib.sha256(draft_bytes).hexdigest() != manifest.get("frozen_from_draft_sha256"):
        raise ValueError("The frozen manifest no longer matches its source draft")
    root = manifest_path.parent.parent
    for relative, digest in manifest.get("source_sha256", {}).items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen source hash check failed: {relative}")
    draft = json.loads(draft_bytes)
    draft_by_symbol = {row["symbol"]: row for row in draft.get("stocks", [])}
    rows = [row for row in manifest.get("stocks", []) if row.get("origin") == "expansion_250"]
    if len(rows) != 250 or len({row["symbol"] for row in rows}) != 250:
        raise ValueError("Expected exactly 250 unique expansion_250 symbols")
    entries = []
    for row in rows:
        source = draft_by_symbol.get(row["symbol"], {})
        cik, name = source.get("cik"), row.get("name")
        if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit() or not name:
            raise ValueError(f"Missing frozen SEC identity for {row['symbol']}")
        entries.append({"symbol": row["symbol"], "sec_cik": cik, "name": name})
    return manifest, rows


def login(client: ApiClient, email: str) -> None:
    password = os.getenv("XING_PASSWORD") or getpass.getpass(f"Password for {email}: ")
    response = client.post("/auth/login", json={"email": email, "password": password})
    del password
    if response.status_code != 200:
        raise RuntimeError(f"Optimize login failed: HTTP {response.status_code}")
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


def prepare(client: ApiClient, manifest_sha256: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for start in range(0, len(entries), 100):
        chunk = entries[start:start + 100]
        response = client.post(
            "/admin/v1/config/whitelist/frozen-cohort",
            headers={"X-Idempotency-Key": f"{COHORT_ID}-{start:03d}"},
            json={"cohort_id": COHORT_ID, "manifest_sha256": manifest_sha256, "entries": chunk},
        )
        if response.status_code != 200:
            raise RuntimeError(f"Optimize cohort import failed for batch {start // 100 + 1}: HTTP {response.status_code}")
        results.append(response.json())
        print(json.dumps({"prepared": min(start + len(chunk), len(entries)), "total": len(entries),
                          "queued": response.json().get("queued_count")}), flush=True)
    return {"cohort_id": COHORT_ID, "symbols": len(entries), "batches": results}


def extend_history(client: ApiClient, rows: list[dict[str, Any]], years: int) -> dict[str, Any]:
    import time
    batches, errors = [], []
    for offset in range(0, len(rows), 25):
        symbols = [row["symbol"] for row in rows[offset:offset + 25]]
        # Respect the platform's existing backlog guard instead of bypassing it.
        while True:
            response = client.post("/admin/v1/pipeline/jobs", json={"symbols": symbols, "stage": "cold",
                "mode": "incremental", "history_years": years, "reason": "Extend frozen 250-symbol SEC CompanyFacts history"},
                headers={"X-Idempotency-Key": f"{COHORT_ID}-history-{years}-{offset}"})
            data = response.json()
            if response.status_code == 409 and ("backlog" in str(data) or "rate limit" in str(data)):
                time.sleep(30)
                continue
            break
        if response.status_code != 200:
            raise RuntimeError(f"History expansion HTTP {response.status_code}: {data}")
        batches.append(data)
        errors.extend(item for item in data.get("results", []) if item.get("error"))
        print(json.dumps({"submitted": min(offset + 25, len(rows)), "total": len(rows),
                          "jobs": len(data.get("jobs", [])), "errors": len(errors)}), flush=True)
    return {"history_years": years, "batches": batches, "errors": errors}


def get_pages(client: ApiClient, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    page, items = 1, []
    while True:
        response = client.get(path, params={**params, "page": page, "page_size": 100})
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} for {path}")
        data = response.json()
        items.extend(data.get("items", []))
        if page >= data.get("total_pages", 1):
            return items
        page += 1


def fetch_company(client: ApiClient, row: dict[str, Any], start: str, end: str,
                  schedule_observations: list[dict[str, Any]], event_start: str | None = None) -> tuple[str, dict[str, Any]]:
    symbol = row["symbol"]
    base = f"/research-data/companies/{symbol}"
    now = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "symbol": symbol,
        "cohort": {
            "origin": row.get("origin"),
            "delisted": bool(row.get("delisted")),
            "delisting_date": row.get("delisting_date"),
            "retirement_category": row.get("retirement_category"),
        },
        "meta": {
            "retrieved_at": now,
            "data_window": {"start": start, "end": end},
            "sources": ["SEC CompanyFacts", "SEC periodic filing headers", "SEC 8-K/6-K originals"],
            "pit_status": "partial",
            "adjustment": "not_applicable",
            "coverage_note": "Only locally collected SEC records are exported; missing values remain missing.",
            "filing_date_semantics": "filing_date and available_at use verified SEC acceptance time; sec_filed_date is the SEC filing date.",
        },
        "financial_versions": {},
        "sic_versions": [],
        "actual_earnings_events": {},
        "historical_earnings_schedule": {
            "status": "unavailable",
            "pit_status": "non_pit",
            "reason": "historical_planned_schedule_not_supported",
            "observed_provider_snapshots": schedule_observations,
            "note": "Saved Alpha Vantage observations are included separately. They are not provider publication-time PIT snapshots and do not reconstruct historical planned dates before the first saved observation.",
        },
        "coverage": {"financial_errors": [], "metadata_error": None, "earnings_error": None},
    }
    for metric in METRICS:
        try:
            versions = get_pages(client, f"{base}/financial-versions", {
                "decision_at": end + "T23:59:59+00:00", "metric": f"raw:us-gaap:{metric}" if metric in EXTRA_TAGS else metric, "fiscal_period": "",
            })
            versions = [item for item in versions if not item.get("accepted_at") or item["accepted_at"][:10] <= end]
            for item in versions:
                item["sec_filed_date"] = item.get("filed_at")
                item["filing_date"] = item.get("accepted_at")
                item["available_at"] = item.get("accepted_at")
            payload["financial_versions"][metric] = versions
        except Exception as exc:  # Continue to report field-level gaps.
            payload["financial_versions"][metric] = []
            payload["coverage"]["financial_errors"].append({"metric": metric, "error": str(exc)})
    payload["coverage"]["additional_fields"] = {
        metric: {"source": f"raw:us-gaap:{metric}",
                 "records": len(payload["financial_versions"][metric]),
                 "strict_pit_records": sum(bool(item.get("pit_eligible")) for item in payload["financial_versions"][metric]),
                 "missing_reason": None if payload["financial_versions"][metric] else "no_retained_reported_sec_tag"}
        for metric in EXTRA_TAGS
    }
    for field, coverage in payload["coverage"]["additional_fields"].items():
        strict = coverage["strict_pit_records"]
        coverage["status"] = "ready" if strict == coverage["records"] and strict else "partial" if strict else "unavailable"
        if coverage["records"] and not strict:
            coverage["missing_reason"] = "no_strict_pit_versions"
    payload["meta"]["financial_lookback_note"] = "Earlier disclosed periods are retained as backtest warmup inputs; the requested decision window is not a claim of complete coverage."
    payload["meta"]["actual_earnings_events_requested_window"] = {"start": event_start or start, "end": end}
    payload["meta"]["additional_fields_basis"] = "Exact reported SEC tags. Cash-flow durations may be year-to-date; retain period_start/period_end. Cash dividends paid are not a dividend announcement or revision event chain."
    payload["coverage"]["derived_metrics"] = {}
    for metric, left, right, require_nonnegative_right in (
        ("EBIT", "IncomeBeforeTax", "InterestExpense", True),
        ("IntangiblesAndGoodwill", "Goodwill", "IntangibleAssetsNetExcludingGoodwill", False),
    ):
        derived, skipped = derive_financial_versions(
            payload["financial_versions"].get(metric, []),
            payload["financial_versions"].get(left, []),
            payload["financial_versions"].get(right, []),
            formula=f"{left} + {right}",
            require_nonnegative_right=require_nonnegative_right,
            instant_period=(metric == "IntangiblesAndGoodwill"),
        )
        payload["financial_versions"][metric].extend(derived)
        payload["coverage"]["derived_metrics"][metric] = {
            "formula": f"{left} + {right}",
            "records_derived": len(derived),
            "skipped_by_reason": skipped,
        }
    try:
        versions = get_pages(client, f"{base}/metadata/versions", {})
        chronological = sorted(versions, key=lambda item: (item.get("accepted_at") or "", item.get("filing_id") or 0))
        sic_versions = []
        for index, item in enumerate(chronological):
            fields = item.get("fields") or {}
            sic_versions.append({
                "symbol": symbol,
                "sic_code": fields.get("sic"),
                "sic_description": fields.get("sic_description"),
                "observed_from": item.get("accepted_at"),
                "observed_until": chronological[index + 1].get("accepted_at") if index + 1 < len(chronological) else None,
                "accepted_at": item.get("accepted_at"),
                "accession": item.get("accession"),
                "form": item.get("form"),
                "source_url": item.get("source_url"),
                "issuer_lineage": item.get("issuer_lineage"),
                "pit_status": "strict" if item.get("accepted_at") else "unavailable",
                "date_semantics": "SEC disclosure observation interval; not a proven economic effective date",
            })
        payload["sic_versions"] = sic_versions
    except Exception as exc:
        payload["coverage"]["metadata_error"] = str(exc)
    try:
        response = client.get(f"{base}/earnings-events", params={"start_date": event_start or start, "end_date": end})
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        payload["actual_earnings_events"] = response.json()
    except Exception as exc:
        payload["coverage"]["earnings_error"] = str(exc)
    return symbol, payload


_DERIVATION_IDENTITY_FIELDS = (
    "filing_accession", "period_start", "period_end", "unit", "fiscal_year",
    "fiscal_period", "accepted_at",
)


def derive_financial_versions(
    existing: list[dict[str, Any]],
    left_versions: list[dict[str, Any]],
    right_versions: list[dict[str, Any]],
    *,
    formula: str,
    require_nonnegative_right: bool = False,
    instant_period: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Derive PIT values only from unique, strictly verified facts in one filing/period."""
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    def identity(item: dict[str, Any]) -> tuple[Any, ...] | None:
        key = tuple(item.get(field) for field in _DERIVATION_IDENTITY_FIELDS)
        if any(value is None for index, value in enumerate(key) if index != 1):
            return None
        if (key[1] is None) != instant_period:
            return None
        return key

    def grouped(items: list[dict[str, Any]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
        result: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for item in items:
            key = identity(item)
            if key is not None:
                result.setdefault(key, []).append(item)
        return result

    existing_keys = {identity(item) for item in existing}
    left_by_key, right_by_key = grouped(left_versions), grouped(right_versions)
    derived = []
    for key in sorted(left_by_key.keys() & right_by_key.keys(), key=str):
        if key in existing_keys:
            continue
        left_rows, right_rows = left_by_key[key], right_by_key[key]
        rows = [*left_rows, *right_rows]
        if any(
            item.get("pit_status") != "strict"
            or item.get("pit_eligible") is not True
            or item.get("acceptance_verified") is not True
            or item.get("period_verified") is not True
            for item in rows
        ):
            skip("inputs_not_strict_pit")
            continue
        try:
            left_values = {Decimal(item["value"]) for item in left_rows}
            right_values = {Decimal(item["value"]) for item in right_rows}
        except (KeyError, InvalidOperation, TypeError):
            skip("invalid_input_value")
            continue
        if len(left_values) != 1 or len(right_values) != 1:
            skip("conflicting_input_values")
            continue
        left_value, right_value = next(iter(left_values)), next(iter(right_values))
        if require_nonnegative_right and right_value < 0:
            skip("interest_expense_not_positive")
            continue
        total = left_value + right_value
        base = dict(left_rows[0])
        for field in ("source_record_id", "record_id", "source_tag", "taxonomy"):
            base.pop(field, None)
        base.update({
            "metric": "EBIT" if formula == "IncomeBeforeTax + InterestExpense" else "IntangiblesAndGoodwill",
            "value": format(total, "f"),
            "source_type": "derived_from_sec_pit_facts",
            "source_record_ids": sorted({item.get("source_record_id") for item in rows if item.get("source_record_id") is not None}),
            "source_urls": sorted({item.get("source_url") for item in rows if item.get("source_url")}),
            "derivation": {
                "formula": formula,
                "input_metrics": [formula.split(" + ")[0], formula.split(" + ")[1]],
                "filing_accession": key[0],
                "period_start": key[1],
                "period_end": key[2],
                "accepted_at": key[6],
            },
            "verification_method": "derived_from_same_verified_sec_filing_and_period",
            "pit_status": "strict",
            "pit_eligible": True,
            "pit_reasons": [],
        })
        derived.append(base)
    return derived, skipped


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def earnings_scan_window(output: Path) -> tuple[date, date]:
    window_path = output / "pilot_300" / "earnings_event_scan_window.json"
    if window_path.exists():
        value = json.loads(window_path.read_text(encoding="utf-8"))
        start, end = date.fromisoformat(value["start"]), date.fromisoformat(value["end"])
        if start > end:
            raise ValueError("Invalid frozen earnings scan window")
        return start, end

    export_manifest_path = output / "pilot_300" / "fundamentals_export_manifest.json"
    if export_manifest_path.exists():
        date_range = json.loads(export_manifest_path.read_text(encoding="utf-8")).get("date_range", {})
        start, end = date.fromisoformat(date_range["start"]), date.fromisoformat(date_range["end"])
    else:
        end = datetime.now(UTC).date()
        start = five_years_before(end)
    if start > end:
        raise ValueError("Invalid earnings scan window")
    atomic_json(window_path, {
        "status": "frozen",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "source": str(export_manifest_path) if export_manifest_path.exists() else "first_scan_invocation",
    })
    return start, end


def scan_events(container: str, entries: list[dict[str, Any]], output: Path,
                start: date, end: date) -> int:
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{.Name}}", container],
        check=False, capture_output=True, text=True,
    )
    if inspected.returncode != 0 or not inspected.stdout.strip().lstrip("/").startswith("agent-optimize-"):
        raise ValueError("The event scan target must be a running agent-optimize API container")
    report_in_container = "/tmp/pilot300_expansion250_earnings_events.json"
    command = [
        "docker", "exec", "--workdir", "/app", "-e", "PYTHONPATH=/app",
        "-e", "SEC_MIN_REQUEST_INTERVAL_SECONDS=0.25", container,
        "/app/.venv/bin/python", "/app/scripts/backfills/sec_earnings_events.py",
        "--symbols", ",".join(item["symbol"] for item in entries),
        "--start-date", start.isoformat(), "--end-date", end.isoformat(),
        "--output", report_in_container, "--apply",
    ]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        return completed.returncode
    report_path = output / "pilot_300" / "earnings_event_scan_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    copied = subprocess.run(["docker", "cp", f"{container}:{report_in_container}", str(report_path)], check=False)
    if copied.returncode != 0:
        raise RuntimeError("SEC scan finished, but its coverage report could not be copied from optimize")
    return 0


def load_schedule_observations(container: str, symbols: list[str], output: Path) -> dict[str, Any]:
    inspected = subprocess.run(["docker", "inspect", "--format", "{{.Name}}", container],
                                check=False, capture_output=True, text=True)
    if inspected.returncode != 0 or not inspected.stdout.strip().lstrip("/").startswith("agent-optimize-"):
        raise ValueError("Schedule observations must be read from a running agent-optimize API container")
    container_path = "/tmp/pilot300_expansion250_schedule_observations.json"
    command = ["docker", "exec", "--workdir", "/app", "-e", "PYTHONPATH=/app", container,
               "/app/.venv/bin/python", "/app/scripts/backfills/export_earnings_schedule_observations.py",
               "--symbols", ",".join(symbols), "--output", container_path]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError("Could not read saved earnings-schedule observations from optimize")
    temporary = output / "pilot_300" / ".earnings_schedule_observations.json"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    copied = subprocess.run(["docker", "cp", f"{container}:{container_path}", str(temporary)], check=False)
    if copied.returncode != 0:
        raise RuntimeError("Could not copy saved earnings-schedule observations from optimize")
    try:
        return json.loads(temporary.read_text(encoding="utf-8"))
    finally:
        temporary.unlink(missing_ok=True)


def export(client: ApiClient, manifest_path: Path, rows: list[dict[str, Any]], output: Path,
           api_container: str, start_date: date | None = None, end_date: date | None = None) -> dict[str, Any]:
    event_start, event_end = earnings_scan_window(output)
    start, end = start_date or event_start, end_date or event_end
    if start > end:
        raise ValueError("Invalid financial export window")
    generated = datetime.now(UTC).isoformat()
    outcomes, errors = [], []
    schedule_data = load_schedule_observations(api_container, [row["symbol"] for row in rows], output)
    schedule_by_symbol = schedule_data["observations"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_company, client, row, start.isoformat(), end.isoformat(),
                               schedule_by_symbol.get(row["symbol"], []), event_start.isoformat()): row for row in rows}
        for number, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            try:
                symbol, payload = future.result()
                path = output / "pilot_300" / symbol / "fundamentals.json"
                atomic_json(path, payload)
                outcomes.append({"symbol": symbol, "path": str(path),
                                 "financial_records": sum(map(len, payload["financial_versions"].values())),
                                 "strict_pit_financial_records": sum(bool(item.get("pit_eligible")) for values in payload["financial_versions"].values() for item in values),
                                 "financial_records_by_metric": {
                                     metric: len(payload["financial_versions"].get(metric, [])) for metric in METRICS
                                 },
                                 "sic_versions": len(payload["sic_versions"]),
                                 "earnings_events": len(payload["actual_earnings_events"].get("events", [])),
                                 "coverage": payload["coverage"]})
            except Exception as exc:
                errors.append({"symbol": row["symbol"], "error": str(exc)})
            if number % 10 == 0 or number == len(rows):
                print(json.dumps({"exported": number, "total": len(rows), "errors": len(errors)}), flush=True)
    sectors = [{"symbol": row["symbol"], "sector": row.get("sector"),
                "sector_basis": row.get("sector_basis", "unknown")} for row in rows]
    sector_path = output / "pilot_300" / "sector_classification_current_non_pit.csv"
    sector_path.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with sector_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "sector", "sector_basis"])
        writer.writeheader()
        writer.writerows(sectors)
    sector_meta_path = sector_path.with_suffix(".meta.json")
    atomic_json(sector_meta_path, {
        "meta": {
            "source": "Frozen pilot_300 manifest sector fields (FMP current profile classification)",
            "retrieved_at": generated,
            "pit_status": "non_pit_current_classification",
            "adjustment": "not_applicable",
        },
        "records": len(sectors),
    })
    schedule_csv = output / "pilot_300" / "earnings_schedule_observations_non_pit.csv"
    schedule_fields = ["symbol", "observed_at", "fiscal_period_end", "report_date", "session",
                       "session_raw", "event_at", "timezone", "source_url", "source_sha256"]
    with schedule_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=schedule_fields)
        writer.writeheader()
        for symbol, observations in schedule_by_symbol.items():
            for observation in observations:
                for schedule_row in observation.get("rows", []):
                    writer.writerow({"symbol": symbol, "observed_at": observation["observed_at"],
                                     **{key: schedule_row.get(key) for key in schedule_fields[2:8]},
                                     "source_url": observation.get("source_url"),
                                     "source_sha256": observation.get("source_sha256")})
    schedule_meta = {
        "source": "Saved Alpha Vantage EARNINGS_CALENDAR observations in optimize",
        "retrieved_at": generated,
        "pit_status": "non_pit_observation_time_is_not_vendor_publication_time",
        "adjustment": "not_applicable",
        "symbols_expected": len(rows),
        "symbols_with_observations": schedule_data["symbols_with_observations"],
        "observation_count": schedule_data["observation_count"],
        "records": sum(len(observation.get("rows", [])) for observations in schedule_by_symbol.values()
                       for observation in observations),
        "limitations": ["No historical planned-date snapshots before the first saved observation.",
                        "Missing rows are not confirmed cancellations.",
                        "Session is reported as provided; clock and timezone are not inferred."],
    }
    schedule_meta_path = schedule_csv.with_suffix(".meta.json")
    atomic_json(schedule_meta_path, schedule_meta)
    report = {
        "generated_at": generated,
        "cohort_id": COHORT_ID,
        "cohort": {"origin": "expansion_250", "delisted_symbols": sum(bool(row.get("delisted")) for row in rows),
                    "symbols_expected": len(rows)},
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "symbols_expected": len(rows), "symbols_exported": len(outcomes), "errors": errors,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "coverage_summary": {
            "strict_pit_financial_records": sum(item["strict_pit_financial_records"] for item in outcomes),
            "additional_fields": {field: {
                "symbols_with_strict_records": sum(item["coverage"]["additional_fields"][field]["strict_pit_records"] > 0 for item in outcomes),
                "strict_pit_records": sum(item["coverage"]["additional_fields"][field]["strict_pit_records"] for item in outcomes),
                "missing_symbols": sorted(item["symbol"] for item in outcomes if not item["coverage"]["additional_fields"][field]["strict_pit_records"]),
            } for field in EXTRA_TAGS},
            "symbols_with_financial_records": sum(item["financial_records"] > 0 for item in outcomes),
            "symbols_without_financial_records": sorted(
                item["symbol"] for item in outcomes if item["financial_records"] == 0
            ),
            "symbols_with_sic_versions": sum(item["sic_versions"] > 0 for item in outcomes),
            "symbols_without_sic_versions": sorted(
                item["symbol"] for item in outcomes if item["sic_versions"] == 0
            ),
            "financial_records_by_metric": {
                metric: sum(item["financial_records_by_metric"][metric] for item in outcomes)
                for metric in METRICS
            },
        },
        "sector_classification": {"path": str(sector_path), "metadata_path": str(sector_meta_path),
                                  "pit_status": "non_pit_current_fmp_profile"},
        "actual_earnings_events": {
            "scan_report_path": str(output / "pilot_300" / "earnings_event_scan_report.json"),
            "scan_window": {"start": event_start.isoformat(), "end": event_end.isoformat()},
            "records_exported": sum(item.get("earnings_events", 0) for item in outcomes),
            "symbols_with_records": sum(item.get("earnings_events", 0) > 0 for item in outcomes),
        },
        "earnings_schedule_observations": {"path": str(schedule_csv), "metadata_path": str(schedule_meta_path),
                                            **schedule_meta},
        "limitations": [
            "Historical planned earnings-calendar snapshots are not available; actual SEC release events are exported separately.",
            "SIC intervals are disclosure-observation intervals, not proven economic effective dates.",
            "Financial and filing coverage reflects the configured initial collection window and may be partial.",
            "Missing or conflicting records are reported, never inferred.",
            "Additional fields use exact SEC tags. DebtCurrent and LongTermDebtCurrent are separate debt concepts, not replacements for ShortTermBorrowings.",
            "WeightedAverageDilutedShares is a period weighted diluted EPS denominator, not historical point-in-time ordinary shares outstanding; multiplying it by a close is only a size proxy, not strict PIT market capitalization.",
        ],
        "companies": outcomes,
    }
    atomic_json(output / "pilot_300" / "fundamentals_export_manifest.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "pilot_300" / "manifest.json")
    parser.add_argument("--draft", type=Path, default=Path(__file__).resolve().parents[1] / "pilot_300" / "manifest.draft.json")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--email", default=os.getenv("XING_EMAIL"))
    parser.add_argument("--history-years", type=int, choices=range(1, 21), metavar="1..20")
    parser.add_argument("--start-date", type=date.fromisoformat, help="Requested financial decision-window start; earlier disclosed inputs remain available")
    parser.add_argument("--end-date", type=date.fromisoformat)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--extend-history", action="store_true", help="Expand cold history through existing optimize worker jobs; warm history is unchanged")
    mode.add_argument("--prepare", action="store_true", help="Import frozen identities and enqueue optimize cold-data jobs")
    mode.add_argument("--scan-events", action="store_true", help="Scan and persist actual SEC earnings releases in optimize")
    mode.add_argument("--export", action="store_true", help="Export persisted PIT financial versions, SIC, actual events, and current sector labels")
    parser.add_argument("--api-container", default=os.getenv("AGENT_OPTIMIZE_API_CONTAINER", "agent-optimize-api-1"))
    args = parser.parse_args()
    if args.extend_history and args.history_years is None:
        parser.error("--extend-history requires --history-years")
    manifest, rows = load_cohort(args.manifest, args.draft)
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    draft_by_symbol = {row["symbol"]: row for row in draft["stocks"]}
    entries = [{"symbol": row["symbol"], "sec_cik": draft_by_symbol[row["symbol"]]["cik"], "name": row["name"]} for row in rows]
    if args.scan_events:
        start, end = earnings_scan_window(args.output)
        return scan_events(args.api_container, entries, args.output, start, end)
    email = args.email or input("Optimize admin email: ").strip()
    client = ApiClient(args.api_base, timeout=60)
    login(client, email)
    if args.extend_history:
        result = extend_history(client, rows, args.history_years)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("errors") else 0
    result = prepare(client, hashlib.sha256(args.manifest.read_bytes()).hexdigest(), entries) if args.prepare else export(
        client, args.manifest, rows, args.output, args.api_container, args.start_date, args.end_date)
    print(json.dumps({key: result[key] for key in result if key not in {"companies", "batches"}}, ensure_ascii=False))
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
