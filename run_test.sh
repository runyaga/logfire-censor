#!/bin/bash
#
# Logfire Scrubbing Validation Test
#
# Demonstrates that Logfire scrubbing prevents sensitive LLM prompt/response
# data from being sent to the Logfire telemetry backend.
#
# Usage: ./run_test.sh
#
# Output: Results are written to the output/ directory
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
TEST_STRING="In 2 sentences what is the Bill of Rights?"
PROXY_PORT=8080
OUTPUT_DIR="$SCRIPT_DIR/output"
NO_SCRUB_FLOWS="$OUTPUT_DIR/no_scrub_flows.mitm"
SCRUB_FLOWS="$OUTPUT_DIR/scrub_flows.mitm"
MITMPROXY_CA="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"
COMBINED_CA="$OUTPUT_DIR/combined-ca-bundle.pem"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }
echo_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
echo_fail() { echo -e "${RED}[FAIL]${NC} $1"; }

cleanup() {
    if [ -n "$MITM_PID" ] && kill -0 "$MITM_PID" 2>/dev/null; then
        kill "$MITM_PID" 2>/dev/null || true
        wait "$MITM_PID" 2>/dev/null || true
    fi
    rm -f "$COMBINED_CA"
}
trap cleanup EXIT

setup_output_dir() {
    mkdir -p "$OUTPUT_DIR"
    rm -f "$NO_SCRUB_FLOWS" "$SCRUB_FLOWS"
    rm -f "$OUTPUT_DIR/BEFORE.md" "$OUTPUT_DIR/AFTER.md"
}

setup_ca_bundle() {
    echo_info "Setting up SSL certificates..."
    SYSTEM_CA=$(python3 -c "import certifi; print(certifi.where())" 2>/dev/null || echo "/etc/ssl/cert.pem")

    if [ ! -f "$SYSTEM_CA" ]; then
        echo_fail "System CA bundle not found at $SYSTEM_CA"
        exit 1
    fi

    if [ ! -f "$MITMPROXY_CA" ]; then
        echo_fail "mitmproxy CA not found. Run 'mitmdump' once to generate it."
        exit 1
    fi

    cat "$SYSTEM_CA" "$MITMPROXY_CA" > "$COMBINED_CA"
}

check_deps() {
    echo_info "Checking dependencies..."

    local missing=0

    if ! command -v mitmdump &> /dev/null; then
        echo_fail "mitmdump not found. Install: brew install mitmproxy"
        missing=1
    fi

    if ! python3 -c "import pydantic_ai" 2>/dev/null; then
        echo_fail "pydantic-ai not installed"
        missing=1
    fi

    if ! python3 -c "import logfire" 2>/dev/null; then
        echo_fail "logfire not installed"
        missing=1
    fi

    if [ "$missing" -eq 1 ]; then
        echo ""
        echo "Install dependencies: pip install -r requirements.txt"
        exit 1
    fi

    echo_pass "All dependencies found"
}

start_proxy() {
    local flow_file="$1"
    mitmdump -p "$PROXY_PORT" -w "$flow_file" --set flow_detail=0 -q &
    MITM_PID=$!
    sleep 2

    if ! kill -0 "$MITM_PID" 2>/dev/null; then
        echo_fail "Failed to start mitmproxy"
        exit 1
    fi
}

stop_proxy() {
    if [ -n "$MITM_PID" ] && kill -0 "$MITM_PID" 2>/dev/null; then
        kill "$MITM_PID" 2>/dev/null || true
        wait "$MITM_PID" 2>/dev/null || true
        MITM_PID=""
        sleep 1
    fi
}

run_demo() {
    local mode="$1"
    export HTTPS_PROXY="http://localhost:$PROXY_PORT"
    export HTTP_PROXY="http://localhost:$PROXY_PORT"
    export SSL_CERT_FILE="$COMBINED_CA"
    export REQUESTS_CA_BUNDLE="$COMBINED_CA"

    python3 demo.py --mode "$mode"

    unset HTTPS_PROXY HTTP_PROXY SSL_CERT_FILE REQUESTS_CA_BUNDLE
}

analyze() {
    local flow_file="$1"
    local expectation="$2"
    python3 analyze_flows.py "$flow_file" "$TEST_STRING" "$expectation" -v
}

generate_reports() {
    echo_info "Generating traffic reports..."
    python3 generate_report.py
    echo_pass "Reports written to output/BEFORE.md and output/AFTER.md"
}

main() {
    echo ""
    echo -e "${BOLD}=============================================="
    echo "  Logfire Scrubbing Validation Test"
    echo -e "==============================================${NC}"
    echo ""

    check_deps
    setup_output_dir
    setup_ca_bundle

    # Phase 1: Baseline
    echo ""
    echo -e "${BOLD}--- Phase 1: Capture WITHOUT Scrubbing ---${NC}"
    echo ""
    start_proxy "$NO_SCRUB_FLOWS"
    echo_info "Running LLM query (no scrubbing)..."
    run_demo "no-scrub"
    stop_proxy

    # Phase 2: Scrubbed
    echo ""
    echo -e "${BOLD}--- Phase 2: Capture WITH Scrubbing ---${NC}"
    echo ""
    start_proxy "$SCRUB_FLOWS"
    echo_info "Running LLM query (with scrubbing)..."
    run_demo "scrub"
    stop_proxy

    # Phase 3: Analysis
    echo ""
    echo -e "${BOLD}--- Phase 3: Analyze Captured Traffic ---${NC}"
    echo ""

    BASELINE_OK=0
    SCRUB_OK=0

    echo "[Test 1] Baseline: expect test string in traffic"
    if analyze "$NO_SCRUB_FLOWS" "--expect-found"; then
        BASELINE_OK=1
    fi

    echo ""
    echo "[Test 2] Scrubbed: expect NO test string in traffic"
    if analyze "$SCRUB_FLOWS" "--expect-not-found"; then
        SCRUB_OK=1
    fi

    # Generate markdown reports
    echo ""
    generate_reports

    # Results
    echo ""
    echo -e "${BOLD}=============================================="
    echo "  RESULTS"
    echo -e "==============================================${NC}"
    echo ""

    if [ "$BASELINE_OK" -eq 1 ] && [ "$SCRUB_OK" -eq 1 ]; then
        echo_pass "ALL TESTS PASSED"
        echo ""
        echo "  Baseline: Prompt/response FOUND in telemetry (as expected)"
        echo "  Scrubbed: Prompt/response NOT found in telemetry (as expected)"
        echo ""
        echo "  View results:"
        echo "    - output/BEFORE.md  (traffic without scrubbing)"
        echo "    - output/AFTER.md   (traffic with scrubbing)"
        echo ""
        echo -e "${GREEN}Conclusion: Logfire scrubbing is working correctly!${NC}"
        exit 0
    else
        echo_fail "SOME TESTS FAILED"
        [ "$BASELINE_OK" -eq 0 ] && echo "  - Baseline: expected to find test string"
        [ "$SCRUB_OK" -eq 0 ] && echo "  - Scrubbed: test string should NOT be found"
        exit 1
    fi
}

main "$@"
