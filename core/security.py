"""Protección CSRF basada en sesión y límite de intentos de login."""
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from flask import abort, request, session

CSRF_KEY = "_csrf_token"


def csrf_token():
    tok = session.get(CSRF_KEY)
    if not tok:
        tok = secrets.token_urlsafe(32)
        session[CSRF_KEY] = tok
    return tok


def init_csrf(app, exempt=()):
    exempt = set(exempt)

    @app.before_request
    def _check_csrf():
        if not app.config.get("CSRF_ENABLED", True):
            return
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        if request.endpoint in exempt:
            return
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        expected = session.get(CSRF_KEY, "")
        if not expected or not sent or not hmac.compare_digest(str(sent), str(expected)):
            abort(400, description="Token de seguridad inválido o vencido. Recarga la página e intenta de nuevo.")

    app.jinja_env.globals["csrf_token"] = csrf_token


class LoginLimiter:
    """Bloquea temporalmente una IP tras varios intentos fallidos."""

    def __init__(self, max_attempts=6, window=300):
        self.max_attempts = max_attempts
        self.window = window
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, scope):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
        return f"{scope}:{ip}"

    def blocked(self, scope="global"):
        now = time.time()
        with self._lock:
            q = self._hits[self._key(scope)]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_attempts:
                return int(self.window - (now - q[0])) + 1
        return 0

    def fail(self, scope="global"):
        with self._lock:
            self._hits[self._key(scope)].append(time.time())

    def reset(self, scope="global"):
        with self._lock:
            self._hits.pop(self._key(scope), None)


def check_password(given, expected):
    return hmac.compare_digest(str(given or ""), str(expected or ""))
