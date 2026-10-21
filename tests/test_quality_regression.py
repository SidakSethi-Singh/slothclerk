import re
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
@pytest.mark.parametrize("sample_file", [
    "samples/commercial_lease.pdf",
    "samples/nda_agreement.docx",
    "samples/saas_msa.docx"
])
def test_quality_and_grounding_regression(sample_file: str):
    """
    Regression test against real model that fails if:
    1. Any checklist deadline or assignee isn't found in the source chunk.
    2. Any string has trailing whitespace runs, stray ”, / ", artifacts, or markdown asterisks.
    3. Any returned citation is unverified.
    4. Any red flag category contradicts its quote.
    5. Stage B status fails or lists are empty.
    """
    file_path = Path(sample_file)
    assert file_path.exists(), f"Sample file not found: {file_path}"

    segs = extract_document(file_path)
    chunks = create_chunks(f"reg_{file_path.stem}", segs)
    chunk_lookup = {c.chunk_id: c.text for c in chunks}

    result = analyzer.analyze_document(
        doc_id=f"reg_{file_path.stem}",
        filename=file_path.name,
        chunks=chunks
    )

    # 1. Stage B must succeed
    assert result.metrics.stage_b_status == "success", f"Stage B did not succeed: {result.metrics.stage_b_status}"
    assert len(result.red_flags) >= 1, f"Red flags empty for {sample_file}"
    assert len(result.action_checklist) >= 1, f"Action checklist empty for {sample_file}"

    # 2. Gather all citations
    all_citations = [result.summary_citation]
    for kd in result.key_dates:
        all_citations.append(kd.citation)
    for ma in result.money_amounts:
        all_citations.append(ma.citation)
    for ob in result.obligations:
        all_citations.append(ob.citation)
    for rf in result.red_flags:
        all_citations.append(rf.citation)
    for act in result.action_checklist:
        all_citations.append(act.citation)

    # 3. Assert EVERY returned citation is verified
    for c in all_citations:
        assert c.verified is True, f"Unverified citation returned in {sample_file}: [{c.chunk_id}] {c.quote}"
        chunk_text = chunk_lookup.get(c.chunk_id, "")
        assert chunk_text, f"Referenced non-existent chunk {c.chunk_id}"
        # Quote must actually match chunk text (exact or normalized substring)
        norm_q = re.sub(r'[^a-zA-Z0-9]', '', c.quote.lower())
        norm_c = re.sub(r'[^a-zA-Z0-9]', '', chunk_text.lower())
        assert norm_q in norm_c or norm_q[:40] in norm_c, (
            f"Citation quote '{c.quote}' does not match chunk text in {c.chunk_id}"
        )

    # 4. Check action checklist grounding: deadline and assignee
    for act in result.action_checklist:
        chunk_text = chunk_lookup[act.citation.chunk_id].lower()

        if act.deadline is not None:
            # Must appear in or be directly supported by chunk text
            tokens = re.findall(r'\b(?:[0-9]+|january|february|march|april|may|june|july|august|september|october|november|december|day|days|month|months|year|years|signing|execution|promptly|advance|prior|expiration)\b', act.deadline.lower())
            assert any(t in chunk_text for t in tokens), (
                f"Action deadline '{act.deadline}' is not grounded in chunk: {chunk_text}"
            )

        if act.assignee is not None:
            # Must appear in chunk text
            assignee_words = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', act.assignee.lower()) if w not in ('the', 'and', 'for', 'team', 'department', 'manager')]
            assert any(w in chunk_text for w in assignee_words), (
                f"Action assignee '{act.assignee}' is not grounded in chunk: {chunk_text}"
            )

    # 5. Check string sanitization across all fields in the JSON response
    def verify_string_clean(val: str, field_name: str):
        if not val:
            return
        # No leading or trailing whitespace
        assert val == val.strip(), f"Field '{field_name}' has unstripped whitespace: '{val}'"
        # No markdown asterisks
        assert "*" not in val, f"Field '{field_name}' contains markdown asterisks: '{val}'"
        # No stray slash quotes
        assert '/ "' not in val and '\\"' not in val, f"Field '{field_name}' contains stray quote artifacts: '{val}'"
        # No trailing smart quotes
        assert not val.endswith('”') and not val.endswith('“'), f"Field '{field_name}' ends with smart quote: '{val}'"
        # No trailing JSON brackets/commas
        assert not val.endswith('}}') and not val.endswith('}},'), f"Field '{field_name}' ends with JSON artifact: '{val}'"

    verify_string_clean(result.summary, "summary")
    verify_string_clean(result.summary_citation.quote, "summary_citation.quote")

    for kd in result.key_dates:
        verify_string_clean(kd.date, "key_date.date")
        verify_string_clean(kd.description, "key_date.description")
        verify_string_clean(kd.citation.quote, "key_date.citation.quote")

    for ma in result.money_amounts:
        verify_string_clean(ma.amount, "money_amount.amount")
        verify_string_clean(ma.context, "money_amount.context")
        verify_string_clean(ma.citation.quote, "money_amount.citation.quote")

    for ob in result.obligations:
        verify_string_clean(ob.party, "obligation.party")
        verify_string_clean(ob.duty, "obligation.duty")
        verify_string_clean(ob.citation.quote, "obligation.citation.quote")

    for rf in result.red_flags:
        verify_string_clean(rf.issue, "red_flag.issue")
        verify_string_clean(rf.risk_explanation, "red_flag.risk_explanation")
        verify_string_clean(rf.citation.quote, "red_flag.citation.quote")

        # 6. Red flag category matching quote
        q_lower = rf.citation.quote.lower()
        issue_lower = rf.issue.lower()
        is_penalty = any(term in q_lower for term in ("late fee", "late surcharge", "liquidated damages", "penalty", "finance penalty"))
        is_termination = any(term in q_lower for term in ("repossess", "termination", "terminate", "evict"))
        if is_penalty and not is_termination:
            assert "termination" not in issue_lower and "repossession" not in issue_lower, (
                f"Penalty clause mislabeled as termination: {rf.issue} for quote '{rf.citation.quote}'"
            )

    for act in result.action_checklist:
        verify_string_clean(act.action, "action_checklist.action")
        if act.deadline:
            verify_string_clean(act.deadline, "action_checklist.deadline")
        if act.assignee:
            verify_string_clean(act.assignee, "action_checklist.assignee")
        verify_string_clean(act.citation.quote, "action_checklist.citation.quote")


