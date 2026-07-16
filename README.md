# Local RAG Assistant

A private, fully local document Q&A assistant. Upload PDFs, notes, or markdown files
and ask questions about them — the model, the embeddings, and the vector store all
run on your own hardware. No document content or query ever leaves the machine.

![status](https://img.shields.io/badge/status-working-brightgreen)

## Why this exists

Cloud LLM APIs are the easy path for "chat with your documents," but that means
uploading potentially sensitive files (contracts, internal memos, personal notes) to
a third party. This project answers a narrower, harder question: **how good an
experience can you build with everything running locally**, on modest consumer
hardware, with no GPU dependency required?

## Architecture

```
┌─────────────┐      HTTP       ┌──────────────┐      HTTP      ┌─────────┐
│   Browser   │ ─────────────▶  │   FastAPI    │ ─────────────▶ │ Ollama  │
│  (chat UI)  │ ◀─────────────  │  (RAG logic) │ ◀───────────── │(models) │
└─────────────┘   SSE stream    └──────┬───────┘   generate/    └─────────┘
                                        │            embeddings
                                        ▼
                                 ┌─────────────┐
                                 │  sqlite-vec │
                                 │ (vector db) │
                                 └─────────────┘
```

1. **Ollama** serves both the chat model and the embedding model. One runtime, one
   container, no separate GPU-serving stack to maintain.
2. **FastAPI app** handles ingestion (chunk → embed → store) and chat (embed query →
   retrieve top-k chunks → build prompt → stream response back over SSE).
3. **sqlite-vec** is the vector store — a SQLite extension, not a separate database
   server. For a single-user local tool, running a Postgres/pgvector or Chroma
   server alongside would be pure overhead.
4. **Static HTML/JS UI** — no frontend build step, deliberately. This is a tool, not
   a product; a build pipeline would add complexity with no payoff here.

## Design decisions (and why)

- **Ollama over raw `llama-cpp-python`**: Ollama wraps llama.cpp with model
  management (pull, quantization selection, GPU/CPU dispatch) and a stable HTTP API.
  Running it in its own container also means the app container has zero ML
  dependencies — just FastAPI, httpx, and sqlite-vec.
- **CPU-first, GPU-optional**: developed and tested against 16GB RAM / no confirmed
  GPU passthrough (AMD GPU under WSL2, where ROCm isn't officially supported).
  Ollama auto-detects a usable GPU (CUDA, ROCm, or Vulkan fallback) and falls back to
  CPU otherwise — the app doesn't need to know or care which path is active.
- **Model choice — quantized 7-8B instruct models (Q4_K_M)**: at Q4 quantization an
  8B model needs roughly 4.5-5GB of RAM, leaving headroom for the embedding model and
  the OS inside a 16GB budget. Going to Q8 or fp16 would roughly double memory
  pressure for a quality gain that doesn't matter much for retrieval-grounded
  answers. Going smaller (3B) frees more RAM but measurably hurts instruction-
  following on multi-fact questions — noticeable during testing with `llama3.2:1b`,
  which is fine for smoke-testing the pipeline but noticeably worse at faithfully
  citing multiple facts than an 8B model.
- **sqlite-vec over Chroma/Postgres+pgvector**: this is a single-user, single-machine
  tool. A client-server vector database adds a process to manage for no retrieval-
  quality benefit at this scale (thousands, not millions, of chunks).
- **Boundary-aware chunking over fixed-width splitting**: the chunker
  (`src/rag.py::chunk_text`) prefers to break on paragraph or sentence boundaries
  near the target size instead of cutting mid-sentence, which keeps retrieved chunks
  semantically coherent — implemented directly rather than pulling in a framework
  like LangChain for a ~20-line function.
- **The prompt explicitly instructs the model to say "I don't know" when the
  context doesn't cover the question** — grounding the model in retrieved context
  is what keeps a small local model from confidently hallucinating.

## Running it

```bash
docker compose up -d --build
./scripts/setup_models.sh   # pulls the chat + embedding models into the ollama container
```

Then open http://localhost:8001.

To use a different model size (e.g. for lower-RAM machines), override before starting:

```bash
OLLAMA_CHAT_MODEL=llama3.2:3b OLLAMA_EMBED_MODEL=nomic-embed-text docker compose up -d --build
./scripts/setup_models.sh
```

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ingest` | POST (multipart) | Upload a `.pdf`, `.txt`, or `.md` file — chunked, embedded, stored |
| `/api/sources` | GET | List ingested document names |
| `/api/sources/{name}` | DELETE | Remove a document and its chunks |
| `/api/chat` | POST | `{message, history}` → SSE stream of `{type: sources|token|done}` events |

## Stack

FastAPI · Ollama (Llama 3.1 8B / Mistral 7B, quantized GGUF) · sqlite-vec ·
vanilla HTML/CSS/JS · Docker Compose

## What's not here (yet)

- Multi-user auth — this is a single-user local tool by design.
- Conversation persistence across restarts — history lives in the browser tab only.
- Reranking — top-k cosine similarity only; a cross-encoder rerank step would
  improve precision on larger document sets but wasn't justified at this scale.
