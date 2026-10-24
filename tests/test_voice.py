from fastapi.testclient import TestClient
from app.main import app
from app.services.elevenlabs_client import elevenlabs_client


def test_elevenlabs_script_builder():
    sample_analysis = {
        "filename": "nda_test.docx",
        "summary": "This is a mutual non-disclosure agreement.",
        "red_flags": [
            {"issue": "Indefinite Term", "severity": "high", "risk_explanation": "Obligations never expire."}
        ],
        "action_checklist": [
            {"action": "Sign NDA", "deadline": "Friday"}
        ],
        "key_dates": [
            {"date": "Nov 1, 2026", "description": "Effective Date"}
        ]
    }
    script = elevenlabs_client.build_briefing_script(sample_analysis)
    assert "Executive Legal Briefing for nda_test.docx" in script
    assert "mutual non-disclosure agreement" in script
    assert "Indefinite Term" in script
    assert "Sign NDA" in script
    assert "End of SlothClerk executive briefing" in script


def test_api_voice_briefing_endpoint():
    client = TestClient(app)
    sample_analysis = {
        "filename": "lease.pdf",
        "summary": "Office lease agreement.",
        "red_flags": [],
        "action_checklist": [],
        "key_dates": []
    }
    resp = client.post("/api/voice/briefing", json={"analysis": sample_analysis})
    assert resp.status_code == 200
    data = resp.json()
    assert "script" in data
    assert "provider" in data
    assert "Executive Legal Briefing for lease.pdf" in data["script"]


def test_api_voice_tts_fallback_endpoint():
    client = TestClient(app)
    resp = client.post("/api/voice/tts", json={"text": "Hello world testing TTS"})
    assert resp.status_code == 200
    data = resp.json()
    assert "has_audio" in data


def test_api_samples_endpoint():
    client = TestClient(app)
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert "samples" in data
    assert len(data["samples"]) >= 1


def test_landing_page_endpoint():
    client = TestClient(app)
    resp = client.get("/landing")
    assert resp.status_code == 200
    assert "SlothClerk.tech" in resp.text
