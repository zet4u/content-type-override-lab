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
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Lato:wght@400;700&display=swap" rel="stylesheet" />
<style>
 :root { color-scheme: dark; }
 :root {
  --bg: #0f1115; --bg-elev: #15181d; --bg-code: #14171c;
  --text: #d6d3cc; --text-soft: #928e87; --text-faint: #65615a;
  --rule: #22252b; --rule-soft: #1a1d22;
  --accent: #c4e84a; --accent-dim: rgba(196,232,74,.09);
  --danger: #e85f5c;
  --display: 'Geist Mono', 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  --bodyfont: 'Lato', 'Ubuntu', 'Inter', 'Roboto', ui-sans-serif, system-ui, -apple-system, sans-serif;
 }
 * { box-sizing: border-box; margin: 0; padding: 0; }
 body {
  background: var(--bg); color: var(--text);
  font-family: var(--bodyfont); font-size: 15px; line-height: 1.65;
  min-height: 100vh;
  background-image:
   radial-gradient(ellipse 80% 50% at 50% -10%, rgba(212,255,63,.05) 0%, transparent 60%),
   radial-gradient(ellipse 60% 40% at 100% 100%, rgba(74,214,255,.025) 0%, transparent 70%);
  background-attachment: fixed;
 }
 ::selection { background: var(--accent); color: var(--bg); }
 a { color: var(--accent); text-decoration: none; transition: color .15s ease; }
 a:hover { color: var(--text); }
 .masthead { max-width: 1280px; margin: 0 auto; padding: 28px 64px;
   display: flex; justify-content: space-between; align-items: center;
   border-bottom: 1px solid var(--rule); }
 .masthead__logo { font-family: var(--display); font-weight: 500; font-size: 14px;
   color: var(--text); letter-spacing: .01em; }
 .masthead__nav { display: flex; gap: 28px; font-family: var(--display);
   font-size: 14px; letter-spacing: .02em; align-items: center; }
 .masthead__nav a { color: var(--text-soft); position: relative; padding: 4px 0; }
 .masthead__nav a:hover { color: var(--text); }
 .masthead__nav a.is-active { color: var(--accent); }
 .masthead__nav a.is-active::before { content: ''; position: absolute;
   inset: auto 0 -2px 0; height: 1px; background: var(--accent); }
 .masthead__nav button { background: none; border: 0; color: var(--text-soft);
   font-family: var(--display); font-size: 14px; letter-spacing: .02em;
   cursor: pointer; padding: 4px 0; }
 .masthead__nav button:hover { color: var(--text); }
 .index { max-width: 960px; margin: 0 auto; padding: 56px 64px 40px; }
 .posts__heading { font-family: var(--display); font-size: 11px; text-transform: uppercase;
   letter-spacing: .18em; color: var(--text-faint); margin-bottom: 8px;
   padding-bottom: 12px; border-bottom: 1px solid var(--rule);
   display: flex; justify-content: space-between; }
 .kicker { color: var(--accent); position: relative; padding-left: 22px;
   font-family: var(--display); font-size: 10.5px; text-transform: uppercase;
   letter-spacing: .14em; }
 .kicker::before { content: ''; position: absolute; left: 0; top: 50%;
   width: 14px; height: 1px; background: var(--accent); transform: translateY(-50%); }
 .panel { border: 1px solid var(--rule); border-radius: 3px;
   background: var(--bg-code); padding: 24px; margin-bottom: 18px; }
 .panel--dashed { border-style: dashed; background: rgba(212,255,63,.02); }
 h1 { font-family: var(--bodyfont); font-weight: 700; font-size: 26px;
   line-height: 1.15; letter-spacing: -.005em; color: var(--text); }
 h2 { font-family: var(--display); font-weight: 500; font-size: 12.5px;
   letter-spacing: .04em; text-transform: uppercase; color: var(--text-soft);
   margin: 1.4em 0 .4em; }
 code { background: var(--bg-code); border: 1px solid var(--rule);
   padding: 2px 7px; border-radius: 3px; color: var(--accent);
   font-family: var(--display); font-size: .9em; }
 .profile { display: flex; gap: 24px; align-items: flex-start;
   padding: 24px 0 32px; margin-bottom: 4px; }
 .avatar-big { width: 96px; height: 96px; object-fit: cover; border-radius: 50%;
   background: var(--bg-code); border: 3px solid var(--bg); flex-shrink: 0; }
 .name { font-family: var(--bodyfont); font-weight: 700; font-size: 28px;
   line-height: 1.15; margin: 0 0 6px; color: var(--text); }
 .status { font-family: var(--display); font-size: 11px; letter-spacing: .1em;
   text-transform: uppercase; color: var(--accent); margin: 0 0 14px; }
 .bio { font-size: 15px; line-height: 1.6; color: var(--text-soft); margin: 0 0 14px; }
 .chips { display: flex; flex-wrap: wrap; gap: 10px 12px; font-family: var(--display);
   font-size: 13px; letter-spacing: -.005em; }
 .chip { display: inline-flex; align-items: baseline; gap: 10px; padding: 8px 14px;
   border: 1px solid var(--rule); border-radius: 999px; color: var(--text);
   transition: border-color .15s ease, color .15s ease, transform .15s ease; }
 .chip:hover { border-color: var(--accent); color: var(--accent); transform: translateY(-1px); }
 .chip .count { font-size: 11px; letter-spacing: .04em; color: var(--text-faint); }
 input, button.b { font-size: 15px; padding: 10px 14px; margin: 6px 0;
   display: block; width: 100%; border-radius: 3px;
   font-family: var(--bodyfont); }
 input { background: var(--bg); border: 1px solid var(--rule); color: var(--text);
   transition: border-color .15s ease; }
 input:focus { outline: none; border-color: var(--accent);
   box-shadow: 0 0 0 3px var(--accent-dim); }
 button.b { background: var(--accent); color: #0c0d0f; border: 0;
   font-family: var(--display); font-size: 12px; font-weight: 600;
   text-transform: uppercase; letter-spacing: .14em; cursor: pointer;
   transition: filter .15s ease; }
 button.b:hover { filter: brightness(1.08); }
 .err { color: var(--danger); font-weight: 600; font-size: 14px;
   font-family: var(--display); letter-spacing: .02em; }
 .ok { color: var(--accent); font-size: 14px; font-family: var(--display);
   letter-spacing: .02em; }
 .muted { color: var(--text-soft); font-size: .95rem; }
 .faint { color: var(--text-faint); font-size: .9rem; }
 .quote { margin: 1.2em 0; padding: 4px 0 4px 18px; border-left: 2px solid var(--accent);
   font-style: italic; color: var(--text-soft); }
 .site-foot { max-width: 960px; margin: 40px auto 36px; padding: 22px 64px 0;
   border-top: 1px solid var(--rule); display: flex; justify-content: space-between;
   align-items: center; font-family: var(--display); font-size: 11px;
   color: var(--text-faint); }
 @media (max-width: 640px) {
   .masthead, .index, .site-foot { padding-left: 20px; padding-right: 20px; }
   .profile { flex-direction: column; }
 }
