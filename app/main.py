import os
import shutil
import hashlib
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel


from app.config import settings
from app.models import (
    DocumentAnalysisResponse,
    ChatRequest,
    ChatResponse,
    Chunk
)
from app.services.extractor import extract_document, ExtractionError
from app.services.chunker import create_chunks
from app.services.vector_store import vector_store
from app.services.analyzer import analyzer
from app.services.ollama_client import ollama_client
from app.services.exporter import export_markdown, export_json
from cli import analyze_document


app = FastAPI(
    title="SlothClerk",
    description="100% Offline Document Assistant powered by local Ollama & ChromaDB",
    version="1.0.0"
)

# Enable CORS for local client interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Upload directory setup
UPLOAD_DIR = Path(settings.UPLOAD_DIRECTORY)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Static directory setup
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health_check():
    """Returns local system health, offline guarantee, and Ollama connection status."""
    ollama_conn = ollama_client.check_connection()
    return {
        "status": "healthy" if ollama_conn.get("reachable") else "degraded",
        "offline": True,
        "ollama": ollama_conn,
        "active_models": {
            "llm": settings.OLLAMA_LLM_MODEL,
            "embed": settings.OLLAMA_EMBED_MODEL
        },
        "settings": {
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "strict_offline": settings.OFFLINE_MODE_ONLY
        }
    }


@app.post("/api/analyze", response_model=DocumentAnalysisResponse)
async def analyze_document_endpoint(file: UploadFile = File(...)):
    """
    Uploads a PDF or DOCX document, extracts text, chunks it, persists embeddings
    into local ChromaDB, and performs 2-stage grounded analysis via Ollama.
    """
    filename = file.filename or "uploaded_document"
    ext = Path(filename).suffix.lower()

    if ext not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Only .pdf and .docx documents are supported."
        )

    # Read and save file content
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Generate deterministic doc_id from file hash
    file_hash = hashlib.sha256(contents).hexdigest()[:12]
    doc_id = f"doc_{file_hash}"
    safe_name = f"{doc_id}_{Path(filename).name}"
    save_path = UPLOAD_DIR / safe_name

    with open(save_path, "wb") as f:
        f.write(contents)

    try:
        # Step 1: Text extraction
        segments = extract_document(save_path)
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=f"Text extraction failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected extraction error: {str(e)}")

    if not segments:
        raise HTTPException(status_code=422, detail="No readable text found in document.")

    # Step 2: Chunking
    chunks = create_chunks(
        doc_id=doc_id,
        segments=segments,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP
    )

    if not chunks:
        raise HTTPException(status_code=422, detail="Failed to generate document chunks.")

    # Step 3: Embed & Store in ChromaDB
    try:
        vector_store.add_chunks(doc_id=doc_id, chunks=chunks)
    except Exception as e:
        print(f"[VECTOR STORE WARNING] Failed to persist embeddings: {e}")

    # Step 4: Grounded Multi-Stage Analysis
    try:
        response = analyze_document(
            doc_id=doc_id,
            filename=filename,
            chunks=chunks
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@app.post("/api/export/markdown")
def export_markdown_endpoint(analysis: DocumentAnalysisResponse):
    """Generates and returns a downloadable Markdown audit report."""
    md_content = export_markdown(analysis)
    safe_filename = Path(analysis.filename).stem or "contract"
    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}_audit_report.md"'}
    )


@app.post("/api/export/json")
def export_json_endpoint(analysis: DocumentAnalysisResponse):
    """Generates and returns a downloadable structured JSON report."""
    json_content = export_json(analysis, indent=2)
    safe_filename = Path(analysis.filename).stem or "contract"
    return Response(
        content=json_content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}_audit_report.json"'}
    )



class ChatPayload(BaseModel):
    doc_id: str
    question: str


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatPayload):
    """Answers follow-up questions over the document chunks using local RAG."""
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        return analyzer.answer_question(
            doc_id=payload.doc_id,
            question=payload.question
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat query failed: {str(e)}")


@app.get("/api/chunks/{doc_id}/{chunk_id}")
def get_chunk_endpoint(doc_id: str, chunk_id: str):
    """Retrieves full text of a specific chunk for citation modal / popover."""
    chunk = vector_store.get_chunk(doc_id=doc_id, chunk_id=chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "page": chunk.page,
        "text": chunk.text,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end
    }


@app.get("/api/chunks/{doc_id}")
def get_all_chunks_endpoint(doc_id: str):
    """Retrieves all chunks for a document."""
    chunks = vector_store.get_all_chunks(doc_id=doc_id)
    return {"doc_id": doc_id, "chunks": chunks}


# Serve Single-Page App
@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"message": "SlothClerk API is running. UI file is loading..."})
    return FileResponse(index_file)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

samples_dir = Path(__file__).parent.parent / "samples"
if samples_dir.exists():
    app.mount("/samples", StaticFiles(directory=str(samples_dir)), name="samples")

