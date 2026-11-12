"""Homologaciones SENA · Ibero — aplicación Flask.

Herramienta interna para asesores comerciales de la Corporación Universitaria Iberoamericana:
consulta de homologaciones SENA (virtual, por créditos), mensajes listos para WhatsApp,
precios SENA y regulares, pensum/brochures, piezas gráficas y panel administrativo.
"""
import os
import re
import shutil
from datetime import datetime, timedelta
from functools import wraps

import pandas as pd
from flask import (Flask, Response, abort, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from werkzeug.utils import secure_filename

from core.activity import ActivityLog
from core.assistant import answer as assistant_answer, claude_available
from core.data import (ACTAS_NOMBRE, DATA_DIR, DEFAULT_CONFIG, DataStore, actas_file, cohorte_texto,
                       ruta_subida, buscar_homologacion, explorar_programas, rank_titles, validar_actas)
from core.pensum import PENSUM_DIRS, buscar_pensum, listar as listar_pensum
from core.messages import mensaje_homologacion, mensaje_precios
from core.security import LoginLimiter, check_password, init_csrf
from core.text import clean_df, fix_text_enc, money, norm, pretty_name  # noqa: F401 (re-export)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = "1.0"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "homologaciones-ibero-2027")
app.config.update(
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.environ.get("SESSION_HOURS", "12"))),
    JSON_AS_ASCII=False,
)
app.json.ensure_ascii = False

# Credenciales (se pueden sobreescribir con variables de entorno)
GLOBAL_USER = os.environ.get("APP_USER", "Innovacion")
GLOBAL_PASSWORD = os.environ.get("APP_PASSWORD", "0228")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Jorsh123")

STATIC_DIR = os.path.join(BASE_DIR, "static")
BROCHURES_DIR = os.path.join(STATIC_DIR, "brochures")
PIEZAS_DIR = os.path.join(STATIC_DIR, "piezas")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_PDF_EXTENSIONS = {"pdf"}

# Versión de los archivos estáticos: cambia con cada despliegue para que el navegador no use una copia vieja
ASSET_VERSION = (os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:10]
                 or str(int(max(os.path.getmtime(os.path.join(STATIC_DIR, f))
                                for f in ("css/app.css", "js/app.js", "js/imagen-homologacion.js")))))

store = DataStore()
# En Vercel (demo) el disco es de solo lectura salvo /tmp
activity = ActivityLog(os.path.join("/tmp" if os.environ.get("VERCEL") else DATA_DIR, "actividad.json"))
limiter = LoginLimiter()

app.extensions["homologaciones_store"] = store
init_csrf(app)


