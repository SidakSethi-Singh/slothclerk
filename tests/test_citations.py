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
    # 3. Employment Agreement: non-compete, signing bonus clawback, inventions assignment, arbitration/jury
    emp_path = Path("samples/employment_agreement.docx")
    if emp_path.exists():
        chunks = create_chunks("test_emp", extract_document(emp_path))
        cands = scan_document_for_red_flag_candidates(chunks)
        quotes = [c.citation.quote.lower() for c in cands]
        issues = [c.issue.lower() for c in cands]
        assert any("competing" in q or "engage in" in q for q in quotes), "Employment must flag non-compete"
        assert any("repay 100%" in q or "signing bonus" in q for q in quotes), "Employment must flag bonus clawback"
        assert any("inventions" in q or "assigns to company" in q for q in quotes), "Employment must flag inventions assignment"
        assert any("arbitration" in q or "jury" in q for q in quotes), "Employment must flag arbitration/jury waiver"


def test_merge_red_flags_same_chunk_topic_keyword():
    """
    (1) merge red flags that cite the same chunk and share a topic keyword such as 'arbitration' or 'attorney'.
    """
    from app.services.analyzer import deduplicate_red_flags
    from app.models import RedFlag, Citation

    # Case A: Two flags citing the same chunk that share "arbitration"
    rf1 = RedFlag(
        issue="Mandatory Binding Arbitration",
        category="other",
        severity="medium",
        risk_explanation="Disputes must be submitted to private binding arbitration.",
        citation=Citation(chunk_id="chunk_4", quote="All disputes must be submitted to binding arbitration in Wilmington, Delaware.", verified=True)
    )
    rf2 = RedFlag(
        issue="Arbitration Clause Waiver",
        category="other",
        severity="high",
        risk_explanation="Forecloses access to court and jury trial through arbitration.",
        citation=Citation(chunk_id="chunk_4", quote="Binding arbitration in Wilmington.", verified=True)
    )

    deduped, dups = deduplicate_red_flags([rf1, rf2])
    assert len(deduped) == 1, f"Expected 1 merged flag, got {len(deduped)}"
    assert dups == 1
    assert deduped[0].severity == "high", "Merged flag should inherit highest severity"
    assert "arbitration" in deduped[0].issue.lower()

    # Case B: Two flags citing the same chunk that share "attorney"
    rf_att1 = RedFlag(
        issue="Attorney Fees Recovery",
        category="other",
        severity="medium",
        risk_explanation="Prevailing party recovers reasonable attorney costs.",
        citation=Citation(chunk_id="chunk_4", quote="The prevailing party is entitled to recover all reasonable attorney costs.", verified=True)
    )
    rf_att2 = RedFlag(
        issue="Unilateral Legal and Attorney Costs",
        category="other",
        severity="high",
        risk_explanation="Exposes party to legal liability for opposing attorney fees.",
        citation=Citation(chunk_id="chunk_4", quote="Reasonable attorney costs shall be awarded.", verified=True)
    )

    deduped_att, dups_att = deduplicate_red_flags([rf_att1, rf_att2])
    assert len(deduped_att) == 1, f"Expected 1 merged flag, got {len(deduped_att)}"
    assert dups_att == 1
    assert deduped_att[0].severity == "high"

    # Case C: Different chunks do not merge even if sharing topic
    rf_diff_chunk = RedFlag(
        issue="Arbitration in Other Contract",
        category="other",
        severity="medium",
        risk_explanation="Other arbitration.",
        citation=Citation(chunk_id="chunk_9", quote="Disputes under section 9 require arbitration.", verified=True)
    )
    deduped_diff, dups_diff = deduplicate_red_flags([rf1, rf_diff_chunk])
    assert len(deduped_diff) == 2, "Flags on different chunks with different quotes must not merge"
    assert dups_diff == 0


