"""Catálogo de pensum en PDF (pregrado y posgrado)."""
import os
import re
from datetime import datetime

from .text import norm, program_similarity, strip_accents

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Los PDF viven en data/pensum/ para que los que se suban desde el admin persistan entre despliegues
PENSUM_DIRS = {
    "pregrado": os.path.join(BASE_DIR, "data", "pensum", "pregrado"),
    "posgrado": os.path.join(BASE_DIR, "data", "pensum", "posgrado"),
}

_SMALL = {"de", "en", "y", "la", "el", "del", "los", "las", "para", "con", "a", "e", "al"}
_WORDS = {
    "administracion": "administración", "agronegocios": "agronegocios", "publica": "pública",
    "comunicacion": "comunicación", "contaduria": "contaduría", "economia": "economía",
    "ingenieria": "ingeniería", "licenciatura": "licenciatura", "educacion": "educación",
    "psicologia": "psicología", "sociologia": "sociología", "tecnico": "técnico",
    "ganaderia": "ganadería", "tecnologia": "tecnología", "gestion": "gestión", "logistica": "logística",
    "especializacion": "especialización", "maestria": "maestría", "auditoria": "auditoría",
    "analitica": "analítica", "epidemiologia": "epidemiología", "informatica": "informática",
    "innovacion": "innovación", "pedagogia": "pedagogía", "pedagogica": "pedagógica",
    "revisoria": "revisoría", "direccion": "dirección", "produccion": "producción",
    "adolsc": "adolescencia", "ciberseguridad": "ciberseguridad", "constitucional": "constitucional",
}
# Restos de nombres de archivo que no hacen parte del programa
_JUNK = [re.compile(r"\(\d+\)"), re.compile(r"specinfancia[\w-]*", re.I), re.compile(r"\s*,\s*,\s*"), re.compile(r"virt$", re.I)]


def display_name(filename):
    name = os.path.splitext(filename)[0]
    for rx in _JUNK:
        name = rx.sub(" " if rx.pattern != r"\s*,\s*,\s*" else ", ", name)
    name = re.sub(r"\s+", " ", name).strip(" ,-_")
    name = name.replace(" ,", ",")
    words = []
    for i, w in enumerate(name.split(" ")):
        low = w.lower()
        key = strip_accents(low).strip(",")
        if key in _WORDS:
            low = _WORDS[key] + ("," if low.endswith(",") else "")
        if i > 0 and low in _SMALL:
            words.append(low)
        else:
            words.append(low[:1].upper() + low[1:])
    return " ".join(words).replace("Infancia, Adolescencia", "Infancia, Adolescencia")


def categoria(nivel, nombre):
    n = norm(nombre)
    if nivel == "posgrado":
        return "Maestrías" if n.startswith("MAESTRIA") else "Especializaciones"
    if n.startswith("TECNICO") or n.startswith("TECNOLOGIA"):
        return "Técnicos y tecnologías"
    return "Profesionales"


def listar(nivel):
    folder = PENSUM_DIRS.get(nivel)
    if not folder or not os.path.isdir(folder):
        return []
    items = []
    for f in os.listdir(folder):
        if not f.lower().endswith(".pdf"):
            continue
        st = os.stat(os.path.join(folder, f))
        nombre = display_name(f)
        items.append({
            "archivo": f, "nombre": nombre, "categoria": categoria(nivel, nombre), "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y"),
        })
    items.sort(key=lambda x: (x["categoria"], norm(x["nombre"])))
    return items


def buscar_pensum(programa, nivel="pregrado"):
    """Devuelve el archivo de pensum que corresponde a un programa (o None)."""
    best, best_sc = None, 0.0
    for it in listar(nivel):
        sc = program_similarity(programa, it["nombre"])
        if sc > best_sc:
            best, best_sc = it, sc
    return best if best_sc >= 0.75 else None