# =====================================================
# HELPERS
# =====================================================
def allowed_file(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def safe_join(base, *parts):
    """Une rutas evitando salir de `base` (protección path traversal)."""
    path = os.path.abspath(os.path.join(base, *parts))
    base_abs = os.path.abspath(base)
    if os.path.commonpath([path, base_abs]) != base_abs:
        return None
    return path


def listed_name(directory, name):
    """Devuelve `name` solo si existe literalmente en `directory` (soporta tildes/ñ)."""
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return None
    try:
        return name if name in os.listdir(directory) else None
    except OSError:
        return None


def breadcrumb_for(subfolder):
    crumbs = []
    if subfolder:
        parts = [p for p in subfolder.replace("\\", "/").split("/") if p]
        for i, part in enumerate(parts):
            crumbs.append({"name": part, "path": "/".join(parts[: i + 1])})
    return crumbs


def list_folder(folder):
    items = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    carpetas = [d for d in items if os.path.isdir(os.path.join(folder, d))]
    imagenes = [f for f in items if os.path.isfile(os.path.join(folder, f)) and allowed_file(f, ALLOWED_IMAGE_EXTENSIONS)]
    return carpetas, imagenes


def count_images(folder):
    total = 0
    for _, _, files in os.walk(folder):
        total += sum(1 for f in files if allowed_file(f, ALLOWED_IMAGE_EXTENSIONS))
    return total


def folder_cover(folder):
    for root, _, files in os.walk(folder):
        for f in sorted(files):
            if allowed_file(f, ALLOWED_IMAGE_EXTENSIONS):
                return os.path.relpath(os.path.join(root, f), STATIC_DIR).replace("\\", "/")
    return None


def file_info(path):
    try:
        st = os.stat(path)
        return {"size": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")}
    except OSError:
        return {"size": 0, "mtime": ""}


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


app.jinja_env.filters["money"] = money
app.jinja_env.filters["pretty"] = pretty_name
app.jinja_env.filters["human_size"] = human_size


MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


def _fecha_larga_filter(v):
    from datetime import date as _d
    try:
        d = _d.fromisoformat(str(v))
    except ValueError:
        return v
    return f"{d.day} de {MESES[d.month]} de {d.year}"


app.jinja_env.filters["fecha_larga"] = _fecha_larga_filter


# =====================================================
# AUTENTICACIÓN
# =====================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Sesión expirada"}), 401
            return redirect(url_for("global_login", next=request.full_path if request.query_string else request.path))
        return f(*args, **kwargs)
    return wrapper


def admin_only(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin")
        return f(*args, **kwargs)
    return wrapper


def admin_required():
    """Compatibilidad: devuelve redirect si no es admin."""
    if not session.get("admin"):
        return redirect("/admin")
    return None


@app.route("/login", methods=["GET", "POST"])
def global_login():
    error = None
    wait = limiter.blocked("global")
    if request.method == "POST":
        if wait:
            error = f"Demasiados intentos. Espera {wait} segundos."
        elif request.form.get("user", "").strip() == GLOBAL_USER and check_password(request.form.get("password", ""), GLOBAL_PASSWORD):
            limiter.reset("global")
            session.clear()
            session.permanent = request.form.get("remember") == "on"
            session["logged_in"] = True
            session["login_at"] = datetime.now().isoformat(timespec="seconds")
            nxt = request.args.get("next", "/")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
        else:
            limiter.fail("global")
            error = "Usuario o contraseña incorrectos"
    return render_template("global_login.html", error=error)


@app.route("/logout")
def global_logout():
    session.clear()
    return redirect("/login")


# =====================================================
# CONTEXTO GLOBAL DE PLANTILLAS
# =====================================================
NAV = [
    ("Principal", [
        ("/dashboard", "fa-gauge-high", "Panel"),
        ("/", "fa-building-columns", "Homologaciones"),
        ("/programas", "fa-diagram-project", "Explorar programas"),
    ]),
    ("Comercial", [
        ("/mensajes", "fa-comments", "Mensajes"),
        ("/precios", "fa-tags", "Precios"),
    ]),
    ("Recursos", [
        ("/piezas", "fa-images", "Piezas gráficas"),
        ("/brochures", "fa-file-pdf", "Brochures y pensum"),
        ("/capacitacion", "fa-user-graduate", "Capacitación e IA"),
    ]),
]

# Módulos que se pueden ocultar desde Administración → Configuración
MODULOS = {
    "piezas": {"label": "Piezas gráficas", "prefixes": ("/piezas",)},
    "capacitacion": {"label": "Capacitación e IA", "prefixes": ("/capacitacion",)},
}
NAV_MODULO = {"/piezas": "piezas", "/capacitacion": "capacitacion"}

TITLES = {item[0]: item[2] for _, items in NAV for item in items}
TITLES.update({"/sena": "Mensajes SENA", "/admin": "Administración"})


def modulos_ocultos():
    return set(store.config.get("modulos_ocultos") or [])


def mod_on(key):
    return key not in modulos_ocultos()


def nav_visible():
    ocultos = modulos_ocultos()
    out = []
    for section, items in NAV:
        vis = [it for it in items if NAV_MODULO.get(it[0]) not in ocultos]
        if vis:
            out.append((section, vis))
    return out


@app.before_request
def bloquear_modulos_ocultos():
    """Los módulos ocultos no están disponibles para asesores (el admin sí puede entrar)."""
    if session.get("admin"):
        return
    for key in modulos_ocultos():
        mod = MODULOS.get(key)
        if mod and any(request.path == p or request.path.startswith(p + "/") or request.path.startswith(p + "?") for p in mod["prefixes"]):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Módulo no disponible"}), 404
            return redirect("/")


def page_title():
    p = request.path
    if p in TITLES:
        return TITLES[p]
    for prefix in ("/piezas", "/admin", "/brochures"):
        if p.startswith(prefix):
            return TITLES.get(prefix, "Ibero")
    return "Ibero"


def nav_active(href):
    p = request.path
    if href == "/":
        return p == "/"
    return p == href or p.startswith(href + "/")


@app.context_processor
def inject_globals():
    return {
        "NAV": nav_visible(),
        "mod_on": mod_on,
        "nav_active": nav_active,
        "page_title": page_title,
        "cfg": store.config,
        "is_admin": bool(session.get("admin")),
        "app_version": APP_VERSION,
        "asset_v": ASSET_VERSION,
        "now": datetime.now(),
    }


# =====================================================
# ESTÁTICOS Y UTILIDADES
# =====================================================
@app.route("/logo.jpg")
def logo():
    return send_from_directory(BASE_DIR, "logo.jpg")


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(STATIC_DIR, "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "version": APP_VERSION, "titulos": len(store.titulos())})


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "No encontrado"}), 404
    return render_template("error.html", code=404, title="Página no encontrada",
                           message="La página que buscas no existe o fue movida."), 404


@app.errorhandler(400)
def bad_request(e):
    msg = getattr(e, "description", "Solicitud inválida")
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"ok": False, "error": msg}), 400
    return render_template("error.html", code=400, title="Solicitud inválida", message=msg), 400


