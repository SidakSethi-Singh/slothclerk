from app.models import Citation
from app.services.analyzer import verify_citation


def test_citation_verifies_exact_match():
    chunk_lookup = {
        "chunk_1": "Receiving Party shall hold and maintain all Confidential Information in strictest confidence."
    }
    citation = Citation(
        chunk_id="chunk_1",
        quote="Confidential Information in strictest confidence",
        verified=True
    )
    result = verify_citation(citation, chunk_lookup)
    assert result.verified is True


def test_citation_verifies_normalized_whitespace_and_punctuation():
    chunk_lookup = {
        "chunk_1": "In the event of an intentional breach, Receiving Party pays $150,000 USD."
    }
    # Slight quote variation with punctuation/quotes
    citation = Citation(
        chunk_id="chunk_1",
        quote='"intentional breach, Receiving Party pays $150,000"',
        verified=True
    )
    result = verify_citation(citation, chunk_lookup)
    assert result.verified is True


def test_citation_flags_hallucinated_unverified_quote():
    chunk_lookup = {
        "chunk_1": "Receiving Party shall hold and maintain all Confidential Information."
    }
    # Hallucinated quote that does not appear in the chunk
    citation = Citation(
        chunk_id="chunk_1",
        quote="Customer is awarded an automatic refund of $5,000,000 immediately",
        verified=True
    )
    result = verify_citation(citation, chunk_lookup)
    assert result.verified is False


def test_citation_flags_nonexistent_chunk_id():
    chunk_lookup = {
        "chunk_1": "Some legitimate contract text."
    }
    citation = Citation(
        chunk_id="chunk_99",
        quote="Some legitimate contract text.",
        verified=True
    )
    result = verify_citation(citation, chunk_lookup)
    assert result.verified is False


def test_red_flag_quality_rejects_contradictory_renewal_and_speculation():
    from app.models import RedFlag
    from app.services.analyzer import validate_red_flag_quality

    # 1. Renewal flag without "renew" in quote must be rejected
    rf_bad_renewal = RedFlag(
        issue="Automatic Renewal Lock-In",
        category="auto_renewal",
        severity="medium",
        risk_explanation="Locks party into paying for additional years.",
        citation=Citation(chunk_id="chunk_1", quote="The term commences on March 1, 2026 and terminates on February 28, 2029.", verified=True)
    )
    is_valid, reason = validate_red_flag_quality(rf_bad_renewal, "doc text")
    assert is_valid is False
    assert "does not contain 'renew'" in reason

    # 2. Speculative words "implied" or "suggesting" must be rejected
    rf_speculative = RedFlag(
        issue="Automatic 24-Month Lock-In Renewal (Implied)",
        category="other",
        severity="medium",
        risk_explanation="The clause suggests an automatic renewal if not terminated.",
        citation=Citation(chunk_id="chunk_1", quote="Term terminates on February 28, 2029.", verified=True)
    )
    is_valid, reason = validate_red_flag_quality(rf_speculative, "doc text")
    assert is_valid is False
    assert "speculative wording" in reason

    # 3. Bilateral casualty boilerplate must be rejected
    rf_casualty = RedFlag(
        issue="Casualty Termination Trigger",
        category="other",
        severity="medium",
        risk_explanation="Allows termination upon damage to premises.",
        citation=Citation(chunk_id="chunk_1", quote="In the event of substantial damage, either party may terminate upon 20 days notice.", verified=True)
    )
    is_valid, reason = validate_red_flag_quality(rf_casualty, "doc text")
    assert is_valid is False
    assert "Bilateral standard boilerplate" in reason

    # 4. Overlap > 80% must be rejected
    rf_copy = RedFlag(
        issue="Repossession Right",
        category="termination",
        severity="high",
        risk_explanation="Sublessor reserves unconditional right to repossess premises upon 7 days notice.",
        citation=Citation(chunk_id="chunk_1", quote="Sublessor reserves unconditional right to repossess premises upon 7 days notice.", verified=True)
    )
    is_valid, reason = validate_red_flag_quality(rf_copy, "doc text")
    assert is_valid is False
    assert ">80% overlap" in reason


def test_action_item_excludes_consequences_and_extracts_source_deadline_and_assignee():
    from app.models import ActionItem
    from app.services.analyzer import is_affirmative_action, ground_action_item

    # 1. Exclude consequences like late surcharge
    is_aff, reason = is_affirmative_action("Pay late surcharge if rent is received after the 5th")
    assert is_aff is False
    assert "Excluded consequence" in reason

    # 2. Keep stated deadline copying source wording & extract defined party assignee
    item = ActionItem(
        action="Pay base monthly rent",
        deadline=None,
        assignee=None,
        citation=Citation(
            chunk_id="chunk_2",
            quote="2.1 Monthly Base Rent: Subtenant agrees to pay base monthly rent of $8,500 USD on the first day of each calendar month.",
            verified=True
        )
    )
    grounded, date_nulled = ground_action_item(item, item.citation.quote, item.citation.quote)
    assert grounded.deadline == "first day of each calendar month"
    assert grounded.assignee == "Subtenant"
    assert date_nulled is False


