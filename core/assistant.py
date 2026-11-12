"""Asistente para asesores.

Funciona siempre en modo local (reglas + datos de actas/precios). Si se define la
variable de entorno ANTHROPIC_API_KEY y el paquete `anthropic` está instalado,
usa Claude con los mismos datos como contexto.
"""
import logging
import os

from .data import buscar_homologacion
from .text import money, norm, program_similarity, similarity, tokens

log = logging.getLogger(__name__)

ASSISTANT_MODEL = os.environ.get("ASSISTANT_MODEL", "claude-opus-5-5")

_FAQ = [
    (("pronto pago", "pronto"), "⚡ *Pronto pago:* aplica solo para el *primer periodo*. El descuento SENA sí se mantiene durante toda la carrera."),
    (("remarketing",), "🏷️ *Remarketing:* es el descuento de la lista regular (no SENA) y se mantiene durante la carrera."),
    (("credito", "creditos"), "📘 En la Ibero la homologación se mide en *créditos*: el acta dice cuántos créditos se homologan, cuántos tiene el programa y cuántos quedan pendientes, con un estimado de semestres por cursar."),
]


def _fmt_homologacion(res, cfg):
    lines = []
    for g in res["grupos"]:
        lines.append(f"🎓 *{g['titulo']}* homologa en:")
        for p in g["programas"]:
            l = (f"• *{p['programa_display']}*: {p['creditos_homologados']} de {p['creditos_programa']} créditos "
                 f"({p['porcentaje']}%), ≈{p['faltantes']} semestres por cursar")
            pr = p.get("precio")
            if pr:
                l += (f" — Precio SENA {money(pr['valor_final'])}/sem" if pr.get("tipo_descuento") == "SENA"
                      else f" — {money(pr['valor_final'])}/sem")
            lines.append(l)
    return "\n".join(lines)


def _match_title(question, titles):
    best, best_sc = None, 0.0
    qtok = set(tokens(question))
    for t in titles:
        tt = tokens(t)
        if not tt:
            continue
        sc = similarity(t, question)
        # recompensa títulos cuyos tokens aparecen casi todos en la pregunta
        cover = sum(1 for x in tt if x in qtok) / len(tt)
        sc = max(sc, cover * 0.95)
        if sc > best_sc or (sc == best_sc and best and len(t) > len(best)):
            best, best_sc = t, sc
    return best if best_sc >= 0.75 else None


def _fmt_precio(p, store):
    from .data import cohorte_texto
    lineas = [f"💰 *{p['programa']}* ({'posgrado' if p.get('nivel') == 'pos' else 'pregrado'} virtual)",
              f"• Valor regular: {money(p['valor'])}",
              f"• Precio final (no SENA): *{money(p['valor_final'])}*"]
    if p.get("valor_sena"):
        lineas.append(f"• Precio SENA ({p['descuento_sena']}% SENA): *{money(p['valor_sena'])}*")
        if p.get("pago_sena") and p["pago_sena"] < p["valor_sena"]:
            lineas.append(f"• Pronto pago SENA (primer periodo): {money(p['pago_sena'])}")
    coh = cohorte_texto(p.get("cohorte_sena") or p.get("cohorte"))
    if coh:
        lineas.append(f"• Cohorte: {coh}")
    return "\n".join(lineas)


def local_answer(question, store):
    q = norm(question)
    if not q:
        return "Escríbeme tu pregunta 🙂"

    titulo = _match_title(question, store.titulos())
    if titulo:
        res = buscar_homologacion(store, titulo)
        if res["grupos"]:
            return _fmt_homologacion(res, store.config) + "\n\n💡 Recuerda: el descuento SENA se mantiene durante toda la carrera."

    for p in sorted(store.precios(), key=lambda x: -len(tokens(x["programa"], {"VIRTUAL"}))):
        ptoks = tokens(p["programa"], {"VIRTUAL", "ESP"})
        if ptoks and all(any(similarity(t, w) >= 0.85 for w in tokens(question)) for t in ptoks):
            return _fmt_precio(p, store)

    for keys, ans in _FAQ:
        if any(norm(k) in q for k in keys):
            return ans

    if any(k in q for k in ("PRECIO", "VALOR", "CUESTA", "COSTO")):
        top = sorted([p for p in store.precios() if p.get("valor_sena")], key=lambda p: p["valor_sena"])[:6]
        return "💰 Algunos precios SENA por semestre:\n" + "\n".join(
            f"• {p['programa']}: {money(p['valor_sena'])}" for p in top) + "\n\nPregúntame por un programa específico."

    return ("Puedo ayudarte con:\n• Qué homologa un título SENA (ej: *¿qué homologa Tecnología en Gestión Logística?*)\n"
            "• Precios de un programa (ej: *precio de Ingeniería Industrial*)\n• Pronto pago, remarketing y créditos")


def _context(store):
    from .data import cohorte_texto
    df = store.actas()
    filas = [f"{r['titulo']} | {r['programa']} | {int(r['ch'])} | {int(r['cp'])} | {r['sem'] if r['sem'] == r['sem'] else '?'}"
             for _, r in df.sort_values(["titulo", "programa"]).iterrows()]
    precios = [f"{'Pregrado' if p.get('nivel', 'pre') == 'pre' else 'Posgrado'} | {p['programa']} | {p['valor']} | {p['valor_final']} | "
               f"{p.get('valor_sena') or 'no aplica'} | {p.get('pago_sena') or '-'} | {cohorte_texto(p.get('cohorte_sena') or p.get('cohorte'))}"
               for p in store.precios()]
    return (
        "Eres el asistente interno de los asesores comerciales de la Corporación Universitaria Iberoamericana (Ibero, Colombia) "
        "para homologaciones de egresados SENA en modalidad virtual. Responde en español, de forma breve y práctica, usando el "
        "formato de WhatsApp (*negrilla*). Usa SOLO los datos de abajo; si algo no está, dilo y sugiere a quién consultar.\n\n"
        "REGLAS: el descuento SENA aplica solo en las carreras de pregrado con homologación (no en posgrado ni en las carreras sin precio SENA) y se mantiene durante toda la carrera; el pronto pago aplica solo para el primer periodo; "
        "el remarketing (lista regular) se mantiene durante la carrera; valores sujetos a cambios institucionales.\n\n"
        "ACTAS DE HOMOLOGACIÓN VIRTUAL (título SENA | programa | créditos homologados | créditos del programa | semestres estimados por cursar):\n"
        + "\n".join(filas)
        + "\n\nPRECIOS POR SEMESTRE (nivel | programa | valor regular COP | precio final no SENA | precio SENA | pago primer periodo SENA con pronto pago | cohorte):\n"
        + "\n".join(precios)
    )


def claude_available():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def claude_answer(question, history, store):
    import anthropic

    client = anthropic.Anthropic()
    messages = []
    for m in (history or [])[-10:]:
        role = "assistant" if m.get("role") == "assistant" else "user"
        text = str(m.get("content", ""))[:4000]
        if text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": question[:4000]})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)

    response = client.beta.messages.create(
        model=ASSISTANT_MODEL,
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system=[{"type": "text", "text": _context(store), "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    if response.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None


def answer(question, history, store):
    """Devuelve (texto, fuente) donde fuente es 'claude' o 'local'."""
    if claude_available():
        try:
            text = claude_answer(question, history, store)
            if text:
                return text, "claude"
        except Exception as e:  # cualquier fallo de red/API cae al modo local
            log.warning("Asistente Claude no disponible: %s", e)
    return local_answer(question, store), "local"
