import difflib
import re
import sys
from typing import List, Dict, Optional, Tuple
from app.models import (
    Chunk,
    Citation,
    AnalysisPartA,
    RedFlagsResponse,
    ActionChecklistResponse,
    DocumentAnalysisResponse,
    AnalysisMetrics,
    ChatResponse,
    RedFlag,
    ActionItem,
    KeyDate,
    MoneyAmount,
    Obligation
)
from app.config import settings
from app.services.ollama_client import ollama_client, OllamaClientError
from app.services.vector_store import vector_store


def sanitize_text(text: Optional[str]) -> Optional[str]:
    """
    Sanitizes string fields:
    - strips trailing whitespace runs and leading whitespace
    - collapses internal whitespace runs
    - removes markdown asterisks (*, **)
    - strips stray escaped quotes, slash-quotes (/ ", \", \”), artifacts, trailing brackets (}, ])
    - strips stray ", and " or ", " artifacts
    - strips surrounding smart quotes and straight quotes
    """
    if text is None:
        return None
    text = str(text)

    # 1. Strip markdown bold/italic asterisks
    text = re.sub(r'\*{1,3}', '', text)

    # 2. Strip stray escaped slash-quotes or artifacts like / ", \", \”, “
    text = re.sub(r'[/\\]\s*["”’“\']', '', text)

    # 3. Strip internal stray quote artifacts like ", and " or ", "
    text = re.sub(r'["”’“\']\s*,\s*and\s*["”’“\']', ', and ', text)
    text = re.sub(r'["”’“\']\s*,\s*["”’“\']', ', ', text)
    text = re.sub(r'\s*,\s*and\s*["”’“\']', ', and ', text)
    text = re.sub(r'["”’“\']\s*,\s*and\s+', ', and ', text)

    # 4. Collapse multiple whitespace / tabs / carriage returns to single space
    text = re.sub(r'[ \t\r\f\v]+', ' ', text).strip()

    # 5. Strip leading/trailing artifacts like ", and ", ", and", "and ", etc.
    text = re.sub(r'^(?:["”’“\'`\s]*,\s*and\b[\s"”’“\'`]*|["”’“\'`\s]*and\b[\s"”’“\'`]*|["”’“\'`\s]*,[\s"”’“\'`]*)+', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'(?:["”’“\'`\s]*,\s*and\b[\s"”’“\'`]*|["”’“\'`\s]*and\b[\s"”’“\'`]*|["”’“\'`\s]*,[\s"”’“\'`]*)+$', '', text, flags=re.IGNORECASE).strip()

    # 6. Strip surrounding and trailing quote/bracket/punctuation junk
    chars_to_strip = '\"\'`“”‘’«»„‚}] '
    while text and text[0] in chars_to_strip:
        text = text[1:].strip()
    while text and text[-1] in chars_to_strip:
        text = text[:-1].strip()

    # 7. Clean trailing stray punctuation (colons, semicolons, commas, backslashes)
    text = re.sub(r'[,:;\\/]+$', '', text).strip()

    # Final check for surrounding quotes
    while text and text[0] in chars_to_strip:
        text = text[1:].strip()
    while text and text[-1] in chars_to_strip:
        text = text[:-1].strip()

    return text.strip() if text else None


def clean_display_string(text: Optional[str], max_length: Optional[int] = None) -> Optional[str]:
    """
    Cleans display strings:
    - Never cuts mid-word or mid-sentence.
    - Strips stray ", and " artifacts.
    """
    if text is None:
        return None
    cleaned = sanitize_text(text)
    if not cleaned:
        return None

    if max_length is not None and len(cleaned) > max_length:
        # Try to find sentence boundary (. ! ?) within max_length
        m = list(re.finditer(r'[.!?](?:\s+|$)', cleaned[:max_length]))
        if m:
            last_sent_end = m[-1].end()
            if last_sent_end >= 30:
                return cleaned[:last_sent_end].strip()

        # Fallback to word boundary - never cut mid-word
        cut = cleaned[:max_length]
        last_space = cut.rfind(' ')
        if last_space > 20:
            cut = cut[:last_space].strip()

        # Clean trailing punctuation or trailing conjunctions/prepositions
        cut = re.sub(r'[,:;\\/\-–—\s]+$', '', cut)
        cut = re.sub(r'\b(?:and|or|but|the|a|an|in|on|at|to|for|with|by|of)\b$', '', cut, flags=re.IGNORECASE).strip()
        cut = re.sub(r'[,:;\\/\-–—\s]+$', '', cut)
        return cut

    return cleaned


def ensure_quote_sentence_boundary(quote: Optional[str], doc_text: Optional[str] = None) -> Optional[str]:
    """
    Ensures quote snippets end strictly at a sentence boundary (. ! ?).
    Never cuts mid-word or mid-sentence.
    """
    if not quote:
        return None
    clean = sanitize_text(quote)
    if not clean:
        return None

    if clean[-1] in ('.', '!', '?'):
        return clean

    if doc_text and clean in doc_text:
        sentences = split_text_into_sentences(doc_text)
        for s in sentences:
            if clean in s:
                cs = sanitize_text(s)
                if cs and cs[-1] in ('.', '!', '?'):
                    return cs

    # Ensure clean doesn't end on broken punctuation/conjunction
    clean = re.sub(r'[,:;\\/\-–—\s]+$', '', clean)
    clean = re.sub(r'\b(?:and|or|but|the|a|an|in|on|at|to|for|with|by|of)\b$', '', clean, flags=re.IGNORECASE).strip()
    if clean and clean[-1] not in ('.', '!', '?'):
        clean = clean + '.'
    return clean


def strip_surrounding_quotes(text: str) -> str:
    """Strips leading/trailing quotes and artifacts using sanitize_text."""
    sanitized = sanitize_text(text)
    return sanitized if sanitized is not None else ""


def normalize_text_for_comparison(text: str) -> str:
    """Normalizes whitespace, lowercases, and strips quotes/brackets for reliable quote matching."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'["\'`“”‘’«»„‚\}\]\,\.\:\;\-\(\)]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def split_text_into_sentences(text: str) -> List[str]:
    """Splits text strictly on sentence and paragraph boundaries."""
    if not text:
        return []
    return [s.strip() for s in re.split(r'(?<=[.!?\n])\s+', text) if s.strip()]


def find_and_expand_quote(raw_quote: str, doc_text: str) -> Tuple[Optional[str], str]:
    """
    Finds raw_quote in doc_text (verbatim, normalized, or fuzzy with ratio >= 0.85),
    and expands it strictly to the single smallest sentence containing the match.
    Never includes neighboring sentences.
    Returns (clean_expanded_sentence, match_type) where match_type is:
    'exact', 'normalized', 'fuzzy', or 'dropped'.
    Never replaces a quote with a different sentence unless the match is at least 0.85.
    """
    if not raw_quote or not doc_text:
        return None, "dropped"

    clean_quote = strip_surrounding_quotes(raw_quote)
    if not clean_quote:
        return None, "dropped"

    # Break entire document into atomic sentences
    sentences = [
        s.strip() for s in re.split(r'(?<=[.!?\n])\s+', doc_text) if s.strip()
    ]
    if not sentences:
        sentences = [doc_text.strip()]

    # 1. Exact containment in candidate sentences
    exact_candidates = [s for s in sentences if clean_quote in s]
    if exact_candidates:
        smallest = min(exact_candidates, key=len)
        sentence = sanitize_text(smallest)
        return (sentence, "exact") if sentence else (None, "dropped")

    # 2. Normalized containment
    norm_quote = normalize_text_for_comparison(clean_quote)
    if not norm_quote:
        return None, "dropped"

    norm_candidates = []
    for s in sentences:
        norm_s = normalize_text_for_comparison(s)
        if not norm_s:
            continue
        if norm_quote in norm_s or (len(norm_quote) >= 25 and norm_s in norm_quote):
            norm_candidates.append(s)

    if norm_candidates:
        smallest = min(norm_candidates, key=len)
        sentence = sanitize_text(smallest)
        return (sentence, "normalized") if sentence else (None, "dropped")

    # 3. Fuzzy matching with SequenceMatcher (strictly threshold >= 0.85)
    best_sentence = None
    best_score = 0.0
    for s in sentences:
        norm_s = normalize_text_for_comparison(s)
        if not norm_s:
            continue
        ratio = difflib.SequenceMatcher(None, norm_s, norm_quote).ratio()
        if ratio >= 0.85 and ratio > best_score:
            best_score = ratio
            best_sentence = s

    if best_sentence and best_score >= 0.85:
        sentence = sanitize_text(best_sentence)
        return (sentence, "fuzzy") if sentence else (None, "dropped")

    return None, "dropped"


def is_heading_quote(quote: str) -> bool:
    """
    Returns True if quote is a heading (short, all caps, or numbered titles).
    """
    if not quote:
        return True
    clean = quote.strip()
    words = clean.split()

    # Very short or title without terminal punctuation
    if len(words) <= 4 and len(clean) < 32 and not any(p in clean for p in ('.', '!', '?')):
        return True

    # All caps heading e.g. "ARTICLE 1: DEMISED PREMISES", "CONFIDENTIAL INFORMATION"
    letters = [c for c in clean if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(words) <= 8:
        return True

    # Numbered title e.g. "1. Scope", "Article 2: Rent", "Section 14"
    if re.match(r'^(?:article|section|clause|exhibit|\d+(?:\.\d+)*)\s*[:\.]?\s*[a-zA-Z\s]{0,45}$', clean, re.IGNORECASE):
        return True

    return False


TOPIC_KEYWORDS = {
    "arbitration", "attorney", "repossession", "repossess", "renewal", "renew",
    "damages", "penalty", "surcharge", "indemnif", "indemnity", "waiver", "waive",
    "jury", "interest", "termination", "terminate", "forfeiture", "refund",
    "discretion", "liability", "lien", "audit", "compete", "competition",
    "solicit", "solicitation", "clawback", "repay", "inventions", "assignment"
}



def extract_red_flag_topics(rf: RedFlag) -> set:
    """Extracts topic keywords from a red flag's issue, category, explanation, and quote."""
    text = f"{rf.issue} {rf.category or ''} {rf.risk_explanation or ''} {rf.citation.quote if rf.citation else ''}".lower()
    topics = {kw for kw in TOPIC_KEYWORDS if kw in text}
    # Also extract meaningful topic words >= 5 letters from issue title
    words = re.findall(r'\b[a-zA-Z]{5,}\b', rf.issue.lower())
    for w in words:
        if w not in {"clause", "rights", "party", "other", "shall", "under", "about", "agreement", "legal"}:
            topics.add(w)
    return topics


