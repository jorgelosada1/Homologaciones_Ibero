from core.data import (DataStore, buscar_homologacion, cohorte_texto, resolve_titles,
                       titulo_sena)
from core.messages import mensaje_homologacion, mensaje_precios
from core.text import fix_text_enc, money, norm, pretty_name, program_similarity, similarity

store = DataStore()


def test_norm_y_money():
    assert norm("Técnico en Gestión") == "TECNICO EN GESTION"
    assert money(2330000) == "$2.330.000"
    assert pretty_name("ADMINISTRACION DE EMPRESAS") == "Administración de Empresas"


def test_fix_encoding():
    assert fix_text_enc("T�cnico en Gesti�n") == "Técnico en Gestión"


def test_similarity_tolerante():
    assert similarity("tecnico en contabilizacion", "Técnico en Contabilización de Operaciones Comerciales y Financieras") > 0.85
    assert program_similarity("ADMINISTRACION DE EMPRESAS", "Administración en Salud") < 0.66


def test_titulo_sena():
    assert titulo_sena("Gestión Logística", "Tecnólogo") == "Tecnología en Gestión Logística"
    assert titulo_sena("Tecnología En Gestión Agroempresarial", "Tecnólogo") == "Tecnología en Gestión Agroempresarial"
    assert titulo_sena("apoyo administrativo En Salud", "Técnico") == "Técnico en Apoyo Administrativo en Salud"


def test_cohorte_texto():
    assert cohorte_texto("1RA COHORTE_27") == "Febrero 2027 · 1ra cohorte"
    assert cohorte_texto("2DA COHORTE_27") == "Abril 2027 · 2da cohorte"
    assert cohorte_texto("3RA COHORTE_27") == "Junio 2027 · 3ra cohorte"
    assert cohorte_texto("4TA COHORTE_27") == "Agosto 2027 · 4ta cohorte"
    assert cohorte_texto("5TA COHORTE_27") == "Octubre 2027 · 5ta cohorte"
    assert cohorte_texto("5TA COHORTE_26") == "Octubre 2026 · 5ta cohorte"
    # La configuración usa '1ra cohorte 2027' y un texto ya convertido no cambia
    assert cohorte_texto("1ra cohorte 2027") == "Febrero 2027 · 1ra cohorte"
    assert cohorte_texto("Febrero 2027 · 1ra cohorte") == "Febrero 2027 · 1ra cohorte"
    assert cohorte_texto("") == ""


def test_acta_solo_virtual():
    df = store.actas()
    assert len(df) > 500 and df["titulo"].nunique() > 200
    assert "Psicología" not in set(df["programa"])  # solo presencial en el acta
    assert {"Ingeniería Industrial", "Administración de Empresas", "Derecho"} <= set(df["programa"])


def test_busqueda_sin_prefijo_trae_tecnico_y_tecnologo():
    elegidos, _, modo = resolve_titles("gestion logistica", store.titulos())
    assert modo == "exacto"
    assert "Tecnología en Gestión Logística" in elegidos and "Técnico en Gestión Logística" in elegidos


def test_busqueda_con_error_de_escritura():
    res = buscar_homologacion(store, "tecnologia en gestion logistik")
    assert res["grupos"] and res["grupos"][0]["titulo"] == "Tecnología en Gestión Logística"


def test_busqueda_sin_resultado():
    res = buscar_homologacion(store, "astronauta espacial cuantico")
    assert res["grupos"] == []


def test_programa_por_creditos_y_precio_sena():
    res = buscar_homologacion(store, "Tecnología en Gestión Logística")
    p = next(x for x in res["grupos"][0]["programas"] if x["programa"] == "Ingeniería Industrial")
    assert p["creditos_homologados"] == 55 and p["creditos_programa"] == 158 and p["porcentaje"] == 35
    assert p["faltantes"] == 5 and p["homologados"] + p["faltantes"] == p["total"]
    assert p["precio"]["tipo_descuento"] == "SENA" and p["precio"]["valor_final"] == 2127965
    assert p["precio"]["pago_primer_periodo"] == 2054126
    assert p["inicio"] == "Octubre 2026 · 5ta cohorte"


