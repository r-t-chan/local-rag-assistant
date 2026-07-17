from prometheus_client import Counter, Gauge, generate_latest

HTTP_REQUESTS = Counter(
    "rag_http_requests_total", "Total HTTP requests", ["endpoint", "status"]
)
DOCUMENTS_INGESTED = Counter("rag_documents_ingested_total", "Total documents ingested")
CHAT_REQUESTS = Counter("rag_chat_requests_total", "Total chat requests")
OLLAMA_UP = Gauge(
    "rag_ollama_up", "Whether Ollama was reachable at the last /metrics scrape (1=up, 0=down)"
)


def render() -> bytes:
    return generate_latest()