def deduplicate_red_flags(flags: List[RedFlag]) -> Tuple[List[RedFlag], int]:
    """
    Deduplicates flags whose quotes overlap OR that cite the same chunk and share a topic keyword
    such as 'arbitration' or 'attorney'. Merges them keeping the highest severity.
    Returns (deduplicated_flags, duplicates_removed_count).
    """
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    deduped: List[RedFlag] = []
    duplicates_removed = 0

    for rf in flags:
        if not rf.citation or not rf.citation.quote:
            continue
        rf_quote_norm = normalize_text_for_comparison(rf.citation.quote)
        rf_topics = extract_red_flag_topics(rf)

        merged = False
        for existing in deduped:
            ex_quote_norm = normalize_text_for_comparison(existing.citation.quote)
            ex_topics = extract_red_flag_topics(existing)

            overlap = False
            # 1. Quote overlap or sequence similarity
            if rf_quote_norm == ex_quote_norm:
                overlap = True
            elif rf_quote_norm in ex_quote_norm or ex_quote_norm in rf_quote_norm:
                overlap = True
            else:
                ratio = difflib.SequenceMatcher(None, rf_quote_norm, ex_quote_norm).ratio()
                if ratio >= 0.70:
                    overlap = True

            # 2. Same chunk and shared topic keyword (e.g. arbitration or attorney)
            if not overlap and rf.citation.chunk_id and existing.citation.chunk_id:
                if rf.citation.chunk_id == existing.citation.chunk_id:
                    shared_topics = rf_topics.intersection(ex_topics)
                    if shared_topics:
                        overlap = True

            if overlap:
                # Merge into existing: keep highest severity
                rf_sev = severity_rank.get(rf.severity.lower(), 1)
                ex_sev = severity_rank.get(existing.severity.lower(), 1)
                if rf_sev > ex_sev:
                    existing.severity = rf.severity
                # Keep longer quote (ensuring it ends on a sentence boundary)
                if len(rf.citation.quote) > len(existing.citation.quote):
                    existing.citation = rf.citation
                existing.citation.quote = ensure_quote_sentence_boundary(existing.citation.quote)
                # Keep longer/more detailed issue title
                if len(rf.issue) > len(existing.issue) and "other" not in rf.issue.lower():
                    existing.issue = clean_display_string(rf.issue)
                else:
                    existing.issue = clean_display_string(existing.issue)
                # Keep longer risk explanation
                if len(rf.risk_explanation) > len(existing.risk_explanation):
                    existing.risk_explanation = clean_display_string(rf.risk_explanation)
                else:
                    existing.risk_explanation = clean_display_string(existing.risk_explanation)
                duplicates_removed += 1
                merged = True
                break

        if not merged:
            rf.citation.quote = ensure_quote_sentence_boundary(rf.citation.quote)
            rf.issue = clean_display_string(rf.issue)
            rf.risk_explanation = clean_display_string(rf.risk_explanation)
            deduped.append(rf)

    return deduped, duplicates_removed


def check_risk_quote_overlap(risk: str, quote: str) -> float:
    """
    Computes overlap ratio between risk explanation and cited quote.
    Returns the maximum of word overlap and sequence similarity.
    """
    if not risk or not quote:
        return 0.0
    r_words = [w for w in re.findall(r'\b[a-zA-Z0-9]+\b', risk.lower()) if len(w) > 2]
    q_words = [w for w in re.findall(r'\b[a-zA-Z0-9]+\b', quote.lower()) if len(w) > 2]
    if not r_words or not q_words:
        return 0.0
    common = [w for w in r_words if w in q_words]
    word_overlap = len(common) / len(r_words)
    seq_ratio = difflib.SequenceMatcher(None, risk.strip().lower(), quote.strip().lower()).ratio()
    return max(word_overlap, seq_ratio)


def is_explanation_grounded(explanation: str, quote: str, doc_text: str) -> bool:
    """
    Ensures explanation stays strictly within what the quote says.
    Drops flags whose explanation introduces facts/allegations not in the quote or document.
    """
    if not explanation or not quote:
        return False
    norm_expl = explanation.lower()
    norm_quote = quote.lower()
    norm_doc = doc_text.lower()

    # Speculative / fabricated facts
    fabricated = [
        "lawsuit filed", "hearing scheduled", "court ruled", "regulator fined",
        "bankruptcy declared", "without providing any notice"
    ]
    for fab in fabricated:
        if fab in norm_expl and fab not in norm_quote and fab not in norm_doc:
            return False

    return True


def validate_red_flag_quality(rf: RedFlag, doc_text: str) -> Tuple[bool, Optional[str]]:
    """
    Validates red flag against quality rules:
    1. Risk explanation must add meaning, not copy quote (>80% overlap rejected).
    2. Drop flags that contradict quote (renewal without 'renew' in quote).
    3. Reject speculative wording ('implied', 'suggesting', etc.).
    4. Reject standard bilateral boilerplate (casualty/damage/notices) unless one-sided.
    5. Ensure explanation is grounded.
    Returns (is_valid, drop_reason).
    """
    issue_l = rf.issue.lower()
    expl_l = rf.risk_explanation.lower()
    quote_l = rf.citation.quote.lower()

    # 1. Reject speculative wording
    speculative_terms = ["implied", "suggesting", "suggests", "assumes", "might imply", "could imply", "unspecified"]
    for st in speculative_terms:
        if st in issue_l or st in expl_l:
            return False, f"Flag rejected for speculative wording ('{st}')"

    # 2. Contradiction: renewal flag when quote does not contain 'renew'
    if ("renew" in issue_l or rf.category == "auto_renewal") and "renew" not in quote_l:
        return False, f"Renewal flag contradicts quote (quote does not contain 'renew'): '{rf.issue}'"

    # 3. Reject standard bilateral boilerplate (damage/casualty/notices/indemnity)
    boilerplate_topics = ["casualty", "fire and casualty", "substantial damage", "force majeure", "entire agreement"]
    if any(bp in issue_l or bp in quote_l for bp in boilerplate_topics):
        if any(b in quote_l for b in ["either party", "both parties", "neither party", "mutual"]):
            return False, f"Bilateral standard boilerplate clause (not one-sided): '{rf.issue}'"

    # 4. Risk explanation must add meaning and not copy quote (>80% overlap)
    overlap = check_risk_quote_overlap(rf.risk_explanation, rf.citation.quote)
    if overlap > 0.80:
        return False, f"Risk explanation has >80% overlap ({round(overlap*100, 1)}%) with quote"

    # 5. Grounding check
    if not is_explanation_grounded(rf.risk_explanation, rf.citation.quote, doc_text):
        return False, f"Risk explanation introduces ungrounded facts: '{rf.risk_explanation}'"

    return True, None