@app.errorhandler(413)
def too_large(e):
    return render_template("error.html", code=413, title="Archivo demasiado grande",
                           message="El archivo supera el límite de 32 MB."), 413


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Error interno del servidor"}), 500
    return render_template("error.html", code=500, title="Algo salió mal",
                           message="Ocurrió un error inesperado. Intenta de nuevo."), 500


# =====================================================
# HOMOLOGACIONES (VIRTUAL)
# =====================================================
def generar_mensaje(titulo_input):
    """Compatibilidad con la versión anterior: devuelve solo el texto."""
    return mensaje_homologacion(buscar_homologacion(store, titulo_input or ""), store.config)


@app.route("/", methods=["GET", "POST"])
@login_required
def homologaciones():
    if request.method == "POST":
        return redirect(url_for("homologaciones", q=request.form.get("titulo", "")))
    return render_template("homologaciones.html", titulos=store.titulos(), q=request.args.get("q", ""))


@app.route("/api/homologar")
@login_required
def api_homologar():
    q = request.args.get("q", "").strip()
    nombre = request.args.get("nombre", "").strip()[:60]
    incluir_precios = request.args.get("precios") == "1"
    if not q:
        return jsonify({"ok": False, "error": "Escribe un título SENA"}), 400
    res = buscar_homologacion(store, q)
    cfg = store.config
    programas = [p for g in res["grupos"] for p in g["programas"]]
    res["mensaje"] = mensaje_homologacion(res, cfg, nombre=nombre, incluir_precios=incluir_precios)
    res["mensaje_precios"] = mensaje_precios(programas, cfg)
    res["ok"] = True
    if request.args.get("log", "1") == "1":
        activity.log("busqueda", res["grupos"][0]["titulo"] if len(res["grupos"]) == 1 else q, res["total_programas"])
    return jsonify(res)


@app.route("/api/titulos")
@login_required
def api_titulos():
    q = request.args.get("q", "").strip()
    titulos = store.titulos()
    if q:
        return jsonify({"ok": True, "items": rank_titles(q, titulos, limit=int(request.args.get("limit", 12)), threshold=0.55)})
    return jsonify({"ok": True, "items": titulos})