def test_mensaje_formato_whatsapp():
    res = buscar_homologacion(store, "Tecnología en Gestión Logística")
    msg = mensaje_homologacion(res, store.config, nombre="Laura", incluir_precios=True, asesor="Jorge")
    assert "¡Hola Laura!" in msg and "Iberoamericana" in msg and "*INGENIERÍA INDUSTRIAL*" in msg
    assert "Créditos homologados: 55 de 158" in msg and "Precio SENA" in msg and "toda la carrera" in msg
    pr = mensaje_precios([p for g in res["grupos"] for p in g["programas"]], store.config)
    assert "Pronto pago" in pr


def test_precios_ibero():
    pre = [p for p in store.precios() if p["nivel"] == "pre"]
    pos = [p for p in store.precios() if p["nivel"] == "pos"]
    assert len(pre) == 22 and len(pos) >= 25
    der = next(p for p in pre if p["programa"] == "Derecho")
    assert der["valor_sena"] == 1801733 and der["valor_final"] == 1854284 and der["descuento_sena"] == 42
    assert all(p["valor_final"] > 0 for p in store.precios())


def test_mensajes_usan_cohorte_del_programa():
    out = store.render("Cohorte: {cohorte}", "Derecho – Virtual", "pre")
    assert out == "Cohorte: Octubre 2026 · 5ta cohorte"
    out = store.render("Cohorte: {cohorte}", "Administración en Salud – Virtual", "pre")
    assert out == "Cohorte: Febrero 2027 · 1ra cohorte"
    assert store.render("{cohorte_actual}") == "Febrero 2027 · 1ra cohorte"


def test_sena_solo_pregrado_con_homologacion():
    acta = set(store.actas()["programa"])
    for p in store.precios():
        if p["valor_sena"]:
            assert p["nivel"] == "pre" and p["programa"] in acta, p["programa"]
    assert all(p["valor_sena"] is None for p in store.precios() if p["nivel"] == "pos")
    msgs = store.mensajes_sena()
    assert msgs and all(m["nivel"] == "pre" for m in msgs)
    assert not any("Esp." in m["titulo"] or "Maestría" in m["titulo"] or "Matemáticas" in m["titulo"] for m in msgs)


def test_mensaje_sin_sena_no_promete_descuento():
    res = buscar_homologacion(store, "Tecnología en Gestión Logística")
    for g in res["grupos"]:
        for p in g["programas"]:
            p["precio"] = None
    msg = mensaje_homologacion(res, store.config)
    assert "SENA" not in msg.split("información")[-1]


def test_comercial_datos():
    c = store.json("comercial.json", {})
    assert [f["mes"] for f in c["fechas_ingreso"]] == ["Febrero 2027", "Abril 2027", "Junio 2027", "Agosto 2027", "Octubre 2027"]
    assert len(c["objeciones_generales"]) == 14 and len(c["objeciones_nivel"]) == 3
    assert sum(o["tipo"] == "pregrado" for o in c["objeciones_programa"]) == 18
    assert sum(o["tipo"] == "posgrado" for o in c["objeciones_programa"]) == 27
    assert sum(1 for o in c["objeciones_generales"] if o.get("p")) == 7  # tabla "pregunta para continuar"
    assert len(c["preguntas_filtro"]) == 7
    assert c["rombo"] == {"tasa_mensual": 1.85, "cuota_inicial": 15, "fee": 69000, "planes": [4, 6, 12], "valor_ejemplo": 2455236}
    plus_ids = {p["id"] for p in store.json("plus_pregrados.json", [])}
    assert all(o["plus"] in plus_ids for o in c["objeciones_programa"] if o.get("plus"))


def test_fechas_ingreso_marca_una_proxima():
    import app as app_module
    fechas = app_module.fechas_ingreso()
    assert len(fechas) == 5 and sum(f["proxima"] for f in fechas) <= 1
    assert fechas[0]["texto"] == "Febrero 2027 · 1ra cohorte"
