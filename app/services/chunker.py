from typing import List, Dict, Any, Optional
import re
from app.models import Chunk
from app.config import settings


def create_chunks(
    doc_id: str,
    segments: List[Dict[str, Any]],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None
) -> List[Chunk]:
    """
    Chunks extracted document segments strictly on paragraph and sentence boundaries.
    Never splits mid-word or mid-sentence.
    Preserves page numbers and ensures natural reading flow.
    """
    target_size = chunk_size or settings.CHUNK_SIZE
    overlap_limit = chunk_overlap or settings.CHUNK_OVERLAP

    chunks: List[Chunk] = []
    chunk_counter = 1
    running_char_offset = 0

    for seg in segments:
        page_num = seg.get("page")
        seg_text = seg.get("text", "").strip()
        if not seg_text:
            continue

        # Split into atomic sentences or paragraphs, respecting punctuation
        raw_sentences = [
            s.strip() for s in re.split(r'(?<=[.!?\n])\s+', seg_text) if s.strip()
        ]
        if not raw_sentences:
            continue

        # If entire segment fits within target_size + 150 tolerance, keep it intact
        if len(seg_text) <= target_size + 150:
            chunk = Chunk(
                chunk_id=f"chunk_{chunk_counter}",
                doc_id=doc_id,
                index=chunk_counter,
                text=seg_text,
                page=page_num,
                char_start=running_char_offset,
                char_end=running_char_offset + len(seg_text)
            )
            chunks.append(chunk)
            chunk_counter += 1
            running_char_offset += len(seg_text) + 1
            continue

        # Segment exceeds target size: pack sentences without splitting them
        i = 0
        n = len(raw_sentences)
        while i < n:
            current_sentences = []
            current_len = 0
            start_i = i

            while i < n:
                sent = raw_sentences[i]
                sent_len = len(sent) + (1 if current_sentences else 0)
                if current_len + sent_len > target_size and current_sentences:
                    break
                current_sentences.append(sent)
                current_len += sent_len
                i += 1

            chunk_text = " ".join(current_sentences).strip()
            if chunk_text:
                char_start = seg_text.find(current_sentences[0])
                last_sent = current_sentences[-1]
                char_end = seg_text.find(last_sent, char_start) + len(last_sent)
                chunk = Chunk(
                    chunk_id=f"chunk_{chunk_counter}",
                    doc_id=doc_id,
                    index=chunk_counter,
                    text=chunk_text,
                    page=page_num,
                    char_start=running_char_offset + (char_start if char_start != -1 else 0),
                    char_end=running_char_offset + (char_end if char_end != -1 else len(chunk_text))
                )
                chunks.append(chunk)
                chunk_counter += 1

            if i >= n:
                break

            # Overlap: step back 1 whole sentence if it fits in overlap_limit
            overlap_chars = 0
            back_steps = 0
            for back_idx in range(i - 1, start_i, -1):
                sent_len = len(raw_sentences[back_idx])
                if overlap_chars + sent_len <= overlap_limit and back_steps < 2:
                    overlap_chars += sent_len
                    back_steps += 1
                else:
                    break

            i = max(start_i + 1, i - back_steps)

        running_char_offset += len(seg_text) + 1

    return chunks