@app.route("/api/track", methods=["POST"])
@login_required
def api_track():
    data = request.get_json(silent=True) or {}
    tipo = str(data.get("tipo", ""))[:30]
    if tipo in ("copia", "whatsapp", "oferta", "imagen"):
        activity.log(tipo, str(data.get("query", ""))[:200], 1)
    return jsonify({"ok": True})


# =====================================================
# EXPLORAR PROGRAMAS (BÚSQUEDA INVERSA)
# =====================================================
@app.route("/programas")
@login_required
def programas():
    return render_template("programas.html", programas=explorar_programas(store))


# =====================================================
# MENSAJES
# =====================================================
@app.route("/mensajes")
@login_required
def mensajes():
    nivel = request.args.get("nivel", "pre")
    if nivel not in ("pre", "pos", "sena", "fav"):
        nivel = "pre"
    return render_template("mensajes.html", programas=store.render_list(store.mensajes_programas()),
                           sena=store.render_list(store.mensajes_sena(), "sena"),
                           nivel=nivel, q=request.args.get("q", ""))


@app.route("/sena")
@login_required
def sena():
    return redirect(url_for("mensajes", nivel="sena", q=request.args.get("q", "")))


# =====================================================
# PRECIOS Y SIMULADOR
# =====================================================
@app.route("/precios")
@login_required
def precios():
    from core.pensum import buscar_pensum
    progs = []
    for p in store.precios():
        nivel = p.get("nivel", "pre")
        pen = buscar_pensum(p["programa"], "posgrado" if nivel == "pos" else "pregrado")
        progs.append({**p, "nivel": nivel, "cohorte_txt": cohorte_texto(p.get("cohorte")), "cohorte_sena_txt": cohorte_texto(p.get("cohorte_sena")),
                      "pensum": pen["archivo"] if pen else None})
    return render_template("precios.html", programas=progs, nivel=request.args.get("nivel", "pre"))


# =====================================================
# PANEL / ESTADÍSTICAS
# =====================================================
@app.route("/dashboard")
@login_required
def dashboard():
    precios_data = [p for p in store.precios() if p.get("nivel", "pre") == "pre"]
    valores = [p.get("valor_sena") or p["valor_final"] for p in precios_data] or [0]
    progs = explorar_programas(store)
    df = store.actas()
    pct = (df["ch"] / df["cp"] * 100).fillna(0) if len(df) else pd.Series(dtype=float)
    rangos = [(0, 20), (20, 40), (40, 60), (60, 101)]
    mensajes_programas = store.mensajes_programas()
    stats = {
        "total_titulos": len(store.titulos()),
        "total_combinaciones": int(len(df)),
        "total_programas_actas": len(progs),
        "total_pregrado": len([m for m in mensajes_programas if m.get("nivel") == "pre"]),
        "total_posgrado": len([m for m in mensajes_programas if m.get("nivel") == "pos"]),
        "total_mensajes_sena": len(store.mensajes_sena()),
        "total_precios": len(precios_data),
        "precio_min": min(valores),
        "precio_max": max(valores),
        "precio_promedio": int(sum(valores) / len(valores)),
        "piezas": count_images(PIEZAS_DIR),
        "max_porcentaje": int(round(pct.max())) if len(pct) else 0,
        "pensum_pre": len(listar_pensum("pregrado")),
        "pensum_pos": len(listar_pensum("posgrado")),
    }
    orden = sorted(precios_data, key=lambda x: x.get("valor_sena") or x["valor_final"])
    chart = {
        "programas": [p["display"] for p in progs],
        "programas_total": [p["total"] for p in progs],
        "dist_labels": [f"{a}–{min(b, 100)}%" for a, b in rangos],
        "dist_values": [int(((pct >= a) & (pct < b)).sum()) for a, b in rangos],
        "precios_labels": [p["programa"] for p in orden],
        "precios_values": [p.get("valor_sena") or p["valor_final"] for p in orden],
    }
    return render_template("dashboard.html", stats=stats, chart=chart, actividad=activity.summary(14))


