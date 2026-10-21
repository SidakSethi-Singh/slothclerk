from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.extractor import extract_document
from app.services.chunker import create_chunks
from cli import analyze_document

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["offline"] is True
    assert "ollama" in data
    assert "active_models" in data


def test_serve_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "SlothClerk" in response.text
    assert "Offline: Ollama connected" in response.text
    assert "Prioritized Action Checklist" in response.text


def test_samples_mounted():
    response = client.get("/samples/commercial_lease.pdf")
    assert response.status_code == 200


@pytest.mark.parametrize("sample_path", [
    "samples/nda_agreement.docx",
    "samples/commercial_lease.pdf",
    "samples/saas_msa.docx"
])
def test_browser_path_and_cli_return_identical_counts(sample_path: str, monkeypatch):
    from app.services.ollama_client import ollama_client
    monkeypatch.setattr(ollama_client, "check_connection", lambda: {"reachable": False, "has_llm": False})

    file_path = Path(sample_path)
    assert file_path.exists(), f"Sample file not found: {file_path}"

    # 1. Run via CLI function
    segments = extract_document(file_path)
    chunks = create_chunks(doc_id=f"cli_{file_path.stem}", segments=segments)
    cli_response = analyze_document(
        doc_id=f"cli_{file_path.stem}",
        filename=file_path.name,
        chunks=chunks
    )

    # 2. Run via Browser / API endpoint (/api/analyze)
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    mime_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    api_res = client.post(
        "/api/analyze",
        files={"file": (file_path.name, file_bytes, mime_type)}
    )
    assert api_res.status_code == 200, f"API analyze failed: {api_res.text}"
    api_data = api_res.json()

    # 3. Prove Key Dates, Money Amounts, Obligations are populated
    assert len(api_data["key_dates"]) > 0, f"Key Dates not populated for {sample_path}"
    assert len(api_data["money_amounts"]) > 0, f"Money Amounts not populated for {sample_path}"
    assert len(api_data["obligations"]) > 0, f"Obligations not populated for {sample_path}"

    # 4. Prove browser path and CLI return IDENTICAL COUNTS
    assert len(api_data["key_dates"]) == len(cli_response.key_dates), (
        f"Key dates count mismatch: API={len(api_data['key_dates'])}, CLI={len(cli_response.key_dates)}"
    )
    assert len(api_data["money_amounts"]) == len(cli_response.money_amounts), (
        f"Money amounts count mismatch: API={len(api_data['money_amounts'])}, CLI={len(cli_response.money_amounts)}"
    )
    assert len(api_data["obligations"]) == len(cli_response.obligations), (
        f"Obligations count mismatch: API={len(api_data['obligations'])}, CLI={len(cli_response.obligations)}"
    )
    assert len(api_data["red_flags"]) == len(cli_response.red_flags), (
        f"Red flags count mismatch: API={len(api_data['red_flags'])}, CLI={len(cli_response.red_flags)}"
    )
    assert len(api_data["action_checklist"]) == len(cli_response.action_checklist), (
        f"Action checklist count mismatch: API={len(api_data['action_checklist'])}, CLI={len(cli_response.action_checklist)}"
    )
    assert api_data["chunks_count"] == cli_response.chunks_count, (
        f"Chunks count mismatch: API={api_data['chunks_count']}, CLI={cli_response.chunks_count}"
    )
