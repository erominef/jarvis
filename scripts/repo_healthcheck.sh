#!/usr/bin/env bash
set -euo pipefail

required=(
  "README.md"
  "SECURITY.md"
  "LICENSE"
  "templates/docker-compose.example.yml"
  "templates/env.example"
  "diagrams/architecture.mmd"
)

for f in "${required[@]}"; do
  if [ ! -f "$f" ]; then
    echo "Missing required file: $f"
    exit 1
  fi
done

echo "✅ Required files present."