def test_deterministic_scanner_title_alignment_and_deadline_regex():
    from app.models import Chunk, RedFlag, Citation
    from app.services.analyzer import (
        scan_document_for_red_flag_candidates,
        enforce_title_quote_alignment,
        extract_deadline_by_regex,
        extract_acting_assignee
    )

    # 1. Scanner finds high-signal clauses
    chunks = [
        Chunk(
            chunk_id="chunk_1",
            doc_id="d1",
            index=0,
            char_start=0,
            char_end=200,
            text="Sublessor reserves unconditional right to repossess premises upon 7 days notice without refunding unamortized improvements. Subtenant waives all jury trial rights. If rent is received after the 5th, a late surcharge of $450 USD will be charged."
        )
    ]
    candidates = scan_document_for_red_flag_candidates(chunks)
    quotes = [c.citation.quote.lower() for c in candidates]
    assert any("unconditional" in q or "without refund" in q for q in quotes)
    assert any("jury" in q and "waive" in q for q in quotes)
    assert any("late surcharge" in q or "$450" in q for q in quotes)

    # 2. Title-quote alignment: don't use "jury" unless quote contains "jury"
    rf_bad_jury = RedFlag(
        issue="Waiver of Jury Trial Rights",
        category="other",
        severity="medium",
        risk_explanation="Limits legal remedies.",
        citation=Citation(chunk_id="c1", quote="This Agreement constitutes the complete understanding between the parties.", verified=True)
    )
    rf_aligned = enforce_title_quote_alignment(rf_bad_jury)
    assert "jury" not in rf_aligned.issue.lower()

    # 3. Deadline by regex: prefer duration over termination date
    nda_sent = "Upon written notice or termination by December 31, 2027, Receiving Party shall destroy or return all materials within fourteen (14) business days."
    d_nda = extract_deadline_by_regex(nda_sent)
    assert d_nda == "within fourteen (14) business days"

    # 4. Mechanic's lien keeping 15 days
    lien_sent = "Subtenant shall promptly discharge any mechanic's lien within fifteen (15) days of filing."
    d_lien = extract_deadline_by_regex(lien_sent)
    assert "fifteen (15) days" in d_lien

    # 5. Acting assignee: actor is subject, not recipient of notice
    assignee = extract_acting_assignee("Provide ten (10) days advance notice", "All cosmetic painting may proceed upon ten (10) days advance notice to Sublessor.", "Subtenant lease")
    assert assignee == "Subtenant"


def test_deterministic_clause_scanner_on_sample_contracts():
    from pathlib import Path
    from app.services.extractor import extract_document
    from app.services.chunker import create_chunks
    from app.services.analyzer import scan_document_for_red_flag_candidates

    # 1. Commercial lease: repossession, jury waiver, and $450 late charge
    lease_path = Path("samples/commercial_lease.pdf")
    if lease_path.exists():
        chunks = create_chunks("test_lease", extract_document(lease_path))
        cands = scan_document_for_red_flag_candidates(chunks)
        quotes = [c.citation.quote.lower() for c in cands]
        assert any("repossess" in q or "without refund" in q for q in quotes), "Lease must flag repossession"
        assert any("jury" in q for q in quotes), "Lease must flag jury waiver"
        assert any("450" in q or "late surcharge" in q for q in quotes), "Lease must flag $450 late charge"

    # 2. SaaS MSA: auto-renewal, $96,000 lock-in, late fee, and NO jury in any title unless quote does
    saas_path = Path("samples/saas_msa.docx")
    if saas_path.exists():
        chunks = create_chunks("test_saas", extract_document(saas_path))
        cands = scan_document_for_red_flag_candidates(chunks)
        quotes = [c.citation.quote.lower() for c in cands]
        assert any("renew" in q for q in quotes), "SaaS must flag auto-renewal"
        assert any("96,000" in q or "renewal fee" in q for q in quotes), "SaaS must flag $96,000 lock-in"
        assert any("penalty" in q or "finance penalty" in q or "1.5%" in q for q in quotes), "SaaS must flag late fee"
        for c in cands:
            if "jury" not in c.citation.quote.lower():
                assert "jury" not in c.issue.lower(), f"SaaS title has 'jury' without quote having jury: {c.issue}"



