#!/bin/bash
# benchmark-models.sh — Test token generation speed for each model on a given Ollama host.
#
# Usage:
#   ./scripts/benchmark-models.sh http://localhost:11434
#   ./scripts/benchmark-models.sh http://<OLLAMA_HOST>:11434
#
# Output: model name, tokens generated, eval_duration (ns), tok/s

OLLAMA_URL="${1:-http://localhost:11434}"
PROMPT="Explain in detail how CPUs execute machine code instructions, covering fetch-decode-execute cycle, pipelining, out-of-order execution, and branch prediction. Be thorough."

MODELS=(
    "qwen3:0.6b"
    "qwen3:4b"
    "qwen2.5:7b"
    "qwen3:14b"
    "deepseek-r1:7b"
)

echo "Ollama: $OLLAMA_URL"
echo "Prompt: $(echo "$PROMPT" | cut -c1-60)..."
echo ""
printf "%-20s %8s %10s %8s\n" "Model" "Tokens" "Dur(ms)" "tok/s"
printf "%-20s %8s %10s %8s\n" "-----" "------" "-------" "-----"

for model in "${MODELS[@]}"; do
    response=$(curl -s "$OLLAMA_URL/api/generate" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"prompt\": \"$PROMPT\",
            \"stream\": false,
            \"options\": {\"num_predict\": 200}
        }" \
        --max-time 120 2>/dev/null)

    if [ $? -ne 0 ] || [ -z "$response" ]; then
        printf "%-20s %s\n" "$model" "ERROR (timeout or connection failed)"
        continue
    fi

    eval_count=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('eval_count', 0))" 2>/dev/null)
    eval_duration=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('eval_duration', 0))" 2>/dev/null)

    if [ -z "$eval_count" ] || [ "$eval_count" -eq 0 ]; then
        printf "%-20s %s\n" "$model" "no tokens generated"
        continue
    fi

    dur_ms=$(echo "scale=0; $eval_duration / 1000000" | bc)
    toks=$(echo "scale=2; $eval_count / ($eval_duration / 1000000000)" | bc)

    printf "%-20s %8s %10s %8s\n" "$model" "$eval_count" "${dur_ms}ms" "${toks}"
done
