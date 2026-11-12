"""Carga de datos (Excel/JSON) con caché por fecha de modificación y lógica de homologación · Ibero.

El acta de la Ibero viene por créditos: créditos homologados, créditos del programa, créditos
pendientes y un estimado de semestres pendientes. Solo se usan las filas de modalidad virtual.
"""
import os
import re
import threading

import pandas as pd

from .storage import load_json, save_json
from .text import norm, similarity, program_similarity, pretty_name, strip_accents, tokens

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
# Los archivos que se suben desde el panel admin se guardan en data/archivos/ (carpeta que debe
# persistir entre despliegues). Si no existen allí, se usan los que vienen en el repositorio.
UPLOADS_DIR = os.path.join(DATA_DIR, "archivos")
ACTAS_NOMBRE = "Actas SENA Ibero.xlsx"
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "nombre_asesor": "",
    "telefono_prefijo": "57",
    "anio": 2027,
    "cohorte_actual": "1ra cohorte 2027",
    "creditos_por_semestre": 18,
    "modulos_ocultos": [],
}

# Columnas del acta (se buscan por palabras clave, sin importar tildes/espacios)
COLUMNAS = {
    "titulo_nombre": ("PROGRAMA SENA",),
    "titulo_nivel": ("TITULO SENA",),
    "programa": ("PROGRAMA A HOMOLOGAR",),
    "ch": ("CREDITOS HOMOLOGADOS",),
    "cp": ("CREDITOS DEL PROGRAMA",),
    "cpend": ("CREDITOS PENDIENTES",),
    "modalidad": ("MODALIDAD",),
    "sem": ("ESTIMADO EN SEMESTRES", "SEMESTRES Y/O"),
}
REQUERIDAS = ("titulo_nombre", "titulo_nivel", "programa", "ch", "cp")
ACTAS_COLUMNS = list(COLUMNAS)

# Nombres bonitos de los programas Ibero (clave = norm del nombre en el acta)
PROGRAMAS_IBERO = {
    "INGENIERIA INDUSTRIAL": "Ingeniería Industrial",
    "ADMINISTRACION DE EMPRESAS": "Administración de Empresas",
    "SEGURIDAD Y SALUD EN EL TRABAJO": "Seguridad y Salud en el Trabajo",
    "ADMINISTRACION EN SALUD": "Administración en Salud",
    "INGENIERIA DE SOFTWARE": "Ingeniería de Software",
    "MERCADEO Y PUBLICIDAD": "Mercadeo y Publicidad",
    "INGENIERIA EN SISTEMAS": "Ingeniería de Sistemas",
    "INGENIERIA DE SISTEMAS": "Ingeniería de Sistemas",
    "NEGOCIOS INTERNACIONALES": "Negocios Internacionales",
    "INGENIERIA EN CIENCIA DE DATOS": "Ingeniería en Ciencia de Datos",
    "ECONOMIA": "Economía",
    "DERECHO": "Derecho",
    "ADMINISTRACION FINANCIERA": "Administración Financiera",
    "TRABAJO SOCIAL": "Trabajo Social",
    "CONTADURIA PUBLICA": "Contaduría Pública",
    "COMUNICACION DIGITAL": "Comunicación Digital",
    "LICENCIATURA EN EDUCACION INFANTIL": "Licenciatura en Educación Infantil",
    "LICENCIATURA EN EDUCACION ESPECIAL": "Licenciatura en Educación Especial",
    "LICENCIATURA EN EDUCACIONESPECIAL": "Licenciatura en Educación Especial",
}


def ruta_archivo(nombre):
    """Ruta vigente de un archivo de datos: primero data/archivos/, luego la raíz del repositorio."""
    subido = os.path.join(UPLOADS_DIR, nombre)
    return subido if os.path.exists(subido) else os.path.join(BASE_DIR, nombre)


