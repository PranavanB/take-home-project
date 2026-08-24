import json
from typing import Any

import httpx


class LLMGatewayError(RuntimeError):
    """A safe, content-free error raised for unusable model responses."""


class EmbeddingGatewayError(RuntimeError):
    """A safe, content-free error raised for unusable embedding responses."""


class VLLMProfileDraftGenerator:
    """Generate a schema-constrained profile draft through vLLM's OpenAI API."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 300,
        max_output_tokens: int = 8192,
        enable_thinking: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = httpx.Timeout(timeout_seconds)
        self.max_output_tokens = max_output_tokens
        self.enable_thinking = enable_thinking
        self.transport = transport

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        request = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "candidate_profile",
                    "schema": json_schema,
                },
            },
            "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
        }
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=request,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            result = json.loads(content)
            if not isinstance(result, dict):
                raise TypeError
            return result
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMGatewayError("vLLM returned an unusable structured response") from exc


class OpenAIEmbeddingGateway:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        query_prefix: str = "query: ",
        document_prefix: str = "",
        timeout_seconds: float = 120,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    async def embed(self, *, model: str, texts: list[str], task: str) -> list[list[float]]:
        if task not in {"search_document", "search_query"}:
            raise ValueError("Unsupported embedding task")
        if model != self.model:
            raise ValueError("Embedding model does not match the configured model")
        if not texts:
            return []
        prefix = self.query_prefix if task == "search_query" else self.document_prefix
        prefixed = [f"{prefix}{text}" for text in texts]
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": model, "input": prefixed},
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        try:
            ordered = sorted(payload["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in ordered]
            dimensions = {len(vector) for vector in vectors}
            if len(vectors) != len(texts) or len(dimensions) != 1 or not dimensions:
                raise ValueError
            return vectors
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingGatewayError(
                "The embedding service returned an unusable response"
            ) from exc


class ModelGateway(OpenAIEmbeddingGateway):
    """Backward-compatible wrapper for the earlier smoke-test gateway."""

    def __init__(
        self,
        *,
        llm_base_url: str,
        embedding_base_url: str,
        timeout_seconds: float = 120,
    ) -> None:
        self.llm_base_url = llm_base_url.rstrip("/")
        super().__init__(
            base_url=embedding_base_url,
            model="nomic-embed-text-v1.5",
            query_prefix="search_query: ",
            document_prefix="search_document: ",
            timeout_seconds=timeout_seconds,
        )
