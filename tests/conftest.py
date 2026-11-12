import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    import app as app_module
    from core.activity import ActivityLog
    app_module.app.config.update(TESTING=True, CSRF_ENABLED=False)
    monkeypatch.setattr(app_module, "activity", ActivityLog(str(tmp_path / "actividad.json")))
    yield app_module.app


@pytest.fixture()
def client(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
    return c


@pytest.fixture()
def admin(client):
    with client.session_transaction() as s:
        s["admin"] = True
    return client
