import io
import os
import urllib.error
import urllib.request

import boto3
from botocore.client import Config
from flask import Flask, Response, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET", "lab-secret-change-me"),
    SESSION_COOKIE_HTTPONLY=os.environ.get("SESSION_COOKIE_HTTPONLY", "0") == "1",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

S3_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")

S3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=os.environ.get("MINIO_ROOT_USER", "labadmin"),
    aws_secret_access_key=os.environ.get("MINIO_ROOT_PASSWORD", "labdev-only-change-me"),
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)
BUCKET = os.environ.get("BUCKET", "public")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PASS_THROUGH_HEADERS = (
    "Content-Type",
    "Content-Length",
    "ETag",
    "Last-Modified",
    "Accept-Ranges",
    "Content-Disposition",
)

USERS = {
    "alice": {"password": "alice-pass-123", "note": "Recovery code: 7721-RDRE-ALICE"},
    "bob": {"password": "bob-pass-123", "note": "Recovery code: 3340-KQJD-BOB"},
}

STYLE = """
<style>
 :root { color-scheme: dark; }
 * { box-sizing: border-box; }
 body {
  font-family: -apple-system, "Segoe UI", Roboto, Inter, sans-serif;
  background: #0b0e14;
  background-image:
   radial-gradient(640px 320px at 12% -8%, rgba(56,132,255,.16), transparent 60%),
   radial-gradient(520px 280px at 108% 6%, rgba(139,92,246,.13), transparent 60%);
  background-repeat: no-repeat;
  min-height: 100vh; margin: 0; color: #e6e9ef;
 }
 .card { max-width: 560px; margin: 48px auto; background: rgba(21,26,35,.92);
         border: 1px solid #232a38; border-radius: 18px;
         padding: 30px 34px; box-shadow: 0 18px 40px rgba(0,0,0,.45); }
 h1 { margin: 0 0 8px; font-size: 1.4rem; letter-spacing: .2px;
      background: linear-gradient(90deg, #4d9fff, #a78bfa);
      -webkit-background-clip: text; background-clip: text; color: transparent; }
 code { background: #1b2230; padding: 2px 7px; border-radius: 6px;
        color: #9ecbff; font-size: .9em; }
 img.avatar { width: 128px; height: 128px; object-fit: cover; border-radius: 50%;
              border: 3px solid #263042; box-shadow: 0 0 0 4px rgba(77,159,255,.18);
              background: #10151d; }
 input, button { font-size: 1rem; padding: 10px 14px; margin: 8px 0;
                 border-radius: 10px; display: block; width: 100%; }
 input { background: #10151d; border: 1px solid #2a3446; color: #e6e9ef; }
 input:focus { outline: none; border-color: #4d9fff;
               box-shadow: 0 0 0 3px rgba(77,159,255,.18); }
 button { background: linear-gradient(90deg, #1877f2, #6d5df6); color: #fff;
          border: 0; cursor: pointer; font-weight: 600;
          transition: filter .15s ease, transform .05s ease; }
 button:hover { filter: brightness(1.12); }
 button:active { transform: scale(.99); }
 .err { color: #ff7b72; font-weight: 600; }
 .ok { color: #4ade80; font-weight: 600; }
 .muted { color: #8a93a6; font-size: .9rem; }
 a { color: #6ea8ff; }
 hr { border: 0; border-top: 1px solid #232a38; margin: 18px 0; }
</style>
"""

LOGIN_PAGE = STYLE + """
<div class="card">
 <h1>◈ TargetSocial</h1>
 <p class="muted" style="margin-top:0">A tiny demo social network: users upload avatar images.</p>
 {% if error %}<p class="err">{{ error }}</p>{% endif %}
 <form method="post" action="/login">
  <input name="username" placeholder="username" value="alice" required>
  <input name="password" type="password" placeholder="password" value="alice-pass-123" required>
  <button>Log in</button>
 </form>
 <p class="muted">Demo users: <code>alice / alice-pass-123</code>,
 <code>bob / bob-pass-123</code></p>
</div>
"""

