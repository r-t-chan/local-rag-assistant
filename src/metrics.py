from prometheus_client import Counter, Gauge, generate_latest

HTTP_REQUESTS = Counter(
    "rag_http_requests_total", "Total HTTP requests", ["endpoint", "status"]
)
DOCUMENTS_INGESTED = Counter("rag_documents_ingested_total", "Total documents ingested")
CHAT_REQUESTS = Counter("rag_chat_requests_total", "Total chat requests")
WIKIPEDIA_QUERIES = Counter("rag_wikipedia_queries_total", "Total Wikipedia searches performed")
WIKIPEDIA_HITS = Counter(
    "rag_wikipedia_hits_total", "Wikipedia searches that returned at least one result"
)
WIKIPEDIA_ERRORS = Counter(
    "rag_wikipedia_errors_total",
    "Wikipedia searches that failed outright (unreachable/malformed), distinct from"
    " zero-result searches — lets hit-rate be computed only over successful attempts",
)
OLLAMA_UP = Gauge(
    "rag_ollama_up", "Whether Ollama was reachable at the last /metrics scrape (1=up, 0=down)"
)
KIWIX_UP = Gauge(
    "rag_kiwix_up", "Whether kiwix-serve was reachable at the last /metrics scrape (1=up, 0=down)"
)


def render() -> bytes:
    return generate_latest()
