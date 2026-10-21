from typing import List, Dict, Any, Optional
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings
from app.models import Chunk
from app.services.ollama_client import ollama_client


class VectorStore:
    def __init__(self):
        # Strict offline configuration with anonymized telemetry disabled
        self.client = chromadb.PersistentClient(
            path=str(Path(settings.CHROMA_PERSIST_DIRECTORY).resolve()),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                is_persistent=True
            )
        )
        self.collection_name = "slothclerk_documents"
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            # We never set an embedding_function here, ensuring Chroma never downloads ONNX models
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "SlothClerk local offline document chunks"}
            )
        return self._collection

    def add_chunks(self, doc_id: str, chunks: List[Chunk]) -> None:
        """Embeds and persists document chunks using local Ollama embeddings."""
        if not chunks:
            return

        texts = [c.text for c in chunks]
        embeddings = ollama_client.get_embeddings_batch(texts)

        ids = [f"{doc_id}_{c.chunk_id}" for c in chunks]
        metadatas = [
            {
                "doc_id": doc_id,
                "chunk_id": c.chunk_id,
                "index": c.index,
                "page": c.page if c.page is not None else -1,
                "char_start": c.char_start,
                "char_end": c.char_end
            }
            for c in chunks
        ]

        # Upsert into Chroma with precomputed embeddings
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

    def similarity_search(self, doc_id: str, query: str, top_k: int = 5) -> List[Chunk]:
        """Performs vector similarity search against a specific document's chunks."""
        query_embedding = ollama_client.get_embedding(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"doc_id": doc_id}
        )

        matched_chunks: List[Chunk] = []
        if results and results.get("ids") and len(results["ids"]) > 0:
            doc_ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else []
            metas = results["metadatas"][0] if results.get("metadatas") else []

            for i in range(len(doc_ids)):
                meta = metas[i] if i < len(metas) else {}
                text = docs[i] if i < len(docs) else ""
                page_val = meta.get("page")
                page_num = None if page_val == -1 else page_val

                matched_chunks.append(
                    Chunk(
                        chunk_id=meta.get("chunk_id", f"chunk_{i+1}"),
                        doc_id=doc_id,
                        index=meta.get("index", i + 1),
                        text=text,
                        page=page_num,
                        char_start=meta.get("char_start", 0),
                        char_end=meta.get("char_end", len(text))
                    )
                )

        # Sort by chunk index for coherent reading flow
        matched_chunks.sort(key=lambda x: x.index)
        return matched_chunks

    def get_all_chunks(self, doc_id: str) -> List[Chunk]:
        """Retrieves all chunks belonging to a document."""
        data = self.collection.get(
            where={"doc_id": doc_id},
            include=["documents", "metadatas"]
        )

        chunks: List[Chunk] = []
        if data and data.get("ids"):
            docs = data.get("documents", [])
            metas = data.get("metadatas", [])
            for i in range(len(data["ids"])):
                meta = metas[i] if i < len(metas) else {}
                text = docs[i] if i < len(docs) else ""
                page_val = meta.get("page")
                page_num = None if page_val == -1 else page_val

                chunks.append(
                    Chunk(
                        chunk_id=meta.get("chunk_id", f"chunk_{i+1}"),
                        doc_id=doc_id,
                        index=meta.get("index", i + 1),
                        text=text,
                        page=page_num,
                        char_start=meta.get("char_start", 0),
                        char_end=meta.get("char_end", len(text))
                    )
                )

        chunks.sort(key=lambda x: x.index)
        return chunks

    def get_chunk(self, doc_id: str, chunk_id: str) -> Optional[Chunk]:
        """Retrieves a single chunk by doc_id and chunk_id."""
        target_id = f"{doc_id}_{chunk_id}"
        data = self.collection.get(
            ids=[target_id],
            include=["documents", "metadatas"]
        )
        if data and data.get("ids") and len(data["ids"]) > 0:
            docs = data.get("documents", [])
            metas = data.get("metadatas", [])
            meta = metas[0] if metas else {}
            text = docs[0] if docs else ""
            page_val = meta.get("page")
            page_num = None if page_val == -1 else page_val
            return Chunk(
                chunk_id=meta.get("chunk_id", chunk_id),
                doc_id=doc_id,
                index=meta.get("index", 1),
                text=text,
                page=page_num,
                char_start=meta.get("char_start", 0),
                char_end=meta.get("char_end", len(text))
            )
        return None

    def delete_document(self, doc_id: str) -> None:
        """Removes all vector records for a document."""
        try:
            self.collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass


vector_store = VectorStore()

