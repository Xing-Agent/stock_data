"""Download K lines through the authenticated XING API, without provider keys."""

from __future__ import annotations

import argparse
from datetime import date
from getpass import getpass
import json
import os
from pathlib import Path
import re
import sys

import httpx


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Stock symbol, e.g. AAPL or BRK.B")
    parser.add_argument("--base-url", default=os.getenv("XING_API_URL", "http://localhost:8010"),
                        help="API base URL (not the frontend URL)")
    parser.add_argument("--interval", choices=("1d", "5min"), default="1d")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--include-actions", action="store_true",
                        help="Also fetch dividends and splits for the requested dates")
    parser.add_argument("--timeout", type=float, default=600, help="Per-request timeout in seconds")
    parser.add_argument("--output", type=Path, required=True, help="New JSON file; existing files are not overwritten")
    args = parser.parse_args(argv)
    args.symbol = args.symbol.upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", args.symbol):
        parser.error("Invalid stock symbol")
    if args.start_date > args.end_date or args.end_date > date.today():
        parser.error("Dates must be ordered and not in the future")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.output.exists():
        parser.error("Output already exists; choose another filename")
    return args


def fetch(client: httpx.Client, path: str, params: dict[str, str]) -> dict:
    response = client.get(path, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "status" not in payload:
        raise ValueError("Unexpected API response (missing status)")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.getenv("XING_BEARER_TOKEN", "").strip()
    if not token:
        if not sys.stdin.isatty():
            print("Set XING_BEARER_TOKEN to your platform access token", file=sys.stderr)
            return 1
        token = getpass("XING access token (hidden): ").strip()
    if not token or "\n" in token or "\r" in token:
        print("Invalid access token", file=sys.stderr)
        return 1
    params = {"start_date": args.start_date.isoformat(), "end_date": args.end_date.isoformat()}
    prefix = f"research-data/market-bars/{args.symbol}"
    try:
        with httpx.Client(
            base_url=args.base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=args.timeout,
            follow_redirects=False,
        ) as client:
            bars = fetch(client, f"{prefix}/{'daily' if args.interval == '1d' else '5min'}", params)
            result = {**bars, "start_date": params["start_date"], "end_date": params["end_date"]}
            actions = None
            if args.include_actions:
                actions = fetch(client, f"{prefix}/actions", params)
                result["corporate_actions"] = actions
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except httpx.HTTPStatusError as exc:
        print(f"API returned HTTP {exc.response.status_code}; check token, API URL and parameters", file=sys.stderr)
        return 1
    except httpx.RequestError:
        print("API connection failed or timed out; cached data can be reused on a later request", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {len(bars.get('data', []))} bars ({bars['status']}) to {args.output}", file=sys.stderr)
    if actions is not None:
        print(f"Corporate actions: {actions['status']}; "
              f"missing dividend payment dates: {len(actions.get('missing_payment_dates', []))}", file=sys.stderr)
    if bars["status"] != "ready" or (actions is not None and actions["status"] != "ready"):
        print("Data is incomplete; inspect status, warnings and missing_months in the JSON", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
