#!/usr/bin/env bash
# Stage 1: baseline GET. This is what a defender sees when they test the
# uploader: the forced Content-Type comes back and everything looks safe.
set -euo pipefail

BASE="${MINIO_URL:-http://127.0.0.1:9000}"
KEY="${1:-public/avatar-payload.png}"

echo "GET ${BASE}/${KEY}"
echo "--- response ---"
curl -sS -D - -o /dev/null "${BASE}/${KEY}"
