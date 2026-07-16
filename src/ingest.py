import io

from pypdf import PdfReader

from . import llm, rag


def extract_text(filename: str, content: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode("utf-8", errors="ignore")


async def ingest_file(filename: str, content: bytes) -> int:
    text = extract_text(filename, content)
    chunks = rag.chunk_text(text)
    for i, chunk in enumerate(chunks):
        embedding = await llm.embed(chunk)
        rag.add_chunk(filename, i, chunk, embedding)
    return len(chunks)
