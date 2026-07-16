import os
from pathlib import PurePosixPath

from fastapi import Header, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

API_KEY = os.environ.get("API_KEY")

limiter = Limiter(key_func=get_remote_address)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
MAGIC_BYTES = {".pdf": b"%PDF"}


async def verify_api_key(x_api_key: str = Header(default="")) -> None:
    if not API_KEY:
        # Fail closed, not open — a misconfigured deployment should refuse
        # requests rather than silently run unauthenticated.
        raise HTTPException(500, "Server misconfigured: API_KEY is not set")
    if x_api_key != API_KEY:
        raise HTTPException(401, "Invalid or missing API key")


def safe_filename(filename: str) -> str:
    """Strip any path components — filename is used as a display label and DB
    key, never as a filesystem path, but a client could still send
    "../../etc/passwd" and we don't want that surfacing in the UI verbatim."""
    return PurePosixPath(filename).name


def validate_upload(filename: str, content: bytes) -> None:
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext or '(none)'}")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit")
    magic = MAGIC_BYTES.get(ext)
    if magic and not content.startswith(magic):
        raise HTTPException(400, "File content doesn't match its extension")