def ruta_subida(nombre):
    """Dónde guardar un archivo que se sube desde el admin."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    return os.path.join(UPLOADS_DIR, nombre)


def actas_file():
    return ruta_archivo(ACTAS_NOMBRE)


ACTAS_FILE = os.path.join(BASE_DIR, ACTAS_NOMBRE)


def _to_num(v, default=0.0):
    try:
        if v is None or pd.isna(v):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default=0):
    return int(round(_to_num(v, default)))


def _key(s):
    return re.sub(r"[^A-Z0-9/ ]", " ", strip_accents(str(s or "")).upper()).split()


def _hoja_y_encabezado(path):
    """Encuentra la hoja visible del acta y la fila de encabezados (la que dice 'Programa a Homologar')."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            for i, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True)):
                texto = " ".join(_key(" ".join(str(c) for c in row if c is not None)))
                if "HOMOLOGAR" in texto and "PROGRAMA" in texto:
                    return ws.title, i
        return wb.sheetnames[0], 0
    finally:
        wb.close()


def _mapear_columnas(cols):
    out = {}
    for c in cols:
        k = " ".join(_key(c))
        for campo, claves in COLUMNAS.items():
            if campo not in out and any(clave in k for clave in claves):
                out[campo] = c
                break
    return out


def nombre_programa(p):
    p = " ".join(str(p).split())
    return PROGRAMAS_IBERO.get(norm(p), pretty_name(p))


def titulo_sena(nombre, nivel):
    """('Gestión Logística', 'Tecnólogo') -> 'Tecnología en Gestión Logística'."""
    nombre = " ".join(str(nombre).split()).strip(" .")
    nivel_n = norm(nivel)
    tecnico = nivel_n.startswith("TECNICO")
    # Quitar prefijos que a veces vienen en el nombre
    nombre = re.sub(r"^(tecnolog[ií]a|t[eé]cnico|tecn[oó]logo)(\s+profesional)?(\s+en)?\s+", "", nombre, flags=re.I)
    base = pretty_name(nombre)
    return f"{'Técnico' if tecnico else 'Tecnología'} en {base[:1].upper() + base[1:]}"


