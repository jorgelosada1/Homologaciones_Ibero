"""Generación de mensajes listos para WhatsApp (formato *negrilla* / _cursiva_) · Ibero."""
from .text import money

U = "Corporación Universitaria Iberoamericana"


def _saludo(nombre, asesor):
    if not nombre and not asesor:
        return ""
    s = f"¡Hola{(' ' + nombre.strip()) if nombre else ''}! 👋"
    if asesor:
        s += f" Te saluda {asesor.strip()} de la *{U}*."
    return s + "\n\n"


def _sem(n):
    return f"{n} semestre{'s' if n != 1 else ''}"


def mensaje_homologacion(resultado, cfg, nombre="", incluir_precios=False, asesor=None):
    """Mensaje a partir de `buscar_homologacion`."""
    query = resultado.get("query", "")
    grupos = resultado.get("grupos", [])
    if not grupos:
        return f"No encontré homologaciones para el título *{query}*."
    asesor = cfg.get("nombre_asesor", "") if asesor is None else asesor
    texto = _saludo(nombre, asesor)
    total = 0
    for g in grupos:
        texto += f"*{g['titulo']}*\nCon este título puedes homologar en la Ibero (100% virtual):\n\n"
        for p in g["programas"]:
            total += 1
            texto += (
                f"🔹 *{p['programa_display'].upper()}*\n"
                f"➡ Créditos homologados: {p['creditos_homologados']} de {p['creditos_programa']} ({p['porcentaje']}%)\n"
                f"➡ Tiempo estimado por cursar: {_sem(p['faltantes'])}\n"
            )
            pr = p.get("precio")
            if incluir_precios and pr:
                if pr.get("tipo_descuento") == "SENA":
                    texto += (f"💰 Valor regular semestre: {money(pr['valor'])}\n"
                              f"✅ *Precio SENA: {money(pr['valor_final'])} por semestre*\n")
                    if pr.get("pago_primer_periodo") and pr["pago_primer_periodo"] < pr["valor_final"]:
                        texto += f"⚡ Con pronto pago, primer periodo: {money(pr['pago_primer_periodo'])}\n"
                else:
                    texto += f"💰 Valor semestre: {money(pr['valor_final'])}\n"
            if incluir_precios and p.get("inicio"):
                texto += f"📅 Cohorte: {p['inicio']}\n"
            texto += "\n"
    texto += ("¿Te gustaría recibir más información sobre este programa?\n\n" if total == 1
              else "¿De cuál de estas opciones te gustaría recibir más información?\n\n")
    texto += "💡 *El descuento SENA se mantiene durante toda la carrera.*"
    return texto


def mensaje_precios(programas, cfg):
    con_precio = [p for p in programas if p.get("precio")]
    if not con_precio:
        return "No se encontraron precios para estos programas."
    texto = "🎓 *Precios Ibero · egresados SENA*\n\n"
    for p in con_precio:
        pr = p["precio"]
        texto += f"📌 *{pr['programa']}*\n💰 Valor regular: {money(pr['valor'])}\n"
        if pr.get("tipo_descuento") == "SENA":
            texto += f"✅ *Precio SENA: {money(pr['valor_final'])} por semestre*\n"
            if pr.get("pago_primer_periodo") and pr["pago_primer_periodo"] < pr["valor_final"]:
                texto += f"⚡ Pronto pago (primer periodo): {money(pr['pago_primer_periodo'])}\n"
        else:
            texto += f"✅ *Valor semestre: {money(pr['valor_final'])}*\n"
        texto += f"📚 Tiempo estimado por cursar: {_sem(p['faltantes'])}\n"
        if p.get("inicio"):
            texto += f"📅 Cohorte: *{p['inicio']}*\n"
        texto += "\n"
    texto += ("_El descuento SENA se mantiene durante toda la carrera. El pronto pago aplica solo para el primer periodo. "
              "Valores sujetos a cambios institucionales._")
    return texto
