#!/bin/sh
# Reproduces the "app" side of the story:
#   1. create a bucket and make it publicly readable (anonymous download)
#   2. upload objects with a *forced* Content-Type, like a hardened uploader would
#      (image/png for the avatar, text/plain for the notes file)
# The stored XSS then comes purely from the serve-time override.
set -eu

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-labadmin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-labdev-only-change-me}"
BUCKET="${BUCKET:-public}"
ALIAS="local"

echo "[*] Waiting for MinIO at ${MINIO_ENDPOINT} ..."
i=0
until mc alias set "${ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "[!] MinIO did not become ready in time"
    exit 1
  fi
  sleep 2
done
echo "[*] Connected to MinIO."

echo "[*] Creating bucket '${BUCKET}' ..."
mc mb --ignore-existing "${ALIAS}/${BUCKET}"

# This is the single line that makes everything from the writeup possible:
# anonymous GET requests are allowed to read the bucket.
echo "[*] Setting anonymous download policy on bucket (public bucket) ..."
mc anonymous set download "${ALIAS}/${BUCKET}"

echo "[*] Uploading 'avatar' with forced Content-Type: image/png ..."
mc cp --attr "Content-Type=image/png" \
  /app/payloads/avatar-payload.png \
  "${ALIAS}/${BUCKET}/avatar-payload.png"

echo "[*] Uploading 'notes' with forced Content-Type: text/plain ..."
mc cp --attr "Content-Type=text/plain" \
  /app/payloads/secret-notes.txt \
  "${ALIAS}/${BUCKET}/secret-notes.txt"

echo "[*] Bucket contents:"
mc ls "${ALIAS}/${BUCKET}/"

echo "LAB-READY"