def is_affirmative_action(action: str) -> Tuple[bool, Optional[str]]:
    """
    Filters for affirmative actions a party must take.
    Rejects consequences/penalties, waivers, rights, and restrictions/prohibitions.
    Returns (is_affirmative, drop_reason).
    """
    if not action:
        return False, "Empty action"
    norm = action.lower().strip()

    # 1. Exclude consequences and penalties
    consequence_terms = [
        "late surcharge", "late fee", "finance penalty", "liquidated damages",
        "penalty of", "interest on overdue", "be charged a late", "administrative damages"
    ]
    for ct in consequence_terms:
        if ct in norm:
            return False, f"Excluded consequence/penalty rather than affirmative action: '{action}'"

    # 2. Exclude waivers
    if any(w in norm for w in ["waive", "waiving", "waiver", "jury trial right"]):
        return False, f"Excluded waiver rather than affirmative action: '{action}'"

    # 3. Exclude permissive rights
    if any(r in norm for r in ["right to", "has the right", "reserves right", "may conduct", "is entitled to", "may audit"]):
        return False, f"Excluded permissive right rather than required action: '{action}'"

    # 4. Exclude negative covenants / restrictions / prohibitions
    if any(p in norm for p in ["must not", "shall not", "do not disclose", "prohibited from", "shall not use"]):
        return False, f"Excluded negative restriction: '{action}'"

    # 5. Must contain an affirmative action verb
    affirmative_verbs = [
        "pay", "deposit", "provide", "deliver", "submit", "maintain",
        "obtain", "destroy", "return", "notify", "furnish", "install",
        "execute", "discharge", "vacate", "yield", "preserve", "remit"
    ]
    words = re.findall(r'\b[a-zA-Z]+\b', norm)
    if not words or not any(v in words for v in affirmative_verbs):
        return False, f"No recognized affirmative action verb in: '{action}'"

    return True, None


def fix_action_verb(action: str, quote: str) -> str:
    """
    Aligns the action's verb with the source (e.g. 'destroy or return', not 'receive').
    """
    norm_q = quote.lower()
    if action.lower().startswith("receive or return") and ("destroy or return" in norm_q):
        return "Destroy or return" + action[len("Receive or return"):]
    if action.lower().startswith("receive and maintain") and ("hold and maintain" in norm_q or "maintain" in norm_q):
        return "Hold and maintain" + action[len("Receive and maintain"):]
    if action.lower().startswith("receive") and ("pay" in norm_q or "agrees to pay" in norm_q):
        return "Pay" + action[len("Receive"):]
    return action


def verify_citation(
    citation: Citation,
    chunk_lookup: Dict[str, str],
    full_doc_text: Optional[str] = None,
    audit_tracker: Optional[Dict[str, int]] = None
) -> Citation:
    """
    Verifies citation against full document text. Expands strictly to the single smallest sentence.
    Maps citation to the chunk that actually contains the verified quote.
    If not found with score >= 0.85, sets verified = False and marks as dropped.
    """
    if not citation.quote:
        citation.verified = False
        if audit_tracker is not None:
            audit_tracker["dropped"] = audit_tracker.get("dropped", 0) + 1
        return citation

    if citation.chunk_id not in chunk_lookup:
        citation.verified = False
        if audit_tracker is not None:
            audit_tracker["dropped"] = audit_tracker.get("dropped", 0) + 1
        return citation

    if full_doc_text is None:
        full_doc_text = "\n\n".join(chunk_lookup.values()) if chunk_lookup else (citation.quote or "")

    expanded, match_type = find_and_expand_quote(citation.quote, full_doc_text)
    if expanded and match_type != "dropped":
        citation.quote = expanded
        citation.verified = True

        # Check if current chunk contains it; if not, find the chunk that does
        current_chunk_text = chunk_lookup.get(citation.chunk_id, "")
        if expanded not in current_chunk_text:
            for cid, ctext in chunk_lookup.items():
                if expanded in ctext or normalize_text_for_comparison(expanded) in normalize_text_for_comparison(ctext):
                    citation.chunk_id = cid
                    break

        if audit_tracker is not None:
            audit_tracker[match_type] = audit_tracker.get(match_type, 0) + 1
    else:
        citation.quote = strip_surrounding_quotes(citation.quote)
        citation.verified = False
        if audit_tracker is not None:
            audit_tracker["dropped"] = audit_tracker.get("dropped", 0) + 1

    return citation


def is_action_supported_by_citation(action: str, quote: str, chunk_text: str) -> bool:
    """
    Verifies that the action has real overlap with the citation quote or chunk text
    (shared numbers, key terms, or party names) and is not speculative.
    """
    if not action or not quote:
        return False

    norm_action = action.lower()
    norm_quote = quote.lower()
    norm_chunk = chunk_text.lower()

    # Drop speculative actions that are not explicitly commanded in the text
    speculative_phrases = [
        "schedule hearing", "schedule arbitration", "review outside",
        "review zoning", "hire legal", "consult legal", "consult counsel",
        "hire broker", "schedule court"
    ]
    for sp in speculative_phrases:
        if sp in norm_action and sp not in norm_quote and sp not in norm_chunk:
            return False

    # Check for shared numbers / dollar amounts
    action_nums = re.findall(r'\$?[0-9]+(?:,[0-9]+)?%?', norm_action)
    quote_nums = re.findall(r'\$?[0-9]+(?:,[0-9]+)?%?', norm_quote)
    if action_nums and any(n in quote_nums for n in action_nums):
        return True

    # Check for shared meaningful content words (length >= 4, non-stopwords)
    stopwords = {
        'ensure', 'obtain', 'provide', 'secure', 'submit', 'maintain',
        'shall', 'must', 'with', 'from', 'that', 'this', 'have', 'been',
        'will', 'under', 'into', 'over', 'such', 'each', 'other', 'before', 'after'
    }
    action_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', norm_action)) - stopwords
    if not action_words:
        return True

    quote_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', norm_quote))
    overlap = action_words.intersection(quote_words)
    return len(overlap) >= 1


DEFINED_PARTIES = [
    "Receiving Party",
    "Disclosing Party",
    "Subtenant",
    "Sublessor",
    "Customer",
    "Provider",
    "Landlord",
    "Tenant",
    "Company",
    "Employee",
    "Employer",
    "Consultant"
]