@pytest.mark.skipif(
    not (ollama_client.check_connection().get("reachable") and ollama_client.check_connection().get("has_llm")),
    reason="Requires live local Ollama with gemma3:4b"
)
def test_specific_stated_deadlines_preserved():
    """
    Verifies that stated deadlines are preserved:
    1. Commercial lease deposit action keeps 'upon signing'.
    2. SaaS non-renewal action keeps '90 days'.
    """
    # 1. Commercial lease
    lease_path = Path("samples/commercial_lease.pdf")
    lease_segs = extract_document(lease_path)
    lease_chunks = create_chunks("test_lease_deadlines", lease_segs)
    lease_res = analyzer.analyze_document(
        doc_id="test_lease_deadlines",
        filename=lease_path.name,
        chunks=lease_chunks
    )
    deposit_actions = [
        act for act in lease_res.action_checklist
        if "deposit" in act.action.lower() or "security" in act.action.lower()
    ]
    assert len(deposit_actions) >= 1, "Must have at least one deposit action in lease"
    assert any("upon signing" in (act.deadline or "").lower() for act in deposit_actions), (
        f"Deposit action did not keep 'upon signing'. Action deadlines: {[act.deadline for act in deposit_actions]}"
    )

    # 2. SaaS MSA
    saas_path = Path("samples/saas_msa.docx")
    saas_segs = extract_document(saas_path)
    saas_chunks = create_chunks("test_saas_deadlines", saas_segs)
    saas_res = analyzer.analyze_document(
        doc_id="test_saas_deadlines",
        filename=saas_path.name,
        chunks=saas_chunks
    )
    non_renewal_actions = [
        act for act in saas_res.action_checklist
        if "non-renewal" in act.action.lower() or "renew" in act.action.lower() or "notice" in act.action.lower()
    ]
    assert len(non_renewal_actions) >= 1, "Must have at least one non-renewal/notice action in SaaS MSA"
    assert any("90" in (act.deadline or "") or "ninety" in (act.deadline or "").lower() for act in non_renewal_actions), (
        f"SaaS non-renewal action did not keep '90 days'. Action deadlines: {[act.deadline for act in non_renewal_actions]}"
    )