PROFILE_PAGE = STYLE + """
<div class="card">
 <h1>{{ username }}</h1>
 <img class="avatar" src="/uploads/{{ avatar }}?v={{ nonce }}" alt="avatar of {{ username }}">
 <p>{{ username }}'s profile page on TargetSocial.</p>
 {% if is_me %}
  <p class="ok">You are logged in. Private note (only you should see this):</p>
  <p><code>{{ note }}</code></p>
  <p><a href="/upload">Upload a new avatar</a> &middot;
     <a href="/u/{{ username }}">Public view</a></p>
  <form method="post" action="/logout"><button>Log out</button></form>
  <p class="muted">Your avatar is served at
     <code>/uploads/{{ avatar }}</code> from this same origin.</p>
 {% else %}
  <p class="muted">You are viewing {{ username }}'s public profile.</p>
  <p><a href="/login">Log in</a></p>
 {% endif %}
</div>
"""

UPLOAD_PAGE = STYLE + """
<div class="card">
 <h1>Upload avatar</h1>
 {% if error %}<p class="err">Rejected: {{ error }}</p>{% endif %}
 {% if notice %}<p class="ok">{{ notice }}</p>{% endif %}
 <form method="post" action="/upload" enctype="multipart/form-data">
  <input type="file" name="file" accept=".png" required>
  <button>Upload</button>
 </form>
 <p class="muted">Allowed: <code>.png</code> files only. Every upload is forced to
 <code>Content-Type: image/png</code> at upload time.</p>
 <p><a href="/profile">Back to profile</a></p>
</div>
"""


def avatar_key(username: str) -> str:
    return f"avatar-{username}.png"


@app.route("/")
def index():
    if "user" in session:
        return redirect("/profile")
    return render_template_string(LOGIN_PAGE, error=None)


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    user = USERS.get(username)
    if not user or user["password"] != password:
        return render_template_string(
            LOGIN_PAGE, error="Wrong username or password."
        )
    session["user"] = username
    return redirect("/profile")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect("/")
    username = session["user"]
    return render_template_string(
        PROFILE_PAGE,
        username=username,
        avatar=avatar_key(username),
        nonce=os.urandom(4).hex(),
        note=USERS[username]["note"],
        is_me=True,
    )


@app.route("/u/<username>")
def public_profile(username):
    if username not in USERS:
        return render_template_string(LOGIN_PAGE, error="No such user."), 404
    return render_template_string(
        PROFILE_PAGE,
        username=username,
        avatar=avatar_key(username),
        nonce=os.urandom(4).hex(),
        note="",
        is_me=False,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user" not in session:
        return redirect("/")
    if request.method == "GET":
        return render_template_string(UPLOAD_PAGE, error=None, notice=None)

    file = request.files.get("file")
    if file is None or file.filename == "":
        return render_template_string(UPLOAD_PAGE, error="no file selected", notice=None)

    if not file.filename.lower().endswith(".png"):
        return render_template_string(
            UPLOAD_PAGE, error="only .png extensions allowed", notice=None
        )

    head = file.stream.read(8)
    file.stream.seek(0)
    if head != PNG_MAGIC:
        return render_template_string(
            UPLOAD_PAGE, error="magic bytes do not look like PNG", notice=None
        )

    data = file.read()
    S3.upload_fileobj(
        io.BytesIO(data),
        BUCKET,
        avatar_key(session["user"]),
        ExtraArgs={"ContentType": "image/png"},
    )
    return render_template_string(
        UPLOAD_PAGE,
        error=None,
        notice=f"Uploaded {file.filename} as avatar-{session['user']}.png (forced to image/png).",
    )


@app.route("/uploads/<path:key>")
def uploads(key):
    """Same-origin serving of bucket objects: proxies the request (including
    its query string, e.g. response-content-type) to the MinIO "public"
    bucket. In the Docker setup nginx handles this path before Flask; this
    route exists so the native, no-Docker mode gets the identical layout of
    the write-up: files rendered on the site's own origin."""
    target = f"{S3_ENDPOINT}/public/{key}"
    if request.query_string:
        target += "?" + request.query_string.decode()
    req = urllib.request.Request(target, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            status, headers, body = r.status, dict(r.getheaders()), r.read()
    except urllib.error.HTTPError as e:
        status, headers, body = e.code, dict(e.headers), e.read()
    resp = Response(body, status=status)
    for header in PASS_THROUGH_HEADERS:
        if header in headers:
            resp.headers[header] = headers[header]
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
