import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import ingest, llm, rag
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


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


SYSTEM_PROMPT = (
    "You are a private, local document assistant. Answer the user's question "
    "using ONLY the provided context below. If the context doesn't contain the "
    "answer, say you don't know — do not make anything up. Cite sources by "
    "filename when you use them.\n\nContext:\n{context}"
)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    """Unauthenticated liveness/readiness probe for the container orchestrator —
    checks that Ollama is actually reachable, not just that this process is up."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{llm.OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning("health check failed: ollama unreachable")
        raise HTTPException(503, "ollama unreachable")
    return {"status": "ok"}


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
    return {"filename": filename, "chunks": n_chunks}


@app.post("/api/chat", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def chat(request: Request, req: ChatRequest):
    query_embedding = await llm.embed(req.message)
    results = rag.search(query_embedding, k=4)
    context = "\n\n".join(
        f"[{r['source']} chunk {r['chunk_index']}]\n{r['text']}" for r in results
    )
    sources_used = sorted({r["source"] for r in results})
    logger.info(
        "chat request",
        extra={"retrieved_count": len(results), "source_count": len(sources_used)},
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(context=context or "(no documents ingested yet)"),
        },
        *req.history,
        {"role": "user", "content": req.message},
    ]

    async def event_stream():
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_used})}\n\n"
        async for token in llm.stream_chat(messages):
            yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
