import os
import json
import sys
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    DocumentAnalysisResponse,
    Citation,
    KeyDate,
    MoneyAmount,
    Obligation,
    RedFlag,
    ActionItem,
    AnalysisMetrics,
)
from app.services.exporter import export_markdown, export_json


def create_mock_analysis_response() -> DocumentAnalysisResponse:
    return DocumentAnalysisResponse(
        doc_id="test_doc_001",
        filename="sample_commercial_lease.pdf",
        summary="Subtenant leases Suite 400 with base monthly rent of $8,500 USD and $17,000 USD deposit.",
        summary_citation=Citation(
            chunk_id="chunk_1",
            quote="This Sublease Agreement is entered into as of February 1, 2026.",
            verified=True
        ),
        key_dates=[
            KeyDate(
                date="March 1, 2026",
                description="Lease Commencement Date",
                citation=Citation(chunk_id="chunk_1", quote="The initial term commences on March 1, 2026.", verified=True)
            )
        ],
        money_amounts=[
            MoneyAmount(
                amount="$8,500 USD",
                context="Monthly base rent payable on the first day of each calendar month.",
                citation=Citation(chunk_id="chunk_2", quote="Monthly Base Rent: Subtenant agrees to pay base monthly rent of $8,500 USD.", verified=True)
            )
        ],
        obligations=[
            Obligation(
                party="Subtenant",
                duty="Maintain interior premises in neat and sanitary condition.",
                citation=Citation(chunk_id="chunk_4", quote="Subtenant shall maintain the interior premises in neat and sanitary condition.", verified=True)
            )
        ],
        red_flags=[
            RedFlag(
                issue="Special Unconditional Repossession",
                category="repossession",
                severity="high",
                risk_explanation="Sublessor can repossess without refunding unamortized improvements on 7 days notice.",
                citation=Citation(chunk_id="chunk_6", quote="Sublessor reserves unconditional right to repossess premises upon 7 days notice.", verified=True)
            )
        ],
        action_checklist=[
            ActionItem(
                action="Pay refundable security deposit",
                deadline="Upon signing",
                assignee="Subtenant",
                citation=Citation(chunk_id="chunk_2", quote="A refundable Security Deposit of $17,000 USD is due upon signing.", verified=True)
            )
        ],
        metrics=AnalysisMetrics(
            model_name="gemma3:4b",
            latency_ms=1250,
            stage_a_latency_ms=600,
            stage_b1_latency_ms=350,
            stage_b2_latency_ms=300,
            stage_b_latency_ms=650,
            stage_b_status="success",
            prompt_tokens=420,
            completion_tokens=180,
            total_tokens=600,
            verbatim_verified_citations=6,
            fuzzy_repaired_citations=0,
            dropped_citations=0,
            duplicates_removed=0,
            headings_rejected=0,
            ungrounded_dates_nulled=0,
            dropped_audit_log=[]
        ),
        chunks_count=6
    )


def test_export_markdown_formatting():
    resp = create_mock_analysis_response()
    md = export_markdown(resp)

    # Core headers and metadata
    assert "# SlothClerk Audit Report: sample_commercial_lease.pdf" in md
    assert "**Document Name:** `sample_commercial_lease.pdf`" in md
    assert "**Document ID:** `test_doc_001`" in md
    assert "100.0%" in md

    # Executive Summary
    assert "## Executive Summary" in md
    assert "Suite 400" in md
    assert "[chunk_1]" in md

    # Red Flags
    assert "## Critical Red Flags & Risk Audit (1)" in md
    assert "**[HIGH]** Special Unconditional Repossession" in md
    assert "[chunk_6]" in md

    # Dates, Amounts, Obligations
    assert "## Key Dates & Milestones (1)" in md
    assert "March 1, 2026" in md
    assert "## Monetary Amounts & Financial Commitments (1)" in md
    assert "$8,500 USD" in md
    assert "## Contractual Obligations & Duties (1)" in md
    assert "Subtenant" in md

    # Checklist
    assert "## Action Checklist (1)" in md
    assert "- [ ] **Pay refundable security deposit**" in md
    assert "Upon signing" in md


def test_export_json_validity():
    resp = create_mock_analysis_response()
    raw_json = export_json(resp)
    parsed = json.loads(raw_json)

    assert parsed["doc_id"] == "test_doc_001"
    assert parsed["filename"] == "sample_commercial_lease.pdf"
    assert parsed["chunks_count"] == 6
    assert len(parsed["red_flags"]) == 1
    assert parsed["red_flags"][0]["severity"] == "high"


def test_api_export_endpoints():
    client = TestClient(app)
    resp = create_mock_analysis_response()
    payload = json.loads(resp.model_dump_json())

    # 1. Markdown endpoint
    res_md = client.post("/api/export/markdown", json=payload)
    assert res_md.status_code == 200
    assert "text/markdown" in res_md.headers["content-type"]
    assert "sample_commercial_lease_audit_report.md" in res_md.headers["content-disposition"]
    assert "# SlothClerk Audit Report" in res_md.text

    # 2. JSON endpoint
    res_json = client.post("/api/export/json", json=payload)
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    assert "sample_commercial_lease_audit_report.json" in res_json.headers["content-disposition"]
    data = res_json.json()
    assert data["doc_id"] == "test_doc_001"


def test_cli_export_output(tmp_path: Path):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    # Test CLI exporting markdown to a temporary file
    out_md = tmp_path / "test_audit.md"
    cmd = [
        sys.executable,
        "cli.py",
        "--file", "samples/nda_agreement.docx",
        "--output", str(out_md),
        "--format", "markdown"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, f"CLI error: {proc.stderr}"
    assert out_md.exists(), "Markdown file not created by CLI"
    content = out_md.read_text(encoding="utf-8")
    assert "# SlothClerk Audit Report" in content
    assert "Executive Summary" in content

    # Test CLI exporting JSON to a temporary file
    out_json = tmp_path / "test_audit.json"
    cmd_json = [
        sys.executable,
        "cli.py",
        "--file", "samples/nda_agreement.docx",
        "--output", str(out_json),
        "--format", "json"
    ]
    proc_json = subprocess.run(cmd_json, capture_output=True, text=True, env=env)
    assert proc_json.returncode == 0, f"CLI JSON error: {proc_json.stderr}"
    assert out_json.exists(), "JSON file not created by CLI"
    parsed = json.loads(out_json.read_text(encoding="utf-8"))
    assert "doc_id" in parsed
    assert "summary" in parsed
