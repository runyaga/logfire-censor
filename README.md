# Logfire Scrubbing Proof-of-Concept

Demonstrates that Logfire's scrubbing feature prevents sensitive LLM prompt/response data from being transmitted to Logfire's telemetry backend.

## What This Proves

| Scenario | Prompt Visible in Network Traffic? |
|----------|-----------------------------------|
| Without scrubbing | **YES** - prompts/responses sent in plaintext |
| With scrubbing | **NO** - content is scrubbed before transmission |

## Quick Start

### 1. Prerequisites

```bash
# Install mitmproxy (for traffic interception)
brew install mitmproxy

# Run once to generate CA certificate
mitmdump -p 8080 &
kill %1
```

### 2. Setup

```bash
# Clone and enter directory
cd logfire-censor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your LOGFIRE_TOKEN and GOOGLE_API_KEY
```

### 3. Run the Test

```bash
./run_test.sh
```

### 4. View Results

After the test completes, check the `output/` directory:

```
output/
├── BEFORE.md           # Traffic WITHOUT scrubbing (shows exposed data)
├── AFTER.md            # Traffic WITH scrubbing (data is hidden)
├── no_scrub_flows.mitm # Raw mitmproxy capture (baseline)
└── scrub_flows.mitm    # Raw mitmproxy capture (scrubbed)
```

## How It Works

```
┌──────────────┐     HTTPS_PROXY      ┌───────────┐      HTTPS       ┌─────────┐
│ Python Demo  │ ──────────────────▶  │ mitmproxy │ ───────────────▶ │ Logfire │
│ (pydantic-ai)│                      │  :8080    │                  │   API   │
└──────────────┘                      └───────────┘                  └─────────┘
                                            │
                                            ▼
                                      Captured traffic
                                      analyzed for test string
```

1. **Phase 1:** Run LLM query WITHOUT scrubbing → capture traffic
2. **Phase 2:** Run LLM query WITH scrubbing → capture traffic
3. **Phase 3:** Analyze both captures for the test prompt
4. **Generate:** Create BEFORE.md and AFTER.md showing the difference

## Scrubbing Configuration

The scrubbed version uses this configuration:

```python
import logfire

logfire.configure(
    send_to_logfire="if-token-present",
    scrubbing=logfire.ScrubbingOptions(extra_patterns=[".*"]),
)
logfire.instrument_pydantic_ai(include_content=False)
```

- `extra_patterns=[".*"]` - Scrubs all string content matching the pattern
- `include_content=False` - Prevents pydantic-ai from logging prompt/response content

## Files

```
.
├── run_test.sh         # Main entry point - runs the full test
├── demo.py             # LLM query script (scrub/no-scrub modes)
├── analyze_flows.py    # Analyzes mitmproxy captures for test string
├── generate_report.py  # Creates BEFORE.md and AFTER.md reports
├── requirements.txt    # Python dependencies
├── .env.example        # Template for credentials
└── output/             # Generated results (git-ignored)
```

## Troubleshooting

**SSL Certificate Error:**
```
mitmproxy CA not found
```
Run `mitmdump` once to generate the CA certificate at `~/.mitmproxy/`.

**Port 8080 in use:**
```
Failed to start mitmproxy
```
Kill any process using port 8080: `lsof -i :8080 | awk 'NR>1 {print $2}' | xargs kill`

**Missing dependencies:**
```
pip install -r requirements.txt
```
