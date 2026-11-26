# Content-Type Override Lab (MinIO)

A local, deliberately vulnerable lab that reproduces the scenario from the
Voorivex write-up
["Content-Type Override to Stored XSS on Public Objects"](https://blog.voorivex.team/content-type-override-to-stored-xss-on-public-objects),
using **MinIO only** (no AWS / S3 involved).

It demonstrates the core idea of that post:

1. **Upload time** - the "hardened uploader" story: a clean
   `Content-Type: image/png` forced onto every image upload. All defenses
   cluster around the moment the file comes in.
2. **Serve time** - the upload handler is not involved anymore. The object
   lives in a **public** (anonymous-download) bucket, and MinIO honors
   `?response-content-type=text/html` on anonymous GETs with no auth check.
   A flat overwrite replaces whatever the app forced at upload time.
3. **Result** - attacker-uploaded bytes that pass every upload check are
   delivered as `text/html`: stored XSS on the origin serving the bucket.

## Layout

```
docker-compose.yml          MinIO (API :9000, console :9001, bound to 127.0.0.1) + setup job
minio/init.sh               creates bucket 'public', sets anonymous download policy,
                            uploads objects with forced Content-Type
payloads/avatar-payload.png 1x1 valid PNG + appended HTML/script page ("dressed up as
                            a valid PNG"; regenerate with scripts/make-payload.py)
payloads/secret-notes.txt   innocent text object, to show text/plain can be flipped too
scripts/run-lab.sh          start lab + run all stages in order
scripts/01-baseline-get.sh  stage 1: baseline GET -> Content-Type: image/png
scripts/02-content-type-override.sh stage 2: one query param -> text/html
scripts/03-verify-stored-xss.sh     stage 3: confirm payload served as HTML
```

## Quickstart

Requires Docker with `docker compose` and `bash`.

```bash
./scripts/run-lab.sh
```

Then open in a browser:

- Baseline (safe-looking), forced `image/png`:
  `http://127.0.0.1:9000/public/avatar-payload.png`
- The attack, one query param:
  `http://127.0.0.1:9000/public/avatar-payload.png?response-content-type=text/html`

Expected results:

| Request | `Content-Type` response | Meaning |
|---|---|---|
| `GET /public/avatar-payload.png` | `image/png` | upload-time hardening "works" |
| `GET /public/avatar-payload.png?response-content-type=text/html` | `text/html` | serve-time override wins, XSS |
| `GET /public/secret-notes.txt?response-content-type=text/html` | `text/html` | works on any object type |

You can inspect the objects manually with `mc`:

```bash
mc alias set lab http://127.0.0.1:9000 labadmin labdev-only-change-me
mc ls lab/public
```

## Why it works (short version, from the write-up)

- MinIO supports a whitelist of response-header override params on GET:
  `response-content-type`, `response-cache-control`, `response-content-disposition`,
  `response-content-encoding`, `response-content-language`, `response-expires`
  (see `cmd/object-handlers.go` in MinIO's source).
- `setHeadGetRespHeaders` applies them with a **flat assignment** — no
  validation, no sanitizing, and **no auth check**.
- In `GetObjectHandler`, MinIO first sets the object's stored headers
  (`setObjectHeaders` -> the forced `image/png`) and only **then** applies
  your query-param overrides. Last writer wins.
- The prerequisite is the same as in the write-up: the object must be
  **publicly readable anonymously**. Here that is done by
  `mc anonymous set download`, mimicking how many apps serve avatars/uploads.

## Mapping to the write-up's hunter's checklist

- Stage 1 = "append `?response-content-type=text/html` and watch what comes
  back". Here the target is MinIO, so the response is `text/html` and you are
  basically done.
- The S3 variant (the `InvalidRequest` error for anonymous overrides, then
  presigning the same public object with your own AWS account) is intentionally
  **out of scope** because this lab is MinIO-only.
- The origin caveat still applies: the XSS is only meaningful on an origin
  that matters. On a real target, files served from the target's own subdomain
  (`cdn.target.com`) or a path behind its reverse proxy (`target.com/uploads/`)
  give real same-origin XSS; files served from an untrusted storage domain lose
  most of the impact.

## Why this matters even though the lab "only" hits 127.0.0.1

In this lab the bucket is reachable directly by URL, so any page served from
it renders in the `http://127.0.0.1:9000` origin. On a real target the MinIO
host would be `cdn.target.com` or `target.com/uploads/` behind a reverse
proxy, and the same one-query-param request runs attacker HTML/JS in the
**target's own origin** — with whatever cookies, DOM, and API access that
origin holds.

## Safety / scope

- Compose binds only `127.0.0.1`; the credentials are disposable lab values.
- Don't expose the MinIO ports beyond localhost.
- This lab exists to study and defend against the technique. Test only in this
  lab, or on systems you have explicit permission to test.
- Practice only against your own lab — never against buckets you do not own.

## Teardown

```bash
docker compose down -v
```