</style>
"""

MASTHEAD = """
<header class="masthead">
 <a href="/" class="masthead__logo">TargetSocial</a>
 <nav class="masthead__nav">
  {% if nav_user %}
   <a href="/profile" class="is-active">Profile</a>
   <a href="/upload">Upload</a>
   <button type="submit" form="logout-form">Log out</button>
  {% else %}
   <a href="/" class="is-active">Log in</a>
  {% endif %}
 </nav>
</header>
<main class="index">
"""

SITEFOOT = """
</main>
<footer class="site-foot">
 <span>TargetSocial — content-type override lab</span>
 <span>all ports bound to 127.0.0.1</span>
</footer>
"""

LOGIN_PAGE = STYLE + MASTHEAD + """
 <div class="posts__heading"><span>— Sign in</span><span>demo · alice, bob</span></div>
 <div class="panel" style="margin-top:24px;max-width:420px">
  <p class="muted" style="margin-bottom:14px">A tiny demo social network: users upload avatar images.</p>
  {% if error %}<p class="err">{{ error }}</p>{% endif %}
  <form method="post" action="/login">
   <input name="username" placeholder="username" value="alice" required>
   <input name="password" type="password" placeholder="password" value="alice-pass-123" required>
   <button type="submit" class="b">Log in</button>
  </form>
  <p class="faint" style="margin-top:14px">Demo users: <code>alice / alice-pass-123</code>,
  <code>bob / bob-pass-123</code></p>
 </div>
