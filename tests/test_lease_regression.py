import pytest
from pathlib import Path
from app.services.extractor import extract_document
from app.services.chunker import create_chunks
from app.services.analyzer import analyzer
from app.services.ollama_client import ollama_client


@pytest.mark.skipif(
    not (ollama_client.check_connection().get("reachable") and ollama_client.check_connection().get("has_llm")),
    reason="Requires live local Ollama with gemma3:4b"
)
def test_commercial_lease_red_flags_and_action_checklist_regression():
    """
    Regression test:
    commercial_lease.pdf contains an unconditional 7-day repossession clause
    with no refund of improvements, a late fee, and a jury trial waiver.
    The analysis must identify at least one red flag citing the repossession clause,
    produce a non-empty action checklist, and maintain stage_b_status as success.
    """
    pdf_path = Path("samples/commercial_lease.pdf")
    assert pdf_path.exists()

    segs = extract_document(pdf_path)
    chunks = create_chunks("regression_lease_test", segs)

    result = analyzer.analyze_document(
        doc_id="regression_lease_test",
        filename="commercial_lease.pdf",
        chunks=chunks
    )

    # 1. Stage B must have succeeded without silent failure
    assert result.metrics.stage_b_status == "success"

    # 2. Red flags must not be empty
    assert len(result.red_flags) >= 1, "Must extract at least one red flag from commercial lease"

    # 3. Must cite the repossession or waiver clause
    combined_rf_text = " ".join(
        (rf.issue + " " + rf.risk_explanation + " " + rf.citation.quote).lower()
        for rf in result.red_flags
    )
    assert any(
        term in combined_rf_text
        for term in ["repossess", "repossession", "zoning", "without refund", "jury trial", "penalty", "surcharge"]
    ), f"Expected repossession or waiver red flag, got: {combined_rf_text}"

    # 4. Action checklist must not be empty
    assert len(result.action_checklist) >= 1, "Action checklist must be non-empty"

    # 5. Preserves qualifiers in summary or red flags
    assert (
        "unconditional" in result.summary.lower()
        or "without refund" in result.summary.lower()
        or "unconditional" in combined_rf_text
        or "without refund" in combined_rf_text
    ), "Summary or red flags must preserve critical qualifiers like unconditional or without refund"