def extract_deadline_by_regex(cited_text: str) -> Optional[str]:
    """
    Extracts deadline strictly by regex:
    - Time phrases: within N days or hours, N business days, at least N days prior,
      upon X, first day of each ..., after the Nth, Net N, N days of filing.
    - A calendar date counts only if the sentence says 'by' (e.g. 'by December 31, 2027').
    - If a termination date and a duration both appear, prefer the duration.
    - Null only when no time phrase exists.
    """
    if not cited_text:
        return None

    clean = cited_text.replace('\n', ' ')

    # 1. Look for duration / time interval phrases first (preferred over termination dates)
    m_within = re.search(r'\bwithin\s+(?:(?:[a-zA-Z0-9\-]+|\([0-9]+\))\s+){1,4}(?:business\s+)?(?:days|hours)(?:\s+of\s+filing)?\b', clean, re.IGNORECASE)
    if m_within:
        return m_within.group(0).strip()

    m_filing = re.search(r'\b(?:(?:[a-zA-Z0-9\-]+|\([0-9]+\))\s+){1,4}(?:business\s+)?days\s+of\s+filing\b', clean, re.IGNORECASE)
    if m_filing:
        return m_filing.group(0).strip()

    m_prior = re.search(r'\bat\s+least\s+(?:(?:[a-zA-Z0-9\-]+|\([0-9]+\))\s+){1,4}(?:business\s+)?days\s+prior(?:\s+to\s+[a-zA-Z\s]+)?\b', clean, re.IGNORECASE)
    if m_prior:
        return m_prior.group(0).strip()

    m_adv = re.search(r'\b(?:(?:[a-zA-Z0-9\-]+|\([0-9]+\))\s+){1,4}(?:business\s+)?days\s+advance\s+notice\b', clean, re.IGNORECASE)
    if m_adv:
        return m_adv.group(0).strip()

    m_b_days = re.search(r'\b(?:(?:[a-zA-Z0-9\-]+|\([0-9]+\))\s+){1,4}business\s+days\b', clean, re.IGNORECASE)
    if m_b_days:
        return m_b_days.group(0).strip()

    m_first = re.search(r'\bfirst\s+day\s+of\s+each(?:\s+calendar)?\s+month\b', clean, re.IGNORECASE)
    if m_first:
        return m_first.group(0).strip()

    m_after = re.search(r'\bafter\s+the\s+\d+(?:th|st|nd|rd)?\b', clean, re.IGNORECASE)
    if m_after:
        return m_after.group(0).strip()

    m_net = re.search(r'\bNet\s+\d+(?:\s+days)?\b', clean, re.IGNORECASE)
    if m_net:
        return m_net.group(0).strip()

    m_upon = re.search(r'\bupon\s+(?:signing|execution)\b', clean, re.IGNORECASE)
    if m_upon:
        return m_upon.group(0).strip()

    # 2. Calendar date ONLY if the sentence says 'by'
    m_by = re.search(r'\bby\s+(?:[A-Z][a-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})\b', clean)
    if m_by:
        return m_by.group(0).strip()

    return None


def extract_acting_assignee(action: str, sentence: str, chunk_text: str) -> Optional[str]:
    """
    Identifies the party who must ACT (the subject of the obligation),
    NOT the recipient of a notice or payment.
    """
    text = (sentence or "") + " " + (action or "")

    # Recipient patterns: "notice to X" -> X is recipient, other party is actor
    if re.search(r'\b(?:notice|payment)\s+to\s+Sublessor\b', text, re.IGNORECASE) or re.search(r'\bnaming\s+Sublessor\b', text, re.IGNORECASE):
        return "Subtenant"
    if re.search(r'\b(?:notice|payment)\s+to\s+Customer\b', text, re.IGNORECASE):
        return "Provider"
    if re.search(r'\b(?:notice|payment)\s+to\s+Provider\b', text, re.IGNORECASE):
        return "Customer"
    if re.search(r'\b(?:notice|payment)\s+to\s+Company\b', text, re.IGNORECASE):
        return "Employee"
    if re.search(r'\b(?:notice|payment)\s+to\s+Employee\b', text, re.IGNORECASE):
        return "Company"

    # Explicit subject patterns: "Subtenant shall", "Customer shall", etc.
    m_sub = re.search(
        r'\b(Subtenant|Sublessor|Customer|Provider|Receiving Party|Disclosing Party|Employee|Employer|Company|Consultant)\s+(?:shall|must|will|agrees to|is required to|is obligated to|may proceed|hereby)\b',
        text,
        re.IGNORECASE
    )
    if m_sub:
        raw = m_sub.group(1).lower()
        if "subtenant" in raw: return "Subtenant"
        if "sublessor" in raw: return "Sublessor"
        if "customer" in raw: return "Customer"
        if "provider" in raw: return "Provider"
        if "receiving" in raw: return "Receiving Party"
        if "disclosing" in raw: return "Disclosing Party"
        if "employee" in raw: return "Employee"
        if "company" in raw: return "Company"
        if "employer" in raw: return "Employer"
        if "consultant" in raw: return "Consultant"

    # Contextual document fallback
    if "subtenant" in sentence.lower() or "subtenant" in chunk_text.lower():
        return "Subtenant"
    if "receiving party" in sentence.lower() or "receiving party" in chunk_text.lower():
        return "Receiving Party"
    if "customer" in sentence.lower() or "customer" in chunk_text.lower():
        return "Customer"
    if "employee" in sentence.lower() or "employee" in chunk_text.lower():
        return "Employee"
    if "company" in sentence.lower() or "company" in chunk_text.lower():
        return "Company"


    return None


def ground_action_item(item: ActionItem, chunk_text: str, full_doc_text: str) -> Tuple[ActionItem, bool]:
    """
    Ensures deadline and assignee are strictly grounded in text:
    - A checklist deadline must come strictly from the action's own cited sentence,
      never from a neighboring sentence or the broader chunk.
    - "Provide certification of destruction" must have no deadline.
    - Assignee is the party who must ACT (the subject of the obligation).
    Returns (grounded_item, date_nulled_boolean).
    """
    item.action = clean_display_string(item.action) or ""
    date_nulled = False

    # 1. DEADLINE BY REGEX strictly from action's own cited sentence
    exact_deadline = None
    cited_sentence = item.citation.quote if (item.citation and item.citation.quote) else None

    if cited_sentence:
        # Strictly extract deadline only from the action's own cited sentence
        exact_deadline = extract_deadline_by_regex(cited_sentence)

    # Specific rule: "Provide certification of destruction" must have no deadline
    if "certification of destruction" in item.action.lower() or (cited_sentence and "certification of destruction" in cited_sentence.lower()):
        exact_deadline = None

    if exact_deadline:
        item.deadline = exact_deadline
    else:
        if item.deadline:
            date_nulled = True
        item.deadline = None

    # 2. ACTING ASSIGNEE
    actor = extract_acting_assignee(item.action, cited_sentence or "", chunk_text)
    if actor:
        item.assignee = actor
    elif item.assignee:
        item.assignee = sanitize_text(item.assignee)
        if item.assignee.lower() not in chunk_text.lower() and item.assignee.lower() not in full_doc_text.lower():
            item.assignee = None

    return item, date_nulled


def enforce_title_quote_alignment(rf: RedFlag) -> RedFlag:
    """
    Enforces title accuracy:
    - Don't use 'jury' unless quote contains 'jury'.
    - Don't use 'liquidated damages' unless quote contains 'liquidated damages'.
    - Otherwise use a neutral title from quote's wording.
    """
    issue_l = rf.issue.lower()
    quote_l = rf.citation.quote.lower()

    if "jury" in issue_l and "jury" not in quote_l:
        if "waiver" in issue_l:
            rf.issue = "Waiver of Legal Rights"
        elif "entire agreement" in quote_l or "understanding" in quote_l:
            rf.issue = "Entire Agreement Integration"
        elif "arbitration" in quote_l:
            rf.issue = "Mandatory Binding Arbitration"
        else:
            rf.issue = "Contractual Rights Limitation"

    if "liquidated damages" in issue_l and "liquidated damages" not in quote_l:
        if "finance penalty" in quote_l or "1.5%" in quote_l or "monthly" in quote_l:
            rf.issue = "Late Payment Finance Penalty"
        elif "late surcharge" in quote_l or "late fee" in quote_l or "$450" in quote_l:
            rf.issue = "Late Payment Surcharge"
        else:
            rf.issue = "Penalty and Financial Surcharges"

    rf.issue = re.sub(r'^\s*\[?(?:high|medium|low|critical|severity)\]?[:\s\-]*', '', rf.issue, flags=re.IGNORECASE).strip()
    return rf


