# local-rag-assistant

## What this is
A private, fully local document Q&A assistant for the portfolio/resume. Upload PDFs/txt/md,
ask questions, get answers grounded in the uploaded content — chat model, embeddings, and
vector store all run locally via Docker. See README.md for the full architecture writeup and
design-decision rationale (why Ollama, why sqlite-vec, why quantized 7-8B, etc).

## Status
Working end-to-end: ingestion, chunking, embedding, retrieval, streaming chat, and citations
all verified via `docker compose up` + manual curl tests. Docker Compose is the primary
deployment path; a bare-metal/systemd path also exists (see below) as a secondary option.

Pushed to GitHub as a **private** repo: `r-t-chan/local-rag-assistant`. Workflow going forward
is feature branch → PR → user reviews/merges (not direct-to-main), except for genuinely urgent
one-line hotfixes (e.g. the trivy-action version pin fix on 2026-07-16, done directly on main).

Security hardening pass complete (2026-07-16, merged to main): API-key auth on all `/api/*`
routes, rate limiting (slowapi), upload validation (extension allowlist + size cap + magic
bytes), Ollama's port no longer published to the host, app container runs
non-root/read-only/cap-dropped, multi-stage Docker build, CI (`pip-audit` + Trivy image scan).
Real bug caught during testing: a stale root-owned sqlite file from before the non-root user
change broke writes under `read_only: true` until removed — worth remembering if
`data/db/vectors.db` ever throws "attempt to write a readonly database" again after changing
container user/permissions.

DevOps track complete (2026-07-16, merged via PR #1 + PR #2): Docker healthchecks +
`depends_on: condition: service_healthy`, resource limits, `/health` endpoint, structured JSON
logging, CI publish job (GHCR, gated behind lint/audit/scan), Dependabot. Also: the CI's
`trivy-action@0.24.0` pin was invalid all along (real tag is `v0.24.0` with a "v" prefix,
confirmed via `git ls-remote --tags` when the API was degraded) — fixed by pinning to
`v0.36.0`'s commit SHA instead of a mutable tag. `gh auth status`/some Actions API endpoints
were flaky/false-negative during this session due to a real GitHub-side "Partially Degraded
Service" incident (confirmed via githubstatus.com) — if `gh` misbehaves again, check
githubstatus.com and try `git ls-remote`/direct `curl` before assuming local auth is broken.

Sysadmin track in progress (2026-07-16) — see below.

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
- No conversation persistence — chat history lives only in the browser tab.
- No reranking step — plain top-k cosine similarity via sqlite-vec; would matter more at a
  much larger document count than this is designed for.
- No test suite (pytest etc.) — everything so far has been verified via live
  docker-compose/curl smoke tests, not automated tests.
- Portfolio site (`~/portfolio-site/projects/`) does not yet have an entry linking to this repo.
- Sysadmin track (in progress): systemd/bare-metal deploy path + backup script (PR A) and
  Zabbix monitoring integration (PR B, using a new `/metrics` Prometheus endpoint) — see
  [[project_local_rag_assistant]] memory for current PR status if resuming this.
