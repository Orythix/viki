"""
DELIBERATELY VULNERABLE DEMO — LOCAL LAB ONLY.

Reflected XSS for defensive training. Never deploy publicly.
Access only from the lab Docker network (http://sandbox-demo:8080).

Mitigations learners should practice:
- output encoding
- Content-Security-Policy
- SameSite cookies if sessions added later
"""
from __future__ import annotations

from flask import Flask, request

app = Flask(__name__)


@app.get("/")
def index():
    return (
        "<h1>Lab sandbox demo (vulnerable)</h1>"
        "<p>This app reflects <code>q</code> without encoding — for XSS education only.</p>"
        "<form method='get'><input name='q' value='hello'/><button type='submit'>Go</button></form>"
    )


@app.get("/echo")
def echo():
    q = request.args.get("q", "")
    # Intentionally unsafe: reflected HTML
    return f"<p>You said: {q}</p><a href='/'>back</a>"


@app.get("/health")
def health():
    return {"status": "ok"}