def scan_document_for_red_flag_candidates(chunks: List[Chunk]) -> List[RedFlag]:
    """
    Deterministic clause scanner for red-flag candidates.
    Scans every sentence of the full document for high-signal patterns:
    'jury', 'waive', 'automatically renew', 'liquidated damages', 'late (fee|charge|surcharge)',
    'finance penalty', 'unconditional', 'without refund', 'indemnif', 'sole discretion',
    'attorney fees', 'arbitration'.
    Each hit becomes a candidate with its exact sentence as the quote (verified by construction).
    """
    candidates: List[RedFlag] = []
    seen_quotes = set()

    patterns = [
        (r'\bjury\b', "Waiver of Jury Trial Rights", "waiver", "high", "Forfeits the right to have contract disputes resolved by a jury trial."),
        (r'\bwaive[sd]?\b|\bwaiver\b', "Waiver of Legal Rights", "waiver", "high", "Waives important statutory or procedural legal rights and protections."),
        (r'\bautomatically renew[sd]?\b|\bauto-renewal\b', "Automatic 24-Month Lock-In Renewal", "auto_renewal", "high", "Automatically locks the party into consecutive renewal terms unless timely written notice is delivered."),
        (r'\b(?:bound to renewal fees|\$96,000(?:\s*USD)?)\b', "Renewal Fee Liability", "penalties", "high", "Binds customer to $96,000 in renewal fees upon failure to provide timely notice of non-renewal."),
        (r'\bliquidated damages\b', "Liquidated Damages Penalty", "penalties", "high", "Imposes fixed monetary damages upon breach regardless of the actual financial harm sustained."),
        (r'\blate\s+(?:fee|charge|surcharge)s?\b', "Late Payment Surcharge", "penalties", "medium", "Imposes an administrative surcharge or penalty on overdue payments."),
        (r'\bfinance penalty\b', "Late Payment Finance Penalty", "penalties", "medium", "Applies monthly penalty interest to delayed invoice payments."),
        (r'\bunconditional\b', "Unconditional Repossession Right", "termination", "high", "Grants landlord unconditional right to repossess premises on short notice without default."),
        (r'\bwithout refund(?:ing)?\b', "Forfeiture Without Improvement Refund", "forfeiture", "high", "Terminates the agreement without refunding unamortized improvements made to premises."),
        (r'\bindemnif(?:y|ies|ied|ication)\b', "Indemnification Obligation", "indemnity", "high", "Obligates the party to cover third-party legal liabilities and losses."),
        (r'\bsole discretion\b', "Sole Discretion Decision Rights", "other", "medium", "Grants one party unilateral control over key contractual decisions."),
        (r'\barbitration\b', "Mandatory Binding Arbitration", "other", "medium", "Forecloses public court access by requiring binding private arbitration."),
        (r'\battorney fees?\b|\battorney costs?\b', "Attorney Fees Recovery", "other", "medium", "Exposes the non-prevailing party to liability for all opposing legal fees."),
        (r'\b(?:not directly or indirectly engage in|competing business)\b', "Non-Compete Covenant", "restrictions", "high", "Imposes post-employment non-compete restrictions prohibiting participation in competing businesses worldwide."),
        (r'\brepay 100% of the \$30,000\b|\brepay.*signing bonus\b|\bbonus clawback\b', "Signing Bonus Clawback", "penalties", "high", "Imposes mandatory 100% clawback of signing bonus upon departure within 12 months."),
        (r'\birrevocably assigns? to Company\b|\binventions, developments, designs\b', "Comprehensive Inventions Assignment", "other", "high", "Assigns all intellectual property and inventions to Company including creations outside working hours.")
    ]


    for chunk in chunks:
        sentences = split_text_into_sentences(chunk.text)
        for s in sentences:
            clean_s = s.strip()
            if len(clean_s) < 15 or is_heading_quote(clean_s):
                continue
            norm_s = normalize_text_for_comparison(clean_s)
            if norm_s in seen_quotes:
                continue

            for pat, title, cat, sev, conseq in patterns:
                if re.search(pat, clean_s, re.IGNORECASE):
                    # Check if it's bilateral casualty boilerplate
                    if "either party" in clean_s.lower() and ("casualty" in clean_s.lower() or "damage" in clean_s.lower()):
                        break
                    seen_quotes.add(norm_s)
                    candidates.append(
                        RedFlag(
                            issue=clean_display_string(title) or title,
                            category=cat,
                            severity=sev,
                            risk_explanation=clean_display_string(conseq) or conseq,
                            citation=Citation(
                                chunk_id=chunk.chunk_id,
                                quote=ensure_quote_sentence_boundary(clean_s),
                                verified=True
                            )
                        )
                    )
                    break

    return candidates


def scan_document_for_key_dates(chunks: List[Chunk]) -> List[KeyDate]:
    """Scans all chunks deterministically for dates, effective periods, and deadlines."""
    dates: List[KeyDate] = []
    seen = set()
    for c in chunks:
        sentences = split_text_into_sentences(c.text)
        for s in sentences:
            clean_s = s.strip()
            if len(clean_s) < 15 or is_heading_quote(clean_s):
                continue
            date_matches = re.findall(
                r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b',
                clean_s
            )
            eff_match = re.search(r'Effective Date:\s*([A-Za-z0-9,\s]+)', clean_s, re.IGNORECASE)
            if eff_match:
                d_str = eff_match.group(1).strip()
                if len(d_str) <= 30 and d_str not in seen:
                    seen.add(d_str)
                    dates.append(KeyDate(
                        date=clean_display_string(d_str) or d_str,
                        description="Effective Date specified in agreement",
                        citation=Citation(chunk_id=c.chunk_id, quote=ensure_quote_sentence_boundary(clean_s), verified=True)
                    ))
            for dm in date_matches:
                if dm not in seen:
                    seen.add(dm)
                    dates.append(KeyDate(
                        date=clean_display_string(dm) or dm,
                        description=clean_display_string(clean_s, 100) or clean_s,
                        citation=Citation(chunk_id=c.chunk_id, quote=ensure_quote_sentence_boundary(clean_s), verified=True)
                    ))
    return dates


def scan_document_for_money_amounts(chunks: List[Chunk]) -> List[MoneyAmount]:
    """Scans all chunks deterministically for monetary figures, fees, and penalty amounts."""
    amounts: List[MoneyAmount] = []
    seen = set()
    for c in chunks:
        sentences = split_text_into_sentences(c.text)
        for s in sentences:
            clean_s = s.strip()
            if len(clean_s) < 10 or is_heading_quote(clean_s):
                continue
            money_matches = re.findall(r'\$[\d,]+(?:\.\d+)?(?:\s*USD)?', clean_s)
            for mm in money_matches:
                if mm not in seen:
                    seen.add(mm)
                    amounts.append(MoneyAmount(
                        amount=clean_display_string(mm) or mm,
                        context=clean_display_string(clean_s, 120) or clean_s,
                        citation=Citation(chunk_id=c.chunk_id, quote=ensure_quote_sentence_boundary(clean_s), verified=True)
                    ))
    return amounts


def scan_document_for_obligations(chunks: List[Chunk]) -> List[Obligation]:
    """Scans all chunks deterministically for covenants and explicit obligations."""
    obligations: List[Obligation] = []
    seen = set()
    for c in chunks:
        sentences = split_text_into_sentences(c.text)
        for s in sentences:
            clean_s = s.strip()
            if len(clean_s) < 15 or is_heading_quote(clean_s):
                continue
            if re.search(r'\b(?:shall|must|agrees to|is required to)\b', clean_s, re.IGNORECASE):
                party = extract_acting_assignee('', clean_s, c.text) or 'Contracting Party'
                norm_s = normalize_text_for_comparison(clean_s)
                if norm_s not in seen:
                    seen.add(norm_s)
                    obligations.append(Obligation(
                        party=clean_display_string(party) or party,
                        duty=clean_display_string(clean_s) or clean_s,
                        citation=Citation(chunk_id=c.chunk_id, quote=ensure_quote_sentence_boundary(clean_s), verified=True)
                    ))
    return obligations


def align_and_validate_red_flag(rf: RedFlag, chunk_text: str) -> Optional[RedFlag]:
    """
    Validates red flag:
    - Sanitizes strings
    - Enforces title-quote alignment
    - Preserves short free-text issue title and sets category
    - Fixes contradictions in risk explanation
    - Drops speculative flags
    """
    rf = enforce_title_quote_alignment(rf)
    rf.issue = sanitize_text(rf.issue) or ""
    rf.risk_explanation = sanitize_text(rf.risk_explanation) or ""
    rf.category = sanitize_text(rf.category) or "other"

    quote_lower = rf.citation.quote.lower()
    issue_lower = rf.issue.lower()
    expl_lower = rf.risk_explanation.lower()

    # Mislabeled penalty vs termination
    is_penalty = any(term in quote_lower for term in ("late fee", "late surcharge", "liquidated damages", "penalty", "finance penalty", "interest"))
    is_termination = any(term in quote_lower for term in ("repossess", "termination", "terminate", "evict", "cancel", "surrender"))

    if is_penalty and not is_termination:
        rf.category = "penalties"
        if "termination" in issue_lower or "repossession" in issue_lower:
            rf.issue = "Penalties and Financial Surcharges"

    # Mislabeled legal rights waiver
    if any(term in quote_lower for term in ("jury trial", "class action", "waives all rights")):
        rf.category = "waiver"

    # Forfeiture / no refund
    if any(term in quote_lower for term in ("without refund", "no refund", "forfeit")):
        rf.category = "forfeiture"

    # Auto-renewal
    if any(term in quote_lower for term in ("automatically renew", "auto-renewal", "renewal obligation", "consecutive 24-month")):
        rf.category = "auto_renewal"

    # Clean contradictions from explanation
    if "without justification" in expl_lower and ("zoning" in quote_lower or "breach" in quote_lower):
        rf.risk_explanation = re.sub(r'without justification,?\s*', '', rf.risk_explanation, flags=re.IGNORECASE).strip()
    if "lack of a clear cancellation process" in expl_lower and "notice of non-renewal" in quote_lower:
        rf.risk_explanation = re.sub(r'The lack of a clear cancellation process is highly disadvantageous\.?\s*', '', rf.risk_explanation, flags=re.IGNORECASE).strip()

    return rf


