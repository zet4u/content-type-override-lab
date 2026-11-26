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
 body { margin: 0; background: #18191a; color: #e4e6eb;
        font-family: Helvetica, Arial, "Segoe UI", Roboto, sans-serif; }
 .topbar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center;
           gap: 14px; background: #242526; border-bottom: 1px solid #3a3b3c;
           padding: 8px 16px; height: 56px; box-shadow: 0 1px 2px rgba(0,0,0,.3); }
 .logo { font-size: 1.6rem; font-weight: 800; letter-spacing: -1px;
         color: #2d88ff; user-select: none; }
 .logo b { color: #a78bfa; }
 .search { flex: 0 1 260px; background: #3a3b3c; border-radius: 999px;
           padding: 8px 16px; color: #b0b3b8; font-size: .9rem; }
 .fill { flex: 1; }
 .mechip { display: flex; align-items: center; gap: 8px; background: #3a3b3c;
           border-radius: 999px; padding: 4px 12px 4px 4px; font-size: .9rem;
           font-weight: 600; }
 .initial { width: 28px; height: 28px; border-radius: 50%; color: #fff; font-size: .85rem;
            display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #2d88ff, #a78bfa); }
 .wrap { max-width: 640px; margin: 16px auto 48px; padding: 0 10px; }
 .card { background: #242526; border: 1px solid #3a3b3c; border-radius: 8px;
         padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.2); }
 h1 { font-size: 1.25rem; margin: 0; }
 h2 { font-size: 1rem; margin: 0 0 12px; color: #b0b3b8; font-weight: 500; }
 code { background: #3a3b3c; padding: 2px 6px; border-radius: 4px;
        color: #9bc1f9; font-size: .9em; }
 .cover { height: 150px; border-radius: 8px 8px 0 0;
          background: linear-gradient(120deg, #16243d, #231a42 55%, #101017);
          margin: -16px -16px 0; }
 .head { display: flex; align-items: flex-end; gap: 14px; margin: -60px 8px 0; }
 img.avatar { width: 128px; height: 128px; object-fit: cover; border-radius: 50%;
              border: 3px solid #242526; background: #3a3b3c; flex-shrink: 0; }
 .who { padding-bottom: 6px; }
 .who .muted { margin: 2px 0 0; }
 input, button { font-size: 15px; padding: 11px 14px; margin: 6px 0;
                 border-radius: 6px; display: block; width: 100%; }
 input { background: #3a3b3c; border: 1px solid transparent; color: #e4e6eb; }
 input:focus { outline: none; border-color: #2d88ff; }
 button { background: #2d88ff; color: #fff; border: 0; cursor: pointer;
          font-weight: 700; transition: background .15s ease; }
 button:hover { background: #1a6fe8; }
 .err { color: #f0284a; font-weight: 600; }
 .ok { color: #45bd62; font-weight: 600; }
 .muted { color: #b0b3b8; font-size: .95rem; }
 a { color: #4599ff; text-decoration: none; }
 a:hover { text-decoration: underline; }
 .div { border-top: 1px solid #3a3b3c; margin: 14px -16px; }
 .links { display: flex; gap: 16px; align-items: center; }
</style>
"""

TOPBAR = """
<div class="topbar">
 <span class="logo">target<b>social</b></span>
 <div class="search">Search TargetSocial</div>
 <div class="fill"></div>
 {% if username %}<span class="mechip"><span class="initial">{{ username[0]|upper }}</span>{{ username }}</span>{% endif %}
</div>
<div class="wrap">
"""

LOGIN_PAGE = STYLE + TOPBAR + """
<div class="card" style="max-width:400px;margin:64px auto">
 <h1>Log in to TargetSocial</h1>
 <p class="muted" style="margin-top:4px">A tiny demo social network: users upload avatar images.</p>
 {% if error %}<p class="err">{{ error }}</p>{% endif %}
 <form method="post" action="/login">
  <input name="username" placeholder="username" value="alice" required>
  <input name="password" type="password" placeholder="password" value="alice-pass-123" required>
  <button>Log in</button>
 </form>
 <div class="div"></div>
 <p class="muted">Demo users: <code>alice / alice-pass-123</code>,
 <code>bob / bob-pass-123</code></p>
</div>
"""

PROFILE_PAGE = STYLE + TOPBAR + """
<div class="card">
 <div class="cover"></div>
 <div class="head">
  <img class="avatar" src="/uploads/{{ avatar }}?v={{ nonce }}" alt="avatar of {{ username }}">
  <div class="who">
   <h1>{{ username }}</h1>
   <p class="muted">{{ username }}'s profile page on TargetSocial</p>
  </div>
 </div>
</div>
{% if is_me %}
<div class="card">
 <h2>You are logged in — private note (only you should see this)</h2>
 <p><code>{{ note }}</code></p>
</div>
<div class="card">
 <div class="links">
  <a href="/upload">Upload a new avatar</a>
  <a href="/u/{{ username }}">Public view</a>
 </div>
 <form method="post" action="/logout"><button>Log out</button></form>
 <p class="muted">Your avatar is served at
    <code>/uploads/{{ avatar }}</code> from this same origin.</p>
</div>
{% else %}
<div class="card">
 <p class="muted">You are viewing {{ username }}'s public profile.</p>
 <p><a href="/login">Log in</a></p>
</div>
{% endif %}
"""

UPLOAD_PAGE = STYLE + TOPBAR + """
<div class="card" style="max-width:480px;margin:24px auto">
 <h1>Upload avatar</h1>
 <p class="muted" style="margin-top:4px">Pick a new profile picture for your account.</p>
 {% if error %}<p class="err">Rejected: {{ error }}</p>{% endif %}
 {% if notice %}<p class="ok">{{ notice }}</p>{% endif %}
 <form method="post" action="/upload" enctype="multipart/form-data">
  <input type="file" name="file" accept=".png" required>
  <button>Upload</button>
 </form>
 <div class="div"></div>
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
