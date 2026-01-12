#!/usr/bin/env python3
"""
Analyze mitmproxy flow dumps to check if test strings appear in Logfire traffic.

Usage:
    python analyze_flows.py <flow_file> <search_string> [--expect-found|--expect-not-found]

Exit codes:
    0 - Expectation met
    1 - Expectation not met
    2 - Error
"""

import argparse
import sys
from pathlib import Path

from mitmproxy import io as mitmproxy_io
from mitmproxy.http import HTTPFlow


def analyze_flows(flow_file: Path, search_string: str, logfire_only: bool = True) -> dict:
    """
    Analyze a mitmproxy flow file for occurrences of a search string.

    Returns a dict with analysis results.
    """
    results = {
        "total_flows": 0,
        "logfire_flows": 0,
        "matches": [],
        "found": False,
    }

    try:
        with open(flow_file, "rb") as f:
            reader = mitmproxy_io.FlowReader(f)
            for flow in reader.stream():
                if not isinstance(flow, HTTPFlow):
                    continue

                results["total_flows"] += 1

                # Filter to only Logfire traffic if requested
                host = flow.request.host
                if logfire_only and "logfire" not in host.lower():
                    continue

                results["logfire_flows"] += 1

                # Check request body
                request_content = ""
                if flow.request.content:
                    try:
                        request_content = flow.request.content.decode("utf-8", errors="replace")
                    except Exception:
                        pass

                # Check response body
                response_content = ""
                if flow.response and flow.response.content:
                    try:
                        response_content = flow.response.content.decode("utf-8", errors="replace")
                    except Exception:
                        pass

                # Search for the string (case-insensitive)
                search_lower = search_string.lower()

                if search_lower in request_content.lower():
                    results["matches"].append({
                        "type": "request",
                        "url": flow.request.pretty_url,
                        "method": flow.request.method,
                    })
                    results["found"] = True

                if search_lower in response_content.lower():
                    results["matches"].append({
                        "type": "response",
                        "url": flow.request.pretty_url,
                        "status": flow.response.status_code if flow.response else None,
                    })
                    results["found"] = True

    except FileNotFoundError:
        print(f"ERROR: Flow file not found: {flow_file}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: Failed to read flow file: {e}", file=sys.stderr)
        sys.exit(2)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Analyze mitmproxy flows for sensitive data"
    )
    parser.add_argument("flow_file", type=Path, help="Path to mitmproxy flow file")
    parser.add_argument("search_string", help="String to search for in traffic")
    parser.add_argument(
        "--expect-found",
        action="store_true",
        help="Expect the string to be found (exit 0 if found, 1 if not)",
    )
    parser.add_argument(
        "--expect-not-found",
        action="store_true",
        help="Expect the string to NOT be found (exit 0 if not found, 1 if found)",
    )
    parser.add_argument(
        "--all-traffic",
        action="store_true",
        help="Analyze all traffic, not just Logfire",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    if args.expect_found and args.expect_not_found:
        print("ERROR: Cannot use both --expect-found and --expect-not-found", file=sys.stderr)
        sys.exit(2)

    if not args.expect_found and not args.expect_not_found:
        print("ERROR: Must specify --expect-found or --expect-not-found", file=sys.stderr)
        sys.exit(2)

    print(f"Analyzing: {args.flow_file}")
    print(f"Searching for: '{args.search_string}'")

    results = analyze_flows(
        args.flow_file,
        args.search_string,
        logfire_only=not args.all_traffic,
    )

    print(f"Total flows: {results['total_flows']}")
    print(f"Logfire flows: {results['logfire_flows']}")
    print(f"String found: {results['found']}")

    if args.verbose and results["matches"]:
        print("\nMatches:")
        for match in results["matches"]:
            print(f"  - {match['type']}: {match['url']}")

    # Determine exit code based on expectation
    if args.expect_found:
        if results["found"]:
            print("\nPASS: String was found as expected")
            return 0
        else:
            print("\nFAIL: String was NOT found (expected to find it)")
            return 1
    else:  # expect_not_found
        if not results["found"]:
            print("\nPASS: String was NOT found as expected")
            return 0
        else:
            print("\nFAIL: String WAS found (expected NOT to find it)")
            return 1


if __name__ == "__main__":
    sys.exit(main())
