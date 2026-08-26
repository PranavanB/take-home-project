# Model smoke-test record

Started: 2026-08-21  
Updated: 2026-08-26

## Environment

- GPU: NVIDIA GeForce RTX 5090, compute capability 12.0
- Driver: 610.62
- VRAM: 32,607 MiB total; approximately 30,383 MiB free before model loading
- Docker engine: 28.3.2
- Primary LLM runtime: dedicated vLLM Docker container
- vLLM image: `vllm/vllm-openai:v0.26.0`
- Pinned linux/amd64 digest:
  `sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b`
- Candidate model: `unsloth/Qwen3.6-35B-A3B-NVFP4-Fast`
- Host endpoint: `http://127.0.0.1:8001/v1`
- Container endpoint used by the API: `http://vllm:8000/v1`

## Passed

### Earlier Nomic embedding check

- Model identifier: `nomic-embed-text-v1.5`
- Endpoint: `POST /v1/embeddings`
- Inputs used the required `search_document:` and `search_query:` prefixes
- Returned two vectors
- Dimensions: 768

This was the first gateway smoke check. Nomic is no longer the configured application
model; the product owner subsequently selected Snowflake Arctic Embed 2.0.

### Current Arctic Embed 2.0 check

- Model identifier: `Snowflake/snowflake-arctic-embed-m-v2.0`
- Runtime: Hugging Face Text Embeddings Inference CPU image `cpu-1.9`, pinned by digest
- Host endpoint: `http://127.0.0.1:8002/v1/embeddings`
- Container endpoint: `http://embedding:80/v1/embeddings`
- Dimensions: 768
- Maximum model context reported by the runtime: 8,192 tokens
- Query phrases use `query: `; catalogue descriptions are unprefixed
- The first ONNX weight download took 214.26 seconds and is now held in the persistent
  `embedding_cache` Docker volume
- The service completed its warm-up and reported ready on port 80

The live synthetic mapping check compared twelve phrases with all 56 catalogue entries.
The selected POC policy is a minimum cosine similarity of `0.25` plus a minimum `0.04`
lead over the second-ranked concept. Examples:

| Phrase | Best concept | Similarity | Runner-up margin | POC outcome |
|---|---|---:|---:|---|
| building RESTful web services | design application interfaces | 0.3310 | 0.1379 | accept |
| automated software delivery pipelines | DevOps | 0.3393 | 0.1651 | accept |
| monitoring application logs | observe logs | 0.4418 | 0.2868 | accept |
| communicating with business leaders | communicate with stakeholders | 0.4400 | 0.2463 | accept |
| container orchestration platform | Docker, then Kubernetes | 0.2532 | 0.0341 | reject as ambiguous |
| spreadsheet expertise | Tableau | 0.3086 | 0.0080 | reject as ambiguous |
| writing legal contracts | apply technical communication skills | 0.1561 | 0.0265 | reject as weak |

These values are similarity measurements, not confidence probabilities. A labelled domain
evaluation is still required before treating the cutoffs as production policy.

### Structured LLM generation

Passed with `unsloth/Qwen3.6-35B-A3B-NVFP4-Fast` served as `job-matcher-llm`:

- vLLM resolved `Qwen3_5MoeForConditionalGeneration` on the RTX 5090.
- It selected native FlashInfer/CUTLASS NVFP4 and `sm120` Blackwell kernels rather than
  emulation.
- The checkpoint is 22.02 GiB; model weights use 20.61 GiB of GPU memory.
- vLLM allocated 4.91 GiB of KV cache and 364,916 cache tokens.
- First engine initialisation took 158.82 seconds, including 56.31 seconds for compilation.
- The persistent compile cache reduced a repeated engine initialisation to 36.36 seconds
  and compilation to 5.40 seconds.
- One earlier four-category profile completed in 18.51 seconds with two roles, ten skills, one
  qualification, and one degree.
- Two simultaneous profiles completed in 21.47 and 22.72 seconds. Both returned two roles,
  nine skills, one qualification, and one degree.
- Peak GPU memory during that concurrency test was 30,290 MiB.
- A live PDF upload completed the worker path in 14.6 seconds, deleted the raw PDF, returned
  the correct current role first, and deleted the whole temporary session when closed.

The original one-request schema was structurally valid but under-extracted categories. A
thinking-mode experiment recovered skills, qualifications, and education but still omitted
experience. Four focused schema-constrained passes succeeded without thinking mode, so that
is the selected profile-extraction design.

All smoke tests use only synthetic CV text. Normal output contains identifiers, timing, and
category counts—not CV content.

### Post-Arctic end-to-end status

A synthetic PDF upload was started after the Arctic service and calibrated thresholds were
connected to the API. That earlier run used the pipeline version active at the time and was
intentionally interrupted before completion when the GPU was released. It is therefore
**not** recorded as a passed end-to-end check for the current persisted-job pipeline.

The earlier live PDF upload described above remains a valid pass for the grounded vLLM
profile pipeline and exact fixture matcher, but it predates the current Experience category,
persisted job requirements, and live Arctic mapping used for CV skill phrases.

### 26 August readiness rerun

- The CPU Arctic endpoint returned HTTP 200 from its health endpoint.
- vLLM loaded all five checkpoint shards in 52.58 seconds, reused its compile cache, and
  exposed `job-matcher-llm` from `/v1/models`.
- vLLM reported 20.61 GiB for model loading, 4.91 GiB of KV cache, and 364,916 cache tokens.
- Host GPU use reached approximately 29,920 MiB of 32,607 MiB after model warm-up.
- A synthetic Jordan Taylor PDF was generated from `seed/sample-resume.md` for the browser
  journey. The in-app automation's file chooser did not expose a file-selection event, so
  the PDF never reached the application and no result from this attempt is claimed.
- The user then requested that Job Matcher GPU work stop while ComfyUI remain available, so
  the rerun ended before CV processing.

## Current runtime state

As of 26 August 2026:

- the vLLM container is stopped to release the RTX 5090;
- the CPU-only Arctic embedding container is also stopped;
- ComfyUI, Comfy Desktop, and the ComfyUI Python process remain running as requested;
- after the Job Matcher model services stopped, total GPU use was approximately 3,113 MiB
  of 32,607 MiB; and
- the API and frontend remain running. The jobs catalogue is available, but new CV
  processing cannot complete until both vLLM and Arctic are restarted.

## Pending

### Reranking

Infinity and `BAAI/bge-reranker-v2-m3` have not yet been started or tested. The gateway
must not claim reranking readiness until a real request passes.
