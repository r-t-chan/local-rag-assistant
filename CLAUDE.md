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

Sysadmin track complete (2026-07-16, merged via PR #9 + PR #10) — see below.

Wikipedia knowledge base added (2026-07-17, branch `feature/kiwix-wikipedia`): a Kiwix
(`ghcr.io/kiwix/kiwix-serve`) service serves an offline Wikipedia ZIM dump, queried in
parallel with the document store on every chat request (`src/kiwix.py`) and merged into
the prompt with source labels.

A Fable-5-powered critic review (via the `critic` subagent) of this same branch caught
three more real, blocking-severity bugs beyond the two found during initial testing —
worth internalizing as a pattern: a second review pass after "it works" is not redundant.
1. Kiwix's full-text search is keyword-based (Xapian), not semantic — passing a raw
   question (with stopwords, trailing "?") returned 0 results even when the ZIM clearly
   covered the topic; confirmed directly (0 → 40 results for the same content after
   stripping stopwords). Fixed with `src/kiwix.py::_keywords`, using `\w+` (not
   `[A-Za-z0-9']+`, caught by the critic pass) so non-ASCII queries survive.
2. The initially-obvious `command: ["*.zim"]` glob approach crash-loops kiwix-serve
   forever when zero ZIM files are present. Fixed by switching to
   `--library --monitorLibrary` mode against an XML manifest (`data/kiwix/library.xml`).
3. **(critic pass)** The book-name cache in `src/kiwix.py` cached an *empty* result the
   same as a real one, meaning registering a ZIM into a running app never actually got
   picked up until the app itself restarted — directly contradicting the "no restart
   needed" claim in the PR. Fixed: empty results are never cached.
4. **(critic pass)** A missing `data/kiwix/library.xml` gets silently replaced by Docker
   with an empty *directory* on `docker compose up`, which then fails kiwix-serve's
   startup entirely — meaning any deployment pulling this feature without re-running
   setup would have `app` hang forever behind `kiwix`'s failed healthcheck. Fixed with a
   one-shot `kiwix-init` service (runs as root — `user: "0:0"` — since the bind-mounted
   host directory's ownership can't be relied on to match a fixed non-root image uid;
   confirmed by hitting that exact permission error with the default user) that
   guarantees the file exists before `kiwix` starts.
5. **(critic pass)** `app`'s `depends_on: kiwix` was `condition: service_healthy`, which
   contradicts the entire "soft dependency" design elsewhere in the code (`kiwix.search`
   returns `[]` on any failure, never raises) — a Kiwix outage would have blocked the
   whole app from starting instead of just disabling Wikipedia context. Changed to
   `condition: service_started`.

Also from the critic pass, non-blocking but real: `kiwix.py` now logs a warning on search
failure (it previously swallowed every error silently), `/metrics`'s Ollama+Kiwix probes
now run concurrently via `asyncio.gather` instead of sequentially (was up to 6s added
latency), a new `rag_wikipedia_errors_total` counter distinguishes "Kiwix unreachable"
from "reachable but no results," and `download_wikipedia_zim.sh` now verifies a sha256
checksum, downloads to a resumable `.part` file, resolves `ZIM_DIR`/`LIBRARY_DIR` to
absolute paths (a relative-vs-absolute-input bug could otherwise double up `$(pwd)/`), and
registers ZIMs via a write-to-temp-then-atomic-rename instead of an in-place edit (closes
a race against kiwix-serve's `--monitorLibrary`, which watches the file read-only).

All of the above verified live post-fix: full stack starts healthy with zero ZIM files
(proving the kiwix-init fix), a ZIM registered against a *running* app was picked up by
the very next chat request with no restart (proving the cache fix), the download script's
checksum step was verified to both pass on a good download and correctly reject +
clean up a deliberately corrupted one, and `/metrics` shows accurate
queries/hits/errors counts after real ingest/chat/search activity.

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
- The Zabbix template has never been imported into a real Zabbix instance and verified end
  to end — it's been validated for YAML correctness and consistency with the existing
  keycloak template's conventions, but not exercised against live Zabbix.
- The production Wikipedia ZIM (`wikipedia_en_all_mini_2026-06.zim`, ~12GB) has never
  actually been downloaded/tested in this environment — all Kiwix testing used the ~700KB
  `wikipedia_en_ray-charles_mini` fixture Kiwix itself uses for testing, to keep this
  session's bandwidth/time reasonable. The mechanism is verified; the specific production
  file is not.
