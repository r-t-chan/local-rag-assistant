# local-rag-assistant

## What this is
A private, fully local document Q&A assistant for the portfolio/resume. Upload PDFs/txt/md,
ask questions, get answers grounded in the uploaded content — chat model, embeddings, and
vector store all run locally via Docker. See README.md for the full architecture writeup and
design-decision rationale (why Ollama, why sqlite-vec, why quantized 7-8B, etc).

## Status
Working end-to-end: ingestion, chunking, embedding, retrieval, streaming chat, and citations
all verified via `docker compose up` + manual curl tests. Not yet deployed anywhere public —
it's a local Docker Compose app, not a hosted web service (that's a deliberate scope choice:
the point is "runs on your own hardware," so there's nothing to host).

## Environment notes
- Developed on WSL2, 16GB RAM, no confirmed GPU passthrough (AMD GPU present but ROCm isn't
  officially supported under WSL2, and this sandboxed shell couldn't detect `/dev/dri` at all).
  Ollama handles GPU/CPU dispatch transparently, so the app never needs to know.
- No system `pip` in this environment — all Python dependency management goes through `uv`
  (`uv sync`, `uv run`). `uv.lock` is committed for reproducible Docker builds.
- Smoke-tested with `llama3.2:1b` + `nomic-embed-text` for speed (fast download). Production
  default in docker-compose.yml is `llama3.1:8b-instruct-q4_K_M`, which fits comfortably in
  the 16GB RAM budget — see README's "Design decisions" section for the quantization tradeoff.

## Remaining/optional work (not started, not blocking)
- No auth — fine for a single-user local tool, would need it before any multi-user exposure.
- No conversation persistence — chat history lives only in the browser tab.
- No reranking step — plain top-k cosine similarity via sqlite-vec; would matter more at a
  much larger document count than this is designed for.
- Portfolio site (`~/portfolio-site/projects/`) does not yet have an entry linking to this repo.
