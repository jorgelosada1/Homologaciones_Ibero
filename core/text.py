"""Utilidades de texto: corrección de encoding, normalización sin tildes y búsqueda difusa."""
import re
import unicodedata
from difflib import SequenceMatcher

U = "�"

# Reemplazos conocidos de palabras con caracteres rotos (�)
_FIXES = [
    ("T{U}CNICO", "TÉCNICO"), ("T{U}cnico", "Técnico"), ("t{U}cnico", "técnico"),
    ("TECNOLOG{U}A", "TECNOLOGÍA"), ("Tecnolog{U}a", "Tecnología"), ("tecnolog{U}a", "tecnología"),
    ("Gest{U}n", "Gestión"), ("GESTI{U}N", "GESTIÓN"),
    ("L{U}nea", "Línea"), ("L{U}NEA", "LÍNEA"),
    ("Asesor{U}a", "Asesoría"), ("ASESOR{U}A", "ASESORÍA"),
    ("N{U}mina", "Nómina"), ("N{U}MINA", "NÓMINA"),
    ("Log{U}stica", "Logística"), ("LOG{U}STICA", "LOGÍSTICA"),
    ("Bogot{U}", "Bogotá"), ("BOGOT{U}", "BOGOTÁ"),
    ("Gal{U}n", "Galán"), ("GAL{U}N", "GALÁN"),
    ("Fontib{U}n", "Fontibón"), ("FONTIB{U}N", "FONTIBÓN"),
    ("Facatativ{U}", "Facatativá"), ("FACATATIV{U}", "FACATATIVÁ"),
    ("Zipaquir{U}", "Zipaquirá"), ("ZIPAQUIR{U}", "ZIPAQUIRÁ"),
    ("C{U}digo", "Código"), ("C{U}DIGO", "CÓDIGO"),
    ("Andr{U}s", "Andrés"), ("ANDR{U}S", "ANDRÉS"),
    ("Hern{U}ndez", "Hernández"), ("HERN{U}NDEZ", "HERNÁNDEZ"),
    ("Mart{U}nez", "Martínez"), ("MART{U}NEZ", "MARTÍNEZ"),
    ("Garc{U}a", "García"), ("GARC{U}A", "GARCÍA"),
    ("R{U}os", "Ríos"), ("R{U}OS", "RÍOS"),
    ("D{U}az", "Díaz"), ("D{U}AZ", "DÍAZ"),
    ("Guti{U}rrez", "Gutiérrez"), ("GUTI{U}RREZ", "GUTIÉRREZ"),
    ("Mu{U}oz", "Muñoz"), ("MU{U}OZ", "MUÑOZ"),
    ("Pe{U}a", "Peña"), ("PE{U}A", "PEÑA"),
    ("Ni{U}o", "Niño"), ("NI{U}O", "NIÑO"),
]
_FIXES = [(a.format(U=U), b) for a, b in _FIXES]

_REGEX_FIXES = [
    (re.compile(rf"i{U}n\b"), "ión"), (re.compile(rf"I{U}N\b"), "IÓN"),
    (re.compile(rf"c{U}n\b"), "ción"), (re.compile(rf"C{U}N\b"), "CIÓN"),
    (re.compile(rf"s{U}n\b"), "sión"), (re.compile(rf"S{U}N\b"), "SIÓN"),
    (re.compile(rf"g{U}a\b"), "gía"), (re.compile(rf"G{U}A\b"), "GÍA"),
    (re.compile(rf"r{U}a\b"), "ría"), (re.compile(rf"R{U}A\b"), "RÍA"),
    (re.compile(rf"T{U}c"), "Téc"), (re.compile(rf"t{U}c"), "téc"), (re.compile(rf"T{U}C"), "TÉC"),
]


def fix_text_enc(s):
    """Corrige caracteres rotos (\\ufffd) en texto en español."""
    if not isinstance(s, str) or U not in s:
        return s
    for a, b in _FIXES:
        s = s.replace(a, b)
    for rx, rep in _REGEX_FIXES:
        s = rx.sub(rep, s)
    return s.replace(U, "")


