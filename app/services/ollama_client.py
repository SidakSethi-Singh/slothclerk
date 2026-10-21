import json
import re
import time
from typing import Type, TypeVar, Tuple, Dict, Any, List, Optional
import httpx
from pydantic import BaseModel
from app.config import settings

T = TypeVar("T", bound=BaseModel)


class OllamaClientError(Exception):
    """Raised when Ollama request fails or Ollama is offline."""
    pass


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.REQUEST_TIMEOUT_SECONDS

    def get_client(self) -> httpx.Client:
        # Strictly local client with no proxies
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            trust_env=False
        )

    def check_connection(self) -> Dict[str, Any]:
        """Checks if local Ollama daemon is reachable and lists downloaded models."""
        try:
            with self.get_client() as client:
                res = client.get("/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return {
                        "reachable": True,
                        "models": models,
                        "has_llm": any(settings.OLLAMA_LLM_MODEL in m for m in models),
                        "has_embed": any(settings.OLLAMA_EMBED_MODEL in m for m in models)
                    }
                return {
                    "reachable": False,
                    "error": f"Ollama HTTP {res.status_code}",
                    "models": [],
                    "has_llm": False,
                    "has_embed": False
                }
        except Exception as e:
            return {
                "reachable": False,
                "error": f"Cannot connect to local Ollama at {self.base_url}: {str(e)}",
                "models": [],
                "has_llm": False,
                "has_embed": False
            }

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Generates embedding for a text using local Ollama model."""
        embed_model = model or settings.OLLAMA_EMBED_MODEL
        try:
            with self.get_client() as client:
                # Try newer /api/embed first
                embed_payload = {"model": embed_model, "input": text}
                res = client.post("/api/embed", json=embed_payload)
                if res.status_code == 200:
                    data = res.json()
                    embeddings = data.get("embeddings", [])
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]

                # Fallback to /api/embeddings
                legacy_payload = {"model": embed_model, "prompt": text}
                res = client.post("/api/embeddings", json=legacy_payload)
                if res.status_code == 200:
                    data = res.json()
                    embedding = data.get("embedding", [])
                    if embedding:
                        return embedding

                raise OllamaClientError(
                    f"Embedding failed (HTTP {res.status_code}): {res.text}"
                )
        except Exception as e:
            if isinstance(e, OllamaClientError):
                raise
            raise OllamaClientError(f"Error connecting to local Ollama for embeddings: {str(e)}")

    def get_embeddings_batch(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """Batch embedding generation with sequential fallback."""
        embed_model = model or settings.OLLAMA_EMBED_MODEL
        try:
            with self.get_client() as client:
                res = client.post("/api/embed", json={"model": embed_model, "input": texts})
                if res.status_code == 200:
                    data = res.json()
                    embeddings = data.get("embeddings", [])
                    if len(embeddings) == len(texts):
                        return embeddings
        except Exception:
            pass

        # Fallback to sequential
        results: List[List[float]] = []
        for text in texts:
            results.append(self.get_embedding(text, model=embed_model))
        return results

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0
    ) -> Tuple[T, Dict[str, Any]]:
        """
        Uses Ollama's structured output capability by passing the Pydantic JSON schema
        via the `format` parameter. Falls back to repair and retry logic if needed.
        Returns (parsed_instance, metrics_dict).
        """
        target_model = model or settings.OLLAMA_LLM_MODEL
        json_schema = response_model.model_json_schema()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": target_model,
            "messages": messages,
            "format": json_schema,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "seed": 42,
                "num_predict": 1024,
                "repeat_penalty": 1.15
            }
        }

        start_time = time.perf_counter()
        raw_text = ""
        metrics = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0.0,
            "model_name": target_model
        }

        try:
            with self.get_client() as client:
                res = client.post("/api/chat", json=payload)
                if res.status_code != 200:
                    # Try /api/generate fallback if /api/chat is unsupported
                    gen_payload = {
                        "model": target_model,
                        "prompt": (f"System: {system_prompt}\n\n" if system_prompt else "") + prompt,
                        "format": json_schema,
                        "stream": False,
                        "options": {
                            "temperature": 0.0,
                            "seed": 42,
                            "num_predict": 1024,
                            "repeat_penalty": 1.15
                        }
                    }
                    res = client.post("/api/generate", json=gen_payload)

                if res.status_code != 200:
                    raise OllamaClientError(
                        f"Ollama generation failed (HTTP {res.status_code}): {res.text}"
                    )

                data = res.json()
                raw_text = (
                    data.get("message", {}).get("content")
                    or data.get("response")
                    or ""
                )

                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", 0)
                total_duration_ns = data.get("total_duration")

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                if total_duration_ns:
                    elapsed_ms = total_duration_ns / 1_000_000.0

                metrics["prompt_tokens"] = prompt_tokens
                metrics["completion_tokens"] = completion_tokens
                metrics["total_tokens"] = prompt_tokens + completion_tokens
                metrics["latency_ms"] = round(elapsed_ms, 2)

        except Exception as e:
            if isinstance(e, OllamaClientError):
                raise
            raise OllamaClientError(f"Ollama request error: {str(e)}")

        # Parse & Validate with repair fallback
        parsed_instance, parse_err = self._parse_and_validate(raw_text, response_model)
        if parsed_instance is not None:
            return parsed_instance, metrics

        print(f"[OLLAMA WARNING] Initial validation failed for {response_model.__name__}: {parse_err}. Raw text:\n{raw_text}", flush=True)

        # Retry once with explicit json correction prompt
        print(f"[OLLAMA RETRY] Initiating schema repair prompt for {response_model.__name__}...", flush=True)
        repaired_instance, retry_metrics = self._retry_repair(
            raw_text=raw_text,
            response_model=response_model,
            target_model=target_model
        )
        metrics["prompt_tokens"] += retry_metrics.get("prompt_tokens", 0)
        metrics["completion_tokens"] += retry_metrics.get("completion_tokens", 0)
        metrics["total_tokens"] = metrics["prompt_tokens"] + metrics["completion_tokens"]
        metrics["latency_ms"] += retry_metrics.get("latency_ms", 0.0)

        return repaired_instance, metrics

    def generate_chat(
        self,
        prompt: str,
        system_prompt: str,
        model: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Generates plain-text RAG completion with metrics."""
        target_model = model or settings.OLLAMA_LLM_MODEL
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.2}
        }

        start_time = time.perf_counter()
        try:
            with self.get_client() as client:
                res = client.post("/api/chat", json=payload)
                if res.status_code != 200:
                    raise OllamaClientError(f"Ollama chat error HTTP {res.status_code}: {res.text}")
                data = res.json()
                content = data.get("message", {}).get("content", "").strip()

                total_duration_ns = data.get("total_duration")
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                if total_duration_ns:
                    elapsed_ms = total_duration_ns / 1_000_000.0

                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", 0)

                metrics = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "latency_ms": round(elapsed_ms, 2),
                    "model_name": target_model
                }
                return content, metrics
        except Exception as e:
            if isinstance(e, OllamaClientError):
                raise
            raise OllamaClientError(f"Error querying Ollama: {str(e)}")

    def _parse_and_validate(self, raw_text: str, response_model: Type[T]) -> Tuple[Optional[T], Optional[str]]:
        """Tries parsing raw JSON and markdown-wrapped JSON into Pydantic model. Returns (instance, error_msg)."""
        if not raw_text or not raw_text.strip():
            return None, "Raw response text is empty"

        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        # Clean weird non-printable/invalid bytes
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", cleaned)

        last_error = None
        try:
            return response_model.model_validate_json(cleaned), None
        except Exception as e:
            last_error = str(e)

        # Try JSONDecoder.raw_decode to handle valid prefix with trailing garbage
        try:
            data, _ = json.JSONDecoder().raw_decode(cleaned)
            return response_model.model_validate(data), None
        except Exception:
            pass

        # Try regex search for first outermost { ... }
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            candidate = match.group(1)
            try:
                return response_model.model_validate_json(candidate), None
            except Exception as e:
                last_error = str(e)
                try:
                    data = json.loads(candidate)
                    return response_model.model_validate(data), None
                except Exception as e2:
                    last_error = f"{e}; JSON dict load error: {e2}"

        # If truncated or looped at the end, try trimming backwards to last valid object
        last_brace = cleaned.rfind("}")
        while last_brace > 100:
            sub = cleaned[:last_brace + 1]
            open_b = sub.count("{") - sub.count("}")
            open_k = sub.count("[") - sub.count("]")
            if open_k >= 0 and open_b >= 0:
                candidate = sub + ("]" * open_k) + ("}" * open_b)
                try:
                    data = json.loads(candidate)
                    return response_model.model_validate(data), None
                except Exception:
                    pass
            last_brace = cleaned.rfind("}", 0, last_brace)

        # If unterminated, try closing unclosed quotes/brackets
        if cleaned.startswith("{") and not cleaned.endswith("}"):
            truncated = cleaned.rstrip()
            if truncated.count('"') % 2 != 0:
                truncated += '"'
            open_braces = truncated.count("{") - truncated.count("}")
            open_brackets = truncated.count("[") - truncated.count("]")
            if open_brackets > 0:
                truncated += "]" * open_brackets
            if open_braces > 0:
                truncated += "}" * open_braces
            try:
                data = json.loads(truncated)
                return response_model.model_validate(data), None
            except Exception:
                pass

        return None, last_error

    def _retry_repair(
        self,
        raw_text: str,
        response_model: Type[T],
        target_model: str
    ) -> Tuple[T, Dict[str, Any]]:
        """One-shot retry to repair invalid JSON to strictly fit schema."""
        json_schema = response_model.model_json_schema()
        # Deduplicate repeating lines to prevent context bloat
        lines = raw_text.splitlines()
        seen = set()
        deduped = []
        for line in lines:
            s_line = line.strip()
            if s_line in seen and len(s_line) > 10:
                continue
            seen.add(s_line)
            deduped.append(line)
        trimmed_raw = "\n".join(deduped)[:1800].strip()

        repair_messages = [
            {
                "role": "system",
                "content": (
                    "You are a precise JSON repair agent. Convert the given malformed or partial output "
                    "into valid JSON that strictly conforms to the provided schema. "
                    "Output ONLY the JSON object and nothing else."
                )
            },
            {
                "role": "user",
                "content": f"Schema:\n{json.dumps(json_schema)}\n\nInput to fix:\n{trimmed_raw}"
            }
        ]

        start_time = time.perf_counter()
        with self.get_client() as client:
            res = client.post(
                "/api/chat",
                json={
                    "model": target_model,
                    "messages": repair_messages,
                    "format": json_schema,
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "seed": 42,
                        "num_predict": 1024,
                        "repeat_penalty": 1.15
                    }
                }
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            if res.status_code == 200:
                data = res.json()
                fixed_text = data.get("message", {}).get("content", "").strip()
                parsed_instance, err = self._parse_and_validate(fixed_text, response_model)
                if parsed_instance is not None:
                    metrics = {
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                        "latency_ms": round(elapsed_ms, 2)
                    }
                    return parsed_instance, metrics

        raise OllamaClientError(
            f"Failed to produce valid structured JSON for schema {response_model.__name__} after retry."
        )


ollama_client = OllamaClient()
