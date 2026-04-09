#!/bin/bash
# Pull the default LLM model into Ollama on HOLYGRAIL
# Usage: bash scripts/setup-ollama-model.sh [model]
#   Default model: llama3.1:8b

set -euo pipefail

MODEL="${1:-llama3.1:8b}"
HOLYGRAIL_SSH="john@holygrail"

echo "=== Ollama Model Setup ==="
echo "Model: $MODEL"
echo ""

# Check Ollama is running
if ! ssh "$HOLYGRAIL_SSH" "curl -sf http://localhost:11434/" >/dev/null 2>&1; then
    echo "ERROR: Ollama is not running on HOLYGRAIL"
    echo "Deploy first: cd ~/docker/ollama && docker compose up -d"
    exit 1
fi

# Pull the model
echo "Pulling $MODEL (this may take several minutes)..."
ssh "$HOLYGRAIL_SSH" "docker exec ollama ollama pull $MODEL"

# Verify
echo ""
echo "=== Installed Models ==="
ssh "$HOLYGRAIL_SSH" "docker exec ollama ollama list"

# Quick test
echo ""
echo "=== Quick Inference Test ==="
RESPONSE=$(ssh "$HOLYGRAIL_SSH" "curl -sf http://localhost:11434/api/generate -d '{\"model\":\"$MODEL\",\"prompt\":\"Say hello in one sentence.\",\"stream\":false}'" 2>/dev/null)
if echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['response'][:200])" 2>/dev/null; then
    echo ""
    echo "Model is working."
else
    echo "WARNING: Could not parse response. Check Ollama logs."
fi

# VRAM check
echo ""
echo "=== GPU Memory Usage ==="
ssh "$HOLYGRAIL_SSH" "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader"
