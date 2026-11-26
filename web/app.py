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
 body { margin: 0; background: #0e1621; color: rgba(255,255,255,.87);
        font-family: -apple-system, "Segoe UI", Roboto, Helvetica, sans-serif; }
 .topbar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center;
           gap: 12px; background: #17212b; border-bottom: 1px solid #101921;
           padding: 6px 14px; height: 52px; }
 .mark { width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
         background: linear-gradient(135deg, #3390ec, #64b5ef);
         display: flex; align-items: center; justify-content: center; }
 .mark svg { width: 18px; height: 18px; fill: #fff; }
 .title { display: flex; flex-direction: column; line-height: 1.2; }
 .title b { font-size: .95rem; font-weight: 700; color: #fff; }
 .title .muted { font-size: .78rem; margin: 0; }
 .search { flex: 0 1 300px; background: #242f3d; border-radius: 22px;
           padding: 8px 16px; color: #7f91a4; font-size: .9rem; }
 .fill { flex: 1; }
 .mechip { display: flex; align-items: center; gap: 8px; background: #242f3d;
           border-radius: 22px; padding: 4px 12px 4px 4px; font-size: .9rem;
           font-weight: 600; }
 .initial { width: 28px; height: 28px; border-radius: 50%; color: #fff; font-size: .85rem;
            display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #3390ec, #8774e1); }
 .wrap { max-width: 560px; margin: 20px auto 56px; padding: 0 10px; }
 .card { background: #17212b; border: 1px solid #101921; border-radius: 12px;
         padding: 16px; margin-bottom: 12px; }
 h1 { font-size: 1.2rem; margin: 0; font-weight: 600; }
 h2 { font-size: .85rem; margin: 0 0 10px; color: #7f91a4; font-weight: 700;
      text-transform: uppercase; letter-spacing: .5px; }
 code { background: #242f3d; padding: 3px 8px; border-radius: 6px;
        color: #64b5ef; font-size: .9em; }
 .center { text-align: center; }
 .avatar-big { width: 112px; height: 112px; object-fit: cover; border-radius: 50%;
               background: #242f3d; margin: 8px auto 10px; display: block;
               border: 3px solid #242f3d; }
 .status { color: #3390ec; font-size: .9rem; margin: 4px 0 0; font-weight: 500; }
 input, button { font-size: 15px; padding: 11px 14px; margin: 6px 0;
                 border-radius: 10px; display: block; width: 100%; }
 input { background: #242f3d; border: 1px solid transparent; color: rgba(255,255,255,.87); }
 input:focus { outline: none; border-color: #3390ec; }
 button { background: #3390ec; color: #fff; border: 0; cursor: pointer;
          font-weight: 700; transition: background .15s ease; }
 button:hover { background: #2b81cc; }
 .err { color: #e8544b; font-weight: 600; }
 .ok { color: #4fce5d; font-weight: 600; }
 .muted { color: #7f91a4; font-size: .92rem; }
 a { color: #62bcf9; text-decoration: none; }
 a:hover { text-decoration: underline; }
 .div { border-top: 1px solid #101921; margin: 14px 0; }
 .bubble { background: #182533; border-radius: 12px 12px 12px 4px; padding: 10px 14px;
           display: inline-block; margin: 0; }
 .links { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
</style>
"""

TOPBAR = """
<div class="topbar">
 <span class="mark"><svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg></span>
 <div class="title"><b>TargetSocial</b><span class="muted">content-type override lab</span></div>
 <div class="search">Search</div>
 <div class="fill"></div>
 {% if username %}<span class="mechip"><span class="initial">{{ username[0]|upper }}</span>{{ username }}</span>{% endif %}
</div>
<div class="wrap">
"""

LOGIN_PAGE = STYLE + TOPBAR + """
<div class="card center" style="max-width:380px;margin:48px auto">
 <div class="mark" style="width:88px;height:88px;margin:10px auto 16px">
  <svg viewBox="0 0 24 24" style="width:44px;height:44px"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
 </div>
 <h1>Sign in to TargetSocial</h1>
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
<div class="card center">
 <img class="avatar-big" src="/uploads/{{ avatar }}?v={{ nonce }}" alt="avatar of {{ username }}">
 <h1>{{ username }}</h1>
 <p class="status">online</p>
 <p class="muted">{{ username }}'s profile page on TargetSocial</p>
</div>
{% if is_me %}
<div class="card">
 <h2>Saved messages — only you should see this</h2>
 <p class="bubble"><code>{{ note }}</code></p>
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
<div class="card center">
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
