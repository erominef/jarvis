#!/usr/bin/env bash
set -euo pipefail

echo "Running basic secret scan…"
fail=0

# Patterns to look for
patterns=(
  "-----BEGIN .* PRIVATE KEY-----"
  "AKIA[0-9A-Z]{16}"            # AWS access key id style
  "xox[baprs]-"                 # Slack tokens
  "Bearer [A-Za-z0-9._-]{20,}"  # Bearer tokens
  "TELEGRAM_BOT_TOKEN=([0-9]+:)"# Telegram token prefix
)

# Files to scan (excluding .git)
files=$(git ls-files 2>/dev/null || find . -type f | sed 's|^\./||')

for p in "${patterns[@]}"; do
  if echo "$files" | xargs -r grep -nE "$p" 2>/dev/null | grep -vE "^\.git/" >/dev/null; then
    echo "⚠️  Possible secret match for pattern: $p"
    echo "$files" | xargs -r grep -nE "$p" 2>/dev/null | grep -vE "^\.git/" | head -n 20
    fail=1
  fi
done

# IPs (private ranges) – not always a secret, but flag for review
if echo "$files" | xargs -r grep -nE "\b(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)" 2>/dev/null | grep -vE "^\.git/" >/dev/null; then
  echo "ℹ️  Found private-network IPs (review if these are real):"
  echo "$files" | xargs -r grep -nE "\b(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)" 2>/dev/null | grep -vE "^\.git/" | head -n 20
fi

if [ "$fail" -eq 1 ]; then
  echo "❌ Secret scan found potential issues. Review before publishing."
  exit 1
fi

echo "✅ No obvious secrets detected."
