"""
SlothClerk Export Service: Formats document analysis results into structured Markdown and JSON reports.
"""
from datetime import datetime, timezone
from typing import Optional
from app.models import DocumentAnalysisResponse


def export_markdown(response: DocumentAnalysisResponse, custom_title: Optional[str] = None) -> str:
    """
    Generates a clean, professional, publication-ready Markdown audit report.
    Includes Executive Summary, Critical Red Flags, Key Dates, Financial Obligations,
    and an actionable Checklist with verified citation badges.
    """
    title = custom_title or f"SlothClerk Audit Report: {response.filename}"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    all_citations = [response.summary_citation]
    for kd in response.key_dates:
        all_citations.append(kd.citation)
    for ma in response.money_amounts:
        all_citations.append(ma.citation)
    for ob in response.obligations:
        all_citations.append(ob.citation)
    for rf in response.red_flags:
        all_citations.append(rf.citation)
    for act in response.action_checklist:
        all_citations.append(act.citation)

    verified_count = sum(1 for c in all_citations if c and c.verified)
    total_citations = len(all_citations)
    verif_rate = (verified_count / total_citations * 100.0) if total_citations > 0 else 100.0

    lines = []
    lines.append(f"# SlothClerk Audit Report: {response.filename}")
    lines.append("")
    lines.append(f"**Document Name:** `{response.filename}`  ")
    lines.append(f"**Document ID:** `{response.doc_id}`  ")
    lines.append(f"**Generated At:** `{now_str}`  ")
    lines.append(f"**Engine & Model:** `{response.metrics.model_name}` (100% Local Offline Inference)  ")
    lines.append(f"**Total Latency:** `{response.metrics.latency_ms:,} ms` (Stage A: {response.metrics.stage_a_latency_ms:,} ms | Stage B: {response.metrics.stage_b_latency_ms:,} ms)  ")
    lines.append(f"**Citation Grounding:** `{verified_count}/{total_citations} Verified ({verif_rate:.1f}%)`  ")
    lines.append(f"**Privacy & Security:** `Zero Cloud Calls | 100% Offline Local Extraction`  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"> {response.summary}")
    lines.append("")
    sum_verif = "[VERIFIED]" if response.summary_citation.verified else "[UNVERIFIED]"
    lines.append(f"- **Source Citation:** `[{response.summary_citation.chunk_id}]` {sum_verif}")
    lines.append(f"- **Verbatim Quote:** *\"{response.summary_citation.quote}\"*")
    lines.append("")

    # Red Flags
    lines.append("---")
    lines.append("")
    lines.append(f"## Critical Red Flags & Risk Audit ({len(response.red_flags)})")
    lines.append("")
    if not response.red_flags:
        lines.append("_No critical red flags detected in this document._")
        lines.append("")
    else:
        for idx, rf in enumerate(response.red_flags, 1):
            sev_badge = f"**[{rf.severity.upper()}]**"
            rf_verif = "[VERIFIED]" if rf.citation.verified else "[UNVERIFIED]"
            lines.append(f"### {idx}. {sev_badge} {rf.issue}")
            lines.append(f"- **Category:** `{rf.category}`")
            lines.append(f"- **Risk Analysis:** {rf.risk_explanation}")
            lines.append(f"- **Citation:** `[{rf.citation.chunk_id}]` {rf_verif}")
            lines.append(f"- **Cited Clause:** *\"{rf.citation.quote}\"*")
            lines.append("")

    # Key Dates
    lines.append("---")
    lines.append("")
    lines.append(f"## Key Dates & Milestones ({len(response.key_dates)})")
    lines.append("")
    if not response.key_dates:
        lines.append("_No key dates or milestones found._")
        lines.append("")
    else:
        for kd in response.key_dates:
            kd_verif = "[VERIFIED]" if kd.citation.verified else "[UNVERIFIED]"
            lines.append(f"- **{kd.date}**: {kd.description} `[{kd.citation.chunk_id} {kd_verif}]`")
            lines.append(f"  - *Quote:* \"{kd.citation.quote}\"")
        lines.append("")

    # Monetary Amounts
    lines.append("---")
    lines.append("")
    lines.append(f"## Monetary Amounts & Financial Commitments ({len(response.money_amounts)})")
    lines.append("")
    if not response.money_amounts:
        lines.append("_No specific financial amounts found._")
        lines.append("")
    else:
        for ma in response.money_amounts:
            ma_verif = "[VERIFIED]" if ma.citation.verified else "[UNVERIFIED]"
            lines.append(f"- **{ma.amount}**: {ma.context} `[{ma.citation.chunk_id} {ma_verif}]`")
            lines.append(f"  - *Quote:* \"{ma.citation.quote}\"")
        lines.append("")

    # Obligations
    lines.append("---")
    lines.append("")
    lines.append(f"## Contractual Obligations & Duties ({len(response.obligations)})")
    lines.append("")
    if not response.obligations:
        lines.append("_No specific contractual duties detected._")
        lines.append("")
    else:
        for ob in response.obligations:
            ob_verif = "[VERIFIED]" if ob.citation.verified else "[UNVERIFIED]"
            lines.append(f"- **{ob.party}**: {ob.duty} `[{ob.citation.chunk_id} {ob_verif}]`")
            lines.append(f"  - *Quote:* \"{ob.citation.quote}\"")
        lines.append("")

    # Action Checklist
    lines.append("---")
    lines.append("")
    lines.append(f"## Action Checklist ({len(response.action_checklist)})")
    lines.append("")
    if not response.action_checklist:
        lines.append("_No actionable tasks found._")
        lines.append("")
    else:
        for act in response.action_checklist:
            act_verif = "[VERIFIED]" if act.citation.verified else "[UNVERIFIED]"
            deadline_str = f"Deadline: **{act.deadline}**" if act.deadline else "Deadline: _None specified_"
            assignee_str = f"Assignee: **{act.assignee}**" if act.assignee else "Assignee: _Unassigned_"
            lines.append(f"- [ ] **{act.action}**")
            lines.append(f"  - {deadline_str} | {assignee_str}")
            lines.append(f"  - *Citation:* `[{act.citation.chunk_id} {act_verif}]` \"{act.citation.quote}\"")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated locally by SlothClerk — 100% Offline & Private Document Intelligence.*")
    lines.append("")
    return "\n".join(lines)


def export_json(response: DocumentAnalysisResponse, indent: int = 2) -> str:
    """Exports the full structured analysis response as formatted JSON."""
    return response.model_dump_json(indent=indent)
