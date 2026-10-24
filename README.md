# SlothClerk 🦥📄

**100% Offline, Privacy-First Document Assistant**

SlothClerk processes sensitive documents (contracts, NDAs, leases, MSAs) locally with **zero external cloud API requests**, telemetry disabled, and strictly grounded citations verified against the source text.

---

## 🌟 Key Features

- **100% Offline & Private**: Powered by local Ollama models (`gemma3:4b` and `nomic-embed-text`) with ChromaDB telemetry completely disabled.
- **Verifiable Citations**: Every claim, date, obligation, and red flag is linked to a source chunk and verified verbatim against the document text.
- **Deterministic Clause Scanner**: Pre-scans high-signal legal clauses (e.g. repossession, waivers of jury trial, automatic renewal, liquidated damages, penalties) before LLM synthesis (~69,000+ chars/sec).
- **📊 Cloud vs Local Benchmark Suite**: Quantitative performance and cost comparison against OpenAI GPT-4o, Claude 3.5 Sonnet, and GPT-4o-mini (`python benchmark.py`, `cli.py --benchmark`, or `GET /api/benchmark`).
- **🎙️ ElevenLabs Voice Executive Briefing**: Spoken audio briefings of contract summaries and critical red flags powered by ElevenLabs text-to-speech with seamless offline browser Web Speech API fallback.
- **🛡️ Contract Risk Score Gauge (0-100)**: Visual risk gauge evaluating overall agreement exposure across repossession, penalties, and uncapped liabilities.
- **☁️ Render Hosting Ready**: Pre-configured `render.yaml` blueprint, containerized `Dockerfile`, and automated cloud demo fallback mode for one-click deployment.
- **🌐 SlothClerk.tech Showcase Landing Page**: Dedicated `.tech` marketing and technical showcase page (`/landing`) with interactive ROI calculators.
- **Unified Analysis Engine**: Standalone CLI tool (`cli.py`) and Web API (`/api/analyze`) use the exact same extraction and verification pipeline.

---

## 📂 Project Structure

```text
├── app/
│   ├── config.py             # Settings and offline guardrails
│   ├── main.py               # FastAPI application & endpoints
│   ├── models.py             # Pydantic schemas for structured extraction
│   ├── services/
│   │   ├── analyzer.py       # Multi-stage analyzer & verification engine
│   │   ├── benchmark_service.py # Cloud vs local latency & ROI calculator
│   │   ├── chunker.py        # Boundary-aware sentence & paragraph chunking
│   │   ├── elevenlabs_client.py # ElevenLabs TTS & executive audio briefing
│   │   ├── exporter.py       # Markdown and JSON audit exporter
│   │   ├── extractor.py      # PDF & DOCX text extraction
│   │   ├── ollama_client.py  # Local Ollama integration
│   │   └── vector_store.py   # Local ChromaDB vector database
│   └── static/
│       ├── index.html        # Interactive Single-Page Web UI
│       └── landing.html      # SlothClerk.tech Showcase Landing Page
├── samples/                  # Realistic anonymized contracts for testing
├── tests/                    # Unit, regression, and API verification tests
├── benchmark.py              # Standalone CLI Cloud vs Local Benchmark Suite
├── cli.py                    # Standalone CLI document analysis tool
├── create_samples.py         # Sample contract generator
├── Dockerfile                # Containerfile for cloud / on-prem deployment
├── render.yaml               # Render Blueprint for 1-click cloud hosting
├── BENCHMARK.md              # Detailed empirical benchmark & ROI report
├── RENDER_DEPLOYMENT.md      # Render deployment guide
├── requirements.txt
└── README.md
```

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) installed locally:
  ```bash
  ollama pull gemma3:4b
  ollama pull nomic-embed-text
  ```

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/SidakSethi-Singh/slothclerk.git
cd slothclerk

# Create virtual environment and activate
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Running via CLI

```bash
# Analyze and print audit summary to terminal
python cli.py --file samples/nda_agreement.docx

# Export a clean, verifiable Markdown audit report
python cli.py --file samples/nda_agreement.docx --output audit_report.md

# Export structured JSON data for programmatic integrations
python cli.py --file samples/commercial_lease.pdf --output audit_report.json

# Run empirical Cloud vs Local offline benchmark & ROI suite
python cli.py --benchmark
# or
python benchmark.py
```

### 4. Running the Web Application

```bash
uvicorn app.main:app --reload --port 8000
```
- Open `http://localhost:8000` for the **SlothClerk Auditor Web App**.
- Open `http://localhost:8000/landing` for the **SlothClerk.tech Showcase**.

---

## ☁️ Deploying to Render

Deploy SlothClerk directly to [Render](https://render.com) using the included `render.yaml` blueprint:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

See [RENDER_DEPLOYMENT.md](file:///c:/Users/sidak/OneDrive/Desktop/HACKTOBER_FEST%20STAGE_3/RENDER_DEPLOYMENT.md) for step-by-step instructions.

---

## 🎙️ ElevenLabs Voice Integration

SlothClerk provides AI-spoken executive briefings of contract summaries and critical red flags:
- Set your `ELEVENLABS_API_KEY` in `.env`.
- When configured, high-clarity voice narration is streamed in real-time.
- If no key is configured or offline mode is forced, SlothClerk seamlessly falls back to the native browser Web Speech API.

---

## 🧪 Testing

Run the test suite using pytest:

```bash
pytest
```
