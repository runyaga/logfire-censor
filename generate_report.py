#!/usr/bin/env python3
"""
Generate BEFORE.md and AFTER.md reports from captured mitmproxy traffic.

This script reads the captured .mitm files and generates human-readable
markdown reports showing the difference between scrubbed and non-scrubbed traffic.
"""

import gzip
from datetime import datetime
from pathlib import Path

from mitmproxy import io as mitmproxy_io
from mitmproxy.http import HTTPFlow

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output"
NO_SCRUB_FLOWS = OUTPUT_DIR / "no_scrub_flows.mitm"
SCRUB_FLOWS = OUTPUT_DIR / "scrub_flows.mitm"

TEST_STRING = "In 2 sentences what is the Bill of Rights?"


def decompress_body(content: bytes) -> str:
    """Decompress gzipped content and return as string."""
    if not content:
        return ""
    try:
        return gzip.decompress(content).decode("utf-8", errors="replace")
    except Exception:
        try:
            return content.decode("utf-8", errors="replace")
        except Exception:
            return ""


def extract_snippet(body: str, search: str, context: int = 150) -> str:
    """Extract a snippet around the search string."""
    idx = body.lower().find(search.lower())
    if idx == -1:
        return ""
    start = max(0, idx - context)
    end = min(len(body), idx + len(search) + context)
    return body[start:end]


def analyze_flow_file(flow_file: Path) -> list[dict]:
    """Analyze a mitmproxy flow file and extract relevant information."""
    results = []

    if not flow_file.exists():
        return results

    with open(flow_file, "rb") as f:
        reader = mitmproxy_io.FlowReader(f)
        for flow in reader.stream():
            if not isinstance(flow, HTTPFlow):
                continue

            # Only analyze Logfire traffic
            if "logfire" not in flow.request.host.lower():
                continue

            # Only analyze POST requests (traces/metrics)
            if flow.request.method != "POST":
                continue

            body = decompress_body(flow.request.content)
            found = TEST_STRING.lower() in body.lower()
            snippet = extract_snippet(body, TEST_STRING) if found else ""

            results.append({
                "url": flow.request.pretty_url,
                "method": flow.request.method,
                "content_length": len(flow.request.content),
                "found": found,
                "snippet": snippet,
            })

    return results


def generate_before_md(results: list[dict]) -> str:
    """Generate BEFORE.md content."""
    lines = [
        "# BEFORE: Traffic Without Scrubbing",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "This shows telemetry sent to Logfire **without** scrubbing enabled.",
        "",
        f"**Test String:** `{TEST_STRING}`",
        "",
        "---",
        "",
        "## Captured Logfire Traffic",
        "",
    ]

    found_any = False
    for r in results:
        lines.append(f"### POST {r['url'].split('/')[-1]}")
        lines.append("")

        if r["found"]:
            found_any = True
            lines.append("**:warning: SENSITIVE DATA FOUND IN PAYLOAD**")
            lines.append("")
            lines.append("```")
            lines.append(f"...{r['snippet']}...")
            lines.append("```")
        else:
            lines.append(":white_check_mark: Test string not in this request")

        lines.append("")
        lines.append(f"Size: {r['content_length']} bytes (compressed)")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.extend([
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Logfire requests | {len(results)} |",
        f"| Requests with sensitive data | {sum(1 for r in results if r['found'])} |",
        "",
    ])

    if found_any:
        lines.extend([
            "**:x: PROBLEM:** Without scrubbing, your LLM prompts and responses",
            "are being transmitted to Logfire in plaintext.",
        ])

    return "\n".join(lines)


def generate_after_md(results: list[dict]) -> str:
    """Generate AFTER.md content."""
    lines = [
        "# AFTER: Traffic With Scrubbing Enabled",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "This shows telemetry sent to Logfire **with** scrubbing enabled.",
        "",
        f"**Test String:** `{TEST_STRING}`",
        "",
        "## Scrubbing Configuration",
        "",
        "```python",
        "logfire.configure(",
        '    send_to_logfire="if-token-present",',
        '    scrubbing=logfire.ScrubbingOptions(extra_patterns=[".*"]),',
        ")",
        "logfire.instrument_pydantic_ai(include_content=False)",
        "```",
        "",
        "---",
        "",
        "## Captured Logfire Traffic",
        "",
    ]

    for r in results:
        lines.append(f"### POST {r['url'].split('/')[-1]}")
        lines.append("")

        if r["found"]:
            lines.append("**:x: UNEXPECTED:** Test string found!")
            lines.append("")
            lines.append("```")
            lines.append(f"...{r['snippet']}...")
            lines.append("```")
        else:
            lines.append(":white_check_mark: Test string NOT found (scrubbed)")

        lines.append("")
        lines.append(f"Size: {r['content_length']} bytes (compressed)")
        lines.append("")
        lines.append("---")
        lines.append("")

    found_count = sum(1 for r in results if r["found"])

    lines.extend([
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Logfire requests | {len(results)} |",
        f"| Requests with sensitive data | {found_count} |",
        "",
    ])

    if found_count == 0:
        lines.extend([
            "**:white_check_mark: SUCCESS:** With scrubbing enabled, your LLM prompts",
            "and responses are NOT transmitted to Logfire. You still get observability",
            "(traces, metrics, latency) without exposing sensitive content.",
        ])
    else:
        lines.extend([
            "**:x: FAILURE:** Some sensitive data was still found. Check configuration.",
        ])

    return "\n".join(lines)


def main():
    # Analyze both flow files
    before_results = analyze_flow_file(NO_SCRUB_FLOWS)
    after_results = analyze_flow_file(SCRUB_FLOWS)

    # Generate markdown reports
    before_md = generate_before_md(before_results)
    after_md = generate_after_md(after_results)

    # Write to output directory
    OUTPUT_DIR.mkdir(exist_ok=True)

    (OUTPUT_DIR / "BEFORE.md").write_text(before_md)
    (OUTPUT_DIR / "AFTER.md").write_text(after_md)


if __name__ == "__main__":
    main()
