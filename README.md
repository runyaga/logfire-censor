# Logfire Scrubbing Proof-of-Concept

Demonstrates that Logfire's scrubbing feature prevents sensitive LLM prompt/response data from being transmitted to Logfire's telemetry backend.

## What This Proves

| Scenario | Network Traffic | Logfire API |
|----------|-----------------|-------------|
| Without scrubbing | Prompt/response **VISIBLE** | Prompt/response **VISIBLE** |
| With scrubbing | Prompt/response **HIDDEN** | Prompt/response **HIDDEN** |

The test validates scrubbing at two levels:
1. **Network level** - mitmproxy captures raw HTTPS traffic
2. **API level** - Queries Logfire directly to verify stored data

## Quick Start

### 1. Prerequisites

- **Python 3.10+**
- **mitmproxy** - installed automatically via `requirements.txt`

Alternatively, install mitmproxy system-wide (optional):
```bash
# macOS
brew install mitmproxy

# Linux (Debian/Ubuntu)
sudo apt install mitmproxy

# Linux (Fedora/RHEL)
sudo dnf install mitmproxy
```

### 2. Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/logfire-censor.git
cd logfire-censor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your tokens (see Environment Variables below)
```

### 3. Run the Test

**Ensure your virtual environment is still active** before running the script:

```bash
chmod +x run_test.sh
./run_test.sh
```

The script automatically:
- Generates mitmproxy CA certificate on first run
- Runs tests with and without scrubbing
- Validates via network capture AND Logfire API

### 4. View Results

After the test completes:

```
output/
├── BEFORE.md           # Traffic WITHOUT scrubbing (shows exposed data)
├── AFTER.md            # Traffic WITH scrubbing (data is hidden)
├── no_scrub_flows.mitm # Raw mitmproxy capture (baseline)
└── scrub_flows.mitm    # Raw mitmproxy capture (scrubbed)
```

## Environment Variables

Configure these in your `.env` file:

| Variable | Required | Description |
|----------|----------|-------------|
| `LOGFIRE_TOKEN` | **Yes** | Write token for sending telemetry to Logfire |
| `GOOGLE_API_KEY` | **Yes** | Google AI API key for Gemini LLM |
| `LOGFIRE_READ_TOKEN` | **Yes** | Read token for querying Logfire API to validate results |

Get your tokens:
- **Logfire tokens:** [logfire.pydantic.dev](https://logfire.pydantic.dev) → Project Settings → Tokens
  - Create both a **Write token** (`LOGFIRE_TOKEN`) and **Read token** (`LOGFIRE_READ_TOKEN`)
- **Google API key:** [aistudio.google.com](https://aistudio.google.com/apikey)

## How It Works

```
┌──────────────┐     HTTPS_PROXY      ┌───────────┐      HTTPS       ┌─────────┐
│ Python Demo  │ ──────────────────▶  │ mitmproxy │ ───────────────▶ │ Logfire │
│ (pydantic-ai)│                      │  :8080    │                  │   API   │
└──────────────┘                      └───────────┘                  └─────────┘
       │                                    │                              │
       │                                    ▼                              │
       │                              Captured traffic                     │
       │                              analyzed for test string             │
       │                                                                   │
       │                              ┌───────────────────┐                │
       └─────────────────────────────▶│ validate_logfire  │◀───────────────┘
                                      │   (Query API)     │
                                      └───────────────────┘
```

**Phase 1:** Run LLM query WITHOUT scrubbing → capture network traffic
**Phase 2:** Run LLM query WITH scrubbing → capture network traffic
**Phase 3:** Analyze mitmproxy captures for test string
**Phase 4:** Query Logfire API to verify scrubbing in stored data

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
├── run_test.sh         # Main entry point - runs the full 4-phase test
├── demo.py             # LLM query script (scrub/no-scrub modes)
├── analyze_flows.py    # Analyzes mitmproxy captures for test string
├── validate_logfire.py # Queries Logfire API to validate scrubbing
├── generate_report.py  # Creates BEFORE.md and AFTER.md reports
├── requirements.txt    # Python dependencies
├── .env.example        # Template for credentials
└── output/             # Generated results (git-ignored)
```

## Troubleshooting

**Port 8080 in use:**
```
Failed to start mitmproxy
```
Kill any process using port 8080:
```bash
# macOS/Linux
lsof -i :8080 | awk 'NR>1 {print $2}' | xargs kill

# Alternative (Linux)
fuser -k 8080/tcp

# Windows (run in PowerShell as Admin)
netstat -ano | findstr :8080
# Then kill using the PID from output:
taskkill /PID <PID> /F
```

**Missing dependencies:**
```bash
pip install -r requirements.txt
```

**Permission denied on run_test.sh:**
```bash
chmod +x run_test.sh
```

**Logfire API validation fails:**
- Ensure `LOGFIRE_READ_TOKEN` is set in `.env`
- Verify the read token has access to the same project as the write token
- Check that telemetry is being sent (baseline test should pass first)
