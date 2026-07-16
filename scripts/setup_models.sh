#!/usr/bin/env bash
# Pulls the chat + embedding models into the running ollama container.
# Run this once after `docker compose up -d`.
set -euo pipefail

CHAT_MODEL="${OLLAMA_CHAT_MODEL:-llama3.1:8b-instruct-q4_K_M}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"

echo "Pulling chat model: $CHAT_MODEL"
docker compose exec ollama ollama pull "$CHAT_MODEL"

echo "Pulling embedding model: $EMBED_MODEL"
docker compose exec ollama ollama pull "$EMBED_MODEL"

echo "Done. Models ready."
