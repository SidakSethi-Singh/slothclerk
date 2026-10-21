import json
from app.models import (
    AnalysisPartA,
    AnalysisPartB,
    DocumentAnalysisResponse,
    Citation,
    KeyDate,
    MoneyAmount,
    Obligation,
    RedFlag,
    ActionItem,
    AnalysisMetrics,
    RedFlagsResponse,
    ActionChecklistResponse,
)


def test_schema_part_a():
    sample_a = {
        "summary": "This is a mutual NDA governing confidentiality terms.",
        "summary_citation": {
            "chunk_id": "chunk_1",
            "quote": "MUTUAL NON-DISCLOSURE AGREEMENT",
            "verified": True
        },
        "key_dates": [
            {
                "date": "November 15, 2026",
                "description": "Effective Date",
                "citation": {"chunk_id": "chunk_1", "quote": "Effective Date: November 15, 2026", "verified": True}
            }
        ],
        "money_amounts": [
            {
                "amount": "$150,000 USD",
                "context": "Liquidated damages for breach",
                "citation": {"chunk_id": "chunk_1", "quote": "liquidated damages amounting to $150,000 USD", "verified": True}
            }
        ],
        "obligations": [
            {
                "party": "Receiving Party",
                "duty": "Maintain confidentiality for 5 years",
                "citation": {"chunk_id": "chunk_1", "quote": "maintain all Confidential Information", "verified": True}
            }
        ]
    }
    part_a = AnalysisPartA.model_validate(sample_a)
    assert part_a.summary.startswith("This is a mutual NDA")
    assert len(part_a.key_dates) == 1
    assert len(part_a.money_amounts) == 1
    assert len(part_a.obligations) == 1


def test_schema_part_b():
    sample_b = {
        "red_flags": [
            {
                "issue": "High liquidated damages clause",
                "severity": "high",
                "risk_explanation": "Imposes $150,000 fixed penalty without requiring proof of actual harm.",
                "citation": {"chunk_id": "chunk_1", "quote": "liquidated damages amounting to $150,000", "verified": True}
            }
        ],
        "action_checklist": [
            {
                "action": "Ensure secure document shredding protocol by December 31, 2027",
                "deadline": "December 31, 2027",
                "assignee": "Compliance Officer",
                "citation": {"chunk_id": "chunk_2", "quote": "destroy or return all materials within fourteen", "verified": True}
            }
        ]
    }
    part_b = AnalysisPartB.model_validate(sample_b)
    assert len(part_b.red_flags) == 1
    assert part_b.red_flags[0].severity == "high"
    assert len(part_b.action_checklist) == 1


def test_split_schemas_b1_and_b2():
    rf_data = {
        "red_flags": [
            {
                "issue": "Unconditional repossession",
                "severity": "high",
                "risk_explanation": "Landlord can terminate on 7 days notice",
                "citation": {"chunk_id": "chunk_1", "quote": "unconditional right to repossess", "verified": True}
            }
        ]
    }
    rf_resp = RedFlagsResponse.model_validate(rf_data)
    assert len(rf_resp.red_flags) == 1

    act_data = {
        "action_checklist": [
            {
                "action": "Pay security deposit",
                "deadline": "Upon signing",
                "assignee": "Tenant",
                "citation": {"chunk_id": "chunk_1", "quote": "Security Deposit of $17,000", "verified": True}
            }
        ]
    }
    act_resp = ActionChecklistResponse.model_validate(act_data)
    assert len(act_resp.action_checklist) == 1


def test_full_document_analysis_response():
    resp = DocumentAnalysisResponse(
        doc_id="doc_123",
        filename="test.docx",
        summary="Executive summary text",
        summary_citation=Citation(chunk_id="chunk_1", quote="Quote text", verified=True),
        key_dates=[],
        money_amounts=[],
        obligations=[],
        red_flags=[],
        action_checklist=[],
        metrics=AnalysisMetrics(
            latency_ms=150.2,
            prompt_tokens=450,
            completion_tokens=220,
            total_tokens=670,
            model_name="gemma3:4b"
        ),
        chunks_count=3
    )
    json_data = resp.model_dump_json()
    assert "doc_123" in json_data
    assert "gemma3:4b" in json_data
