#!/usr/bin/env python3
"""
Logfire Scrubbing Demo

Demonstrates that logfire scrubbing prevents sensitive LLM prompt/response
data from being sent to the Logfire telemetry backend.

Usage:
    python demo.py --mode no-scrub  # Baseline: data IS sent
    python demo.py --mode scrub     # Scrubbed: data is NOT sent
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from local .env file
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

import logfire
from pydantic_ai import Agent

# Test prompt - this is what we'll search for in the captured traffic
TEST_PROMPT = "In 2 sentences what is the Bill of Rights?"


def configure_logfire(mode: str) -> None:
    """Configure logfire based on the scrubbing mode."""
    scrubbing_enabled = mode == "scrub"

    if scrubbing_enabled:
        # Enable aggressive scrubbing - pattern ".*" matches everything
        logfire.configure(
            send_to_logfire="if-token-present",
            scrubbing=logfire.ScrubbingOptions(extra_patterns=[".*"]),
        )
        # Instrument pydantic-ai without content logging
        logfire.instrument_pydantic_ai(include_content=False)
        print("[SCRUB MODE] Logfire configured with full scrubbing enabled")
    else:
        # No scrubbing - baseline to show data IS normally sent
        logfire.configure(send_to_logfire="if-token-present")
        # Instrument pydantic-ai WITH content logging (default)
        logfire.instrument_pydantic_ai(include_content=True)
        print("[NO-SCRUB MODE] Logfire configured without scrubbing")

    # Log a span showing scrubbing configuration
    with logfire.span("scrubbing configured", scrubbing_enabled=scrubbing_enabled, mode=mode):
        logfire.info("will scrub content" if scrubbing_enabled else "content will pass through")


def run_llm_query() -> str:
    """Run a query against Gemini using pydantic-ai."""
    # Create agent with Gemini model
    agent = Agent(
        "google-gla:gemini-2.0-flash",
        system_prompt="You are a helpful assistant. Be concise.",
    )

    print(f"Sending prompt: {TEST_PROMPT}")

    with logfire.span("llm query", prompt_length=len(TEST_PROMPT)):
        # Check for sensitive content (demonstration)
        has_sensitive_words = any(
            word in TEST_PROMPT.lower()
            for word in ["bill", "rights", "constitution"]
        )
        with logfire.span("content check", has_sensitive_words=has_sensitive_words):
            if has_sensitive_words:
                logfire.info("prompt has sensitive words")
            else:
                logfire.info("prompt appears safe")

        # Run the query synchronously
        result = agent.run_sync(TEST_PROMPT)

    print(f"Response: {result.output}")
    return result.output


def main():
    parser = argparse.ArgumentParser(
        description="Logfire scrubbing demonstration"
    )
    parser.add_argument(
        "--mode",
        choices=["scrub", "no-scrub"],
        required=True,
        help="Scrubbing mode: 'scrub' enables full scrubbing, 'no-scrub' is baseline",
    )
    args = parser.parse_args()

    # Verify required env vars
    if not os.getenv("LOGFIRE_TOKEN"):
        print("ERROR: LOGFIRE_TOKEN not found in environment", file=sys.stderr)
        sys.exit(1)
    if not os.getenv("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not found in environment", file=sys.stderr)
        sys.exit(1)

    print(f"Using env file: {ENV_PATH}")
    print(f"LOGFIRE_TOKEN: {os.getenv('LOGFIRE_TOKEN')[:20]}...")
    print(f"GOOGLE_API_KEY: {os.getenv('GOOGLE_API_KEY')[:10]}...")

    # Configure logfire based on mode
    configure_logfire(args.mode)

    # Run the LLM query
    response = run_llm_query()

    # Force flush all telemetry before exit
    print("Flushing telemetry...")
    logfire.shutdown()

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
