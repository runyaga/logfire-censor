#!/usr/bin/env python3
"""
Logfire Validation Script

Queries Logfire API to verify that scrubbing is working correctly.
Searches for the test string in recent spans to confirm it was/wasn't transmitted.

Usage:
    python validate_logfire.py --expect-found      # Expect test string in Logfire
    python validate_logfire.py --expect-not-found  # Expect test string NOT in Logfire
"""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

# Test string to search for (must match demo.py)
TEST_STRING = "Bill of Rights"

# Colors for output
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
NC = "\033[0m"  # No color


def query_logfire_for_string(read_token: str, search_string: str, minutes: int = 10) -> dict:
    """
    Query Logfire for spans containing the search string.

    Returns dict with:
        - found: bool - whether the string was found
        - count: int - number of matching spans
        - details: list - sample of matching data
    """
    from logfire.query_client import LogfireQueryClient

    # SQL query to search for the test string in span attributes
    # The attributes column contains JSON with prompt/response data
    sql = f"""
    SELECT
        start_timestamp,
        span_name,
        message,
        attributes
    FROM records
    WHERE
        start_timestamp > NOW() - INTERVAL '{minutes} minutes'
        AND (
            message LIKE '%{search_string}%'
            OR attributes::text LIKE '%{search_string}%'
        )
    ORDER BY start_timestamp DESC
    LIMIT 20
    """

    try:
        with LogfireQueryClient(read_token=read_token) as client:
            result = client.query_json(sql=sql)

            # query_json returns column-oriented data
            # Convert to row count
            if result and "start_timestamp" in result:
                count = len(result["start_timestamp"])
                details = []
                for i in range(min(count, 5)):  # Sample first 5
                    details.append({
                        "timestamp": result["start_timestamp"][i] if "start_timestamp" in result else None,
                        "span_name": result["span_name"][i] if "span_name" in result else None,
                        "message": result["message"][i][:100] if "message" in result and result["message"][i] else None,
                    })
                return {"found": count > 0, "count": count, "details": details}
            else:
                return {"found": False, "count": 0, "details": []}

    except Exception as e:
        print(f"{RED}[ERROR]{NC} Failed to query Logfire: {e}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description="Validate Logfire scrubbing via API")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--expect-found",
        action="store_true",
        help="Expect the test string to be found in Logfire (baseline test)",
    )
    group.add_argument(
        "--expect-not-found",
        action="store_true",
        help="Expect the test string NOT to be found in Logfire (scrubbing test)",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=10,
        help="Number of minutes to look back (default: 10)",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=3,
        help="Number of retries with delay (default: 3)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    args = parser.parse_args()

    # Check for read token
    read_token = os.getenv("LOGFIRE_READ_TOKEN")
    if not read_token:
        print(f"{RED}[ERROR]{NC} LOGFIRE_READ_TOKEN not found in environment")
        print("       Get a read token from: https://logfire.pydantic.dev → Project Settings → Tokens")
        sys.exit(1)

    print(f"{YELLOW}[INFO]{NC} Querying Logfire for test string: '{TEST_STRING}'")
    print(f"{YELLOW}[INFO]{NC} Looking back {args.minutes} minutes")

    # Query with retries (telemetry may take a moment to appear)
    result = None
    for attempt in range(args.retry):
        if attempt > 0:
            print(f"{YELLOW}[INFO]{NC} Retry {attempt + 1}/{args.retry} (waiting 5s for telemetry)...")
            time.sleep(5)

        result = query_logfire_for_string(read_token, TEST_STRING, args.minutes)

        # For expect-found, we can exit early if found
        if args.expect_found and result["found"]:
            break
        # For expect-not-found, we need to wait and retry to be sure
        if args.expect_not_found and not result["found"] and attempt == args.retry - 1:
            break

    # Report results
    if args.verbose and result["details"]:
        print(f"\n{YELLOW}[DEBUG]{NC} Sample matches:")
        for detail in result["details"]:
            print(f"  - {detail['span_name']}: {detail['message']}")
        print()

    # Validate expectations
    if args.expect_found:
        if result["found"]:
            print(f"{GREEN}[PASS]{NC} Test string FOUND in Logfire ({result['count']} spans)")
            print(f"       This confirms telemetry is being sent (baseline working)")
            return 0
        else:
            print(f"{RED}[FAIL]{NC} Test string NOT found in Logfire")
            print(f"       Expected to find '{TEST_STRING}' but it wasn't there")
            print(f"       Check that LOGFIRE_TOKEN is correct and telemetry was sent")
            return 1

    else:  # expect-not-found
        if not result["found"]:
            print(f"{GREEN}[PASS]{NC} Test string NOT found in Logfire")
            print(f"       This confirms scrubbing is working correctly!")
            return 0
        else:
            print(f"{RED}[FAIL]{NC} Test string FOUND in Logfire ({result['count']} spans)")
            print(f"       Expected scrubbing to hide '{TEST_STRING}' but it was visible")
            print(f"       Scrubbing configuration may not be working")
            return 1


if __name__ == "__main__":
    sys.exit(main())