@app.route("/stats")
@login_required
def stats():
    return redirect(url_for("dashboard"))


# =====================================================
# PÁGINAS DE CONTENIDO
# =====================================================
@app.route("/capacitacion")
@login_required
def capacitacion():
    return render_template("capacitacion.html", ia_claude=claude_available())


@app.route("/capacitacion/api/chat", methods=["POST"])
@app.route("/api/asistente", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json(silent=True) or {}
    msg = str(data.get("message", "")).strip()[:2000]
    if not msg:
        return jsonify({"ok": False, "error": "Mensaje vacío"}), 400
    text, source = assistant_answer(msg, data.get("history") or [], store)
    activity.log("asistente", msg, 1)
    return jsonify({"ok": True, "reply": text, "response": text, "source": source})


# =====================================================
# PIEZAS GRÁFICAS Y BROCHURES
# =====================================================
@app.route("/piezas")
@app.route("/piezas/<path:subfolder>")
@login_required
def piezas(subfolder=""):
    os.makedirs(PIEZAS_DIR, exist_ok=True)
    carpeta = safe_join(PIEZAS_DIR, subfolder)
    if not carpeta or not os.path.isdir(carpeta):
        return redirect("/piezas")
    carpetas, imagenes = list_folder(carpeta)
    folders = [{"name": d, "path": (subfolder + "/" + d) if subfolder else d,
                "count": count_images(os.path.join(carpeta, d)), "cover": folder_cover(os.path.join(carpeta, d))}
               for d in carpetas]
    imgs = [{"name": f, "path": "piezas/" + ((subfolder + "/") if subfolder else "") + f,
             **file_info(os.path.join(carpeta, f))} for f in imagenes]
    return render_template("piezas.html", carpetas=folders, imagenes=imgs, subfolder=subfolder,
                           breadcrumb=breadcrumb_for(subfolder))


# =====================================================
# BROCHURES Y PENSUM (PDF)
# =====================================================
@app.route("/pensum")
@app.route("/pensum/<nivel>")
@login_required
def pensum(nivel="pregrado"):
    """Compatibilidad: el pensum ahora vive dentro de Brochures."""
    return redirect(url_for("brochures", nivel=nivel if nivel in PENSUM_DIRS else "pregrado", ver=request.args.get("ver") or None))


@app.route("/brochures/<nivel>/archivo/<path:filename>")
@app.route("/pensum/<nivel>/archivo/<path:filename>")
@login_required
def pensum_archivo(nivel, filename):
    folder = PENSUM_DIRS.get(nivel)
    if not folder or not listed_name(folder, filename):
        abort(404)
    return send_from_directory(folder, filename, mimetype="application/pdf", conditional=True,
                               as_attachment=request.args.get("descargar") == "1")


@app.route("/brochures")
@login_required
def brochures():
    os.makedirs(BROCHURES_DIR, exist_ok=True)
    otros = [{"archivo": f, "nombre": os.path.splitext(f)[0].replace("_", " "), "categoria": "Otros documentos",
              "size": file_info(os.path.join(BROCHURES_DIR, f))["size"]}
             for f in sorted(os.listdir(BROCHURES_DIR)) if f.lower().endswith(".pdf")]
    conteo = {"pregrado": len(listar_pensum("pregrado")), "posgrado": len(listar_pensum("posgrado")), "otros": len(otros)}
    nivel = request.args.get("nivel", "pregrado")
    if nivel not in conteo or (nivel == "otros" and not otros):
        nivel = "pregrado"
    if nivel == "otros":
        items = [{**o, "url": url_for("static", filename="brochures/" + o["archivo"])} for o in otros]
    else:
        items = [{**it, "url": url_for("pensum_archivo", nivel=nivel, filename=it["archivo"])} for it in listar_pensum(nivel)]
    return render_template("brochures.html", nivel=nivel, items=items, conteo=conteo, ver=request.args.get("ver", ""))


# =====================================================
# ADMINISTRACIÓN
# =====================================================
@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin_login():
    if session.get("admin"):
        return redirect("/admin/dashboard")
    error = None
    if request.method == "POST":
        wait = limiter.blocked("admin")
        if wait:
            error = f"Demasiados intentos. Espera {wait} segundos."
        elif check_password(request.form.get("password", ""), ADMIN_PASSWORD):
            limiter.reset("admin")
            session["admin"] = True
            return redirect("/admin/dashboard")
        else:
            limiter.fail("admin")
            error = "Contraseña incorrecta"
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
@login_required
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")


@app.route("/admin/dashboard")
@admin_only
def admin_dashboard():
    os.makedirs(BROCHURES_DIR, exist_ok=True)
    stats = {
        "mensajes_comerciales": len(store.mensajes_programas()),
        "mensajes_sena": len(store.mensajes_sena()),
        "precios": len(store.precios()),
        "piezas": count_images(PIEZAS_DIR),
        "brochures": len(listar_pensum("pregrado")) + len(listar_pensum("posgrado"))
                     + len([f for f in os.listdir(BROCHURES_DIR) if f.lower().endswith(".pdf")]),
        "titulos": len(store.titulos()),
        "combinaciones": int(len(store.actas())),
    }
    return render_template("admin_dashboard.html", stats=stats, actas_info=file_info(actas_file()),
                           actividad=activity.summary(7))


def _crud_list(filename, fields, ints=(), opcionales=()):
    items = store.json(filename)
    items = list(items)
    action = request.form.get("action")
    idx = request.form.get("index", type=int)

    def read():
        out = {}
        for f in fields:
            v = request.form.get(f, "")
            if f in opcionales:
                out[f] = int(v) if v.strip() else None
            elif f.startswith("cohorte"):
                out[f] = v.strip() or None
            else:
                out[f] = int(v or 0) if f in ints else v.replace("\r\n", "\n")
        return out

    if action == "update" and idx is not None and 0 <= idx < len(items):
        items[idx].update(read())
    elif action == "add":
        nuevo = read()
        if filename == "precios.json":
            nuevo = {"id": max([p.get("id", 0) for p in items], default=0) + 1, **nuevo}
        items.append(nuevo)
    elif action == "delete" and idx is not None and 0 <= idx < len(items):
        items.pop(idx)
    elif action == "move" and idx is not None and 0 <= idx < len(items):
        j = idx + (1 if request.form.get("dir") == "down" else -1)
        if 0 <= j < len(items):
            items[idx], items[j] = items[j], items[idx]
    else:
        return
    store.save(filename, items)


@app.route("/admin/mensajes-comerciales", methods=["GET", "POST"])
@admin_only
def admin_mensajes_comerciales():
    if request.method == "POST":
        _crud_list("mensajes_programas.json", ["nivel", "titulo", "texto"])
        return redirect("/admin/mensajes-comerciales")
    return render_template("admin_mensajes.html", mensajes=store.mensajes_programas(), tipo="comerciales",
                           titulo="Mensajes comerciales", accion="/admin/mensajes-comerciales")


@app.route("/admin/mensajes-sena", methods=["GET", "POST"])
@admin_only
def admin_mensajes_sena():
    if request.method == "POST":
        _crud_list("mensajes_sena.json", ["titulo", "texto"])
        return redirect("/admin/mensajes-sena")
    return render_template("admin_mensajes.html", mensajes=store.mensajes_sena(), tipo="sena",
                           titulo="Mensajes SENA", accion="/admin/mensajes-sena")


@app.route("/admin/precios", methods=["GET", "POST"])
@admin_only
def admin_precios():
    if request.method == "POST":
        _crud_list("precios.json", ["nivel", "programa", "valor", "subsidio", "valor_lista", "remarketing", "pronto_pago",
                                    "valor_final", "cohorte", "descuento_sena", "valor_sena", "pronto_pago_sena", "pago_sena",
                                    "cohorte_sena"],
                   ints=("valor", "valor_final", "subsidio", "remarketing", "pronto_pago"),
                   opcionales=("valor_lista", "descuento_sena", "valor_sena", "pronto_pago_sena", "pago_sena"))
        return redirect("/admin/precios")
    return render_template("admin_precios.html", precios=store.precios())


@app.route("/admin/config", methods=["GET", "POST"])
@admin_only
def admin_config():
    saved = False
    if request.method == "POST":
        cfg = store.config
        for k, default in DEFAULT_CONFIG.items():
            if isinstance(default, list):
                continue
            if k in request.form:
                v = request.form.get(k, "").strip()
                if isinstance(default, int):
                    try:
                        cfg[k] = int(v)
                    except ValueError:
                        continue
                else:
                    cfg[k] = v
        if request.form.get("modulos_form") == "1":
            visibles = set(request.form.getlist("modulos_visibles"))
            cfg["modulos_ocultos"] = [k for k in MODULOS if k not in visibles]
        store.save("config.json", cfg)
        saved = True
    return render_template("admin_config.html", config=store.config, saved=saved, modulos=MODULOS,
                           ocultos=modulos_ocultos())


@app.route("/admin/reemplazar", methods=["POST"])
@admin_only
def admin_reemplazar():
    buscar = request.form.get("buscar", "")
    reemplazo = request.form.get("reemplazo", "")
    destinos = request.form.getlist("destinos") or ["mensajes_programas.json", "mensajes_sena.json"]
    total = 0
    if buscar:
        for fname in destinos:
            if fname not in ("mensajes_programas.json", "mensajes_sena.json"):
                continue
            items = list(store.json(fname))
            for m in items:
                for campo in ("titulo", "texto"):
                    if buscar in m.get(campo, ""):
                        total += m[campo].count(buscar)
                        m[campo] = m[campo].replace(buscar, reemplazo)
            store.save(fname, items)
    return redirect(url_for("admin_dashboard", reemplazos=total))


@app.route("/admin/datos", methods=["POST"])
@admin_only
def admin_datos():
    file = request.files.get("archivo")
    if request.form.get("tipo") != "actas" or not file or not file.filename.lower().endswith(".xlsx"):
        return redirect(url_for("admin_dashboard", error="Selecciona un archivo .xlsx válido"))
    os.makedirs(BACKUP_DIR, exist_ok=True)
    tmp = os.path.join(BACKUP_DIR, "_subida_actas.xlsx")
    file.save(tmp)
    try:
        ok, msg, _ = validar_actas(tmp)
    except Exception as e:  # noqa: BLE001
        ok, msg = False, f"No se pudo leer el Excel: {e}"
    if not ok:
        os.remove(tmp)
        return redirect(url_for("admin_dashboard", error=msg))
    previo = actas_file()
    if os.path.exists(previo):
        shutil.copy2(previo, os.path.join(BACKUP_DIR, f"actas_{datetime.now():%Y%m%d_%H%M%S}.xlsx"))
    os.replace(tmp, ruta_subida(ACTAS_NOMBRE))
    store.invalidate()
    return redirect(url_for("admin_dashboard", ok=f"Acta actualizada: {msg}."))


@app.route("/admin/datos/descargar/<kind>")
@admin_only
def admin_datos_descargar(kind):
    if kind != "actas" or not os.path.exists(actas_file()):
        abort(404)
    return send_file(actas_file(), as_attachment=True)


@app.route("/admin/actividad/limpiar", methods=["POST"])
@admin_only
def admin_actividad_limpiar():
    activity.clear()
    return redirect(url_for("admin_dashboard", ok="Historial de actividad borrado"))


@app.route("/admin/piezas", methods=["GET", "POST"])
@app.route("/admin/piezas/<path:subfolder>", methods=["GET", "POST"])
@admin_only
def admin_piezas(subfolder=""):
    current_dir = safe_join(PIEZAS_DIR, subfolder)
    if not current_dir:
        return redirect("/admin/piezas")
    os.makedirs(current_dir, exist_ok=True)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "upload":
            for file in request.files.getlist("imagenes"):
                if file and file.filename and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
                    name = secure_filename(file.filename) or f"imagen_{datetime.now():%H%M%S}.jpg"
                    file.save(os.path.join(current_dir, name))
        elif action == "delete":
            name = listed_name(current_dir, request.form.get("filename"))
            if name and os.path.isfile(os.path.join(current_dir, name)):
                os.remove(os.path.join(current_dir, name))
        elif action == "rename":
            old = listed_name(current_dir, request.form.get("filename"))
            new = secure_filename(request.form.get("new_name", "").strip())
            if old and new:
                ext = old.rsplit(".", 1)[-1]
                if not allowed_file(new, ALLOWED_IMAGE_EXTENSIONS) and not os.path.isdir(os.path.join(current_dir, old)):
                    new = f"{new}.{ext}"
                if not os.path.exists(os.path.join(current_dir, new)):
                    os.rename(os.path.join(current_dir, old), os.path.join(current_dir, new))
        elif action == "create_folder":
            name = request.form.get("folder_name", "").strip().replace("/", "").replace("\\", "")
            name = name if name not in ("", ".", "..") else ""
            if name:
                os.makedirs(os.path.join(current_dir, name), exist_ok=True)
        elif action == "delete_folder":
            name = listed_name(current_dir, request.form.get("folder_name"))
            if name and os.path.isdir(os.path.join(current_dir, name)):
                shutil.rmtree(os.path.join(current_dir, name))
        return redirect("/admin/piezas" + ("/" + subfolder if subfolder else ""))

    carpetas, imagenes = list_folder(current_dir)
    folders = [{"name": d, "count": count_images(os.path.join(current_dir, d))} for d in carpetas]
    imgs = [{"name": f, "path": "piezas/" + ((subfolder + "/") if subfolder else "") + f,
             **file_info(os.path.join(current_dir, f))} for f in imagenes]
    return render_template("admin_piezas.html", carpetas=folders, imagenes=imgs, subfolder=subfolder,
                           breadcrumb=breadcrumb_for(subfolder))


@app.route("/admin/brochures", methods=["GET", "POST"])
@admin_only
def admin_brochures():
    destinos = {"pregrado": PENSUM_DIRS["pregrado"], "posgrado": PENSUM_DIRS["posgrado"], "otros": BROCHURES_DIR}
    for d in destinos.values():
        os.makedirs(d, exist_ok=True)
    if request.method == "POST":
        action = request.form.get("action")
        carpeta = destinos.get(request.form.get("destino"), BROCHURES_DIR)
        if action == "upload":
            n = 0
            for file in request.files.getlist("pdfs"):
                if file and file.filename and allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
                    nombre = os.path.basename(file.filename.replace("\\", "/")).strip()
                    if not nombre or nombre.startswith(".") or not nombre.lower().endswith(".pdf"):
                        nombre = secure_filename(file.filename) or f"documento_{datetime.now():%H%M%S}.pdf"
                    file.save(os.path.join(carpeta, nombre))
                    n += 1
            return redirect(url_for("admin_brochures", ok=f"{n} PDF subidos"))
        elif action == "delete":
            name = listed_name(carpeta, request.form.get("filename"))
            if name:
                os.remove(os.path.join(carpeta, name))
        return redirect("/admin/brochures")
    grupos = []
    for key, label in (("pregrado", "Pensum pregrado"), ("posgrado", "Pensum posgrado"), ("otros", "Otros documentos")):
        carpeta = destinos[key]
        archivos = [{"name": f, **file_info(os.path.join(carpeta, f)),
                     "url": url_for("static", filename="brochures/" + f) if key == "otros" else url_for("pensum_archivo", nivel=key, filename=f)}
                    for f in sorted(os.listdir(carpeta)) if f.lower().endswith(".pdf")]
        grupos.append({"key": key, "label": label, "archivos": archivos})
    return render_template("admin_brochures.html", grupos=grupos, ok=request.args.get("ok"))


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", port=int(os.environ.get("PORT", 8000)))
