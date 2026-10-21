# SlothClerk 🦥📄

**100% Offline, Privacy-First Document Assistant**

SlothClerk processes sensitive documents (contracts, NDAs, leases, MSAs) locally with **zero external cloud API requests**, telemetry disabled, and strictly grounded citations verified against the source text.

---

## 🌟 Key Features

- **100% Offline & Private**: Powered by local Ollama models (`gemma3:4b` and `nomic-embed-text`) with ChromaDB telemetry completely disabled.
- **Verifiable Citations**: Every claim, date, obligation, and red flag is linked to a source chunk and verified verbatim against the document text.
- **Deterministic Clause Scanner**: Pre-scans high-signal legal clauses (e.g. repossession, waivers of jury trial, automatic renewal, liquidated damages, penalties) before LLM synthesis.
- **Unified Analysis Engine**: The CLI tool (`cli.py`) and Web API (`/api/analyze`) use the exact same extraction and verification pipeline.
- **Full-Featured Modern Web UI**: Single-page application with drag-and-drop document upload, live health check status, structured cards for Key Dates, Monetary Amounts, Obligations, and Red Flags, interactive citation popover, and follow-up RAG chat.

---

## 📂 Project Structure

```text
├── app/
│   ├── config.py             # Settings and offline guardrails
│   ├── main.py               # FastAPI application & endpoints
│   ├── models.py             # Pydantic schemas for structured extraction
│   ├── services/
│   │   ├── analyzer.py       # Multi-stage analyzer & verification engine
│   │   ├── chunker.py        # Boundary-aware sentence & paragraph chunking
│   │   ├── extractor.py      # PDF & DOCX text extraction
│   │   ├── ollama_client.py  # Local Ollama integration
│   │   └── vector_store.py   # Local ChromaDB vector database
│   └── static/
│       └── index.html        # Interactive Single-Page Web UI
├── samples/                  # Realistic anonymized contracts for testing
├── tests/                    # Unit, regression, and API verification tests
├── cli.py                    # Standalone CLI document analysis tool
├── create_samples.py         # Sample contract generator
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
python cli.py --file samples/nda_agreement.docx
python cli.py --file samples/commercial_lease.pdf
python cli.py --file samples/saas_msa.docx
```

### 4. Running the Web Application

```bash
uvicorn app.main:app --reload --port 8000
```
Open your browser at `http://localhost:8000` to access the SlothClerk Web UI.

---

## 🧪 Testing

Run the test suite using pytest:

```bash
pytest
```
