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

Security hardening pass complete (2026-07-16): API-key auth on all `/api/*` routes, rate
limiting (slowapi), upload validation (extension allowlist + size cap + magic bytes), Ollama's
port no longer published to the host, app container runs non-root/read-only/cap-dropped,
multi-stage Docker build (no `pip`/`uv` in the final image), and CI (`pip-audit` + Trivy image
scan). This was a deliberate pivot from "AI engineering demo" toward "DevOps/security portfolio
piece" — see README's new Security section for the full threat model. All of it verified live
(not just written), including a real bug caught during testing: a stale root-owned sqlite file
from before the non-root user change broke writes under `read_only: true` until removed —
worth remembering if `data/db/vectors.db` ever throws "attempt to write a readonly database"
again after changing container user/permissions.

## Environment notes
- Developed on WSL2, 16GB RAM, no confirmed GPU passthrough (AMD GPU present but ROCm isn't
  officially supported under WSL2, and this sandboxed shell couldn't detect `/dev/dri` at all).
  Ollama handles GPU/CPU dispatch transparently, so the app never needs to know.
- No system `pip` in this environment — all Python dependency management goes through `uv`
  (`uv sync`, `uv run`). `uv.lock` is committed for reproducible Docker builds.
- Smoke-tested with `llama3.2:1b` + `nomic-embed-text` for speed (fast download). Production
  default in docker-compose.yml is `llama3.1:8b-instruct-q4_K_M`, which fits comfortably in
  the 16GB RAM budget — see README's "Design decisions" section for the quantization tradeoff.

Monitoring integration added (2026-07-16, sysadmin track part B): a `/metrics` Prometheus
endpoint (API-key protected — request volume/activity is more sensitive than the bare
up/down `/health` check) exposing `rag_http_requests_total{endpoint,status}`,
`rag_documents_ingested_total`, `rag_chat_requests_total`, and a live-checked
`rag_ollama_up` gauge. Plus `zabbix/template_local_rag_assistant_metrics.yaml`, following
the exact conventions of the existing `keycloak-zabbix-monitoring` repo (HTTP agent master
item + Prometheus-pattern dependent items + triggers), reusing its Google Chat webhook
media type for alert routing rather than standing up a new one. Verified live: auth
enforced, business counters increment correctly on real ingest/chat calls, and the
route-template label (`/api/sources/{source}`) avoids per-filename cardinality blowup.

## Remaining/optional work (not started, not blocking)
- No conversation persistence — chat history lives only in the browser tab.
- No reranking step — plain top-k cosine similarity via sqlite-vec; would matter more at a
  much larger document count than this is designed for.
- No test suite (pytest etc.) — everything verified via live docker-compose/curl smoke tests.
- Portfolio site (`~/portfolio-site/projects/`) does not yet have an entry linking to this repo.
- The Zabbix template has never been imported into a real Zabbix instance and verified end
  to end — it's been validated for YAML correctness and consistency with the existing
  keycloak template's conventions, but not exercised against live Zabbix.
