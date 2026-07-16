import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ingest, llm, rag

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    rag.init_db()
    yield


app = FastAPI(title="Local RAG Assistant", lifespan=lifespan)
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


@app.get("/api/sources")
def sources():
    return {"sources": rag.list_sources()}


@app.delete("/api/sources/{source}")
def delete_source(source: str):
    rag.delete_source(source)
    return {"deleted": source}


@app.post("/api/ingest")
async def ingest_endpoint(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    n_chunks = await ingest.ingest_file(file.filename, content)
    return {"filename": file.filename, "chunks": n_chunks}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    query_embedding = await llm.embed(req.message)
    results = rag.search(query_embedding, k=4)
    context = "\n\n".join(
        f"[{r['source']} chunk {r['chunk_index']}]\n{r['text']}" for r in results
    )
    sources_used = sorted({r["source"] for r in results})

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
