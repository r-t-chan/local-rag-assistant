import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import ingest, kiwix, llm, metrics, rag
from .logging_config import configure_logging
from .security import limiter, safe_filename, validate_upload, verify_api_key

configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("local_rag_assistant")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    rag.init_db()
    logger.info("startup complete")
    yield


app = FastAPI(title="Local RAG Assistant", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def track_request_metrics(request: Request, call_next):
    response = await call_next(request)
    # Prefer the matched route template (e.g. "/api/sources/{source}") over the
    # raw path, so per-request path segments (filenames) don't blow up label
    # cardinality in Prometheus.
    route = request.scope.get("route")
    endpoint = route.path if route is not None else request.url.path
    metrics.HTTP_REQUESTS.labels(endpoint=endpoint, status=response.status_code).inc()
    return response


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


SYSTEM_PROMPT = (
    "You are a private, local document assistant. Answer the user's question "
    'using the context below. Content under "Your documents" is the user\'s '
    "own uploaded material — treat it as authoritative. Content under "
    '"Wikipedia (general knowledge)" comes from a local, offline Wikipedia '
    "copy — use it to fill gaps only when the documents don't cover the "
    "question, and prefer document content when both are relevant. If "
    "neither source covers the question, say you don't know — do not make "
    "anything up. Cite sources by name when you use them.\n\n"
    "Your documents:\n{doc_context}\n\n"
    "Wikipedia (general knowledge):\n{wiki_context}"
)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    """Unauthenticated liveness/readiness probe for the container orchestrator —
    checks that Ollama is actually reachable, not just that this process is up.
    Kiwix is reported but doesn't fail the check: it's a nice-to-have knowledge
    source, and the app degrades gracefully (document-only answers) without it."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{llm.OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning("health check failed: ollama unreachable")
        raise HTTPException(503, "ollama unreachable")

    kiwix_reachable = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{kiwix.KIWIX_HOST}/")
            kiwix_reachable = resp.status_code == 200
    except httpx.HTTPError:
        pass

    return {"status": "ok", "kiwix": "reachable" if kiwix_reachable else "unreachable"}


@app.get("/metrics", dependencies=[Depends(verify_api_key)])
async def metrics_endpoint():
    """API-key protected, unlike /health — request counts and ingest/chat
    activity are more sensitive than a bare up/down check."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{llm.OLLAMA_HOST}/api/tags")
            metrics.OLLAMA_UP.set(1 if resp.status_code == 200 else 0)
    except httpx.HTTPError:
        metrics.OLLAMA_UP.set(0)
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{kiwix.KIWIX_HOST}/")
            metrics.KIWIX_UP.set(1 if resp.status_code == 200 else 0)
    except httpx.HTTPError:
        metrics.KIWIX_UP.set(0)
    return Response(metrics.render(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/sources", dependencies=[Depends(verify_api_key)])
def sources():
    return {"sources": rag.list_sources()}


@app.delete("/api/sources/{source}", dependencies=[Depends(verify_api_key)])
def delete_source(source: str):
    rag.delete_source(source)
    return {"deleted": source}


@app.post("/api/ingest", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def ingest_endpoint(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    filename = safe_filename(file.filename)
    validate_upload(filename, content)
    n_chunks = await ingest.ingest_file(filename, content)
    logger.info("document ingested", extra={"source": filename, "chunk_count": n_chunks})
    metrics.DOCUMENTS_INGESTED.inc()
    return {"filename": filename, "chunks": n_chunks}


@app.post("/api/chat", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def chat(request: Request, req: ChatRequest):
    query_embedding = await llm.embed(req.message)
    # Documents and Wikipedia are queried in parallel on every request — always
    # blending both is simpler and more predictable than a relevance-threshold
    # heuristic deciding when to fall back to Wikipedia (see README).
    doc_results, wiki_results = await asyncio.gather(
        asyncio.to_thread(rag.search, query_embedding, 4),
        kiwix.search(req.message, limit=3),
    )

    doc_context = "\n\n".join(
        f"[{r['source']} chunk {r['chunk_index']}]\n{r['text']}" for r in doc_results
    )
    doc_sources = sorted({r["source"] for r in doc_results})

    wiki_context = "\n\n".join(f"[{w['title']}]\n{w['snippet']}" for w in wiki_results)
    wiki_sources = sorted({w["title"] for w in wiki_results})

    metrics.CHAT_REQUESTS.inc()
    metrics.WIKIPEDIA_QUERIES.inc()
    if wiki_results:
        metrics.WIKIPEDIA_HITS.inc()
    logger.info(
        "chat request",
        extra={
            "retrieved_count": len(doc_results),
            "source_count": len(doc_sources),
            "wikipedia_hit_count": len(wiki_results),
        },
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                doc_context=doc_context or "(no documents ingested yet)",
                wiki_context=wiki_context or "(no results)",
            ),
        },
        *req.history,
        {"role": "user", "content": req.message},
    ]

    async def event_stream():
        sources_event = {"type": "sources", "documents": doc_sources, "wikipedia": wiki_sources}
        yield f"data: {json.dumps(sources_event)}\n\n"
        async for token in llm.stream_chat(messages):
            yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
