"""Lectura/escritura segura de JSON (escritura atómica + lock por proceso)."""
import json
import os
import tempfile
import threading

_LOCK = threading.RLock()


def load_json(path, default=None):
    if default is None:
        default = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with _LOCK:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def update_json(path, fn, default=None):
    """Lee, transforma con fn(data) -> data y guarda, todo bajo lock."""
    with _LOCK:
        data = load_json(path, default)
        data = fn(data)
        save_json(path, data)
        return data