def test_clean_display_strings_and_quote_boundary():
    """
    (2) Clean display strings: never cut mid-word or mid-sentence,
    strip stray ', and ' artifacts, and end quote snippets at a sentence boundary.
    """
    from app.services.analyzer import clean_display_string, ensure_quote_sentence_boundary, sanitize_text

    # Part A: Strip stray ", and " artifacts
    assert sanitize_text('", and "') is None
    assert clean_display_string('", and "') is None
    assert clean_display_string('", and Subtenant shall pay rent') == "Subtenant shall pay rent"
    assert clean_display_string('Subtenant shall pay rent", and "') == "Subtenant shall pay rent"
    assert clean_display_string('Subtenant shall pay rent", and other fees') == "Subtenant shall pay rent, and other fees"
    assert clean_display_string('Clause A", and "Clause B.') == "Clause A, and Clause B."

    # Part B: Never cut mid-word or mid-sentence
    long_text = "The rent of $12,000 USD is payable on the first day of each calendar month during the lease term."
    cleaned = clean_display_string(long_text, max_length=60)
    assert cleaned is not None
    # Must not cut inside a word (e.g. no partial word like 'calen')
    words = cleaned.split()
    assert all(w.isalpha() or w.startswith('$') or w.isdigit() or w in (',', '.') for w in words)
    # Must not end with broken trailing conjunctions
    assert not cleaned.endswith(("and", "or", "during", "of", "the", "a", "an", "in", "to"))

    # Part C: End quote snippets at a sentence boundary (. ! ?)
    q1 = ensure_quote_sentence_boundary("Certification of destruction must be provided")
    assert q1 == "Certification of destruction must be provided."
    assert q1.endswith((".", "!", "?"))

    q2 = ensure_quote_sentence_boundary("Subtenant shall yield Demised Premises broom clean.")
    assert q2 == "Subtenant shall yield Demised Premises broom clean."
    assert q2.endswith((".", "!", "?"))

    doc = "Section 3. Receiving Party shall destroy or return all materials within fourteen (14) business days. Certification of destruction must be provided."
    q3 = ensure_quote_sentence_boundary("Receiving Party shall destroy or return all materials", doc)
    assert q3 == "Receiving Party shall destroy or return all materials within fourteen (14) business days."


def test_checklist_deadline_isolated_to_own_sentence():
    """
    (3) A checklist deadline must come from the action's own cited sentence,
    not from a neighboring sentence. 'Provide certification of destruction' must have no deadline.
    """
    from app.services.analyzer import ground_action_item
    from app.models import ActionItem, Citation

    full_chunk_text = (
        "Upon written notice or termination by December 31, 2027, Receiving Party shall "
        "destroy or return all materials within fourteen (14) business days. "
        "Certification of destruction must be provided."
    )

    # Action 1: "Provide certification of destruction"
    # Even if an LLM hallucinated a deadline or the chunk has a neighboring deadline, it must be nulled
    item_cert = ActionItem(
        action="Provide certification of destruction",
        deadline="within fourteen (14) business days",
        assignee="Receiving Party",
        citation=Citation(chunk_id="chunk_3", quote="Certification of destruction must be provided.", verified=True)
    )
    grounded_cert, nulled = ground_action_item(item_cert, full_chunk_text, full_chunk_text)
    assert grounded_cert.deadline is None, f"Certification of destruction must have no deadline, got: {grounded_cert.deadline}"
    assert nulled is True

    # Action 2: Action whose own cited sentence has the deadline
    item_return = ActionItem(
        action="Destroy or return all materials",
        deadline=None,
        assignee="Receiving Party",
        citation=Citation(
            chunk_id="chunk_3",
            quote="Receiving Party shall destroy or return all materials within fourteen (14) business days.",
            verified=True
        )
    )
    grounded_return, _ = ground_action_item(item_return, full_chunk_text, full_chunk_text)
    assert grounded_return.deadline == "within fourteen (14) business days"