def load_actas(path):
    hoja, header = _hoja_y_encabezado(path)
    raw = pd.read_excel(path, sheet_name=hoja, header=header)
    cols = _mapear_columnas(raw.columns)
    faltan = [c for c in REQUERIDAS if c not in cols]
    if faltan:
        raise ValueError(f"Faltan columnas en la hoja '{hoja}': {', '.join(faltan)}")
    df = pd.DataFrame({campo: raw[col] for campo, col in cols.items()})
    for c in ACTAS_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df.dropna(subset=["titulo_nombre", "programa"]).copy()
    # Solo modalidad virtual (incluye "Presencial y virtual")
    mod = df["modalidad"].fillna("virtual").astype(str).map(norm)
    df = df[mod.str.contains("VIRTUAL")].copy()
    df["titulo"] = [titulo_sena(n, v) for n, v in zip(df["titulo_nombre"], df["titulo_nivel"])]
    df["programa"] = df["programa"].map(nombre_programa)
    for c in ("ch", "cp", "cpend", "sem"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["cpend"] = df["cpend"].fillna(df["cp"] - df["ch"])
    df = df[df["cp"].fillna(0) > 0]
    # Si un título aparece varias veces para el mismo programa, se deja la mejor homologación
    df = df.sort_values("ch", ascending=False).drop_duplicates(subset=["titulo", "programa"]).reset_index(drop=True)
    df["_titulo_norm"] = df["titulo"].map(norm)
    return df[["titulo", "programa", "ch", "cp", "cpend", "sem", "_titulo_norm"]]


class DataStore:
    """Mantiene los datos en memoria y los recarga solo cuando cambia el archivo."""

    def __init__(self):
        self._lock = threading.RLock()
        self._cache = {}

    # ---------- caché genérica ----------
    def _cached(self, key, path, loader):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == mtime:
                return hit[1]
            value = loader() if mtime is not None else loader(missing=True)
            self._cache[key] = (mtime, value)
            return value

    def invalidate(self):
        with self._lock:
            self._cache.clear()

    # ---------- JSON ----------
    def json(self, name, default=None):
        path = os.path.join(DATA_DIR, name)
        return self._cached("json:" + name, path, lambda missing=False: load_json(path, default if default is not None else []))

    def save(self, name, data):
        save_json(os.path.join(DATA_DIR, name), data)
        with self._lock:
            self._cache.pop("json:" + name, None)

    @property
    def config(self):
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(self.json("config.json", {}) or {})
        return cfg

    def cohorte_de(self, programa, nivel="pre"):
        """Cohorte vigente del programa según la lista de precios (p. ej. '1ra cohorte 2027')."""
        p = self.match_precio(programa, nivel) if programa else None
        return cohorte_texto(p.get("cohorte_sena") or p.get("cohorte")) if p else self.config.get("cohorte_actual", "")

    def render(self, text, titulo=None, tipo=None):
        """Reemplaza variables de configuración dentro de los mensajes guardados.

        `{cohorte}` (o `{inicio}`) toma la cohorte vigente del programa según la lista de precios.
        """
        if not isinstance(text, str):
            return text
        cfg = self.config
        for var in ("{cohorte}", "{inicio}"):
            if var in text:
                text = text.replace(var, self.cohorte_de(titulo, "pos" if tipo == "pos" else "pre") if titulo
                                    else cfg.get("cohorte_actual", ""))
        valores = {"{anio}": str(cfg.get("anio", "")), "{cohorte_actual}": cfg.get("cohorte_actual", "")}
        for k, v in valores.items():
            text = text.replace(k, str(v))
        return text

    def render_list(self, items, tipo=None):
        out = []
        for m in items:
            t = m.get("nivel") or (tipo if tipo in ("pre", "pos") else "pre")
            out.append({**m, "titulo": self.render(m.get("titulo", "")),
                        "texto": self.render(m.get("texto", ""), m.get("titulo", ""), t)})
        return out

    def precios(self):
        return self.json("precios.json")

    def mensajes_programas(self):
        return self.json("mensajes_programas.json")

    def mensajes_sena(self):
        return self.json("mensajes_sena.json")

    # ---------- Actas ----------
    def actas(self):
        def load(missing=False):
            if missing:
                return pd.DataFrame(columns=["titulo", "programa", "ch", "cp", "cpend", "sem", "_titulo_norm"])
            return load_actas(actas_file())
        return self._cached("actas:" + actas_file(), actas_file(), load)

    def titulos(self):
        df = self.actas()
        return sorted(df["titulo"].unique().tolist(), key=norm)

    def programas_actas(self):
        df = self.actas()
        return sorted(df["programa"].unique().tolist())

    def creditos_por_semestre(self, programa):
        """Créditos promedio por semestre del programa, deducidos del acta (pendientes / semestres)."""
        df = self.actas()
        sub = df[(df["programa"] == programa) & (df["sem"] > 0)]
        if not sub.empty:
            r = (sub["cpend"] / sub["sem"]).median()
            if r and r > 0:
                return float(r)
        return float(self.config.get("creditos_por_semestre", 18) or 18)

    # ---------- Precios ----------
    def match_precio(self, programa, nivel="pre"):
        best, best_score = None, 0.0
        for p in self.precios():
            if nivel and p.get("nivel", "pre") != nivel:
                continue
            sc = program_similarity(programa, p.get("programa", ""))
            if sc > best_score:
                best, best_score = p, sc
        return best if best_score >= 0.66 else None


_ORD = {"1RA": "1ra", "2DA": "2da", "3RA": "3ra", "4TA": "4ta", "5TA": "5ta", "6TA": "6ta", "STA": "5ta"}


def cohorte_texto(v):
    """'5TA COHORTE_26' -> '5ta cohorte 2026'."""
    if not v:
        return ""
    m = re.match(r"\s*(\w+)\s*COHORTE[_\s-]*(\d{2,4})", str(v), re.I)
    if not m:
        return str(v)
    n, a = m.group(1).upper(), m.group(2)
    return f"{_ORD.get(n, n.lower())} cohorte {('20' + a) if len(a) == 2 else a}"


def rank_titles(query, titles, limit=8, threshold=0.62):
    scored = []
    for t in titles:
        sc = similarity(query, t)
        if sc >= threshold:
            scored.append((sc, t))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return [{"titulo": t, "score": round(s, 3)} for s, t in scored[:limit]]


_PREFIJOS = re.compile(r"^(TECNOLOGIA|TECNICO|TECNOLOGO)(\s+PROFESIONAL)?(\s+EN)?\s+")


def _sin_prefijo(s):
    return _PREFIJOS.sub("", norm(s))


def resolve_titles(query, titles):
    """Devuelve (titulos_elegidos, sugerencias, modo).

    modo: 'exacto' | 'contiene' | 'aproximado' | 'ninguno'
    """
    qn = norm(query)
    if not qn:
        return [], [], "ninguno"
    exact = [t for t in titles if norm(t) == qn]
    if exact:
        return exact, [], "exacto"
    qtok = tokens(query)
    if qtok:
        same = [t for t in titles if tokens(t) == qtok]
        if same:
            return same, [], "exacto"
    # Sin "Tecnología en / Técnico en": 'gestion logistica' encuentra técnico y tecnólogo
    qs = _sin_prefijo(query)
    base = [t for t in titles if _sin_prefijo(t) == qs]
    if base:
        return base, [], "exacto"
    contains = [t for t in titles if qn in norm(t)]
    if contains:
        return contains, [], "contiene"
    ranked = rank_titles(query, titles, limit=6, threshold=0.6)
    if ranked and ranked[0]["score"] >= 0.8:
        top = ranked[0]["titulo"]
        return [top], [r["titulo"] for r in ranked[1:]], "aproximado"
    return [], [r["titulo"] for r in ranked], "ninguno"


def semestres_de(store, programa, ch, cp, sem):
    """(total, homologados, faltantes) en semestres a partir de los créditos del acta."""
    cps = store.creditos_por_semestre(programa)
    precio = store.match_precio(programa)
    total = int(precio["semestres"]) if precio and precio.get("semestres") else max(1, int(round(cp / cps)))
    faltantes = int(round(sem)) if sem and sem > 0 else int(round((cp - ch) / cps))
    faltantes = min(max(faltantes, 1 if ch < cp else 0), total)
    return total, total - faltantes, faltantes


def calcular_precio(precio, homologados, faltantes):
    """Precios Ibero para egresados SENA: precio regular, precio SENA por semestre y pago del primer periodo."""
    valor = int(precio.get("valor") or 0)
    sena = precio.get("valor_sena")
    final = int(sena) if sena else int(precio.get("valor_final") or valor)
    pago1 = int(precio.get("pago_sena") or final) if sena else int(precio.get("valor_final") or final)
    desc = round((1 - final / valor) * 100) if valor else 0
    return {
        "id": precio.get("id"),
        "programa": precio.get("programa"),
        "valor": valor,
        "valor_lista": precio.get("valor_lista"),
        "descuento": desc,
        "descuento_sena": precio.get("descuento_sena"),
        "pronto_pago": precio.get("pronto_pago_sena") if sena else precio.get("pronto_pago"),
        "tipo_descuento": "SENA" if sena else "regular",
        "valor_final": final,
        "pago_primer_periodo": pago1,
        "semestres": precio.get("semestres"),
        "cohorte": cohorte_texto(precio.get("cohorte_sena") or precio.get("cohorte")),
        "inversion_total": final * faltantes - (final - pago1),
        "ahorro_homologacion": final * homologados,
        "ahorro_descuento": (valor - final) * faltantes,
        "ahorro_total": final * homologados + (valor - final) * faltantes,
    }


def build_programa(store, programa, ch, cp, cpend, sem, cfg):
    total, homologados, faltantes = semestres_de(store, programa, ch, cp, sem)
    precio = store.match_precio(programa)
    item = {
        "programa": programa,
        "programa_display": programa,
        "creditos_homologados": int(round(ch)),
        "creditos_programa": int(round(cp)),
        "creditos_pendientes": int(round(cpend if cpend == cpend and cpend is not None else cp - ch)),
        "semestres_estimados": round(float(sem), 1) if sem == sem and sem else None,
        "homologados": homologados,
        "faltantes": faltantes,
        "total": total,
        "precio": calcular_precio(precio, homologados, faltantes) if precio else None,
        "porcentaje": round(ch / cp * 100) if cp else 0,
    }
    from .pensum import buscar_pensum
    pen = buscar_pensum(programa)
    item["pensum"] = pen["archivo"] if pen else None
    item["inicio"] = item["precio"]["cohorte"] if item["precio"] and item["precio"]["cohorte"] else cfg.get("cohorte_actual", "")
    return item


def buscar_homologacion(store, query):
    df = store.actas()
    titles = df["titulo"].unique().tolist()
    elegidos, sugerencias, modo = resolve_titles(query, titles)
    cfg = store.config
    grupos = []
    for t in sorted(elegidos, key=norm):
        sub = df[df["titulo"] == t]
        programas = [build_programa(store, r["programa"], _to_num(r["ch"]), _to_num(r["cp"]), _to_num(r["cpend"], None),
                                    _to_num(r["sem"], None), cfg) for _, r in sub.iterrows()]
        programas.sort(key=lambda p: (-p["porcentaje"], p["programa_display"]))
        grupos.append({"titulo": t, "programas": programas})
    return {
        "query": query,
        "modo": modo,
        "grupos": grupos,
        "sugerencias": sugerencias,
        "total_programas": sum(len(g["programas"]) for g in grupos),
    }


def explorar_programas(store):
    """Vista inversa: por cada programa, qué títulos SENA homologan."""
    df = store.actas()
    out = []
    from .pensum import buscar_pensum
    for prog, sub in df.groupby("programa"):
        titulos = []
        for _, r in sub.iterrows():
            ch, cp = _to_num(r["ch"]), _to_num(r["cp"])
            _, h, f = semestres_de(store, prog, ch, cp, _to_num(r["sem"], None))
            titulos.append({"titulo": r["titulo"], "homologados": h, "faltantes": f,
                            "creditos": int(round(ch)), "creditos_programa": int(round(cp)),
                            "porcentaje": round(ch / cp * 100) if cp else 0})
        titulos.sort(key=lambda x: (-x["creditos"], norm(x["titulo"])))
        ps = [t["porcentaje"] for t in titulos] or [0]
        pen = buscar_pensum(prog)
        out.append({
            "programa": prog, "display": prog, "titulos": titulos, "total": len(titulos),
            "pensum": pen["archivo"] if pen else None,
            "max_porcentaje": max(ps), "min_porcentaje": min(ps),
            "promedio": round(sum(ps) / len(ps)), "precio": store.match_precio(prog),
        })
    out.sort(key=lambda p: -p["total"])
    return out


def validar_actas(path):
    try:
        df = load_actas(path)
    except Exception as e:  # noqa: BLE001
        return False, str(e), 0
    if df.empty:
        return False, "El archivo no tiene filas de modalidad virtual", 0
    return True, f"{len(df)} homologaciones virtuales ({df['titulo'].nunique()} títulos, {df['programa'].nunique()} programas)", len(df)
