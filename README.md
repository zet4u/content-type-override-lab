# Content-Type Override Lab (MinIO + a "real target" site)

A local, deliberately vulnerable lab that reproduces the scenario from the
Voorivex write-up
["Content-Type Override to Stored XSS on Public Objects"](https://blog.voorivex.team/content-type-override-to-stored-xss-on-public-objects),
using **MinIO only** (no AWS / S3 involved).

It contains two ways to study the same bug:

- **Part A — direct MinIO**: the core behavior of the write-up, one query
  param flips a public object from `image/png` to `text/html`.
- **Part B — a real target site**: `TargetSocial`, a small social network
  behind an nginx reverse proxy at `http://target.com:8080`, avatars served
  same-origin from `target.com/uploads/` (the write-up's highest-impact
  layout). You reproduce the whole attack chain: hardened upload → crafted
  link → stored XSS reading cookies and private data on the site's own origin.

## Architecture

```
Browser
  |
  |  http://target.com:8080            (/etc/hosts -> 127.0.0.1)
  v
nginx  ── /uploads/*  ──>  MinIO :9000 (public bucket 'public', anonymous download)
  |                         ^ query string (?response-content-type=...) passed through
  └── /  ──────────────>  TargetSocial (Flask :5000)
                             . login, session cookie (not HttpOnly in this lab)
                             . upload: .png whitelist + PNG magic bytes + forced
                               Content-Type: image/png  (the "hardened uploader")
                             . profile shows a private note per user
```

| Request | `Content-Type` served | Meaning |
|---|---|---|
| `GET /uploads/avatar-bob.png` | `image/png` | upload-time hardening "works" |
| `GET /uploads/avatar-bob.png?response-content-type=text/html` | `text/html` | serve-time override wins: stored XSS on `target.com` origin |

## Layout

```
docker-compose.yml          minio (127.0.0.1:9000/:9001) + web + nginx (127.0.0.1:8080) + setup job
minio/init.sh               creates bucket 'public', anonymous download policy,
                            uploads demo objects with forced Content-Type
nginx/default.conf          target.com vhost: /uploads/ -> MinIO, / -> site
web/app.py                  TargetSocial: login/upload/profile, upload hardening
payloads/avatar-payload.png valid 1x1 PNG + appended HTML/script (regenerate with
                            scripts/make-payload.py)
scripts/run-lab.sh          start everything + run Part A stages
scripts/01..03-*.sh         Part A: baseline, override, XSS verification
```

## Installation (Linux / macOS)

Prerequisites: [Docker Engine](https://docs.docker.com/get-docker/) with the
`docker compose` plugin (or Docker Desktop), `bash`, `curl`.

```bash
# 1. clone
git clone https://github.com/zet4u/content-type-override-lab.git
cd content-type-override-lab

# 2. point target.com at your machine (one line)
echo "127.0.0.1 target.com" | sudo tee -a /etc/hosts

# 3. build + start everything
./scripts/run-lab.sh
```

That is the whole setup. `run-lab.sh` builds the images, starts the stack,
waits for bucket initialization, and then runs the Part A stages for you.

## Installation (Windows)

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/),
Git, PowerShell as Administrator.

```powershell
git clone https://github.com/zet4u/content-type-override-lab.git
cd content-type-override-lab

# hosts file (elevated PowerShell)
Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 target.com"

docker compose up -d --build
```

Then follow Part B below manually; the Part A scripts are bash-only.

## Full status check

```bash
docker compose ps
curl -s -o /dev/null -w '%{http_code}\n' http://target.com:8080/
```

## Part A — direct MinIO (headless)

```bash
# baseline: the forced image/png comes back, all "checks passed"
curl -s -D - -o /dev/null http://127.0.0.1:9000/public/avatar-payload.png

# the attack: one query parameter decides the Content-Type
curl -s -D - -o /dev/null \
  'http://127.0.0.1:9000/public/avatar-payload.png?response-content-type=text/html'
```

Expected: first request `image/png`, second `text/html` — same object, same
bytes, anonymous. Interactive version: `./scripts/run-lab.sh`.

## Part B — attacking the real site

1. Open `http://target.com:8080` in your browser and log in as
   **alice / alice-pass-123** (leave this window logged in — this is the
   victim session).
2. In a second, private window, log in as **bob / bob-pass-123** and go to
   **Upload avatar**. Upload `payloads/avatar-payload.png`:
   - `.png` extension — passes the whitelist,
   - real PNG magic bytes in the first 8 bytes — passes the sniffing check,
   - stored with a forced `Content-Type: image/png` — passes the uploader's
     final test.
   Every defense the app has is satisfied.
3. Bob sends alice the crafted link (the entire attack is the query param):

   ```
   http://target.com:8080/uploads/avatar-bob.png?response-content-type=text/html
   ```

4. Alice opens the link while logged in. The bytes that were validated as a
   PNG are now rendered as **HTML on the `target.com` origin**:
   - an `alert` shows `document.domain` and `document.cookie`
     (this lab's session cookie is deliberately readable),
   - the script then does a same-origin `fetch('/profile')` and renders
     alice's private note on the page.

### Variants to try

- Flip any other object type too: `secret-notes.txt?response-content-type=text/html`.
- Other supported MinIO override params (see the write-up's whitelist):
  `response-content-disposition`, `response-cache-control`,
  `response-content-encoding`, `response-content-language`, `response-expires`.
- Replace the payload: edit `scripts/make-payload.py`, run
  `python3 scripts/make-payload.py`, re-upload as bob, re-open the link.

## Why the same-origin detail matters

In Part B the avatar is not on a detached storage domain — it comes back from
`target.com/uploads/...`. The query-param override therefore runs attacker
HTML/JS **inside the site's own origin**, which is exactly the write-up's
point: the impact is decided by where the file is served from, not by what
the uploader validated.

## Why it works (short version)

- MinIO honors a whitelist of response-header override params on GET
  (`response-content-type`, `response-content-disposition`, ...)
  in `cmd/object-handlers.go`.
- `setHeadGetRespHeaders` applies them with a flat assignment: no validation,
  no sanitizing, no auth check.
- `GetObjectHandler` sets the object's stored headers (`setObjectHeaders`
  -> the forced `image/png`) first, then applies your query-param overrides.
  Last writer wins.
- The prerequisite: the object is anonymously readable
  (`mc anonymous set download` here).

The S3 variant (`InvalidRequest` for anonymous overrides + presigning the
public object with your own AWS account) is intentionally out of scope here.

## Troubleshooting

- **`target.com` does not load** — check `getent hosts target.com` (Linux,
  expect `127.0.0.1`); on Windows check
  `C:\Windows\System32\drivers\etc\hosts` and restart the browser.
- **Port already in use** (`9000`/`9001`/`8080`) — stop the conflicting
  service or change the left side of the `ports:` mappings in
  `docker-compose.yml` (then update the scripts/URLs).
- **Setup job fails** — `docker compose logs setup`; usually the MinIO image
  is still pulling; rerun `./scripts/run-lab.sh`.
- **Start from a clean slate** — `docker compose down -v` removes MinIO data
  and all avatars.

## Restart / stop / reset

```bash
docker compose up -d --build   # start / rebuild after changes
docker compose stop            # stop, keep data
docker compose down -v         # stop and wipe everything
```

## Safety / scope

- All ports bind to `127.0.0.1` only. Do not expose them.
- Credentials (`labadmin / labdev-only-change-me`, site passwords) are
  disposable lab values.
- This lab exists to study and defend against the technique. Practice only
  against this lab, or against systems you have explicit permission to test.
