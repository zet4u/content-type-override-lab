import io
import os

import boto3
from botocore.client import Config
from flask import Flask, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET", "lab-secret-change-me"),
    SESSION_COOKIE_HTTPONLY=os.environ.get("SESSION_COOKIE_HTTPONLY", "0") == "1",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

S3 = boto3.client(
    "s3",
    endpoint_url=os.environ.get("MINIO_ENDPOINT", "http://minio:9000"),
    aws_access_key_id=os.environ.get("MINIO_ROOT_USER", "labadmin"),
    aws_secret_access_key=os.environ.get("MINIO_ROOT_PASSWORD", "labdev-only-change-me"),
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)
BUCKET = os.environ.get("BUCKET", "public")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

USERS = {
    "alice": {"password": "alice-pass-123", "note": "Recovery code: 7721-RDRE-ALICE"},
    "bob": {"password": "bob-pass-123", "note": "Recovery code: 3340-KQJD-BOB"},
}

STYLE = """
<style>
 body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background:#f0f2f5; margin:0; }
 .card { max-width:560px; margin:48px auto; background:#fff; border-radius:12px;
         padding:28px 32px; box-shadow:0 2px 10px rgba(0,0,0,.12); }
 h1 { margin:0 0 6px; color:#1877f2; }
 code { background:#eee; padding:2px 6px; border-radius:4px; }
 img.avatar { width:128px; height:128px; object-fit:cover; border-radius:50%;
              border:2px solid #ddd; background:#fafafa; }
 input, button { font-size:1rem; padding:8px 12px; margin:6px 0; border-radius:8px;
                 border:1px solid #ccc; display:block; width:90%; }
 button { background:#1877f2; color:#fff; border:0; cursor:pointer; width:95%; }
 .err { color:#c00; font-weight:600; }
 .ok { color:#080; font-weight:600; }
 .muted { color:#777; font-size:.9rem; }
</style>
"""

LOGIN_PAGE = STYLE + """
<div class="card">
 <h1>TargetSocial</h1>
 <p>A tiny demo social network: users upload avatar images.</p>
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
