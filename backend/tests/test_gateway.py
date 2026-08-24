import json

import httpx
import pytest

from app.gateway import (
    LLMGatewayError,
    OpenAIEmbeddingGateway,
    VLLMProfileDraftGenerator,
)


@pytest.mark.asyncio
async def test_vllm_generator_requests_json_schema_and_returns_object() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"experiences": []})}}
                ]
            },
        )

    generator = VLLMProfileDraftGenerator(
        base_url="http://vllm:8000/v1/",
        model="job-matcher-llm",
        transport=httpx.MockTransport(handler),
    )
    schema = {"type": "object", "properties": {"experiences": {"type": "array"}}}

    result = await generator.generate(
        system_prompt="system",
        user_prompt="user",
        json_schema=schema,
    )

    assert result == {"experiences": []}
    assert captured["model"] == "job-matcher-llm"
    assert captured["temperature"] == 0
    assert captured["max_tokens"] == 8192
    assert captured["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "candidate_profile", "schema": schema},
    }
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_vllm_generator_rejects_invalid_json_without_exposing_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json secret CV text"}}]},
        )

    generator = VLLMProfileDraftGenerator(
        base_url="http://vllm:8000/v1",
        model="job-matcher-llm",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGatewayError) as caught:
        await generator.generate(system_prompt="system", user_prompt="user", json_schema={})

    assert "secret CV text" not in str(caught.value)


@pytest.mark.asyncio
async def test_embedding_gateway_adds_arctic_query_prefix_and_orders_vectors() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    gateway = OpenAIEmbeddingGateway(
        base_url="http://embedding:80/v1/",
        model="Snowflake/snowflake-arctic-embed-m-v2.0",
        transport=httpx.MockTransport(handler),
    )

    vectors = await gateway.embed(
        model="Snowflake/snowflake-arctic-embed-m-v2.0",
        texts=["Python", "Kubernetes"],
        task="search_query",
    )

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["url"] == "http://embedding/v1/embeddings"
    assert captured["model"] == "Snowflake/snowflake-arctic-embed-m-v2.0"
    assert captured["input"] == ["query: Python", "query: Kubernetes"]


@pytest.mark.asyncio
async def test_embedding_gateway_leaves_arctic_catalog_documents_unprefixed() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
        )

    gateway = OpenAIEmbeddingGateway(
        base_url="http://embedding:80/v1",
        model="Snowflake/snowflake-arctic-embed-m-v2.0",
        transport=httpx.MockTransport(handler),
    )

    await gateway.embed(
        model="Snowflake/snowflake-arctic-embed-m-v2.0",
        texts=["Kubernetes. Container orchestration and deployment."],
        task="search_document",
    )

    assert captured["input"] == ["Kubernetes. Container orchestration and deployment."]