@pytest.mark.skipif(
    not (ollama_client.check_connection().get("reachable") and ollama_client.check_connection().get("has_llm")),
    reason="Requires live local Ollama with gemma3:4b"
)
def test_new_unlabeled_samples_regression():
    """
    Regression tests on the new unlabeled contracts:
    1. The SaaS sample must produce a red flag citing the auto-renewal clause.
    2. The lease must produce a flag citing the repossession clause.
    3. No two flags share the same quote.
    4. No quote is a heading or starts mid-word.
    5. Every checklist date appears in the source.
    """
    from app.services.analyzer import is_heading_quote

    for sample_file in ["samples/saas_msa.docx", "samples/commercial_lease.pdf", "samples/nda_agreement.docx"]:
        file_path = Path(sample_file)
        segs = extract_document(file_path)
        chunks = create_chunks(f"reg_unlab_{file_path.stem}", segs)
        full_text = " ".join(s["text"] for s in segs)

        res = analyzer.analyze_document(
            doc_id=f"reg_unlab_{file_path.stem}",
            filename=file_path.name,
            chunks=chunks
        )

        # 1. Specific clause citations
        if "saas" in sample_file:
            rf_quotes = " ".join(rf.citation.quote.lower() for rf in res.red_flags)
            assert any(k in rf_quotes for k in ["automatically renew", "auto-renewal", "consecutive 24-month", "ninety (90) days", "90 days"]), (
                f"SaaS sample must produce a red flag citing the auto-renewal clause. Found quotes: {rf_quotes}"
            )
        elif "lease" in sample_file:
            rf_quotes = " ".join(rf.citation.quote.lower() for rf in res.red_flags)
            assert any(k in rf_quotes for k in ["repossess", "repossession", "7 days notice", "zoning revisions", "without refunding"]), (
                f"Lease sample must produce a flag citing the repossession clause. Found quotes: {rf_quotes}"
            )

        # 2. No two flags share the same quote
        quotes = [rf.citation.quote.strip().lower() for rf in res.red_flags]
        assert len(quotes) == len(set(quotes)), f"Duplicate red flag quotes found in {sample_file}: {quotes}"

        # 3. No quote is a heading or starts mid-word
        for rf in res.red_flags:
            q = rf.citation.quote.strip()
            # Not a heading
            assert not is_heading_quote(q), f"Red flag quote is a heading in {sample_file}: '{q}'"
            # Does not start mid-word
            assert q[0].isupper() or q[0].isdigit() or q[0] in '"\'“‘', f"Quote starts mid-word or lowercase in {sample_file}: '{q}'"
            # No speculative words
            assert "implied" not in rf.issue.lower() and "suggesting" not in rf.issue.lower(), (
                f"Speculative red flag found in {sample_file}: {rf.issue}"
            )
            assert "suggesting" not in rf.risk_explanation.lower(), (
                f"Speculative risk explanation found in {sample_file}: {rf.risk_explanation}"
            )
            # If renewal, quote must contain renew
            if "renew" in rf.issue.lower() or rf.category == "auto_renewal":
                assert "renew" in q.lower(), f"Renewal flag contradicts quote in {sample_file}: {rf.issue} -> {q}"

        # 4. Action checklist quality
        for act in res.action_checklist:
            # Exclude consequences like late surcharge
            assert "late surcharge" not in act.action.lower() and "late fee" not in act.action.lower(), (
                f"Consequence penalty included in action checklist in {sample_file}: '{act.action}'"
            )
            if act.deadline:
                norm_d = act.deadline.lower()
                tokens = re.findall(r'\b(?:[0-9]+|january|february|march|april|may|june|july|august|september|october|november|december|day|days|month|months|signing|execution|net|hours|first)\b', norm_d)
                assert any(t in full_text.lower() for t in tokens), (
                    f"Checklist date/deadline '{act.deadline}' not found in source text for {sample_file}"
                )