def clean_df(df):
    """Limpia nombres de columnas y celdas de texto de un DataFrame."""
    df.columns = [fix_text_enc(str(c)).strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object or str(df[col].dtype).startswith("str"):
            df[col] = df[col].apply(fix_text_enc)
    return df


def strip_accents(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def norm(s):
    """Normaliza texto: sin tildes, mayúsculas y solo alfanuméricos separados por un espacio."""
    if s is None:
        return ""
    s = strip_accents(s).upper()
    s = re.sub(r"[^A-Z0-9Ñ]+", " ", s)
    return s.strip()


STOPWORDS = {"EN", "DE", "LA", "EL", "Y", "DEL", "LOS", "LAS", "PARA", "CON", "A", "E", "O", "U", "AL", "POR"}

ABBREV = {
    "LIC": "LICENCIATURA", "ING": "INGENIERIA", "ADM": "ADMINISTRACION", "ADMON": "ADMINISTRACION",
    "TEC": "TECNOLOGIA", "TECNOLOGO": "TECNOLOGIA", "TECNICA": "TECNICO", "INTERN": "INTERNACIONALES",
    "ADMINITRACION": "ADMINISTRACION", "SST": "SEGURIDAD SALUD TRABAJO",
}


def tokens(s, drop=()):
    out = []
    for t in norm(s).split():
        t = ABBREV.get(t, t)
        for part in t.split():
            if part not in STOPWORDS and part not in drop and len(part) > 1:
                out.append(part)
    return out


def _tok_match(a, b):
    if a == b:
        return 1.0
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
        return 0.92
    r = SequenceMatcher(None, a, b).ratio()
    return r if r >= 0.8 else 0.0


def similarity(query, candidate):
    """Puntaje 0..1 de qué tan bien `query` describe `candidate` (tolerante a tildes y typos)."""
    qn, cn = norm(query), norm(candidate)
    if not qn or not cn:
        return 0.0
    if qn == cn:
        return 1.0
    if qn in cn:
        return 0.9 + 0.09 * (len(qn) / len(cn))
    qt, ct = tokens(query), tokens(candidate)
    if not qt or not ct:
        return 0.0
    total = 0.0
    for q in qt:
        total += max((_tok_match(q, c) for c in ct), default=0.0)
    coverage = total / len(qt)
    seq = SequenceMatcher(None, qn, cn).ratio()
    return round(max(coverage * 0.85, seq * 0.8), 4)


def program_similarity(a, b):
    """Similitud simétrica entre nombres de programa (para cruzar actas con precios)."""
    drop = {"VIRTUAL", "PROFESIONAL"}
    ta, tb = set(tokens(a, drop)), set(tokens(b, drop))
    if not ta or not tb:
        return 0.0
    hits = 0.0
    for x in ta:
        hits += max((_tok_match(x, y) for y in tb), default=0.0)
    return hits / max(len(ta), len(tb))


_SMALL = {"de", "en", "y", "la", "el", "del", "los", "las", "para", "con", "a", "e"}
_ACCENT_WORDS = {
    "administracion": "administración", "adminitracion": "administración", "ingenieria": "ingeniería",
    "educacion": "educación", "tecnologia": "tecnología", "gestion": "gestión", "logistica": "logística",
    "publica": "pública", "economia": "economía", "psicologia": "psicología", "sociologia": "sociología",
    "comunicacion": "comunicación", "contaduria": "contaduría", "biomedica": "biomédica",
    "grafico": "gráfico", "diseno": "diseño", "produccion": "producción", "informacion": "información",
    "tecnico": "técnico", "credito": "crédito", "electronica": "electrónica", "mecanica": "mecánica",
    "maestria": "maestría", "auditoria": "auditoría", "pedagogia": "pedagogía", "pedagogica": "pedagógica",
    "revisoria": "revisoría", "analitica": "analítica", "epidemiologia": "epidemiología", "innovacion": "innovación",
    "matematicas": "matemáticas", "informatica": "informática", "especializacion": "especialización",
    "direccion": "dirección", "comunicacion": "comunicación", "logistica": "logística", "ganaderia": "ganadería",
    "propedeuticos": "propedéuticos", "practicas": "prácticas", "sociologia": "sociología",
}


def pretty_name(s):
    """'ADMINISTRACION DE EMPRESAS' -> 'Administración de Empresas'."""
    if not s:
        return ""
    words = str(s).strip().split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        lw = _ACCENT_WORDS.get(strip_accents(lw), lw) if strip_accents(lw) == lw else lw
        if i > 0 and lw in _SMALL:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    return " ".join(out)


def money(v):
    """Formato pesos colombianos: 2330000 -> '$2.330.000'."""
    try:
        return "$" + f"{int(round(float(v))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"
