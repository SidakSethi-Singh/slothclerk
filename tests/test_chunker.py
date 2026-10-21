from app.services.chunker import create_chunks


def test_chunker_basic():
    doc_id = "test_doc"
    # Create segment of ~2500 chars
    long_paragraph = "This is a legal clause explaining party obligations and liabilities. " * 40
    segments = [{"page": 1, "text": long_paragraph}]

    chunks = create_chunks(doc_id=doc_id, segments=segments, chunk_size=1100, chunk_overlap=150)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.doc_id == doc_id
        assert c.chunk_id.startswith("chunk_")
        assert len(c.text) <= 1250
        assert c.page == 1


def test_chunker_preserves_page_numbers():
    segments = [
        {"page": 1, "text": "Page one text content that is distinct and short."},
        {"page": 2, "text": "Page two text content that is also distinct and short."}
    ]
    chunks = create_chunks("multi_page_doc", segments)
    assert len(chunks) == 2
    assert chunks[0].page == 1
    assert chunks[1].page == 2
    assert "Page one" in chunks[0].text
    assert "Page two" in chunks[1].text
