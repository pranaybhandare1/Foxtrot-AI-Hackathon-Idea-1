"""Oura OAuth2 (authorization-code flow) for a single local user.

`connect()` opens Oura's consent page, catches the redirect on http://localhost:8766/callback with a
one-shot local server (state-checked), exchanges the code, and stores tokens in data/secrets/
(gitignored, chmod 600). `access_token()` returns a valid token, refreshing when needed. Oura rotates
refresh tokens, so every refresh response is persisted.

Credentials are read from the environment or the repo's .env file; they are never logged.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from t1d_core.settings import REPO_ROOT, Config

AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
REFRESH_MARGIN_S = 300


class OuraAuthError(RuntimeError):
    pass


def read_env_file(path: Path = REPO_ROOT / ".env") -> dict[str, str]:
    """Minimal KEY=VALUE parser (comments and blank lines ignored, optional quotes stripped)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str

    @classmethod
    def load(cls) -> Credentials:
        env = read_env_file() | {k: v for k, v in os.environ.items() if k.startswith("OURA_")}
        cid, secret = env.get("OURA_CLIENT_ID", ""), env.get("OURA_CLIENT_SECRET", "")
        if not cid or not secret:
            raise OuraAuthError("OURA_CLIENT_ID and OURA_CLIENT_SECRET must be set in .env (see .env.example)")
        return cls(cid, secret)


def token_path(cfg: Config) -> Path:
    return cfg.layers.root / "secrets" / "oura_token.json"


def _save(cfg: Config, token: dict) -> None:
    path = token_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    token = token | {"obtained_at": int(time.time())}
    path.write_text(json.dumps(token, indent=2))
    path.chmod(0o600)


def _post_token(form: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:  # never echo the request (it contains the secret)
        raise OuraAuthError(f"token endpoint returned {e.code}: {e.read()[:300]!r}") from None


def authorize_url(cfg: Config, client_id: str, state: str) -> str:
    oura = cfg.raw["sources"]["oura"]
    query = {
        "client_id": client_id,
        "redirect_uri": oura["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(oura["scopes"]),
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(query)}"


def connect(cfg: Config, open_browser: bool = True, timeout_s: int = 300) -> dict:
    """Interactive one-time consent. Returns non-secret token metadata."""
    creds = Credentials.load()
    redirect = urllib.parse.urlparse(cfg.raw["sources"]["oura"]["redirect_uri"])
    state = secrets.token_urlsafe(24)
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            url = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(url.query))
            if url.path != redirect.path:
                self.send_response(404)
                self.end_headers()
                return
            ok = params.get("state") == state and "code" in params
            result.update(params if ok else {"error": params.get("error", "state mismatch or missing code")})
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Oura connected. You can close this tab." if ok else f"Oura connection failed: {result['error']}"
            self.wfile.write(
                f"<html><body style='font-family:system-ui;padding:40px'><h2>{msg}</h2></body></html>".encode()
            )

        def log_message(self, *args):  # keep the code out of terminal logs
            pass

    server = HTTPServer(("127.0.0.1", redirect.port or 80), Handler)
    server.timeout = 1
    url = authorize_url(cfg, creds.client_id, state)
    print(f"Opening Oura consent page. If it doesn't open, visit:\n{url}")
    if open_browser:
        webbrowser.open(url)
    deadline = time.time() + timeout_s
    while not result and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if "code" not in result:
        raise OuraAuthError(result.get("error", "timed out waiting for the Oura redirect"))

    token = _post_token(
        {
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": cfg.raw["sources"]["oura"]["redirect_uri"],
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }
    )
    _save(cfg, token)
    return {"status": "connected", "scope": token.get("scope"), "expires_in": token.get("expires_in")}


def access_token(cfg: Config) -> str:
    """A valid access token, refreshing (and persisting the rotated refresh token) when close to expiry."""
    path = token_path(cfg)
    if not path.exists():
        raise OuraAuthError("Oura is not connected yet: run `make oura-connect`")
    token = json.loads(path.read_text())
    expires_at = token.get("obtained_at", 0) + int(token.get("expires_in", 0))
    if time.time() < expires_at - REFRESH_MARGIN_S:
        return token["access_token"]
    creds = Credentials.load()
    fresh = _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }
    )
    fresh.setdefault("refresh_token", token["refresh_token"])
    _save(cfg, fresh)
    return fresh["access_token"]