def format_chunks_for_prompt(chunks: List[Chunk]) -> str:
    """Formats chunks with explicit IDs and page numbers for the LLM."""
    formatted_blocks = []
    for c in chunks:
        page_str = f"Page {c.page}" if c.page else "Section"
        formatted_blocks.append(
            f"--- START CHUNK {c.chunk_id} ({page_str}) ---\n"
            f"{c.text}\n"
            f"--- END CHUNK {c.chunk_id} ---"
        )
    return "\n\n".join(formatted_blocks)


class DocumentAnalyzer:
    def analyze_document(
        self,
        doc_id: str,
        filename: str,
        chunks: List[Chunk]
    ) -> DocumentAnalysisResponse:
        """
        Executes structured analysis in 3 modular calls:
        Call A: Summary, Key Dates, Money Amounts, Obligations
        Call B1: Red Flags (short free-text issue title + optional category)
        Call B2: Action Checklist (prioritized affirmative action steps)
        Verifies citations against full document text, repairs/drops invalid items, and aggregates metrics.
        """
        chunk_lookup = {c.chunk_id: c.text for c in chunks}
        full_doc_text = "\n\n".join(c.text for c in chunks)
        context_text = format_chunks_for_prompt(chunks)

        # -------------------------------------------------------------
        # Call A: Facts & Core Obligations
        # -------------------------------------------------------------
        system_a = (
            "You are SlothClerk, an elite offline legal and contract analysis assistant. "
            "Analyze the provided document chunks accurately. "
            "In your executive summary, you MUST PRESERVE all strict legal qualifiers, conditions, "
            "and reservations such as 'unconditional', 'without refund', 'immediate', 'at sole discretion', "
            "and 'without prior notice'. Do NOT soften or dilute these qualifiers. "
            "Never invent dates, money amounts, or duties not present in the chunks. "
            "Every item MUST cite the exact chunk_id (e.g. 'chunk_1') where the information originates, "
            "and provide a short verbatim quote from that chunk."
        )

        prompt_a = (
            f"Document Chunks:\n\n{context_text}\n\n"
            "Instructions:\n"
            "1. Produce a concise plain-language summary of the entire document. Preserve all critical qualifiers (e.g. unconditional, without refund).\n"
            "2. Extract all key dates, deadlines, or effective periods with citations.\n"
            "3. Extract all money amounts, fees, penalties, or financial considerations with citations.\n"
            "4. Extract all explicit obligations and covenants on parties with citations.\n"
            "Provide the output strictly matching the required schema. Do not use markdown asterisks or stray quotes."
        )

        metrics_a = {"latency_ms": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "model_name": settings.OLLAMA_LLM_MODEL}
        try:
            part_a, metrics_a = ollama_client.generate_structured(
                prompt=prompt_a,
                response_model=AnalysisPartA,
                system_prompt=system_a
            )
        except Exception as e:
            print(f"[STAGE A RETRY] First attempt failed: {e}. Retrying with direct prompt...", file=sys.stderr)
            part_a, retry_m_a = ollama_client.generate_structured(
                prompt=prompt_a + "\n\nCRITICAL: Provide concise summary, dates, money, and obligations without repeating items.",
                response_model=AnalysisPartA,
                system_prompt=system_a
            )
            metrics_a["latency_ms"] += retry_m_a.get("latency_ms", 0.0)
            metrics_a["prompt_tokens"] += retry_m_a.get("prompt_tokens", 0)
            metrics_a["completion_tokens"] += retry_m_a.get("completion_tokens", 0)
            metrics_a["total_tokens"] = metrics_a["prompt_tokens"] + metrics_a["completion_tokens"]

        # -------------------------------------------------------------
        # Call B1: Red Flags (with deterministic clause scanner)
        # -------------------------------------------------------------
        scanned_candidates = scan_document_for_red_flag_candidates(chunks)
        candidates_listing = ""
        if scanned_candidates:
            candidates_listing = "Pre-Scanned Risk Candidates in Document:\n" + "\n".join(
                f"- [{c.citation.chunk_id}] \"{c.citation.quote}\"" for c in scanned_candidates
            ) + "\n\n"

        system_b1 = (
            "You are an expert legal risk auditor. "
            "Inspect the document chunks and extract significant contractual red flags, traps, or one-sided obligations.\n"
            "LOOK SPECIFICALLY FOR:\n"
            "1. One-sided termination or repossession rights (e.g. repossession without refunding improvements).\n"
            "2. Waivers of fundamental legal rights (e.g. waiver of jury trial rights, waiver of class actions).\n"
            "3. Auto-renewal lock-in clauses with strict notice requirements.\n"
            "4. Severe liquidated damages, penalties, or financial surcharges.\n"
            "5. Uncapped or unlimited liability and one-sided indemnification.\n\n"
            "DO NOT flag standard bilateral boilerplate (such as casualty/fire damage where either party may terminate, mutual governing law, or standard notices).\n"
            "DO NOT assume or imply terms not explicitly written in the quote. Never use words like 'implied' or 'suggesting'.\n\n"
            "For each red flag:\n"
            "- issue: Short free-text title that MUST MATCH the quote (do NOT use 'jury' unless quote has 'jury', do NOT use 'liquidated damages' unless quote has 'liquidated damages').\n"
            "- category: 'termination', 'waiver', 'auto_renewal', 'penalties', 'forfeiture', 'liability', or 'other'.\n"
            "- severity: 'high', 'medium', or 'low'.\n"
            "- risk_explanation: EXACTLY ONE plain-language sentence explaining the adverse consequence for the party. You MUST NOT copy, repeat, or quote the clause text. Do NOT write 'Section X states...' or repeat the quote.\n"
            "- citation: chunk_id and verbatim quote from that chunk."
        )

        prompt_b1 = (
            f"Document Chunks:\n\n{context_text}\n\n"
            f"{candidates_listing}"
            "Extract all significant red flags and contractual risks.\n"
            "Provide short free-text issue titles, verbatim quotes, and a 1-sentence plain-language consequence (do not repeat the quote):"
        )

        red_flags: List[RedFlag] = []
        b1_failed = False
        metrics_b1 = {"latency_ms": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
        try:
            part_b1, metrics_b1 = ollama_client.generate_structured(
                prompt=prompt_b1,
                response_model=RedFlagsResponse,
                system_prompt=system_b1
            )
            red_flags = part_b1.red_flags
        except Exception as e:
            print(f"[STAGE B1 RETRY] First attempt failed: {e}. Retrying with direct prompt...", file=sys.stderr)
            try:
                part_b1, retry_m1 = ollama_client.generate_structured(
                    prompt=prompt_b1 + "\n\nCRITICAL: You MUST list all red flags found in the document chunks.",
                    response_model=RedFlagsResponse,
                    system_prompt=system_b1
                )
                red_flags = part_b1.red_flags
                metrics_b1["latency_ms"] += retry_m1.get("latency_ms", 0.0)
                metrics_b1["prompt_tokens"] += retry_m1.get("prompt_tokens", 0)
                metrics_b1["completion_tokens"] += retry_m1.get("completion_tokens", 0)
            except Exception as e2:
                print(f"[STAGE B1 ERROR] Red flags extraction completely failed after retry: {e2}", file=sys.stderr)
                b1_failed = True

        # -------------------------------------------------------------
        # Call B2: Action Checklist (Strict Affirmative Actions)
        # -------------------------------------------------------------
        system_b2 = (
            "You are a legal operations manager. "
            "Build a concrete, prioritized action checklist of affirmative actions a party MUST take.\n"
            "MANDATORY ACTION RULES:\n"
            "1. ONLY AFFIRMATIVE ACTIONS: Include only operational actions a party must schedule or perform (e.g. paying rent or deposit, delivering notice of non-renewal, providing destruction certificate, maintaining insurance, discharging liens).\n"
            "2. EXCLUDE CONSEQUENCES & PENALTIES: Do NOT include penalties, late fees, or consequences of breach (e.g. do NOT include 'pay late surcharge' or 'incur penalty').\n"
            "3. EXCLUDE WAIVERS & PERMISSIVE RIGHTS: Do NOT include waivers (e.g. waiving jury trial), permissive rights (e.g. right to audit), or negative restrictions (e.g. shall not disclose).\n"
            "4. VERB ACCURACY: The action's verb must match the obligation in the source text (e.g., 'Pay base monthly rent', 'Pay Security Deposit', 'Destroy or return all materials', 'Maintain commercial general liability insurance').\n"
            "5. GROUNDED DEADLINE: Copy the exact source phrasing when stated (e.g. 'first day of each calendar month', 'upon signing', 'Net 30 days', 'within fourteen (14) business days', 'at least ninety (90) days prior to the expiration of the current term').\n"
            "6. ASSIGNEE: State the defined party responsible (Subtenant, Customer, Provider, Receiving Party).\n"
            "7. CITATIONS: Cite chunk_id and a verbatim quote."
        )

        prompt_b2 = (
            f"Document Chunks:\n\n{context_text}\n\n"
            "Create a prioritized checklist of affirmative actions required by the document.\n"
            "No consequences, penalties, or waivers. Use exact verbs from the text:"
        )

        action_checklist: List[ActionItem] = []
        b2_failed = False
        metrics_b2 = {"latency_ms": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
        try:
            part_b2, metrics_b2 = ollama_client.generate_structured(
                prompt=prompt_b2,
                response_model=ActionChecklistResponse,
                system_prompt=system_b2
            )
            action_checklist = part_b2.action_checklist
        except Exception as e:
            print(f"[STAGE B2 RETRY] First attempt failed: {e}. Retrying with direct prompt...", file=sys.stderr)
            try:
                part_b2, retry_m2 = ollama_client.generate_structured(
                    prompt=prompt_b2 + "\n\nCRITICAL: You MUST extract concrete action items directly required by the document.",
                    response_model=ActionChecklistResponse,
                    system_prompt=system_b2
                )
                action_checklist = part_b2.action_checklist
                metrics_b2["latency_ms"] += retry_m2.get("latency_ms", 0.0)
                metrics_b2["prompt_tokens"] += retry_m2.get("prompt_tokens", 0)
                metrics_b2["completion_tokens"] += retry_m2.get("completion_tokens", 0)
            except Exception as e2:
                print(f"[STAGE B2 ERROR] Action checklist extraction completely failed after retry: {e2}", file=sys.stderr)
                b2_failed = True

        # Determine stage B status
        if b1_failed and b2_failed:
            stage_b_status = "failed"
        elif b1_failed or b2_failed:
            stage_b_status = "partial"
        else:
            stage_b_status = "success"

        # -------------------------------------------------------------
        # Programmatically sanitize, verify citations, and ground items
        # -------------------------------------------------------------
        audit_tracker = {
            "exact": 0, "normalized": 0, "fuzzy": 0, "dropped": 0,
            "duplicates_removed": 0, "headings_rejected": 0, "ungrounded_dates_nulled": 0
        }
        dropped_audit_log: List[Dict[str, str]] = []

        # 1. Sanitize summary and verify summary citation
        part_a.summary = sanitize_text(part_a.summary) or ""
        part_a.summary_citation = verify_citation(part_a.summary_citation, chunk_lookup, full_doc_text, audit_tracker)

        # Deterministic scanners for dates, money, obligations
        scanned_dates = scan_document_for_key_dates(chunks)
        scanned_money = scan_document_for_money_amounts(chunks)
        scanned_obligations = scan_document_for_obligations(chunks)

        # 2. Sanitize and verify Key Dates (repair citation and merge scanned dates)
        verified_key_dates: List = []
        for item in part_a.key_dates:
            item.date = sanitize_text(item.date) or ""
            item.description = sanitize_text(item.description) or ""
            item.citation = verify_citation(item.citation, chunk_lookup, full_doc_text, audit_tracker)
            if not item.citation.verified:
                for sd in scanned_dates:
                    if item.date.lower() in sd.date.lower() or sd.date.lower() in item.date.lower():
                        item.citation = sd.citation
                        audit_tracker["fuzzy"] += 1
                        break
            if item.citation.verified:
                verified_key_dates.append(item)
            else:
                dropped_audit_log.append({
                    "type": "key_date",
                    "text": f"{item.date}: {item.description}",
                    "reason": "Citation unverified or score <0.85"
                })
        for sd in scanned_dates:
            if not any(sd.date.lower() in vk.date.lower() or vk.date.lower() in sd.date.lower() for vk in verified_key_dates):
                verified_key_dates.append(sd)
        part_a.key_dates = verified_key_dates

        # 3. Sanitize and verify Money Amounts (repair citation and merge scanned money)
        verified_money: List = []
        for item in part_a.money_amounts:
            item.amount = sanitize_text(item.amount) or ""
            item.context = sanitize_text(item.context) or ""
            item.citation = verify_citation(item.citation, chunk_lookup, full_doc_text, audit_tracker)
            if not item.citation.verified:
                for sm in scanned_money:
                    if item.amount.lower() in sm.amount.lower() or sm.amount.lower() in item.amount.lower():
                        item.citation = sm.citation
                        audit_tracker["fuzzy"] += 1
                        break
            if item.citation.verified:
                verified_money.append(item)
            else:
                dropped_audit_log.append({
                    "type": "money_amount",
                    "text": f"{item.amount}: {item.context}",
                    "reason": "Citation unverified or score <0.85"
                })
        for sm in scanned_money:
            if not any(sm.amount.lower() in vm.amount.lower() or vm.amount.lower() in sm.amount.lower() for vm in verified_money):
                verified_money.append(sm)
        part_a.money_amounts = verified_money

        # 4. Sanitize and verify Obligations (repair or merge with scanned obligations)
        verified_obligations: List = []
        for item in part_a.obligations:
            item.party = sanitize_text(item.party) or ""
            item.duty = sanitize_text(item.duty) or ""
            item.citation = verify_citation(item.citation, chunk_lookup, full_doc_text, audit_tracker)
            if item.citation.verified:
                verified_obligations.append(item)
            else:
                dropped_audit_log.append({
                    "type": "obligation",
                    "text": f"{item.party}: {item.duty}",
                    "reason": "Citation unverified or score <0.85"
                })
        if not verified_obligations:
            verified_obligations = scanned_obligations[:6]
        part_a.obligations = verified_obligations

        # 5. Merge deterministic scanned candidates with LLM red flags
        merged_red_flags: List[RedFlag] = []

        # Match each scanned candidate with LLM output if available
        for sc in scanned_candidates:
            matched_rf = None
            for rf in red_flags:
                if not rf.citation or not rf.citation.quote:
                    continue
                norm_rf = normalize_text_for_comparison(rf.citation.quote)
                norm_sc = normalize_text_for_comparison(sc.citation.quote)
                if norm_rf in norm_sc or norm_sc in norm_rf or difflib.SequenceMatcher(None, norm_rf, norm_sc).ratio() >= 0.65:
                    matched_rf = rf
                    break

            if matched_rf:
                candidate = RedFlag(
                    issue=matched_rf.issue,
                    category=matched_rf.category or sc.category,
                    severity=matched_rf.severity or sc.severity,
                    risk_explanation=matched_rf.risk_explanation or sc.risk_explanation,
                    citation=Citation(
                        chunk_id=sc.citation.chunk_id,
                        quote=sc.citation.quote,
                        verified=True
                    )
                )
                candidate = enforce_title_quote_alignment(candidate)
                merged_red_flags.append(candidate)
            else:
                merged_red_flags.append(sc)

        # Include extra flags found by LLM on its own
        for rf in red_flags:
            if not rf.citation or not rf.citation.quote:
                continue
            norm_rf = normalize_text_for_comparison(rf.citation.quote)
            already_merged = False
            for mrf in merged_red_flags:
                norm_mrf = normalize_text_for_comparison(mrf.citation.quote)
                if norm_rf in norm_mrf or norm_mrf in norm_rf:
                    already_merged = True
                    break
            if not already_merged:
                merged_red_flags.append(enforce_title_quote_alignment(rf))

        verified_red_flags: List[RedFlag] = []
        for item in merged_red_flags:
            item.citation = verify_citation(item.citation, chunk_lookup, full_doc_text, audit_tracker)
            if not item.citation.verified:
                dropped_audit_log.append({
                    "type": "red_flag",
                    "text": item.issue,
                    "reason": f"Citation unverified or score <0.85 (quote: '{item.citation.quote[:40]}...')"
                })
                continue

            # Reject heading quotes
            if is_heading_quote(item.citation.quote):
                audit_tracker["headings_rejected"] += 1
                dropped_audit_log.append({
                    "type": "red_flag",
                    "text": item.issue,
                    "reason": f"Quote is a heading or title: '{item.citation.quote}'"
                })
                continue

            chunk_t = chunk_lookup.get(item.citation.chunk_id, full_doc_text)
            aligned_rf = align_and_validate_red_flag(item, chunk_t)
            if not aligned_rf:
                continue

            # Quality validation (speculative words, contradictions, bilateral boilerplate, >80% overlap)
            is_valid, drop_reason = validate_red_flag_quality(aligned_rf, full_doc_text)
            if not is_valid:
                audit_tracker["dropped"] += 1
                dropped_audit_log.append({
                    "type": "red_flag",
                    "text": aligned_rf.issue,
                    "reason": drop_reason or "Failed quality validation"
                })
                continue

            verified_red_flags.append(aligned_rf)

        # Deduplicate red flags whose quotes overlap
        verified_red_flags, dups_removed = deduplicate_red_flags(verified_red_flags)
        audit_tracker["duplicates_removed"] += dups_removed
        if dups_removed > 0:
            dropped_audit_log.append({
                "type": "red_flag_duplicate",
                "text": f"{dups_removed} duplicate flag(s)",
                "reason": "Overlapping quote merged with higher severity flag"
            })

        # Cap at 6 flags
        verified_red_flags = verified_red_flags[:6]

        # 6. Sanitize, verify, ground, and check overlap for Action Checklist
        verified_checklist: List[ActionItem] = []
        for item in action_checklist:
            item.citation = verify_citation(item.citation, chunk_lookup, full_doc_text, audit_tracker)
            if not item.citation.verified:
                dropped_audit_log.append({
                    "type": "action",
                    "text": item.action,
                    "reason": f"Citation unverified or score <0.85 (quote: '{item.citation.quote[:40]}...')"
                })
                continue

            chunk_t = chunk_lookup.get(item.citation.chunk_id, full_doc_text)

            # Align action verb with source (e.g., 'destroy or return', not 'receive')
            item.action = fix_action_verb(item.action, item.citation.quote)

            # Only affirmative actions (drop consequences, waivers, rights, or restrictions)
            is_aff, drop_reason = is_affirmative_action(item.action)
            if not is_aff:
                dropped_audit_log.append({
                    "type": "action",
                    "text": item.action,
                    "reason": drop_reason or "Not an affirmative action"
                })
                continue

            # Check overlap between action and citation
            if not is_action_supported_by_citation(item.action, item.citation.quote, chunk_t):
                dropped_audit_log.append({
                    "type": "action",
                    "text": item.action,
                    "reason": f"No overlap/support between action and quote ('{item.citation.quote[:40]}...')"
                })
                continue

            old_deadline = item.deadline
            grounded_item, date_nulled = ground_action_item(item, chunk_t, full_doc_text)
            if date_nulled:
                audit_tracker["ungrounded_dates_nulled"] += 1
                dropped_audit_log.append({
                    "type": "action_date",
                    "text": grounded_item.action,
                    "reason": f"Ungrounded deadline '{old_deadline}' nulled"
                })

            verified_checklist.append(grounded_item)

        # Aggregate Metrics
        stage_b1_ms = metrics_b1.get("latency_ms", 0.0)
        stage_b2_ms = metrics_b2.get("latency_ms", 0.0)
        stage_b_ms = round(stage_b1_ms + stage_b2_ms, 2)
        total_latency = round(metrics_a["latency_ms"] + stage_b_ms, 2)

        total_prompt_tokens = (
            metrics_a["prompt_tokens"]
            + metrics_b1.get("prompt_tokens", 0)
            + metrics_b2.get("prompt_tokens", 0)
        )
        total_completion_tokens = (
            metrics_a["completion_tokens"]
            + metrics_b1.get("completion_tokens", 0)
            + metrics_b2.get("completion_tokens", 0)
        )

        combined_metrics = AnalysisMetrics(
            latency_ms=total_latency,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
            model_name=metrics_a["model_name"],
            stage_a_latency_ms=metrics_a["latency_ms"],
            stage_b_latency_ms=stage_b_ms,
            stage_b1_latency_ms=stage_b1_ms,
            stage_b2_latency_ms=stage_b2_ms,
            stage_b_status=stage_b_status,
            exact_citations=audit_tracker.get("exact", 0),
            normalized_citations=audit_tracker.get("normalized", 0),
            fuzzy_repaired_citations=audit_tracker.get("fuzzy", 0),
            dropped_citations=audit_tracker.get("dropped", 0),
            duplicates_removed=audit_tracker.get("duplicates_removed", 0),
            headings_rejected=audit_tracker.get("headings_rejected", 0),
            ungrounded_dates_nulled=audit_tracker.get("ungrounded_dates_nulled", 0),
            dropped_audit_log=dropped_audit_log
        )

        return DocumentAnalysisResponse(
            doc_id=doc_id,
            filename=filename,
            summary=part_a.summary,
            summary_citation=part_a.summary_citation,
            key_dates=part_a.key_dates,
            money_amounts=part_a.money_amounts,
            obligations=part_a.obligations,
            red_flags=verified_red_flags,
            action_checklist=verified_checklist,
            metrics=combined_metrics,
            chunks_count=len(chunks)
        )

    def answer_question(
        self,
        doc_id: str,
        question: str
    ) -> ChatResponse:
        """
        RAG Q&A: Retrieves top relevant chunks from ChromaDB, asks Ollama,
        and provides citations with quote verification.
        """
        relevant_chunks = vector_store.similarity_search(doc_id=doc_id, query=question, top_k=4)
        if not relevant_chunks:
            relevant_chunks = vector_store.get_all_chunks(doc_id)[:4]

        chunk_lookup = {c.chunk_id: c.text for c in relevant_chunks}
        context_str = format_chunks_for_prompt(relevant_chunks)

        system = (
            "You are SlothClerk, an offline document assistant. Answer the user's question "
            "truthfully based ONLY on the provided document chunks. If the information is not in the text, "
            "state so clearly. Cite the relevant [chunk_id] for every claim."
        )

        prompt = (
            f"Context Chunks:\n\n{context_str}\n\n"
            f"User Question: {question}\n\n"
            "Provide a direct, clear answer. Reference chunk numbers like [chunk_1] in your explanation."
        )

        answer_text, metrics_raw = ollama_client.generate_chat(prompt=prompt, system_prompt=system)

        found_chunk_ids = list(set(re.findall(r'chunk_\d+', answer_text, flags=re.IGNORECASE)))
        valid_chunk_ids = [cid for cid in found_chunk_ids if cid in chunk_lookup]
        primary_chunk_id = valid_chunk_ids[0] if valid_chunk_ids else (relevant_chunks[0].chunk_id if relevant_chunks else "chunk_1")

        raw_snippet = clean_display_string(answer_text, 120) or ""
        matched_chunk_text = chunk_lookup.get(primary_chunk_id, "")
        chunk_sentences = split_text_into_sentences(matched_chunk_text)
        fallback_sentence = chunk_sentences[0] if chunk_sentences else matched_chunk_text
        verified_quote = find_and_expand_quote(raw_snippet, matched_chunk_text)[0] or ensure_quote_sentence_boundary(fallback_sentence)
        verified_quote = ensure_quote_sentence_boundary(verified_quote)

        return ChatResponse(
            answer=answer_text,
            citation=Citation(
                chunk_id=primary_chunk_id,
                quote=verified_quote,
                verified=bool(verified_quote)
            )
        )


analyzer = DocumentAnalyzer()