""" + SITEFOOT

PROFILE_PAGE = STYLE + MASTHEAD + """
 <div class="posts__heading"><span>— Profile</span><span>{{ username }} / targetsocial</span></div>
 <div class="profile">
  <img class="avatar-big" src="/uploads/{{ avatar }}?v={{ nonce }}" alt="avatar of {{ username }}">
  <div>
   <h1 class="name">{{ username }}</h1>
   <p class="status">online</p>
   <p class="bio">{{ username }}'s profile page on TargetSocial.</p>
  </div>
 </div>
{% if is_me %}
 <div class="panel">
  <p class="kicker" style="margin-bottom:10px">Saved messages — only you should see this</p>
  <blockquote class="quote"><code>{{ note }}</code></blockquote>
 </div>
 <div class="panel" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
  <div class="chips">
   <a class="chip" href="/upload">Upload avatar <span class="count">↗</span></a>
   <a class="chip" href="/u/{{ username }}">Public view <span class="count">↗</span></a>
  </div>
  <form method="post" action="/logout" id="logout-form"><button type="submit" class="b" style="width:auto;padding:10px 18px">Log out</button></form>
 </div>
 <p class="faint">Your avatar is served at
    <code>/uploads/{{ avatar }}</code> from this same origin.</p>
{% else %}
 <div class="panel">
  <p class="muted">You are viewing {{ username }}'s public profile.</p>
  <p style="margin-top:10px"><a href="/login">Log in →</a></p>
 </div>
{% endif %}
""" + SITEFOOT

UPLOAD_PAGE = STYLE + MASTHEAD + """
 <div class="posts__heading"><span>— Upload avatar</span><span>.png only</span></div>
 <div class="panel panel--dashed" style="max-width:480px;margin-top:24px">
  <p class="muted" style="margin-bottom:12px">Pick a new profile picture for your account.</p>
  {% if error %}<p class="err">Rejected: {{ error }}</p>{% endif %}
  {% if notice %}<p class="ok">{{ notice }}</p>{% endif %}
  <form method="post" action="/upload" enctype="multipart/form-data">
   <input type="file" name="file" accept=".png" required>
   <button type="submit" class="b">Upload</button>
  </form>
  <p class="faint" style="margin-top:14px">Allowed: <code>.png</code> files only. Every upload is forced to
  <code>Content-Type: image/png</code> at upload time.</p>
  <p style="margin-top:10px"><a href="/profile">← Back to profile</a></p>
 </div>
""" + SITEFOOT

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
        nav_user=username,
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
        nav_user=None,
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
        return render_template_string(
            UPLOAD_PAGE, error=None, notice=None, nav_user=session["user"]
        )

    file = request.files.get("file")
    if file is None or file.filename == "":
        return render_template_string(
            UPLOAD_PAGE, error="no file selected", notice=None, nav_user=session["user"]
        )

    if not file.filename.lower().endswith(".png"):
        return render_template_string(
            UPLOAD_PAGE, error="only .png extensions allowed", notice=None,
            nav_user=session["user"],
        )

    head = file.stream.read(8)
    file.stream.seek(0)
    if head != PNG_MAGIC:
        return render_template_string(
            UPLOAD_PAGE, error="magic bytes do not look like PNG", notice=None,
            nav_user=session["user"],
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
        nav_user=session["user"],
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
