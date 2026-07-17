import os
import re
import xml.etree.ElementTree as ET

import httpx

KIWIX_HOST = os.environ.get("KIWIX_HOST", "http://localhost:8080")
ATOM_NS = "{http://www.w3.org/2005/Atom}"

_book_names_cache: list[str] | None = None

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "what", "who", "whom", "which", "when", "where", "why", "how",
    "do", "does", "did", "can", "could", "should", "would", "will",
    "of", "in", "on", "at", "to", "for", "with", "about", "as", "by",
    "and", "or", "but", "if", "than", "that", "this", "these", "those",
    "it", "its", "i", "you", "he", "she", "they", "we", "me", "him",
    "her", "them", "us", "my", "your", "his", "their", "our",
}  # fmt: skip


def _keywords(query: str) -> str:
    """Kiwix's full-text search is keyword-based (Xapian), not semantic — a
    full natural-language question, with stopwords and a trailing "?", often
    matches nothing even when the content clearly covers it (verified: the
    same query minus stopwords went from 0 results to 40 against the same
    ZIM). Stripping stopwords/punctuation before searching consistently
    finds what the raw question misses."""
    words = re.findall(r"[A-Za-z0-9']+", query.lower())
    keywords = [w for w in words if w not in _STOPWORDS]
    return " ".join(keywords) or query


async def _discover_book_names(client: httpx.AsyncClient) -> list[str]:
    """kiwix-serve's /search endpoint wants the full content id (e.g.
    "wikipedia_en_ray-charles_mini_2026-05"), not the short book name — the
    catalog is the only place that id is exposed, so it's looked up once and
    cached rather than requiring the operator to configure it by hand."""
    global _book_names_cache
    if _book_names_cache is not None:
        return _book_names_cache
    resp = await client.get(f"{KIWIX_HOST}/catalog/v2/entries")
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    names = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        for link in entry.findall(f"{ATOM_NS}link"):
            href = link.get("href", "")
            if href.startswith("/content/"):
                names.append(href.removeprefix("/content/"))
                break
    _book_names_cache = names
    return names


async def search(query: str, limit: int = 3) -> list[dict]:
    """Full-text search across every ZIM loaded into kiwix-serve. Returns []
    on any failure (unreachable, no books loaded, malformed response) —
    Wikipedia context is a nice-to-have for the chat endpoint, not a hard
    dependency it should fail on."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            book_names = await _discover_book_names(client)
            if not book_names:
                return []
            pattern = _keywords(query)
            params = [("pattern", pattern), ("format", "xml"), ("pageLength", str(limit))]
            params.extend(("books.name", name) for name in book_names)
            resp = await client.get(f"{KIWIX_HOST}/search", params=params)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
    except (httpx.HTTPError, ET.ParseError):
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    results = []
    for item in channel.findall("item")[:limit]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        description = item.findtext("description") or ""
        snippet = re.sub(r"</?b>", "", description)
        results.append({"title": title, "link": link, "snippet": snippet})
    return results
