"""Registro liviano de actividad (búsquedas, copias) para analítica interna."""
import os
from collections import Counter
from datetime import datetime, timedelta

from .storage import load_json, update_json

MAX_EVENTS = 5000


class ActivityLog:
    def __init__(self, path):
        self.path = path

    def log(self, tipo, query="", resultados=0, extra=None):
        evt = {"ts": datetime.now().isoformat(timespec="seconds"), "tipo": tipo,
               "query": (query or "")[:200], "resultados": int(resultados or 0)}
        if extra:
            evt.update(extra)

        def fn(data):
            data = data if isinstance(data, list) else []
            data.append(evt)
            return data[-MAX_EVENTS:]
        try:
            update_json(self.path, fn, default=[])
        except OSError:
            pass

    def events(self):
        data = load_json(self.path, [])
        return data if isinstance(data, list) else []

    def summary(self, days=14):
        evs = self.events()
        today = datetime.now().date()
        start = today - timedelta(days=days - 1)
        per_day = Counter()
        busquedas = Counter()
        sin_resultado = Counter()
        tipos = Counter()
        for e in evs:
            try:
                d = datetime.fromisoformat(e["ts"]).date()
            except (KeyError, ValueError):
                continue
            tipos[e.get("tipo", "")] += 1
            if e.get("tipo") in ("busqueda", "busqueda_presencial"):
                q = (e.get("query") or "").strip()
                if q:
                    busquedas[q] += 1
                    if not e.get("resultados"):
                        sin_resultado[q] += 1
                if d >= start:
                    per_day[d.isoformat()] += 1
        dias = [(start + timedelta(days=i)).isoformat() for i in range(days)]
        hoy = per_day.get(today.isoformat(), 0)
        return {
            "dias": dias,
            "por_dia": [per_day.get(d, 0) for d in dias],
            "top_busquedas": busquedas.most_common(10),
            "sin_resultado": sin_resultado.most_common(10),
            "total_busquedas": sum(busquedas.values()),
            "busquedas_hoy": hoy,
            "copias": tipos.get("copia", 0),
            "whatsapp": tipos.get("whatsapp", 0),
            "total_eventos": len(evs),
        }

    def clear(self):
        if os.path.exists(self.path):
            os.remove(self.path)
